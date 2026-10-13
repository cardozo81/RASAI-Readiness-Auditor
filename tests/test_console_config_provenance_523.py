"""#523: validate secure INI provenance and real subprocess round-trip on Win/Linux."""
from __future__ import annotations

from configparser import ConfigParser
import json
import os
from pathlib import Path
import subprocess
import sys

from rasai.console_config_path import canonical_console_config_path, prepare_console_config
from rasai.console_config_provenance_523 import inspect_configuration, render_provenance
from rasai.console_search_intelligence import SearchConsoleState
from rasai.console_ui_refactor import _install_search_persistence
from rasai.console_complete_persistence import install as install_complete_persistence
from rasai import console_settings


def test_actual_ini_path_is_env_or_cwd_and_not_synthetic(tmp_path):
    env: dict[str, str] = {}
    saved = prepare_console_config(env=env, cwd=tmp_path)
    assert saved == (tmp_path / "rasai-console.ini").resolve()
    assert env["RASAI_CONSOLE_INI"] == str(saved)
    env["RASAI_CONSOLE_INI"] = "nested/different.ini"
    assert canonical_console_config_path(env=env, cwd=tmp_path) == (
        tmp_path / "nested" / "different.ini"
    ).resolve()


def test_secret_safe_shadowing_and_unknown_keys_are_counted_not_displayed(tmp_path):
    path = tmp_path / "operator.ini"
    path.write_text(
        "[environment]\nRASAI_SERP_MAX_REQUESTS = 12\n"
        "OPENAI_API_KEY = NEVER_SHOW_THIS_SECRET\n"
        "UNREGISTERED_KEY = ALSO_NEVER_SHOW\n",
        encoding="utf-8",
    )
    result = inspect_configuration(
        path,
        env={"RASAI_SERP_MAX_REQUESTS": "17", "OPENAI_API_KEY": "REAL_SECRET"},
    )
    assert result.persisted_public == 1
    assert result.session_overrides == 1
    assert result.invalid_entries == 2
    printed = render_provenance(result)
    assert "divergência(s)" in printed
    assert "prioridade efetiva depende do campo" in printed
    assert "NEVER_SHOW" not in printed
    assert "REAL_SECRET" not in printed
    assert "OPENAI_API_KEY" not in printed
    assert "RASAI_SERP_MAX_REQUESTS" not in printed
    assert "UNREGISTERED_KEY" not in printed


def test_missing_invalid_and_malformed_ini_abstain(tmp_path):
    assert inspect_configuration(None).file_status == "NÃO RESOLVIDO"
    assert inspect_configuration(tmp_path / "none.ini").file_status == "AUSENTE"
    invalid = tmp_path / "invalid.ini"
    invalid.write_text("[not_valid\n", encoding="utf-8")
    assert inspect_configuration(invalid).file_status == "INVÁLIDO"
    empty = tmp_path / "empty.ini"
    empty.write_text("[console]\ntarget=https://example.test\n", encoding="utf-8")
    assert "sem inventário" in inspect_configuration(empty).file_status


