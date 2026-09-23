"""Windows-authoritative presentation contract for selective reprocessing."""
from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from types import ModuleType, SimpleNamespace

import rasai.console_reprocess_parity as parity


def _result() -> SimpleNamespace:
    return SimpleNamespace(
        reprocess_id="RPR-TEST",
        processing_status="PARTIAL_RETRYABLE",
        score_status="PENDING",
        report_status="PRELIMINARY",
        consolidation_eligible=False,
        attempted_items=1,
        successful_items=0,
        skipped_success_items=9,
        remaining_items=1,
        temporal_expired_items=0,
    )


def _usage(*, attempts: int, tokens: int, cost: float) -> SimpleNamespace:
    return SimpleNamespace(
        ai_attempts=attempts,
        ai_successes=max(attempts - 1, 0),
        input_tokens=tokens,
        cached_input_tokens=0,
        output_tokens=0,
        reasoning_tokens=0,
        total_tokens=tokens,
        costs=(("USD", cost),) if cost else (),
        unpriced_ai_attempts=0,
        web_external_calls=0,
        web_services=(),
    )


def test_reprocess_preparation_uses_processing_style_action_surface(monkeypatch, tmp_path: Path) -> None:
    from rasai import console_navigation

    monkeypatch.setattr(
        console_navigation,
        "_safe_summary",
        lambda audit_root, audit_id: {
            "processing_status": "PARTIAL_RETRYABLE",
            "successful_items": 9,
            "required_items": 10,
        },
    )
    console = ModuleType("fake_console")
    console.render_header = lambda state: print("HEADER")
    state = SimpleNamespace(audits_root=str(tmp_path))
    pending = (
        SimpleNamespace(
            component="SEMANTIC_AI",
            scope_key="SNAP-1",
            status="FAILED_RETRYABLE",
            last_error_code="NETWORK",
            last_error_message="NETWORK",
        ),
    )
    successes = tuple(SimpleNamespace() for _ in range(9))

    with redirect_stdout(StringIO()) as output:
        parity.render_reprocess_preparation(console, state, "AUD-TEST", pending, successes)

    rendered = output.getvalue()
    assert "INÍCIO > AUDITORIAS / HISTÓRICO > REPROCESSAR AUDITORIA" in rendered
    assert "PREPARAR REPROCESSAMENTO" in rendered
    assert "9/10 atendidos" in rendered
    assert "Sucessos preservados : 9" in rendered
    assert "SELEÇÃO DE ITENS PARA REPROCESSAMENTO" not in rendered
    assert "PRÓXIMA ETAPA" in rendered
    assert "Confirmar e iniciar reprocessamento" not in rendered
    assert "REPROCESSAR:" not in rendered


def test_item_selection_accepts_t_once_and_clears_previous_error(monkeypatch) -> None:
    pending = (
        SimpleNamespace(component="WEB_PERFORMANCE", scope_key="AUDIT"),
        SimpleNamespace(component="IMPROVEMENT_INTELLIGENCE", scope_key="AUDIT"),
    )
    state = SimpleNamespace(operation="", error="erro anterior")
    prompts: list[str] = []

    def read(prompt=""):
        prompts.append(prompt)
        return "t"

    monkeypatch.setattr("builtins.input", read)
    with redirect_stdout(StringIO()) as output:
        selected = parity._select_reprocess_items(state, pending)

    assert selected == pending
    assert prompts == ["Escolha: "]
    assert state.error == ""
    rendered = output.getvalue()
    assert rendered.count("SELEÇÃO DE ITENS PARA REPROCESSAMENTO") == 1


def test_ai_choice_has_no_phantom_error_and_invalid_message_is_separate(monkeypatch) -> None:
    state = SimpleNamespace(operation="", error="erro anterior")
    answers = iter(("x", ""))
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))

    with redirect_stdout(StringIO()) as output:
        use_ai = parity._choose_reprocess_ai(state)

    assert use_ai is False
    assert state.error == ""
    rendered = output.getvalue()
    assert "COMO EXECUTAR O REPROCESSAMENTO" in rendered
    assert "1. Reprocessar itens selecionados com IA quando aplicável" in rendered
    assert "2. Reprocessar itens selecionados sem IA" in rendered
    assert "\nOpção inválida. Use 1, 2 ou V." in rendered
    assert "ERRO" not in rendered


