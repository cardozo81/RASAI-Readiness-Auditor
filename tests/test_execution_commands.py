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
    # Also paste into a live cmd.exe stdin, not only .cmd/scheduler.
    result.unlink()
    interactive = subprocess.run(
        ["cmd.exe", "/q", "/d", "/v:off"],
        input=command + "\r\nexit\r\n", text=True,
        capture_output=True, cwd=tmp_path, timeout=30,
    )
    assert interactive.returncode == 0, interactive.stderr
    assert json.loads(result.read_text(encoding="utf-8")) == {
        "argv": list(args), "env": env_value,
    }


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


def test_m_menu_uses_selected_shell_for_clipboard(monkeypatch, tmp_path: Path) -> None:
    plan = commands.CommandPlan(
        "AUDITORIA",
        ("python", "-m", "rasai", "audit", "https://example.test/?a=1&b=2"),
        (commands.EnvValue("OPENAI_API_KEY", None, True),),
    )
    blocks = {platform: commands.render(plan, platform)
              for platform in commands.PLATFORMS}
    monkeypatch.setattr(commands, "_os", lambda: "windows")
    choices = iter(["1", "C", "2", "C", "V"])
    monkeypatch.setattr("builtins.input", lambda _prompt: next(choices))
    copied: list[str] = []
    monkeypatch.setattr(commands, "_copy", lambda value: copied.append(value) or True)
    commands._menu(blocks, tmp_path / "history.log", None, "EXTERNAL COMMAND")
    assert len(copied) == 2
    assert '"https://example.test/?a=1&b=2"' in copied[0]
    assert "& 'python' '-m' 'rasai'" in copied[1]
    assert "**********" not in copied[0] + copied[1]
    assert "OPENAI_API_KEY" not in copied[0] + copied[1]
    assert " && " not in copied[1]


def test_historical_commands_show_original_blocks_without_session_rebuild(
    monkeypatch, tmp_path: Path,
) -> None:
    plan = commands.CommandPlan(
        "REPROCESSAMENTO", ("python", "-m", "rasai", "reprocess", "AUD-ORIGINAL",
                           "--item", "CAT-08", "--no-use-ai"),
        (), "EXECUTADO",
    )
    commands.record(plan, tmp_path, "AUD-ORIGINAL", append=False)
    observed: list[dict[str, str]] = []
    monkeypatch.setattr(
        commands, "_menu",
        lambda blocks, _path, _root, _title: observed.append(dict(blocks)),
    )
    assert commands.show_logged(tmp_path, "AUD-ORIGINAL") is True
    assert len(observed) == 1
    assert "powershell" in observed[0]
    assert "AUD-ORIGINAL" in observed[0]["powershell"]
    assert "--no-use-ai" in observed[0]["windows"]
    assert "PLANEJADO" not in observed[0]["windows"]


