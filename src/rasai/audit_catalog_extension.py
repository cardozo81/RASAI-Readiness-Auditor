"""Additive CAT-* expansion for an already-complete logical AUD.

The initial audit configuration is immutable evidence.  A later catalog expansion is
recorded separately and materializes only the new fulfillment work.  Collection and
analysis continue through the canonical RPR runtimes.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
from typing import Any, Mapping

from rasai.audit_fulfillment import (
    LIVE_RECOLLECTION,
    REPLAY_SAFE,
    REQUESTED_NOT_EXECUTED,
    SUCCESS,
    finish_reprocess_run,
    recalculate,
    register_work_item,
    set_work_item_status,
    start_reprocess_run,
    update_reprocess_run_configuration,
)
from rasai.domain import new_id
from rasai.persistence import AuditWorkspace

SCHEMA_VERSION = "AUDIT-CATALOG-EXTENSION-001"
_LIVE_CATALOGS = frozenset({"CAT-04", "CAT-05", "CAT-06", "CAT-07"})

_SCHEMA = """
CREATE TABLE IF NOT EXISTS audit_catalog_extensions(
    extension_id TEXT PRIMARY KEY,
    audit_id TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    status TEXT NOT NULL,
    base_catalogs_json TEXT NOT NULL,
    added_catalogs_json TEXT NOT NULL,
    effective_catalogs_json TEXT NOT NULL,
    catalog_items_json TEXT NOT NULL,
    configuration_json TEXT NOT NULL,
    live_valid_until TEXT,
    reprocess_id TEXT,
    requested_at TEXT NOT NULL,
    completed_at TEXT,
    note TEXT
);
CREATE INDEX IF NOT EXISTS idx_audit_catalog_extensions_audit
ON audit_catalog_extensions(audit_id,requested_at);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json(raw: Any, default: Any) -> Any:
    if raw in (None, ""):
        return default
    if isinstance(raw, (dict, list, tuple)):
        return raw
    try:
        return json.loads(str(raw))
    except (TypeError, ValueError, json.JSONDecodeError):
        return default


def _connect(workspace: AuditWorkspace) -> sqlite3.Connection:
    con = sqlite3.connect(workspace.database)
    con.row_factory = sqlite3.Row
    con.executescript(_SCHEMA)
    con.commit()
    return con


def _original_catalog_block(con: sqlite3.Connection, audit_id: str) -> dict[str, Any]:
    try:
        row = con.execute(
            "SELECT configuration_json FROM audit_execution_configurations WHERE audit_id=?",
            (audit_id,),
        ).fetchone()
    except sqlite3.OperationalError:
        row = None
    payload = _json(row[0], {}) if row else {}
    block = payload.get("audit_catalog") if isinstance(payload, Mapping) else None
    return dict(block) if isinstance(block, Mapping) else {}


def effective_catalog_projection(
    con: sqlite3.Connection,
    audit_id: str,
) -> tuple[set[str], dict[str, dict[str, Any]], tuple[dict[str, Any], ...]]:
    """Return initial selection plus every committed/requested additive extension."""
    block = _original_catalog_block(con, audit_id)
    selected = {
        str(value).strip().upper()
        for value in block.get("selected", ())
        if str(value).strip()
    }
    items: dict[str, dict[str, Any]] = {}
    for raw in block.get("items", ()) if isinstance(block.get("items"), list) else ():
        if not isinstance(raw, Mapping):
            continue
        key = str(raw.get("id") or raw.get("catalog_id") or "").strip().upper()
        if key:
            items[key] = dict(raw)

    try:
        rows = con.execute(
            """SELECT * FROM audit_catalog_extensions
               WHERE audit_id=? AND status NOT IN ('CANCELLED','ROLLED_BACK')
               ORDER BY requested_at,extension_id""",
            (audit_id,),
        ).fetchall()
    except sqlite3.OperationalError:
        rows = ()
    rpr_by_extension: dict[str, dict[str, Any]] = {}
    try:
        rpr_rows = con.execute(
            """SELECT reprocess_id,status,configuration,started_at,completed_at
               FROM audit_reprocess_runs WHERE audit_id=?
               ORDER BY started_at,reprocess_id""",
            (audit_id,),
        ).fetchall()
    except sqlite3.OperationalError:
        rpr_rows = ()
    for rpr in rpr_rows:
        configuration = _json(rpr["configuration"], {})
        context = configuration.get("execution_context") if isinstance(configuration, Mapping) else None
        extension_id = str(
            (context.get("catalog_extension_id") if isinstance(context, Mapping) else "")
            or ""
        )
        if extension_id:
            rpr_by_extension[extension_id] = {
                "reprocess_id": str(rpr["reprocess_id"]),
                "rpr_status": str(rpr["status"] or ""),
                "rpr_started_at": rpr["started_at"],
                "rpr_completed_at": rpr["completed_at"],
            }

    history: list[dict[str, Any]] = []
    for row in rows:
        added = [
            str(value).strip().upper()
            for value in _json(row["added_catalogs_json"], [])
            if str(value).strip()
        ]
        extension_id = str(row["extension_id"])
        linked = rpr_by_extension.get(extension_id, {})
        row_status = str(row["status"] or "").strip().upper()
        # A persisted request becomes part of the effective AUD only after a causal
        # RPR exists (or a future explicit committed status is written before sealing).
        # This prevents a crash between INSERT and RPR creation from silently changing
        # the logical audit contract.
        is_effective = bool(linked) or row_status in {"SUCCESS", "COMPLETED"}
        if is_effective:
            selected.update(added)
            for raw in _json(row["catalog_items_json"], []):
                if not isinstance(raw, Mapping):
                    continue
                key = str(raw.get("id") or raw.get("catalog_id") or "").strip().upper()
                if key:
                    items[key] = dict(raw)
        history.append({
            "extension_id": extension_id,
            "status": str(linked.get("rpr_status") or row["status"]),
            "effective": is_effective,
            "added": added,
            "reprocess_id": linked.get("reprocess_id") or row["reprocess_id"],
            "requested_at": row["requested_at"],
            "completed_at": linked.get("rpr_completed_at") or row["completed_at"],
            "live_valid_until": row["live_valid_until"],
        })
    return selected, items, tuple(history)


