"""Regression contracts for the task-oriented local console navigation."""
from __future__ import annotations

import builtins
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from types import ModuleType, SimpleNamespace

import rasai.console_navigation as navigation
from rasai.console_navigation import _audit_directories, install


def _console() -> ModuleType:
    module = ModuleType("test_console_navigation_fake")
    module.render_header = lambda state: None
    module._menu = lambda state: builtins.input("Escolha: ").strip().upper()
    return module


def _state(tmp_path: Path | None = None):
    return SimpleNamespace(
        project="Projeto",
        target="https://example.com/",
        audit_id="",
        audits_root=str(tmp_path or Path("audits")),
        error="",
    )


def test_navigation_keeps_complete_existing_dashboard_reachable(monkeypatch) -> None:
    console = _console()
    install(console)
    answers = iter(["1", "R"])
    monkeypatch.setattr(builtins, "input", lambda prompt="": next(answers))

    assert console._menu(_state()) == "R"


def test_preparation_context_survives_actions_until_explicit_back(monkeypatch) -> None:
    console = _console()
    install(console)
    state = _state()

    answers = iter(["1", "S"])
    monkeypatch.setattr(builtins, "input", lambda prompt="": next(answers))
    with redirect_stdout(StringIO()) as first_output:
        assert console._menu(state) == "S"
    assert "V. Voltar ao início" in first_output.getvalue()

    answers = iter(["E"])
    monkeypatch.setattr(builtins, "input", lambda prompt="": next(answers))
    with redirect_stdout(StringIO()) as second_output:
        assert console._menu(state) == "E"
    assert "INÍCIO\n" not in second_output.getvalue()
    assert "V. Voltar ao início" in second_output.getvalue()

    answers = iter(["V", "3"])
    monkeypatch.setattr(builtins, "input", lambda prompt="": next(answers))
    with redirect_stdout(StringIO()) as third_output:
        assert console._menu(state) == "C"
    assert "INÍCIO\n" in third_output.getvalue()


def test_history_configuration_reuse_hands_off_to_preparation(monkeypatch) -> None:
    console = _console()
    install(console)
    state = _state()
    monkeypatch.setattr(navigation, "_audit_history", lambda console_module, current_state: True)
    answers = iter(["2", "R"])
    monkeypatch.setattr(builtins, "input", lambda prompt="": next(answers))

    with redirect_stdout(StringIO()) as output:
        assert console._menu(state) == "R"

    assert "V. Voltar ao início" in output.getvalue()


def test_navigation_routes_existing_global_actions_without_reimplementing_them(monkeypatch) -> None:
    routes = {"3": "C", "4": "E", "5": "D", "?": "H", "Q": "Q"}
    for selected, expected in routes.items():
        console = _console()
        install(console)
        answers = iter([selected])
        monkeypatch.setattr(builtins, "input", lambda prompt="", answers=answers: next(answers))
        assert console._menu(_state()) == expected


def test_audit_history_discovers_only_aud_workspaces_with_database(tmp_path: Path) -> None:
    first = tmp_path / "AUD-FIRST"
    second = tmp_path / "AUD-SECOND"
    ignored = tmp_path / "OTHER"
    first.mkdir()
    second.mkdir()
    ignored.mkdir()
    (first / "audit.db").write_bytes(b"")
    (second / "audit.db").write_bytes(b"")
    (ignored / "audit.db").write_bytes(b"")

    discovered = {item.name for item in _audit_directories(tmp_path)}

    assert discovered == {"AUD-FIRST", "AUD-SECOND"}