def test_ai_mode_warns_when_selected_scope_has_no_ai_item(monkeypatch) -> None:
    selected = (
        SimpleNamespace(component="WEB_PERFORMANCE", scope_key="AUDIT", status="FAILED_RETRYABLE"),
    )
    state = SimpleNamespace(
        operation="LOCAL:AUD_REPROCESS",
        error="",
        ai_provider="auto",
        ai_model=None,
    )
    token = parity._RPR_PRESENTATION_CONTEXT.set(("AUD-TEST", 8, selected))
    monkeypatch.setattr("builtins.input", lambda prompt="": "1")
    try:
        with redirect_stdout(StringIO()) as output:
            assert parity._choose_reprocess_ai(state) is True
    finally:
        parity._RPR_PRESENTATION_CONTEXT.reset(token)

    rendered = output.getvalue()
    assert "Itens selecionados com IA: 0" in rendered
    assert "IA não se aplica ao escopo selecionado" in rendered
    assert "pendências não selecionadas não serão incluídas" in rendered
    assert "[sem efeito neste escopo]" in rendered


def test_real_rpr_prompt_sequence_has_one_scope_prompt_and_no_phantom_error(monkeypatch) -> None:
    from rasai.console_operator_ux_consistency import public_output

    pending = (
        SimpleNamespace(component="WEB_PERFORMANCE", scope_key="AUDIT"),
        SimpleNamespace(component="IMPROVEMENT_INTELLIGENCE", scope_key="AUDIT"),
    )
    state = SimpleNamespace(
        audit_id="AUD-TEST",
        operation="LOCAL:AUD_REPROCESS",
        error="erro anterior",
    )
    answers = iter(("t", ""))
    prompts: list[str] = []

    def read(prompt=""):
        prompts.append(prompt)
        return next(answers)

    monkeypatch.setattr("builtins.input", read)
    with redirect_stdout(StringIO()) as output, public_output(state):
        selected = parity._select_reprocess_items(state, pending)
        use_ai = parity._choose_reprocess_ai(state)

    assert selected == pending
    assert use_ai is False
    assert prompts == ["Escolha: ", "Escolha: "]
    rendered = output.getvalue()
    assert rendered.count("SELEÇÃO DE ITENS PARA REPROCESSAMENTO") == 1
    assert rendered.count("COMO EXECUTAR O REPROCESSAMENTO") == 1
    assert "ERRO" not in rendered
    assert state.error == ""



def test_ai_mode_choice_is_final_action_and_preserves_summary(monkeypatch) -> None:
    selected = (
        SimpleNamespace(component="SEMANTIC_AI", scope_key="AUDIT", status="FAILED_RETRYABLE"),
    )
    state = SimpleNamespace(
        operation="LOCAL:AUD_REPROCESS",
        error="",
        ai_provider="auto",
        ai_model=None,
    )
    monkeypatch.setattr("builtins.input", lambda prompt="": "1")
    token = parity._RPR_PRESENTATION_CONTEXT.set(("AUD-TEST", 9, selected))
    try:
        with redirect_stdout(StringIO()) as output:
            assert parity._choose_reprocess_ai(state) is True
    finally:
        parity._RPR_PRESENTATION_CONTEXT.reset(token)

    rendered = output.getvalue()
    assert "RESUMO DAS ESCOLHAS" in rendered
    assert "AUD-TEST" in rendered
    assert "SEMANTIC_AI/AUDIT" in rendered
    assert "Sucessos preservados" in rendered
    assert "1. Reprocessar itens selecionados com IA" in rendered
    assert "Confirmar e iniciar reprocessamento" not in rendered

