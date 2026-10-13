"""Issue #523: offline INI/session/Apdex/Perplexity persistence contracts.

Only temporary files and in-memory environment variables are used; no paid calls.
"""
from __future__ import annotations

from configparser import ConfigParser
from contextlib import redirect_stdout
from io import StringIO
import os
from pathlib import Path
from unittest.mock import patch

from rasai import console_settings
from rasai.console_complete_persistence import install as install_complete_persistence
from rasai.console_config import is_secret
from rasai.console_provider_environment import refresh_specs
from rasai.console_search_intelligence import SearchConsoleState
from rasai.console_ui_refactor import _install_search_persistence


def _install_config_contract() -> None:
    _install_search_persistence()
    install_complete_persistence()


def _nondefault_apdex_state() -> SearchConsoleState:
    state = SearchConsoleState()
    # Explicit operator configuration, not historical defaults.
    state.device = "desktop"
    state.synthetic_apdex = True
    state.apdex_threshold = 2.1
    state.apdex_samples = 7
    state.apdex_max_attempts = 13
    state.apdex_max_pages = 2
    state.apdex_timeout = 48.0
    state.apdex_delay = 1.5
    state.apdex_concurrency = 2
    state.apdex_experience = True
    state.apdex_experience_samples = 9
    state.apdex_experience_max_attempts = 17
    state.apdex_experience_max_pages = 2
    state.apdex_experience_session_mode = "warm"
    state.apdex_experience_architecture = "CSR_SPA"
    state.apdex_experience_profile_mode = "DYNATRACE_GUIDED"
    state.apdex_experience_kpm = "VISUALLY_COMPLETE"
    state.apdex_experience_satisfied = 2.5
    state.apdex_experience_frustrated = 9.0
    state.apdex_experience_errors = False
    state.apdex_experience_javascript_errors = False
    state.apdex_experience_request_errors = True
    state.apdex_experience_console_errors = False
    state.apdex_experience_javascript_capture = True
    state.apdex_experience_xhr_capture = False
    state.apdex_experience_fetch_capture = True
    state.apdex_experience_console_capture = False
    state.apdex_experience_max_error_details = 8
    state.apdex_experience_error_scope = "first-party"
    state.apdex_experience_settle = 4.5
    state.apdex_experience_delay = 1.25
    state.apdex_experience_concurrency = 2
    state.apdex_dynatrace_import = True
    state.dynatrace_base_url = "https://dynatrace.example.test"
    state.dynatrace_application_id = "APPLICATION-523"
    state.apdex_dynatrace_config_json = '{"load_action":"VISUALLY_COMPLETE"}'
    # SERP is an explicitly reusable input; Perplexity is not.
    state.search_queries = ("teste seguro",)
    state.search_region = "Brasil"
    state.search_depth = 17
    state.perplexity_queries = ("paid-intent-must-not-survive",)
    state.perplexity_search_type = "fast"
    return state


def test_apdex_all_fields_roundtrip_new_process_and_effective_executor_environment(tmp_path) -> None:
    _install_config_contract()
    with patch.dict(os.environ, {}, clear=True):
        before = _nondefault_apdex_state()
        path = tmp_path / "523" / "operator.ini"
        saved = console_settings._state_values(before)
        projected_before = console_settings._runtime_environment_projection(before)
        console_settings.save_console_config(before, path)
        text = path.read_text(encoding="utf-8")
        assert "paid-intent-must-not-survive" not in text
        assert "perplexity_queries" not in text
        assert "perplexity_search_type" not in text

        # Simulate a new process (not just a new dataclass in the same env).
        os.environ.clear()
        after = SearchConsoleState()
        result = console_settings.load_console_config(after, path)
        assert result.created is False
        assert not result.warnings, result.warnings
        restored = console_settings._state_values(after)
        for section in ("synthetic_apdex", "synthetic_apdex_experience", "search_intelligence"):
            assert restored[section] == saved[section], section
        assert after.perplexity_queries == ()
        assert after.perplexity_search_type == "web"
        assert after.device == "desktop"

        # Verify actual state->executor environment projection, not only INI text.
        projected_after = console_settings._runtime_environment_projection(after)
        for name, value in projected_before.items():
            if name.startswith(("RASAI_APDEX_", "RASAI_SYNTHETIC_APDEX", "RASAI_DYNATRACE_")):
                assert projected_after.get(name) == value, name
        console_settings.sync_nonsecret_runtime_environment(after)
        for name, value in projected_after.items():
            if name.startswith(("RASAI_APDEX_", "RASAI_SYNTHETIC_APDEX", "RASAI_DYNATRACE_")):
                assert os.environ.get(name) == value, name


