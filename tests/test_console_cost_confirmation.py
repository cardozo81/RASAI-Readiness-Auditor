from __future__ import annotations

import sqlite3
from contextlib import redirect_stdout
from io import StringIO
from types import ModuleType, SimpleNamespace

from rasai import console_catalog_plan
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


def test_financial_screen_exposes_execution_modes_without_redundant_confirmation(monkeypatch) -> None:
    output = StringIO()
    monkeypatch.setattr("builtins.input", lambda prompt="": "V")
    with redirect_stdout(output):
        action = console_cost_confirmation._financial_execution_action(
            SimpleNamespace(), ModuleType("financial_actions_console")
        )

    rendered = output.getvalue()
    assert action == "V"
    assert "1. Executar auditoria com IA" in rendered
    assert "2. Executar auditoria sem IA" in rendered
    assert "Confirmar e executar" not in rendered
    assert "A. Ajustar configuração de IA" in rendered
    assert "V. Voltar sem executar" in rendered
    assert "Escolha:" not in rendered  # prompt belongs to input(), not duplicated by print



def test_financial_mode_numbers_map_directly_to_execution(monkeypatch) -> None:
    module = ModuleType("financial_mode_console")
    state = SimpleNamespace()
    answers = iter(("1", "2"))
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))
    assert console_cost_confirmation._financial_execution_action(state, module) == "C"
    assert console_cost_confirmation._financial_execution_action(state, module) == "N"

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


def test_cost_confirmation_can_execute_current_audit_without_ai_and_restore_plan(monkeypatch) -> None:
    observed: list[bool] = []
    module = ModuleType("cost_confirmation_no_ai_test_console")
    module.render_header = lambda state: None
    module._post_run_actions = lambda state: True
    module.run_audit_from_console = (
        lambda state: observed.append(console_catalog_plan.ai_execution_enabled(state)) or 0
    )
    monkeypatch.setattr(console_cost_confirmation, "forecast_local_cost", lambda state: _forecast())
    monkeypatch.setattr("builtins.input", lambda prompt="": "N")
    install(module)
    state = SimpleNamespace(status="READY", operation="", error="")
    console_catalog_plan.set_selected_catalog_ids(state, ["CAT-03"])
    console_catalog_plan.set_ai_execution_enabled(state, True)

    assert module.run_audit_from_console(state) == 0
    assert observed == [False]
    assert console_catalog_plan.ai_execution_enabled(state) is True
    assert state.operation == "LOCAL:COST_CONFIRMED_NO_AI"


def test_cost_confirmation_reconfigures_ai_then_recalculates_before_confirmation(monkeypatch) -> None:
    calls: list[str] = []
    module = _module(calls)
    forecasts = [_forecast(), _forecast()]
    monkeypatch.setattr(
        console_cost_confirmation,
        "forecast_local_cost",
        lambda state: forecasts.pop(0),
    )
    from rasai import ai_provider_console_management as provider_management
    configured: list[bool] = []
    monkeypatch.setattr(
        provider_management,
        "configure_ai_from_shortcut",
        lambda state, console: configured.append(True),
    )
    answers = iter(("A", "C"))
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))
    install(module)
    state = SimpleNamespace(status="READY", operation="", error="")

    assert module.run_audit_from_console(state) == 0
    assert configured == [True]
    assert calls.count("header") == 2
    assert "run" in calls


def test_no_forecast_requires_explicit_final_authorization_before_external_audit(monkeypatch) -> None:
    calls: list[str] = []
    module = _module(calls)
    monkeypatch.setattr(
        console_cost_confirmation, "forecast_local_cost",
        lambda state: CostForecast(False, False, source="test"),
    )
    prompts = []
    monkeypatch.setattr("builtins.input", lambda prompt="": (prompts.append(prompt), "C")[1])
    install(module)
    state = SimpleNamespace(
        status="READY", operation="", error="", target="https://example.org",
        device="mobile", synthetic_apdex=True, apdex_experience=True,
    )
    output = StringIO()
    with redirect_stdout(output):
        assert module.run_audit_from_console(state) == 0
    assert calls.count("run") == 1
    assert state.operation == "LOCAL:EXECUTION_CONFIRMED"
    assert prompts == ["Escolha [C/V]: "]
    assert "CONFIRMAÇÃO FINAL ANTES DA AUDITORIA" in output.getvalue()
    assert "Sem previsão financeira confirmável" in output.getvalue()
    assert "Apdex experiência" in output.getvalue()


def test_no_forecast_enter_is_safe_cancel_and_preserves_state(monkeypatch) -> None:
    calls = []
    module = _module(calls)
    monkeypatch.setattr(
        console_cost_confirmation, "forecast_local_cost",
        lambda state: CostForecast(False, False, source="test"),
    )
    monkeypatch.setattr("builtins.input", lambda prompt="": "")
    install(module)
    state = SimpleNamespace(
        status="READY", operation="", error="old", target="https://example.org",
        device="mobile", synthetic_apdex=True, apdex_experience=True,
    )
    assert module.run_audit_from_console(state) == 0
    assert "run" not in calls
    assert state.status == "READY"
    assert state.operation == "LOCAL:EXECUTION_DECLINED"
    assert state.error == ""
    assert module._post_run_actions(state) is False
    assert "post" not in calls


