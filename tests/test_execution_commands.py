from __future__ import annotations

from types import SimpleNamespace
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

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


def test_powershell_log_and_clipboard_preserve_shell_identity(monkeypatch, tmp_path) -> None:
    plan = _plan(monkeypatch, tmp_path)
    output = commands.render_log(plan)
    blocks = commands._blocks(output)
    assert tuple(blocks) == commands.PLATFORMS
    assert "[WINDOWS]\n" in output
    assert "[POWERSHELL]\n" in output
    assert "REM set" in blocks["windows"]
    assert "# $env:OPENAI_API_KEY = '**********'" in blocks["powershell"]
    copy = commands._copyable_command(blocks["powershell"], "powershell")
    assert "$env:RASAI_SERP_MODE = 'live'" in copy
    assert " && " not in copy  # Windows PowerShell 5.1 does not support &&
    assert ";" in copy
    assert "**********" not in copy
    assert "OPENAI_API_KEY" not in copy
    assert "sk-RASAI-TEST-DO-NOT-LEAK" not in output


def test_shells_preserve_specials_and_never_materialize_secrets() -> None:
    argv = ("python", "-m", "rasai", "audit", "https://example.test/?a=1&b=2")
    env = (
        commands.EnvValue("RASAI_SERP_MODE", "live", False),
        commands.EnvValue("OPENAI_API_KEY", None, True),
    )
    plan = commands.CommandPlan("AUDITORIA", argv, env)
    cmd = commands.render(plan, "windows")
    ps = commands.render(plan, "powershell")
    assert '"https://example.test/?a=1&b=2"' in cmd
    assert "& 'python' '-m' 'rasai' 'audit' 'https://example.test/?a=1&b=2'" in ps
    assert 'set "RASAI_SERP_MODE=live"' in cmd
    assert "$env:RASAI_SERP_MODE = 'live'" in ps
    assert "OPENAI_API_KEY=**********" in cmd
    assert "**********" not in commands._copyable_command(cmd, "windows")
    assert "**********" not in commands._copyable_command(ps, "powershell")


def test_legacy_logs_have_no_fabricated_powershell_renderer() -> None:
    old = "[WINDOWS]\nREM Old\npython -m rasai audit AUD-X\n[/WINDOWS]\n[LINUX]\npython3\n[/LINUX]"
    blocks = commands._blocks(old)
    assert blocks["windows"].endswith("AUD-X")
    assert "powershell" not in blocks


def test_cmd_transport_never_serializes_sensitive_environment_values() -> None:
    plan = commands.CommandPlan(
        "AUDITORIA",
        ("python", "-m", "rasai", "audit", "https://example.test/?q=100%&c=1"),
        (
            commands.EnvValue("PUBLIC_VALUE", "%PATH%!~^", False),
            commands.EnvValue("OPENAI_API_KEY", None, True),
        ),
    )
    rendered = commands.render(plan, "windows")
    assert "base64" in rendered
    assert "**********" in rendered  # comment-only, not process environment
    assert "OPENAI_API_KEY" not in commands._copyable_command(rendered, "windows")
    assert "PUBLIC_VALUE" not in commands._copyable_command(rendered, "windows")  # encapsulated
    assert "https://example.test/?q=100%" not in commands._copyable_command(rendered, "windows")
    assert "100%" not in commands._copyable_command(rendered, "windows")


def test_environment_names_fail_closed() -> None:
    plan = commands.CommandPlan(
        "AUDITORIA", ("python", "-m", "rasai"),
        (commands.EnvValue("VAR&echo hacked", "a", False),),
    )
    for target in commands.PLATFORMS:
        with pytest.raises(ValueError, match="nome de variável"):
            commands.render(plan, target)


def _probe(tmp_path: Path, args: tuple[str, ...], *, env_value: str) -> tuple[commands.CommandPlan, Path]:
    stub = tmp_path / "quoted args" / "probe.py"
    stub.parent.mkdir(exist_ok=True)
    stub.write_text(
        "import json, os, pathlib, sys\n"
        "pathlib.Path(sys.argv[1]).write_text("
        "json.dumps({'argv': sys.argv[2:], 'env': os.getenv('RASAI_TEST_VALUE')},"
        "ensure_ascii=False), encoding='utf-8')\n",
        encoding="utf-8",
    )
    result = tmp_path / "result with space.json"
    plan = commands.CommandPlan(
        "AUDITORIA", (sys.executable, str(stub), str(result), *args),
        (
            commands.EnvValue("RASAI_TEST_VALUE", env_value, False),
            commands.EnvValue("OPENAI_API_KEY", None, True),
        ),
    )
    return plan, result


