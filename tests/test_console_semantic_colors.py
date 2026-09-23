from __future__ import annotations

from pathlib import Path

from rasai.console_ui import (
    GRAY,
    GREEN,
    RED,
    YELLOW,
    semantic_color,
)


def test_semantic_color_contract_for_operational_states() -> None:
    assert semantic_color("CONCLUÍDA") == GREEN
    assert semantic_color("SUCCESS") == GREEN
    assert semantic_color("PARCIAL - pode reprocessar") == YELLOW
    assert semantic_color("EM EXECUÇÃO") == YELLOW
    assert semantic_color("FALHA DEFINITIVA") == RED
    assert semantic_color("INDISPONÍVEL") == RED
    assert semantic_color("NÃO NECESSÁRIO") == GRAY


def test_operational_semantic_helpers_do_not_enter_variable_or_credential_presenters() -> None:
    root = Path(__file__).resolve().parents[1] / "src" / "rasai"
    protected = (
        root / "console_configuration_presentation.py",
        root / "console_ui_catalog.py",
        root / "console_provider_environment.py",
        root / "ai_provider_console_management.py",
        root / "console_environment_reset.py",
    )
    for path in protected:
        text = path.read_text(encoding="utf-8")
        assert "semantic_text" not in text, path
        assert "destructive_text" not in text, path
        assert "title_text" not in text, path
