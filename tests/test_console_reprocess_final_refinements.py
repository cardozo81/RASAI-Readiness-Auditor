from __future__ import annotations

from contextlib import redirect_stdout
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from types import ModuleType, SimpleNamespace

from rasai.cost_forecast import CostForecast, unavailable_forecast
import rasai.console_reprocess_final_refinements as final
import rasai.console_reprocess_visual_presentation as visual


def _item(component: str, status: str, *, retryable: bool = True, required: bool = True):
    return SimpleNamespace(
        component=component,
        scope_key="AUDIT",
        status=status,
        retryable=retryable,
        required=required,
        last_error_code="ERR" if status != "SUCCESS" else None,
        last_error_message="falha de teste" if status != "SUCCESS" else None,
        attempt_count=1,
        temporal_mode="REPLAY_SAFE",
        valid_until=None,
    )


def test_work_item_preview_excludes_not_applicable_and_disabled(monkeypatch, tmp_path: Path) -> None:
    from rasai import audit_fulfillment, persistence

    items = (
        _item("SEMANTIC_AI", "SUCCESS"),
        _item("TECHNICAL_AI", "FAILED_RETRYABLE"),
        _item("CONTENT_REMEDIATION_AI", "NOT_APPLICABLE"),
        _item("WEB_PERFORMANCE", "DISABLED"),
    )
    monkeypatch.setattr(persistence.AuditWorkspace, "open", staticmethod(lambda path: object()))
    monkeypatch.setattr(audit_fulfillment, "list_work_items", lambda workspace, audit_id: items)
    state = SimpleNamespace(audits_root=str(tmp_path))

    pending, successes = final._work_item_preview(state, "AUD-TEST")

    assert [item.component for item in pending] == ["TECHNICAL_AI"]
    assert [item.component for item in successes] == ["SEMANTIC_AI"]


def test_selective_cost_forecast_scales_only_pending_ai_share() -> None:
    forecast = CostForecast(
        available=True,
        show_confirmation=True,
        currency="USD",
        success_baseline=1.0,
        expected=2.0,
        likely_low=1.5,
        likely_high=2.5,
        potential=3.0,
        sample_runs=8,
        sample_calls=40,
        target_pages=5,
        confidence="MODERADA",
        source="local-audit-history",
        repriced_share=1.0,
        notes=("base",),
    )

    scaled = final._scale_forecast(forecast, pending_ai=2, total_ai=4)

    assert scaled.expected == 1.0
    assert scaled.success_baseline == 0.5
    assert scaled.likely_low == 0.75
    assert scaled.likely_high == 1.25
    assert scaled.potential == 1.5
    assert "2/4" in " ".join(scaled.notes)
    assert scaled.source.endswith(":selective-reprocess")


def test_preparation_shows_compact_ui_cost_preview_before_selection(monkeypatch, tmp_path: Path) -> None:
    from rasai import console_navigation

    monkeypatch.setattr(
        console_navigation,
        "_safe_summary",
        lambda audit_root, audit_id: {
            "processing_status": "PARTIAL_RETRYABLE",
            "successful_items": 4,
            "required_items": 6,
        },
    )
    monkeypatch.setattr(final, "_render_reprocess_cost_preview", lambda state, audit_id, pending: print("CUSTO-SELETIVO"))

    console = ModuleType("fake_console")
    console.render_header = lambda state: print("HEADER")
    state = SimpleNamespace(audits_root=str(tmp_path))
    pending = (_item("TECHNICAL_AI", "FAILED_RETRYABLE"),)
    successes = (_item("SEMANTIC_AI", "SUCCESS"),)

    with redirect_stdout(StringIO()) as output:
        final.render_reprocess_preparation(console, state, "AUD-TEST", pending, successes)

    rendered = output.getvalue()
    assert "PENDÊNCIAS DESTA TENTATIVA" in rendered
    assert "Pendências a tentar" in rendered
    assert "Fora da fila" in rendered
    assert "CUSTO-SELETIVO" in rendered
    assert "PRÓXIMA ETAPA" in rendered
    assert "Selecione os itens que deseja reprocessar" in rendered
    assert "C. Confirmar e iniciar reprocessamento" not in rendered
    assert "V. Voltar sem reprocessar" not in rendered
    assert "REPROCESSAR:" not in rendered