@pytest.mark.skipif(sys.platform != "win32", reason="cmd.exe físico indisponível")
@pytest.mark.parametrize("args, env_value", [
    (("https://example.test/?a=1&b=2", "space within", "pipe|symbol", "a=b?c"), "o valor&com|shell"),
    (("100% válido", "!exclamation!", "power^caret", '"double"quote', "backslash\\"), "%PATH%&!^"),
    (("café 'completo'", "--item", "CAT-08", "∆ Unicode"), "café & 'completo'"),
])
def test_real_windows_cmd_roundtrip(tmp_path: Path, args: tuple[str, ...], env_value: str) -> None:
    plan, result = _probe(tmp_path, args, env_value=env_value)
    command = commands._copyable_command(commands.render(plan, "windows"), "windows")
    # Windows subprocess(list) applies CRT quoting intended for *argv* to the
    # /c payload; cmd.exe then sees literal backslash-escaped quotes. A .cmd
    # file is the supported scheduler surface and exercises its actual parser.
    batch = tmp_path / "rasai-stub.cmd"
    batch.write_text("@echo off\nsetlocal DisableDelayedExpansion\n" +
                     command + "\n", encoding="ascii")
    subprocess.run(["cmd.exe", "/d", "/v:off", "/c", str(batch)],
                   check=True, cwd=tmp_path, timeout=30)
    actual = json.loads(result.read_text(encoding="utf-8"))
    assert actual == {"argv": list(args), "env": env_value}


@pytest.mark.skipif(sys.platform != "win32", reason="PowerShell Windows não disponível")
@pytest.mark.parametrize("shell", ["powershell.exe", "pwsh.exe"])
@pytest.mark.parametrize("args, env_value", [
    (("https://example.test/?a=1&b=2", "space within", "pipe|symbol", "100%", 'a"b', "O'Brian"), "test% | 'com aspas'"),
    (("--item", "CAT-09", "café ∆", "!^", "some\\path\\"), "café ™ 123"),
])
def test_real_windows_powershell_roundtrip(tmp_path: Path, shell: str, args: tuple[str, ...], env_value: str) -> None:
    if not shutil.which(shell):
        pytest.skip(f"{shell} não instalado no runner")
    plan, result = _probe(tmp_path, args, env_value=env_value)
    command = commands._copyable_command(commands.render(plan, "powershell"), "powershell")
    subprocess.run([shell, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", command],
                   check=True, cwd=tmp_path, timeout=30)
    actual = json.loads(result.read_text(encoding="utf-8"))
    assert actual == {"argv": list(args), "env": env_value}


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX shell")
def test_real_posix_shell_roundtrip(tmp_path: Path) -> None:
    args = ("https://example.test/?a=1&b=2", "!^%|", 'a"b', "O'Brian", "café ∆", "path with space/")
    env_value = "café & | ! % ^"
    plan, result = _probe(tmp_path, args, env_value=env_value)
    target = commands._os()
    script = commands._copyable_command(commands.render(plan, target), target)
    subprocess.run(["/bin/sh", "-c", script], check=True, cwd=tmp_path, timeout=30)
    actual = json.loads(result.read_text(encoding="utf-8"))
    assert actual == {"argv": list(args), "env": env_value}


def test_reprocess_and_consolidation_keep_selection_and_ai_flags(tmp_path: Path) -> None:
    state = SimpleNamespace(
        audits_root=tmp_path / "work root",
        ai_provider="openai",
        ai_model="gpt-example",
        ai_reasoning="medium",
        web_performance=False,
        field_source="auto",
    )
    rpr = commands.reprocess_plan(
        state, "AUD-TEST", selected_items=["CAT-02", "CAT-08", "CAT-08"],
        use_ai=False, env={}, status="EXECUTADO",
    )
    assert rpr.status == "EXECUTADO"
    assert rpr.argv.count("--item") == 2
    assert rpr.argv[-1] == "--no-use-ai"
    assert "--ai-provider" not in rpr.argv
    assert "--audits-root" in rpr.argv
    for target in commands.PLATFORMS:
        output = commands.render(rpr, target)
        assert "reprocess" in output or "base64" in output

    selection = SimpleNamespace(
        baseline_audit_id="AUD-BASE",
        current_audit_id="AUD-CURRENT",
        selection_mode="MANUAL",
        audit_ids=("AUD-BASE", "AUD-MIDDLE", "AUD-CURRENT"),
    )
    filters = SimpleNamespace(specialist_ai=True, ai_provider="openai",
                              ai_model="gpt-example", ai_reasoning="medium",
                              ai_timeout_seconds=120)
    cons = commands.consolidation_plan(tmp_path / "work root", selection, filters,
                                      env={}, status="PLANEJADO")
    assert cons.argv[cons.argv.index("--manual-audit-id") + 1] == "AUD-MIDDLE"
    assert "--specialist-ai" in cons.argv
    assert "--ai-provider" in cons.argv
    assert "--ai-model" in cons.argv
    assert "--ai-reasoning" in cons.argv
