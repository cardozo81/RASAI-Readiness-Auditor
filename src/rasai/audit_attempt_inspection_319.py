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
        "caveat": timeline.timing_caveat +
            " Custo observado pelo provedor não equivale à fatura. "
            "Processamentos fora da sessão física da AUD também podem figurar no histórico.",
        "stages": stages,
        "provider_requests": 0,
        "audit_writes": 0,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Read persisted AUD M18/M20 attempt chronology without external calls."
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
