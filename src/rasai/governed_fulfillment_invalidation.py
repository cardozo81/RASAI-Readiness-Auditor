"""Explicit fulfillment invalidation for evidence-version transitions.

Normal fulfillment intentionally treats SUCCESS as monotonic so a later transient error
cannot erase an effective result. Evidence-version invalidation is different: when a
previous AI result is formally marked STALE, the corresponding work item must become
retryable again while preserving its prior success timestamp/reference and history.

Only the governed RPR stale transition is allowed through this adapter; the general
``set_work_item_status`` monotonic-success contract remains unchanged.
"""
from __future__ import annotations

from datetime import datetime, timezone
import sqlite3
from typing import Any


_INSTALLED = False


def invalidate_ai_work_item(
    workspace: Any,
    *,
    audit_id: str,
    component: str,
    scope_key: str = "AUDIT",
    error_code: str = "AI_RESULT_STALE",
    error_message: str = "resultado de IA invalidado por mudança da evidência dependente",
) -> None:
    from rasai.audit_fulfillment import FAILED_RETRYABLE, ensure_schema, recalculate

    ensure_schema(workspace)
    now = datetime.now(timezone.utc).isoformat()
    connection = sqlite3.connect(workspace.database)
    try:
        row = connection.execute(
            """SELECT work_item_id FROM audit_fulfillment_work_items
               WHERE audit_id=? AND component=? AND scope_key=?""",
            (audit_id, str(component).upper(), scope_key),
        ).fetchone()
        if row is None:
            return
        with connection:
            connection.execute(
                """UPDATE audit_fulfillment_work_items SET
                   status=?,retryable=1,last_error_class='EVIDENCE_VERSION',
                   last_error_code=?,last_error_message=?,updated_at=?
                   WHERE work_item_id=?""",
                (
                    FAILED_RETRYABLE,
                    error_code,
                    str(error_message)[:1000],
                    now,
                    str(row[0]),
                ),
            )
    finally:
        connection.close()
    recalculate(workspace, audit_id)


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    try:
        from rasai import governed_reprocess_runtime as rpr
    except ImportError:
        _INSTALLED = True
        return

    current = rpr.set_work_item_status
    if not bool(getattr(current, "_rasai_stale_invalidation", False)):
        def set_work_item_status(*args: Any, **kwargs: Any):
            if (
                str(kwargs.get("error_code") or "").upper() == "AI_RESULT_STALE"
                and str(kwargs.get("status") or "").upper() != "SUCCESS"
            ):
                return invalidate_ai_work_item(
                    args[0] if args else kwargs.get("workspace"),
                    audit_id=str(kwargs.get("audit_id") or ""),
                    component=str(kwargs.get("component") or ""),
                    scope_key=str(kwargs.get("scope_key") or "AUDIT"),
                    error_code="AI_RESULT_STALE",
                    error_message=str(kwargs.get("error_message") or "resultado de IA stale"),
                )
            return current(*args, **kwargs)

        set_work_item_status._rasai_stale_invalidation = True
        set_work_item_status._rasai_original = current
        rpr.set_work_item_status = set_work_item_status
    _INSTALLED = True


__all__ = ["install", "invalidate_ai_work_item"]
