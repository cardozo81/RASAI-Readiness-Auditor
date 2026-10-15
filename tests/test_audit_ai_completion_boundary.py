"""#319: offline AUD completion boundary versus AI HTTP economics."""
from __future__ import annotations

from hashlib import sha256
import json
import sqlite3

import pytest

from rasai.audit_ai_completion_boundary_319 import (
    inspect_ai_audit_boundary, main,
)


def _db(tmp_path):
    db = tmp_path / "audit.db"
    with sqlite3.connect(db) as con:
        con.executescript("""
            CREATE TABLE audits(audit_id TEXT, status TEXT,
                completion_status TEXT, started_at TEXT, completed_at TEXT);
            CREATE TABLE ai_provider_attempts(
                attempt_id TEXT,audit_id TEXT,operation TEXT,
                surface TEXT, started_at TEXT,finished_at TEXT,
                duration_ms REAL,estimated_cost REAL,cost_currency TEXT,
                observed_cost REAL,observed_cost_currency TEXT);
            CREATE TABLE content_remediation_attempts(
                attempt_id TEXT,audit_id TEXT,operation TEXT,
                started_at TEXT,finished_at TEXT,
                duration_ms REAL,estimated_cost REAL,cost_currency TEXT,
                observed_cost REAL,observed_cost_currency TEXT);
            INSERT INTO audits VALUES (
                'AUD-T', 'COMPLETED', 'COMPLETE',
                '2026-10-08T11:00:00-03:00', '2026-10-08T11:26:07-03:00'
            );
        """)
        con.executemany(
            "INSERT INTO ai_provider_attempts VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            [
                ("A1","AUD-T","IMPROVEMENT_INTELLIGENCE",None,
                 "2026-10-08T11:10:00-03:00","2026-10-08T11:12:00-03:00",
                 120000,.020,"USD",None,None),
                ("A2","AUD-T","COMPETITIVE",None,
                 "2026-10-08T14:11:00+00:00","2026-10-08T14:13:00+00:00",
                 120000,.030,"USD",None,None),
                ("A3","AUD-T","DIRECTED_ANALYSIS",None,
                 "2026-10-08T11:27:00-03:00","2026-10-08T11:29:00-03:00",
                 120000,.04,"USD",.035,"USD"),
                ("A4","AUD-T","OTHER_AI",None,"?",
                 "2026-10-08T14:25:00Z",3000,.01,"USD",None,None),
                ("FOREIGN","AUD-OTHER","IMPROVEMENT_INTELLIGENCE",None,
                 "2026-10-08T11:00:00-03:00","2026-10-08T11:02:00-03:00",
                 120000,100.0,"USD",None,None),
            ],
        )
        con.execute(
            "INSERT INTO content_remediation_attempts VALUES (?,?,?,?,?,?,?,?,?,?)",
            ("M20","AUD-T","CONTENT_REMEDIATION",
             "2026-10-08T11:25:30-03:00","2026-10-08T11:26:45-03:00",
             75000,.10,"USD",.08,"USD"),
        )
    return db


def test_core_vs_post_aud_is_evidence_based_and_prevents_parallel_double_count(tmp_path):
    db = _db(tmp_path)
    before = sha256(db.read_bytes()).hexdigest()
    result = inspect_ai_audit_boundary(db, "AUD-T")
    assert result["status"] == "DESCRIPTIVE_ONLY"
    assert result["contract_version"] == "RASAI-AUD-AI-TIME-ECONOMICS-319-002"
    assert result["aud_started_at_utc"] == "2026-10-08T14:00:00+00:00"
    assert result["total_attempts"] == 5
    assert result["aud_completed_at_utc"] == "2026-10-08T14:26:07+00:00"
    during, post, crossing, unknown, pre_aud_bucket, start_cross = result["buckets"]
    assert [x["classification"] for x in result["buckets"]] == [
        "DURING_AUD","AFTER_AUD","CROSSES_AUD_COMPLETION","UNKNOWN_CLOCK",
        "BEFORE_AUD","CROSSES_AUD_START",
    ]
    assert [x["attempts"] for x in result["buckets"]] == [2,1,1,1,0,0]
    assert pre_aud_bucket["attempts"] == start_cross["attempts"] == 0
    assert during["sum_call_durations_ms"] == 240000
    assert during["union_active_calls_ms"] == 180000
    assert during["overlap_ms"] == 60000
    assert during["posthoc_estimated_cost_usd"] == .05
    assert post["provider_observed_cost_usd"] == .035
    assert post["provider_observed_cost_attempts"] == 1
    assert post["provider_observed_cost_available"] is True
    assert post["provider_observed_cost_complete"] is True
    assert post["stages"]["DIRECTED_ANALYSIS"]["provider_observed_cost_attempts"] == 1
    assert post["stages"]["DIRECTED_ANALYSIS"]["provider_observed_cost_complete"] is True
    assert during["provider_observed_cost_usd"] == 0
    assert during["provider_observed_cost_attempts"] == 0
    assert during["provider_observed_cost_available"] is False
    assert during["provider_observed_cost_complete"] is False
    assert during["stages"]["COMPETITIVE_AI"]["provider_observed_cost_available"] is False
    assert post["posthoc_estimated_cost_usd"] == 0
    assert "DIRECTED_ANALYSIS" in post["stages"]
    assert crossing["provider_observed_cost_usd"] == .08
    assert "CONTENT_REMEDIATION" in crossing["stages"]
    assert unknown["unknown_timing_attempts"] == 1
    assert unknown["union_active_calls_ms"] is None
    assert unknown["posthoc_estimated_cost_usd"] == .01
    assert result["post_aud_cost_included_in_aud_core_price"] is None
    assert result["stage_latency_is_aud_total"] is False
    assert result["provider_invoice_verified"] is False
    assert result["non_ai_stages_measured"] is False
    assert result["provider_requests"] == result["audit_writes"] == 0
    assert sha256(db.read_bytes()).hexdigest() == before


