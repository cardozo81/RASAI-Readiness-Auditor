"""#319: real SQLite physical console time + M18/M20 7+1 attempts, no providers."""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import sqlite3
from types import SimpleNamespace

import pytest

from rasai.audit_attempt_inspection_319 import (
    inspect_audit_attempts, inspect_ai_stage_scope,
)

AUD = "AUD-319-TEST"
FOREIGN = "AUD-319-OTHER"

def make_aud(tmp_path: Path, *, completion="COMPLETE", include_window=True):
    root = tmp_path / AUD
    root.mkdir()
    db = root / "audit.db"
    with sqlite3.connect(db) as con:
        con.executescript("""
            CREATE TABLE audits(audit_id TEXT PRIMARY KEY, status TEXT, completion_status TEXT);
            CREATE TABLE console_execution_projections(
                audit_id TEXT, duration_ms INTEGER, started_at TEXT, finished_at TEXT);
            CREATE TABLE ai_provider_attempts(
                attempt_id TEXT PRIMARY KEY, audit_id TEXT, operation TEXT,
                surface TEXT, started_at TEXT, finished_at TEXT,
                duration_ms REAL, observed_cost REAL, observed_cost_currency TEXT,
                estimated_cost REAL, cost_currency TEXT);
            CREATE TABLE content_remediation_attempts(
                attempt_id TEXT PRIMARY KEY, audit_id TEXT, operation TEXT,
                started_at TEXT, finished_at TEXT, duration_ms REAL,
                observed_cost REAL, observed_cost_currency TEXT,
                estimated_cost REAL, cost_currency TEXT);
        """)
        con.executemany("INSERT INTO audits VALUES (?,?,?)", [
            (AUD, "COMPLETED", completion), (FOREIGN, "COMPLETED", "COMPLETE")])
        if include_window:
            con.execute("INSERT INTO console_execution_projections VALUES (?,?,?,?)",
                        (AUD, 1200000, "2026-10-08T10:00:00+00:00",
                         "2026-10-08T10:20:00+00:00"))
        rows = [
            ("IMP-1", AUD, "IMPROVEMENT_INTELLIGENCE", None,
             "2026-10-08T10:01:00+00:00", "2026-10-08T10:03:00+00:00",
             120000, .020, "USD", None, None),
            ("IMP-2", AUD, "IMPROVEMENT_INTELLIGENCE", None,
             "2026-10-08T10:02:00+00:00", "2026-10-08T10:04:00+00:00",
             120000, .030, "USD", None, None),
            ("SEM-1", AUD, "SEMANTIC_AI", None,
             "2026-10-08T10:04:00+00:00", "2026-10-08T10:05:00+00:00",
             60000, None, None, .004, "USD"),
            ("COMP-1", AUD, "COMPETITIVE_AI", None,
             "2026-10-08T10:05:00+00:00", "2026-10-08T10:06:00+00:00",
             60000, .005, "USD", None, None),
            ("DIR-POST", AUD, "DIRECTED_ANALYSIS", None,
             "2026-10-08T10:25:00+00:00", "2026-10-08T10:29:00+00:00",
             240000, .1, "USD", None, None),
            ("CROSS-UNCERTAIN", AUD, "DIRECTED_ANALYSIS", None,
             "2026-10-08T10:19:59+00:00", "2026-10-08T10:20:10+00:00",
             11000, .001, "USD", None, None),
            ("CLOCK-UNKNOWN", AUD, "SEMANTIC_AI", None,
             None, None, 30000, None, None, .002, "USD"),
            ("PRIVATE", FOREIGN, "DIRECTED_ANALYSIS", None,
             "2026-10-08T10:26:00+00:00", "2026-10-08T10:30:00+00:00",
             240000, 999, "USD", None, None),
        ]
        con.executemany("INSERT INTO ai_provider_attempts VALUES (?,?,?,?,?,?,?,?,?,?,?)", rows)
        con.execute(
            "INSERT INTO content_remediation_attempts VALUES (?,?,?,?,?,?,?,?,?,?)",
            ("M20-1", AUD, "CONTENT_REMEDIATION",
             "2026-10-08T10:06:00+00:00", "2026-10-08T10:07:00+00:00",
             60000, .02, "USD", None, None),
        )
    return root, db


