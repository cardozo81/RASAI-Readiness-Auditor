"""#319: read-only, audit-scoped chronology of persisted commercial AI attempts.

This is POST-HOC telemetry, not ex-ante forecast, invoicing, Apdex,
collector latency or a modification to AI pricing/provider selection.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import math
import sqlite3

_MAX_LEDGER_ROWS = 10000


@dataclass(frozen=True, slots=True)
class TimelineStage:
    name: str
    attempts: int
    summed_duration_ms: float
    union_active_ms: float | None
    overlapping_duration_ms: float | None
    priced_usd_estimate: float
    priced_usd_provider_observed: float
    unpriced_attempts: int
    unknown_intervals: int
    observed_cost_attempts: int = 0


@dataclass(frozen=True, slots=True)
class AuditAttemptTimeline:
    audit_id: str
    stages: tuple[TimelineStage, ...]
    attempts: int
    summed_duration_ms: float
    union_active_ms: float | None
    overlapping_duration_ms: float | None
    provider_observed_usd: float
    posthoc_estimated_usd: float
    unpriced_attempts: int
    unknown_intervals: int
    non_ai_stages_measured: bool = False

    @property
    def timing_caveat(self) -> str:
        return (
            "Soma de durações pode conter simultaneidade; tempo ativo é a união "
            "dos intervalos de chamadas IA registrados, não a duração total AUD. "
            "Coleta, PSI e Apdex não estão medidos nesta projeção."
        )


def _time(raw: object) -> float | None:
    if raw is None or not str(raw).strip():
        return None
    try:
        value = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        if value.tzinfo is None:
            return None  # Never combine naive clocks with offset-aware timestamps.
        return value.astimezone(timezone.utc).timestamp() * 1000
    except (ValueError, OverflowError):
        return None


def _interval_union(intervals: list[tuple[float, float]]) -> float:
    union = 0.0
    until: float | None = None
    for start, stop in sorted(intervals):
        if until is None or start > until:
            union += stop - start
            until = stop
        else:
            union += max(0.0, stop - until)
            until = max(until, stop)
    return union


def _group(row: dict, *, table: str) -> str:
    if table == "content_remediation_attempts":
        return "CONTENT_REMEDIATION"
    if str(row.get("surface") or "").upper() == "SEARCH_API":
        return "EXTERNAL_SEARCH_API"
    operation = str(row.get("operation") or row.get("ai_task_id") or "").strip().upper()
    if "DIRECTED" in operation:
        return "DIRECTED_ANALYSIS"
    if "IMPROVEMENT" in operation:
        return "IMPROVEMENT_INTELLIGENCE"
    if "COMPETITIVE" in operation:
        return "COMPETITIVE_AI"
    return operation if operation else "OTHER_AI"


def _stage(name: str, rows: list[dict]) -> TimelineStage:
    intervals: list[tuple[float, float]] = []
    elapsed = 0.0
    unknown = 0
    estimated = observed = 0.0
    unpriced = 0
    observed_count = 0
    for row in rows:
        start = _time(row.get("started_at"))
        stop = _time(row.get("finished_at"))
        if start is None or stop is None or stop < start:
            unknown += 1
            # When timestamps are incomplete, retain the available duration for
            # summed telemetry, but do not claim a calculable interval union.
            duration = row.get("duration_ms")
            if duration is not None:
                try:
                    value = float(duration)
                    if math.isfinite(value) and value >= 0:
                        elapsed += value
                except (ValueError, TypeError, OverflowError):
                    pass
        else:
            # Compare like with like. Persisted duration_ms is a separately
            # rounded clock and can differ by milliseconds from wall timestamps.
            # Using it here could imply an impossible union > summed duration.
            intervals.append((start, stop))
            elapsed += stop - start
        observed_value = row.get("observed_cost")
        estimate_value = row.get("estimated_cost")
        observed_currency = str(row.get("observed_cost_currency") or "").upper()
        estimate_currency = str(row.get("cost_currency") or "").upper()
        try:
            if observed_value is not None and observed_currency == "USD":
                amount = float(observed_value)
                if not math.isfinite(amount) or amount < 0:
                    raise ValueError("invalid observed provider amount")
                observed += amount
                observed_count += 1
            elif estimate_value is not None and estimate_currency == "USD":
                amount = float(estimate_value)
                if not math.isfinite(amount) or amount < 0:
                    raise ValueError("invalid posthoc estimate amount")
                estimated += amount
            else:
                unpriced += 1
        except (ValueError, TypeError, OverflowError):
            # Do not let NaN/Infinity/negative values enter the aggregate.
            # Unlike provider ledger, this projection cannot infer a price.
            unpriced += 1
    active = _interval_union(intervals) if not unknown else None
    return TimelineStage(
        name=name,
        attempts=len(rows),
        summed_duration_ms=elapsed,
        union_active_ms=active,
        overlapping_duration_ms=max(elapsed - active, 0.0) if active is not None else None,
        priced_usd_estimate=estimated,
        priced_usd_provider_observed=observed,
        unpriced_attempts=unpriced,
        unknown_intervals=unknown,
        observed_cost_attempts=observed_count,
    )


def _sealed_timeline_source(db: Path) -> None:
    if (
        db.is_symlink() or not db.is_file()
        or any(Path(str(db) + ending).exists()
               for ending in ("-wal", "-shm", "-journal"))
    ):
        raise ValueError("AI attempt timeline SQLite source has unverified WAL/SHM/journal")


def read_audit_attempt_timeline(
    database: Path, audit_id: str, *, sealed_source: bool = False,
) -> AuditAttemptTimeline:
    """Read both economic ledgers once. Opt in to immutable sealed-AUD mode.

    Existing running-console/forecast callers retain their historical
    mode=ro semantics. Physical offline inspectors require sealed_source.
    """
    database = Path(database)
    if sealed_source:
        _sealed_timeline_source(database)
    uri = database.resolve().as_uri() + (
        "?mode=ro&immutable=1" if sealed_source else "?mode=ro"
    )
    connection = sqlite3.connect(uri, uri=True, timeout=5)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA query_only=ON")
        groups: dict[str, list[dict]] = {}
        all_rows: list[dict] = []
        # Attempt IDs are generated identities, not table-local row numbers.
        # A collision across M18/M20 makes a complete economic census unsafe.
        global_seen: set[str] = set()
        for table in ("ai_provider_attempts", "content_remediation_attempts"):
            if connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
            ).fetchone() is None:
                continue
            rows = connection.execute(
                f"SELECT * FROM {table} WHERE audit_id=? LIMIT ?",
                (audit_id, _MAX_LEDGER_ROWS + 1),
            ).fetchall()
            if len(rows) > _MAX_LEDGER_ROWS or len(all_rows) + len(rows) > _MAX_LEDGER_ROWS:
                raise ValueError("bounded AI attempt timeline ledger population exceeded")
            seen: set[str] = set()
            for raw in rows:
                row = dict(raw)
                key = str(row.get("attempt_id") or "").strip()
                # A physical duplicate is not a second observation and not
                # an ignorable row. Silently dropping it understates cost and
                # time; refuse the entire ambiguous ledger instead.
                if not key or key in seen:
                    raise ValueError(
                        "ambiguous AI attempt_id in physical " + table + " ledger"
                    )
                if key in global_seen:
                    raise ValueError("ambiguous AI attempt_id across physical ledgers")
                seen.add(key)
                global_seen.add(key)
                name = _group(row, table=table)
                groups.setdefault(name, []).append(row)
                all_rows.append(row)
        stages = tuple(_stage(key, groups[key]) for key in sorted(groups))
        total = _stage("ALL_ATTEMPTS", all_rows)
        result = AuditAttemptTimeline(
            audit_id=audit_id,
            stages=stages,
            attempts=total.attempts,
            summed_duration_ms=total.summed_duration_ms,
            union_active_ms=total.union_active_ms,
            overlapping_duration_ms=total.overlapping_duration_ms,
            provider_observed_usd=total.priced_usd_provider_observed,
            posthoc_estimated_usd=total.priced_usd_estimate,
            unpriced_attempts=total.unpriced_attempts,
            unknown_intervals=total.unknown_intervals,
        )
    finally:
        connection.close()
    if sealed_source:
        _sealed_timeline_source(database)
    return result
