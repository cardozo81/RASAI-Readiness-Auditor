"""Regression: console configuration reuse restores only an explicit architecture choice."""
from types import SimpleNamespace

from rasai.architecture_choice import ArchitectureChoice
from rasai.architecture_choice_audit_adapter import prepare_audit_choice_configuration
from rasai.audit_configuration_reuse_console import _apply_settings


def _state():
    return SimpleNamespace(target="", input_mode="", architecture_choice=None,
                           search_queries=())


def test_reuse_explicit_architecture_choice(monkeypatch):
    from rasai import console_settings
    monkeypatch.setattr(console_settings, "_known_nonsecret_environment_names", lambda: ())
    monkeypatch.setattr(console_settings, "_state_values", lambda state: {})
    monkeypatch.setattr(console_settings, "sync_nonsecret_runtime_environment", lambda state: None)
    state = _state()
    config = prepare_audit_choice_configuration(
        {"settings": {}, "targets": ["https://example.org"]},
        choice=ArchitectureChoice("DECLARED", "HYDRATED"),
    )
    assert _apply_settings(state, config, "AUD-TEST") == ()
    assert state.architecture_choice == ArchitectureChoice("DECLARED", "HYDRATED")


def test_reuse_legacy_source_clears_previous_architecture(monkeypatch):
    from rasai import console_settings
    monkeypatch.setattr(console_settings, "_known_nonsecret_environment_names", lambda: ())
    monkeypatch.setattr(console_settings, "_state_values", lambda state: {})
    monkeypatch.setattr(console_settings, "sync_nonsecret_runtime_environment", lambda state: None)
    state = _state()
    state.architecture_choice = ArchitectureChoice("AUTO")
    _apply_settings(state, {"settings": {}, "targets": ["https://example.org"]}, "AUD-OLD")
    assert state.architecture_choice is None