def test_319_physical_console_window_separates_7_plus_1_by_stage_and_time(tmp_path):
    root, db = make_aud(tmp_path)
    before = sha256(db.read_bytes()).hexdigest()
    result = inspect_audit_attempts(root)
    stage = inspect_ai_stage_scope(root)
    assert result["attempts_total"] == 8
    assert result["stage_attempts_total"] == 8
    assert result["verified_aud_wall_duration_ms"] == 1200000
    assert result["ai_attempt_execution_scope"]["stage_attempts_total"] == 8
    assert stage["status"] == "VERIFIED_PHYSICAL_WINDOW_COHORTS"
    assert sum(row["attempts"] for row in stage["by_stage"]) == 8
    cohorts = stage["cohorts"]
    assert cohorts["WITHIN_VERIFIED_CONSOLE_SESSION"]["attempts"] == 5
    assert cohorts["AFTER_VERIFIED_CONSOLE_SESSION"]["attempts"] == 1
    assert cohorts["UNCERTAIN_TIME_OR_SCOPE"]["attempts"] == 2
    by = {(i["session_scope"], i["stage"]): i for i in stage["by_stage"]}
    improvement = by[("WITHIN_VERIFIED_CONSOLE_SESSION", "IMPROVEMENT_INTELLIGENCE")]
    assert improvement["attempts"] == 2
    assert improvement["summed_ai_attempts_ms"] == 240000
    assert improvement["union_active_ai_ms"] == 180000
    assert improvement["overlap_ai_ms"] == 60000
    assert improvement["provider_observed_attempts"] == 2
    assert improvement["provider_observed_usd"] == .05
    assert by[("AFTER_VERIFIED_CONSOLE_SESSION", "DIRECTED_ANALYSIS")]["attempts"] == 1
    assert by[("UNCERTAIN_TIME_OR_SCOPE", "DIRECTED_ANALYSIS")]["attempts"] == 1
    assert by[("WITHIN_VERIFIED_CONSOLE_SESSION", "CONTENT_REMEDIATION")]["attempts"] == 1
    assert "PRIVATE" not in str(result)
    assert "999" not in str(stage)
    assert stage["temporal_attribution"] == "CLOCK_PLACEMENT_ONLY_NOT_OPERATION_PROOF"
    assert sha256(db.read_bytes()).hexdigest() == before


@pytest.mark.parametrize("ledger", [
    "ai_provider_attempts", "content_remediation_attempts",
])
def test_319_oversized_ai_attempt_ledger_abstains_without_partial_costs(
    tmp_path, ledger,
):
    root, db = make_aud(tmp_path)
    # Copy real physical rows into the same AUD under unique attempt IDs.
    # 2001 extra attempts exceeds the 2000-row independent per-ledger budget.
    original = "IMP-1" if ledger == "ai_provider_attempts" else "M20-1"
    with sqlite3.connect(db) as con:
        fields = [row[1] for row in con.execute(f"PRAGMA table_info({ledger})")]
        source_columns = ", ".join(fields[1:])
        con.executemany(
            f"INSERT INTO {ledger} SELECT ?, {source_columns} "
            "FROM " + ledger + " WHERE attempt_id=?",
            ((f"OVERSIZE-{i}", original) for i in range(2001)),
        )
    before = db.read_bytes()
    with pytest.raises(ValueError, match="bounded inspection limit"):
        inspect_audit_attempts(root)
    assert db.read_bytes() == before


def test_319_partial_or_missing_window_never_classifies_calls_as_initial_or_later(tmp_path):
    for key, kwargs in (("partial", {"completion": "PARTIAL_RETRYABLE"}),
                        ("missing", {"include_window": False})):
        base = tmp_path / key
        base.mkdir()
        root, db = make_aud(base, **kwargs)
        before = db.read_bytes()
        result = inspect_audit_attempts(root)
        scope = result["ai_attempt_execution_scope"]
        assert result["verified_aud_wall_duration_ms"] is None
        assert scope["status"] == "AUD_WINDOW_UNVERIFIABLE"
        assert scope["cohorts"]["UNCERTAIN_TIME_OR_SCOPE"]["attempts"] == 8
        assert all(item["session_scope"] == "UNCERTAIN_TIME_OR_SCOPE"
                   for item in scope["by_stage"])
        assert db.read_bytes() == before


def test_319_metrics_html_shows_scope_by_stage_without_changing_scores(tmp_path, monkeypatch):
    from rasai import catalog_report_site as report
    root, db = make_aud(tmp_path)
    source = db.read_bytes()
    monkeypatch.setattr(report, "_audit_hero", lambda *_args: "")
    monkeypatch.setattr(report, "_catalog_metrics", lambda *_args: {})
    monkeypatch.setattr(report, "_catalog_metric_rows", lambda *_args: [])
    monkeypatch.setattr(report, "_section", lambda key, title, body:
                        "<section id='" + key + "'><h2>" + title + "</h2>" + body + "</section>")
    monkeypatch.setattr(report, "_table", lambda _headers, rows, **_kwargs:
                        " ".join(str(row) for row in rows))
    html = report._metrics_body(db, SimpleNamespace(scores=[], audit_id=AUD))
    assert "ai-session-scope-319" in html
    assert "Após a sessão física verificada" in html
    assert "Dentro da sessão física verificada" in html
    assert "Tempo/escopo não comprovável" in html
    assert "Improvement Intelligence" in html
    assert "Content Remediation" in html
    assert "Direcionada" not in html or "não equivale" in html
    assert "999" not in html
    assert db.read_bytes() == source


