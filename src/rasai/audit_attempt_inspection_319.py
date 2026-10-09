"""#319: read-only single-AUD attempt chronology inspection.

It reports the canonical M18 + M20 ledgers without adding physical
request elapsed times, AI costs, or speculative non-AI stage estimates.
No replay, provider requests, DDL, or original report materialization.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import re
import sqlite3
from typing import Sequence

from rasai.audit_attempt_timeline import read_audit_attempt_timeline
from rasai.audit_duration_forecast_319 import _m21_http_request_sums

_AUD = re.compile(r"^AUD-[A-Za-z0-9-]{1,100}$")


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