def test_no_forecast_v_cancels_without_calling_engine(monkeypatch) -> None:
    calls = []
    module = _module(calls)
    monkeypatch.setattr(
        console_cost_confirmation, "forecast_local_cost",
        lambda state: CostForecast(False, False, source="test"),
    )
    monkeypatch.setattr("builtins.input", lambda prompt="": "V")
    install(module)
    state = SimpleNamespace(status="READY", operation="", error="")
    assert module.run_audit_from_console(state) == 0
    assert "run" not in calls
    assert state.operation == "LOCAL:EXECUTION_DECLINED"
    assert module._post_run_actions(state) is False


def test_no_forecast_invalid_choice_cannot_accidentally_start(monkeypatch) -> None:
    calls = []
    module = _module(calls)
    monkeypatch.setattr(
        console_cost_confirmation, "forecast_local_cost",
        lambda state: CostForecast(False, False, source="test"),
    )
    answers = iter(("R", "Y", "V"))
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))
    install(module)
    state = SimpleNamespace(status="READY", operation="", error="")
    assert module.run_audit_from_console(state) == 0
    assert "run" not in calls
    assert state.operation == "LOCAL:EXECUTION_DECLINED"
    assert module._post_run_actions(state) is False


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


def test_post_run_zero_cost_without_ai_success_is_not_within_expected() -> None:
    outcome = console_cost_confirmation._evaluate_cost_outcome(
        _forecast(),
        costs=(),
        unpriced_ai_attempts=0,
        actual_pages=3,
        ai_attempts=1,
        ai_successes=0,
        ai_failure_context="OPENAI/gpt-test; NETWORK; code=CONNECT_ERROR",
    )
    assert outcome.comparable is False
    assert outcome.status == "NÃO CONSUMIDO"
    assert outcome.actual == 0.0
    assert outcome.deviation is None
    assert outcome.deviation_percent is None
    notes = " ".join(outcome.notes)
    assert "1 tentativa(s)" in notes
    assert "Motivo técnico registrado" in notes
    assert "NETWORK" in notes
    assert "não representa aderência" in notes


def test_post_run_without_materialized_ai_attempt_is_not_within_expected() -> None:
    outcome = console_cost_confirmation._evaluate_cost_outcome(
        _forecast(),
        costs=(),
        unpriced_ai_attempts=0,
        actual_pages=3,
        ai_attempts=0,
        ai_successes=0,
    )
    assert outcome.comparable is False
    assert outcome.status == "NÃO CONSUMIDO"
    assert outcome.actual == 0.0
    assert "nenhuma tentativa" in " ".join(outcome.notes)


def test_latest_ai_failure_context_reuses_persisted_diagnostic(tmp_path) -> None:
    database = tmp_path / "audit.db"
    connection = sqlite3.connect(database)
    try:
        connection.execute(
            """
            CREATE TABLE ai_provider_attempts (
                provider TEXT,
                model TEXT,
                status TEXT,
                http_status INTEGER,
                error_class TEXT,
                error_type TEXT,
                error_code TEXT,
                started_at TEXT
            )
            """
        )
        connection.execute(
            """
            INSERT INTO ai_provider_attempts VALUES (?,?,?,?,?,?,?,?)
            """,
            (
                "OPENAI",
                "gpt-test",
                "FAILED",
                503,
                "NETWORK",
                "ConnectError",
                "CONNECT_ERROR",
                "2026-09-15T12:00:00+00:00",
            ),
        )
        connection.commit()
    finally:
        connection.close()

    context = console_cost_confirmation._latest_ai_failure_context(tmp_path)
    assert context == "OPENAI/gpt-test; Erro de rede; motivo=Erro de conexão; HTTP 503"
    assert "NETWORK" not in context
    assert "CONNECT_ERROR" not in context



