"""#523: validate secure INI provenance and real subprocess round-trip on Win/Linux."""
from __future__ import annotations

from configparser import ConfigParser
import json
import os
from pathlib import Path
import subprocess
import sys

from rasai.console_config_path import canonical_console_config_path, prepare_console_config
from rasai.console_config_provenance import inspect_configuration, render_provenance
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
    assert result.private_entries_in_ini == 1
    printed = render_provenance(result)
    assert "potencialmente sensível" in printed
    assert "divergência(s)" in printed
    assert "prioridade efetiva depende do campo" in printed
    assert "NEVER_SHOW" not in printed
    assert "REAL_SECRET" not in printed
    assert "OPENAI_API_KEY" not in printed
    assert "RASAI_SERP_MAX_REQUESTS" not in printed
    assert "UNREGISTERED_KEY" not in printed


def test_default_section_is_not_a_persisted_environment_assignment(tmp_path):
    """Counts must reflect only physical [environment] keys, not [DEFAULT]."""
    path = tmp_path / "inherited.ini"
    path.write_text(
        "[DEFAULT]\n"
        "OPENAI_API_KEY = SHOULD_NOT_BE_COUNTED\n"
        "RASAI_SERP_MAX_REQUESTS = 99\n"
        "UNREGISTERED_SECRET = SHOULD_NOT_BE_COUNTED\n"
        "[environment]\n"
        "RASAI_SERP_MAX_REQUESTS = 12\n",
        encoding="utf-8",
    )
    before = path.read_bytes()
    result = inspect_configuration(
        path, env={"RASAI_SERP_MAX_REQUESTS": "12"},
    )
    assert result.file_status == "LIDO: arquivo existente"
    assert result.persisted_public == 1
    assert result.session_overrides == 0
    assert result.private_entries_in_ini == 0
    assert result.invalid_entries == 0
    assert "SHOULD_NOT_BE_COUNTED" not in render_provenance(result)
    assert path.read_bytes() == before


def test_provenance_abstains_if_file_changes_during_bounded_read(tmp_path, monkeypatch):
    """A file race must not be mistaken for a loaded configuration."""
    from rasai import console_config_provenance as module

    path = tmp_path / "race.ini"
    path.write_text("[environment]\nRASAI_SERP_MAX_REQUESTS=12\n", encoding="utf-8")
    monkeypatch.setattr(
        module, "_ini_with_status",
        lambda _path: (None, "SOURCE_CHANGED_DURING_READ"),
    )
    result = inspect_configuration(path, env={})
    assert "alterado durante leitura" in result.file_status
    assert result.persisted_public == 0
    assert result.session_overrides == 0
    assert result.private_entries_in_ini == 0


def test_missing_invalid_and_malformed_ini_abstain(tmp_path):
    assert inspect_configuration(None).file_status == "NÃO RESOLVIDO"
    assert inspect_configuration(tmp_path / "none.ini").file_status == "AUSENTE"
    invalid = tmp_path / "invalid.ini"
    invalid.write_text("[not_valid\n", encoding="utf-8")
    assert inspect_configuration(invalid).file_status == "INVÁLIDO"
    empty = tmp_path / "empty.ini"
    empty.write_text("[console]\ntarget=https://example.test\n", encoding="utf-8")
    assert "sem inventário" in inspect_configuration(empty).file_status



def test_configuration_provenance_refuses_symlink_ini_source_when_supported(tmp_path):
    source = tmp_path / "private.ini"
    source.write_text("[environment]\\nOPENAI_API_KEY=secret-value\\n", encoding="utf-8")
    link = tmp_path / "redirect.ini"
    try:
        link.symlink_to(source)
    except (OSError, NotImplementedError):
        return  # Windows test runner may lack symlink creation privileges.
    inspected = inspect_configuration(link, env={})
    assert inspected.file_status == "NÃO INSPECIONADO: caminho simbólico"
    assert inspected.persisted_public == 0
    assert inspected.private_entries_in_ini == 0
    assert "secret-value" not in render_provenance(inspected)



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
    'draft': state.perplexity_draft_queries,
    'draft_mode': state.perplexity_draft_search_type,
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
    assert b"do not authorize next run" in digest_before
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
    assert data["draft"] == ["do not authorize next run"]
    assert data["draft_mode"] == "fast"
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


def test_windows_utf8_bom_ini_is_inspected_without_mutation(tmp_path):
    path = tmp_path / "windows.ini"
    path.write_bytes(b"\xef\xbb\xbf[environment]\nRASAI_SERP_MAX_REQUESTS=12\n")
    original = path.read_bytes()
    result = inspect_configuration(path, env={})
    assert result.file_status == "LIDO: arquivo existente"
    assert result.persisted_public == 1
    assert path.read_bytes() == original


