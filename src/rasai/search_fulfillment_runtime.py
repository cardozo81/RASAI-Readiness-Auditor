"""Bind console-requested Search Intelligence to the canonical AUD fulfillment.

Search Monitoring in the SaaS control plane remains a separate SEARCH_MONITOR job.
This module covers only Search Intelligence explicitly requested as part of one local
AUD console execution. The work item stores the non-secret execution contract so a
later selective reprocessing run can repeat only this observation with the current
credential for the same provider/configuration.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from rasai.audit_fulfillment import (
    FAILED_RETRYABLE,
    LIVE_RECOLLECTION,
    SUCCESS,
    begin_attempt,
    finish_attempt,
    list_work_items,
    live_valid_until,
    project_report_validity,
    register_work_item,
    set_work_item_status,
)
from rasai.fulfillment_execution_contract import REQUESTED_NOT_EXECUTED
from rasai.persistence import AuditWorkspace

_INSTALLED = False


def _configuration(state: Any) -> dict[str, Any]:
    """Persist only non-secret settings required to reproduce the requested SERP work."""
    from rasai.console_search_intelligence import _engine_for_provider
    from rasai.search_intelligence.config import SerpRuntimeConfig

    try:
        runtime = SerpRuntimeConfig.from_environment(validate=False)
        provider = str(runtime.provider or "")
        runtime_config = {
            "mode": str(runtime.mode or "disabled"),
            "provider": provider,
            "engine": _engine_for_provider(provider),
            "fixture_path": str(runtime.fixture_path) if runtime.fixture_path is not None else "",
            "max_queries": int(runtime.max_queries),
            "max_requests": int(runtime.max_requests),
            "max_depth": int(runtime.max_depth),
            "max_competitors": int(runtime.max_competitors),
            "timeout_seconds": float(runtime.timeout_seconds),
            "retries": int(runtime.retries),
            "min_interval_seconds": float(runtime.min_interval_seconds),
        }
    except (OSError, TypeError, ValueError):
        runtime_config = {}

    return {
        "requested": True,
        "surface": "console-audit",
        "queries": list(tuple(getattr(state, "search_queries", ()) or ())),
        "depth": int(getattr(state, "search_depth", 20)),
        "region": str(getattr(state, "search_region", "") or ""),
        "device": str(getattr(state, "search_device", "mobile") or "mobile"),
        "competitive": bool(getattr(state, "search_competitive", True)),
        "compare_content": bool(getattr(state, "search_compare_content", False)),
        "max_content_pages": int(getattr(state, "search_max_content_pages", 3)),
        "content_timeout_seconds": float(getattr(state, "search_content_timeout_seconds", 10.0)),
        "content_max_bytes": int(getattr(state, "search_content_max_bytes", 2_000_000)),
        "content_max_redirects": int(getattr(state, "search_content_max_redirects", 5)),
        "ai_competitive": bool(getattr(state, "search_ai_competitive", False)),
        "ymyl_mode": str(getattr(state, "search_ymyl_mode", "AUTO") or "AUTO").upper(),
        "ai_provider": str(getattr(state, "ai_provider", "none") or "none"),
        "ai_model": str(getattr(state, "ai_model", "") or ""),
        "ai_timeout_seconds": float(getattr(state, "ai_timeout", 180.0) or 180.0),
        "market": str(getattr(state, "market", "BR") or "BR"),
        "language": str(getattr(state, "language", "pt-BR") or "pt-BR"),
        **runtime_config,
    }


def _workspace(state: Any) -> AuditWorkspace | None:
    audit_id = str(getattr(state, "audit_id", "") or "")
    if not audit_id:
        return None
    root = Path(getattr(state, "audits_root", "audits")) / audit_id
    if not (root / "audit.db").is_file():
        return None
    return AuditWorkspace.open(root)


def _current_item(workspace: AuditWorkspace, audit_id: str):
    return next(
        (
            item
            for item in list_work_items(workspace, audit_id)
            if item.component == "SEARCH_INTELLIGENCE" and item.scope_key == "AUDIT"
        ),
        None,
    )


def _project(state: Any) -> None:
    queries = tuple(getattr(state, "search_queries", ()) or ())
    if not queries:
        return
    workspace = _workspace(state)
    if workspace is None:
        return
    audit_id = str(state.audit_id)
    config = _configuration(state)
    register_work_item(
        workspace,
        audit_id=audit_id,
        component="SEARCH_INTELLIGENCE",
        required=True,
        temporal_mode=LIVE_RECOLLECTION,
        retryable=True,
        configuration=config,
        valid_until=live_valid_until(),
    )

    status = str(getattr(state, "search_last_status", "") or "").upper()
    detail = str(getattr(state, "search_last_detail", "") or "").strip()
    current_item = _current_item(workspace, audit_id)
    if status == "COMPLETE":
        if current_item is None or current_item.status != SUCCESS:
            attempt_id = begin_attempt(
                workspace,
                audit_id=audit_id,
                component="SEARCH_INTELLIGENCE",
                metadata={"surface": "console", "queries": len(queries)},
            )
            finish_attempt(
                workspace,
                attempt_id,
                status=SUCCESS,
                result_ref="search-intelligence:effective",
                retryable=False,
                metadata={"console_status": status},
            )
    elif status == "COMPLETE_WITH_LIMITATIONS":
        if current_item is None or current_item.status != SUCCESS:
            attempt_id = begin_attempt(
                workspace,
                audit_id=audit_id,
                component="SEARCH_INTELLIGENCE",
                metadata={"surface": "console", "queries": len(queries)},
            )
            finish_attempt(
                workspace,
                attempt_id,
                status=FAILED_RETRYABLE,
                error_class="SEARCH_PROVIDER",
                error_code="SEARCH_INTELLIGENCE_INCOMPLETE",
                error_message=detail or "Search Intelligence terminou com limitações",
                retryable=True,
                metadata={"console_status": status},
            )
    elif current_item is None or current_item.status != SUCCESS:
        set_work_item_status(
            workspace,
            audit_id=audit_id,
            component="SEARCH_INTELLIGENCE",
            status=REQUESTED_NOT_EXECUTED,
            error_class="ORCHESTRATION",
            error_code=REQUESTED_NOT_EXECUTED,
            error_message=detail or "Search Intelligence foi solicitado, mas não possui execução materializada",
            retryable=True,
        )
    project_report_validity(audit_id=audit_id, workspace=workspace)


def install(console_module: Any) -> None:
    """Wrap the complete console chain after Search execution but before final result UI."""
    global _INSTALLED
    if _INSTALLED:
        return
    original = console_module.run_audit_from_console
    if bool(getattr(original, "_rasai_search_fulfillment", False)):
        _INSTALLED = True
        return

    def run_with_search_fulfillment(state: Any) -> int:
        code = int(original(state) or 0)
        _project(state)
        return code

    run_with_search_fulfillment._rasai_search_fulfillment = True
    run_with_search_fulfillment._rasai_original = original
    console_module.run_audit_from_console = run_with_search_fulfillment
    _INSTALLED = True