def test_cost_preview_uses_canonical_catalog_fallback_without_history(monkeypatch) -> None:
    from rasai import cost_forecast

    state = SimpleNamespace(audits_root="audits")
    pending = (
        _item("SEMANTIC_AI", "FAILED_RETRYABLE"),
        _item("TECHNICAL_AI", "FAILED_RETRYABLE"),
    )
    source = SimpleNamespace(ai_provider="gemini", ai_model="gemini-test", ai_reasoning=None)
    monkeypatch.setattr(final, "_source_forecast_state", lambda current_state, audit_id: source)
    monkeypatch.setattr(final, "_all_applicable_ai_items", lambda current_state, audit_id: pending)
    monkeypatch.setattr(
        cost_forecast,
        "forecast_local_cost",
        lambda current_state: unavailable_forecast("sem histórico financeiro comparável", source="test"),
    )
    monkeypatch.setattr(
        final,
        "_catalog_fallback_estimate",
        lambda current_state, items: (0.012345, "USD", 14000, 9000, "STANDARD"),
    )

    with redirect_stdout(StringIO()) as output:
        final._render_reprocess_cost_preview(state, "AUD-TEST", pending)

    rendered = output.getvalue()
    assert "PREVISÃO DE CUSTO DE IA" in rendered
    assert "CATÁLOGO / BAIXA CONFIANÇA" in rendered
    assert "USD 0.012345" in rendered
    assert "entrada=14000" in rendered


def test_rpr_cost_preview_uses_current_session_ai_and_preserves_original_aud(monkeypatch) -> None:
    from rasai import cost_forecast

    state = SimpleNamespace(
        audits_root="audits",
        ai_provider="auto",
        ai_model=None,
        ai_reasoning=None,
    )
    pending = (_item("IMPROVEMENT_INTELLIGENCE", "NOT_CONFIGURED"),)
    original = SimpleNamespace(
        ai_provider="none",
        ai_model=None,
        ai_reasoning=None,
        content_remediation=False,
        technical_remediation=False,
        improvement_enabled=True,
        directed_ai_enabled=False,
        device="mobile",
        input_mode="url",
        target="https://example.test/",
        max_pages=1,
        audits_root="audits",
    )
    monkeypatch.setattr(final, "_source_forecast_state", lambda current_state, audit_id: original)
    monkeypatch.setattr(final, "_all_applicable_ai_items", lambda current_state, audit_id: pending)

    observed: list[str] = []

    def fake_forecast(current_state):
        observed.append(current_state.ai_provider)
        return unavailable_forecast("sem histórico comparável", source="test")

    monkeypatch.setattr(cost_forecast, "forecast_local_cost", fake_forecast)
    monkeypatch.setattr(final, "_catalog_fallback_estimate", lambda current_state, items: None)

    with redirect_stdout(StringIO()) as output:
        final._render_reprocess_cost_preview(state, "AUD-TEST", pending)

    rendered = output.getvalue()
    assert observed == ["auto"]
    assert "Configuração original" in rendered
    assert "NONE / <sem chamada de IA>" in rendered
    assert "IA atual da sessão" in rendered
    assert "AUTO / <provider e modelo resolvidos pelo orquestrador>" in rendered
    assert "Política deste RPR" in rendered