def effective_catalog_ids(workspace: AuditWorkspace, audit_id: str) -> tuple[str, ...]:
    con = _connect(workspace)
    try:
        selected, _items, _history = effective_catalog_projection(con, audit_id)
    finally:
        con.close()
    from rasai.audit_catalog import CATALOGS
    return tuple(item.id for item in CATALOGS if item.id in selected)


def _live_deadline(workspace: AuditWorkspace, audit_id: str) -> str | None:
    con = sqlite3.connect(workspace.database)
    try:
        rows = con.execute(
            """SELECT valid_until FROM audit_fulfillment_work_items
               WHERE audit_id=? AND temporal_mode='LIVE_RECOLLECTION'
                 AND component IN ('DISCOVERY_ACQUISITION','HTTP_ACQUISITION','RENDER_CAPTURE')
                 AND valid_until IS NOT NULL
               ORDER BY valid_until""",
            (audit_id,),
        ).fetchall()
    except sqlite3.OperationalError:
        rows = ()
    finally:
        con.close()
    return str(rows[0][0]) if rows and rows[0][0] else None


def _deadline_active(value: str | None) -> bool:
    if not value:
        return False
    try:
        instant = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) <= instant.astimezone(timezone.utc)


def extension_readiness(
    workspace: AuditWorkspace,
    audit_id: str,
    added_catalogs: set[str],
    *,
    extra_live_catalogs: set[str] | None = None,
) -> tuple[bool, str, str | None]:
    deadline = _live_deadline(workspace, audit_id)
    live = sorted(
        (added_catalogs & _LIVE_CATALOGS)
        | set(extra_live_catalogs or ())
    )
    if live and not _deadline_active(deadline):
        return (
            False,
            "A janela temporal desta AUD expirou para novas coletas live ("
            + ", ".join(live)
            + "); crie um novo AUD para esses catálogos.",
            deadline,
        )
    return True, "extensão aditiva elegível", deadline


def _request_item(
    workspace: AuditWorkspace,
    audit_id: str,
    component: str,
    configuration: Mapping[str, Any],
    *,
    temporal_mode: str,
    valid_until: str | None = None,
) -> bool:
    from rasai.audit_fulfillment import list_work_items
    if any(
        item.component == component and item.scope_key == "AUDIT"
        for item in list_work_items(workspace, audit_id)
    ):
        return False
    register_work_item(
        workspace,
        audit_id=audit_id,
        component=component,
        scope_key="AUDIT",
        required=True,
        temporal_mode=temporal_mode,
        status=REQUESTED_NOT_EXECUTED,
        retryable=True,
        configuration=dict(configuration),
        valid_until=valid_until,
    )
    set_work_item_status(
        workspace,
        audit_id=audit_id,
        component=component,
        scope_key="AUDIT",
        status=REQUESTED_NOT_EXECUTED,
        error_class="CATALOG_EXTENSION",
        error_code="CATALOG_ADDED_AFTER_INITIAL_COMPLETION",
        error_message="catálogo acrescentado após o fechamento do contrato inicial da AUD",
        retryable=True,
    )
    return True


