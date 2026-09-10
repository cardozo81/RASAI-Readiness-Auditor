from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from rasai.console_config import is_secret
from rasai.console_environment import ENV_NAMES, SPECS
from rasai.console_m23 import State, apply_m23_environment_defaults
from rasai.console_settings import (
    _known_nonsecret_environment_names,
    _persisted_environment_values,
    _runtime_environment_projection,
)
from rasai.m25_cli import DEFAULT_UX_DEVICE_MIX, configured_experience, parse_device_mix


ROOT = Path(__file__).resolve().parents[1]


def test_disabled_experience_keeps_complete_coherent_defaults() -> None:
    cfg = configured_experience(SimpleNamespace(), {})
    assert cfg.enabled is False
    assert cfg.target_samples_per_page == 100
    assert cfg.max_attempts_per_page == 125
    assert cfg.max_pages == 1
    assert dict(cfg.device_mix) == dict(parse_device_mix(DEFAULT_UX_DEVICE_MIX))
    assert cfg.session_mode == "cold"
    assert cfg.kpm == "USER_ACTION_DURATION"
    assert cfg.errors_affect_apdex is True
    assert cfg.error_scope == "first-party"
    assert cfg.settle_seconds == 5.0
    assert cfg.delay_seconds == 1.0
    assert cfg.concurrency == 1


def test_experience_environment_overrides_are_projected_before_enablement() -> None:
    env = {
        "RASAI_APDEX_EXPERIENCE": "false",
        "RASAI_APDEX_EXPERIENCE_SAMPLES": "40",
        "RASAI_APDEX_EXPERIENCE_MAX_ATTEMPTS": "55",
        "RASAI_APDEX_EXPERIENCE_DEVICE_MIX": "mobile=50,desktop=40,tablet=10",
        "RASAI_APDEX_EXPERIENCE_SESSION_MODE": "warm",
    }
    state = State()
    issues = apply_m23_environment_defaults(state, env)
    assert issues == ()
    assert state.apdex_experience is False
    assert state.apdex_experience_samples == 40
    assert state.apdex_experience_max_attempts == 55
    assert state.apdex_experience_device_mix == "mobile=50,desktop=40,tablet=10"
    assert state.apdex_experience_session_mode == "warm"


def test_all_safe_console_environment_variables_are_ini_persistable() -> None:
    expected = {
        spec.name
        for spec in SPECS
        if not spec.sensitive and not is_secret(spec.name)
    }
    assert set(_known_nonsecret_environment_names()) == expected


def test_saved_configuration_contains_runtime_and_experience_defaults(monkeypatch) -> None:
    state = State()
    state.apdex_experience_device_mix = DEFAULT_UX_DEVICE_MIX
    # The helper also preserves advanced environment-only overrides. Isolate all
    # state-owned projections so this test cannot inherit mutable process state from
    # another test or from a developer shell.
    for name in _runtime_environment_projection(state):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("RASAI_REMOTE_TIMEOUT_SECONDS", "45")
    values = _persisted_environment_values(state)
    assert values["RASAI_DEVICE_CONTEXT"] == "mobile"
    assert values["RASAI_SYNTHETIC_APDEX"] == "false"
    assert values["RASAI_APDEX_EXPERIENCE"] == "false"
    assert values["RASAI_APDEX_EXPERIENCE_SAMPLES"] == "100"
    assert values["RASAI_APDEX_EXPERIENCE_DEVICE_MIX"] == DEFAULT_UX_DEVICE_MIX
    assert values["RASAI_REMOTE_TIMEOUT_SECONDS"] == "45"


def test_every_configuration_has_default_or_explicit_conditional_requirement() -> None:
    for spec in SPECS:
        if spec.default is not None or spec.sensitive:
            continue
        assert spec.required_when != "Nunca; override opcional.", spec.name


def test_environment_reference_document_covers_the_console_catalog() -> None:
    text = (ROOT / "docs" / "ENVIRONMENT_VARIABLES.md").read_text(encoding="utf-8")
    missing = sorted(name for name in ENV_NAMES if name not in text)
    assert not missing, "environment variables missing from documentation: " + ", ".join(missing)
