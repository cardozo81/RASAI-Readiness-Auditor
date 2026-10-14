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
    state.target = "https://example.test/consulta"
    state.project = "Projeto QA"
    state.market = "BR"
    state.language = "pt-BR"
    state.max_pages = 3
    state.ai_timeout = 183.0
    state.ai_max_cycles = 2
    state.ai_cycle_delay = 0.5
    state.content_remediation = True
    state.web_performance = True
    state.web_max_pages = 2
    state.web_timeout = 133.0
    state.field_source = "crux"
    state.lighthouse_categories = "performance,accessibility"
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
    # Both SERP and Perplexity terms can be saved; only Perplexity intent is transient.
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
        assert "[perplexity_draft]" in text
        assert "queries = paid-intent-must-not-survive" in text
        assert "search_type = fast" in text
        assert "perplexity_queries" not in text

        # Simulate a new process (not just a new dataclass in the same env).
        os.environ.clear()
        after = SearchConsoleState()
        result = console_settings.load_console_config(after, path)
        assert result.created is False
        assert not result.warnings, result.warnings
        restored = console_settings._state_values(after)
        for section, values in saved.items():
            assert restored[section] == values, section
        assert after.perplexity_queries == ()
        assert after.perplexity_search_type == "web"
        assert after.perplexity_draft_queries == ("paid-intent-must-not-survive",)
        assert after.perplexity_draft_search_type == "fast"
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


def test_save_console_discloses_perplexity_draft_without_inherited_intent(tmp_path) -> None:
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
    assert "RASCUNHO no INI" in message
    assert "não serão solicitados automaticamente" in message
    assert "CAT-05 > P > 9" in message


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


def test_saved_apdex_inputs_are_consumed_by_real_m23_m25_config_adapters_without_aud(tmp_path) -> None:
    """Prove consumption after restore, not merely an environment string roundtrip."""
    import argparse
    from rasai.m23_cli import configured_apdex, register_apdex_arguments
    from rasai.m25_runtime import peek_pending_config, set_pending_config
    from rasai.m25_apdex_experience import ExperienceApdexConfig

    _install_config_contract()
    with patch.dict(os.environ, {}, clear=True):
        before = _nondefault_apdex_state()
        # This scenario tests the custom offline KPM path, never Dynatrace live.
        before.apdex_dynatrace_import = False
        before.dynatrace_base_url = ""
        before.dynatrace_application_id = ""
        before.apdex_dynatrace_config_json = ""
        before.apdex_experience_profile_mode = "CUSTOM"
        before.apdex_experience_kpm = "USER_ACTION_DURATION"
        before.apdex_experience_satisfied = 2.5
        before.apdex_experience_frustrated = 9.0
        path = tmp_path / "restored.ini"
        console_settings.save_console_config(before, path)
        physical_before = path.read_bytes()
        os.environ.clear()

        after = SearchConsoleState()
        result = console_settings.load_console_config(after, path)
        assert result.warnings == ()
        assert after.apdex_experience_architecture == "CSR_SPA"
        assert after.apdex_experience_profile_mode == "CUSTOM"
        console_settings.sync_nonsecret_runtime_environment(after)
        env = dict(os.environ)

        cli = argparse.ArgumentParser()
        register_apdex_arguments(cli)
        arguments = cli.parse_args([])
        try:
            navigation = configured_apdex(arguments, env=env)
            experience = peek_pending_config()
            assert navigation.enabled is True
            assert navigation.threshold_seconds == 2.1
            assert navigation.target_valid_samples == 7
            assert navigation.max_attempts_per_context == 13
            assert navigation.max_pages == 2
            assert navigation.timeout_seconds == 48.0
            assert navigation.delay_seconds == 1.5
            assert navigation.concurrency == 2

            assert experience.enabled is True
            assert experience.target_samples_per_page == 9
            assert experience.max_attempts_per_page == 17
            assert experience.max_pages == 2
            assert experience.device_mix_dict() == {"DESKTOP": 100.0}
            assert experience.session_mode == "warm"
            assert experience.kpm == "USER_ACTION_DURATION"
            assert experience.satisfied_threshold_seconds == 2.5
            assert experience.frustrated_threshold_seconds == 9.0
            assert experience.errors_affect_apdex is False
            assert experience.javascript_errors_affect_apdex is False
            assert experience.request_errors_affect_apdex is True
            assert experience.console_errors_affect_apdex is False
            assert experience.javascript_error_capture is True
            assert experience.xhr_capture is False
            assert experience.fetch_capture is True
            assert experience.console_error_capture is False
            assert experience.max_error_details == 8
            assert experience.error_scope == "first-party"
            assert experience.settle_seconds == 4.5
            assert experience.delay_seconds == 1.25
            assert experience.concurrency == 2
            assert experience.dynatrace_import is False
            assert env["RASAI_APDEX_EXPERIENCE_ARCHITECTURE"] == "CSR_SPA"
            assert env["RASAI_APDEX_EXPERIENCE_PROFILE_MODE"] == "CUSTOM"
            assert physical_before == path.read_bytes()
        finally:
            set_pending_config(ExperienceApdexConfig(enabled=False))


