"""Relational persistence helpers for SaaS AI model/pricing backoffice data."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from typing import Any
import uuid

from rasai.ai_model_catalog import AiModelCatalog
from rasai.ai_model_saas import model_catalog_to_toml
from rasai.ai_pricing_catalog import PricingCatalog
from rasai.ai_pricing_saas import pricing_catalog_to_toml
from rasai.provider_registry import provider_registrations

_CATALOG_STATES = frozenset({"DRAFT", "VALIDATED", "PUBLISHED", "DISABLED"})
_ADAPTER_TYPES = {
    "OPENAI": "RESPONSES_API",
    "DEEPSEEK": "RESPONSES_API",
    "MIMO": "RESPONSES_API",
    "XAI": "RESPONSES_API",
    "QWEN": "OPENAI_COMPATIBLE_CHAT",
    "GEMINI": "GEMINI_INTERACTIONS",
    "ANTHROPIC": "ANTHROPIC_MESSAGES",
    "COPILOT": "GITHUB_COPILOT_SDK",
}


def _now(value: datetime | None = None) -> str:
    instant = value or datetime.now(timezone.utc)
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=timezone.utc)
    return instant.astimezone(timezone.utc).isoformat()


def _state(value: str) -> str:
    state = value.strip().upper()
    if state not in _CATALOG_STATES:
        raise ValueError("catalog status must be DRAFT, VALIDATED, PUBLISHED or DISABLED")
    return state


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sync_ai_providers(connection: Any, *, at: datetime | None = None) -> None:
    timestamp = _now(at)
    with connection:
        for item in provider_registrations():
            connection.execute(
                """INSERT INTO ai_providers(
                       provider_code,display_name,adapter_type,enabled,explicit_only,
                       credential_env,model_env,reasoning_env,endpoint_env,
                       documentation_url,credential_url,created_at,updated_at
                   ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(provider_code) DO UPDATE SET
                       display_name=EXCLUDED.display_name,
                       adapter_type=EXCLUDED.adapter_type,
                       enabled=EXCLUDED.enabled,
                       explicit_only=EXCLUDED.explicit_only,
                       credential_env=EXCLUDED.credential_env,
                       model_env=EXCLUDED.model_env,
                       reasoning_env=EXCLUDED.reasoning_env,
                       endpoint_env=EXCLUDED.endpoint_env,
                       documentation_url=EXCLUDED.documentation_url,
                       credential_url=EXCLUDED.credential_url,
                       updated_at=EXCLUDED.updated_at""",
                (
                    item.provider_name,
                    item.display_name,
                    _ADAPTER_TYPES[item.provider_name],
                    1,
                    1 if item.explicit_only else 0,
                    item.key_env,
                    item.model_env,
                    item.reasoning_env,
                    item.endpoint_env,
                    item.documentation_url,
                    item.credential_url,
                    timestamp,
                    timestamp,
                ),
            )


def _existing_hash(connection: Any, table: str, catalog_version: str) -> tuple[str | None, str | None]:
    row = connection.execute(
        f"SELECT status,sha256 FROM {table} WHERE catalog_version=?",
        (catalog_version,),
    ).fetchone()
    if row is None:
        return None, None
    return str(row[0]), str(row[1]) if row[1] is not None else None


def _guard_published(existing_status: str | None, existing_hash: str | None, new_hash: str) -> None:
    if existing_status == "PUBLISHED" and existing_hash and existing_hash != new_hash:
        raise ValueError("published AI catalog version is immutable; create a new catalog_version")


def _catalog_event(
    connection: Any,
    *,
    kind: str,
    version: str,
    action: str,
    actor_user_id: str | None,
    details: dict[str, Any],
    at: datetime | None,
) -> None:
    connection.execute(
        """INSERT INTO ai_catalog_events(
               event_id,catalog_kind,catalog_version,action,actor_user_id,details_json,occurred_at
           ) VALUES(?,?,?,?,?,?,?)""",
        (
            str(uuid.uuid4()),
            kind,
            version,
            action,
            actor_user_id,
            json.dumps(details, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
            _now(at),
        ),
    )


def publish_model_catalog(
    connection: Any,
    catalog: AiModelCatalog,
    *,
    status: str = "PUBLISHED",
    actor_user_id: str | None = None,
    at: datetime | None = None,
) -> str:
    state = _state(status)
    payload = model_catalog_to_toml(catalog)
    digest = _digest(payload)
    version = catalog.metadata.catalog_version
    sync_ai_providers(connection, at=at)
    existing_status, existing_hash = _existing_hash(connection, "ai_model_catalogs", version)
    _guard_published(existing_status, existing_hash, digest)
    timestamp = _now(at)
    with connection:
        connection.execute(
            """INSERT INTO ai_model_catalogs(
                   catalog_version,schema_version,reference_date,verified_on,review_recommended_on,
                   status,sha256,created_by,created_at,published_at
               ) VALUES(?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(catalog_version) DO UPDATE SET
                   schema_version=EXCLUDED.schema_version,
                   reference_date=EXCLUDED.reference_date,
                   verified_on=EXCLUDED.verified_on,
                   review_recommended_on=EXCLUDED.review_recommended_on,
                   status=EXCLUDED.status,
                   sha256=EXCLUDED.sha256,
                   published_at=EXCLUDED.published_at""",
            (
                version,
                catalog.metadata.schema_version,
                catalog.metadata.reference_date,
                catalog.metadata.verified_on,
                catalog.metadata.review_recommended_on,
                state,
                digest,
                actor_user_id,
                timestamp,
                timestamp if state == "PUBLISHED" else None,
            ),
        )
        connection.execute("DELETE FROM ai_models WHERE catalog_version=?", (version,))
        for item in catalog.models:
            connection.execute(
                """INSERT INTO ai_models(
                       catalog_version,provider_code,model_code,enabled,selectable,adapter_default,
                       public_default,auto_eligible,qualification,rasai_class,rank,recommended_depth,
                       recommended_use,reasoning_values_json,default_reasoning,capabilities_json,
                       context_window,max_output_tokens,effective_from,effective_until,source_reference
                   ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    version,
                    item.provider,
                    item.model,
                    1 if item.enabled else 0,
                    1 if item.selectable else 0,
                    1 if item.adapter_default else 0,
                    1 if item.public_default else 0,
                    1 if item.auto_eligible else 0,
                    item.qualification,
                    item.rasai_class,
                    item.rank,
                    item.recommended_depth,
                    item.recommended_use,
                    json.dumps(item.reasoning_values, ensure_ascii=False),
                    item.default_reasoning,
                    json.dumps(item.capabilities, ensure_ascii=False),
                    item.context_window,
                    item.max_output_tokens,
                    item.effective_from,
                    item.effective_until,
                    item.source_reference,
                ),
            )
        _catalog_event(
            connection,
            kind="MODEL",
            version=version,
            action=state,
            actor_user_id=actor_user_id,
            details={"sha256": digest, "models": len(catalog.models)},
            at=at,
        )
    return digest


def publish_pricing_catalog(
    connection: Any,
    catalog: PricingCatalog,
    *,
    status: str = "PUBLISHED",
    actor_user_id: str | None = None,
    at: datetime | None = None,
) -> str:
    state = _state(status)
    payload = pricing_catalog_to_toml(catalog)
    digest = _digest(payload)
    version = catalog.metadata.catalog_version
    sync_ai_providers(connection, at=at)
    existing_status, existing_hash = _existing_hash(connection, "ai_pricing_catalogs", version)
    _guard_published(existing_status, existing_hash, digest)
    timestamp = _now(at)
    with connection:
        connection.execute(
            """INSERT INTO ai_pricing_catalogs(
                   catalog_version,schema_version,reference_date,verified_on,review_recommended_on,
                   status,sha256,created_by,created_at,published_at
               ) VALUES(?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(catalog_version) DO UPDATE SET
                   schema_version=EXCLUDED.schema_version,
                   reference_date=EXCLUDED.reference_date,
                   verified_on=EXCLUDED.verified_on,
                   review_recommended_on=EXCLUDED.review_recommended_on,
                   status=EXCLUDED.status,
                   sha256=EXCLUDED.sha256,
                   published_at=EXCLUDED.published_at""",
            (
                version,
                catalog.metadata.schema_version,
                catalog.metadata.reference_date,
                catalog.metadata.verified_on,
                catalog.metadata.review_recommended_on,
                state,
                digest,
                actor_user_id,
                timestamp,
                timestamp if state == "PUBLISHED" else None,
            ),
        )
        connection.execute("DELETE FROM ai_pricing_rules WHERE catalog_version=?", (version,))
        for policy in catalog.models:
            for rule in policy.rules:
                connection.execute(
                    """INSERT INTO ai_pricing_rules(
                           catalog_version,provider_code,model_code,pricing_model,reasoning_billing,
                           region,currency,source_reference,rule_id,context,priority,effective_from,
                           effective_until,input_tokens_gte,input_tokens_gt,input_tokens_lte,input_tokens_lt,
                           weekdays_utc_json,time_windows_utc_json,input_price_per_million,
                           cached_input_price_per_million,output_price_per_million
                       ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        version,
                        policy.provider,
                        policy.model,
                        policy.pricing_model,
                        policy.reasoning_billing,
                        policy.region,
                        policy.currency,
                        policy.source_reference,
                        rule.rule_id,
                        rule.context,
                        rule.priority,
                        rule.effective_from,
                        rule.effective_until,
                        rule.input_tokens_gte,
                        rule.input_tokens_gt,
                        rule.input_tokens_lte,
                        rule.input_tokens_lt,
                        json.dumps(rule.weekdays_utc),
                        json.dumps(rule.time_windows_utc),
                        rule.input_price_per_million,
                        rule.cached_input_price_per_million,
                        rule.output_price_per_million,
                    ),
                )
        _catalog_event(
            connection,
            kind="PRICING",
            version=version,
            action=state,
            actor_user_id=actor_user_id,
            details={"sha256": digest, "models": len(catalog.models)},
            at=at,
        )
    return digest


def record_job_catalog_snapshot(
    connection: Any,
    *,
    job_id: str,
    model_catalog_version: str,
    model_catalog_sha256: str,
    pricing_catalog_version: str,
    pricing_catalog_sha256: str,
    at: datetime | None = None,
) -> None:
    with connection:
        connection.execute(
            """INSERT INTO ai_job_catalog_snapshots(
                   job_id,model_catalog_version,model_catalog_sha256,
                   pricing_catalog_version,pricing_catalog_sha256,created_at
               ) VALUES(?,?,?,?,?,?)
               ON CONFLICT(job_id) DO NOTHING""",
            (
                job_id,
                model_catalog_version,
                model_catalog_sha256,
                pricing_catalog_version,
                pricing_catalog_sha256,
                _now(at),
            ),
        )
