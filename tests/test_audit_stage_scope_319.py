"""#319: real SQLite physical console time + M18/M20 7+1 attempts, no providers."""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import sqlite3
from types import SimpleNamespace

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