def test_console_loader_does_not_apply_inherited_ini_default_values(tmp_path):
    _install_config_contract()
    ini = tmp_path / "operator-defaults.ini"
    ini.write_text(
        "[DEFAULT]\n"
        "RASAI_SERP_MAX_REQUESTS=777\n"
        "architecture=CSR_SPA\n"
        "[environment]\n"
        "RASAI_WEB_PERFORMANCE=true\n"
        "[synthetic_apdex_experience]\n"
        "profile_mode=CUSTOM\n",
        encoding="utf-8",
    )
    original = ini.read_bytes()
    with patch.dict(os.environ, {}, clear=True):
        state = SearchConsoleState()
        original_architecture = state.apdex_experience_architecture
        result = console_settings.load_console_config(state, ini)
        assert not result.created
        assert "RASAI_SERP_MAX_REQUESTS" not in os.environ
        assert os.environ["RASAI_WEB_PERFORMANCE"] == "true"
        assert state.apdex_experience_architecture == original_architecture
        assert state.apdex_experience_profile_mode == "CUSTOM"
    assert ini.read_bytes() == original


def test_console_loader_explicit_environment_overrides_default(tmp_path):
    _install_config_contract()
    ini = tmp_path / "explicit-operator.ini"
    ini.write_text(
        "[DEFAULT]\n"
        "RASAI_SERP_MAX_REQUESTS=777\n"
        "[environment]\n"
        "RASAI_SERP_MAX_REQUESTS=11\n",
        encoding="utf-8",
    )
    with patch.dict(os.environ, {}, clear=True):
        result = console_settings.load_console_config(SearchConsoleState(), ini)
        assert not result.created
        assert os.environ["RASAI_SERP_MAX_REQUESTS"] == "11"


def test_malformed_operator_ini_does_not_crash_or_leak_secret(tmp_path):
    _install_config_contract()
    path = tmp_path / "bad.ini"
    secret = "SHOULD_NOT_ECHO_OPERATOR_VALUE"
    path.write_text(
        "[environment]\nRASAI_SERP_MAX_REQUESTS=3\n"
        "RASAI_SERP_MAX_REQUESTS=" + secret + "\n",
        encoding="utf-8",
    )
    original_bytes = path.read_bytes()
    with patch.dict(os.environ, {}, clear=True):
        state = SearchConsoleState()
        original_device = state.device
        result = console_settings.load_console_config(state, path)
        assert result.created is False
        assert len(result.warnings) == 1
        assert "DuplicateOptionError" in result.warnings[0]
        assert secret not in str(result.warnings)
        assert "RASAI_SERP_MAX_REQUESTS" not in os.environ
        assert state.device == original_device
    assert path.read_bytes() == original_bytes


def test_truncated_operator_ini_abstains_without_partial_activation(tmp_path):
    _install_config_contract()
    path = tmp_path / "unfinished.ini"
    path.write_text(
        "[environment]\nRASAI_SERP_MAX_REQUESTS=5\n"
        "[synthetic_apdex_experience\narchitecture=CSR_SPA\n",
        encoding="utf-8",
    )
    with patch.dict(os.environ, {}, clear=True):
        result = console_settings.load_console_config(SearchConsoleState(), path)
        assert result.created is False
        assert result.warnings
        assert "RASAI_SERP_MAX_REQUESTS" not in os.environ

def test_saved_perplexity_draft_survives_unrelated_save_without_optin(tmp_path):
    """Saving other settings after reboot does not silently discard the draft."""
    from rasai.console_perplexity_readiness_318 import inspect_perplexity_readiness

    _install_config_contract()
    path = tmp_path / "persisted.ini"
    with patch.dict(os.environ, {}, clear=True):
        original = SearchConsoleState(
            perplexity_queries=("seguro família", "seguro carro"),
            perplexity_search_type="fast",
        )
        console_settings.save_console_config(original, path)
        restored = SearchConsoleState()
        console_settings.load_console_config(restored, path)
        assert restored.perplexity_queries == ()
        assert restored.perplexity_draft_queries == ("seguro família", "seguro carro")
        assert restored.perplexity_draft_search_type == "fast"
        readiness = inspect_perplexity_readiness(
            restored, environment={"RASAI_PERPLEXITY_ENABLED": "true",
                                   "PERPLEXITY_API_KEY": "fake"}
        )
        assert readiness["saved_draft_available"] is True
        assert readiness["queries_requested"] is False
        assert readiness["executable_request_pending"] is False

        restored.project = "Projeto novo"
        console_settings.save_console_config(restored, path)
        third = SearchConsoleState()
        console_settings.load_console_config(third, path)
        assert third.perplexity_draft_queries == ("seguro família", "seguro carro")
        assert third.perplexity_draft_search_type == "fast"
        assert third.perplexity_queries == ()
        assert third.perplexity_last_status == "NOT_REQUESTED"


def test_malformed_perplexity_draft_never_becomes_paid_request(tmp_path):
    _install_config_contract()
    path = tmp_path / "invalid.ini"
    path.write_text(
        "[perplexity_draft]\\nqueries = um;dois;três;quatro;cinco;seis\\n"
        "search_type = unknown\\n"
        "[environment]\\nRASAI_PERPLEXITY_ENABLED = true\\n",
        encoding="utf-8",
    )
    with patch.dict(os.environ, {}, clear=True):
        state = SearchConsoleState()
        result = console_settings.load_console_config(state, path)
        assert result.warnings
        assert state.perplexity_queries == ()
        assert state.perplexity_draft_queries == ()
        assert state.perplexity_last_status == "NOT_REQUESTED"
        assert state.perplexity_draft_search_type == "web"