def test_console_load_accepts_bom_ini_without_rewriting_source(tmp_path, monkeypatch):
    path = tmp_path / "operator-bom.ini"
    path.write_bytes(b"\xef\xbb\xbf[environment]\nRASAI_SERP_MAX_REQUESTS=12\n")
    initial = path.read_bytes()
    monkeypatch.delenv("RASAI_SERP_MAX_REQUESTS", raising=False)
    _install_search_persistence()
    install_complete_persistence()
    state = SearchConsoleState()
    result = console_settings.load_console_config(state, path)
    assert not any("não foi possível ler" in warning for warning in result.warnings)
    assert path.read_bytes() == initial


def test_guarded_save_accepts_known_bom_ini(tmp_path):
    path = tmp_path / "operator-bom.ini"
    _install_search_persistence()
    install_complete_persistence()
    state = SearchConsoleState()
    console_settings.save_console_config(state, path)
    path.write_bytes(bytes((239, 187, 191)) + path.read_bytes())
    loaded = SearchConsoleState()
    assert not console_settings.load_console_config(loaded, path).warnings
    assert console_settings.save_console_config(loaded, path) == path
    reloaded = SearchConsoleState()
    assert not console_settings.load_console_config(reloaded, path).warnings


def test_console_load_refuses_symlink_without_modifying_state_or_source(tmp_path, monkeypatch):
    """A startup config cannot follow a symlink to unrelated operator data."""
    from rasai.console_search_intelligence import SearchConsoleState
    real = tmp_path / "real.ini"
    real.write_text("[environment]\nRASAI_SERP_MAX_REQUESTS=37\n", encoding="utf-8")
    link = tmp_path / "console.ini"
    try:
        link.symlink_to(real)
    except (OSError, NotImplementedError):
        import pytest
        pytest.skip("symlinks unavailable on this platform")
    source_before = real.read_bytes()
    monkeypatch.delenv("RASAI_SERP_MAX_REQUESTS", raising=False)
    state = SearchConsoleState()
    prior = state.device
    result = console_settings.load_console_config(state, link)
    assert not result.created
    assert result.warnings
    assert "RASAI_SERP_MAX_REQUESTS" not in os.environ
    assert state.device == prior
    assert real.read_bytes() == source_before
    assert link.is_symlink()


def test_console_load_refuses_oversized_ini_without_side_effects(tmp_path, monkeypatch):
    """Reader rejects files beyond the existing 2MB source guard."""
    from rasai.console_search_intelligence import SearchConsoleState
    path = tmp_path / "too-large.ini"
    path.write_bytes(b"[environment]\nRASAI_SERP_MAX_REQUESTS=4\n" +
                     b";" * 2_000_001)
    source_before = path.stat().st_size
    monkeypatch.delenv("RASAI_SERP_MAX_REQUESTS", raising=False)
    state = SearchConsoleState()
    original_device = state.device
    result = console_settings.load_console_config(state, path)
    assert result.warnings and result.created is False
    assert "RASAI_SERP_MAX_REQUESTS" not in os.environ
    assert state.device == original_device
    assert path.stat().st_size == source_before


def test_console_load_refuses_changed_source_before_any_environment_activation(
    tmp_path, monkeypatch,
):
    """Source identity race on read fails closed instead of partially loading."""
    from rasai.console_search_intelligence import SearchConsoleState
    from unittest.mock import patch
    path = tmp_path / "unstable.ini"
    path.write_text("[environment]\nRASAI_SERP_MAX_REQUESTS=22\n", encoding="utf-8")
    original = path.read_bytes()
    monkeypatch.delenv("RASAI_SERP_MAX_REQUESTS", raising=False)
    state = SearchConsoleState()
    with patch("rasai.console_settings._existing_ini_snapshot",
               side_effect=ValueError("source changed during read")):
        result = console_settings.load_console_config(state, path)
    assert result.warnings and not result.created
    assert "RASAI_SERP_MAX_REQUESTS" not in os.environ
    assert path.read_bytes() == original



def test_console_load_dangling_symlink_is_not_treated_as_missing_ini(tmp_path, monkeypatch):
    """Reject even a broken link before the create-default path."""
    from rasai.console_search_intelligence import SearchConsoleState
    import pytest

    link = tmp_path / "dangling.ini"
    try:
        link.symlink_to(tmp_path / "missing.ini")
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable")
    assert not link.exists() and link.is_symlink()
    state = SearchConsoleState()
    monkeypatch.delenv("RASAI_SERP_MAX_REQUESTS", raising=False)
    result = console_settings.load_console_config(state, link)
    assert not result.created and result.warnings
    assert link.is_symlink()
    assert "RASAI_SERP_MAX_REQUESTS" not in os.environ
    assert not (tmp_path / "missing.ini").exists()


