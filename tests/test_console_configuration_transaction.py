from __future__ import annotations

from configparser import ConfigParser

import pytest

from rasai import console_configuration_transaction as transaction
from rasai import console_provider_environment as environment
from rasai import console_settings
from rasai import console_ui_catalog as ui_catalog
from rasai.console_m23 import M23_ENV_NAMES, apply_m23_environment_defaults
from rasai.console_search_intelligence import SearchConsoleState
from rasai.m23_cli import APDEX_MAX_ATTEMPTS_ENV, APDEX_SAMPLES_ENV
from rasai.m25_cli import M25_ENV_NAMES, UX_MAX_ATTEMPTS_ENV, UX_SAMPLES_ENV


def _prepare_apdex(monkeypatch: pytest.MonkeyPatch, *, samples: int, attempts: int) -> SearchConsoleState:
    for name in dict.fromkeys((*M23_ENV_NAMES, *M25_ENV_NAMES)):
        monkeypatch.delenv(name, raising=False)

    values = {
        "RASAI_SYNTHETIC_APDEX": "true",
        "RASAI_APDEX_THRESHOLD_SECONDS": "1",
        APDEX_SAMPLES_ENV: str(samples),
        APDEX_MAX_ATTEMPTS_ENV: str(attempts),
        "RASAI_APDEX_MAX_PAGES": "1",
        "RASAI_APDEX_TIMEOUT_SECONDS": "10",
        "RASAI_APDEX_DELAY_SECONDS": "0",
        "RASAI_APDEX_CONCURRENCY": "1",
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)

    state = SearchConsoleState()
    assert apply_m23_environment_defaults(state) == ()
    return state



def _prepare_experience_apdex(
    monkeypatch: pytest.MonkeyPatch,
    *,
    samples: int,
    attempts: int,
) -> SearchConsoleState:
    state = _prepare_apdex(monkeypatch, samples=1, attempts=2)
    values = {
        "RASAI_APDEX_EXPERIENCE": "true",
        UX_SAMPLES_ENV: str(samples),
        UX_MAX_ATTEMPTS_ENV: str(attempts),
        "RASAI_APDEX_EXPERIENCE_MAX_PAGES": "1",
        "RASAI_APDEX_EXPERIENCE_DEVICE_MIX": "mobile=60,desktop=35,tablet=5",
        "RASAI_APDEX_EXPERIENCE_SESSION_MODE": "cold",
        "RASAI_APDEX_EXPERIENCE_KPM": "USER_ACTION_DURATION",
        "RASAI_APDEX_EXPERIENCE_SATISFIED_SECONDS": "3",
        "RASAI_APDEX_EXPERIENCE_FRUSTRATED_SECONDS": "12",
        "RASAI_APDEX_EXPERIENCE_ERRORS_AFFECT": "true",
        "RASAI_APDEX_EXPERIENCE_ERROR_SCOPE": "first-party",
        "RASAI_APDEX_EXPERIENCE_SETTLE_SECONDS": "5",
        "RASAI_APDEX_EXPERIENCE_DELAY_SECONDS": "1",
        "RASAI_APDEX_EXPERIENCE_CONCURRENCY": "1",
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)

    assert apply_m23_environment_defaults(state) == ()
    return state


def _spec(name: str):
    return next(spec for spec in environment.refresh_specs() if spec.name == name)


@pytest.fixture
def transactional_apply():
    original = ui_catalog._apply
    transaction.install(ui_catalog)
    try:
        yield ui_catalog._apply
    finally:
        ui_catalog._apply = original


def test_samples_increase_reconciles_attempt_budget_before_runtime_validation(
    monkeypatch: pytest.MonkeyPatch,
    transactional_apply,
) -> None:
    state = _prepare_apdex(monkeypatch, samples=1, attempts=2)

    transactional_apply(state, _spec(APDEX_SAMPLES_ENV), "10")

    assert state.error == ""
    assert state.apdex_samples == 10
    assert state.apdex_max_attempts == 13
    assert environment.os.environ[APDEX_SAMPLES_ENV] == "10"
    assert environment.os.environ[APDEX_MAX_ATTEMPTS_ENV] == "13"


