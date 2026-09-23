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
