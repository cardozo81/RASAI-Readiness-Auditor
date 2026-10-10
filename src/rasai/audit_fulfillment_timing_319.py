"""#319: read-only fulfillment *attempt* elapsed-time evidence.

The fulfillment ledger records work-item wrappers, not instrumented collector
stage boundaries. These intervals cannot be subtracted from an AUD wall clock,
interpreted as exclusive phase duration, or merged with M18/M20 attempt clocks.
Reprocess attempts and insufficient timestamp provenance remain distinct.
"""
from __future__ import annotations

from datetime import datetime, timezone
import math
import sqlite3
from typing import Any

_MAX_MS = 48 * 60 * 60 * 1000
_MAX_ATTEMPTS = 2000
_REQUIRED_ATTEMPT = {
    "attempt_id", "audit_id", "work_item_id", "reprocess_id",
    "started_at", "finished_at", "status",
}
_REQUIRED_ITEM = {"work_item_id", "audit_id", "component"}


def _columns(connection: sqlite3.Connection, table: str) -> set[str]:
    # Table name is an internal constant, not user-supplied SQL.
    return {str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})")}


def _instant(value: Any) -> float | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            return None
        result = parsed.astimezone(timezone.utc).timestamp() * 1000
        return result if math.isfinite(result) else None
    except (ValueError, OverflowError, TypeError):
        return None


def _union_ms(intervals: list[tuple[float, float]]) -> float:
    if not intervals:
        return 0.0
    ordered = sorted(intervals)
    start, end = ordered[0]
    active = 0.0
    for lo, hi in ordered[1:]:
        if lo > end:
            active += end - start
            start, end = lo, hi
        else:
            end = max(end, hi)
    return active + end - start


def inspect_fulfillment_attempt_intervals(
    connection: sqlite3.Connection,
    audit_id: str,
    verified_console_window: tuple[float, float, float] | None,
) -> dict[str, Any]:
    """Inspect existing AUD-scoped WKA wrapper timestamps without SQLite writes.

    verified_console_window is (wall_ms, start_epoch_ms, finish_epoch_ms)
    validated by the independent #319 single-session verifier. Temporal
    placement alone does NOT prove a stage ran exclusively in that session.
    """
    result: dict[str, Any] = {
        "contract_version": "RASAI-FULFILLMENT-ATTEMPT-TIMING-001",
        "status": "NOT_AVAILABLE",
        "source": "audit_fulfillment_attempts+audit_fulfillment_work_items",
        "measurement": "WRAPPER_ATTEMPT_ELAPSED_NOT_STAGE_WALL_CLOCK",
        "physical_stage_duration_available": False,
        "attempts_total": 0,
        "by_component": [],
        "note": (
            "Intervalos entre begin_attempt/finish_attempt representam tentativas "
            "de fulfillment, nao cronometros exclusivos de captura, renderizacao, "
            "extracao, Apdex ou relatorio. Nao somar com IA/HTTP, nao subtrair "
            "da duracao da AUD e nao usar como previsao fisica por etapa."
        ),
        "provider_requests": 0,
        "audit_writes": 0,
    }
    if not (
        _REQUIRED_ATTEMPT <= _columns(connection, "audit_fulfillment_attempts")
        and _REQUIRED_ITEM <= _columns(connection, "audit_fulfillment_work_items")
    ):
        result["status"] = "SCHEMA_NOT_AVAILABLE"
        return result
    rows = connection.execute(
        """
        SELECT a.attempt_id, a.started_at, a.finished_at, a.status,
               a.reprocess_id, w.component
          FROM audit_fulfillment_attempts AS a
          JOIN audit_fulfillment_work_items AS w
            ON w.work_item_id=a.work_item_id AND w.audit_id=a.audit_id
         WHERE a.audit_id=?
         ORDER BY a.attempt_id
         LIMIT ?
        """,
        (audit_id, _MAX_ATTEMPTS + 1),
    ).fetchall()
    if len(rows) > _MAX_ATTEMPTS:
        result["status"] = "ATTEMPT_LIMIT_EXCEEDED"
        return result
    if not rows:
        result["status"] = "NO_ATTEMPTS"
        return result
    by_key: dict[tuple[str, str], dict[str, Any]] = {}
    seen: set[str] = set()
    for attempt_id, started, finished, status, reprocess_id, component in rows:
        # Duplicate or malformed identifiers make the ledger unsuitable for
        # a complete projection; do not return partial totals as exhaustive.
        if not isinstance(attempt_id, str) or not attempt_id or attempt_id in seen:
            result["status"] = "ATTEMPT_IDENTITY_UNVERIFIABLE"
            return result
        seen.add(attempt_id)
        name = str(component or "").strip().upper()
        if not name:
            name = "COMPONENT_UNVERIFIED"
        lo, hi = _instant(started), _instant(finished)
        valid = (
            lo is not None and hi is not None
            and 0 < hi - lo <= _MAX_MS
            and str(status or "").upper() != "RUNNING"
        )
        if reprocess_id:
            placement = "REPROCESS_ATTEMPT"
        elif not valid or verified_console_window is None:
            placement = "WINDOW_UNVERIFIED"
        elif verified_console_window[1] <= lo and hi <= verified_console_window[2]:
            placement = "WITHIN_VERIFIED_CONSOLE_WINDOW"
        elif hi < verified_console_window[1]:
            placement = "BEFORE_VERIFIED_CONSOLE_WINDOW"
        elif lo > verified_console_window[2]:
            placement = "AFTER_VERIFIED_CONSOLE_WINDOW"
        else:
            placement = "CROSSES_CONSOLE_WINDOW"
        key = (name, placement)
        group = by_key.setdefault(key, {
            "component": name,
            "temporal_scope": placement,
            "attempts": 0,
            "verified_intervals": 0,
            "unknown_intervals": 0,
            "_intervals": [],
        })
        group["attempts"] += 1
        if valid:
            group["verified_intervals"] += 1
            group["_intervals"].append((lo, hi))
        else:
            group["unknown_intervals"] += 1
    for group in by_key.values():
        intervals = group.pop("_intervals")
        if group["unknown_intervals"]:
            group["summed_elapsed_ms"] = None
            group["union_elapsed_ms"] = None
            group["overlap_elapsed_ms"] = None
        else:
            total = sum(hi - lo for lo, hi in intervals)
            union = _union_ms(intervals)
            group["summed_elapsed_ms"] = round(total, 2)
            group["union_elapsed_ms"] = round(union, 2)
            group["overlap_elapsed_ms"] = round(total - union, 2)
    result["status"] = "ATTEMPT_INTERVALS_WITH_LIMITATIONS"
    result["attempts_total"] = len(rows)
    result["by_component"] = [
        by_key[key] for key in sorted(by_key)
    ]
    return result