def test_319_metrics_html_shows_aud_scoped_m21_http_request_sums_not_stage_clocks(
    tmp_path, monkeypatch,
):
    from rasai import catalog_report_site as report
    root, db = make_aud(tmp_path)
    with sqlite3.connect(db) as con:
        con.execute(
            "CREATE TABLE web_performance_attempts("
            "attempt_id TEXT PRIMARY KEY, audit_id TEXT, "
            "service TEXT, duration_ms REAL)"
        )
        con.executemany(
            "INSERT INTO web_performance_attempts VALUES (?,?,?,?)",
            [
                ("PSI-1", AUD, "PAGESPEED_INSIGHTS", 20000.0),
                ("PSI-2", AUD, "PAGESPEED_INSIGHTS", 40000.0),
                ("CRUX-1", AUD, "CRUX_API", 10000.0),
                ("FOREIGN", FOREIGN, "PAGESPEED_INSIGHTS", 999000.0),
                ("UNKNOWN", AUD, "UNREGISTERED_PROVIDER", 777000.0),
            ],
        )
    before = db.read_bytes()
    monkeypatch.setattr(report, "_audit_hero", lambda *_args: "")
    monkeypatch.setattr(report, "_catalog_metrics", lambda *_args: {})
    monkeypatch.setattr(report, "_catalog_metric_rows", lambda *_args: [])
    monkeypatch.setattr(
        report, "_section",
        lambda key, title, body:
            "<section id='" + key + "'><h2>" + title + "</h2>" + body + "</section>"
    )
    monkeypatch.setattr(
        report, "_table",
        lambda _headers, rows, **_kwargs: " ".join(str(row) for row in rows)
    )
    html = report._metrics_body(db, SimpleNamespace(scores=[], audit_id=AUD))
    assert "http-request-observations-319" in html
    assert "Tempos observados de requisições web" in html
    assert "PageSpeed Insights" in html and "60.00 s" in html
    assert "CrUX API" in html and "10.00 s" in html
    assert "Tempo físico de fase: N/D" in html
    assert "não somar com atividade IA" in html
    assert "999.00 s" not in html
    assert "777.00 s" not in html
    assert "ai-session-scope-319" in html
    assert db.read_bytes() == before


def test_319_metrics_html_m21_incomplete_service_abstains_not_zero(
    tmp_path, monkeypatch,
):
    from rasai import catalog_report_site as report
    root, db = make_aud(tmp_path)
    with sqlite3.connect(db) as con:
        con.execute(
            "CREATE TABLE web_performance_attempts("
            "attempt_id TEXT PRIMARY KEY, audit_id TEXT, "
            "service TEXT, duration_ms REAL)"
        )
        con.executemany(
            "INSERT INTO web_performance_attempts VALUES (?,?,?,?)",
            [
                ("PSI-VALID", AUD, "PAGESPEED_INSIGHTS", 25000.0),
                ("PSI-UNKNOWN", AUD, "PAGESPEED_INSIGHTS", None),
                ("CRUX-VALID", AUD, "CRUX_API", 11000.0),
            ],
        )
    before = db.read_bytes()
    monkeypatch.setattr(report, "_audit_hero", lambda *_args: "")
    monkeypatch.setattr(report, "_catalog_metrics", lambda *_args: {})
    monkeypatch.setattr(report, "_catalog_metric_rows", lambda *_args: [])
    monkeypatch.setattr(
        report, "_section",
        lambda key, title, body:
            "<section id='" + key + "'><h2>" + title + "</h2>" + body + "</section>"
    )
    monkeypatch.setattr(
        report, "_table",
        lambda _headers, rows, **_kwargs: repr(rows)
    )
    html = report._metrics_body(db, SimpleNamespace(scores=[], audit_id=AUD))
    assert "http-request-observations-319" in html
    m21_html = html.split("http-request-observations-319", 1)[1]
    assert "'PageSpeed Insights', 'N/D'" in m21_html
    assert "'CrUX API', '11.00 s'" in m21_html
    assert "25.00 s" not in m21_html  # rejected whole partial service
    assert "Sem telemetria temporal completa" in m21_html
    assert db.read_bytes() == before


def test_319_fulfillment_wrapper_intervals_are_not_physical_stage_durations(tmp_path):
    root, db = make_aud(tmp_path)
    with sqlite3.connect(db) as con:
        con.executescript("""
            CREATE TABLE audit_fulfillment_work_items (
                work_item_id TEXT PRIMARY KEY, audit_id TEXT, component TEXT
            );
            CREATE TABLE audit_fulfillment_attempts (
                attempt_id TEXT PRIMARY KEY, audit_id TEXT, work_item_id TEXT,
                reprocess_id TEXT, started_at TEXT, finished_at TEXT, status TEXT
            );
        """)
        con.executemany(
            "INSERT INTO audit_fulfillment_work_items VALUES (?,?,?)",
            [("W-1", AUD, "EXTRACTION"), ("W-2", FOREIGN, "EXTRACTION")],
        )
        con.executemany(
            "INSERT INTO audit_fulfillment_attempts VALUES (?,?,?,?,?,?,?)",
            [
                ("A", AUD, "W-1", None, "2026-10-08T10:01:00Z",
                 "2026-10-08T10:03:00Z", "SUCCESS"),
                ("B", AUD, "W-1", None, "2026-10-08T10:02:00+00:00",
                 "2026-10-08T10:04:00+00:00", "FAILED_RETRYABLE"),
                ("POST", AUD, "W-1", None, "2026-10-08T10:22:00Z",
                 "2026-10-08T10:23:00Z", "SUCCESS"),
                ("RPR", AUD, "W-1", "RPR-ONE", "2026-10-08T10:05:00Z",
                 "2026-10-08T10:06:00Z", "SUCCESS"),
                ("UNKNOWN", AUD, "W-1", None, "2026-10-08T10:04:00",
                 "2026-10-08T10:06:00", "RUNNING"),
                ("FOREIGN", FOREIGN, "W-2", None, "2026-10-08T10:01:00Z",
                 "2026-10-08T10:19:00Z", "SUCCESS"),
            ],
        )
    before = sha256(db.read_bytes()).hexdigest()
    inspection = inspect_audit_attempts(root)
    evidence = inspection["fulfillment_attempt_temporal_evidence"]
    assert evidence["status"] == "ATTEMPT_INTERVALS_WITH_LIMITATIONS"
    assert evidence["attempts_total"] == 5
    assert evidence["physical_stage_duration_available"] is False
    assert inspection["non_ai_stages_measured"] is False
    groups = {
        (r["component"], r["temporal_scope"]): r for r in evidence["by_component"]
    }
    within = groups[("EXTRACTION", "WITHIN_VERIFIED_CONSOLE_WINDOW")]
    assert within["attempts"] == 2
    assert within["summed_elapsed_ms"] == 240000
    assert within["union_elapsed_ms"] == 180000
    assert within["overlap_elapsed_ms"] == 60000
    assert groups[("EXTRACTION", "AFTER_VERIFIED_CONSOLE_WINDOW")]["attempts"] == 1
    assert groups[("EXTRACTION", "REPROCESS_ATTEMPT")]["attempts"] == 1
    assert groups[("EXTRACTION", "WINDOW_UNVERIFIED")]["unknown_intervals"] == 1
    assert groups[("EXTRACTION", "WINDOW_UNVERIFIED")]["union_elapsed_ms"] is None
    assert "FOREIGN" not in str(evidence)
    assert sha256(db.read_bytes()).hexdigest() == before


