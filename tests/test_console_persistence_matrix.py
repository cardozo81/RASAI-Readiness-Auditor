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

import pytest

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
    from rasai.console_perplexity_readiness import inspect_perplexity_readiness

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
        "[perplexity_draft]\nqueries = um;dois;três;quatro;cinco;seis\n"
        "search_type = unknown\n"
        "[environment]\nRASAI_PERPLEXITY_ENABLED = true\n",
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




def test_saved_serp_controls_reach_real_runtime_adapter_after_restart_without_requests(
    tmp_path,
):
    """A saved public SERP setting must reach its canonical consumer, not just INI."""
    from rasai.search_intelligence.config import SerpRuntimeConfig

    _install_config_contract()
    configured = {
        "RASAI_SERP_MODE": "disabled",
        "RASAI_SERP_PROVIDER": "serpapi",
        "RASAI_SERP_MAX_QUERIES": "3",
        "RASAI_SERP_MAX_REQUESTS": "5",
        "RASAI_SERP_MAX_DEPTH": "12",
        "RASAI_SERP_MAX_COMPETITORS": "2",
        "RASAI_SERP_TIMEOUT_SECONDS": "9.5",
        "RASAI_SERP_RETRIES": "0",
        "RASAI_SERP_MIN_INTERVAL_SECONDS": "0.75",
    }
    with patch.dict(os.environ, {}, clear=True):
        os.environ.update(configured)
        path = tmp_path / "serp.ini"
        console_settings.save_console_config(SearchConsoleState(), path)
        original = path.read_bytes()
        # Simulate an independently started process with no caller authorization.
        os.environ.clear()
        after = SearchConsoleState()
        restored = console_settings.load_console_config(after, path)
        assert restored.warnings == () and restored.created is False
        runtime = SerpRuntimeConfig.from_environment(dict(os.environ))
        assert runtime.mode == "disabled"
        assert runtime.provider == "serpapi"
        assert runtime.max_queries == 3
        assert runtime.max_requests == 5
        assert runtime.max_depth == 12
        assert runtime.max_competitors == 2
        assert runtime.timeout_seconds == 9.5
        assert runtime.retries == 0
        assert runtime.min_interval_seconds == 0.75
        assert runtime.force_refresh is False
        assert after.perplexity_queries == ()
        assert path.read_bytes() == original



@pytest.mark.parametrize(("requested", "expected_state"), [
    ("false", "DISABLED"),
    ("true", "NOT_CONFIGURED"),
])
def test_saved_gsc_scope_policy_reaches_real_consumer_without_oauth_or_requests(
    tmp_path, requested, expected_state,
):
    """Configuration is effective; persisted site URL is not OAuth consent."""
    from rasai.gsc_scope import (
        assess_gsc_target, gsc_request_mode,
        GSC_ENABLED_ENV, GSC_SITE_URL_ENV, GSC_TOKEN_ENV,
    )
    from rasai.standards_gsc_policy import (
        GSC_SEARCH_ANALYTICS_DAYS_ENV, GSC_SEARCH_MAX_ROWS_ENV,
        GSC_FINAL_DATA_LAG_DAYS_ENV, search_analytics_days,
        search_max_rows, final_data_lag_days,
    )

    _install_config_contract()
    configured = {
        GSC_ENABLED_ENV: requested,
        GSC_SITE_URL_ENV: "sc-domain:example.org",
        GSC_SEARCH_ANALYTICS_DAYS_ENV: "7",
        GSC_SEARCH_MAX_ROWS_ENV: "97",
        GSC_FINAL_DATA_LAG_DAYS_ENV: "5",
    }
    with patch.dict(os.environ, {}, clear=True):
        os.environ.update(configured)
        path = tmp_path / "gsc-policy.ini"
        console_settings.save_console_config(SearchConsoleState(), path)
        data_before = path.read_bytes()
        # A fresh process must not inherit provider credentials or tokens.
        os.environ.clear()
        restored = SearchConsoleState()
        result = console_settings.load_console_config(restored, path)
        assert result.warnings == () and result.created is False
        assert GSC_TOKEN_ENV not in os.environ
        assert gsc_request_mode(os.environ) == (
            "disabled" if requested == "false" else "required"
        )
        scope = assess_gsc_target("https://www.example.org/test", dict(os.environ))
        assert scope.state == expected_state
        assert not scope.eligible
        assert scope.token_present is False
        assert scope.blocking == (requested == "true")
        assert search_analytics_days(os.environ[GSC_SEARCH_ANALYTICS_DAYS_ENV]) == 7
        assert search_max_rows(os.environ[GSC_SEARCH_MAX_ROWS_ENV]) == 97
        assert final_data_lag_days(os.environ[GSC_FINAL_DATA_LAG_DAYS_ENV]) == 5
        assert restored.perplexity_queries == ()
        assert path.read_bytes() == data_before