def test_recursive_rpr_composition_does_not_prompt_scope_twice(monkeypatch) -> None:
    state = SimpleNamespace()
    calls: list[str] = []

    def nested(console_module, current_state, audit_id):
        calls.append(audit_id)
        # Simulate a composed wrapper accidentally routing the same AUD back into the
        # public entry while it is already active.
        parity.reprocess_selected(console_module, current_state, audit_id)

    monkeypatch.setattr(parity, "_reprocess_selected_once", nested)
    parity.reprocess_selected(ModuleType("fake_console"), state, "AUD-TEST")

    assert calls == ["AUD-TEST"]


def test_rpr_ai_prompt_shows_current_auto_session_configuration(monkeypatch) -> None:
    state = SimpleNamespace(
        operation="LOCAL:AUD_REPROCESS",
        error="",
        ai_provider="auto",
        ai_model=None,
    )
    monkeypatch.setattr("builtins.input", lambda prompt="": "")

    with redirect_stdout(StringIO()) as output:
        assert parity._choose_reprocess_ai(state) is False

    rendered = output.getvalue()
    assert "Configuração de IA" in rendered
    assert "AUTO / provider e modelo resolvidos pelo orquestrador" in rendered


def test_invalid_ai_choice_error_is_rendered_on_its_own_line(monkeypatch) -> None:
    from rasai.console_operator_ux_consistency import public_output

    state = SimpleNamespace(operation="LOCAL:AUD_REPROCESS", error="")
    answers = iter(("erro", "n"))
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))

    with redirect_stdout(StringIO()) as output, public_output(state):
        assert parity._choose_reprocess_ai(state) is False

    rendered = output.getvalue()
    assert "Opção inválida. Use 1, 2 ou V." in rendered
    assert "ERRO" in rendered
    assert "\nERRO" in rendered or "\n\033" in rendered
    assert state.error == ""


def test_reprocess_cancel_returns_without_error(monkeypatch) -> None:
    state = SimpleNamespace(operation="", error="erro anterior")
    monkeypatch.setattr("builtins.input", lambda prompt="": "V")

    assert parity._confirm_reprocess(state) is False
    assert state.operation == "LOCAL:AUD_REPROCESS_CANCELLED"
    assert state.error == ""


def test_result_explains_why_item_remained_unresolved() -> None:
    unresolved = (
        SimpleNamespace(
            component="SEMANTIC_AI",
            scope_key="SNAP-1",
            status="WAITING_FOR_DATA",
            last_error_code="MAIN_CONTENT_UNAVAILABLE",
            last_error_message="AI_WAITING_FOR_DATA:MAIN_CONTENT_UNAVAILABLE",
            attempt_count=2,
            retryable=True,
            temporal_mode="REPLAY_SAFE",
            valid_until=None,
        ),
    )

    token = parity._RPR_PRESENTATION_CONTEXT.set(("AUD-TEST", 8, ()))
    try:
        with redirect_stdout(StringIO()) as output:
            parity.render_reprocess_result(_result(), unresolved)
    finally:
        parity._RPR_PRESENTATION_CONTEXT.reset(token)

    rendered = output.getvalue()
    assert "PENDÊNCIAS APÓS O REPROCESSAMENTO" in rendered
    assert "SEMANTIC_AI/SNAP-1" in rendered
    assert "NÃO SELECIONADO" in rendered
    assert "Motivo persistido" in rendered
    assert "WAITING_FOR_DATA" in rendered
    assert "MAIN_CONTENT_UNAVAILABLE" in rendered
    assert "pré-requisito" in rendered