@pytest.mark.parametrize("unverified_status", [
    "PENDING", "RUNNING", "WAITING_FOR_DATA", "UNRECOGNIZED", "SUCCESS ",
])
def test_319_nonterminal_or_unknown_attempt_status_never_proves_elapsed_time(
    tmp_path, unverified_status,
):
    """#319: elapsed timestamps alone do not make a WKA attempt terminal."""
    root, db = make_aud(tmp_path)
    with sqlite3.connect(db) as con:
        con.executescript("""
            CREATE TABLE audit_fulfillment_work_items(
                work_item_id TEXT PRIMARY KEY, audit_id TEXT, component TEXT
            );
            CREATE TABLE audit_fulfillment_attempts(
                attempt_id TEXT PRIMARY KEY, audit_id TEXT, work_item_id TEXT,
                reprocess_id TEXT, started_at TEXT, finished_at TEXT, status TEXT
            );
        """)
        con.execute(
            "INSERT INTO audit_fulfillment_work_items VALUES (?,?,?)",
            ("WORK", AUD, "CAPTURE"),
        )
        con.executemany(
            "INSERT INTO audit_fulfillment_attempts VALUES (?,?,?,?,?,?,?)",
            [
                ("INVALID", AUD, "WORK", None,
                 "2026-10-08T10:01:00Z", "2026-10-08T10:02:00Z",
                 unverified_status),
                ("VALID", AUD, "WORK", None,
                 "2026-10-08T10:03:00Z", "2026-10-08T10:04:00Z",
                 "FAILED_RETRYABLE"),
            ],
        )
    original = db.read_bytes()
    projection = inspect_audit_attempts(root)["fulfillment_attempt_temporal_evidence"]
    assert projection["status"] == "ATTEMPT_INTERVALS_WITH_LIMITATIONS"
    assert projection["attempts_total"] == 2
    groups = {row["temporal_scope"]: row for row in projection["by_component"]}
    unverified = groups["WINDOW_UNVERIFIED"]
    assert unverified["attempts"] == 1
    assert unverified["verified_intervals"] == 0
    assert unverified["unknown_intervals"] == 1
    assert unverified["summed_elapsed_ms"] is None
    assert unverified["union_elapsed_ms"] is None
    valid = groups["WITHIN_VERIFIED_CONSOLE_WINDOW"]
    assert valid["attempts"] == valid["verified_intervals"] == 1
    assert valid["summed_elapsed_ms"] == 60000
    assert valid["union_elapsed_ms"] == 60000
    assert projection["physical_stage_duration_available"] is False
    assert projection["provider_requests"] == projection["audit_writes"] == 0
    assert db.read_bytes() == original


def test_319_missing_fulfillment_tables_and_partial_aud_abstain(tmp_path):
    (tmp_path / "missing").mkdir()
    root, db = make_aud(tmp_path / "missing")
    source = db.read_bytes()
    evidence = inspect_audit_attempts(root)["fulfillment_attempt_temporal_evidence"]
    assert evidence["status"] == "SCHEMA_NOT_AVAILABLE"
    assert evidence["by_component"] == []
    assert db.read_bytes() == source
    (tmp_path / "partial").mkdir()
    root2, db2 = make_aud(tmp_path / "partial", completion="PARTIAL_RETRYABLE")
    with sqlite3.connect(db2) as con:
        con.executescript("""
            CREATE TABLE audit_fulfillment_work_items (
                work_item_id TEXT PRIMARY KEY, audit_id TEXT, component TEXT
            );
            CREATE TABLE audit_fulfillment_attempts (
                attempt_id TEXT PRIMARY KEY, audit_id TEXT, work_item_id TEXT,
                reprocess_id TEXT, started_at TEXT, finished_at TEXT, status TEXT
            );
        """)
        con.execute(
            "INSERT INTO audit_fulfillment_work_items VALUES (?,?,?)",
            ("W-ONE", AUD, "CAPTURE"),
        )
        con.execute(
            "INSERT INTO audit_fulfillment_attempts VALUES (?,?,?,?,?,?,?)",
            ("ATT-ONE", AUD, "W-ONE", None,
             "2026-10-08T10:01:00Z", "2026-10-08T10:02:00Z", "SUCCESS"),
        )
    digest = sha256(db2.read_bytes()).hexdigest()
    result = inspect_audit_attempts(root2)
    assert result["verified_aud_wall_duration_ms"] is None
    attempt = result["fulfillment_attempt_temporal_evidence"]["by_component"][0]
    assert attempt["temporal_scope"] == "WINDOW_UNVERIFIED"
    assert result["non_ai_stages_measured"] is False
    assert sha256(db2.read_bytes()).hexdigest() == digest