def test_registry_complete_ini_and_sensitive_values_excluded(tmp_path) -> None:
    _install_config_contract()
    with patch.dict(os.environ, {}, clear=True):
        os.environ["PERPLEXITY_API_KEY"] = "DO_NOT_PERSIST_PERPLEXITY"
        os.environ["RASAI_DYNATRACE_API_TOKEN"] = "DO_NOT_PERSIST_DYNATRACE"
        os.environ["OPENAI_API_KEY"] = "DO_NOT_PERSIST_OPENAI"
        os.environ["RASAI_SERP_MAX_REQUESTS"] = "19"
        state = SearchConsoleState()
        path = tmp_path / "rasai-console.ini"
        console_settings.save_console_config(state, path)
        parser = ConfigParser(interpolation=None)
        parser.optionxform = str
        parser.read(path, encoding="utf-8")
        safe = {spec.name for spec in refresh_specs() if not spec.sensitive and not is_secret(spec.name)}
        assert set(parser["environment"]) == safe
        assert parser.get("environment", "RASAI_SERP_MAX_REQUESTS") == "19"
        raw = path.read_text(encoding="utf-8")
        for sensitive in ("DO_NOT_PERSIST_PERPLEXITY", "DO_NOT_PERSIST_DYNATRACE", "DO_NOT_PERSIST_OPENAI"):
            assert sensitive not in raw
        for option in ("architecture", "profile_mode", "kpm", "xhr_capture", "fetch_capture"):
            assert parser.has_option("synthetic_apdex_experience", option)


def test_save_console_explicitly_discloses_perplexity_intent_not_persisted(tmp_path) -> None:
    from rasai import interactive_console as console

    state = _nondefault_apdex_state()
    destination = tmp_path / "operator.ini"
    output = StringIO()
    with patch("rasai.interactive_console.sync_nonsecret_runtime_environment"), patch(
        "rasai.interactive_console.save_console_config", return_value=destination
    ), patch("rasai.interactive_console.render_header"), patch(
        "builtins.input", return_value=""
    ), redirect_stdout(output):
        assert console._save_configuration(state) is True
    message = output.getvalue()
    assert "Perplexity Search" in message
    assert "NÃO são salvos" in message
    assert "nova solicitação/autorização explícita" in message


def test_legacy_ini_does_not_auto_authorize_optional_perplexity(tmp_path) -> None:
    _install_config_contract()
    ini = tmp_path / "legacy.ini"
    ini.write_text(
        "[console]\nconfig_version=4\n"
        "[synthetic_apdex_experience]\n"
        "architecture = HYDRATED\nprofile_mode = CUSTOM\n"
        "kpm = USER_ACTION_DURATION\n"
        "[environment]\nRASAI_PERPLEXITY_ENABLED = true\n",
        encoding="utf-8",
    )
    with patch.dict(os.environ, {}, clear=True):
        state = SearchConsoleState()
        result = console_settings.load_console_config(state, ini)
        assert not result.warnings
        assert state.apdex_experience_architecture == "HYDRATED"
        assert state.apdex_experience_profile_mode == "CUSTOM"
        assert state.perplexity_queries == ()
        assert state.perplexity_last_status == "NOT_REQUESTED"
        # Activation restored, but intent for a new paid request remains absent.
        assert os.environ.get("RASAI_PERPLEXITY_ENABLED") == "true"
