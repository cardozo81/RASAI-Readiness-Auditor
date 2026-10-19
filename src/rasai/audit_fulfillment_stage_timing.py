"""#319: post-hoc work-item attempt intervals, not exclusive stage timers.

Audit fulfillment attempts can contain retries, post-AUD recovery, or work
that overlaps AI and HTTP request ledgers. This *additional* observation never
changes a method or estimates non-AI-only elapsed time by subtraction.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any
import sqlite3

from rasai.audit_attempt_timeline import _time, _interval_union
from rasai.audit_fulfillment_timing import _FINISHED_STATES

_MAX_ATTEMPTS = 10_000
_MAX_COMPONENTS = 32
_MAX_INTERVAL_MS = 7 * 24 * 60 * 60 * 1000


def fulfillment_attempt_intervals(
    con: sqlite3.Connection, audit_id: str,
) -> dict[str, Any]:
    """Read all rows for one AUD or abstain, never return a biased truncated set."""
    absent = {
        "status": "NOT_AVAILABLE", "attempts": None, "components": [],
        "scope": "FULFILLMENT_WORK_ATTEMPTS_NOT_EXCLUSIVE_PHASES",
        "exclusive_non_ai_timing_proven": False,
    }
    if not isinstance(audit_id, str) or not audit_id.strip():
        return absent
    try:
        required = {
            "audit_fulfillment_work_items": {
                "work_item_id", "audit_id", "component",
            },
            "audit_fulfillment_attempts": {
                "attempt_id", "audit_id", "work_item_id", "started_at",
                "finished_at", "status", "reprocess_id",
            },
        }
        for table, columns in required.items():
            found = {str(row[1]) for row in con.execute(
                "PRAGMA table_info(" + table + ")"
            )}
            if not columns.issubset(found):
                return absent
        rows = con.execute(
            "SELECT a.attempt_id, w.component, a.started_at, a.finished_at, "
            "a.status, a.reprocess_id, w.audit_id, a.audit_id "
            "FROM audit_fulfillment_attempts a "
            "LEFT JOIN audit_fulfillment_work_items w "
            "ON w.work_item_id=a.work_item_id AND w.audit_id=a.audit_id "
            "WHERE a.audit_id=? ORDER BY a.attempt_id LIMIT ?",
            (audit_id, _MAX_ATTEMPTS + 1),
        ).fetchall()
        if len(rows) > _MAX_ATTEMPTS:
            return {**absent, "status": "POPULATION_LIMIT"}
        if not rows:
            return {**absent, "status": "NO_RECORDED_ATTEMPTS", "attempts": 0}
        identified: set[str] = set()
        groups: dict[str, list[tuple[float, float] | None]] = defaultdict(list)
        recovery: dict[str, int] = defaultdict(int)
        unsuccessful: dict[str, int] = defaultdict(int)
        non_terminal: dict[str, int] = defaultdict(int)
        cohort_intervals: list[tuple[float, float]] = []
        for attempt, component, started, finished, status, reprocess_id, work_aud, attempt_aud in rows:
            # A foreign/orphan work item or duplicated LEFT JOIN match must
            # invalidate the cohort, never vanish silently from denominators.
            if (
                not isinstance(attempt, str) or not attempt
                or attempt != attempt.strip()
                or any(ord(ch) < 32 or ord(ch) == 127 for ch in attempt)
                or attempt in identified
                or not isinstance(component, str) or not component
                or component != component.strip() or len(component) > 120
                or any(ord(ch) < 32 or ord(ch) == 127 for ch in component)
                or work_aud != audit_id or attempt_aud != audit_id
            ):
                return {**absent, "status": "INCONSISTENT_AUD_IDENTITIES"}
            identified.add(attempt)
            first = _time(started)
            last = _time(finished)
            terminal = isinstance(status, str) and status in _FINISHED_STATES
            # A filled finished_at is not proof that a RUNNING or unknown
            # attempt terminated; zero-length clocks are also unverifiable.
            if (
                not terminal or first is None or last is None
                or last <= first or last - first > _MAX_INTERVAL_MS
            ):
                groups[component].append(None)
            else:
                groups[component].append((first, last))
                cohort_intervals.append((first, last))
            if not terminal:
                non_terminal[component] += 1
            if reprocess_id is not None:
                recovery[component] += 1
            if status != "SUCCESS":
                unsuccessful[component] += 1
        if len(groups) > _MAX_COMPONENTS:
            return {**absent, "status": "TOO_MANY_COMPONENTS"}
        components = []
        for name, samples in sorted(groups.items()):
            available = [s for s in samples if s is not None]
            complete = len(available) == len(samples)
            summed = sum(b - a for a, b in available) if complete else None
            union = _interval_union(available) if complete else None
            components.append({
                "component": name,
                "attempts": len(samples),
                "complete_time_intervals": len(available),
                "unknown_time_intervals": len(samples) - len(available),
                "reprocess_attempts": recovery[name],
                "non_success_attempts": unsuccessful[name],
                "non_terminal_attempts": non_terminal[name],
                "summed_ms": summed,
                "union_active_ms": union,
                "exclusive_phase_timer": False,
                "overlap_with_ai_or_http_possible": True,
            })
        # Cross-component attempt envelope: the union across ALL work-item
        # attempts (not the sum of per-component active times). Gaps between
        # first and last attempt are not "idle AUD" since activity outside
        # the fulfillment ledger may be unobserved.
        all_timed = len(cohort_intervals) == len(rows)
        if all_timed:
            active = _interval_union(cohort_intervals)
            summed_all = sum(end - start for start, end in cohort_intervals)
            elapsed_span = (
                max(end for _, end in cohort_intervals)
                - min(start for start, _ in cohort_intervals)
            )
            envelope = {
                "status": "COMPLETE_RECORDED_ATTEMPT_COHORT",
                "attempts_with_timing": len(cohort_intervals),
                "total_attempts": len(rows),
                "summed_attempt_ms": summed_all,
                "union_active_ms": active,
                "overlap_attempt_ms": max(0.0, summed_all - active),
                "observed_span_ms": elapsed_span,
                "unobserved_gap_between_attempts_ms": max(0.0, elapsed_span - active),
                "exclusive_audit_or_non_ai_wall_time_proven": False,
            }
        else:
            envelope = {
                "status": "INCOMPLETE_ATTEMPT_COHORT",
                "attempts_with_timing": len(cohort_intervals),
                "total_attempts": len(rows),
                "summed_attempt_ms": None,
                "union_active_ms": None,
                "overlap_attempt_ms": None,
                "observed_span_ms": None,
                "unobserved_gap_between_attempts_ms": None,
                "exclusive_audit_or_non_ai_wall_time_proven": False,
            }
        return {
            **absent,
            "status": "OBSERVED_NONEXCLUSIVE_WORK_INTERVALS",
            "attempts": len(rows), "components": components,
            "attempt_envelope": envelope,
            "posthoc_only": True,
            "work_outside_initial_audit_possible": True,
        }
    except (sqlite3.Error, TypeError, ValueError, OverflowError):
        return {**absent, "status": "SCHEMA_OR_WORK_COHORT_UNVERIFIABLE"}


__all__ = ["fulfillment_attempt_intervals"]
