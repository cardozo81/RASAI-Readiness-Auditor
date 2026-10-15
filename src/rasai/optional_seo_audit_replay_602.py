"""Bounded, immutable audit.db replay of optional-SEO policy sensitivities.

The canonical SCORE-GEO-004 result is recomputed from RuleExecutions and
checked against the AUD's persisted scores before showing any alternatives.
This is *not* permission to republish or migrate SARI/score history.
"""
from __future__ import annotations

import argparse
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from typing import Any, Sequence

from rasai.domain import DeviceContext, RuleExecution, RuleResult
from rasai.optional_seo_score_scenarios_602 import preview_optional_seo_policy_sensitivity

_MAX_DB_BYTES = 256 * 1024 * 1024
_MAX_ROWS = 4000
_SUPPORTED_VERSION = "SCORE-GEO-004"


def _read_hash(db: Path) -> str:
    if db.is_symlink() or not db.is_file() or db.stat().st_size > _MAX_DB_BYTES:
        raise ValueError("AUD SQLite source unavailable or exceeds budget")
    if any(Path(str(db) + suffix).exists() for suffix in ("-wal", "-shm", "-journal")):
        raise ValueError("unverified SQLite journal/sidecar")
    size = db.stat().st_size
    digest = sha256()
    count = 0
    with db.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
            count += len(chunk)
            if count > _MAX_DB_BYTES:
                raise ValueError("AUD SQLite source exceeds budget while reading")
    if db.stat().st_size != size or count != size:
        raise ValueError("AUD SQLite source changed")
    return digest.hexdigest()


def _row_to_execution(row: sqlite3.Row) -> RuleExecution:
    raw_device = row["device"]
    try:
        device = DeviceContext(raw_device) if raw_device is not None else None
        observed = json.loads(row["observed_value"])
        evidence = json.loads(row["evidence_ids"])
        result = RuleResult(row["result"])
        timestamp = datetime.fromisoformat(row["executed_at"].replace("Z", "+00:00"))
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise ValueError("unverified rule execution time")
        if not isinstance(evidence, list) or any(not isinstance(v, str) for v in evidence):
            raise ValueError("invalid evidence identifiers")
    except (ValueError, TypeError, KeyError, AttributeError) as exc:
        raise ValueError("unverifiable persisted RuleExecution") from exc
    return RuleExecution(
        rule_execution_id=row["rule_execution_id"],
        audit_id=row["audit_id"],
        rule_id=row["rule_id"],
        rule_version=row["rule_version"],
        page_id=row["page_id"],
        snapshot_id=row["snapshot_id"],
        device=device,
        result=result,
        observed_value=observed,
        expected_condition=row["expected_condition"],
        evidence_ids=tuple(evidence),
        executed_at=timestamp,
        error=row["error"],
    )


def replay_optional_seo_from_audit(
    audit_dir: Path, *, device: DeviceContext = DeviceContext.MOBILE,
) -> dict[str, Any]:
    root = Path(audit_dir)
    if not root.is_dir() or root.is_symlink() or not root.name.startswith("AUD-"):
        raise ValueError("physical AUD directory required")
    if not isinstance(device, DeviceContext):
        raise ValueError("valid device required")
    db = root / "audit.db"
    original = _read_hash(db)
    with sqlite3.connect(
        db.resolve().as_uri() + "?mode=ro&immutable=1", uri=True, timeout=2,
    ) as con:
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA query_only=ON")
        if con.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise ValueError("AUD SQLite quick_check failed")
        if con.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise ValueError("AUD SQLite references invalid")
        ids = con.execute(
            "SELECT audit_id FROM audits WHERE audit_id=?", (root.name,),
        ).fetchall()
        if len(ids) != 1:
            raise ValueError("AUD identity ambiguous")
        rows = con.execute(
            "SELECT * FROM rule_executions WHERE audit_id=? LIMIT ?",
            (root.name, _MAX_ROWS + 1),
        ).fetchall()
        if len(rows) > _MAX_ROWS:
            raise ValueError("RuleExecution source volume exceeds budget")
        executions = tuple(_row_to_execution(row) for row in rows)
        persisted = con.execute(
            "SELECT dimension, value, coverage, confidence, consolidation_status, "
            "scoring_version FROM scores WHERE audit_id=? AND device=?",
            (root.name, device.value),
        ).fetchall()
    if not persisted:
        raise ValueError("no persisted scores to verify baseline")
    baseline = {
        row["dimension"]: row for row in persisted
    }
    if len(baseline) != len(persisted):
        raise ValueError("duplicated persisted score dimension")
    if any(row["scoring_version"] != _SUPPORTED_VERSION for row in persisted):
        raise ValueError("unknown/mixed persisted scoring contract")
    preview = preview_optional_seo_policy_sensitivity(
        root.name, executions, device=device,
    )
    observed = preview["scenarios"]["CANONICAL_SCORE_GEO_004"]
    if set(observed) != set(baseline):
        raise ValueError("replayed score dimensions do not match persisted contract")
    for name, expected in baseline.items():
        actual = observed[name]
        for field in ("value", "coverage"):
            left, right = actual[field], expected[field]
            if (left is None) != (right is None):
                raise ValueError("baseline score nullness mismatch")
            if left is not None and abs(float(left) - float(right)) > 0.00002:
                raise ValueError("replayed baseline numeric parity failed")
        for field in ("confidence", "consolidation_status"):
            if actual[field] != expected[field]:
                raise ValueError("replayed baseline quality contract mismatch")
    if original != _read_hash(db):
        raise ValueError("physical AUD changed during replay")
    return {
        **preview,
        "source_audit_db_sha256": original,
        "source_audit_db_replay_parity": "VERIFIED_SCORE_GEO_004",
        "published_score_mutated": False,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Replay optional SEO policy scenarios offline")
    parser.add_argument("audit_dir", type=Path)
    parser.add_argument("--device", choices=("MOBILE", "DESKTOP"), default="MOBILE")
    args = parser.parse_args(argv)
    result = replay_optional_seo_from_audit(
        args.audit_dir, device=DeviceContext(args.device),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
