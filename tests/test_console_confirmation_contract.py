from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from types import SimpleNamespace

import rasai.audit_management_console as audit_management
from rasai.console_confirmation_contract import confirm_continue, confirm_sensitive
import rasai.console_usability_refinements as usability


def test_simple_confirmation_requires_explicit_c() -> None:
    prompts: list[str] = []

    assert confirm_continue(
        "Confirmar avanço",
        back_label="Voltar sem avançar",
        input_fn=lambda prompt: prompts.append(prompt) or "",
    ) is False

    assert prompts == ["Escolha [C/V]: "]


def test_simple_confirmation_accepts_c_and_rejects_implicit_enter() -> None:
    answers = iter(["x", "C"])
    output = StringIO()
    with redirect_stdout(output):
        assert confirm_continue(
            "Confirmar avanço",
            back_label="Voltar sem avançar",
            input_fn=lambda prompt: next(answers),
        ) is True

    rendered = output.getvalue()
    assert "C. Confirmar avanço" in rendered
    assert "V. Voltar sem avançar" in rendered
    assert "Opção inválida" in rendered


def test_sensitive_confirmation_displays_required_phrase_before_cursor() -> None:
    prompts: list[str] = []
    output = StringIO()
    with redirect_stdout(output):
        result = confirm_sensitive(
            "EXCLUIR TODOS OS AUDS",
            action_label="Excluir permanentemente as auditorias listadas",
            back_label="Voltar sem excluir",
            input_fn=lambda prompt: prompts.append(prompt) or "V",
        )

    assert result is False
    rendered = output.getvalue()
    assert "CONFIRMAÇÃO OBRIGATÓRIA" in rendered
    assert "Digite exatamente: EXCLUIR TODOS OS AUDS" in rendered
    assert "V. Voltar sem excluir" in rendered
    assert prompts == ["Confirmação: "]


def test_sensitive_confirmation_colors_only_required_phrase(monkeypatch) -> None:
    monkeypatch.setattr("rasai.console_ui.supports_color", lambda: True)
    output = StringIO()
    with redirect_stdout(output):
        result = confirm_sensitive(
            "EXCLUIR",
            action_label="Excluir auditorias",
            back_label="Voltar sem excluir",
            input_fn=lambda prompt: "V",
        )

    assert result is False
    rendered = output.getvalue()
    assert "Digite exatamente: " in rendered
    assert "\x1b[1m\x1b[31mEXCLUIR\x1b[0m" in rendered
    assert "\x1b[31mDigite exatamente:" not in rendered


def test_sensitive_confirmation_can_preserve_configuration_surface_colors(monkeypatch) -> None:
    monkeypatch.setattr("rasai.console_ui.supports_color", lambda: True)
    output = StringIO()
    with redirect_stdout(output):
        result = confirm_sensitive(
            "PERSISTIR",
            action_label="Persistir credencial no Windows/User",
            back_label="Voltar sem persistir",
            input_fn=lambda prompt: "V",
            emphasize_phrase=False,
            colorize=False,
        )

    assert result is False
    rendered = output.getvalue()
    assert "Digite exatamente: PERSISTIR" in rendered
    assert "\x1b[31mPERSISTIR" not in rendered
    assert "\x1b[36mCONFIRMAÇÃO OBRIGATÓRIA" not in rendered


def test_sensitive_confirmation_requires_exact_phrase() -> None:
    answers = iter(["EXCLUI", "EXCLUIR"])
    output = StringIO()
    with redirect_stdout(output):
        result = confirm_sensitive(
            "EXCLUIR",
            action_label="Excluir auditorias",
            back_label="Voltar sem excluir",
            input_fn=lambda prompt: next(answers),
        )

    assert result is True
    assert "Confirmação inválida" in output.getvalue()


