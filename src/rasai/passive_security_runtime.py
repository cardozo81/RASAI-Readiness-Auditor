"""Governed runtime integration for the passive-security catalog."""
from __future__ import annotations

from typing import Any

from rasai.audit_fulfillment import (
    FAILED_RETRYABLE,
    REPLAY_SAFE,
    SUCCESS,
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


def _deterministic_hook(*, audit_id: str, workspace: Any, source_blocked: bool = False):
    if not enabled():
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


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    # MDN Observatory is registered at order 32. Security external intelligence runs
    # after existing standards collectors and before deterministic derivations.
    register_collection_hook("PASSIVE_SECURITY_INTELLIGENCE", _collection_hook, order=38)
    register_deterministic_hook("PASSIVE_SECURITY", _deterministic_hook, order=80)
    _INSTALLED = True


__all__ = ["install"]