def _request_scoped_item(
    workspace: AuditWorkspace,
    audit_id: str,
    component: str,
    scope_key: str,
    configuration: Mapping[str, Any],
    *,
    temporal_mode: str,
    required: bool = True,
    valid_until: str | None = None,
) -> bool:
    from rasai.audit_fulfillment import list_work_items
    if any(
        item.component == component and item.scope_key == scope_key
        for item in list_work_items(workspace, audit_id)
    ):
        return False
    register_work_item(
        workspace,
        audit_id=audit_id,
        component=component,
        scope_key=scope_key,
        required=required,
        temporal_mode=temporal_mode,
        status=REQUESTED_NOT_EXECUTED,
        retryable=True,
        configuration=dict(configuration),
        valid_until=valid_until,
    )
    set_work_item_status(
        workspace,
        audit_id=audit_id,
        component=component,
        scope_key=scope_key,
        status=REQUESTED_NOT_EXECUTED,
        error_class="CATALOG_EXTENSION",
        error_code="CATALOG_ADDED_AFTER_INITIAL_COMPLETION",
        error_message="catálogo acrescentado após o fechamento do contrato inicial da AUD",
        retryable=True,
    )
    return True


def _snapshot_ids(workspace: AuditWorkspace, audit_id: str) -> tuple[str, ...]:
    con = sqlite3.connect(workspace.database)
    try:
        rows = con.execute(
            """SELECT ps.snapshot_id
               FROM page_snapshots ps
               JOIN pages p ON p.page_id=ps.page_id
               WHERE p.audit_id=?
               ORDER BY ps.captured_at,ps.snapshot_id""",
            (audit_id,),
        ).fetchall()
    except sqlite3.OperationalError:
        rows = ()
    finally:
        con.close()
    return tuple(str(row[0]) for row in rows if row[0])


def _web_configuration(state: Any) -> dict[str, Any]:
    categories = tuple(
        value.strip()
        for value in str(getattr(state, "lighthouse_categories", "") or "").split(",")
        if value.strip()
    )
    return {
        "enabled": True,
        "max_pages": int(getattr(state, "web_max_pages", 10) or 0),
        "timeout_seconds": float(getattr(state, "web_timeout", 120.0) or 120.0),
        "categories": list(categories),
        "field_source": str(getattr(state, "field_source", "auto") or "auto"),
        "pagespeed_key_configured": bool((os.environ.get("RASAI_PAGESPEED_API_KEY") or "").strip()),
        "crux_key_configured": bool((os.environ.get("RASAI_CRUX_API_KEY") or "").strip()),
    }


def _search_configuration(state: Any) -> dict[str, Any]:
    from rasai.search_intelligence.config import SerpRuntimeConfig
    runtime = SerpRuntimeConfig.from_environment(validate=False)
    queries = [
        str(value).strip()
        for value in tuple(getattr(state, "search_queries", ()) or ())
        if str(value).strip()
    ]
    return {
        "enabled": bool(queries),
        "queries": list(dict.fromkeys(queries)),
        "depth": int(getattr(state, "search_depth", 20) or 20),
        "region": str(getattr(state, "search_region", "") or ""),
        "device": str(getattr(state, "search_device", "mobile") or "mobile"),
        "competitive": bool(getattr(state, "search_competitive", True)),
        "compare_content": bool(getattr(state, "search_compare_content", False)),
        "max_content_pages": int(getattr(state, "search_max_content_pages", 3) or 3),
        "content_timeout_seconds": float(getattr(state, "search_content_timeout_seconds", 10.0) or 10.0),
        "content_max_bytes": int(getattr(state, "search_content_max_bytes", 2_000_000) or 2_000_000),
        "content_max_redirects": int(getattr(state, "search_content_max_redirects", 5) or 5),
        "ai_competitive": bool(getattr(state, "search_ai_competitive", False)),
        "ymyl_mode": str(getattr(state, "search_ymyl_mode", "AUTO") or "AUTO").upper(),
        "mode": str(runtime.mode),
        "provider": str(runtime.provider),
        "fixture_path": str(runtime.fixture_path) if runtime.fixture_path else "",
        "max_queries": int(runtime.max_queries),
        "max_requests": int(runtime.max_requests),
        "max_depth": int(runtime.max_depth),
        "max_competitors": int(runtime.max_competitors),
        "timeout_seconds": float(runtime.timeout_seconds),
        "retries": int(runtime.retries),
        "min_interval_seconds": float(runtime.min_interval_seconds),
    }