def test_web_performance_reprocess_warns_about_conditional_downstream_ai(monkeypatch) -> None:
    pending = (_item("WEB_PERFORMANCE", "FAILED_RETRYABLE"),)
    monkeypatch.setattr(
        final,
        "_source_forecast_state",
        lambda state, audit_id: SimpleNamespace(
            improvement_enabled=True,
            directed_ai_enabled=True,
            content_remediation=True,
            technical_remediation=True,
        ),
    )

    downstream = final._conditional_ai_dependencies(
        SimpleNamespace(audits_root="audits"),
        "AUD-TEST",
        pending,
    )

    assert downstream == (
        "CAT-08 · Análise profunda",
        "Análise Direcionada",
    )

    with redirect_stdout(StringIO()) as output:
        visual._conditional_ai_cost_preview(final, pending, downstream)

    rendered = output.getvalue()
    assert "IA CONDICIONAL" in rendered
    assert "não é possível garantir custo zero" in rendered
    assert "CAT-08" in rendered
    assert "Análise Direcionada" in rendered
    assert "CUSTO ZERO" not in rendered


def test_zero_ai_preview_is_explicit_zero_cost_forecast() -> None:
    pending = (
        _item("EXPERIENCE_APDEX", "FAILED_RETRYABLE"),
        _item("SYNTHETIC_APDEX", "FAILED_RETRYABLE"),
    )

    with redirect_stdout(StringIO()) as output:
        visual._zero_ai_cost_preview(final, pending)

    rendered = output.getvalue()
    assert "PREVISÃO DE CUSTO DE IA" in rendered
    assert "CUSTO ZERO — ESCOPO SEM IA" in rendered
    assert "Chamadas IA previstas" in rendered
    assert "Custo IA previsto" in rendered
    assert "0 (zero)" in rendered
    assert "EXATA PARA O ESCOPO ATUAL" in rendered
    assert "EXPERIENCE_APDEX" in rendered
    assert "SYNTHETIC_APDEX" in rendered
    assert "NÃO APLICÁVEL" not in rendered


def test_mode_choice_starts_reprocess_without_second_confirmation(monkeypatch, tmp_path: Path) -> None:
    from rasai import console_runtime

    @dataclass(slots=True)
    class SlottedState:
        audits_root: str
        audit_id: str = ""
        status: str = "READY"
        operation: str = "LOCAL:MENU"
        error: str = ""

    state = SlottedState(str(tmp_path))
    console = ModuleType("fake_console")
    calls: list[tuple[str, float, dict[str, object]]] = []
    monkeypatch.setattr(
        console_runtime,
        "set_runtime_progress",
        lambda current_state, label, percent, **kwargs: calls.append((label, percent, kwargs)),
    )
    token = final._CURRENT_AUDIT_ID.set("AUD-TEST")
    try:
        with redirect_stdout(StringIO()) as output:
            started = final._confirm_reprocess_with_feedback(console, state)
    finally:
        final._CURRENT_AUDIT_ID.reset(token)

    assert started is True
    assert state.audit_id == "AUD-TEST"
    assert state.status == "REPROCESSING"
    assert state.operation == "LOCAL:AUD_REPROCESS"
    assert len(calls) == 1
    assert calls[0][0:2] == ("Preparando reprocessamento", 0.0)
    assert calls[0][2]["stage_index"] == 1
    assert calls[0][2]["stage_count"] == 3
    rendered = output.getvalue()
    assert "CONFIRMAÇÃO DO REPROCESSAMENTO" not in rendered
    assert "Confirmar e iniciar reprocessamento" not in rendered


