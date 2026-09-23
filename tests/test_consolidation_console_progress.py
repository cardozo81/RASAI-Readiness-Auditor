from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from types import SimpleNamespace

from rasai.consolidation import console
from rasai.consolidation.selection import AuditCandidate


def test_consolidated_progress_uses_canonical_stage_context(monkeypatch) -> None:
    monkeypatch.setattr(console, "_clear", lambda: None)
    console._CONSOLIDATED_PROGRESS_CONTEXT.clear()
    console._CONSOLIDATED_PROGRESS_CONTEXT.update(
        {
            "selected_count": 5,
            "excluded_count": 9,
            "source_databases": 5,
            "use_ai": False,
        }
    )

    with redirect_stdout(StringIO()) as output:
        console._render_progress(
            "MATERIALIZING",
            "RUNNING",
            "materializando o relatório consolidado",
        )

    rendered = output.getvalue()
    assert "PROGRESSO DO PIPELINE" in rendered
    assert "5 de 6" in rendered
    assert "Anterior" in rendered
    assert "Análise complementar / IA" in rendered
    assert "Atual" in rendered
    assert "Gerando relatório" in rendered
    assert "Próxima" in rendered
    assert "Validação e conclusão" in rendered
    assert "dados/evidências já persistidos" in rendered
    assert "renderizar HTML" in rendered
    assert "Nova coleta da URL" in rendered
    assert "NÃO" in rendered
    assert "Auditorias do conjunto" in rendered
    assert "5" in rendered


def test_candidate_table_matches_audit_history_model_and_colors_eligibility(monkeypatch) -> None:
    values = (
        AuditCandidate(
            audit_id="AUD-ELIGIBLE",
            event_time="2026-09-23T12:00:00+00:00",
            url="https://example.test/a",
            domain="example.test",
            device="MOBILE",
            status="COMPLETED",
            completion_status="COMPLETE",
        ),
        AuditCandidate(
            audit_id="AUD-PARTIAL",
            event_time="2026-09-23T13:00:00+00:00",
            url="https://example.test/a",
            domain="example.test",
            device="MOBILE",
            status="COMPLETED",
            completion_status="COMPLETE_WITH_LIMITATIONS",
        ),
    )
    monkeypatch.setattr(console, "_candidate_status", lambda root, item: (
        ("COMPLETE", "Concluída") if item.audit_id == "AUD-ELIGIBLE"
        else ("PARTIAL_RETRYABLE", "Parcial — pode reprocessar")
    ))
    monkeypatch.setattr(
        console,
        "_candidate_eligible",
        lambda root, item: item.audit_id == "AUD-ELIGIBLE",
    )
    monkeypatch.setattr(console, "_local_timestamp", lambda value: "23/09/2026 09:00")
    monkeypatch.setattr("rasai.console_ui.supports_color", lambda: True)

    with redirect_stdout(StringIO()) as output:
        console._candidate_table(
            values,
            Path("audits"),
            selected_ids=("AUD-ELIGIBLE", "AUD-PARTIAL"),
        )

    rendered = output.getvalue()
    assert "AUDITORIA" in rendered
    assert "DATA/HORA LOCAL" in rendered
    assert "SITUAÇÃO" in rendered
    assert "DISPOSITIVO" in rendered
    assert "ELEGÍVEL" in rendered
    assert "DOMÍNIO" in rendered
    assert "23/09/2026 09:00" in rendered
    assert "\x1b[32m" in rendered  # verde: elegível/selecionado
    assert "\x1b[33m" in rendered  # amarelo: não elegível/selecionado
    assert "SIM" in rendered
    assert "NÃO" in rendered


