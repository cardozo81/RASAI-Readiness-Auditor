"""#319: read-only single-AUD attempt chronology inspection.

It reports the canonical M18 + M20 ledgers without adding physical
request elapsed times, AI costs, or speculative non-AI stage estimates.
No replay, provider requests, DDL, or original report materialization.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from dataclasses import asdict
import json
import math
from pathlib import Path
import re
import sqlite3
from typing import Sequence

from rasai.audit_attempt_timeline import _group, _stage, _time, read_audit_attempt_timeline
from rasai.audit_duration_forecast_319 import _m21_http_request_sums

_AUD = re.compile(r"^AUD-[A-Za-z0-9-]{1,100}$")



def _verified_console_window(
    con: sqlite3.Connection, audit_id: str, *, status: str, completion: str,
) -> tuple[float, float, float] | None:
    """Observe one persisted physical session; never infer from AI attempt sums.

    Multiple sessions (e.g. continuation/RPR), naive timestamps, implausible
    clocks and logically partial AUDs abstain rather than fabricating wall-time.
    """
    if status.upper() != "COMPLETED" or completion.upper() != "COMPLETE":
        return None
    cols = {str(r[1]) for r in con.execute(
        "PRAGMA table_info(console_execution_projections)"
    )}
    if not {"audit_id", "duration_ms", "started_at", "finished_at"}.issubset(cols):
        return None
    rows = con.execute(
        "SELECT duration_ms, started_at, finished_at "
        "FROM console_execution_projections WHERE audit_id=? LIMIT 2",
        (audit_id,),
    ).fetchall()
    if len(rows) != 1:
        return None
    duration, start_raw, finish_raw = rows[0]
    try:
        if type(duration) not in (int, float):
            return None
        elapsed = float(duration)
        start = datetime.fromisoformat(str(start_raw).replace("Z", "+00:00"))
        finish = datetime.fromisoformat(str(finish_raw).replace("Z", "+00:00"))
        if start.tzinfo is None or finish.tzinfo is None:
            return None
        physical = (
            finish.astimezone(timezone.utc) -
            start.astimezone(timezone.utc)
        ).total_seconds() * 1000
    except (ValueError, TypeError, OverflowError):
        return None
    if (
        not math.isfinite(elapsed) or not math.isfinite(physical)
        or not 0 < elapsed <= 48 * 60 * 60 * 1000
        or not 0 < physical <= 48 * 60 * 60 * 1000
        or abs(elapsed - physical) > max(5000, physical * .05)
    ):
        return None
    return (
        elapsed,
        start.astimezone(timezone.utc).timestamp() * 1000,
        finish.astimezone(timezone.utc).timestamp() * 1000,
    )


def _ai_attempt_scope_breakdown(
    con: sqlite3.Connection,
    audit_id: str,
    window: tuple[float, float, float] | None,
) -> dict:
    """Read-only economic/time cohorts by proven initial physical session.

    Cohorts only describe observed clock placement, not whether a later
    invocation was directed analysis, RPR or authorized post-AUD work.
    No overlapping operations are added into wall-clock stage estimates.
    """
    groups: dict[str, list[dict]] = {
        "WITHIN_VERIFIED_CONSOLE_SESSION": [],
        "AFTER_VERIFIED_CONSOLE_SESSION": [],
        "BEFORE_VERIFIED_CONSOLE_SESSION": [],
        "UNCERTAIN_TIME_OR_SCOPE": [],
    }
    stage_groups: dict[tuple[str, str], list[dict]] = {}
    for table in ("ai_provider_attempts", "content_remediation_attempts"):
        cols = {str(x[1]) for x in con.execute("PRAGMA table_info(" + table + ")")}
        if not {"audit_id", "attempt_id"}.issubset(cols):
            continue
        seen: set[str] = set()
        cursor = con.execute(
            "SELECT * FROM " + table + " WHERE audit_id=?", (audit_id,)
        )
        fields = tuple(str(column[0]) for column in cursor.description)
        for row in cursor:
            data = dict(zip(fields, row))
            attempt = str(data.get("attempt_id") or "")
            if attempt in seen:
                continue
            seen.add(attempt)
            start = _time(data.get("started_at"))
            stop = _time(data.get("finished_at"))
            if (
                window is None or start is None or stop is None
                or stop < start
            ):
                category = "UNCERTAIN_TIME_OR_SCOPE"
            elif start >= window[2]:
                category = "AFTER_VERIFIED_CONSOLE_SESSION"
            elif stop <= window[1]:
                category = "BEFORE_VERIFIED_CONSOLE_SESSION"
            elif window[1] <= start <= stop <= window[2]:
                category = "WITHIN_VERIFIED_CONSOLE_SESSION"
            else:
                category = "UNCERTAIN_TIME_OR_SCOPE"
            groups[category].append(data)
            stage = _group(data, table=table)
            stage_groups.setdefault((category, stage), []).append(data)
    result = {}
    for label, rows in groups.items():
        metrics = _stage(label, rows)
        result[label] = {
            "attempts": metrics.attempts,
            "summed_ai_attempts_ms": metrics.summed_duration_ms,
            "union_active_ai_ms": metrics.union_active_ms,
            "provider_observed_usd": metrics.priced_usd_provider_observed,
            "posthoc_estimated_usd": metrics.priced_usd_estimate,
            "unpriced_attempts": metrics.unpriced_attempts,
            "unknown_intervals": metrics.unknown_intervals,
            "provider_observed_attempts": metrics.observed_cost_attempts,
        }
    stage_rows = []
    for (scope, name), rows in sorted(stage_groups.items()):
        metrics = _stage(name, rows)
        stage_rows.append({
            "stage": name,
            "session_scope": scope,
            "attempts": metrics.attempts,
            "summed_ai_attempts_ms": metrics.summed_duration_ms,
            "union_active_ai_ms": metrics.union_active_ms,
            "overlap_ai_ms": metrics.overlapping_duration_ms,
            "provider_observed_usd": metrics.priced_usd_provider_observed,
            "provider_observed_attempts": metrics.observed_cost_attempts,
            "posthoc_estimated_usd": metrics.priced_usd_estimate,
            "unpriced_attempts": metrics.unpriced_attempts,
            "unknown_intervals": metrics.unknown_intervals,
        })
    return {
        "status": (
            "VERIFIED_PHYSICAL_WINDOW_COHORTS"
            if window is not None else "AUD_WINDOW_UNVERIFIABLE"
        ),
        "cohorts": result,
        "by_stage": stage_rows,
        "stage_attempts_total": sum(row["attempts"] for row in stage_rows),
        "temporal_attribution": "CLOCK_PLACEMENT_ONLY_NOT_OPERATION_PROOF",
        "limitation": (
            "O recorte usa somente relógios de tentativas M18/M20 "
            "frente à sessão física completa comprovada. Chamadas posteriores "
            "podem ser continuação, RPR ou outro escopo: não se deduz operação "
            "a partir do instante. Valores estimados e observados não são "
            "fatura nem devem ser somados como wall-clock de fases."
        ),
    }


def inspect_audit_attempts(aud_dir: Path) -> dict:
    root = Path(aud_dir)
    if not _AUD.fullmatch(root.name) or root.is_symlink():
        raise ValueError("invalid AUD directory identity")
    db = root / "audit.db"
    if not db.is_file() or db.is_symlink():
        raise ValueError("AUD audit.db missing")
    with sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True, timeout=2) as con:
        con.execute("PRAGMA query_only=ON")
        fields = {str(x[1]) for x in con.execute("PRAGMA table_info(audits)")}
        if not {"audit_id", "status", "completion_status"}.issubset(fields):
            raise ValueError("AUD metadata schema unavailable")
        rows = con.execute(
            "SELECT status, completion_status FROM audits WHERE audit_id=?",
            (root.name,),
        ).fetchall()
        if len(rows) != 1:
            raise ValueError("AUD identity not verified against audit.db")
        if con.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise ValueError("AUD database integrity is not verified")
        if con.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise ValueError("AUD database foreign keys inconsistent")
        status, completion = rows[0]
        window = _verified_console_window(
            con, root.name,
            status=str(status or ""), completion=str(completion or ""),
        )
        wall_duration_ms = window[0] if window is not None else None
        scope_breakdown = _ai_attempt_scope_breakdown(con, root.name, window)
        # M21 records per HTTP attempt, not stage wall-clock. Preserve the
        # same conservative, AUD-scoped and fail-closed interpretation already
        # used by the historical duration forecast.
        http_request_sums = _m21_http_request_sums(con, root.name)
    timeline = read_audit_attempt_timeline(db, root.name)
    stages = [asdict(x) for x in timeline.stages]
    return {
        "contract_version": "RASAI-READONLY-ATTEMPT-INSPECTION-001",
        "audit_id": root.name,
        "source_audit_status": str(status or "N/D"),
        "source_completion_status": str(completion or "N/D"),
        "verified_aud_wall_duration_ms": wall_duration_ms,
        "aud_wall_clock_scope": (
            "SINGLE_VERIFIED_COMPLETE_CONSOLE_SESSION"
            if wall_duration_ms is not None else "NOT_VERIFIABLE"
        ),
        "aud_wall_clock_caveat": (
            "Duração física da única sessão completa persistida; não pode "
            "ser derivada de somas de IA/HTTP, nem atribuída a fases "
            "sem cronômetros próprios. Continuações e RPR são escopos distintos."
        ),
        "ai_attempt_execution_scope": scope_breakdown,
        "attempts_total": timeline.attempts,
        "stage_attempts_total": sum(x["attempts"] for x in stages),
        "m18_m20_ledger_union": "NO_DOUBLE_COUNT_WITHIN_EACH_LEDGER",
        "summed_ai_attempts_ms": timeline.summed_duration_ms,
        "union_active_ai_ms": timeline.union_active_ms,
        "overlap_ai_ms": timeline.overlapping_duration_ms,
        "unknown_ai_intervals": timeline.unknown_intervals,
        "posthoc_estimated_usd": timeline.posthoc_estimated_usd,
        "provider_observed_usd": timeline.provider_observed_usd,
        "unpriced_attempts": timeline.unpriced_attempts,
        "non_ai_stages_measured": False,
        "observed_http_request_sums_ms": http_request_sums,
        "http_request_telemetry": (
            "OBSERVED_CUMULATIVE_REQUEST_DURATION"
            if http_request_sums else "NOT_VERIFIABLE"
        ),
        "http_request_stage_wall_clock_available": False,
        "http_request_caveat": (
            "Valores M21 são somas verificadas de duração de requisições "
            "HTTP PSI/CrUX por serviço, não tempo físico de fase, "
            "nem parcelas somáveis ao tempo ativo IA ou à duração da AUD. "
            "Serviços com tentativa de tempo inválido permanecem N/D."
        ),
        "caveat": timeline.timing_caveat +
            " Custo observado pelo provedor não equivale à fatura. "
            "Processamentos fora da sessão física da AUD também podem figurar no histórico.",
        "stages": stages,
        "provider_requests": 0,
        "audit_writes": 0,
    }



def inspect_ai_stage_scope(audit_dir: Path) -> dict:
    """Read audit-scoped attempt cohorts, no package writes or billability claim.

    This is the same verification entrypoint used by the #319 CLI inspector,
    but returning only stage and temporal-scope evidence for the HTML report.
    """
    return inspect_audit_attempts(audit_dir)["ai_attempt_execution_scope"]

def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Read AUD M18/M20 attempts and distinct M21 HTTP request telemetry without network."
    )
    parser.add_argument("audit_dir", type=Path)
    args = parser.parse_args(argv)
    print(json.dumps(
        inspect_audit_attempts(args.audit_dir),
        indent=2, ensure_ascii=False, sort_keys=True, allow_nan=False,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