def test_319_fulfillment_metrics_report_is_explicitly_not_stage_measurement(
    tmp_path, monkeypatch,
):
    from rasai import catalog_report_site as report
    root, db = make_aud(tmp_path)
    with sqlite3.connect(db) as con:
        con.executescript("""
            CREATE TABLE audit_fulfillment_work_items (
                work_item_id TEXT PRIMARY KEY, audit_id TEXT, component TEXT
            );
            CREATE TABLE audit_fulfillment_attempts (
                attempt_id TEXT PRIMARY KEY, audit_id TEXT, work_item_id TEXT,
                reprocess_id TEXT, started_at TEXT, finished_at TEXT, status TEXT
            );
        """)
        con.execute(
            "INSERT INTO audit_fulfillment_work_items VALUES (?,?,?)",
            ("WORK", AUD, "EXTRACTION"),
        )
        con.execute(
            "INSERT INTO audit_fulfillment_attempts VALUES (?,?,?,?,?,?,?)",
            ("ATT", AUD, "WORK", None,
             "2026-10-08T10:01:00Z", "2026-10-08T10:03:00Z", "SUCCESS"),
        )
    before = db.read_bytes()
    monkeypatch.setattr(report, "_audit_hero", lambda *_: "")
    monkeypatch.setattr(report, "_catalog_metrics", lambda *_: {})
    monkeypatch.setattr(report, "_catalog_metric_rows", lambda *_: [])
    monkeypatch.setattr(
        report, "_section", lambda key, title, body:
        "<section id='" + key + "'>" + title + body + "</section>",
    )
    monkeypatch.setattr(report, "_table", lambda _headers, rows, **_kwargs:
                        " ".join(str(r) for r in rows))
    html = report._metrics_body(db, SimpleNamespace(scores=[], audit_id=AUD))
    assert "fulfillment-intervals-319" in html
    assert "Intervalos das tentativas operacionais" in html
    assert "120.00 s" in html
    assert "não duração física exclusiva" in html
    assert "N/D - sem cronômetro físico da etapa" in html
    assert db.read_bytes() == before


def test_319_cross_aud_work_item_reference_abstains_instead_of_dropping_row(tmp_path):
    root, db = make_aud(tmp_path)
    with sqlite3.connect(db) as con:
        con.executescript("""
            CREATE TABLE audit_fulfillment_work_items (
                work_item_id TEXT PRIMARY KEY, audit_id TEXT, component TEXT
            );
            CREATE TABLE audit_fulfillment_attempts (
                attempt_id TEXT PRIMARY KEY, audit_id TEXT, work_item_id TEXT,
                reprocess_id TEXT, started_at TEXT, finished_at TEXT, status TEXT
            );
        """)
        con.execute(
            "INSERT INTO audit_fulfillment_work_items VALUES (?,?,?)",
            ("FOREIGN-WORK", FOREIGN, "CAPTURE"),
        )
        con.execute(
            "INSERT INTO audit_fulfillment_attempts VALUES (?,?,?,?,?,?,?)",
            ("CROSS-AUD", AUD, "FOREIGN-WORK", None,
             "2026-10-08T10:01:00Z", "2026-10-08T10:02:00Z", "SUCCESS"),
        )
    original = db.read_bytes()
    inspection = inspect_audit_attempts(root)
    evidence = inspection["fulfillment_attempt_temporal_evidence"]
    assert evidence["status"] == "WORK_ITEM_AUDIT_IDENTITY_MISMATCH"
    assert evidence["by_component"] == []
    assert evidence["physical_stage_duration_available"] is False
    assert inspection["non_ai_stages_measured"] is False
    assert db.read_bytes() == original