def test_result_marks_selected_unresolved_item_as_selected() -> None:
    item = SimpleNamespace(
        component="IMPROVEMENT_INTELLIGENCE",
        scope_key="AUDIT",
        status="REQUESTED_NOT_EXECUTED",
        last_error_code="AI_NOT_AUTHORIZED_FOR_EXECUTION",
        last_error_message="estado persistido anterior",
        attempt_count=0,
        retryable=True,
        temporal_mode="REPLAY_SAFE",
        valid_until=None,
    )
    token = parity._RPR_PRESENTATION_CONTEXT.set(("AUD-TEST", 8, (item,)))
    try:
        with redirect_stdout(StringIO()) as output:
            parity.render_reprocess_result(_result(), (item,))
    finally:
        parity._RPR_PRESENTATION_CONTEXT.reset(token)

    rendered = output.getvalue()
    assert "Nesta tentativa     : SELECIONADO" in rendered
    assert "Motivo persistido" not in rendered


def test_live_frame_matches_normal_processing_body_without_inline_cost(tmp_path: Path) -> None:
    console = ModuleType("fake_console")
    console.render_header = lambda state: print("HEADER")
    state = SimpleNamespace(audit_id="AUD-TEST")

    with redirect_stdout(StringIO()) as output:
        parity._render_live_frame(console, state, tmp_path)

    rendered = output.getvalue()
    assert "HEADER" in rendered
    assert "Audit ID    : AUD-TEST" in rendered
    assert "Log técnico:" in rendered
    assert "Custo IA" not in rendered
    assert "REPROCESSAMENTO EM EXECUÇÃO" not in rendered


def test_reprocess_reads_only_new_improvement_progress_events(tmp_path: Path) -> None:
    log = tmp_path / "logs" / "audit.log"
    log.parent.mkdir(parents=True)
    log.write_text(
        '{"event":"IMPROVEMENT_INTELLIGENCE_STAGE","stage":"EVIDENCE","progress_percent":12,"detail":"antigo"}\n',
        encoding="utf-8",
    )
    offset = parity._operational_log_offset(tmp_path)
    with log.open("a", encoding="utf-8") as stream:
        stream.write(
            '{"event":"IMPROVEMENT_INTELLIGENCE_STAGE","stage":"AI_ANALYSIS","progress_percent":80,'
            '"detail":"consultando provider","provider":"openai","model":"gpt-test"}\n'
        )

    new_offset, event = parity._read_new_improvement_progress(tmp_path, offset)

    assert new_offset > offset
    assert event is not None
    assert event["stage"] == "AI_ANALYSIS"
    assert event["progress_percent"] == 80
    rows = dict(parity._ai_progress_rows(event))
    assert rows["Subetapa IA"] == "Consultando provider de IA"
    assert rows["Andamento interno"] == "80% [medido]"
    assert rows["Provider"] == "OPENAI"
    assert rows["Modelo"] == "gpt-test"


def test_live_reprocess_redraw_is_throttled_and_heartbeat_bounded() -> None:
    first = ("1", "0", (), "aguardando provider", "API:AI")
    changed = ("1", "1", (), "provider respondeu", "API:AI")

    assert parity._should_render_live_update(
        signature=first,
        last_signature=None,
        now=0.50,
        last_rendered_at=0.0,
    ) is False
    assert parity._should_render_live_update(
        signature=first,
        last_signature=None,
        now=1.00,
        last_rendered_at=0.0,
    ) is True
    assert parity._should_render_live_update(
        signature=first,
        last_signature=first,
        now=2.00,
        last_rendered_at=1.00,
    ) is False
    assert parity._should_render_live_update(
        signature=changed,
        last_signature=first,
        now=2.00,
        last_rendered_at=1.00,
    ) is True
    assert parity._should_render_live_update(
        signature=first,
        last_signature=first,
        now=6.00,
        last_rendered_at=1.00,
    ) is True


