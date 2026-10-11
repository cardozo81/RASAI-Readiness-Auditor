"""#374: public console first-run and cost wrappers authorize an AUD only once.

All runs are fake functions; no browser, external URL or paid provider is accessed.
"""
from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
from types import ModuleType, SimpleNamespace
import inspect

import pytest

from rasai import console_catalog_plan
from rasai import console_cost_confirmation as cost
from rasai import console_first_run_cost_preview as preview
from rasai import console_entrypoint
from rasai.console_cost import ExposureEstimate
from rasai.cost_forecast import CostForecast


def _forecast(monetary: bool = False) -> CostForecast:
    if not monetary:
        return CostForecast(False, False, source="fixture")
    return CostForecast(
        available=True, show_confirmation=True, currency="USD",
        success_baseline=0.10, expected=0.12, likely_low=0.10,
        likely_high=0.14, potential=0.18, sample_runs=2, sample_calls=4,
        target_pages=1, confidence="MODERADA", source="fixture",
        repriced_share=1.0, notes=(),
    )


def _exposure(attempts: int) -> ExposureEstimate:
    return ExposureEstimate(
        level="MÉDIO" if attempts else "NENHUM",
        min_pages=1, max_pages=1, device_contexts=1,
        min_ai_attempts=1 if attempts else 0, max_ai_attempts=attempts,
        min_web_calls=0, max_web_calls=0, pricing_lines=(), reasons=(),
    )


@pytest.fixture
def composed(monkeypatch):
    calls = []
    console = ModuleType("console_public_run_374")
    console.render_header = lambda state: calls.append("header")
    console.run_audit_from_console = lambda state: calls.append(
        ("run", console_catalog_plan.ai_execution_enabled(state))
    ) or 0
    console._post_run_actions = lambda state: calls.append("post") or True
    monkeypatch.setattr(cost, "forecast_local_cost", lambda state: _forecast())
    monkeypatch.setattr(preview, "forecast_local_cost", lambda state: _forecast())
    monkeypatch.setattr(preview, "estimate_exposure", lambda state: _exposure(0))
    # Same installation order as console_entrypoint.main().
    cost.install(console)
    preview.install(console)
    state = SimpleNamespace(
        status="READY", operation="LOCAL:MENU", error="",
        target="https://example.org", device="mobile",
        synthetic_apdex=True, apdex_experience=True,
    )
    console_catalog_plan.set_selected_catalog_ids(state, ["CAT-03"])
    console_catalog_plan.set_ai_execution_enabled(state, True)
    yield console, state, calls
    # No lingering session-scoped declined state after a fake completion.
    cost._DECLINED.discard(id(state))
    preview._DECLINED.discard(id(state))


def _input(monkeypatch, answers):
    answers = iter(answers)
    prompts = []
    def read(prompt=""):
        prompts.append(prompt)
        return next(answers)
    monkeypatch.setattr("builtins.input", read)
    return prompts


@pytest.mark.parametrize("choice,expected_runs", [
    ("C", 1), ("", 0), ("V", 0),
])
def test_non_monetary_zero_ai_exposure_demands_final_c_v(
    monkeypatch, composed, choice, expected_runs,
):
    console, state, calls = composed
    prompts = _input(monkeypatch, [choice])
    output = StringIO()
    with redirect_stdout(output):
        assert console.run_audit_from_console(state) == 0
    assert sum(isinstance(x, tuple) and x[0] == "run" for x in calls) == expected_runs
    assert prompts == ["Escolha [C/V]: "]
    assert "https://example.org" in output.getvalue()
    assert "MOBILE" in output.getvalue()
    assert "Apdex navegação" in output.getvalue()
    assert "Apdex experiência" in output.getvalue()
    assert "IA no plano" in output.getvalue()
    assert "NÃO significa zero custos" in output.getvalue()
    if expected_runs:
        assert state.operation == "LOCAL:EXECUTION_CONFIRMED"
    else:
        assert state.operation == "LOCAL:EXECUTION_DECLINED"
        assert console._post_run_actions(state) is False


def test_invalid_non_monetary_choice_does_not_authorize(monkeypatch, composed):
    console, state, calls = composed
    prompts = _input(monkeypatch, ["R", "x", "V"])
    output = StringIO()
    with redirect_stdout(output):
        assert console.run_audit_from_console(state) == 0
    assert prompts == ["Escolha [C/V]: "] * 3
    assert "Opção inválida" in output.getvalue()
    assert all(not isinstance(x, tuple) for x in calls)
    assert state.operation == "LOCAL:EXECUTION_DECLINED"


@pytest.mark.parametrize("choice,expected_ai", [("C", True), ("N", False)])
def test_explicit_exposure_choice_is_single_authorization(
    monkeypatch, composed, choice, expected_ai,
):
    console, state, calls = composed
    monkeypatch.setattr(preview, "estimate_exposure", lambda state: _exposure(2))
    prompts = _input(monkeypatch, [choice])
    output = StringIO()
    with redirect_stdout(output):
        assert console.run_audit_from_console(state) == 0
    runs = [x for x in calls if isinstance(x, tuple) and x[0] == "run"]
    assert runs == [("run", expected_ai)]
    assert prompts == ["Escolha: "]
    assert "Escolha [C/V]" not in output.getvalue()
    assert console_catalog_plan.ai_execution_enabled(state) is True


def test_exposure_decline_does_not_enter_inner_audit_gate(monkeypatch, composed):
    console, state, calls = composed
    monkeypatch.setattr(preview, "estimate_exposure", lambda state: _exposure(2))
    prompts = _input(monkeypatch, ["V"])
    assert console.run_audit_from_console(state) == 0
    assert prompts == ["Escolha: "]
    assert "run" not in calls
    assert console._post_run_actions(state) is False
    assert state.operation == "LOCAL:COST_EXPOSURE_DECLINED"


def test_exposure_authorization_is_not_reused_for_next_run(monkeypatch, composed):
    console, state, calls = composed
    monkeypatch.setattr(preview, "estimate_exposure", lambda state: _exposure(2))
    prompts = _input(monkeypatch, ["C", "V"])
    with redirect_stdout(StringIO()):
        assert console.run_audit_from_console(state) == 0
        assert console.run_audit_from_console(state) == 0
    assert prompts == ["Escolha: ", "Escolha: "]
    assert len([x for x in calls if isinstance(x, tuple)]) == 1


def test_monetary_forecast_keeps_single_existing_c_n_a_v_menu(monkeypatch, composed):
    console, state, calls = composed
    monkeypatch.setattr(preview, "forecast_local_cost", lambda state: _forecast(True))
    monkeypatch.setattr(cost, "forecast_local_cost", lambda state: _forecast(True))
    prompts = _input(monkeypatch, ["C"])
    with redirect_stdout(StringIO()):
        assert console.run_audit_from_console(state) == 0
    assert prompts == ["Escolha: "]
    assert [x for x in calls if isinstance(x, tuple)] == [("run", True)]


def test_entrypoint_install_order_preserves_final_gate():
    src = inspect.getsource(console_entrypoint.main)
    assert src.index("install_cost_confirmation(interactive_console)") < src.index(
        "install_first_run_cost_preview(interactive_console)"
    ) < src.index("return interactive_console.main()")