def _gsc_configuration() -> dict[str, Any]:
    return {
        "requested": True,
        "service_id": "google-search-console",
        "site_url": os.environ.get("RASAI_GOOGLE_SEARCH_CONSOLE_SITE_URL", ""),
        "max_urls": os.environ.get("RASAI_STANDARDS_MAX_URLS", ""),
        "timeout_seconds": os.environ.get("RASAI_STANDARDS_TIMEOUT_SECONDS", ""),
        "search_analytics_days": os.environ.get("RASAI_GSC_SEARCH_ANALYTICS_DAYS", ""),
        "search_max_rows": os.environ.get("RASAI_GSC_SEARCH_MAX_ROWS", ""),
        "final_data_lag_days": os.environ.get("RASAI_GSC_FINAL_DATA_LAG_DAYS", ""),
    }


def _truthy(value: Any) -> bool:
    return str(value or "").strip().casefold() in {"1", "true", "yes", "on", "sim", "s"}


def _materialize_added_work(
    workspace: AuditWorkspace,
    audit_id: str,
    state: Any,
    added: set[str],
    *,
    live_valid_until: str | None,
) -> set[str]:
    components: set[str] = set()
    if added & {"CAT-02", "CAT-04"} and bool(getattr(state, "web_performance", False)):
        if _request_item(
            workspace, audit_id, "WEB_PERFORMANCE", _web_configuration(state),
            temporal_mode=LIVE_RECOLLECTION, valid_until=live_valid_until,
        ):
            components.add("WEB_PERFORMANCE")

    if "CAT-05" in added:
        search = _search_configuration(state)
        if search["enabled"] and _request_item(
            workspace, audit_id, "SEARCH_INTELLIGENCE", search,
            temporal_mode=LIVE_RECOLLECTION, valid_until=live_valid_until,
        ):
            components.add("SEARCH_INTELLIGENCE")
        if _truthy(os.environ.get("RASAI_GSC_ENABLED")) and _request_item(
            workspace, audit_id, "GOOGLE_SEARCH_CONSOLE", _gsc_configuration(),
            temporal_mode=LIVE_RECOLLECTION, valid_until=live_valid_until,
        ):
            components.add("GOOGLE_SEARCH_CONSOLE")

    if "CAT-06" in added:
        from rasai.console_m23 import config_from_state
        cfg = config_from_state(state)
        nav = {
            "enabled": True,
            "threshold_seconds": cfg.threshold_seconds,
            "target_valid_samples": cfg.target_valid_samples,
            "max_attempts_per_context": cfg.max_attempts_per_context,
            "max_pages": cfg.max_pages,
            "timeout_seconds": cfg.timeout_seconds,
            "delay_seconds": cfg.delay_seconds,
            "concurrency": cfg.concurrency,
            "mobile_profile": cfg.mobile_profile.as_dict(),
            "desktop_profile": cfg.desktop_profile.as_dict(),
        }
        if _request_item(
            workspace, audit_id, "SYNTHETIC_APDEX", nav,
            temporal_mode=LIVE_RECOLLECTION, valid_until=live_valid_until,
        ):
            components.add("SYNTHETIC_APDEX")

    if "CAT-07" in added:
        from rasai.console_m23 import experience_from_state
        ux = experience_from_state(state).as_dict()
        if _request_item(
            workspace, audit_id, "EXPERIENCE_APDEX", ux,
            temporal_mode=LIVE_RECOLLECTION, valid_until=live_valid_until,
        ):
            components.add("EXPERIENCE_APDEX")

    if "CAT-03" in added and bool(getattr(state, "_rasai_catalog_extension_use_ai", False)):
        provider = str(getattr(state, "ai_provider", "none") or "none").casefold()
        for snapshot_id in _snapshot_ids(workspace, audit_id):
            if _request_scoped_item(
                workspace,
                audit_id,
                "SEMANTIC_AI",
                snapshot_id,
                {
                    "requested": True,
                    "provider": provider,
                    "model": str(getattr(state, "ai_model", "") or ""),
                    "reasoning": str(getattr(state, "ai_reasoning", "") or ""),
                    "source": "catalog_extension",
                },
                temporal_mode=REPLAY_SAFE,
            ):
                components.add("SEMANTIC_AI")

    if "CAT-08" in added:
        provider = str(getattr(state, "ai_provider", "none") or "none").casefold()
        config = {
            "requested": True,
            "provider": provider,
            "model": str(getattr(state, "ai_model", "") or ""),
            "reasoning": str(getattr(state, "ai_reasoning", "") or ""),
            "domains": [
                value.strip()
                for value in str(os.environ.get("RASAI_IMPROVEMENT_DOMAINS", "")).split(",")
                if value.strip()
            ],
            "max_recommendations": os.environ.get("RASAI_IMPROVEMENT_MAX_RECOMMENDATIONS", "50"),
            "timeout_seconds": os.environ.get("RASAI_IMPROVEMENT_AI_TIMEOUT_SECONDS", "240"),
            "language": os.environ.get("RASAI_AI_ANALYSIS_LANGUAGE", "auto"),
        }
        if _request_item(
            workspace, audit_id, "IMPROVEMENT_INTELLIGENCE", config,
            temporal_mode=REPLAY_SAFE,
        ):
            components.add("IMPROVEMENT_INTELLIGENCE")

    if "CAT-09" in added:
        if bool(getattr(state, "content_remediation", False)) and _request_item(
            workspace, audit_id, "CONTENT_REMEDIATION_AI",
            {"requested": True, "source": "catalog_extension"},
            temporal_mode=REPLAY_SAFE,
        ):
            components.add("CONTENT_REMEDIATION_AI")
        if bool(getattr(state, "technical_remediation", False)) and _request_item(
            workspace, audit_id, "TECHNICAL_AI",
            {"requested": True, "source": "catalog_extension"},
            temporal_mode=REPLAY_SAFE,
        ):
            components.add("TECHNICAL_AI")

    if "CAT-10" in added:
        security = {
            "requested": True,
            "mode": "PASSIVE_ONLY",
            "headers": os.environ.get("RASAI_SECURITY_HEADERS", "true"),
            "cookies": os.environ.get("RASAI_SECURITY_COOKIES", "true"),
            "resources": os.environ.get("RASAI_SECURITY_RESOURCES", "true"),
            "third_party": os.environ.get("RASAI_SECURITY_THIRD_PARTY", "true"),
            "runtime": os.environ.get("RASAI_SECURITY_RUNTIME_CORRELATION", "true"),
            "osv": os.environ.get("RASAI_SECURITY_OSV", "true"),
            "kev": os.environ.get("RASAI_SECURITY_CISA_KEV", "true"),
            "external_timeout_seconds": os.environ.get("RASAI_SECURITY_EXTERNAL_TIMEOUT_SECONDS", "15"),
        }
        if _request_item(
            workspace, audit_id, "PASSIVE_SECURITY", security,
            temporal_mode=REPLAY_SAFE,
        ):
            components.add("PASSIVE_SECURITY")

        # CAT-10 AI is optional in the catalog contract. If the operator explicitly
        # authorizes AI for this extension and CAT-08 is not the owner of the same
        # Improvement engine, materialize the SECURITY-only analysis as required for
        # this chosen extension attempt, exactly as the initial catalog projection does.
        if (
            bool(getattr(state, "_rasai_catalog_extension_use_ai", False))
            and "CAT-08" not in added
            and _request_item(
                workspace,
                audit_id,
                "IMPROVEMENT_INTELLIGENCE",
                {
                    "requested": True,
                    "provider": str(getattr(state, "ai_provider", "none") or "none").casefold(),
                    "model": str(getattr(state, "ai_model", "") or ""),
                    "reasoning": str(getattr(state, "ai_reasoning", "") or ""),
                    "domains": ["SECURITY"],
                    "max_recommendations": os.environ.get("RASAI_IMPROVEMENT_MAX_RECOMMENDATIONS", "30"),
                    "timeout_seconds": os.environ.get("RASAI_IMPROVEMENT_AI_TIMEOUT_SECONDS", "240"),
                    "language": os.environ.get("RASAI_AI_ANALYSIS_LANGUAGE", "auto"),
                    "source": "catalog_extension:CAT-10",
                },
                temporal_mode=REPLAY_SAFE,
            )
        ):
            components.add("IMPROVEMENT_INTELLIGENCE")
    return components