def test_explicit_empty_session_value_is_not_mistaken_for_absent_override(tmp_path):
    """Provenance must distinguish an explicitly empty input from no input."""
    path = tmp_path / "session-empty.ini"
    path.write_text("[environment]\nRASAI_SERP_MAX_REQUESTS=12\n", encoding="utf-8")
    original = path.read_bytes()
    absent = inspect_configuration(path, env={})
    empty = inspect_configuration(path, env={"RASAI_SERP_MAX_REQUESTS": ""})
    assert absent.persisted_public == 1
    assert absent.session_overrides == 0
    assert empty.session_overrides == 1
    assert "12" not in render_provenance(empty)
    assert path.read_bytes() == original


def test_ini_environment_precedence_preserves_explicit_empty_session_override(
    tmp_path, monkeypatch,
):
    """#523: presence, not truthiness, decides session > INI precedence."""
    from rasai.console_search_intelligence import SearchConsoleState

    path = tmp_path / "precedence.ini"
    path.write_text(
        "[environment]\nRASAI_SERP_MAX_REQUESTS=12\n",
        encoding="utf-8",
    )
    for initial, expected in ((None, "12"), ("", ""), ("7", "7")):
        if initial is None:
            monkeypatch.delenv("RASAI_SERP_MAX_REQUESTS", raising=False)
        else:
            monkeypatch.setenv("RASAI_SERP_MAX_REQUESTS", initial)
        result = console_settings.load_console_config(SearchConsoleState(), path)
        assert not result.warnings
        assert os.environ.get("RASAI_SERP_MAX_REQUESTS") == expected


def test_console_load_reports_unknown_ini_section_without_leaking_values(
    tmp_path, monkeypatch,
):
    from rasai.console_search_intelligence import SearchConsoleState

    ini = tmp_path / "unknown-section.ini"
    ini.write_text(
        "[unexpected_private_section]\nTOKEN=DO_NOT_DISCLOSE_523\n"
        "[environment]\nRASAI_SERP_MAX_REQUESTS=9\n", encoding="utf-8",
    )
    monkeypatch.delenv("RASAI_SERP_MAX_REQUESTS", raising=False)
    result = console_settings.load_console_config(SearchConsoleState(), ini)
    assert any("unexpected_private_section" in note for note in result.warnings)
    assert "DO_NOT_DISCLOSE_523" not in repr(result.warnings)
    assert os.environ["RASAI_SERP_MAX_REQUESTS"] == "9"


def test_invalid_restored_typed_value_marks_configuration_unsaved(tmp_path):
    """#523: partial typed restoration must not claim a clean saved state."""
    from rasai.console_search_intelligence import SearchConsoleState

    ini = tmp_path / "invalid-pages.ini"
    ini.write_text("[console]\nmax_pages=not-a-number\n", encoding="utf-8")
    state = SearchConsoleState()
    result = console_settings.load_console_config(state, ini)
    assert any("console.max_pages" in note for note in result.warnings)
    assert state.config_dirty is True

    valid = tmp_path / "valid-pages.ini"
    valid.write_text("[console]\nmax_pages=4\n", encoding="utf-8")
    fresh = SearchConsoleState()
    result = console_settings.load_console_config(fresh, valid)
    assert result.warnings == ()
    assert fresh.config_dirty is False


def test_console_ini_rejects_nonfinite_runtime_delays_and_timeouts(tmp_path):
    """#523/#357: NaN and infinity cannot enter runtime configuration."""
    from rasai.console_search_intelligence import SearchConsoleState

    for section, option, invalid in (
        ("ai", "timeout_seconds", "nan"),
        ("ai", "cycle_delay_seconds", "nan"),
        ("web_performance", "timeout_seconds", "inf"),
        ("synthetic_apdex", "delay_seconds", "-inf"),
        ("synthetic_apdex_experience", "delay_seconds", "nan"),
        ("synthetic_apdex_experience", "settle_seconds", "inf"),
    ):
        ini = tmp_path / "nonfinite.ini"
        ini.write_text(f"[{section}]\n{option}={invalid}\n", encoding="utf-8")
        state = SearchConsoleState()
        result = console_settings.load_console_config(state, ini)
        assert any(note.startswith(f"{section}.{option}:") for note in result.warnings)
        assert state.config_dirty is True
