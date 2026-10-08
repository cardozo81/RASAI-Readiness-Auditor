from __future__ import annotations

import os
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from rasai.console_m23 import State, apply_m23_environment_defaults
from rasai.standards_console_runtime import install as install_standards_console_runtime
from rasai.standards_runtime import install_pre_context
from rasai.system_default_dependencies import install as install_system_default_dependencies
from rasai.system_defaults import (
    LOW_LOAD_EXPERIENCE_SAMPLES,
    LOW_LOAD_NAVIGATION_SAMPLES,
    REPRESENTATIVE_APDEX_SAMPLES,
    apply_structured_defaults,
    canonical_environment_defaults,
    load_console_config_with_system_defaults,
    load_system_defaults,
    restore_program_defaults,
)


def _install_standards_catalog() -> None:
    install_pre_context()
    install_standards_console_runtime()


def test_packaged_defaults_enable_maximum_credential_free_baseline() -> None:
    parser = load_system_defaults()
    assert parser.getboolean("synthetic_apdex", "enabled") is True
    assert parser.getfloat("synthetic_apdex", "threshold_seconds") == 3.0
    assert parser.getint("synthetic_apdex", "samples_per_context") == LOW_LOAD_NAVIGATION_SAMPLES == 150
    assert parser.getboolean("synthetic_apdex_experience", "enabled") is True
    assert parser.getint("synthetic_apdex_experience", "samples_per_page") == LOW_LOAD_EXPERIENCE_SAMPLES == 100
    assert REPRESENTATIVE_APDEX_SAMPLES == 100

    for name in (
        "RASAI_DERIVED_READINESS_METRICS",
        "RASAI_RETRIEVAL_METRICS",
        "RASAI_OPEN_WEB_METRICS",
        "RASAI_W3C_VALIDATOR",
        "RASAI_W3C_CSS_VALIDATOR",
        "RASAI_MDN_OBSERVATORY",
        "RASAI_WEB_PLATFORM_BASELINE",
    ):
        assert parser.getboolean("environment", name) is True
    assert parser.get("environment", "RASAI_WEB_FEATURES_DATASET") == "auto"
    assert parser.get("environment", "RASAI_PERPLEXITY_ENABLED") == "true"

    # Credential-driven services stay AUTO-by-requirements: the defaults file must not
    # materialize an explicit hard-on/hard-off that defeats credential discovery.
    assert not parser.has_option("environment", "RASAI_PAGESPEED_ENABLED")
    assert not parser.has_option("environment", "RASAI_CRUX_ENABLED")
    assert not parser.has_option("environment", "RASAI_GSC_ENABLED")


def test_canonical_environment_defaults_accept_runtime_configuration_extensions(monkeypatch) -> None:
    from rasai import console_settings as settings

    original_values = settings._state_values
    original_assign = settings._assign

    def extended_values(state):
        values = dict(original_values(state))
        values["improvement_intelligence"] = {
            "enabled": "false",
        }
        return values

    def extended_assign(state, section: str, option: str, raw: str) -> None:
        if (section, option) == ("improvement_intelligence", "enabled"):
            state.improvement_enabled = settings._parse_bool(raw)
            return
        original_assign(state, section, option, raw)

    monkeypatch.setattr(settings, "_state_values", extended_values)
    monkeypatch.setattr(settings, "_assign", extended_assign)

    defaults = canonical_environment_defaults()

    assert defaults["RASAI_SYNTHETIC_APDEX"] == "true"
    assert defaults["RASAI_APDEX_SAMPLES_PER_CONTEXT"] == "150"
    assert defaults["RASAI_APDEX_EXPERIENCE"] == "true"


def test_structured_defaults_apply_low_load_apdex_and_dynatrace_compatible_thresholds() -> None:
    state = State()
    warnings = apply_structured_defaults(state)
    assert warnings == ()
    assert state.synthetic_apdex is True
    assert state.apdex_threshold == 3.0
    assert state.apdex_samples == 150
    assert state.apdex_max_attempts == 188
    assert state.apdex_experience is True
    assert state.apdex_experience_samples == 100
    assert state.apdex_experience_max_attempts == 125
    assert state.apdex_experience_kpm == "USER_ACTION_DURATION"
    assert state.apdex_experience_satisfied == 3.0
    assert state.apdex_experience_frustrated == 12.0


def test_missing_user_ini_is_created_from_system_defaults_and_external_free_services_are_on() -> None:
    _install_standards_catalog()
    with TemporaryDirectory() as directory, patch.dict(os.environ, {}, clear=True):
        path = Path(directory) / "rasai-console.ini"
        state = State()
        result = load_console_config_with_system_defaults(state, path)
        assert result.created is True
        assert state.synthetic_apdex is True
        assert state.apdex_samples == 150
        assert state.apdex_experience is True
        assert state.apdex_experience_samples == 100
        assert os.environ["RASAI_W3C_VALIDATOR"] == "true"
        assert os.environ["RASAI_W3C_CSS_VALIDATOR"] == "true"
        assert os.environ["RASAI_MDN_OBSERVATORY"] == "true"
        assert os.environ["RASAI_WEB_PLATFORM_BASELINE"] == "true"
        assert os.environ["RASAI_WEB_FEATURES_DATASET"] == "auto"
        text = path.read_text(encoding="utf-8")
        assert "enabled = true" in text
        assert "samples_per_context = 150" in text
        assert "samples_per_page = 100" in text
        assert "RASAI_WEB_FEATURES_DATASET = auto" in text
        assert "RASAI_PERPLEXITY_ENABLED = true" in text
        assert "OPENAI_API_KEY" not in text