def test_fast_reprocess_renders_progress_before_result_surface(monkeypatch, tmp_path: Path) -> None:
    """A millisecond-fast local retry must still produce a perceivable live frame."""
    from rasai import audit_reprocess, console_cost, console_navigation, console_runtime

    pending = SimpleNamespace(
        component="EXPERIENCE_APDEX",
        scope_key="AUDIT",
        status="FAILED_RETRYABLE",
        attempt_count=1,
        required=True,
    )
    state = SimpleNamespace(
        audits_root=str(tmp_path),
        audit_id="",
        status="READY",
        operation="LOCAL:MENU",
        error="",
        current_url="-",
    )
    console = ModuleType("fake_console")
    rendered_labels: list[str] = []

    monkeypatch.setattr(console_navigation, "_work_item_preview", lambda current_state, audit_id: ((pending,), ()))
    monkeypatch.setattr(parity, "render_reprocess_preparation", lambda *args, **kwargs: None)
    prompt_calls = {"items": 0, "ai": 0}

    def select_once(current_state, items):
        prompt_calls["items"] += 1
        return items

    def choose_ai_once(current_state):
        prompt_calls["ai"] += 1
        return False

    monkeypatch.setattr(parity, "_select_reprocess_items", select_once)
    monkeypatch.setattr(parity, "_choose_reprocess_ai", choose_ai_once)
    monkeypatch.setattr(parity, "_confirm_reprocess", lambda current_state: True)
    monkeypatch.setattr(console_cost, "actual_usage", lambda audit_root: _usage(attempts=0, tokens=0, cost=0.0))
    monkeypatch.setattr(audit_reprocess, "reprocess_audit", lambda *args, **kwargs: _result())
    monkeypatch.setattr(parity, "_audit_primary_url", lambda audit_root: None)
    monkeypatch.setattr(parity, "_pending_items", lambda current_state, audit_id: (pending,))
    monkeypatch.setattr(parity, "_run_post_actions", lambda *args, **kwargs: None)
    monkeypatch.setattr(parity.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(
        parity,
        "_reprocess_live_snapshot",
        lambda audit_root, audit_id, baseline: {"total": 1, "evaluated": 1, "running": ()},
    )
    monkeypatch.setattr(parity, "_reprocess_activity", lambda snapshot: "finalizando requisito local")

    def record_frame(console_module, current_state, audit_root):
        progress = console_runtime.runtime_progress_summary(current_state)
        rendered_labels.append(progress.label if progress is not None else "")

    monkeypatch.setattr(parity, "_render_live_frame", record_frame)

    parity.reprocess_selected(console, state, "AUD-TEST")

    assert prompt_calls == {"items": 1, "ai": 1}
    assert rendered_labels
    assert rendered_labels[0] == "Executando requisitos selecionados"
    assert "Gerando relatório" in rendered_labels
    assert rendered_labels[-1] == "Validação e conclusão"


def test_post_reprocess_uses_standard_post_run_usage_surface() -> None:
    console = ModuleType("fake_console")
    state = SimpleNamespace()

    def normal_usage(current_state):
        print("CONSUMO E COBERTURA REAL PERSISTIDOS")

    console._render_actual_usage = normal_usage

    def post_run(current_state):
        console._render_actual_usage(current_state)
        print("AÇÕES DA AUDITORIA DESTA SESSÃO")
        return False

    console._post_run_actions = post_run

    with redirect_stdout(StringIO()) as output:
        parity._run_post_actions(
            console,
            state,
            result=_result(),
            unresolved=(),
            before_usage=_usage(attempts=1, tokens=100, cost=0.01),
            after_usage=_usage(attempts=2, tokens=160, cost=0.02),
        )

    rendered = output.getvalue()
    assert "RESULTADO DO REPROCESSAMENTO" in rendered
    assert "CONSUMO DESTA TENTATIVA DE REPROCESSAMENTO" in rendered
    assert "Custo IA estimado" in rendered
    assert "CONSUMO E COBERTURA REAL PERSISTIDOS" in rendered
    assert "AÇÕES DA AUDITORIA DESTA SESSÃO" in rendered


def test_entrypoint_installs_parity_after_existing_audit_workflow() -> None:
    import inspect
    import rasai.console_entrypoint as entrypoint

    source = inspect.getsource(entrypoint.main)
    assert source.index("install_console_audit_workflow") < source.index(
        "install_console_reprocess_parity"
    )
