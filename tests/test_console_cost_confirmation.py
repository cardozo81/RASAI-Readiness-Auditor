from __future__ import annotations

from types import ModuleType, SimpleNamespace

from rasai import console_cost_confirmation
from rasai.console_cost_confirmation import install
from rasai.cost_forecast import CostForecast


def _forecast() -> CostForecast:
    return CostForecast(
        available=True,
        show_confirmation=True,
        currency="USD",
        success_baseline=0.10,
        expected=0.12,
        likely_low=0.10,
        likely_high=0.14,
        potential=0.18,
        sample_runs=12,
        sample_calls=40,
        target_pages=3,
        confidence="MODERADA",
        source="test",
        repriced_share=1.0,
        notes=("teste",),
    )


def _module(calls: list[str]) -> ModuleType:
    module = ModuleType("cost_confirmation_test_console")
    module.render_header = lambda state: calls.append("header")
    module.run_audit_from_console = lambda state: calls.append("run") or 0
    module._post_run_actions = lambda state: calls.append("post") or True
    return module


def test_cost_confirmation_decline_returns_without_running(monkeypatch) -> None:
    calls: list[str] = []
    module = _module(calls)
    monkeypatch.setattr(console_cost_confirmation, "forecast_local_cost", lambda state: _forecast())
    monkeypatch.setattr("builtins.input", lambda prompt="": "V")
    install(module)
    state = SimpleNamespace(status="READY", operation="", error="")

    assert module.run_audit_from_console(state) == 0
    assert "run" not in calls
    assert state.operation == "LOCAL:COST_DECLINED"
    assert module._post_run_actions(state) is False
    assert "post" not in calls


def test_cost_confirmation_confirm_runs_normally(monkeypatch) -> None:
    calls: list[str] = []
    module = _module(calls)
    monkeypatch.setattr(console_cost_confirmation, "forecast_local_cost", lambda state: _forecast())
    monkeypatch.setattr("builtins.input", lambda prompt="": "C")
    install(module)
    state = SimpleNamespace(status="READY", operation="", error="")

    assert module.run_audit_from_console(state) == 0
    assert "run" in calls
    assert state.operation == "LOCAL:COST_CONFIRMED"
    assert module._post_run_actions(state) is True
    assert "post" in calls


def test_cost_confirmation_is_silent_without_monetary_forecast(monkeypatch) -> None:
    calls: list[str] = []
    module = _module(calls)
    monkeypatch.setattr(
        console_cost_confirmation,
        "forecast_local_cost",
        lambda state: CostForecast(False, False, source="test"),
    )
    install(module)
    state = SimpleNamespace(status="READY", operation="", error="")

    assert module.run_audit_from_console(state) == 0
    assert calls == ["run"]


def test_post_run_cost_at_or_below_expected_is_green_semantics() -> None:
    outcome = console_cost_confirmation._evaluate_cost_outcome(
        _forecast(), costs=(("USD", 0.11),), unpriced_ai_attempts=0, actual_pages=3
    )
    assert outcome.comparable is True
    assert outcome.status == "DENTRO DO ESPERADO"
    assert outcome.deviation_percent is not None and outcome.deviation_percent < 0


def test_post_run_cost_up_to_five_percent_above_expected_is_alert() -> None:
    outcome = console_cost_confirmation._evaluate_cost_outcome(
        _forecast(), costs=(("USD", 0.126),), unpriced_ai_attempts=0, actual_pages=3
    )
    assert outcome.comparable is True
    assert outcome.status == "ALERTA"
    assert outcome.deviation_percent is not None
    assert round(outcome.deviation_percent, 8) == 5.0


def test_post_run_cost_more_than_five_percent_above_expected_is_critical() -> None:
    outcome = console_cost_confirmation._evaluate_cost_outcome(
        _forecast(), costs=(("USD", 0.12612),), unpriced_ai_attempts=0, actual_pages=3
    )
    assert outcome.comparable is True
    assert outcome.status == "CRÍTICO"
    assert outcome.deviation_percent is not None and outcome.deviation_percent > 5


def test_post_run_cost_with_unpriced_attempt_is_not_falsely_classified() -> None:
    outcome = console_cost_confirmation._evaluate_cost_outcome(
        _forecast(), costs=(("USD", 0.10),), unpriced_ai_attempts=1, actual_pages=3
    )
    assert outcome.comparable is False
    assert outcome.status == "NÃO COMPARÁVEL"
    assert outcome.actual == 0.10
    assert outcome.deviation_percent is None