def test_319_monotonic_step_log_is_observed_but_never_exclusive_or_sealed(tmp_path):
    import json
    root, db = make_aud(tmp_path)
    directory = root / "logs"
    directory.mkdir()
    log = directory / "audit.log"
    events = [
        {"event": "AUDIT_PIPELINE_STEP_STARTED", "audit_id": AUD,
         "timestamp": "2026-10-08T10:02:00Z"},
        {"event": "AUDIT_PIPELINE_STEP_FINISHED", "audit_id": AUD,
         "timestamp": "2026-10-08T10:04:00Z", "phase": "COLLECTION",
         "step_key": "RENDER", "duration_ms": 120000, "status": "SUCCESS"},
        {"event": "AUDIT_PIPELINE_STEP_FINISHED", "audit_id": AUD,
         "timestamp": "2026-10-08T10:05:00Z", "phase": "PERF",
         "step_key": "PSI", "duration_ms": 60000, "status": "ERROR"},
        {"event": "AUDIT_PIPELINE_STEP_FINISHED", "audit_id": FOREIGN,
         "timestamp": "2026-10-08T10:06:00Z", "phase": "PERF",
         "step_key": "FOREIGN", "duration_ms": 999999, "status": "SUCCESS"},
        {"event": "AUDIT_PIPELINE_STEP_FINISHED", "audit_id": AUD,
         "timestamp": "2026-10-08T10:26:00Z", "phase": "REPROCESS",
         "step_key": "POST_AUD", "duration_ms": 30000, "status": "SUCCESS"},
    ]
    log.write_text("".join(json.dumps(v) + "\n" for v in events), encoding="utf-8")
    old_db, old_log = db.read_bytes(), log.read_bytes()
    response = inspect_audit_attempts(root)
    evidence = response["pipeline_step_timer_evidence"]
    assert evidence["status"] == "OBSERVED_UNSEALED_WRAPPER_TIMERS"
    assert evidence["physical_wrapper_timer_observed"] is True
    assert evidence["exclusive_stage_wall_clock_proven"] is False
    assert evidence["operational_log_sealed_evidence"] is False
    assert response["non_ai_stages_measured"] is False
    assert evidence["audit_writes"] == evidence["provider_requests"] == 0
    assert [item["observed_monotonic_wrapper_ms"] for item in evidence["by_step"]] == [
        120000, 60000, 30000,
    ]
    assert evidence["by_step"][0]["console_window_placement"] == "WITHIN_VERIFIED_WINDOW_UNSEALED"
    assert evidence["by_step"][2]["console_window_placement"] == "NOT_PROVEN_IN_INITIAL_WINDOW"
    assert "FOREIGN" not in str(evidence)
    assert db.read_bytes() == old_db and log.read_bytes() == old_log
    assert inspect_audit_attempts(root)["pipeline_step_timer_evidence"] == evidence


@pytest.mark.parametrize(("name", "first_key"), [
    ("foreign-aud", '"audit_id": "AUD-319-OTHER",'),
    ("contradictory-duration", '"duration_ms": 999999,'),
    ("duplicate-identical-duration", '"duration_ms": 2000,'),
    ("wrong-event", '"event": "AUDIT_PIPELINE_STEP_STARTED",'),
])
def test_319_duplicate_pipeline_json_event_keys_never_become_timer_evidence(
    tmp_path, name, first_key,
):
    import json
    from rasai.audit_step_timer_inspection import inspect_pipeline_step_timers
    root, db = make_aud(tmp_path)
    directory = root / "logs"
    directory.mkdir()
    log = directory / "audit.log"
    good = {
        "event": "AUDIT_PIPELINE_STEP_FINISHED", "audit_id": AUD,
        "timestamp": "2026-10-08T10:05:00Z", "phase": "COLLECTION",
        "step_key": "RENDER", "duration_ms": 2000, "status": "SUCCESS",
    }
    # A standard decoder uses the final value and incorrectly presents an
    # apparently valid timer even when the raw event has conflicting keys.
    line = "{" + first_key + json.dumps(good)[1:]
    assert json.loads(line) == good
    log.write_text(line + "\n", encoding="utf-8")
    before = (db.read_bytes(), log.read_bytes())
    evidence = inspect_pipeline_step_timers(root, AUD, None)
    assert evidence["status"] == "LOG_JSON_INVALID"
    assert evidence["by_step"] == []
    assert evidence["provider_requests"] == evidence["audit_writes"] == 0
    assert (db.read_bytes(), log.read_bytes()) == before


def test_319_invalid_or_missing_pipeline_log_fails_closed(tmp_path):
    import json
    from rasai.audit_step_timer_inspection import inspect_pipeline_step_timers
    root, db = make_aud(tmp_path)
    assert inspect_pipeline_step_timers(root, AUD, None)["status"] == "NOT_AVAILABLE"
    assert not (root / "logs").exists()
    directory = root / "logs"
    directory.mkdir()
    log = directory / "audit.log"
    event = {"event": "AUDIT_PIPELINE_STEP_FINISHED", "audit_id": AUD,
             "timestamp": "2026-10-08T10:05:00Z", "phase": "COLLECTION",
             "step_key": "M3", "duration_ms": 2000, "status": "SUCCESS"}
    log.write_text(json.dumps(event) + "\n" + "broken\n", encoding="utf-8")
    result = inspect_pipeline_step_timers(root, AUD, None)
    assert result["status"] == "LOG_JSON_INVALID" and result["by_step"] == []
    log.write_text(json.dumps({**event, "duration_ms": -1}) + "\n", encoding="utf-8")
    assert inspect_pipeline_step_timers(root, AUD, None)["status"] == "STEP_EVIDENCE_INVALID"
    log.write_text(json.dumps({**event, "timestamp": "2026-10-08T10:05:00"}) + "\n", encoding="utf-8")
    assert inspect_pipeline_step_timers(root, AUD, None)["status"] == "STEP_EVIDENCE_INVALID"
    log.write_bytes(b"x" * (8 * 1024 * 1024 + 1))
    assert inspect_pipeline_step_timers(root, AUD, None)["status"] == "LOG_TOO_LARGE"