def test_consolidated_history_uses_local_time_and_equivalent_columns(monkeypatch) -> None:
    item = SimpleNamespace(
        cons_id="CONS-TEST",
        generated_at="2026-09-23T12:00:00+00:00",
        url="https://example.test/a",
        domain="example.test",
        device="MOBILE",
        period_start="2026-09-01T12:00:00+00:00",
        period_end="2026-09-23T12:00:00+00:00",
        audit_ids=("AUD-A", "AUD-B"),
        audit_count=2,
        selection_mode="ALL",
        generation_mode="DETERMINISTIC",
        ai_status="NOT_REQUESTED",
        confidence="Alta",
        report_path=Path("report.html"),
        report_dir=Path("."),
    )
    monkeypatch.setattr(console, "_clear", lambda: None)
    monkeypatch.setattr(console, "list_consolidated_history", lambda root, query="": (item,))
    monkeypatch.setattr(console, "_local_timestamp", lambda value: "23/09/2026 09:00")
    monkeypatch.setattr("builtins.input", lambda prompt="": "V")

    with redirect_stdout(StringIO()) as output:
        console._history(Path("audits"))

    rendered = output.getvalue()
    assert "CONSOLIDADO" in rendered
    assert "GERADO EM" in rendered
    assert "DISPOSITIVO" in rendered
    assert "AUDITORIAS" in rendered
    assert "MODO" in rendered
    assert "CONFIANÇA" in rendered
    assert "DOMÍNIO" in rendered
    assert "23/09/2026 09:00" in rendered
    assert "2026-09-23T12:00:00+00:00" not in rendered


def test_canonical_progress_uses_semantic_colors(monkeypatch) -> None:
    from rasai.execution_progress_presentation import render_canonical_progress

    monkeypatch.setattr("rasai.console_ui.supports_color", lambda: True)
    with redirect_stdout(StringIO()) as output:
        render_canonical_progress(
            current_label="Executando requisitos selecionados",
            current_status="EM EXECUÇÃO",
            stage_index=1,
            stage_count=3,
            previous_label="Preparando reprocessamento",
            next_label="Gerando relatório",
            stage_percent=50.0,
            stage_exact=True,
            overall_percent=20.0,
            overall_exact=False,
            detail_rows=(
                ("Elegíveis conclusivas", "3"),
                ("Não elegíveis", "1"),
                ("Status", "EM EXECUÇÃO"),
            ),
        )

    rendered = output.getvalue()
    assert "\x1b[32m" in rendered  # verde: concluído/elegível
    assert "\x1b[33m" in rendered  # amarelo: em execução/não elegível
    assert "\x1b[90m" in rendered  # cinza: próxima etapa aguardando


def test_consolidated_mode_choice_is_final_action_without_second_confirmation(monkeypatch) -> None:
    selected = SimpleNamespace(
        url="https://example.com/",
        device="MOBILE",
        baseline_audit_id="AUD-BASE",
        current_audit_id="AUD-ATUAL",
        audit_ids=("AUD-BASE", "AUD-ATUAL"),
        selection_mode="ALL",
    )
    recognition = {"discovered": 4, "eligible": 3, "excluded": 2}
    monkeypatch.setattr(console, "_clear", lambda: None)
    monkeypatch.setattr("builtins.input", lambda prompt="": "2")

    with redirect_stdout(StringIO()) as output:
        use_ai = console._choose_ai_mode(
            ai_provider="none",
            ai_available=False,
            ai_unavailable_reason="provider não configurado",
            preview=None,
            selected=selected,
            recognition=recognition,
        )

    assert use_ai is False
    rendered = output.getvalue()
    assert "RESUMO DAS ESCOLHAS" in rendered
    assert "1. Gerar relatório consolidado com IA" in rendered
    assert "2. Gerar relatório consolidado sem IA" in rendered
    assert "Confirmar e gerar relatório consolidado" not in rendered
    assert "C. Confirmar" not in rendered


def test_consolidated_ai_reuse_exposes_zero_new_ai_cost(monkeypatch) -> None:
    selected = SimpleNamespace(
        url="https://example.com/",
        device="MOBILE",
        baseline_audit_id="AUD-BASE",
        current_audit_id="AUD-ATUAL",
        audit_ids=("AUD-BASE", "AUD-ATUAL"),
        selection_mode="ALL",
    )
    recognition = {"discovered": 2, "eligible": 2, "excluded": 0}
    monkeypatch.setattr(console, "_clear", lambda: None)
    monkeypatch.setattr("builtins.input", lambda prompt="": "1")

    with redirect_stdout(StringIO()) as output:
        use_ai = console._choose_ai_mode(
            ai_provider="auto",
            ai_available=True,
            ai_unavailable_reason=None,
            preview=None,
            selected=selected,
            recognition=recognition,
            ai_reusable=True,
        )

    assert use_ai is True
    rendered = output.getvalue()
    assert "consolidado íntegro reutilizável" in rendered
    assert "Nova chamada : NÃO" in rendered
    assert "Custo novo IA: USD 0.000000" in rendered
