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
    envelope = work["attempt_envelope"]
    assert envelope["status"] == "INCOMPLETE_ATTEMPT_COHORT"
    assert envelope["attempts_with_timing"] == 2
    assert envelope["total_attempts"] == 3
    assert envelope["union_active_ms"] is None
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
    assert components["CAPTURE_AND_RENDER"]["summed_ms"] is None
    assert components["CAPTURE_AND_RENDER"]["union_active_ms"] is None
    assert components["CAPTURE_AND_RENDER"]["complete_time_intervals"] == 1
    assert components["CAPTURE_AND_RENDER"]["unknown_time_intervals"] == 1
    assert components["CAT-04"]["summed_ms"] is None


def test_319_orphan_work_item_is_not_dropped_from_physical_attempt_census(tmp_path):
    db = _source(tmp_path)
    with sqlite3.connect(db) as con:
        con.execute(
            "INSERT INTO audit_fulfillment_attempts VALUES "
            "('ORPHAN','AUD-319','MISSING','2026-10-08T15:00:00Z',"
            "'2026-10-08T15:00:01Z','SUCCESS',NULL)"
        )
    original = db.read_bytes()
    with sqlite3.connect(db.resolve().as_uri() + "?mode=ro&immutable=1", uri=True) as con:
        outcome = fulfillment_attempt_intervals(con, "AUD-319")
    assert outcome["status"] == "INCONSISTENT_AUD_IDENTITIES"
    assert outcome["attempts"] is None and outcome["components"] == []
    report = inspect_stage_economics(db, "AUD-319")
    assert report["fulfillment"]["status"] == "INCONSISTENT_AUD_IDENTITIES"
    assert "Atividades fulfillment: N/D" in "\n".join(stage_console_lines(report))
    assert "Atividades fulfillment: N/D" in stage_report_html(report)
    assert db.read_bytes() == original


def test_319_nonterminal_with_finished_clock_must_stay_nd(tmp_path):
    db = _source(tmp_path)
    with sqlite3.connect(db) as con:
        con.execute(
            "UPDATE audit_fulfillment_attempts "
            "SET finished_at='2026-10-08T15:00:04Z' WHERE attempt_id='T-3'"
        )
    with sqlite3.connect(db.resolve().as_uri() + "?mode=ro&immutable=1", uri=True) as con:
        outcome = fulfillment_attempt_intervals(con, "AUD-319")
    cat = {entry["component"]: entry for entry in outcome["components"]}["CAT-04"]
    assert cat["non_terminal_attempts"] == 1
    assert cat["complete_time_intervals"] == 0
    assert cat["unknown_time_intervals"] == 1
    assert cat["summed_ms"] is None and cat["union_active_ms"] is None


def test_319_terminal_failed_attempt_is_timed_without_claiming_success(tmp_path):
    db = _source(tmp_path)
    with sqlite3.connect(db) as con:
        con.execute(
            "UPDATE audit_fulfillment_attempts "
            "SET status='FAILED_RETRYABLE', "
            "finished_at='2026-10-08T15:00:04Z' WHERE attempt_id='T-3'"
        )
    with sqlite3.connect(db.resolve().as_uri() + "?mode=ro&immutable=1", uri=True) as con:
        outcome = fulfillment_attempt_intervals(con, "AUD-319")
    cat = {entry["component"]: entry for entry in outcome["components"]}["CAT-04"]
    assert cat["non_success_attempts"] == 1
    assert cat["non_terminal_attempts"] == 0
    assert cat["complete_time_intervals"] == 1
    assert cat["summed_ms"] == cat["union_active_ms"] == 2250


def test_319_duplicate_join_or_noncanonical_identifier_abstains(tmp_path):
    for variant in ("duplicate_work_item", "control_char", "padded_attempt"):
        folder = tmp_path / variant
        folder.mkdir()
        db = _source(folder)
        with sqlite3.connect(db) as con:
            if variant == "duplicate_work_item":
                con.execute(
                    "INSERT INTO audit_fulfillment_work_items VALUES "
                    "('W-1','AUD-319','CAPTURE_AND_RENDER')"
                )
            elif variant == "control_char":
                con.execute(
                    "UPDATE audit_fulfillment_work_items SET component=? "
                    "WHERE work_item_id='W-1'",
                    ("CAPTURE\x1b[2J",),
                )
            else:
                con.execute(
                    "UPDATE audit_fulfillment_attempts SET attempt_id=' T-1' "
                    "WHERE attempt_id='T-1'"
                )
        before = db.read_bytes()
        with sqlite3.connect(db.resolve().as_uri() + "?mode=ro&immutable=1", uri=True) as con:
            outcome = fulfillment_attempt_intervals(con, "AUD-319")
        assert outcome["status"] == "INCONSISTENT_AUD_IDENTITIES"
        assert outcome["components"] == []
        assert db.read_bytes() == before


def test_319_cross_component_timeline_envelope_is_not_aud_walltime(tmp_path):
    db = _source(tmp_path)
    with sqlite3.connect(db) as con:
        con.execute(
            "UPDATE audit_fulfillment_attempts "
            "SET status='SUCCESS',finished_at='2026-10-08T15:00:04Z' "
            "WHERE attempt_id='T-3'"
        )
    original = db.read_bytes()
    with sqlite3.connect(db.resolve().as_uri() + "?mode=ro&immutable=1", uri=True) as con:
        report = fulfillment_attempt_intervals(con, "AUD-319")
    envelope = report["attempt_envelope"]
    assert envelope["status"] == "COMPLETE_RECORDED_ATTEMPT_COHORT"
    assert envelope["attempts_with_timing"] == 3
    assert envelope["total_attempts"] == 3
    assert envelope["summed_attempt_ms"] == 4250
    assert envelope["union_active_ms"] == 3750
    assert envelope["overlap_attempt_ms"] == 500
    assert envelope["observed_span_ms"] == 4000
    assert envelope["unobserved_gap_between_attempts_ms"] == 250
    assert envelope["exclusive_audit_or_non_ai_wall_time_proven"] is False
    timeline = inspect_stage_economics(db, "AUD-319")
    assert timeline["fulfillment"]["attempt_envelope"] == envelope
    console = "\n".join(stage_console_lines(timeline))
    html = stage_report_html(timeline)
    assert "união ativa 3.75 s" in console
    assert "sobreposição 0.50 s" in console
    assert "lacunas entre tentativas 0.25 s" in console
    assert "Envelope de tentativas fulfillment" in html
    assert "3.75 s" in html and "4.25 s" in html
    assert "não duração da AUD" in html
    assert db.read_bytes() == original


def test_319_partial_work_cohort_must_not_display_total_duration(tmp_path):
    db = _source(tmp_path)
    original = db.read_bytes()
    outcome = inspect_stage_economics(db, "AUD-319")
    envelope = outcome["fulfillment"]["attempt_envelope"]
    assert envelope["status"] == "INCOMPLETE_ATTEMPT_COHORT"
    for key in (
        "summed_attempt_ms", "union_active_ms", "overlap_attempt_ms",
        "observed_span_ms", "unobserved_gap_between_attempts_ms",
    ):
        assert envelope[key] is None
    assert "Envelope fulfillment: N/D" in "\n".join(stage_console_lines(outcome))
    assert "Envelope fulfillment: N/D" in stage_report_html(outcome)
    assert db.read_bytes() == original
