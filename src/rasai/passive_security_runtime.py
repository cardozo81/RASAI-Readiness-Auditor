"""Governed runtime integration for the passive-security catalog."""
from __future__ import annotations

import sqlite3
from typing import Any

from rasai.audit_fulfillment import (
    FAILED_RETRYABLE,
    REPLAY_SAFE,
    SUCCESS,
    list_work_items,
    register_work_item,
    set_work_item_status,
)
from rasai.audit_phase_runtime import register_collection_hook, register_deterministic_hook
from rasai.operational_log import try_append_operational_event
from rasai.passive_security import (
    CONTRACT_VERSION,
    analyze_passive_security,
    collect_external_intelligence,
    enabled,
)

_INSTALLED = False
_COMPONENT = "PASSIVE_SECURITY"


def _collection_hook(*, audit_id: str, workspace: Any, source_blocked: bool = False):
    if not enabled():
        return {"collection_state": "DISABLED", "reason": "PASSIVE_SECURITY_NOT_SELECTED"}
    result = collect_external_intelligence(
        audit_id=audit_id,
        workspace=workspace,
        source_blocked=source_blocked,
    )
    try_append_operational_event(
        workspace,
        "PASSIVE_SECURITY_EXTERNAL_INTELLIGENCE",
        audit_id=audit_id,
        contract_version=CONTRACT_VERSION,
        result=result,
        active_scanning=False,
        scoring_impact="NONE",
    )
    return result


def _selected_reprocess_item(workspace: Any, audit_id: str):
    """Return PASSIVE_SECURITY only when explicitly inside the current RPR scope."""
    try:
        from rasai.reprocess_policy import current_policy, item_selected

        policy = current_policy()
        if policy.selected_items is None:
            return None
        return next(
            (
                item
                for item in list_work_items(workspace, audit_id)
                if str(item.component) == _COMPONENT and item_selected(item)
            ),
            None,
        )
    except Exception:
        return None


def _deterministic_hook(*, audit_id: str, workspace: Any, source_blocked: bool = False):
    if not enabled():
        item = _selected_reprocess_item(workspace, audit_id)
        if item is not None:
            current = str(getattr(item, "status", "") or "").upper()
            if current == SUCCESS:
                return {
                    "status": "COMPLETED",
                    "reason": "RPR_GOVERNED_RESULT_REUSED",
                }
            if current:
                return {
                    "status": current,
                    "reason": "RPR_GOVERNED_RESULT_REUSED",
                }
        return {"status": "DISABLED", "reason": "PASSIVE_SECURITY_NOT_SELECTED"}
    register_work_item(
        workspace,
        audit_id=audit_id,
        component=_COMPONENT,
        required=True,
        temporal_mode=REPLAY_SAFE,
        retryable=True,
        configuration={
            "contract_version": CONTRACT_VERSION,
            "mode": "PASSIVE_ONLY",
            "active_scanning": False,
            "reuses_persisted_http_browser_evidence": True,
        },
    )
    try:
        result = analyze_passive_security(
            audit_id=audit_id,
            workspace=workspace,
            source_blocked=source_blocked,
        )
    except Exception as exc:
        set_work_item_status(
            workspace,
            audit_id=audit_id,
            component=_COMPONENT,
            status=FAILED_RETRYABLE,
            error_class="PASSIVE_SECURITY",
            error_code=type(exc).__name__,
            error_message=str(exc)[:512],
            retryable=True,
        )
        raise
    status = str(result.get("status") or "").upper()
    if status in {"COMPLETED", "PARTIAL"}:
        set_work_item_status(
            workspace,
            audit_id=audit_id,
            component=_COMPONENT,
            status=SUCCESS,
            result_ref=f"passive_security_runs:{audit_id}",
        )
    else:
        set_work_item_status(
            workspace,
            audit_id=audit_id,
            component=_COMPONENT,
            status=FAILED_RETRYABLE,
            error_class="PASSIVE_SECURITY",
            error_code=status or "NO_RESULT",
            error_message=str(result.get("reason") or "Segurança passiva sem resultado")[:512],
            retryable=True,
        )
    try_append_operational_event(
        workspace,
        "PASSIVE_SECURITY_DETERMINISTIC_ANALYSIS",
        level="WARNING" if status == "PARTIAL" else "INFO",
        audit_id=audit_id,
        contract_version=CONTRACT_VERSION,
        result=result,
        active_scanning=False,
        scoring_impact="NONE",
    )
    return result


def _truthy(raw: Any, default: bool = False) -> bool:
    if raw in (None, ""):
        return default
    return str(raw).strip().casefold() in {"1", "true", "yes", "on", "sim", "s"}


def reconcile_persisted_coverage(workspace: Any, audit_id: str) -> bool:
    """Reopen an old CAT-10 SUCCESS only when requested coverage was never evaluated.

    This repairs audits produced by the catalog-extension bug where the governed
    PASSIVE_SECURITY calculation succeeded but OSV/CISA KEV states were never
    materialized. Prior success timestamp/result reference/history are preserved.
    """
    item = next(
        (
            value
            for value in list_work_items(workspace, audit_id)
            if str(value.component) == _COMPONENT
        ),
        None,
    )
    if item is None or str(item.status).upper() != SUCCESS:
        return False

    configuration = dict(getattr(item, "configuration", {}) or {})
    expected: set[str] = set()
    if _truthy(configuration.get("osv"), True):
        expected.add("OSV")
    if _truthy(configuration.get("kev"), True):
        expected.add("CISA_KEV")
    if not expected:
        return False

    connection = sqlite3.connect(workspace.database)
    try:
        table = connection.execute(
            """SELECT 1 FROM sqlite_master
               WHERE type='table' AND name='passive_security_integrations'"""
        ).fetchone()
        actual = set()
        if table is not None:
            actual = {
                str(row[0]).upper()
                for row in connection.execute(
                    """SELECT integration_id FROM passive_security_integrations
                       WHERE audit_id=?""",
                    (audit_id,),
                ).fetchall()
            }
    finally:
        connection.close()

    missing = sorted(expected - actual)
    if not missing:
        return False

    from rasai.governed_fulfillment_invalidation import invalidate_work_item

    return invalidate_work_item(
        workspace,
        audit_id=audit_id,
        component=_COMPONENT,
        error_class="EVIDENCE_COVERAGE",
        error_code="PASSIVE_SECURITY_EXTERNAL_COVERAGE_INCOMPLETE",
        error_message=(
            "CAT-10 possui resultado efetivo, mas a cobertura solicitada não foi "
            "materializada para: " + ", ".join(missing)
        ),
        retryable=True,
    )


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    # MDN Observatory is registered at order 32. Security external intelligence runs
    # after existing standards collectors and before deterministic derivations.
    register_collection_hook("PASSIVE_SECURITY_INTELLIGENCE", _collection_hook, order=38)
    register_deterministic_hook("PASSIVE_SECURITY", _deterministic_hook, order=80)
    _INSTALLED = True


__all__ = ["install", "reconcile_persisted_coverage"]