def test_provider_reported_zero_is_distinct_from_missing_and_partial_coverage(tmp_path):
    db = _db(tmp_path)
    with sqlite3.connect(db) as con:
        con.execute(
            "UPDATE ai_provider_attempts SET observed_cost=0, "
            "observed_cost_currency='USD' WHERE attempt_id='A1'"
        )
    original = sha256(db.read_bytes()).hexdigest()
    report = inspect_ai_audit_boundary(db, "AUD-T")
    during = report["buckets"][0]
    assert during["attempts"] == 2
    assert during["provider_observed_cost_usd"] == 0
    assert during["provider_observed_cost_attempts"] == 1
    assert during["provider_observed_cost_available"] is True
    assert during["provider_observed_cost_complete"] is False
    stages = during["stages"]
    assert stages["IMPROVEMENT_INTELLIGENCE"]["provider_observed_cost_usd"] == 0
    assert stages["IMPROVEMENT_INTELLIGENCE"]["provider_observed_cost_attempts"] == 1
    assert stages["IMPROVEMENT_INTELLIGENCE"]["provider_observed_cost_available"] is True
    assert stages["IMPROVEMENT_INTELLIGENCE"]["provider_observed_cost_complete"] is True
    assert stages["COMPETITIVE_AI"]["provider_observed_cost_available"] is False
    assert sha256(db.read_bytes()).hexdigest() == original


def test_missing_or_foreign_aud_not_made_comparable(tmp_path):
    db = _db(tmp_path)
    assert inspect_ai_audit_boundary(db,"AUD-WRONG")["reason"] == (
        "AUD_NOT_COMPLETE_OR_FOREIGN"
    )
    with sqlite3.connect(db) as con:
        con.execute("UPDATE audits SET completion_status='PARTIAL_RETRYABLE'")
    assert inspect_ai_audit_boundary(db,"AUD-T")["status"] == "NOT_COMPARABLE"
    with sqlite3.connect(db) as con:
        con.execute("UPDATE audits SET completion_status='COMPLETE',"
                    "completed_at='2026-10-08'")
    assert inspect_ai_audit_boundary(db,"AUD-T")["reason"] == (
        "AUD_COMPLETION_CLOCK_UNVERIFIABLE"
    )


def test_pre_aud_directed_action_remains_pre_not_forced_after(tmp_path):
    db = _db(tmp_path)
    with sqlite3.connect(db) as con:
        con.execute(
            "UPDATE ai_provider_attempts SET started_at=?, finished_at=? "
            "WHERE attempt_id='A3'",
            ("2026-10-08T11:14:00-03:00","2026-10-08T11:16:00-03:00"),
        )
    result = inspect_ai_audit_boundary(db, "AUD-T")
    assert "DIRECTED_ANALYSIS" in result["buckets"][0]["stages"]
    assert result["buckets"][1]["attempts"] == 0


def test_duplicate_attempt_id_fails_closed_without_double_counting(tmp_path):
    db = _db(tmp_path)
    with sqlite3.connect(db) as con:
        con.execute(
            "INSERT INTO ai_provider_attempts SELECT * FROM ai_provider_attempts "
            "WHERE attempt_id='A1'"
        )
    result = inspect_ai_audit_boundary(db,"AUD-T")
    assert result["reason"] == "AI_ATTEMPT_ID_UNVERIFIABLE"
    assert result["buckets"] == []