def test_319_partial_aud_does_not_promote_wrapper_to_initial_session(tmp_path):
    import json
    base = tmp_path / "partial"
    base.mkdir()
    root, _ = make_aud(base, completion="PARTIAL_RETRYABLE")
    directory = root / "logs"
    directory.mkdir()
    (directory / "audit.log").write_text(json.dumps({
        "event": "AUDIT_PIPELINE_STEP_FINISHED", "audit_id": AUD,
        "timestamp": "2026-10-08T10:03:00Z", "phase": "COLLECTION",
        "step_key": "RENDER", "duration_ms": 3000, "status": "SUCCESS",
    }) + "\n", encoding="utf-8")
    response = inspect_audit_attempts(root)
    event = response["pipeline_step_timer_evidence"]["by_step"][0]
    assert event["console_window_placement"] == "NOT_PROVEN_IN_INITIAL_WINDOW"
    assert response["non_ai_stages_measured"] is False


@pytest.mark.parametrize("case", ("valid", "corrupt", "missing", "partial"))
def test_319_metrics_wrapper_timer_projection_never_claims_exclusive_clock(
    tmp_path, monkeypatch, case,
):
    """Expose actual wrapper observations, but no partial JSONL or phase claims."""
    import json
    from rasai import catalog_report_site as report

    root, db = make_aud(
        tmp_path, completion="PARTIAL_RETRYABLE" if case == "partial" else "COMPLETE"
    )
    event = {
        "event": "AUDIT_PIPELINE_STEP_FINISHED",
        "audit_id": AUD,
        "timestamp": "2026-10-08T10:05:00Z",
        "phase": "COLLECTION",
        "step_key": "RENDER",
        "duration_ms": 2000,
        "status": "SUCCESS",
    }
    if case != "missing":
        directory = root / "logs"
        directory.mkdir()
        log = directory / "audit.log"
        events = [json.dumps(event) + "\n"]
        if case == "valid":
            events += [
                json.dumps({**event, "audit_id": FOREIGN, "duration_ms": 999000}) + "\n",
                json.dumps({**event, "timestamp": "2026-10-08T10:26:00Z",
                            "step_key": "POST_AUD", "duration_ms": 3000}) + "\n",
            ]
        if case == "corrupt":
            events += ["broken JSONL\n"]
        log.write_text("".join(events), encoding="utf-8")
        original_log = log.read_bytes()
    original_db = db.read_bytes()

    monkeypatch.setattr(report, "_audit_hero", lambda *_args: "")
    monkeypatch.setattr(report, "_catalog_metrics", lambda *_args: {})
    monkeypatch.setattr(report, "_catalog_metric_rows", lambda *_args: [])
    monkeypatch.setattr(
        report, "_section",
        lambda key, title, body:
            "<section id='" + key + "'><h2>" + title + "</h2>" + body + "</section>",
    )
    monkeypatch.setattr(
        report, "_table",
        lambda _headers, rows, **_kwargs: repr(rows),
    )
    html = report._metrics_body(db, SimpleNamespace(scores=[], audit_id=AUD))
    timers_html = html.split("pipeline-wrapper-timers-319", 1)[1].split("</section>", 1)[0]
    assert "Cronômetros operacionais dos invólucros do pipeline" in timers_html
    assert "não tempos exclusivos" in timers_html
    assert "não comprova identidade de execução" in timers_html
    assert "999.00 s" not in timers_html  # other AUD is never included
    if case in ("valid", "partial"):
        assert "Distribuição dos invólucros por fase" in timers_html
        # The test mocks _table to rows-only, so headers are deliberately absent.
        assert "N/D - não medido" in timers_html
        assert "não tempo da fase" in timers_html
    else:
        assert "Distribuição dos invólucros por fase" not in timers_html
    if case in ("valid", "partial"):
        assert "2.00 s" in timers_html
        assert "Sucesso" in timers_html
        if case == "valid":
            assert "3.00 s" in timers_html
            assert "Na janela verificada (log não selado)" in timers_html
            assert "Vínculo à sessão inicial não comprovado" in timers_html
        else:
            assert "Na janela verificada (log não selado)" not in timers_html
            assert "Vínculo à sessão inicial não comprovado" in timers_html
    else:
        assert "Tempos operacionais: N/D" in timers_html
        assert "2.00 s" not in timers_html  # corrupt log does not leak partial events
    assert db.read_bytes() == original_db
    if case != "missing":
        assert log.read_bytes() == original_log


