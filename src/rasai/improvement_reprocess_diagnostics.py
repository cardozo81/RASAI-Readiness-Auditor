"""Causal diagnostics for Improvement Intelligence during selective RPR.

This adapter does not own CAT-08 execution. It preserves diagnostics produced by the
canonical governed hook when a run row could not be materialized, and makes escaped
hook failures explicit instead of letting later reconciliation replace their cause.
"""
from __future__ import annotations

from typing import Any

from rasai.audit_fulfillment import (
    FAILED_RETRYABLE,
    set_work_item_status,
)
from rasai.operational_log import try_append_operational_event

_INSTALLED = False
_GENERIC_NOT_MATERIALIZED = "IMPROVEMENT_RETRY_NOT_MATERIALIZED"
_PRESERVABLE_STATUSES = frozenset(
    {"FAILED_RETRYABLE", "NOT_CONFIGURED", "REQUESTED_NOT_EXECUTED"}
)


def _specific_failure(item: Any | None) -> dict[str, Any] | None:
    if item is None:
        return None
    status = str(getattr(item, "status", "") or "").upper()
    code = str(getattr(item, "last_error_code", "") or "").strip()
    error_class = str(getattr(item, "last_error_class", "") or "").strip()
    message = str(getattr(item, "last_error_message", "") or "").strip()
    if (
        status not in _PRESERVABLE_STATUSES
        or not code
        or code == _GENERIC_NOT_MATERIALIZED
        or not (error_class or message)
    ):
        return None
    return {
        "status": status,
        "error_class": error_class or None,
        "error_code": code,
        "error_message": message or None,
        "retryable": bool(getattr(item, "retryable", True)),
    }


def _install_reconciliation_guard() -> None:
    from rasai import selective_optional_reprocess as optional

    original = optional._reconcile_improvement_rpr
    if bool(getattr(original, "_rasai_improvement_causal_guard", False)):
        return

    def reconcile(workspace: Any, audit_id: str) -> None:
        before = _specific_failure(
            optional._item(workspace, audit_id, "IMPROVEMENT_INTELLIGENCE")
        )
        original(workspace, audit_id)
        if before is None:
            return
        if optional._improvement_run(workspace, audit_id) is not None:
            return
        after = optional._item(workspace, audit_id, "IMPROVEMENT_INTELLIGENCE")
        if str(getattr(after, "last_error_code", "") or "") != _GENERIC_NOT_MATERIALIZED:
            return
        set_work_item_status(
            workspace,
            audit_id=audit_id,
            component="IMPROVEMENT_INTELLIGENCE",
            status=str(before["status"]),
            error_class=before["error_class"],
            error_code=str(before["error_code"]),
            error_message=before["error_message"],
            retryable=bool(before["retryable"]),
        )
        try_append_operational_event(
            workspace,
            "IMPROVEMENT_INTELLIGENCE_CAUSE_PRESERVED",
            level="INFO",
            audit_id=audit_id,
            error_class=before["error_class"],
            error_code=before["error_code"],
            provider_attempt_synthesized=False,
        )

    reconcile._rasai_improvement_causal_guard = True
    reconcile._rasai_original = original
    optional._reconcile_improvement_rpr = reconcile


def _install_governed_hook_guard() -> None:
    from rasai import audit_phase_runtime as phase

    hook = phase._AI_HOOKS.get("IMPROVEMENT_INTELLIGENCE")
    if hook is None:
        return
    current = hook.callback
    if bool(getattr(current, "_rasai_improvement_exception_guard", False)):
        return

    def guarded(*, audit_id: str, workspace: Any, evidence_snapshot: Any):
        try:
            return current(
                audit_id=audit_id,
                workspace=workspace,
                evidence_snapshot=evidence_snapshot,
            )
        except Exception as exc:
            code = f"IMPROVEMENT_GOVERNED_HOOK_{type(exc).__name__.upper()}"
            set_work_item_status(
                workspace,
                audit_id=audit_id,
                component="IMPROVEMENT_INTELLIGENCE",
                status=FAILED_RETRYABLE,
                error_class="ORCHESTRATION",
                error_code=code,
                error_message=str(exc)[:1000],
                retryable=True,
            )
            try_append_operational_event(
                workspace,
                "IMPROVEMENT_INTELLIGENCE_FAILURE",
                level="WARNING",
                audit_id=audit_id,
                stage="GOVERNED_HOOK",
                error_type=type(exc).__name__,
                error_message=str(exc)[:512],
                scoring_impact="NONE",
            )
            return {
                "status": "ERROR",
                "reason": code,
                "provider_called": False,
            }

    guarded._rasai_improvement_exception_guard = True
    guarded._rasai_original = current
    phase.register_ai_hook("IMPROVEMENT_INTELLIGENCE", guarded, order=hook.order)


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    _install_reconciliation_guard()
    _install_governed_hook_guard()
    _INSTALLED = True


__all__ = ["install"]