@pytest.mark.parametrize(
    ("requested", "maximum", "timeout", "language"),
    [
        ("false", 11, 42.5, "pt-BR"),
        ("true", 27, 73.5, "en-US"),
    ],
)
def test_saved_improvement_runtime_contract_consumes_nondefault_fields_without_provider(
    tmp_path, requested, maximum, timeout, language,
):
    """The actual improvement adapter receives restored settings without an AI call."""
    from rasai.improvement_intelligence import ImprovementConfig

    _install_config_contract()
    with patch.dict(os.environ, {}, clear=True):
        os.environ.update({
            "RASAI_IMPROVEMENT_INTELLIGENCE": requested,
            "RASAI_IMPROVEMENT_MAX_RECOMMENDATIONS": str(maximum),
            "RASAI_IMPROVEMENT_AI_TIMEOUT_SECONDS": str(timeout),
            "RASAI_AI_ANALYSIS_LANGUAGE": language,
        })
        path = tmp_path / "improvement.ini"
        console_settings.save_console_config(SearchConsoleState(), path)
        immutable = path.read_bytes()
        os.environ.clear()
        result = console_settings.load_console_config(SearchConsoleState(), path)
        assert result.warnings == ()
        assert not result.created
        effective = ImprovementConfig.from_environment(dict(os.environ))
        assert effective.enabled == (requested == "true")
        assert effective.max_recommendations == maximum
        assert effective.timeout_seconds == timeout
        assert effective.language == language
        assert effective.provider in {"", "none"}
        assert path.read_bytes() == immutable


@pytest.mark.parametrize("timezone", ["America/Sao_Paulo", "UTC", "Europe/Lisbon"])
def test_saved_presentation_timezone_reaches_canonical_consumer(tmp_path, timezone):
    """INI restoration must affect the effective timezone, not just file contents."""
    from rasai.time_contract import configured_presentation_timezone

    _install_config_contract()
    with patch.dict(os.environ, {}, clear=True):
        os.environ["RASAI_PRESENTATION_TIMEZONE"] = timezone
        path = tmp_path / "timezone.ini"
        console_settings.save_console_config(SearchConsoleState(), path)
        immutable = path.read_bytes()
        os.environ.clear()
        result = console_settings.load_console_config(SearchConsoleState(), path)
        assert result.warnings == ()
        assert configured_presentation_timezone(dict(os.environ)) == timezone
        assert path.read_bytes() == immutable


@pytest.mark.parametrize(
    ("requested", "timeout", "expected"),
    [("true", "7.25", True), ("false", "31.5", False)],
)
def test_saved_passive_security_controls_reach_actual_offline_runtime_policy(
    tmp_path, requested, timeout, expected,
):
    """Cross the real INI loader and consumer without collecting or invoking services."""
    from rasai.passive_security import enabled, external_timeout

    _install_config_contract()
    with patch.dict(os.environ, {}, clear=True):
        os.environ.update({
            "RASAI_PASSIVE_SECURITY": requested,
            "RASAI_SECURITY_EXTERNAL_TIMEOUT_SECONDS": timeout,
            "RASAI_SECURITY_OSV": "false",
            "RASAI_SECURITY_CISA_KEV": "false",
        })
        path = tmp_path / "security.ini"
        console_settings.save_console_config(SearchConsoleState(), path)
        original = path.read_bytes()
        os.environ.clear()
        result = console_settings.load_console_config(SearchConsoleState(), path)
        assert result.warnings == ()
        assert not result.created
        assert enabled(dict(os.environ)) is expected
        assert external_timeout(dict(os.environ)) == float(timeout)
        # Remote feeds remain hard-disabled; neither function performs I/O.
        assert os.environ["RASAI_SECURITY_OSV"] == "false"
        assert os.environ["RASAI_SECURITY_CISA_KEV"] == "false"
        assert path.read_bytes() == original


