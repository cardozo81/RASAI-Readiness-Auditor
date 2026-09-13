"""Integrity invalidation for successful core fulfillment work-items.

Ordinary retry state is monotonic: once a work-item reaches SUCCESS, later retries must
not downgrade it. Persisted-evidence integrity is different. If a source was recorded as
successful and the artifact that proves that result is no longer available, the logical
AUD can no longer be final or consolidatable. This module provides that one explicit
exception without weakening SUCCESS protection for normal retry/error transitions.
"""
from __future__ import annotations

from datetime import datetime, timezone
import sqlite3
from typing import Any

from rasai.audit_fulfillment import BLOCKED, SUCCESS, recalculate


_INTEGRITY_CODES = frozenset({
    "PERSISTED_RENDER_ARTIFACT_MISSING",
    "PERSISTED_EXTRACTION_SOURCE_MISSING",
})
_INSTALLED = False


def invalidate_persisted_evidence(
    workspace: Any,
    *,
    audit_id: str,
    component: str,
    scope_key: str,
    error_code: str,
    error_message: str | None = None,
) -> bool:
    """Invalidate an effective SUCCESS only for a persisted-evidence integrity loss.

    The previous effective_result_ref and last_success_at remain stored for forensic
    traceability. No provider/network attempt is created because integrity invalidation
    is an evidence-state transition, not a retry attempt.
    """
    if error_code not in _INTEGRITY_CODES:
        raise ValueError(f"unsupported integrity invalidation code: {error_code}")
    database = workspace.database
    now = datetime.now(timezone.utc).isoformat()
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    try:
        row = connection.execute(
            """SELECT work_item_id,status FROM audit_fulfillment_work_items
               WHERE audit_id=? AND component=? AND scope_key=?""",
            (audit_id, component.upper(), scope_key),
        ).fetchone()
        if row is None or str(row["status"]) != SUCCESS:
            return False
        with connection:
            connection.execute(
                """UPDATE audit_fulfillment_work_items SET
                   status=?,retryable=0,last_error_class='INTEGRITY',last_error_code=?,
                   last_error_message=?,updated_at=? WHERE work_item_id=?""",
                (
                    BLOCKED,
                    error_code,
                    (error_message or "")[:1000] or None,
                    now,
                    row["work_item_id"],
                ),
            )
    finally:
        connection.close()
    recalculate(workspace, audit_id)
    return True


def install() -> None:
    """Teach core projection to invalidate missing artifacts after prior SUCCESS."""
    global _INSTALLED
    if _INSTALLED:
        return
    from rasai import core_reprocessing

    original = core_reprocessing._set_item
    if getattr(original, "_rasai_integrity_invalidation", False):
        _INSTALLED = True
        return

    def set_item_with_integrity(*args: Any, **kwargs: Any) -> None:
        original(*args, **kwargs)
        status = str(kwargs.get("status") or "")
        error_code = str(kwargs.get("error_code") or "")
        if status != BLOCKED or error_code not in _INTEGRITY_CODES:
            return
        workspace = kwargs.get("workspace")
        if workspace is None and args:
            workspace = args[0]
        audit_id = str(kwargs.get("audit_id") or "")
        component = str(kwargs.get("component") or "")
        scope_key = str(kwargs.get("scope_key") or "")
        if workspace is None or not audit_id or not component or not scope_key:
            return
        invalidate_persisted_evidence(
            workspace,
            audit_id=audit_id,
            component=component,
            scope_key=scope_key,
            error_code=error_code,
            error_message=kwargs.get("error_message"),
        )

    set_item_with_integrity._rasai_integrity_invalidation = True
    set_item_with_integrity._rasai_original = original
    core_reprocessing._set_item = set_item_with_integrity
    _INSTALLED = True
