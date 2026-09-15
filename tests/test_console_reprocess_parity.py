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
    assert "C. Confirmar e iniciar reprocessamento" in rendered
    assert "V. Voltar sem reprocessar" in rendered
    assert "REPROCESSAR:" not in rendered


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

    with redirect_stdout(StringIO()) as output:
        parity.render_reprocess_result(_result(), unresolved)

    rendered = output.getvalue()
    assert "PENDÊNCIAS APÓS O REPROCESSAMENTO" in rendered
    assert "SEMANTIC_AI/SNAP-1" in rendered
    assert "WAITING_FOR_DATA" in rendered
    assert "MAIN_CONTENT_UNAVAILABLE" in rendered
    assert "pré-requisito" in rendered


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
