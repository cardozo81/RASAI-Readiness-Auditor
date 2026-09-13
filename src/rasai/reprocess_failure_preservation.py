"""Preserve authoritative recovery diagnostics during selective reprocessing.

A recovery adapter may already have projected a precise fulfillment state (for example
WAITING_FOR_DATA with a prerequisite code, or FAILED_RETRYABLE with the provider error)
before the generic reprocess orchestrator receives ``success=False``.  The generic
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
    error_code = str(getattr(current, "last_error_code", "") or "")
    error_message = str(getattr(current, "last_error_message", "") or "")
    has_detail = bool(error_code or error_message)

    # Waiting/blocking states describe prerequisite or integrity conditions.  Turning
    # them into a generic retry failure loses the operational reason and can encourage
    # pointless provider retries.
    if status in {WAITING_FOR_DATA, BLOCKED, FAILED_PERMANENT}:
        return has_detail

    if status != FAILED_RETRYABLE or not has_detail:
        return False

    # Preserve a provider/service failure when this recovery evaluation changed the
    # effective diagnostic or created a fresh component attempt.  An unchanged stale
    # generic failure can still be replaced by the orchestrator fallback.
    return (
        int(getattr(current, "attempt_count", 0) or 0)
        > int(getattr(original, "attempt_count", 0) or 0)
        or error_code != str(getattr(original, "last_error_code", "") or "")
        or error_message != str(getattr(original, "last_error_message", "") or "")
        or status != str(getattr(original, "status", ""))
    )


def install() -> None:
    """Wrap the generic fallback before the RPR trace wrapper is installed."""
    global _INSTALLED
    if _INSTALLED:
        return

    from rasai import audit_reprocess

    original = audit_reprocess._apply_result
    if bool(getattr(original, "_rasai_preserve_reprocess_failure", False)):
        _INSTALLED = True
        return

    def apply_result(workspace: Any, *, item: Any, success: bool, **kwargs: Any) -> bool:
        if not success:
            current = _current_item(workspace, item)
            if should_preserve_failure(item, current):
                return False
        return bool(original(workspace, item=item, success=success, **kwargs))

    apply_result._rasai_preserve_reprocess_failure = True
    apply_result._rasai_original = original
    audit_reprocess._apply_result = apply_result
    _INSTALLED = True
