from __future__ import annotations

from types import ModuleType, SimpleNamespace

from rasai import console_catalog_plan
from rasai import console_first_run_cost_preview
from rasai.console_cost import ExposureEstimate
from rasai.cost_forecast import CostForecast


def _module(calls: list[str]) -> ModuleType:
    module = ModuleType("first_run_cost_preview_test_console")
    module.render_header = lambda state: calls.append("header")
    module.run_audit_from_console = lambda state: calls.append("run") or 0
    module._post_run_actions = lambda state: calls.append("post") or True
    return module


def _exposure(ai_attempts: int) -> ExposureEstimate:
    return ExposureEstimate(
        level="MÉDIO" if ai_attempts else "NENHUM",
        min_pages=1,
        max_pages=1,
        device_contexts=1,
        min_ai_attempts=1 if ai_attempts else 0,
        max_ai_attempts=ai_attempts,
        min_web_calls=0,
        max_web_calls=0,
        pricing_lines=("OPENAI/test: input USD 1/1M tokens; cache USD 0/1M; output USD 2/1M; contexto tarifário padrão.",) if ai_attempts else (),
        reasons=(),
    )


def test_first_ai_run_requires_acknowledgement_without_historical_total(monkeypatch) -> None:
    calls: list[str] = []
    module = _module(calls)
    monkeypatch.setattr(
        console_first_run_cost_preview,
        "forecast_local_cost",
        lambda state: CostForecast(False, False, source="test", notes=("sem histórico",)),
    )
    monkeypatch.setattr(console_first_run_cost_preview, "estimate_exposure", lambda state: _exposure(3))
    monkeypatch.setattr("builtins.input", lambda prompt="": "C")
    console_first_run_cost_preview.install(module)
    state = SimpleNamespace(status="READY", operation="", error="")

    assert module.run_audit_from_console(state) == 0
    assert calls == ["header", "run"]
    assert state.operation == "LOCAL:COST_EXPOSURE_CONFIRMED"


def test_first_ai_run_can_execute_without_ai_for_only_current_audit(monkeypatch) -> None:
    observed: list[bool] = []
    module = ModuleType("first_run_no_ai_test_console")
    module.render_header = lambda state: None
    module._post_run_actions = lambda state: True
    module.run_audit_from_console = (
        lambda state: observed.append(console_catalog_plan.ai_execution_enabled(state)) or 0
    )
    monkeypatch.setattr(
        console_first_run_cost_preview,
        "forecast_local_cost",
        lambda state: CostForecast(False, False, source="test"),
    )
    monkeypatch.setattr(console_first_run_cost_preview, "estimate_exposure", lambda state: _exposure(2))
    monkeypatch.setattr("builtins.input", lambda prompt="": "N")
    console_first_run_cost_preview.install(module)
    state = SimpleNamespace(status="READY", operation="", error="")
    console_catalog_plan.set_selected_catalog_ids(state, ["CAT-03"])
    console_catalog_plan.set_ai_execution_enabled(state, True)

    assert module.run_audit_from_console(state) == 0
    assert observed == [False]
    assert console_catalog_plan.ai_execution_enabled(state) is True
    assert state.operation == "LOCAL:COST_EXPOSURE_CONFIRMED_NO_AI"


def test_first_ai_run_can_be_declined_without_false_post_run(monkeypatch) -> None:
    calls: list[str] = []
    module = _module(calls)
    monkeypatch.setattr(
        console_first_run_cost_preview,
        "forecast_local_cost",
        lambda state: CostForecast(False, False, source="test"),
    )
    monkeypatch.setattr(console_first_run_cost_preview, "estimate_exposure", lambda state: _exposure(2))
    monkeypatch.setattr("builtins.input", lambda prompt="": "V")
    console_first_run_cost_preview.install(module)
    state = SimpleNamespace(status="READY", operation="", error="")

    assert module.run_audit_from_console(state) == 0
    assert "run" not in calls
    assert module._post_run_actions(state) is False
    assert "post" not in calls


def test_no_ai_exposure_keeps_existing_silent_path(monkeypatch) -> None:
    calls: list[str] = []
    module = _module(calls)
    monkeypatch.setattr(
        console_first_run_cost_preview,
        "forecast_local_cost",
        lambda state: CostForecast(False, False, source="test"),
    )
    monkeypatch.setattr(console_first_run_cost_preview, "estimate_exposure", lambda state: _exposure(0))
    console_first_run_cost_preview.install(module)
    state = SimpleNamespace(status="READY", operation="", error="")

    assert module.run_audit_from_console(state) == 0
    assert calls == ["run"]
