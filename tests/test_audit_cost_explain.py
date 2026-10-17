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


import pytest


@pytest.mark.parametrize("invalid", [-0.01, float("-inf"), True])
def test_invalid_observed_cost_is_not_reported_inside_forecast_range(invalid):
    html = forecast_readout(
        {"expected_cost": .1, "likely_low": 0, "likely_high": .2,
         "potential": .3},
        observed_total=invalid, priced_attempts=1, total_attempts=1,
    )
    assert "Posição do custo na faixa histórica: N/D" in html
    assert "dentro da faixa histórica provável" not in html
    assert "Desvio frente à estimativa pontual" not in html


@pytest.mark.parametrize("invalid_field", ["expected_cost", "likely_low", "likely_high"])
def test_negative_forecast_money_never_produces_false_interval_claim(
    invalid_field,
):
    forecast = {
        "expected_cost": .1, "likely_low": .05,
        "likely_high": .2, "potential": .3,
    }
    forecast[invalid_field] = -1
    html = forecast_readout(
        forecast, observed_total=.15, priced_attempts=1, total_attempts=1,
    )
    if invalid_field in ("likely_low", "likely_high"):
        assert "Posição do custo na faixa histórica: N/D" in html
        assert "dentro da faixa histórica provável" not in html
    else:
        assert "Desvio frente à estimativa pontual" not in html
    assert "nan%" not in html.lower()


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


def test_optional_directed_attempts_prevent_false_total_forecast_comparison():
    forecast = {"expected_cost": .06, "likely_low": .01, "likely_high": .2}
    html = forecast_readout(
        forecast, observed_total=.15, priced_attempts=8,
        total_attempts=8, optional_attempts=1,
    )
    assert "análise complementar/direcionada" in html
    assert "dentro da faixa histórica provável" not in html
    assert "Desvio frente à estimativa pontual" not in html


def test_mixed_currency_does_not_claim_forecast_range():
    html = forecast_readout(
        {"expected_cost": .1, "likely_low": .05, "likely_high": .3},
        observed_total=.2, priced_attempts=2, total_attempts=2,
        comparable_currency=False,
    )
    assert "Moedas dos custos" in html
    assert "dentro da faixa histórica provável" not in html


@pytest.mark.parametrize("invalid", [None, "2", -1, True, 1.5, float("inf")])
def test_invalid_attempt_counts_abstain_from_cost_accuracy(invalid):
    forecast = {"expected_cost": 0.1, "likely_low": 0, "likely_high": 0.2}
    for counts in ({"priced_attempts": invalid, "total_attempts": 2},
                   {"priced_attempts": 2, "total_attempts": invalid},
                   {"priced_attempts": 2, "total_attempts": 2, "optional_attempts": invalid}):
        html = forecast_readout(forecast, observed_total=0.12,
                                priced_attempts=counts["priced_attempts"],
                                total_attempts=counts["total_attempts"],
                                optional_attempts=counts.get("optional_attempts", 0))
        assert "Contagens de tentativas inválidas" in html
        assert "Posição do custo na faixa histórica: N/D" in html
        assert "Desvio frente à estimativa pontual" not in html


def test_more_priced_than_total_does_not_claim_full_coverage():
    html = forecast_readout(
        {"expected_cost": 0.1, "likely_low": 0, "likely_high": 0.2},
        observed_total=0.15, priced_attempts=3, total_attempts=2,
    )
    assert "Contagens de tentativas inválidas" in html
    assert "Posição do custo na faixa histórica: N/D" in html


def test_unrepresentable_cost_deviation_is_not_reported_as_infinite() -> None:
    html = forecast_readout(
        {"expected_cost": 1e-300, "likely_low": 0, "likely_high": 1e308},
        observed_total=1e308, priced_attempts=1, total_attempts=1,
    )
    assert "amplitude não representável" in html
    assert "+inf%" not in html.lower()


def test_optional_attempt_count_exceeding_total_cannot_be_reported_as_valid():
    html = forecast_readout(
        {"expected_cost": 0.1, "likely_low": 0.05, "likely_high": 0.2},
        observed_total=0.12, priced_attempts=2, total_attempts=2,
        optional_attempts=3,
    )
    assert "Contagens de tentativas inválidas" in html
    assert "Posição do custo na faixa histórica: N/D" in html
    assert "Há 3 tentativa" not in html
    assert "Desvio frente à estimativa pontual" not in html