def test_audit_delete_screen_shows_phrase_and_v_cancels_without_execution(monkeypatch) -> None:
    audit = SimpleNamespace(
        audit_id="AUD-TEST",
        event_time="2026-09-21T10:00:00+00:00",
        created_at="2026-09-21T10:00:00+00:00",
        domains=("example.com",),
    )
    impact = SimpleNamespace(
        audits=(audit,),
        consolidated=(),
        total_bytes=1024,
        series_ids=("SER-1",),
        reusable_configurations=1,
    )
    state = SimpleNamespace(
        audits_root="audits",
        status="",
        operation="",
        error="",
        audit_id="",
    )
    console = SimpleNamespace(render_header=lambda current: None)
    executed: list[bool] = []
    prompts: list[str] = []

    monkeypatch.setattr(audit_management, "plan_deletion", lambda root, ids: impact)
    monkeypatch.setattr(
        audit_management,
        "execute_deletion",
        lambda root, current: executed.append(True),
    )
    monkeypatch.setattr(
        "builtins.input",
        lambda prompt="": prompts.append(prompt) or "V",
    )

    output = StringIO()
    with redirect_stdout(output):
        assert audit_management._delete(
            console,
            state,
            ("AUD-TEST",),
            all_audits=True,
        ) is False

    rendered = output.getvalue()
    assert "IMPACTO DA EXCLUSÃO" in rendered
    assert "Digite exatamente: EXCLUIR TODOS OS AUDS" in rendered
    assert "V. Voltar sem excluir" in rendered
    assert "Confirmação: " in prompts
    assert executed == []
    assert state.status == "AUDIT_DELETION_CANCELLED"


def test_guided_choice_empty_input_does_not_confirm() -> None:
    selected = usability._confirm_choice(
        "desktop",
        "Dispositivo desktop",
        lambda prompt: "",
    )
    assert selected is None


def test_console_confirmation_surfaces_do_not_use_previous_confirmation_patterns() -> None:
    root = Path(__file__).resolve().parents[1] / "src" / "rasai"
    paths = (
        root / "interactive_console.py",
        root / "console_environment.py",
        root / "console_navigation.py",
        root / "console_audit_workflow.py",
        root / "console_execution_profiles.py",
        root / "console_execution_profile_readiness.py",
        root / "console_profile_capability_architecture.py",
        root / "console_usability_refinements.py",
    )
    for current in paths:
        text = current.read_text(encoding="utf-8")
        assert "Digite SIM" not in text, current
        assert "digite REPROCESSAR" not in text, current
        assert "A. Aplicar à sessão" not in text, current

    usability_text = (root / "console_usability_refinements.py").read_text(encoding="utf-8")
    assert 'in {"C", ""}' not in usability_text


def test_sensitive_surfaces_use_shared_phrase_confirmation_contract() -> None:
    root = Path(__file__).resolve().parents[1] / "src" / "rasai"
    expectations = {
        "audit_management_console.py": '"EXCLUIR TODOS OS AUDS"',
        "console_environment_reset.py": '"RESETAR"',
        "system_defaults.py": '"RESTAURAR"',
        "console_environment.py": '"PERSISTIR"',
        "interactive_console.py": '"DESCARTAR"',
    }
    for filename, phrase in expectations.items():
        text = (root / filename).read_text(encoding="utf-8")
        assert "confirm_sensitive(" in text, filename
        assert phrase in text, filename


def test_non_destructive_advance_surfaces_use_shared_c_v_contract() -> None:
    root = Path(__file__).resolve().parents[1] / "src" / "rasai"
    paths = (
        root / "console_navigation.py",
        root / "console_audit_workflow.py",
        root / "console_reprocess_parity.py",
        root / "integration_diagnostics_console.py",
        root / "integration_network_diagnostics.py",
        root / "console_execution_profiles.py",
        root / "console_execution_profile_readiness.py",
        root / "console_profile_capability_architecture.py",
    )
    for current in paths:
        text = current.read_text(encoding="utf-8")
        assert "confirm_continue(" in text, current


def test_mode_choice_surfaces_do_not_reintroduce_redundant_confirmation() -> None:
    root = Path(__file__).resolve().parents[1] / "src" / "rasai"
    paths = (
        root / "console_reprocess_final_refinements.py",
        root / "console_cost_confirmation.py",
        root / "console_first_run_cost_preview.py",
        root / "consolidation" / "console.py",
    )
    for current in paths:
        text = current.read_text(encoding="utf-8")
        assert "C. Confirmar e iniciar reprocessamento" not in text, current
        assert "C. Confirmar e gerar relatório consolidado" not in text, current


def test_simple_confirmation_accepts_c_when_screen_already_rendered_options() -> None:
    output = StringIO()
    with redirect_stdout(output):
        assert confirm_continue(
            "Confirmar avanço",
            back_label="Voltar sem avançar",
            input_fn=lambda prompt: "C",
            show_options=False,
        ) is True

    rendered = output.getvalue()
    assert "C. Confirmar avanço" not in rendered
    assert "V. Voltar sem avançar" not in rendered