def test_canonical_save_and_reopen_in_separate_python_process_with_unchanged_ini(tmp_path, monkeypatch):
    """Exercise actual module import/boot from two isolated Python processes.

    No inherited credentials; the two executions use different process-local
    environments and read the exact RASAI_CONSOLE_INI path.
    """
    path = (tmp_path / "independent" / "operator.ini").resolve()
    path.parent.mkdir()
    safe = {
        name: value
        for name, value in os.environ.items()
        if name.upper() in {
            "PATH", "PATHEXT", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "TMPDIR",
            "HOME", "USERPROFILE", "PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV",
        }
    }
    safe["RASAI_CONSOLE_INI"] = str(path)
    write_code = """
from rasai.console_config_path import prepare_console_config
from rasai.console_ui_refactor import _install_search_persistence
from rasai.console_complete_persistence import install
from rasai.console_search_intelligence import SearchConsoleState
from rasai import console_settings
_install_search_persistence()
install()
state = SearchConsoleState()
state.target = 'https://example.test/path'
state.apdex_experience = True
state.apdex_experience_architecture = 'CSR_SPA'
state.apdex_experience_profile_mode = 'DYNATRACE_GUIDED'
state.apdex_experience_kpm = 'VISUALLY_COMPLETE'
state.apdex_experience_xhr_capture = False
state.apdex_experience_fetch_capture = True
state.apdex_experience_javascript_errors = False
state.apdex_experience_request_errors = True
state.apdex_experience_concurrency = 2
state.apdex_experience_samples = 7
state.apdex_experience_max_attempts = 11
state.synthetic_apdex = True
state.apdex_samples = 5
state.apdex_max_attempts = 7
state.perplexity_queries = ('do not authorize next run',)
state.perplexity_search_type = 'fast'
path = prepare_console_config()
console_settings.save_console_config(state, path)
print(path)
"""
    read_code = """
import json
from rasai.console_config_path import prepare_console_config
from rasai.console_ui_refactor import _install_search_persistence
from rasai.console_complete_persistence import install
from rasai.console_search_intelligence import SearchConsoleState
from rasai import console_settings
_install_search_persistence()
install()
path = prepare_console_config()
state = SearchConsoleState()
result = console_settings.load_console_config(state, path)
projection = console_settings._runtime_environment_projection(state)
print(json.dumps({
    'path': str(result.path),
    'warnings': result.warnings,
    'architecture': state.apdex_experience_architecture,
    'profile': state.apdex_experience_profile_mode,
    'kpm': state.apdex_experience_kpm,
    'xhr': state.apdex_experience_xhr_capture,
    'fetch': state.apdex_experience_fetch_capture,
    'js_affect': state.apdex_experience_javascript_errors,
    'request_affect': state.apdex_experience_request_errors,
    'concurrency': state.apdex_experience_concurrency,
    'samples': state.apdex_experience_samples,
    'attempts': state.apdex_experience_max_attempts,
    'nav': [state.synthetic_apdex,state.apdex_samples,state.apdex_max_attempts],
    'queries': state.perplexity_queries,
    'perplexity_mode': state.perplexity_search_type,
    'env_arch': projection['RASAI_APDEX_EXPERIENCE_ARCHITECTURE'],
    'env_profile': projection['RASAI_APDEX_EXPERIENCE_PROFILE_MODE'],
}))
"""
    a = subprocess.run(
        [sys.executable, "-c", write_code], cwd=tmp_path, env=safe,
        check=True, text=True, capture_output=True, timeout=30,
    )
    assert str(path) in a.stdout
    digest_before = path.read_bytes()
    assert b"do not authorize next run" not in digest_before
    assert b"perplexity_queries" not in digest_before
    b = subprocess.run(
        [sys.executable, "-c", read_code], cwd=tmp_path, env=safe,
        check=True, text=True, capture_output=True, timeout=30,
    )
    data = json.loads(b.stdout.strip().splitlines()[-1])
    assert data["path"] == str(path)
    assert data["warnings"] == []
    assert (data["architecture"], data["env_arch"]) == ("CSR_SPA", "CSR_SPA")
    assert (data["profile"], data["env_profile"]) == ("DYNATRACE_GUIDED", "DYNATRACE_GUIDED")
    assert data["kpm"] == "VISUALLY_COMPLETE"
    assert data["xhr"] is False and data["fetch"] is True
    assert data["js_affect"] is False and data["request_affect"] is True
    assert data["concurrency"] == 2 and data["samples"] == 7 and data["attempts"] == 11
    assert data["nav"] == [True, 5, 7]
    assert data["queries"] == []
    assert data["perplexity_mode"] == "web"
    assert path.read_bytes() == digest_before


def test_typed_ini_can_win_over_prior_process_environment_on_runtime_sync(tmp_path):
    """Observe precedence physically instead of interpreting raw env conflicts."""
    from unittest.mock import patch

    path = tmp_path / "typed-priority.ini"
    path.write_text(
        "[environment]\nRASAI_APDEX_EXPERIENCE_ARCHITECTURE = STATIC_OR_SSR\n"
        "[synthetic_apdex_experience]\narchitecture = CSR_SPA\n",
        encoding="utf-8",
    )
    key = "RASAI_APDEX_EXPERIENCE_ARCHITECTURE"
    with patch.dict(os.environ, {key: "HYDRATED"}, clear=True):
        metadata = inspect_configuration(path)
        assert metadata.session_overrides == 1
        display = render_provenance(metadata)
        assert "prioridade efetiva depende do campo" in display
        assert "HYDRATED" not in display
        assert "STATIC_OR_SSR" not in display

        state = SearchConsoleState()
        result = console_settings.load_console_config(state, path)
        assert not result.warnings, result.warnings
        assert os.environ[key] == "HYDRATED"  # load preserves explicit process env
        assert state.apdex_experience_architecture == "CSR_SPA"
        console_settings.sync_nonsecret_runtime_environment(state)
        assert os.environ[key] == "CSR_SPA"  # typed INI state reprojects at run
