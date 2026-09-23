from __future__ import annotations

from types import SimpleNamespace

from rasai import execution_commands as commands


def _plan(monkeypatch, tmp_path):
    monkeypatch.setattr(
        commands,
        "_names",
        lambda: ("OPENAI_API_KEY", "RASAI_SERP_MODE", "RASAI_SERP_PROVIDER"),
    )
    monkeypatch.setattr(
        commands,
        "_secret",
        lambda name: name == "OPENAI_API_KEY",
    )
    state = SimpleNamespace(
        ai_provider="none",
        web_performance=False,
        field_source="auto",
        target="https://example.test/",
        device="mobile",
    )
    return commands.audit_plan(
        state,
        env={
            "OPENAI_API_KEY": "sk-RASAI-TEST-DO-NOT-LEAK",
            "RASAI_SERP_MODE": "live",
            "RASAI_SERP_PROVIDER": "serpapi",
        },
        argv=("/venv/python", "-m", "rasai", "audit", "https://example.test/"),
    )


def test_secret_is_placeholder_only_and_never_leaks(monkeypatch, tmp_path) -> None:
    plan = _plan(monkeypatch, tmp_path)

    secret = next(item for item in plan.environment if item.name == "OPENAI_API_KEY")
    assert secret.secret is True
    assert secret.value is None

    rendered = commands.render_log(plan)
    assert "sk-RASAI-TEST-DO-NOT-LEAK" not in rendered
    assert 'REM set "OPENAI_API_KEY=**********"' in rendered
    assert "# export OPENAI_API_KEY='**********'" in rendered
    assert "[WINDOWS]" in rendered
    assert "[LINUX]" in rendered
    assert "[MACOS]" in rendered


def test_copyable_command_omits_secret_placeholders(monkeypatch, tmp_path) -> None:
    plan = _plan(monkeypatch, tmp_path)

    windows = commands.render(plan, "windows")
    copied = commands._copyable_command(windows, "windows")

    assert "**********" not in copied
    assert "OPENAI_API_KEY" not in copied
    assert 'set "RASAI_SERP_MODE=live"' in copied
    assert "rasai" in copied
    assert "audit" in copied


def test_command_log_is_outside_audit_workspace_and_is_human_text(
    monkeypatch, tmp_path
) -> None:
    plan = _plan(monkeypatch, tmp_path)

    path = commands.record(plan, tmp_path, "AUD-TEST", append=False)

    assert path.name == "AUD-TEST.log"
    assert path.parent.name == "execution-commands"
    assert path.is_file()
    assert not (tmp_path / "AUD-TEST").exists()
    text = path.read_text(encoding="utf-8")
    assert text.startswith("=")
    assert "RASAi - LINHA DE COMANDO" in text
    assert "sk-RASAI-TEST-DO-NOT-LEAK" not in text
