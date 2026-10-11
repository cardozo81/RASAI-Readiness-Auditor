"""#319: post-hoc AI-cost timing against the physically recorded AUD boundary.

Standalone offline advisory, not a replacement for provider ledger, pricing,
duration forecast, Directed Analysis orchestration or the AUD lifecycle.
"""
from __future__ import annotations

import argparse
from contextlib import closing
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from typing import Any, Sequence

from rasai.audit_attempt_timeline import _group, _stage

_MAX_ATTEMPTS = 5000
_BUCKETS = (
    "DURING_AUD", "AFTER_AUD", "CROSSES_AUD_COMPLETION", "UNKNOWN_CLOCK",
    "BEFORE_AUD", "CROSSES_AUD_START",
)
_TABLES = ("ai_provider_attempts", "content_remediation_attempts")
# Amount and duration fields can be absent in older physical AUDs. The
# reused stage ledger treats missing cost as unpriced (N/D), not zero.
_REQUIRED = {"attempt_id", "audit_id", "started_at", "finished_at"}


def _utc(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return result.astimezone(timezone.utc) if result.tzinfo else None
    except (ValueError, OverflowError, TypeError):
        return None


def _columns(con: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in con.execute(f"PRAGMA table_info({table})")}


def _render_bucket(kind: str, rows: list[tuple[str, dict]]) -> dict[str, Any]:
    grouped: dict[str, list[dict]] = {}
    for table, value in rows:
        grouped.setdefault(_group(value, table=table), []).append(value)
    stages = {label: _stage(label, grouped[label]) for label in sorted(grouped)}
    total = _stage(kind, [value for _, value in rows])
    return {
        "classification": kind,
        "attempts": total.attempts,
        "sum_call_durations_ms": round(total.summed_duration_ms, 3),
        "union_active_calls_ms": (
            round(total.union_active_ms, 3)
            if total.union_active_ms is not None else None
        ),
        "overlap_ms": (
            round(total.overlapping_duration_ms, 3)
            if total.overlapping_duration_ms is not None else None
        ),
        "provider_observed_cost_usd": round(total.priced_usd_provider_observed, 9),
        "posthoc_estimated_cost_usd": round(total.priced_usd_estimate, 9),
        "unknown_price_attempts": total.unpriced_attempts,
        "unknown_timing_attempts": total.unknown_intervals,
        "stages": {
            label: {
                "attempts": metric.attempts,
                "sum_call_durations_ms": round(metric.summed_duration_ms, 3),
                "provider_observed_cost_usd": round(metric.priced_usd_provider_observed, 9),
                "posthoc_estimated_cost_usd": round(metric.priced_usd_estimate, 9),
                "unknown_price_attempts": metric.unpriced_attempts,
            } for label, metric in stages.items()
        },
    }


def inspect_ai_audit_boundary(database: Path, audit_id: str) -> dict[str, Any]:
    """Separate calls by known physical timing, never by operation name alone."""
    path = Path(database)
    if not isinstance(audit_id, str) or not audit_id.startswith("AUD-"):
        raise ValueError("exact AUD identity required")
    if (not path.is_file() or path.is_symlink()
            or any(Path(str(path) + suffix).exists()
                   for suffix in ("-wal", "-shm", "-journal"))):
        raise ValueError("existing SQLite source without links or sidecars required")
    base = {
        "contract_version": "RASAI-AUD-AI-TIME-ECONOMICS-319-002",
        "audit_id": audit_id,
        "status": "NOT_COMPARABLE",
        "reason": None, "aud_started_at_utc": None,
        "aud_completed_at_utc": None,
        "buckets": [],
        "stage_latency_is_aud_total": False,
        "non_ai_stages_measured": False,
        "provider_invoice_verified": False,
        "post_aud_cost_included_in_aud_core_price": None,
        "provider_requests": 0, "audit_writes": 0,
        "source_rewritten": False,
        "limitations": (
            "Buckets classify persisted AI HTTP call intervals relative to "
            "audits.started_at AND audits.completed_at, not stage "
            "execution/wait or provider invoice. Calls before the start "
            "or crossing the start cannot be included in DURING_AUD. "
            "An interval crossing completion is never forcibly assigned to "
            "one side. Directed Analysis may run before/after completion; "
            "its name alone does not determine the bucket. Non-AI, PSI, "
            "capture and Apdex time remain N/D. Currencies other than USD "
            "and missing price are not silently converted or zero-filled."
        ),
    }
    def abstain(reason: str) -> dict[str, Any]:
        return {**base, "reason": reason}
    try:
        with closing(sqlite3.connect(
            path.resolve().as_uri() + "?mode=ro&immutable=1",
            uri=True, timeout=2,
        )) as con:
            con.row_factory = sqlite3.Row
            con.execute("PRAGMA query_only=ON")
            if not {"audit_id", "status", "completion_status", "started_at", "completed_at"} <= _columns(con, "audits"):
                return abstain("AUD_COMPLETION_SCHEMA_MISSING")
            audits = con.execute(
                "SELECT audit_id,status,completion_status,started_at,completed_at "
                "FROM audits LIMIT 2"
            ).fetchall()
            if (len(audits) != 1 or audits[0]["audit_id"] != audit_id
                    or str(audits[0]["status"]).upper() != "COMPLETED"
                    or str(audits[0]["completion_status"]).upper() != "COMPLETE"):
                return abstain("AUD_NOT_COMPLETE_OR_FOREIGN")
            started = _utc(audits[0]["started_at"])
            finished = _utc(audits[0]["completed_at"])
            if finished is None:
                return abstain("AUD_COMPLETION_CLOCK_UNVERIFIABLE")
            if started is None or started >= finished:
                return abstain("AUD_START_CLOCK_UNVERIFIABLE")
            rows: list[tuple[str, dict]] = []
            seen: set[tuple[str, str]] = set()
            for table in _TABLES:
                cols = _columns(con, table)
                if not cols:
                    continue
                if not _REQUIRED <= cols:
                    return abstain("AI_ATTEMPT_SCHEMA_INCOMPLETE")
                data = con.execute(
                    f"SELECT * FROM {table} WHERE audit_id=? LIMIT ?",
                    (audit_id, _MAX_ATTEMPTS + 1),
                ).fetchall()
                if len(data) + len(rows) > _MAX_ATTEMPTS:
                    return abstain("AI_ATTEMPT_VOLUME_EXCEEDED")
                for raw in data:
                    item = dict(raw)
                    identifier = item.get("attempt_id")
                    key = (table, identifier)
                    if (not isinstance(identifier, str)
                            or not identifier.strip() or key in seen):
                        return abstain("AI_ATTEMPT_ID_UNVERIFIABLE")
                    seen.add(key)
                    rows.append((table, item))
            buckets: dict[str, list[tuple[str, dict]]] = {name: [] for name in _BUCKETS}
            for table, item in rows:
                start = _utc(item.get("started_at"))
                end = _utc(item.get("finished_at"))
                if start is None or end is None or end < start:
                    bucket = "UNKNOWN_CLOCK"
                elif end <= started:
                    bucket = "BEFORE_AUD"
                elif start < started:
                    bucket = "CROSSES_AUD_START"
                elif end <= finished:
                    bucket = "DURING_AUD"
                elif start >= finished:
                    bucket = "AFTER_AUD"
                else:
                    bucket = "CROSSES_AUD_COMPLETION"
                buckets[bucket].append((table, item))
            return {
                **base,
                "status": "DESCRIPTIVE_ONLY",
                "aud_started_at_utc": started.isoformat(),
                "aud_completed_at_utc": finished.isoformat(),
                "total_attempts": len(rows),
                "buckets": [_render_bucket(k, buckets[k]) for k in _BUCKETS],
            }
    except (sqlite3.Error, OSError, ValueError, OverflowError):
        return abstain("AUD_SOURCE_READ_OR_SCHEMA_FAILURE")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Offline posthoc AI timing before/after AUD completion (#319)."
    )
    parser.add_argument("--audit-db", type=Path, required=True)
    parser.add_argument("--audit-id", required=True)
    args = parser.parse_args(argv)
    try:
        outcome = inspect_ai_audit_boundary(args.audit_db, args.audit_id)
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps(outcome, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
