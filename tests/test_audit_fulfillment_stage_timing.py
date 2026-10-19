"""#319: isolated attempt wall-clock evidence; no exclusive-phase inference."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import sqlite3

from rasai.audit_fulfillment_stage_timing import fulfillment_attempt_intervals
from rasai.audit_stage_cost_presentation import (
    inspect_stage_economics, stage_report_html, stage_console_lines,
)


def _source(tmp_path):
    db = tmp_path / "audit.db"
    with sqlite3.connect(db) as con:
        con.executescript(
            "CREATE TABLE audit_fulfillment_work_items("
            "work_item_id TEXT,audit_id TEXT,component TEXT);"
            "CREATE TABLE audit_fulfillment_attempts("
            "attempt_id TEXT,audit_id TEXT,work_item_id TEXT,"
            "started_at TEXT,finished_at TEXT,status TEXT,reprocess_id TEXT);"
        )
        con.executemany(
            "INSERT INTO audit_fulfillment_work_items VALUES (?,?,?)", [
                ("W-1", "AUD-319", "CAPTURE_AND_RENDER"),
                ("W-2", "AUD-319", "CAT-04"),
                ("W-OTHER", "AUD-OTHER", "UNRELATED"),
            ],
        )
        time = datetime(2026, 10, 8, 15, tzinfo=timezone.utc)
        def at(ms):
            return (time + timedelta(milliseconds=ms)).isoformat()
        con.executemany(
            "INSERT INTO audit_fulfillment_attempts VALUES (?,?,?,?,?,?,?)",
            [
                ("T-1", "AUD-319", "W-1", at(0), at(1000), "SUCCESS", None),
                ("T-2", "AUD-319", "W-1", at(500), at(1500), "SUCCESS", "RPR-1"),
                ("T-3", "AUD-319", "W-2", at(1750), None, "RUNNING", None),
                ("T-OTHER", "AUD-OTHER", "W-OTHER", at(0), at(999999), "SUCCESS", None),
            ],
        )
    return db


def test_319_fulfillment_physical_attempts_are_nonexclusive_not_subtracted_from_ai(tmp_path):
    db = _source(tmp_path)
    original = db.read_bytes()
    with sqlite3.connect(db.resolve().as_uri() + "?mode=ro&immutable=1", uri=True) as conn:
        work = fulfillment_attempt_intervals(conn, "AUD-319")
    assert work["status"] == "OBSERVED_NONEXCLUSIVE_WORK_INTERVALS"
    assert work["attempts"] == 3
    assert work["exclusive_non_ai_timing_proven"] is False
    components = {row["component"]: row for row in work["components"]}
    assert components["CAPTURE_AND_RENDER"]["summed_ms"] == 2000
    assert components["CAPTURE_AND_RENDER"]["union_active_ms"] == 1500
    assert components["CAPTURE_AND_RENDER"]["reprocess_attempts"] == 1
    assert components["CAT-04"]["complete_time_intervals"] == 0
    assert components["CAT-04"]["summed_ms"] is None
    assert components["CAT-04"]["unknown_time_intervals"] == 1
    assert "UNRELATED" not in components
    assert db.read_bytes() == original
    projection = inspect_stage_economics(db, "AUD-319")
    assert projection["fulfillment"] == work
    assert projection["status"] == "NO_AI_ATTEMPTS"
    output = "\n".join(stage_console_lines(projection))
    html = stage_report_html(projection)
    assert "Atividade CAPTURE_AND_RENDER" in output
    assert "não tempo de fase" in output
    assert "Atividade registrada: CAPTURE_AND_RENDER" in html
    assert "1.50 s" in html and "2.00 s" in html
    assert db.read_bytes() == original


def test_319_cross_aud_attempt_work_identity_abstains(tmp_path):
    db = _source(tmp_path)
    with sqlite3.connect(db) as conn:
        conn.execute(
            "UPDATE audit_fulfillment_attempts SET work_item_id='W-OTHER' "
            "WHERE attempt_id='T-1'",
        )
    original = db.read_bytes()
    with sqlite3.connect(db.resolve().as_uri() + "?mode=ro&immutable=1", uri=True) as con:
        result = fulfillment_attempt_intervals(con, "AUD-319")
    assert result["status"] == "INCONSISTENT_AUD_IDENTITIES"
    assert result["components"] == []
    assert db.read_bytes() == original


def test_319_unknown_time_kept_nd_not_forced_to_zero(tmp_path):
    db = _source(tmp_path)
    with sqlite3.connect(db) as con:
        con.execute(
            "UPDATE audit_fulfillment_attempts SET finished_at=started_at "
            "WHERE attempt_id='T-2'"
        )
    with sqlite3.connect(db.resolve().as_uri() + "?mode=ro&immutable=1", uri=True) as con:
        result = fulfillment_attempt_intervals(con, "AUD-319")
    components = {row["component"]: row for row in result["components"]}
    assert components["CAPTURE_AND_RENDER"]["summed_ms"] == 1000
    assert components["CAPTURE_AND_RENDER"]["union_active_ms"] == 1000
    assert components["CAT-04"]["summed_ms"] is None