def test_first_run_preserves_explicit_environment_precedence() -> None:
    _install_standards_catalog()
    with TemporaryDirectory() as directory, patch.dict(
        os.environ,
        {"RASAI_SYNTHETIC_APDEX": "false", "RASAI_APDEX_EXPERIENCE": "true"},
        clear=True,
    ):
        path = Path(directory) / "rasai-console.ini"
        state = State()
        result = load_console_config_with_system_defaults(state, path)
        assert result.created is True
        # The system baseline is what gets materialized in the newly-created INI,
        # but the incoming process/OS override must survive the writer unchanged.
        assert state.synthetic_apdex is True
        assert os.environ["RASAI_SYNTHETIC_APDEX"] == "false"

        # CAT-06 and CAT-07 are independent. An explicit Navigation=OFF must not
        # suppress an explicit Experience=ON supplied at the same precedence.
        adapter = SimpleNamespace(
            apply_m23_environment_defaults=apply_m23_environment_defaults,
        )
        install_system_default_dependencies(adapter)
        issues = adapter.apply_m23_environment_defaults(
            state,
            names={"RASAI_SYNTHETIC_APDEX"},
        )
        assert issues == ()
        assert state.synthetic_apdex is False
        assert state.apdex_experience is True


def test_user_ini_still_overrides_system_defaults() -> None:
    _install_standards_catalog()
    with TemporaryDirectory() as directory, patch.dict(os.environ, {}, clear=True):
        path = Path(directory) / "rasai-console.ini"
        path.write_text(
            "[console]\n"
            "config_version = 4\n\n"
            "[synthetic_apdex]\n"
            "enabled = false\n"
            "threshold_seconds = 2\n"
            "samples_per_context = 7\n"
            "max_attempts_per_context = 9\n"
            "max_pages = 1\n"
            "timeout_seconds = 45\n"
            "delay_seconds = 1\n"
            "concurrency = 1\n\n"
            "[synthetic_apdex_experience]\n"
            "enabled = false\n"
            "samples_per_page = 40\n"
            "max_attempts_per_page = 50\n"
            "max_pages = 1\n"
            "device_mix = mobile=60,desktop=35,tablet=5\n"
            "session_mode = cold\n"
            "kpm = USER_ACTION_DURATION\n"
            "satisfied_seconds = 3\n"
            "frustrated_seconds = 12\n"
            "errors_affect_apdex = true\n"
            "javascript_errors_affect_apdex = true\n"
            "request_errors_affect_apdex = true\n"
            "console_errors_affect_apdex = false\n"
            "error_scope = all\n"
            "settle_seconds = 5\n"
            "delay_seconds = 1\n"
            "concurrency = 1\n"
            "dynatrace_import = false\n",
            encoding="utf-8",
        )
        state = State()
        result = load_console_config_with_system_defaults(state, path)
        assert result.created is False
        assert state.synthetic_apdex is False
        assert state.apdex_threshold == 2.0
        assert state.apdex_samples == 7
        assert state.apdex_experience is False
        assert state.apdex_experience_samples == 40


def test_perplexity_explicit_false_survives_load_and_global_restore_sets_true() -> None:
    _install_standards_catalog()
    with TemporaryDirectory() as directory, patch.dict(
        os.environ, {"PERPLEXITY_API_KEY": "opaque-key"}, clear=True
    ), patch("rasai.system_defaults.machine_environment_value", return_value=None), patch(
        "rasai.system_defaults.user_environment_value", return_value=None
    ):
        path = Path(directory) / "rasai-console.ini"
        path.write_text(
            "[console]\\nconfig_version = 4\\n[environment]\\nRASAI_PERPLEXITY_ENABLED = false\\n",
            encoding="utf-8",
        )
        state = State()
        result = load_console_config_with_system_defaults(state, path)
        assert result.warnings == ()
        assert os.environ["RASAI_PERPLEXITY_ENABLED"] == "false"
        assert "opaque-key" not in path.read_text(encoding="utf-8")
        restored = restore_program_defaults(state, clear_credentials=False, path=path)
        assert restored.warnings == ()
        assert os.environ["RASAI_PERPLEXITY_ENABLED"] == "true"
        assert os.environ["PERPLEXITY_API_KEY"] == "opaque-key"
        assert "RASAI_PERPLEXITY_ENABLED = true" in path.read_text(encoding="utf-8")


def test_restore_preserves_or_clears_credentials_only_when_selected() -> None:
    _install_standards_catalog()
    with TemporaryDirectory() as directory, patch.dict(
        os.environ,
        {"OPENAI_API_KEY": "sk-preserve", "RASAI_W3C_VALIDATOR": "false"},
        clear=True,
    ), patch("rasai.system_defaults.machine_environment_value", return_value=None), patch(
        "rasai.system_defaults.user_environment_value", return_value=None
    ):
        first_path = Path(directory) / "preserve.ini"
        state = State()
        result = restore_program_defaults(state, clear_credentials=False, path=first_path)
        assert result.warnings == ()
        assert os.environ["OPENAI_API_KEY"] == "sk-preserve"
        assert os.environ["RASAI_W3C_VALIDATOR"] == "true"
        assert os.environ["RASAI_WEB_FEATURES_DATASET"] == "auto"
        assert state.synthetic_apdex is True
        assert state.apdex_experience_samples == 100

        second_path = Path(directory) / "clear.ini"
        result = restore_program_defaults(state, clear_credentials=True, path=second_path)
        assert result.warnings == ()
        assert "OPENAI_API_KEY" not in os.environ
        assert "OPENAI_API_KEY" not in second_path.read_text(encoding="utf-8")
