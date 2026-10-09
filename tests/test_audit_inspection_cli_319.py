"""#319: isolated Windows-compatible, read-only audit attempt inventory."""
from __future__ import annotations

import json
import sqlite3

import pytest

from rasai.audit_attempt_inspection_319 import inspect_audit_attempts, main


def _fixture(tmp_path):
    root = tmp_path / "AUD-NEW-COMPLETE"
    root.mkdir()
    db = root / "audit.db"
    with sqlite3.connect(db) as con:
        con.executescript("""
            CREATE TABLE audits (
                audit_id TEXT PRIMARY KEY, status TEXT, completion_status TEXT
            );
            CREATE TABLE ai_provider_attempts (
                attempt_id TEXT PRIMARY KEY, audit_id TEXT,
                operation TEXT, started_at TEXT, finished_at TEXT,
                duration_ms REAL, estimated_cost REAL, cost_currency TEXT
            );
            CREATE TABLE content_remediation_attempts (
                attempt_id TEXT PRIMARY KEY, audit_id TEXT,
                operation TEXT, started_at TEXT, finished_at TEXT,
                duration_ms REAL, observed_cost REAL, observed_cost_currency TEXT
            );
        """)
        con.execute(
            "INSERT INTO audits VALUES (?,?,?)",
            (root.name, "COMPLETED", "COMPLETE"),
        )
        for i in range(7):
            # Seven sequential 10-second canonical M18 attempts.
            con.execute(
                "INSERT INTO ai_provider_attempts VALUES (?,?,?,?,?,?,?,?)",
                (f"AI-{i}", root.name, "IMPROVEMENT_INTELLIGENCE",
                 f"2026-10-09T10:{i:02d}:00+00:00",
                 f"2026-10-09T10:{i:02d}:10+00:00",
                 10000, .01, "USD"),
            )
        con.execute(
            "INSERT INTO content_remediation_attempts VALUES (?,?,?,?,?,?,?,?)",
            ("M20-1", root.name, "CONTENT_REMEDIATION",
             "2026-10-09T10:07:00+00:00",
             "2026-10-09T10:07:20+00:00",
             20000, .04, "USD"),
        )
        con.execute(
            "INSERT INTO ai_provider_attempts VALUES (?,?,?,?,?,?,?,?)",
            ("FOREIGN", "AUD-FOREIGN", "IMPROVEMENT_INTELLIGENCE",
             "2026-10-09T10:09:00+00:00",
             "2026-10-09T10:19:00+00:00", 600000, 9000, "USD"),
        )
    return root


def test_eight_attempts_across_both_ledgers_are_counted_once(tmp_path):
    root = _fixture(tmp_path)
    before = (root / "audit.db").read_bytes()
    out = inspect_audit_attempts(root)
    assert out["attempts_total"] == out["stage_attempts_total"] == 8
    assert out["summed_ai_attempts_ms"] == 90000
    assert out["union_active_ai_ms"] == 90000
    assert out["unknown_ai_intervals"] == 0
    assert out["provider_requests"] == out["audit_writes"] == 0
    assert out["non_ai_stages_measured"] is False
    assert out["provider_observed_usd"] == .04
    assert abs(out["posthoc_estimated_usd"] - .07) < 0.000001
    assert {x["name"]: x["attempts"] for x in out["stages"]} == {
        "CONTENT_REMEDIATION": 1, "IMPROVEMENT_INTELLIGENCE": 7,
    }
    assert "não equivale à fatura" in out["caveat"]
    assert (root / "audit.db").read_bytes() == before


def test_audit_attempts_cli_never_installs_provider_runtime(tmp_path, capsys, monkeypatch):
    from rasai import entrypoint
    root = _fixture(tmp_path)
    monkeypatch.setattr(
        entrypoint, "_install_audit_runtime",
        lambda: pytest.fail("read-only CLI cannot bootstrap audit"),
    )
    assert entrypoint.main(["audit-attempts", str(root)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["attempts_total"] == 8
    assert result["provider_requests"] == 0
    assert main([str(root)]) == 0


def test_unverified_or_missing_aud_fails_without_files(tmp_path):
    root = _fixture(tmp_path)
    with pytest.raises(ValueError, match="identity"):
        inspect_audit_attempts(tmp_path / "AUD-NO-DB")
    with sqlite3.connect(root / "audit.db") as con:
        con.execute("UPDATE audits SET audit_id='AUD-FOREIGN'")
    before = (root / "audit.db").read_bytes()
    with pytest.raises(ValueError, match="identity"):
        inspect_audit_attempts(root)
    assert (root / "audit.db").read_bytes() == before
    assert not (tmp_path / "AUD-NO-DB").exists()


def test_partial_aud_still_explicitly_identified_as_not_complete(tmp_path):
    root = _fixture(tmp_path)
    with sqlite3.connect(root / "audit.db") as con:
        con.execute("UPDATE audits SET completion_status='PARTIAL_RETRYABLE'")
    result = inspect_audit_attempts(root)
    assert result["source_completion_status"] == "PARTIAL_RETRYABLE"
    assert result["attempts_total"] == 8
