"""#319: financial forecast interpretation is read-only and coverage-aware."""
from __future__ import annotations

import sqlite3

from rasai.audit_cost_explain import forecast_readout
from rasai.audit_attempt_timeline import read_audit_attempt_timeline


def test_realistic_severe_point_deviation_can_still_be_inside_interval():
    data = {
        "expected_cost": 0.0638734,
        "actual_cost": 0.153062004,
        "likely_low": 0.0170852,
        "likely_high": 0.17323987,
        "potential": 0.23679907,
        "status": "CRÍTICO",
    }
    html = forecast_readout(
        data, observed_total=0.153062004, priced_attempts=8, total_attempts=8
    )
    assert "dentro da faixa histórica provável" in html
    assert "+139.63%" in html
    assert "não constitui fatura" in html
    assert "P90" in html
    assert "pós-AUD" in html


def test_cost_coverage_incomplete_never_claims_interval_precision():
    data = {"expected_cost": 0.06, "likely_low": 0.02, "likely_high": 0.2}
    html = forecast_readout(data, observed_total=0.05, priced_attempts=5, total_attempts=8)
    assert "5/8 tentativa" in html
    assert "Posição do custo na faixa histórica: N/D" in html
    assert "dentro da faixa histórica provável" not in html
    assert "Desvio frente à estimativa pontual" not in html


def test_absent_or_invalid_forecast_does_not_invent_cost():
    assert "Sem previsão financeira" in forecast_readout(
        None, observed_total=None, priced_attempts=0, total_attempts=0
    )
    html = forecast_readout(
        {"expected_cost": "NaN", "likely_low": 0.1, "likely_high": 0.05},
        observed_total=None, priced_attempts=0, total_attempts=1
    )
    assert "N/D" in html
    assert "nan%" not in html.lower()
    assert "dentro da faixa" not in html


def test_explicit_zero_value_is_covered_and_no_other_aud_leaks(tmp_path):
    db = tmp_path / "audit.db"
    with sqlite3.connect(db) as con:
        con.execute(
            "CREATE TABLE ai_provider_attempts (attempt_id TEXT, audit_id TEXT, "
            "operation TEXT, started_at TEXT, finished_at TEXT, "
            "observed_cost REAL, observed_cost_currency TEXT)"
        )
        con.executemany("INSERT INTO ai_provider_attempts VALUES (?,?,?,?,?,?,?)", [
            ("ZERO", "AUD-1", "DIRECTED_ANALYSIS", "2026-10-09T10:00:00Z",
             "2026-10-09T10:00:01Z", 0, "USD"),
            ("OTHER", "AUD-2", "IMPROVEMENT_INTELLIGENCE", "2026-10-09T10:00:00Z",
             "2026-10-09T10:00:01Z", 100, "USD"),
        ])
    original = db.read_bytes()
    timeline = read_audit_attempt_timeline(db, "AUD-1")
    assert timeline.attempts == 1
    assert timeline.provider_observed_usd == 0
    assert timeline.stages[0].observed_cost_attempts == 1
    assert timeline.stages[0].name == "DIRECTED_ANALYSIS"
    assert "dentro da faixa" in forecast_readout(
        {"expected_cost": 0.01, "likely_low": 0, "likely_high": 0.1},
        observed_total=0, priced_attempts=1, total_attempts=1
    )
    assert db.read_bytes() == original