@pytest.mark.parametrize("selected,authorized,queries", [
    (("CAT-05",), True, ("seguro de vida", "previdencia privada")),
    (("CAT-05",), False, ("seguro de vida", "previdencia privada")),
    (("CAT-04",), True, ("seguro de vida", "previdencia privada")),
    (("CAT-05",), False, ()),
])
def test_planned_serp_matches_governed_child_without_authorizing_work(
    monkeypatch, selected, authorized, queries
) -> None:
    from types import ModuleType
    from rasai import console_config, console_runtime
    from rasai import console_governed_search_runtime as governed
    from rasai.console_catalog_plan import project_plan, set_ai_execution_enabled, set_selected_catalog_ids
    from rasai.console_search_intelligence import SearchConsoleState

    state = SearchConsoleState(
        target="https://example.test/",
        search_queries=queries,
        search_depth=30,
        search_region="São Paulo",
        search_device="desktop",
        search_competitive=False,
        search_compare_content=True,
        search_max_content_pages=4,
        search_content_timeout_seconds=12.5,
        search_content_max_bytes=1_500_000,
        search_content_max_redirects=2,
        search_ai_competitive=True,
        search_ymyl_mode="ON",
        ai_provider="openai",
        perplexity_draft_queries=("rascunho não autorizado",),
    )
    set_selected_catalog_ids(state, selected)
    set_ai_execution_enabled(state, authorized)
    monkeypatch.setattr(commands, "_names", lambda: ("OPENAI_API_KEY", "RASAI_GSC_ENABLED"))
    monkeypatch.setattr(commands, "_secret", lambda name: name == "OPENAI_API_KEY")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-RASAI-TEST-DO-NOT-LEAK")
    monkeypatch.setenv("RASAI_GSC_ENABLED", "true")
    source_env = dict(os.environ)
    observed = {}
    module = ModuleType("command_plan_child_stub")

    def child_stub(current):
        observed["argv"] = tuple(console_runtime.build_command(current))
        observed["env"] = dict(os.environ)
        return 0

    module.run_audit_from_console = child_stub
    monkeypatch.setattr(console_runtime, "build_command", console_config.build_command)
    monkeypatch.setattr(governed, "_INSTALLED", False)
    monkeypatch.setattr(governed, "_project_result", lambda _state: None)
    governed.install(module)

    # Reproduce the original omission in the base builder, before projection.
    assert "--search-query" not in console_config.build_command(state)
    plan = commands.audit_plan(state, env=source_env)
    # The preview must not call even the stub; no state or environment changes escape.
    assert not observed
    assert dict(os.environ) == source_env
    assert state.search_queries == queries
    assert state.search_ai_competitive is True
    assert state.ai_provider == "openai"
    assert state.perplexity_queries == ()
    assert state.perplexity_draft_queries == ("rascunho não autorizado",)

    with project_plan(state):
        assert module.run_audit_from_console(state) == 0

    assert plan.argv == observed["argv"]
    assert dict(os.environ) == source_env
    assert state.search_queries == queries
    expected_search = "CAT-05" in selected and bool(queries)
    if expected_search:
        assert [plan.argv[i + 1] for i, token in enumerate(plan.argv) if token == "--search-query"] == list(queries)
        for flag, value in (
            ("--search-depth", "30"), ("--search-region", "São Paulo"),
            ("--search-device", "desktop"), ("--search-max-content-pages", "4"),
            ("--search-content-timeout-seconds", "12.5"), ("--search-content-max-bytes", "1500000"),
            ("--search-content-max-redirects", "2"), ("--search-ymyl-mode", "ON"),
        ):
            assert plan.argv[plan.argv.index(flag) + 1] == value
        assert "--no-search-competitive" in plan.argv
        assert "--search-compare-content" in plan.argv
        assert ("--search-ai-competitive" if authorized else "--no-search-ai-competitive") in plan.argv
    else:
        assert not any(token.startswith("--search-") or token.startswith("--no-search-") for token in plan.argv)
    if not authorized or "CAT-05" not in selected:
        assert plan.argv[plan.argv.index("--ai-provider") + 1] == "none"
    gsc = next(item for item in plan.environment if item.name == "RASAI_GSC_ENABLED")
    assert gsc.value == observed["env"]["RASAI_GSC_ENABLED"]
    assert "sk-RASAI-TEST-DO-NOT-LEAK" not in commands.render_log(plan)


def test_executed_command_uses_captured_argv_and_environment_without_reprojection(monkeypatch, tmp_path) -> None:
    from rasai.console_search_intelligence import SearchConsoleState
    from rasai import console_catalog_plan

    state = SearchConsoleState(
        search_queries=("termo que não pertence ao subprocesso",),
        perplexity_queries=("pesquisa opcional do console",),
    )
    argv = ("python", "-m", "rasai", "audit", "https://example.test/", "--search-query", "termo efetivo")
    monkeypatch.setattr(console_catalog_plan, "project_plan", lambda *_args, **_kwargs: pytest.fail("reprojeção indevida"))
    monkeypatch.setattr(commands, "_names", lambda: ("OPENAI_API_KEY",))
    monkeypatch.setattr(commands, "_secret", lambda name: name == "OPENAI_API_KEY")
    plan = commands.executed(commands.audit_plan(state, argv=argv, env={"OPENAI_API_KEY": "sk-FAKE-SECRET"}))
    assert plan.status == "EXECUTADO"
    assert plan.argv == argv
    log = commands.record(plan, tmp_path, "AUD-STUB", append=False).read_text(encoding="utf-8")
    assert "Estado        : EXECUTADO" in log
    assert "sk-FAKE-SECRET" not in log
    assert "pesquisa opcional do console" not in log
    assert "PLANEJADO" not in log
    for shell, block in commands._blocks(log).items():
        assert "Pesquisa Perplexity e outras ações próprias pós-subprocesso" in block
        assert "não são reproduzidas nem comprovadas" in block
        copied = commands._copyable_command(block, shell)
        assert "Perplexity" not in copied
        assert "**********" not in copied
        assert "termo que não pertence ao subprocesso" not in copied