def test_optional_price_columns_are_unpriced_not_zero_cost(tmp_path):
    db = _db(tmp_path)
    with sqlite3.connect(db) as con:
        con.execute("ALTER TABLE content_remediation_attempts DROP COLUMN observed_cost")
        con.execute("ALTER TABLE content_remediation_attempts DROP COLUMN observed_cost_currency")
        con.execute("ALTER TABLE content_remediation_attempts DROP COLUMN estimated_cost")
        con.execute("ALTER TABLE content_remediation_attempts DROP COLUMN cost_currency")
    result = inspect_ai_audit_boundary(db,"AUD-T")
    assert result["status"] == "DESCRIPTIVE_ONLY"
    assert result["buckets"][2]["unknown_price_attempts"] == 1
    assert result["buckets"][2]["provider_observed_cost_usd"] == 0
    assert result["buckets"][2]["provider_observed_cost_attempts"] == 0
    assert result["buckets"][2]["provider_observed_cost_available"] is False
    assert result["buckets"][2]["provider_observed_cost_complete"] is False


def test_reject_linked_missing_or_sidecar_sqlite(tmp_path):
    db = tmp_path / "nonexistent.db"
    with pytest.raises(ValueError, match="existing SQLite"):
        inspect_ai_audit_boundary(db,"AUD-X")
    db = _db(tmp_path)
    (tmp_path/"audit.db-wal").write_bytes(b"in-progress")
    with pytest.raises(ValueError, match="sidecars"):
        inspect_ai_audit_boundary(db,"AUD-T")


def test_offline_cli_emits_json_without_mutating_db(tmp_path, capsys):
    db = _db(tmp_path)
    before = db.read_bytes()
    assert main(["--audit-db",str(db),"--audit-id","AUD-T"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "DESCRIPTIVE_ONLY"
    assert result["total_attempts"] == 5
    assert db.read_bytes() == before


def test_ai_calls_before_aud_or_crossing_start_do_not_inflate_in_aud(
    tmp_path,
):
    db = _db(tmp_path)
    with sqlite3.connect(db) as con:
        con.executemany(
            "INSERT INTO ai_provider_attempts VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            [
                ("BEFORE", "AUD-T", "DIRECTED_ANALYSIS", None,
                 "2026-10-08T10:40:00-03:00",
                 "2026-10-08T10:45:00-03:00",
                 300000, .30, "USD", None, None),
                ("START-CROSS", "AUD-T", "COMPETITIVE", None,
                 "2026-10-08T10:59:30-03:00",
                 "2026-10-08T11:00:30-03:00",
                 60000, .06, "USD", None, None),
                ("AT-START", "AUD-T", "OTHER_AI", None,
                 "2026-10-08T11:00:00-03:00",
                 "2026-10-08T11:00:10-03:00",
                 10000, .01, "USD", None, None),
            ],
        )
    before_digest = sha256(db.read_bytes()).hexdigest()
    outcome = inspect_ai_audit_boundary(db, "AUD-T")
    assert outcome["status"] == "DESCRIPTIVE_ONLY"
    assert outcome["total_attempts"] == 8
    during, post, completion, unknown, earlier, start_overlap = outcome["buckets"]
    assert during["attempts"] == 3
    assert during["posthoc_estimated_cost_usd"] == .06
    assert earlier["attempts"] == 1
    assert earlier["posthoc_estimated_cost_usd"] == .30
    assert "DIRECTED_ANALYSIS" in earlier["stages"]
    assert start_overlap["attempts"] == 1
    assert start_overlap["posthoc_estimated_cost_usd"] == .06
    assert outcome["post_aud_cost_included_in_aud_core_price"] is None
    assert sha256(db.read_bytes()).hexdigest() == before_digest


@pytest.mark.parametrize("start_clock,expected", [
    ("2026-10-08", "AUD_START_CLOCK_UNVERIFIABLE"),
    ("2026-10-09T12:00:00-03:00", "AUD_START_CLOCK_UNVERIFIABLE"),
    ("", "AUD_START_CLOCK_UNVERIFIABLE"),
])
def test_missing_or_inverted_physical_aud_start_abstains(
    tmp_path, start_clock, expected,
):
    db = _db(tmp_path)
    with sqlite3.connect(db) as con:
        con.execute("UPDATE audits SET started_at=?", (start_clock,))
    original = db.read_bytes()
    result = inspect_ai_audit_boundary(db, "AUD-T")
    assert result["status"] == "NOT_COMPARABLE"
    assert result["reason"] == expected
    assert result["buckets"] == []
    assert db.read_bytes() == original


def test_historical_aud_without_started_column_cannot_claim_in_aud(
    tmp_path,
):
    db = _db(tmp_path)
    with sqlite3.connect(db) as con:
        con.execute("ALTER TABLE audits DROP COLUMN started_at")
    result = inspect_ai_audit_boundary(db, "AUD-T")
    assert result["status"] == "NOT_COMPARABLE"
    assert result["reason"] == "AUD_COMPLETION_SCHEMA_MISSING"
    assert result["buckets"] == []