def test_usage_refreshes_cached_cost_outcome_after_reprocess(monkeypatch) -> None:
    calls: list[str] = []
    module = ModuleType("cost_confirmation_refresh_after_rpr")
    module.render_header = lambda state: None
    module.run_audit_from_console = lambda state: 0
    module._post_run_actions = lambda state: True
    module._render_actual_usage = lambda state: calls.append("base-usage")

    install(module)
    state = SimpleNamespace(audit_id="AUD-RPR", audits_root="audits")
    forecast = _forecast()
    stale = console_cost_confirmation._CostOutcome(
        comparable=False,
        currency="USD",
        expected=forecast.expected,
        actual=0.0,
        deviation=None,
        deviation_percent=None,
        status="NÃO COMPARÁVEL",
        relation="execução obrigatória incompleta; custo observado é apenas parcial",
        forecast_pages=forecast.target_pages,
        actual_pages=1,
        unpriced_ai_attempts=0,
        notes=("3 requisito(s) obrigatório(s) permanece(m) incompleto(s)",),
    )
    refreshed = console_cost_confirmation._CostOutcome(
        comparable=True,
        currency="USD",
        expected=forecast.expected,
        actual=0.04263060,
        deviation=0.04263060 - float(forecast.expected or 0.0),
        deviation_percent=-64.4745,
        status="DENTRO DO ESPERADO",
        relation="dentro da faixa provável histórica",
        forecast_pages=forecast.target_pages,
        actual_pages=1,
        unpriced_ai_attempts=0,
        notes=("fulfillment finalizado após RPR",),
    )

    console_cost_confirmation._FORECASTS[id(state)] = forecast
    console_cost_confirmation._OUTCOMES[id(state)] = stale
    rendered: list[console_cost_confirmation._CostOutcome] = []
    persisted: list[console_cost_confirmation._CostOutcome] = []
    finalized: list[str] = []
    from rasai import execution_adherence_refinement

    monkeypatch.setattr(console_cost_confirmation, "_build_outcome", lambda *_args: refreshed)
    monkeypatch.setattr(
        console_cost_confirmation,
        "_persisted_outcome_matches",
        lambda *_args: False,
    )
    monkeypatch.setattr(
        console_cost_confirmation,
        "_persist_outcome",
        lambda _state, _forecast_value, outcome: persisted.append(outcome) or True,
    )
    monkeypatch.setattr(
        execution_adherence_refinement,
        "finalize_catalog_projection",
        lambda current_state: finalized.append(current_state.audit_id),
    )
    monkeypatch.setattr(
        console_cost_confirmation,
        "_render_outcome",
        lambda _forecast_value, outcome: rendered.append(outcome),
    )
    try:
        module._render_actual_usage(state)
    finally:
        console_cost_confirmation._FORECASTS.pop(id(state), None)
        console_cost_confirmation._OUTCOMES.pop(id(state), None)

    assert calls == ["base-usage"]
    assert persisted == [refreshed]
    assert finalized == ["AUD-RPR"]
    assert rendered == [refreshed]
    assert rendered[0].actual == 0.04263060
    assert "incompleto" not in " ".join(rendered[0].notes).casefold()


def test_persisted_cost_match_ignores_evaluated_at_only(monkeypatch, tmp_path) -> None:
    state = SimpleNamespace(audit_id="AUD-152")
    forecast = _forecast()
    outcome = console_cost_confirmation._evaluate_cost_outcome(
        forecast,
        costs=(("USD", 0.11),),
        unpriced_ai_attempts=0,
        actual_pages=3,
    )
    database = tmp_path / "audit.db"
    sqlite3.connect(database).close()
    monkeypatch.setattr(
        console_cost_confirmation,
        "artifact_status",
        lambda _state: (tmp_path, None),
    )

    assert console_cost_confirmation._persist_outcome(state, forecast, outcome) is True
    connection = sqlite3.connect(database)
    try:
        connection.execute(
            """
            UPDATE console_cost_forecast_outcomes
            SET evaluated_at=?
            WHERE audit_id=?
            """,
            ("2099-01-01T00:00:00+00:00", state.audit_id),
        )
        connection.commit()
    finally:
        connection.close()

    assert console_cost_confirmation._persisted_outcome_matches(
        state,
        forecast,
        outcome,
    ) is True


def test_usage_does_not_rewrite_matching_persisted_cost_outcome(monkeypatch) -> None:
    calls: list[str] = []
    module = ModuleType("cost_confirmation_noop_after_final_report")
    module.render_header = lambda state: None
    module.run_audit_from_console = lambda state: 0
    module._post_run_actions = lambda state: True
    module._render_actual_usage = lambda state: calls.append("base-usage")

    install(module)
    state = SimpleNamespace(audit_id="AUD-152", audits_root="audits")
    forecast = _forecast()
    refreshed = console_cost_confirmation._evaluate_cost_outcome(
        forecast,
        costs=(("USD", 0.11),),
        unpriced_ai_attempts=0,
        actual_pages=3,
    )
    console_cost_confirmation._FORECASTS[id(state)] = forecast
    console_cost_confirmation._OUTCOMES[id(state)] = refreshed

    persisted: list[str] = []
    finalized: list[str] = []
    rendered: list[console_cost_confirmation._CostOutcome] = []
    from rasai import execution_adherence_refinement

    monkeypatch.setattr(console_cost_confirmation, "_build_outcome", lambda *_args: refreshed)
    monkeypatch.setattr(
        console_cost_confirmation,
        "_persisted_outcome_matches",
        lambda *_args: True,
    )
    monkeypatch.setattr(
        console_cost_confirmation,
        "_persist_outcome",
        lambda *_args: persisted.append("persist") or True,
    )
    monkeypatch.setattr(
        execution_adherence_refinement,
        "finalize_catalog_projection",
        lambda current_state: finalized.append(current_state.audit_id),
    )
    monkeypatch.setattr(
        console_cost_confirmation,
        "_render_outcome",
        lambda _forecast_value, outcome: rendered.append(outcome),
    )
    try:
        module._render_actual_usage(state)
    finally:
        console_cost_confirmation._FORECASTS.pop(id(state), None)
        console_cost_confirmation._OUTCOMES.pop(id(state), None)

    assert calls == ["base-usage"]
    assert persisted == []
    assert finalized == []
    assert rendered == [refreshed]
