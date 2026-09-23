from __future__ import annotations

from datetime import date
import inspect
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from rasai.audit_management import AuditInventoryFilter
import rasai.audit_management_console as audit_management_console
import rasai.console_apdex_configuration as apdex_console
from rasai.console_input_contract import (
    EditCancelled,
    prompt_text,
    prompt_yes_no,
)
from rasai.console_m23 import State
import rasai.console_reprocess_final_refinements as reprocess_final
import rasai.console_navigation as navigation
import rasai.console_runtime as console_runtime
import rasai.console_usability_refinements as usability
import rasai.consolidation.console as consolidated_console


def test_text_prompt_identifies_field_current_value_and_cancel_action() -> None:
    prompts: list[str] = []

    def answer(prompt: str) -> str:
        prompts.append(prompt)
        return "V"

    with pytest.raises(EditCancelled):
        prompt_text("Idioma da auditoria", current="pt-BR", input_fn=answer)

    assert prompts == ["Idioma da auditoria [pt-BR] [V=voltar sem salvar]: "]


def test_yes_no_prompt_can_cancel_without_returning_a_new_value() -> None:
    prompts: list[str] = []

    with pytest.raises(EditCancelled):
        prompt_yes_no(
            "Habilitar Web Performance",
            True,
            input_fn=lambda prompt: prompts.append(prompt) or "V",
        )

    assert prompts == ["Habilitar Web Performance [S/n] [V=voltar sem salvar]: "]


def test_audit_filter_edit_is_transactional_when_operator_goes_back(monkeypatch) -> None:
    current = AuditInventoryFilter(
        date_from=date(2026, 9, 1),
        date_to=date(2026, 9, 20),
        domain="example.com",
        project="Projeto A",
        status="COMPLETE",
    )
    answers = iter(["2026-09-05", "V"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))

    result = audit_management_console._configure_filters(current)

    assert result == current


def test_apdex_edit_restores_previous_values_when_cancelled_mid_form(monkeypatch) -> None:
    state = State(
        synthetic_apdex=True,
        apdex_threshold=3.0,
        apdex_samples=100,
    )
    original = (
        state.synthetic_apdex,
        state.apdex_threshold,
        state.apdex_samples,
    )
    answers = iter(["", "4", "V"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))

    apdex_console.configure_apdex(state)

    assert (
        state.synthetic_apdex,
        state.apdex_threshold,
        state.apdex_samples,
    ) == original
    assert state.operation == "LOCAL:APDEX_EDIT_CANCELLED"
    assert state.error == ""


def test_reprocess_live_frame_delegates_to_same_runtime_renderer_as_processing(
    monkeypatch,
    tmp_path: Path,
) -> None:
    calls: list[tuple[object, Path | None, str | None]] = []

    def render(state, workspace, *, title=None):
        calls.append((state, workspace, title))

    monkeypatch.setattr(console_runtime, "render_live_audit_context", render)
    state = SimpleNamespace(audit_id="AUD-TEST")

    reprocess_final._render_live_frame(ModuleType("fake_console"), state, tmp_path)

    assert calls == [(state, tmp_path, "REPROCESSAMENTO EM EXECUÇÃO")]


def test_report_and_folder_hotkeys_are_uniform_in_audit_and_consolidated_surfaces() -> None:
    audit_source = inspect.getsource(usability._selected_audit_menu)
    history_source = inspect.getsource(consolidated_console._history)
    generation_source = inspect.getsource(consolidated_console._generate)

    assert "I. Abrir relatório HTML" in audit_source
    assert 'if choice == "I"' in audit_source

    for source in (history_source, generation_source):
        assert "I. Abrir relatório" in source
        assert "P. Abrir pasta" in source
        assert "V. Voltar" in source
        assert "A. Abrir relatório" not in source


def test_primary_navigation_modules_expose_explicit_back_action() -> None:
    root = Path(__file__).resolve().parents[1] / "src" / "rasai"
    paths = (
        root / "console_catalog_ui.py",
        root / "console_ui_catalog.py",
        root / "console_provider_environment.py",
        root / "console_history_presentation.py",
        root / "integration_diagnostics_console.py",
        root / "system_defaults.py",
        root / "audit_management_console.py",
        root / "consolidation" / "console.py",
    )
    for path in paths:
        text = path.read_text(encoding="utf-8")
        assert "V. Voltar" in text, path


def test_audit_id_lookup_uses_b_and_honors_v_without_validation() -> None:
    navigation_source = inspect.getsource(navigation._choose_audit)
    usability_source = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "rasai"
        / "console_usability_refinements.py"
    ).read_text(encoding="utf-8")
    for source in (navigation_source, usability_source):
        assert "B. Buscar por Audit ID" in source
        assert 'Audit ID (AUD-*) [V=voltar]' in source
        assert 'if audit_id == "V"' in source


def test_configuration_editor_uses_local_effective_value_resolver() -> None:
    import rasai.console_configuration_presentation as presentation

    source = inspect.getsource(presentation.variable_editor)
    assert "current=raw_effective_value(spec)" in source
    assert "env.raw_effective_value" not in source
