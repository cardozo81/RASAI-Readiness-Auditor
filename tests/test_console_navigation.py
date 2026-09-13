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


def test_selected_audit_menu_marks_missing_snapshot_as_unavailable(monkeypatch, tmp_path: Path) -> None:
    console = _console()
    state = _state(tmp_path)
    reason = "AUD-LEGACY não possui snapshot canônico de configuração reutilizável"
    monkeypatch.setattr(
        navigation,
        "_safe_summary",
        lambda audit_root, audit_id: {
            "processing_status": "COMPLETE",
            "score_status": "FINAL",
            "report_status": "FINAL",
            "consolidation_eligible": True,
            "required_items": 6,
            "successful_items": 6,
            "pending_items": 0,
            "blocked_items": 0,
            "reprocess_count": 0,
            "last_reprocess_id": None,
        },
    )
    monkeypatch.setattr(
        navigation,
        "_configuration_reuse_status",
        lambda current_state, audit_id: (False, reason),
    )
    answers = iter(["2", "V"])
    monkeypatch.setattr(builtins, "input", lambda prompt="": next(answers))

    with redirect_stdout(StringIO()) as output:
        assert navigation._selected_audit_menu(console, state, "AUD-LEGACY") is False

    rendered = output.getvalue()
    assert "Configuração   : INDISPONÍVEL" in rendered
    assert "Carregar esta configuração para uma nova auditoria [INDISPONÍVEL]" in rendered
    assert reason in rendered
    assert state.error == reason
    assert state.operation == "LOCAL:AUD_CONFIG_REUSE"
    assert state.status == "CONFIG_SOURCE_REJECTED"


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