@pytest.mark.parametrize(
    ("module_name", "source_key", "file_key", "settings_name", "loader_name"),
    [
        ("rasai.ai_model_catalog", "RASAI_AI_MODELS_SOURCE",
         "RASAI_AI_MODELS_FILE", "model_runtime_settings", "load_model_catalog"),
        ("rasai.ai_pricing_catalog", "RASAI_AI_PRICING_SOURCE",
         "RASAI_AI_PRICING_FILE", "pricing_runtime_settings", "load_pricing_catalog"),
        ("rasai.ai_task_profiles", "RASAI_AI_TASK_PROFILES_SOURCE",
         "RASAI_AI_TASK_PROFILES_FILE", "task_profile_runtime_settings",
         "load_task_profile_catalog"),
    ],
)
def test_restored_ai_catalog_selectors_reach_real_offline_loaders(
    tmp_path, module_name, source_key, file_key, settings_name, loader_name,
):
    """Prove restored catalog selections reach actual consumers without network."""
    from importlib import import_module

    _install_config_contract()
    target = tmp_path / "absent-catalog.toml"
    with patch.dict(os.environ, {}, clear=True):
        os.environ.update({source_key: "auto", file_key: str(target)})
        ini = tmp_path / "catalog.ini"
        console_settings.save_console_config(SearchConsoleState(), ini)
        before = ini.read_bytes()
        os.environ.clear()
        result = console_settings.load_console_config(SearchConsoleState(), ini)
        assert not result.created and result.warnings == ()
        module = import_module(module_name)
        source, path = getattr(module, settings_name)(env=dict(os.environ), cwd=tmp_path)
        assert source == "auto" and path == target.resolve()
        # Missing optional override falls back to factory: never a provider call.
        assert getattr(module, loader_name)(env=dict(os.environ), cwd=tmp_path)
        assert ini.read_bytes() == before
        assert not target.exists()


@pytest.mark.parametrize("secret_key", ["api_token", "API_KEY", "password", "clientSecret", "Authorization"])
def test_dynatrace_export_with_embedded_credentials_is_not_written_to_ini(
    tmp_path, secret_key,
):
    """Typed non-secret JSON may not smuggle credentials into the operator INI."""
    import json
    _install_config_contract()
    with patch.dict(os.environ, {}, clear=True):
        state = SearchConsoleState()
        state.apdex_dynatrace_config_json = json.dumps({
            "load_action": "VISUALLY_COMPLETE",
            "nested": [{secret_key: "NO_PERSIST_SECRET_VALUE"}],
        })
        path = tmp_path / "operator.ini"
        with pytest.raises(ValueError, match="credencial nao persistiveis"):
            console_settings.save_console_config(state, path)
        assert not path.exists()
        assert "NO_PERSIST_SECRET_VALUE" not in str(os.environ)
        state.apdex_dynatrace_config_json = '{"load_action":"VISUALLY_COMPLETE"}'
        console_settings.save_console_config(state, path)
        assert "NO_PERSIST_SECRET_VALUE" not in path.read_text(encoding="utf-8")


def test_dynatrace_secret_hidden_in_environment_json_cannot_be_saved(tmp_path):
    """The registry nonsecret label cannot override a credential-bearing value."""
    with patch.dict(os.environ, {}, clear=True):
        os.environ["RASAI_DYNATRACE_CONFIG_JSON"] = (
            '{"settings":{"API_KEY":"DONT_SAVE_THIS_SECRET"}}'
        )
        state = SearchConsoleState()
        path = tmp_path / "safe.ini"
        with pytest.raises(ValueError, match="credencial nao persistiveis"):
            console_settings.save_console_config(state, path)
        assert not path.exists()


def test_malicious_dynatrace_json_in_ini_does_not_restore_secret(tmp_path):
    """A tampered INI cannot populate state or process environment with embedded keys."""
    from configparser import ConfigParser
    import json
    _install_config_contract()
    with patch.dict(os.environ, {}, clear=True):
        state = SearchConsoleState()
        path = tmp_path / "tampered.ini"
        console_settings.save_console_config(state, path)
        cfg = ConfigParser(interpolation=None)
        cfg.optionxform = str
        cfg.read(path, encoding="utf-8")
        secret = json.dumps({"nested": {"api_token": "MUST_NOT_REHYDRATE"}})
        cfg["environment"]["RASAI_DYNATRACE_CONFIG_JSON"] = secret
        cfg["synthetic_apdex_experience"]["dynatrace_config_json"] = secret
        with path.open("w", encoding="utf-8") as out:
            cfg.write(out)
        before = path.read_bytes()
        restored = SearchConsoleState()
        result = console_settings.load_console_config(restored, path)
        assert result.warnings
        assert restored.apdex_dynatrace_config_json != secret
        assert os.environ.get("RASAI_DYNATRACE_CONFIG_JSON") != secret
        assert path.read_bytes() == before
