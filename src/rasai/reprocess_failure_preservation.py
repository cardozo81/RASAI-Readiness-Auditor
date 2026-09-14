"""Preserve authoritative recovery diagnostics during selective reprocessing.

A recovery adapter may already have projected a precise fulfillment state (for example
WAITING_FOR_DATA with a prerequisite code, or FAILED_RETRYABLE with the provider error)
before the generic reprocess orchestrator receives ``success=False``. The generic
fallback must not erase that more specific state with ``*_RETRY_INCOMPLETE``.
"""
from __future__ import annotations

from typing import Any

from rasai.audit_fulfillment import (
    BLOCKED,
    FAILED_PERMANENT,
    FAILED_RETRYABLE,
    WAITING_FOR_DATA,
    list_work_items,
)

_INSTALLED = False


def _current_item(workspace: Any, item: Any) -> Any | None:
    try:
        return next(
            current
            for current in list_work_items(workspace, str(item.audit_id))
            if current.component == str(item.component)
            and current.scope_key == str(item.scope_key)
        )
    except (StopIteration, OSError, ValueError, RuntimeError):
        return None


def should_preserve_failure(original: Any, current: Any | None) -> bool:
    """Return True when recovery already persisted a more authoritative failure."""
    if current is None:
        return False
    status = str(getattr(current, "status", ""))
    error_class = str(getattr(current, "last_error_class", "") or "")
    error_code = str(getattr(current, "last_error_code", "") or "")
    error_message = str(getattr(current, "last_error_message", "") or "")
    has_detail = bool(error_code or error_message)

    # Waiting/blocking states describe prerequisite or integrity conditions. Turning
    # them into a generic retry failure loses the operational reason and can encourage
    # pointless provider retries.
    if status in {WAITING_FOR_DATA, BLOCKED, FAILED_PERMANENT}:
        return has_detail

    if status != FAILED_RETRYABLE or not has_detail:
        return False

    # Technical AI recovery now reprojects the latest persisted provider attempt before
    # the generic orchestrator fallback runs. Preserve that authoritative provider or
    # evidence-contract diagnosis even when a repeated failure has the same code/text.
    # Replacing it with TECHNICAL_AI_RETRY_INCOMPLETE would reintroduce the original
    # information-loss bug on the second or later RPR.
    if (
        str(getattr(original, "component", "")) == "TECHNICAL_AI"
        and error_class in {"AI_CONTRACT", "AI_PROVIDER"}
    ):
        return True

    # Preserve a provider/service failure when this recovery evaluation changed the
    # effective diagnostic or created a fresh component attempt. An unchanged stale
    # generic failure can still be replaced by the orchestrator fallback.
    return (
        int(getattr(current, "attempt_count", 0) or 0)
        > int(getattr(original, "attempt_count", 0) or 0)
        or error_code != str(getattr(original, "last_error_code", "") or "")
        or error_message != str(getattr(original, "last_error_message", "") or "")
        or status != str(getattr(original, "status", ""))
    )


def _install_technical_ai_recovery_projection() -> None:
    """Project the newest technical-AI provider attempt before RPR fallback handling."""
    from rasai import reprocess_ai

    original = reprocess_ai.recover_technical_ai
    if bool(getattr(original, "_rasai_technical_diagnostic_projection", False)):
        return

    def recover_with_projection(*args: Any, **kwargs: Any):
        success, provider = original(*args, **kwargs)
        workspace = kwargs.get("workspace")
        audit_id = str(kwargs.get("audit_id") or "")
        if workspace is not None and audit_id:
            from rasai.fulfillment_execution_contract import reconcile_technical_ai_fulfillment

            reconcile_technical_ai_fulfillment(
                workspace=workspace,
                audit_id=audit_id,
                state="AVAILABLE" if success else None,
            )
        return success, provider

    recover_with_projection._rasai_technical_diagnostic_projection = True
    recover_with_projection._rasai_original = original
    reprocess_ai.recover_technical_ai = recover_with_projection


def install() -> None:
    """Wrap the generic fallback before the RPR trace wrapper is installed."""
    global _INSTALLED
    if _INSTALLED:
        return

    from rasai import audit_reprocess

    original = audit_reprocess._apply_result
    if not bool(getattr(original, "_rasai_preserve_reprocess_failure", False)):
        def apply_result(workspace: Any, *, item: Any, success: bool, **kwargs: Any) -> bool:
            if not success:
                current = _current_item(workspace, item)
                if should_preserve_failure(item, current):
                    return False
            return bool(original(workspace, item=item, success=success, **kwargs))

        apply_result._rasai_preserve_reprocess_failure = True
        apply_result._rasai_original = original
        audit_reprocess._apply_result = apply_result

    _install_technical_ai_recovery_projection()
    _INSTALLED = True
