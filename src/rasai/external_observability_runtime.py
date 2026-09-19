"""Safe external observability composed into audit finalization.

The runtime is intentionally non-blocking: provider/public-index failures are recorded
as service outcomes and never turn website readiness into a failure. All external
records go to observability.db; audit.db receives only the existing service-run status
metadata needed by the standards report. Durable AuditJob payloads contain only
non-secret controls; credentials remain worker/secret-store concerns.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
import os
import sqlite3
import sys
from typing import Any, Mapping

from rasai.external_observability_policy import (
    CLARITY_DAYS_ENV,
    CLARITY_DIMENSIONS_ENV,
    CLARITY_ENABLED_ENV,
    CLARITY_TOKEN_ENV,
    COMMON_CRAWL_ENABLED_ENV,
    COMMON_CRAWL_INDEX_COUNT_ENV,
    COMMON_CRAWL_MAX_URLS_ENV,
    CRUX_HISTORY_ENABLED_ENV,
    DEFAULT_CLARITY_DAYS,
    DEFAULT_CLARITY_DIMENSIONS,
    DEFAULT_COMMON_CRAWL_INDEX_COUNT,
    DEFAULT_COMMON_CRAWL_MAX_URLS,
    clarity_days,
    clarity_dimensions,
    common_crawl_index_count,
    common_crawl_max_urls,
    dimensions_csv,
)
from rasai.observability.crux_history import collect_crux_history
from rasai.observability.external_sources import collect_clarity_insights, collect_common_crawl_history
from rasai.secret_safety import redact_text
from rasai.standards_service_registry import (
    DEFAULT_STANDARDS_TIMEOUT_SECONDS,
    STANDARDS_TIMEOUT_ENV,
    service,
    service_state,
)

_LOGGER = logging.getLogger(__name__)
CRUX_KEY_ENV = "RASAI_CRUX_API_KEY"
_DEVICE_TO_CRUX = {"mobile": "PHONE", "desktop": "DESKTOP", "tablet": "TABLET"}
_SERVICE_IDS = ("crux-history", "microsoft-clarity", "common-crawl")

_EXTERNAL_PAYLOAD_TO_ENV = {
    "crux_history_enabled": CRUX_HISTORY_ENABLED_ENV,
    "clarity_enabled": CLARITY_ENABLED_ENV,
    "common_crawl_enabled": COMMON_CRAWL_ENABLED_ENV,
}
_EXTERNAL_FIELDS = frozenset({
    *_EXTERNAL_PAYLOAD_TO_ENV,
    "clarity_days",
    "clarity_dimensions",
    "common_crawl_max_urls",
    "common_crawl_index_count",
})


def install_service_contract() -> None:
    """Extend the secret-free AuditJob contract with external-observability controls."""
    from rasai import audit_execution_contract as contract

    if getattr(contract, "_rasai_external_observability_contract", False):
        _rebind_contract_consumers(contract)
        return

    original_options = contract.audit_job_options
    original_defaults = contract.audit_job_defaults
    original_normalize = contract.normalize_audit_job_payload
    original_environment = contract.audit_job_environment_overrides
    original_fields = contract.AUDIT_JOB_FIELDS
    contract.AUDIT_JOB_FIELDS = frozenset((*original_fields, *_EXTERNAL_FIELDS))

    def options_with_external_observability():
        options = list(original_options())
        options.extend((
            contract.AuditJobOption(
                "crux_history_enabled", None, "boolean",
                required_when="Auto requires RASAI_CRUX_API_KEY in the worker/secret store.",
                description="null/omitted=auto by credential; false=off; true=requested explicitly.",
            ),
            contract.AuditJobOption(
                "clarity_enabled", False, "boolean",
                required_when="Requires RASAI_CLARITY_API_TOKEN in the worker/secret store.",
                description="Opt-in because Clarity allows only 10 Data Export requests/day/project.",
            ),
            contract.AuditJobOption(
                "common_crawl_enabled", True, "boolean",
                description="Credential-free bounded Common Crawl URL-history observation.",
            ),
            contract.AuditJobOption(
                "clarity_days", DEFAULT_CLARITY_DAYS, "integer",
                description="Microsoft Clarity rolling window: 1, 2 or 3 days.",
            ),
            contract.AuditJobOption(
                "clarity_dimensions", dimensions_csv(DEFAULT_CLARITY_DIMENSIONS), "string",
                description="Up to three Clarity dimensions; RASAi requires URL to preserve audited-origin scope.",
            ),
            contract.AuditJobOption(
                "common_crawl_max_urls", DEFAULT_COMMON_CRAWL_MAX_URLS, "integer",
                description="Bounded exact audited URLs queried in Common Crawl; 0 disables the subcollection.",
            ),
            contract.AuditJobOption(
                "common_crawl_index_count", DEFAULT_COMMON_CRAWL_INDEX_COUNT, "integer",
                description="Recent Common Crawl monthly indexes queried per selected URL.",
            ),
        ))
        return tuple(options)

    def defaults_with_external_observability():
        result = dict(original_defaults())
        result.update({
            "crux_history_enabled": None,
            "clarity_enabled": False,
            "common_crawl_enabled": True,
            "clarity_days": DEFAULT_CLARITY_DAYS,
            "clarity_dimensions": dimensions_csv(DEFAULT_CLARITY_DIMENSIONS),
            "common_crawl_max_urls": DEFAULT_COMMON_CRAWL_MAX_URLS,
            "common_crawl_index_count": DEFAULT_COMMON_CRAWL_INDEX_COUNT,
        })
        return result

    def normalize_with_external_observability(payload: Mapping[str, Any]):
        base_payload = {key: value for key, value in payload.items() if key not in _EXTERNAL_FIELDS}
        normalized = dict(original_normalize(base_payload))
        normalized["crux_history_enabled"] = _optional_bool(payload, "crux_history_enabled", None)
        normalized["clarity_enabled"] = _optional_bool(payload, "clarity_enabled", False)
        normalized["common_crawl_enabled"] = _optional_bool(payload, "common_crawl_enabled", True)
        normalized["clarity_days"] = clarity_days(_payload_text(payload, "clarity_days", str(DEFAULT_CLARITY_DAYS)))
        normalized["clarity_dimensions"] = dimensions_csv(
            clarity_dimensions(_payload_text(payload, "clarity_dimensions", dimensions_csv(DEFAULT_CLARITY_DIMENSIONS)))
        )
        normalized["common_crawl_max_urls"] = common_crawl_max_urls(
            _payload_text(payload, "common_crawl_max_urls", str(DEFAULT_COMMON_CRAWL_MAX_URLS))
        )
        normalized["common_crawl_index_count"] = common_crawl_index_count(
            _payload_text(payload, "common_crawl_index_count", str(DEFAULT_COMMON_CRAWL_INDEX_COUNT))
        )
        return normalized

    def environment_with_external_observability(payload: Mapping[str, Any]):
        base_payload = {key: value for key, value in payload.items() if key not in _EXTERNAL_FIELDS}
        overrides = dict(original_environment(base_payload))
        normalized = normalize_with_external_observability(payload)
        for name, env_name in _EXTERNAL_PAYLOAD_TO_ENV.items():
            value = normalized[name]
            if value is None:
                continue
            overrides[env_name] = "true" if value else "false"
        overrides[CLARITY_DAYS_ENV] = str(normalized["clarity_days"])
        overrides[CLARITY_DIMENSIONS_ENV] = str(normalized["clarity_dimensions"])
        overrides[COMMON_CRAWL_MAX_URLS_ENV] = str(normalized["common_crawl_max_urls"])
        overrides[COMMON_CRAWL_INDEX_COUNT_ENV] = str(normalized["common_crawl_index_count"])
        return overrides

    contract.audit_job_options = options_with_external_observability
    contract.audit_job_defaults = defaults_with_external_observability
    contract.normalize_audit_job_payload = normalize_with_external_observability
    contract.audit_job_environment_overrides = environment_with_external_observability
    contract._rasai_external_observability_contract = True
    _rebind_contract_consumers(contract)


def _rebind_contract_consumers(contract: Any) -> None:
    bindings = {
        "rasai.execution_contract": (("normalize_audit_job_payload", contract.normalize_audit_job_payload),),
        "rasai.worker": (
            ("normalize_audit_job_payload", contract.normalize_audit_job_payload),
            ("audit_job_environment_overrides", contract.audit_job_environment_overrides),
        ),
        "rasai.saas_context_integration": (("normalize_audit_job_payload", contract.normalize_audit_job_payload),),
        "rasai.web.saas_management_routes": (("audit_job_options", contract.audit_job_options),),
    }
    for module_name, assignments in bindings.items():
        module = sys.modules.get(module_name)
        if module is None:
            continue
        for name, value in assignments:
            setattr(module, name, value)


def _optional_bool(payload: Mapping[str, Any], name: str, default: bool | None) -> bool | None:
    value = payload.get(name, default)
    if value is None:
        return None
    if not isinstance(value, bool):
        raise ValueError(f"AUDIT payload field {name} must be boolean or null")
    return value


def _payload_text(payload: Mapping[str, Any], name: str, default: str) -> str:
    value = payload.get(name, default)
    if isinstance(value, bool) or value is None:
        raise ValueError(f"AUDIT payload field {name} has invalid type")
    return str(value)


def collect_configured_external_observability(
    *,
    audit_id: str,
    workspace: Any,
    env: Mapping[str, str] | None = None,
) -> dict[str, dict[str, Any]]:
    environment = env if env is not None else os.environ
    timeout = _positive_float(environment.get(STANDARDS_TIMEOUT_ENV), DEFAULT_STANDARDS_TIMEOUT_SECONDS)
    outcomes: dict[str, dict[str, Any]] = {}

    crux_state = service_state(service("crux-history"), environment)
    crux_result = _base_result(crux_state)
    if bool(crux_state["effective_enabled"]):
        key = str(environment.get(CRUX_KEY_ENV) or "").strip()
        targets = _origin_form_factors(workspace, audit_id)
        attempted = 0
        succeeded = 0
        datasets: list[str] = []
        errors: list[str] = []
        for origin, form_factor in targets:
            attempted += 1
            try:
                datasets.append(
                    collect_crux_history(
                        audit_workspace=workspace.root,
                        api_key=key,
                        target=origin,
                        target_scope="origin",
                        form_factor=form_factor,
                        collection_period_count=40,
                        timeout=timeout,
                    )
                )
                succeeded += 1
            except Exception as exc:
                errors.append(_safe_error("CRUX_HISTORY", exc))
        crux_result.update(
            targets_attempted=attempted,
            targets_succeeded=succeeded,
            datasets=datasets,
            errors=errors,
            collection_state=_collection_state(attempted, succeeded),
            scope="ORIGIN+FORM_FACTOR",
        )
    outcomes["crux-history"] = crux_result

    clarity_state = service_state(service("microsoft-clarity"), environment)
    clarity_result = _base_result(clarity_state)
    if bool(clarity_state["effective_enabled"]):
        attempted = 1
        try:
            dataset_id = collect_clarity_insights(
                audit_workspace=workspace.root,
                api_token=str(environment.get(CLARITY_TOKEN_ENV) or ""),
                days=clarity_days(environment.get(CLARITY_DAYS_ENV)),
                dimensions=clarity_dimensions(environment.get(CLARITY_DIMENSIONS_ENV)),
                timeout=timeout,
            )
            clarity_result.update(
                targets_attempted=attempted,
                targets_succeeded=1,
                datasets=[dataset_id],
                errors=[],
                collection_state="SUCCESS",
                scope="ORIGIN/URL+DEVICE_WHEN_DIMENSION_PRESENT",
            )
        except Exception as exc:
            clarity_result.update(
                targets_attempted=attempted,
                targets_succeeded=0,
                datasets=[],
                errors=[_safe_error("CLARITY", exc)],
                collection_state="ERROR",
            )
    outcomes["microsoft-clarity"] = clarity_result

    common_state = service_state(service("common-crawl"), environment)
    common_result = _base_result(common_state)
    if bool(common_state["effective_enabled"]):
        max_urls = common_crawl_max_urls(environment.get(COMMON_CRAWL_MAX_URLS_ENV))
        if max_urls == 0:
            common_result.update(
                targets_attempted=0,
                targets_succeeded=0,
                datasets=[],
                errors=[],
                collection_state="NO_DATA",
                reason="COMMON_CRAWL_MAX_URLS_ZERO",
            )
        else:
            try:
                dataset_id = collect_common_crawl_history(
                    audit_workspace=workspace.root,
                    max_urls=max_urls,
                    collection_count=common_crawl_index_count(environment.get(COMMON_CRAWL_INDEX_COUNT_ENV)),
                    timeout=timeout,
                )
                common_result.update(
                    targets_attempted=1,
                    targets_succeeded=1,
                    datasets=[dataset_id],
                    errors=[],
                    collection_state="SUCCESS",
                    scope="URL",
                )
            except Exception as exc:
                common_result.update(
                    targets_attempted=1,
                    targets_succeeded=0,
                    datasets=[],
                    errors=[_safe_error("COMMON_CRAWL", exc)],
                    collection_state="ERROR",
                )
    outcomes["common-crawl"] = common_result

    for service_id, result in outcomes.items():
        _upsert_service_run(audit_id=audit_id, workspace=workspace, service_id=service_id, result=result)
    return outcomes


def _base_result(state_info: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "service_state": str(state_info.get("state") or "UNKNOWN"),
        "requested": bool(state_info.get("requested")),
        "configured": bool(state_info.get("configured")),
        "effective_enabled": bool(state_info.get("effective_enabled")),
        "configuration_source": str(state_info.get("configuration_source") or ""),
        "missing_configuration": list(state_info.get("missing_configuration") or ()),
        "targets_attempted": 0,
        "targets_succeeded": 0,
        "datasets": [],
        "errors": [],
        "collection_state": str(state_info.get("state") or "UNKNOWN"),
    }


def _origin_form_factors(workspace: Any, audit_id: str) -> tuple[tuple[str, str | None], ...]:
    connection = sqlite3.connect(workspace.database)
    try:
        origins = [
            str(row[0]).rstrip("/")
            for row in connection.execute(
                "SELECT DISTINCT normalized_origin FROM audit_targets WHERE audit_id=? ORDER BY normalized_origin",
                (audit_id,),
            ).fetchall()
            if row[0]
        ]
        devices = {
            str(row[0]).strip().casefold()
            for row in connection.execute(
                """SELECT DISTINCT ps.device FROM page_snapshots ps
                   JOIN pages p ON p.page_id=ps.page_id WHERE p.audit_id=?""",
                (audit_id,),
            ).fetchall()
            if row[0]
        }
    finally:
        connection.close()
    form_factors = tuple(_DEVICE_TO_CRUX[item] for item in ("mobile", "desktop", "tablet") if item in devices)
    result: list[tuple[str, str | None]] = []
    for origin in origins:
        result.append((origin, None))
        result.extend((origin, form_factor) for form_factor in form_factors)
    return tuple(result)


def _upsert_service_run(*, audit_id: str, workspace: Any, service_id: str, result: Mapping[str, Any]) -> None:
    if service_id not in _SERVICE_IDS:
        return
    connection = sqlite3.connect(workspace.database)
    try:
        exists = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='standards_service_runs'"
        ).fetchone()
        if exists is None:
            return
        with connection:
            connection.execute(
                """INSERT OR REPLACE INTO standards_service_runs(
                    audit_id,service_id,requested,configured,effective_enabled,state,
                    targets_attempted,targets_succeeded,details_json,updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (
                    audit_id,
                    service_id,
                    int(bool(result.get("requested"))),
                    int(bool(result.get("configured"))),
                    int(bool(result.get("effective_enabled"))),
                    str(result.get("collection_state") or result.get("service_state") or "UNKNOWN"),
                    int(result.get("targets_attempted") or 0),
                    int(result.get("targets_succeeded") or 0),
                    json.dumps(dict(result), ensure_ascii=False, sort_keys=True, separators=(",", ":")),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
    finally:
        connection.close()


def _collection_state(attempted: int, succeeded: int) -> str:
    if attempted <= 0:
        return "NO_DATA"
    if succeeded == attempted:
        return "SUCCESS"
    if succeeded > 0:
        return "PARTIAL"
    return "ERROR"


def _positive_float(raw: str | None, default: float) -> float:
    if raw is None or not str(raw).strip():
        return default
    value = float(str(raw).strip())
    if value <= 0 or value >= 3600:
        raise ValueError("external observability timeout must be > 0 and < 3600 seconds")
    return value


def _safe_error(label: str, exc: Exception) -> str:
    return redact_text(f"{label}:{type(exc).__name__}:{str(exc)[:350]}")


def install() -> None:
    """Collect configured external observability in the audit collection lifecycle."""
    from rasai import report_completion

    if getattr(report_completion, "_rasai_external_observability_runtime", False):
        return
    original = report_completion.finalize_audit_report_site

    def finalize_with_external_observability(*, audit_id: str, workspace: Any, context_interpretations=(), routing_snapshot=None):
        base = original(
            audit_id=audit_id,
            workspace=workspace,
            context_interpretations=context_interpretations,
            routing_snapshot=routing_snapshot,
        )
        from rasai.selective_reprocess_context import active as reprocess_active
        if reprocess_active():
            # Common Crawl, CrUX History and Clarity are not fulfillment-required RPR
            # dependencies. A report/data finalizer must never refresh them implicitly.
            return base
        try:
            outcomes = collect_configured_external_observability(
                audit_id=audit_id,
                workspace=workspace,
            )
            for service_id, result in outcomes.items():
                if result.get("collection_state") in {"ERROR", "PARTIAL"}:
                    _LOGGER.warning(
                        "External observability %s completed as %s: %s",
                        service_id,
                        result.get("collection_state"),
                        "; ".join(str(item) for item in result.get("errors") or ()),
                    )
        except Exception:
            _LOGGER.exception(
                "External observability finalization failed; canonical audit data preserved"
            )

        return report_completion.AuditReportCompletion(
            expected_pages=base.expected_pages,
            generated_pages=base.generated_pages,
            missing_pages=base.missing_pages,
            renderer_errors=base.renderer_errors,
        )

    report_completion.finalize_audit_report_site = finalize_with_external_observability
    report_completion._rasai_external_observability_runtime = True

