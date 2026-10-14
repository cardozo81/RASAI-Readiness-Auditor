from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from types import SimpleNamespace

from rasai import console_navigation
from rasai import interactive_console as console


def test_post_run_r_uses_current_audit_id_without_prompting_for_audit(monkeypatch, tmp_path: Path) -> None:
    state = SimpleNamespace(
        audit_id="AUD-CURRENT",
        error="erro residual",
    )
    monkeypatch.setattr(console, "render_header", lambda current_state: print("HEADER"))
    monkeypatch.setattr(
        console,
        "artifact_status",
        lambda current_state: (tmp_path / "AUD-CURRENT", tmp_path / "AUD-CURRENT" / "report-catalog" / "index.html"),
    )
    monkeypatch.setattr(console, "_render_actual_usage", lambda current_state: print("USAGE"))
    monkeypatch.setattr(console, "_render_incomplete_requirements", lambda current_state, workspace: print("PENDING"))
    monkeypatch.setattr(console, "_post_run_reprocessability", lambda current_state, workspace: (2, 2))

    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(
        console_navigation,
        "_reprocess_selected",
        lambda module, current_state, audit_id: calls.append((current_state.audit_id, audit_id)),
    )
    monkeypatch.setattr("builtins.input", lambda prompt="": "R")

    with redirect_stdout(StringIO()) as output:
        result = console._post_run_actions(state)

    assert result is False
    assert calls == [("AUD-CURRENT", "AUD-CURRENT")]
    rendered = output.getvalue()
    assert "R. Reprocessar pendências desta auditoria" in rendered


def test_post_run_complete_audit_does_not_offer_reprocess(monkeypatch, tmp_path: Path) -> None:
    state = SimpleNamespace(audit_id="AUD-COMPLETE", error="")
    monkeypatch.setattr(console, "render_header", lambda current_state: None)
    monkeypatch.setattr(
        console,
        "artifact_status",
        lambda current_state: (tmp_path / "AUD-COMPLETE", Path("report.html")),
    )
    monkeypatch.setattr(console, "_render_actual_usage", lambda current_state: None)
    monkeypatch.setattr(console, "_render_incomplete_requirements", lambda current_state, workspace: None)
    monkeypatch.setattr(console, "_post_run_reprocessability", lambda current_state, workspace: (0, 0))
    monkeypatch.setattr("builtins.input", lambda prompt="": "V")

    with redirect_stdout(StringIO()) as output:
        result = console._post_run_actions(state)

    assert result is False
    assert "Reprocessar pendências desta auditoria" not in output.getvalue()


def _prepare_complete_post_run(monkeypatch, tmp_path: Path):
    state = SimpleNamespace(audit_id="AUD-WINHANDLE", error="", status="COMPLETE")
    actions = []
    monkeypatch.setattr(console, "render_header", lambda current: None)
    monkeypatch.setattr(
        console, "artifact_status",
        lambda current: (tmp_path / "AUD-WINHANDLE", tmp_path / "report.html"),
    )
    monkeypatch.setattr(console, "_render_actual_usage", lambda current: actions.append("usage"))
    monkeypatch.setattr(console, "_render_incomplete_requirements", lambda current, workspace: None)
    monkeypatch.setattr(console, "_post_run_reprocessability", lambda current, workspace: (0, 0))
    monkeypatch.setattr(
        console, "_artifact_action",
        lambda current, choice: actions.append("artifact"),
    )
    return state, actions


def test_post_run_invalid_windows_stdin_exits_cleanly_through_wrapped_scope(
    monkeypatch, tmp_path: Path,
) -> None:
    """WinError 6 at the post-AUD prompt must not turn a finished AUD into exit code 1."""
    import builtins
    from rasai import console_submenu_action_scope as scope

    state, actions = _prepare_complete_post_run(monkeypatch, tmp_path)

    def invalid_handle(prompt=""):
        assert prompt == "Escolha: "
        err = OSError(9, "Invalid handle")
        err.winerror = 6
        raise err

    monkeypatch.setattr(builtins, "input", invalid_handle)
    original_input = builtins.input
    wrapped = scope._wrap_post_run_actions(console._post_run_actions)
    with redirect_stdout(StringIO()) as output:
        assert wrapped(state) is True
    assert builtins.input is original_input
    assert actions == ["usage"]
    assert state.status == "COMPLETE"
    assert state.audit_id == "AUD-WINHANDLE"
    assert "WinError 6" in output.getvalue()
    assert "reabra o console" in output.getvalue()
    assert "Q. Sair" not in output.getvalue()


def test_post_run_unrelated_oserror_is_not_suppressed(
    monkeypatch, tmp_path: Path,
) -> None:
    import pytest

    state, actions = _prepare_complete_post_run(monkeypatch, tmp_path)
    def other_error(prompt=""):
        raise OSError(5, "Unrelated I/O problem")

    monkeypatch.setattr("builtins.input", other_error)
    with pytest.raises(OSError, match="Unrelated I/O problem"):
        console._post_run_actions(state)
    assert actions == ["usage"]


def test_post_run_keyboard_interrupt_is_not_suppressed(
    monkeypatch, tmp_path: Path,
) -> None:
    import pytest

    state, actions = _prepare_complete_post_run(monkeypatch, tmp_path)
    def keyboard_interrupt(prompt=""):
        raise KeyboardInterrupt()

    monkeypatch.setattr("builtins.input", keyboard_interrupt)
    with pytest.raises(KeyboardInterrupt):
        console._post_run_actions(state)
    assert actions == ["usage"]