def test_319_phase_wrapper_distribution_never_sums_overlapping_operations(tmp_path):
    import json
    root, db = make_aud(tmp_path)
    logs = root / "logs"
    logs.mkdir()
    source = logs / "audit.log"
    events = [
        {"event": "AUDIT_PIPELINE_STEP_FINISHED", "audit_id": AUD,
         "timestamp": "2026-10-08T10:05:00Z", "phase": "COLLECTION",
         "step_key": "RENDER", "duration_ms": 120000, "status": "SUCCESS"},
        {"event": "AUDIT_PIPELINE_STEP_FINISHED", "audit_id": AUD,
         "timestamp": "2026-10-08T10:05:30Z", "phase": "COLLECTION",
         "step_key": "EXTRACT", "duration_ms": 90000, "status": "SUCCESS"},
        {"event": "AUDIT_PIPELINE_STEP_FINISHED", "audit_id": AUD,
         "timestamp": "2026-10-08T10:06:00Z", "phase": "PERF",
         "step_key": "PSI", "duration_ms": 10000, "status": "ERROR"},
        {"event": "AUDIT_PIPELINE_STEP_FINISHED", "audit_id": AUD,
         "timestamp": "2026-10-08T10:26:00Z", "phase": "COLLECTION",
         "step_key": "CONTINUATION", "duration_ms": 30000, "status": "SUCCESS"},
        {"event": "AUDIT_PIPELINE_STEP_FINISHED", "audit_id": FOREIGN,
         "timestamp": "2026-10-08T10:07:00Z", "phase": "COLLECTION",
         "step_key": "FOREIGN", "duration_ms": 999999, "status": "SUCCESS"},
    ]
    source.write_text("".join(json.dumps(event) + "\n" for event in events), encoding="utf-8")
    before = (db.read_bytes(), source.read_bytes())
    output = inspect_audit_attempts(root)
    wrappers = output["pipeline_step_timer_evidence"]
    assert wrappers["status"] == "OBSERVED_UNSEALED_WRAPPER_TIMERS"
    assert wrappers["phase_summary_measurement"] == "WRAPPER_MIN_MAX_NOT_STAGE_WALL_CLOCK"
    assert wrappers["exclusive_stage_wall_clock_proven"] is False
    assert output["non_ai_stages_measured"] is False
    phases = wrappers["by_phase"]
    assert len(phases) == 3
    inside = next(row for row in phases if row["phase"] == "COLLECTION"
                  and row["console_window_placement"] == "WITHIN_VERIFIED_WINDOW_UNSEALED")
    assert inside["wrapper_count"] == 2
    assert inside["success_count"] == 2 and inside["error_count"] == 0
    assert inside["min_observed_wrapper_ms"] == 90000
    assert inside["max_observed_wrapper_ms"] == 120000
    assert inside["exclusive_phase_wall_clock_ms"] is None
    assert inside["physical_execution_identity_verified"] is False
    later = next(row for row in phases if row["phase"] == "COLLECTION"
                 and row["console_window_placement"] == "NOT_PROVEN_IN_INITIAL_WINDOW")
    assert later["wrapper_count"] == 1
    assert later["min_observed_wrapper_ms"] == later["max_observed_wrapper_ms"] == 30000
    perf = next(row for row in phases if row["phase"] == "PERF")
    assert perf["error_count"] == 1 and perf["success_count"] == 0
    assert wrappers["provider_requests"] == wrappers["audit_writes"] == 0
    assert (db.read_bytes(), source.read_bytes()) == before


def test_319_corrupt_step_log_never_publishes_phase_summary(tmp_path):
    import json
    from rasai.audit_step_timer_inspection import inspect_pipeline_step_timers

    root, db = make_aud(tmp_path)
    log_dir = root / "logs"
    log_dir.mkdir()
    path = log_dir / "audit.log"
    event = {"event": "AUDIT_PIPELINE_STEP_FINISHED", "audit_id": AUD,
             "timestamp": "2026-10-08T10:05:00Z", "phase": "COLLECTION",
             "step_key": "RENDER", "duration_ms": 2000, "status": "SUCCESS"}
    path.write_text(json.dumps(event) + "\n" + "invalid-json\n", encoding="utf-8")
    original = (db.read_bytes(), path.read_bytes())
    evidence = inspect_pipeline_step_timers(root, AUD, None)
    assert evidence["status"] == "LOG_JSON_INVALID"
    assert evidence["by_step"] == []
    assert evidence["by_phase"] == []
    assert (db.read_bytes(), path.read_bytes()) == original


def test_319_log_appended_during_read_abstains_and_keeps_source_aud_immutable(
    tmp_path, monkeypatch,
):
    """A concurrently growing operational log cannot publish partial phase timers."""
    import json
    from pathlib import Path
    from rasai.audit_step_timer_inspection import inspect_pipeline_step_timers

    root, db = make_aud(tmp_path)
    directory = root / "logs"
    directory.mkdir()
    log = directory / "audit.log"
    event = {
        "event": "AUDIT_PIPELINE_STEP_FINISHED",
        "audit_id": AUD,
        "timestamp": "2026-10-08T10:05:00Z",
        "phase": "COLLECTION",
        "step_key": "RENDER",
        "duration_ms": 2000,
        "status": "SUCCESS",
    }
    log.write_text(json.dumps(event) + "\n", encoding="utf-8")
    db_before = db.read_bytes()
    original_open = Path.open
    changed = []

    def append_on_read(self, mode="r", *args, **kwargs):
        if self == log and mode == "rb" and not changed:
            changed.append(True)
            with original_open(self, "ab") as writer:
                writer.write((json.dumps({**event, "step_key": "NEW"}) + "\n").encode())
        return original_open(self, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", append_on_read)
    response = inspect_pipeline_step_timers(root, AUD, None)
    assert changed
    assert response["status"] == "LOG_CHANGED_DURING_READ"
    assert response["by_step"] == []
    assert response["by_phase"] == []
    assert response["exclusive_stage_wall_clock_proven"] is False
    assert response["provider_requests"] == response["audit_writes"] == 0
    assert db.read_bytes() == db_before