def test_post_actions_offer_direct_retry_with_slotted_state(monkeypatch, tmp_path: Path) -> None:
    from rasai import console_artifacts, console_reprocess_parity as parity

    @dataclass(slots=True)
    class SlottedState:
        audits_root: str
        audit_id: str = "AUD-TEST"
        error: str = ""

    console = ModuleType("fake_console")
    console.render_header = lambda state: print("HEADER")
    console._render_actual_usage = lambda state: print("USAGE")
    console._artifact_action = lambda state, action: None
    console._confirm_exit = lambda state: False
    state = SlottedState(str(tmp_path))
    result = SimpleNamespace(
        reprocess_id="RPR-TEST",
        processing_status="PARTIAL_RETRYABLE",
        score_status="PENDING",
        report_status="PRELIMINARY",
        consolidation_eligible=False,
        attempted_items=1,
        successful_items=0,
        skipped_success_items=4,
        remaining_items=1,
        temporal_expired_items=0,
    )
    unresolved = (_item("TECHNICAL_AI", "FAILED_RETRYABLE", retryable=True),)

    monkeypatch.setattr(console_artifacts, "artifact_status", lambda current_state: (tmp_path, tmp_path / "report.html"))
    monkeypatch.setattr(parity, "render_reprocess_result", lambda result, unresolved: print("RESULT"))
    monkeypatch.setattr(parity, "_render_reprocess_usage_delta", lambda before, after: print("DELTA"))
    monkeypatch.setattr("builtins.input", lambda prompt="": "R")

    token = final._REPEAT_REQUESTED.set(False)
    try:
        with redirect_stdout(StringIO()) as output:
            final._run_post_actions(
                console,
                state,
                result=result,
                unresolved=unresolved,
                before_usage=None,
                after_usage=None,
            )

        assert final._REPEAT_REQUESTED.get() is True
    finally:
        final._REPEAT_REQUESTED.reset(token)

    assert not hasattr(state, "__dict__")
    assert "Reprocessar novamente" in output.getvalue()
    assert "CONSUMO ACUMULADO" in output.getvalue()


def test_post_actions_clear_live_progress_when_returning_to_menu(monkeypatch, tmp_path: Path) -> None:
    from rasai import console_artifacts, console_reprocess_parity as parity, console_runtime

    state = SimpleNamespace(
        audits_root=str(tmp_path),
        audit_id="AUD-TEST",
        error="",
        status="PARTIAL_RETRYABLE",
        operation="LOCAL:DONE",
    )
    console = ModuleType("fake_console")
    console.render_header = lambda current_state: None
    console._render_actual_usage = lambda current_state: None
    console._artifact_action = lambda current_state, action: None
    console._confirm_exit = lambda current_state: False
    result = SimpleNamespace(
        reprocess_id="RPR-TEST",
        processing_status="PARTIAL_RETRYABLE",
        score_status="PENDING",
        report_status="PRELIMINARY",
        consolidation_eligible=False,
        attempted_items=1,
        successful_items=1,
        skipped_success_items=4,
        remaining_items=1,
        temporal_expired_items=0,
    )
    console_runtime.set_runtime_progress(
        state,
        "Validação e conclusão",
        100.0,
        exact=True,
        stage_index=3,
        stage_count=3,
    )
    monkeypatch.setattr(console_artifacts, "artifact_status", lambda current_state: (tmp_path, tmp_path / "report.html"))
    monkeypatch.setattr(parity, "render_reprocess_result", lambda result, unresolved: None)
    monkeypatch.setattr(parity, "_render_reprocess_usage_delta", lambda before, after: None)
    monkeypatch.setattr("builtins.input", lambda prompt="": "V")

    final._run_post_actions(
        console,
        state,
        result=result,
        unresolved=(),
        before_usage=None,
        after_usage=None,
    )

    assert console_runtime.runtime_progress_summary(state) is None
    assert state.operation == "LOCAL:MENU"


def test_reprocess_wrapper_repeats_only_after_explicit_result_action(monkeypatch) -> None:
    from rasai import console_reprocess_parity as parity

    calls: list[int] = []
    state = SimpleNamespace()

    def fake_reprocess(console_module, current_state, audit_id):
        calls.append(len(calls) + 1)
        if len(calls) == 1:
            final._REPEAT_REQUESTED.set(True)

    monkeypatch.setattr(parity, "reprocess_selected", fake_reprocess)
    final._reprocess_selected(ModuleType("fake_console"), state, "AUD-TEST")

    assert calls == [1, 2]