def _insert_extension(
    workspace: AuditWorkspace,
    audit_id: str,
    *,
    base: tuple[str, ...],
    added: tuple[str, ...],
    effective: tuple[str, ...],
    catalog_items: tuple[dict[str, Any], ...],
    configuration: Mapping[str, Any],
    live_valid_until: str | None,
) -> str:
    extension_id = new_id("CEX")
    con = _connect(workspace)
    try:
        con.execute(
            """INSERT INTO audit_catalog_extensions(
                extension_id,audit_id,schema_version,status,base_catalogs_json,
                added_catalogs_json,effective_catalogs_json,catalog_items_json,
                configuration_json,live_valid_until,reprocess_id,requested_at,
                completed_at,note
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                extension_id,audit_id,SCHEMA_VERSION,"REQUESTED",
                json.dumps(list(base), ensure_ascii=False),
                json.dumps(list(added), ensure_ascii=False),
                json.dumps(list(effective), ensure_ascii=False),
                json.dumps(list(catalog_items), ensure_ascii=False),
                json.dumps(dict(configuration), ensure_ascii=False, default=str),
                live_valid_until,None,_now(),None,None,
            ),
        )
        con.commit()
    finally:
        con.close()
    return extension_id


def _work_item_ids(
    workspace: AuditWorkspace,
    audit_id: str,
) -> frozenset[str] | None:
    """Snapshot fulfillment identities before extension planning starts.

    None means the snapshot could not be proven and therefore disables cleanup;
    rollback must fail closed rather than risk removing a pre-existing work-item.
    """
    con = sqlite3.connect(workspace.database)
    try:
        table = con.execute(
            """SELECT 1 FROM sqlite_master
               WHERE type='table' AND name='audit_fulfillment_work_items'"""
        ).fetchone()
        if table is None:
            return frozenset()
        columns = {
            str(row[1])
            for row in con.execute(
                "PRAGMA table_info(audit_fulfillment_work_items)"
            ).fetchall()
        }
        if not {"work_item_id", "audit_id"}.issubset(columns):
            return None
        return frozenset(
            str(row[0])
            for row in con.execute(
                """SELECT work_item_id FROM audit_fulfillment_work_items
                   WHERE audit_id=?""",
                (audit_id,),
            ).fetchall()
            if row[0]
        )
    except sqlite3.Error:
        return None
    finally:
        con.close()


def _extension_work_components(added: set[str]) -> frozenset[str]:
    """Bound pre-RPR cleanup to components owned by the requested catalog delta."""
    ownership = {
        "CAT-01": (),
        "CAT-02": ("WEB_PERFORMANCE",),
        "CAT-03": ("SEMANTIC_AI",),
        "CAT-04": ("WEB_PERFORMANCE",),
        "CAT-05": ("SEARCH_INTELLIGENCE", "GOOGLE_SEARCH_CONSOLE"),
        "CAT-06": ("SYNTHETIC_APDEX",),
        "CAT-07": ("EXPERIENCE_APDEX",),
        "CAT-08": ("IMPROVEMENT_INTELLIGENCE",),
        "CAT-09": ("CONTENT_REMEDIATION_AI", "TECHNICAL_AI"),
        "CAT-10": ("PASSIVE_SECURITY", "IMPROVEMENT_INTELLIGENCE"),
    }
    return frozenset(
        component
        for catalog_id in added
        for component in ownership.get(str(catalog_id).upper(), ())
    )

def _rollback_unlinked_extension_work(
    workspace: AuditWorkspace,
    audit_id: str,
    *,
    preexisting_work_item_ids: frozenset[str] | None,
    candidate_components: frozenset[str],
) -> tuple[str, ...]:
    """Remove only zero-attempt planning rows created before any causal RPR exists.

    This is not an evidence rollback: collectors/providers have not run yet. Rows with
    an attempt, or rows that existed before the extension request, are always preserved.
    The failed audit_catalog_extensions row remains as the durable diagnostic trail.
    """
    if preexisting_work_item_ids is None:
        return ()
    con = sqlite3.connect(workspace.database)
    con.row_factory = sqlite3.Row
    try:
        tables = {
            str(row[0])
            for row in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        if "audit_fulfillment_work_items" not in tables:
            return ()
        columns = {
            str(row[1])
            for row in con.execute(
                "PRAGMA table_info(audit_fulfillment_work_items)"
            ).fetchall()
        }
        required = {"work_item_id", "audit_id", "attempt_count"}
        if not required.issubset(columns):
            return ()
        rows = con.execute(
            """SELECT work_item_id,attempt_count,component
               FROM audit_fulfillment_work_items WHERE audit_id=?""",
            (audit_id,),
        ).fetchall()
        removable: list[str] = []
        attempts_available = "audit_fulfillment_attempts" in tables
        for row in rows:
            work_item_id = str(row["work_item_id"] or "")
            if not work_item_id or work_item_id in preexisting_work_item_ids:
                continue
            if str(row["component"] or "").strip().upper() not in candidate_components:
                continue
            if int(row["attempt_count"] or 0) != 0:
                continue
            if attempts_available:
                attempts = int(
                    con.execute(
                        """SELECT COUNT(*) FROM audit_fulfillment_attempts
                           WHERE work_item_id=?""",
                        (work_item_id,),
                    ).fetchone()[0]
                )
                if attempts:
                    continue
            removable.append(work_item_id)
        if removable:
            con.executemany(
                "DELETE FROM audit_fulfillment_work_items WHERE work_item_id=?",
                ((work_item_id,) for work_item_id in removable),
            )
            con.commit()
        return tuple(removable)
    finally:
        con.close()


def _mark_unlinked_extension_failed(
    workspace: AuditWorkspace,
    audit_id: str,
    extension_id: str,
    *,
    note: str,
) -> bool:
    """Persist a retryable pre-RPR failure without mutating a sealed extension.

    Once a causal RPR exists, its ledger is authoritative and may already have been
    included in the report fingerprint. In that case this function deliberately does
    not mutate audit_catalog_extensions after the fact.
    """
    con = _connect(workspace)
    try:
        linked = False
        try:
            rows = con.execute(
                """SELECT configuration FROM audit_reprocess_runs
                   WHERE audit_id=? ORDER BY started_at,reprocess_id""",
                (audit_id,),
            ).fetchall()
        except sqlite3.OperationalError:
            rows = ()
        for row in rows:
            configuration = _json(row[0], {})
            context = (
                configuration.get("execution_context")
                if isinstance(configuration, Mapping)
                else None
            )
            if (
                isinstance(context, Mapping)
                and str(context.get("catalog_extension_id") or "") == extension_id
            ):
                linked = True
                break
        if linked:
            return False
        con.execute(
            """UPDATE audit_catalog_extensions
               SET status='FAILED_RETRYABLE',completed_at=?,note=?
               WHERE audit_id=? AND extension_id=? AND status='REQUESTED'""",
            (_now(), note, audit_id, extension_id),
        )
        con.commit()
        return True
    finally:
        con.close()


def apply_catalog_extension(
    *,
    state: Any,
    audit_id: str,
) -> Any:
    """Commit the additive catalog delta and execute only newly required work."""
    from rasai.audit_catalog import CATALOGS
    from rasai.audit_reprocess import ReprocessResult, reprocess_audit
    from rasai.console_catalog_plan import (
        ai_execution_enabled,
        catalog_snapshot,
        selected_catalog_ids,
    )
    from rasai.reprocess_policy import reprocess_policy

    workspace = AuditWorkspace.open(Path(state.audits_root) / audit_id)
    preexisting_work_item_ids = _work_item_ids(workspace, audit_id)
    current = set(effective_catalog_ids(workspace, audit_id))
    requested = set(selected_catalog_ids(state))
    removed = current - requested
    if removed:
        raise ValueError(
            "Complementação é somente aditiva; não remova catálogo(s) já pertencentes à AUD: "
            + ", ".join(sorted(removed))
        )
    added = requested - current
    if not added:
        raise ValueError("nenhum catálogo novo foi selecionado para complementar esta AUD")
    extension_work_components = _extension_work_components(added)

    use_ai = bool(ai_execution_enabled(state))
    setattr(state, "_rasai_catalog_extension_use_ai", use_ai)
    extension_id: str | None = None

    try:
        extra_live: set[str] = set()
        if "CAT-02" in added and bool(getattr(state, "web_performance", False)):
            extra_live.add("CAT-02")
        ready, detail, deadline = extension_readiness(
            workspace,
            audit_id,
            added,
            extra_live_catalogs=extra_live,
        )
        if not ready:
            raise ValueError(detail)

        order = [item.id for item in CATALOGS]
        base = tuple(value for value in order if value in current)
        added_ordered = tuple(value for value in order if value in added)
        effective = tuple(value for value in order if value in requested)
        rows = tuple(
            dict(row)
            for row in catalog_snapshot(state)
            if row.get("selected")
            and str(row.get("catalog_id") or row.get("id") or "").upper() in added
        )
        extension_contract = {
            "schema_version": SCHEMA_VERSION,
            "base": list(base),
            "added": list(added_ordered),
            "effective": list(effective),
            "ai_enabled": bool(ai_execution_enabled(state)),
        }
        extension_id = _insert_extension(
            workspace,
            audit_id,
            base=base,
            added=added_ordered,
            effective=effective,
            catalog_items=rows,
            configuration={"catalog_extension": extension_contract},
            live_valid_until=deadline,
        )
        execution_context = {
            "catalog_extension_id": extension_id,
            "catalog_extension": extension_contract,
        }

        # Everything after the durable request INSERT stays inside this guarded
        # lifecycle. Any pre-RPR failure is marked retryable and remains non-effective.
        components = _materialize_added_work(
            workspace,
            audit_id,
            state,
            added,
            live_valid_until=deadline,
        )
        recalculate(workspace, audit_id)

        with reprocess_policy(
            selected_items=tuple(sorted(components)),
            use_ai=use_ai,
            ai_provider=str(getattr(state, "ai_provider", "none") or "none"),
            ai_model=str(getattr(state, "ai_model", "") or "") or None,
            ai_reasoning=str(getattr(state, "ai_reasoning", "") or "") or None,
            execution_context=execution_context,
            workspace=workspace,
            audit_id=audit_id,
        ):
            result = reprocess_audit(
                audit_id,
                audits_root=state.audits_root,
                source="CONSOLE_CATALOG_EXTENSION",
            )

        if result.reprocess_id is None:
            # Projection-only extension, or a selected AI catalog intentionally kept
            # pending without provider authorization. Still create an auditable RPR.
            rpr = start_reprocess_run(
                workspace,
                audit_id,
                source="CONSOLE_CATALOG_EXTENSION",
                note="additive catalog extension without executable new collector",
                configuration={
                    "selected_items": [],
                    "use_ai": use_ai,
                    "ai_provider": (
                        str(getattr(state, "ai_provider", "none") or "none")
                        if use_ai
                        else None
                    ),
                    "ai_model": (
                        str(getattr(state, "ai_model", "") or "") or None
                        if use_ai
                        else None
                    ),
                    "ai_reasoning": (
                        str(getattr(state, "ai_reasoning", "") or "") or None
                        if use_ai
                        else None
                    ),
                    "execution_context": execution_context,
                },
            )
            summary = finish_reprocess_run(
                workspace,
                rpr,
                status=SUCCESS,
                attempted_items=0,
                successful_items=0,
                note="catálogo(s) adicionados; nenhum coletor novo executável nesta tentativa",
            )
            from rasai.report_completion import materialize_catalog_report_projection

            materialize_catalog_report_projection(audit_id=audit_id, workspace=workspace)
            result = ReprocessResult(
                audit_id=audit_id,
                reprocess_id=rpr,
                processing_status=summary.processing_status,
                score_status=summary.score_status,
                report_status=summary.report_status,
                consolidation_eligible=summary.consolidation_eligible,
                attempted_items=0,
                successful_items=0,
                skipped_success_items=summary.successful_items,
                remaining_items=summary.pending_items + summary.blocked_items,
                temporal_expired_items=summary.expired_items,
                report_root=workspace.root / "report-catalog",
                selected_items=0,
                unselected_items=0,
                ai_used=False,
            )

        # Do not mutate audit.db after the canonical RPR/report finalizer. The causal
        # RPR configuration makes the extension effective and keeps the sealed
        # fingerprint aligned with the final database state.
        return replace(result)
    except Exception as exc:
        if extension_id is not None:
            try:
                from rasai.secret_safety import redact_text

                diagnostic = redact_text(f"{type(exc).__name__}: {exc}")[:1000]
            except Exception:
                diagnostic = f"{type(exc).__name__}: {str(exc)[:900]}"
            rolled_back_work_items: tuple[str, ...] = ()
            try:
                unlinked = _mark_unlinked_extension_failed(
                    workspace,
                    audit_id,
                    extension_id,
                    note=diagnostic,
                )
                if unlinked:
                    rolled_back_work_items = _rollback_unlinked_extension_work(
                        workspace,
                        audit_id,
                        preexisting_work_item_ids=preexisting_work_item_ids,
                        candidate_components=extension_work_components,
                    )
                    try:
                        recalculate(workspace, audit_id)
                    except (OSError, sqlite3.Error):
                        pass
            except Exception:
                unlinked = False
            try:
                from rasai.operational_log import try_append_operational_event

                try_append_operational_event(
                    workspace,
                    "AUDIT_CATALOG_EXTENSION_FAILURE",
                    level="ERROR",
                    audit_id=audit_id,
                    catalog_extension_id=extension_id,
                    error_type=type(exc).__name__,
                    error_message=diagnostic,
                    pre_rpr_failure=bool(unlinked),
                    rolled_back_planning_work_items=list(rolled_back_work_items),
                )
            except Exception:
                pass
        raise
    finally:
        try:
            delattr(state, "_rasai_catalog_extension_use_ai")
        except AttributeError:
            pass


__all__ = [
    "SCHEMA_VERSION",
    "apply_catalog_extension",
    "effective_catalog_ids",
    "effective_catalog_projection",
    "extension_readiness",
]
