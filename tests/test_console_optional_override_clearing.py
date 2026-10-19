"""#523: cleared optional state must not leak a stale runtime override to M23/M25."""
from __future__ import annotations

from configparser import ConfigParser
import os
from unittest.mock import patch

from rasai import console_settings
from rasai.console_complete_persistence import install as install_persistence
from rasai.console_search_intelligence import SearchConsoleState
from rasai.console_ui_refactor import _install_search_persistence
from rasai.provider_registry import get_provider_registration
from rasai.provider_runtime_policy import provider_reasoning_env


def test_clear_optional_apdex_and_dynatrace_removes_stale_runtime_and_roundtrips(tmp_path):
    _install_search_persistence()
    install_persistence()
    with patch.dict(os.environ, {}, clear=True):
        state = SearchConsoleState()
        state.synthetic_apdex = True
        state.apdex_threshold = 2.75
        state.apdex_experience_satisfied = 2.5
        state.apdex_experience_frustrated = 9.5
        state.apdex_dynatrace_import = True
        state.dynatrace_base_url = "https://tenant.example.invalid"
        state.dynatrace_application_id = "offline-application"
        state.apdex_dynatrace_config_json = '{"load_action":"VISUALLY_COMPLETE"}'
        console_settings.sync_nonsecret_runtime_environment(state)
        keys = (
            "RASAI_APDEX_THRESHOLD_SECONDS",
            "RASAI_APDEX_EXPERIENCE_SATISFIED_SECONDS",
            "RASAI_APDEX_EXPERIENCE_FRUSTRATED_SECONDS",
            "RASAI_DYNATRACE_BASE_URL",
            "RASAI_DYNATRACE_APPLICATION_ID",
            "RASAI_DYNATRACE_CONFIG_JSON",
        )
        assert all(os.environ.get(name) for name in keys)

        state.synthetic_apdex = False
        state.apdex_threshold = None
        state.apdex_experience_satisfied = None
        state.apdex_experience_frustrated = None
        state.apdex_dynatrace_import = False
        state.dynatrace_base_url = ""
        state.dynatrace_application_id = ""
        state.apdex_dynatrace_config_json = ""
        console_settings.sync_nonsecret_runtime_environment(state)
        assert all(name not in os.environ for name in keys)

        ini = tmp_path / "cleared.ini"
        console_settings.save_console_config(state, ini)
        before = ini.read_bytes()
        parser = ConfigParser(interpolation=None)
        parser.optionxform = str
        parser.read(ini, encoding="utf-8")
        assert parser.get("synthetic_apdex", "threshold_seconds") == ""
        for option in ("satisfied_seconds", "frustrated_seconds"):
            assert parser.get("synthetic_apdex_experience", option) == ""
        previously_set = {
            "RASAI_APDEX_THRESHOLD_SECONDS": "2.75",
            "RASAI_DYNATRACE_BASE_URL": "https://tenant.example.invalid",
            "RASAI_DYNATRACE_APPLICATION_ID": "offline-application",
            "RASAI_DYNATRACE_CONFIG_JSON": '{"load_action":"VISUALLY_COMPLETE"}',
        }
        # A complete inventory may save safe registry defaults. It cannot
        # retain the previous session values when typed fields are cleared.
        for name, stale in previously_set.items():
            assert parser.get("environment", name) != stale

        with patch.dict(os.environ, {}, clear=True):
            restored = SearchConsoleState()
            loaded = console_settings.load_console_config(restored, ini)
            assert not loaded.created and not loaded.warnings
            console_settings.sync_nonsecret_runtime_environment(restored)
            assert all(name not in os.environ for name in keys)
            assert restored.apdex_threshold is None
            assert restored.apdex_experience_satisfied is None
            assert restored.apdex_experience_frustrated is None
        assert ini.read_bytes() == before


def test_clear_selected_provider_model_without_erasing_other_providers_or_secrets():
    with patch.dict(os.environ, {}, clear=True):
        state = SearchConsoleState()
        state.ai_provider = "openai"
        state.ai_model = "offline-model"
        state.ai_reasoning = "LOW"
        provider = get_provider_registration("openai")
        assert provider is not None
        reasoning = provider_reasoning_env(provider.provider_name)
        console_settings.sync_nonsecret_runtime_environment(state)
        assert os.environ[provider.model_env] == "offline-model"
        if reasoning:
            assert os.environ[reasoning] == "LOW"
        os.environ["OTHER_PROVIDER_MODEL"] = "preserve"
        os.environ["PERPLEXITY_API_KEY"] = "no-external-requests"
        state.ai_model = None
        state.ai_reasoning = None
        console_settings.sync_nonsecret_runtime_environment(state)
        assert provider.model_env not in os.environ
        if reasoning:
            assert reasoning not in os.environ
        assert os.environ["OTHER_PROVIDER_MODEL"] == "preserve"
        assert os.environ["PERPLEXITY_API_KEY"] == "no-external-requests"


def test_malformed_typed_ini_warning_does_not_echo_original_value(tmp_path):
    marker = "PRIVATE-INPUT-MARKER-ABCD"
    path = tmp_path / "untrusted.ini"
    path.write_text(
        "[ai]\\nmax_cycles = " + marker + "\\n"
        "[synthetic_apdex]\\nsamples_per_context = " + marker + "\\n",
        encoding="utf-8",
    )
    before = path.read_bytes()
    with patch.dict(os.environ, {}, clear=True):
        state = SearchConsoleState()
        result = console_settings.load_console_config(state, path)
        assert result.created is False
        assert len(result.warnings) == 2
        assert marker not in str(result.warnings)
        assert any(w.startswith("ai.max_cycles:") for w in result.warnings)
        assert any(w.startswith("synthetic_apdex.samples_per_context:")
                   for w in result.warnings)
        assert state.config_dirty is True
    assert path.read_bytes() == before