def test_transactional_edit_survives_ini_save_and_reload(
    monkeypatch: pytest.MonkeyPatch,
    transactional_apply,
    tmp_path,
) -> None:
    state = _prepare_apdex(monkeypatch, samples=1, attempts=2)
    transactional_apply(state, _spec(APDEX_SAMPLES_ENV), "10")

    destination = tmp_path / "rasai-console.ini"
    console_settings.save_console_config(state, destination)

    parser = ConfigParser(interpolation=None)
    parser.optionxform = str
    parser.read(destination, encoding="utf-8")
    assert parser.get("synthetic_apdex", "samples_per_context") == "10"
    assert parser.get("synthetic_apdex", "max_attempts_per_context") == "13"
    assert parser.get("environment", APDEX_SAMPLES_ENV) == "10"
    assert parser.get("environment", APDEX_MAX_ATTEMPTS_ENV) == "13"

    for name in dict.fromkeys((*M23_ENV_NAMES, *M25_ENV_NAMES)):
        monkeypatch.delenv(name, raising=False)

    restored = SearchConsoleState()
    console_settings.load_console_config(restored, destination)
    assert restored.apdex_samples == 10
    assert restored.apdex_max_attempts == 13


def test_invalid_dependent_edit_rolls_back_environment_and_state(
    monkeypatch: pytest.MonkeyPatch,
    transactional_apply,
) -> None:
    state = _prepare_apdex(monkeypatch, samples=10, attempts=13)

    with pytest.raises(ValueError, match="max_attempts_per_context"):
        transactional_apply(state, _spec(APDEX_MAX_ATTEMPTS_ENV), "5")

    assert environment.os.environ[APDEX_SAMPLES_ENV] == "10"
    assert environment.os.environ[APDEX_MAX_ATTEMPTS_ENV] == "13"
    assert state.apdex_samples == 10
    assert state.apdex_max_attempts == 13


def test_experience_samples_increase_reconciles_attempt_budget_before_runtime_validation(
    monkeypatch: pytest.MonkeyPatch,
    transactional_apply,
) -> None:
    state = _prepare_experience_apdex(monkeypatch, samples=2, attempts=3)

    transactional_apply(state, _spec(UX_SAMPLES_ENV), "120")

    assert state.error == ""
    assert state.apdex_experience_samples == 120
    assert state.apdex_experience_max_attempts == 150
    assert environment.os.environ[UX_SAMPLES_ENV] == "120"
    assert environment.os.environ[UX_MAX_ATTEMPTS_ENV] == "150"


def test_experience_transactional_edit_survives_ini_save_and_reload(
    monkeypatch: pytest.MonkeyPatch,
    transactional_apply,
    tmp_path,
) -> None:
    state = _prepare_experience_apdex(monkeypatch, samples=2, attempts=3)
    transactional_apply(state, _spec(UX_SAMPLES_ENV), "120")

    destination = tmp_path / "rasai-console.ini"
    console_settings.save_console_config(state, destination)

    parser = ConfigParser(interpolation=None)
    parser.optionxform = str
    parser.read(destination, encoding="utf-8")
    assert parser.get("synthetic_apdex_experience", "samples_per_page") == "120"
    assert parser.get("synthetic_apdex_experience", "max_attempts_per_page") == "150"
    assert parser.get("environment", UX_SAMPLES_ENV) == "120"
    assert parser.get("environment", UX_MAX_ATTEMPTS_ENV) == "150"

    for name in dict.fromkeys((*M23_ENV_NAMES, *M25_ENV_NAMES)):
        monkeypatch.delenv(name, raising=False)

    restored = SearchConsoleState()
    console_settings.load_console_config(restored, destination)
    assert restored.apdex_experience_samples == 120
    assert restored.apdex_experience_max_attempts == 150


def test_invalid_experience_attempt_budget_rolls_back_environment_and_state(
    monkeypatch: pytest.MonkeyPatch,
    transactional_apply,
) -> None:
    state = _prepare_experience_apdex(monkeypatch, samples=120, attempts=150)

    with pytest.raises(ValueError, match="max_attempts_per_page"):
        transactional_apply(state, _spec(UX_MAX_ATTEMPTS_ENV), "100")

    assert environment.os.environ[UX_SAMPLES_ENV] == "120"
    assert environment.os.environ[UX_MAX_ATTEMPTS_ENV] == "150"
    assert state.apdex_experience_samples == 120
    assert state.apdex_experience_max_attempts == 150
