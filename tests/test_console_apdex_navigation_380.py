"""#380: effective Navigation editor must use the canonical concurrency policy.

Compose the actual interactive_console._configure, system_defaults.install, and the
#381 persistence wrapper; no network, browser or physical AUD is permitted.
"""
from __future__ import annotations

import builtins
from contextlib import redirect_stdout
from io import StringIO
import os
from types import ModuleType

import pytest

from rasai import console_apdex_configuration as apdex
from rasai import console_ui_refactor as persistence
from rasai import interactive_console
from rasai import system_defaults
from rasai.apdex_concurrency_policy import (
    NAVIGATION_MAX_CONCURRENCY, EXPERIENCE_MAX_CONCURRENCY,
    validate_navigation_concurrency,
)
from rasai.console_m23 import State


@pytest.fixture
def effective_console(monkeypatch, tmp_path):
    """Install real editor wrappers while isolating unrelated process-wide catalog patches."""
    console = ModuleType("rasai_console_380")
    console._menu = lambda state: "Q"
    console._configure = interactive_console._configure
    console.mark_dirty = lambda state, value=True: None
    saved = []
    destination = tmp_path / "rasai-console.ini"
    destination.write_text("original-ini-content\n", encoding="utf-8")

    def save(state):
        saved.append(True)
        destination.write_text("saved-content\n", encoding="utf-8")
        return True

    console._save_configuration = save
    monkeypatch.setattr(interactive_console, "render_header", lambda state: None)
    monkeypatch.setattr(interactive_console, "_configure_apdex", apdex.configure_apdex)
    monkeypatch.setattr(system_defaults, "_patch_environment_catalog", lambda: None)
    # Preserve global editor references/flags for other tests sharing this process.
    monkeypatch.setattr(apdex, "_show_experience_defaults", apdex._show_experience_defaults)
    monkeypatch.setattr(apdex, "_rasai_system_default_guidance", False, raising=False)
    canonical = apdex._configure_navigation
    system_defaults.install(console)
    assert apdex._configure_navigation is canonical  # no shadow editor
    persistence._install_configure_persistence(console)
    monkeypatch.setattr(apdex, "_configure_experience", lambda state: None)

    state = State(device="mobile")
    state.synthetic_apdex = True
    state.apdex_threshold = 3.0
    state.apdex_samples = 10
    state.apdex_max_attempts = 20
    state.apdex_max_pages = 1
    state.apdex_timeout = 45.0
    state.apdex_delay = 1.0
    state.apdex_concurrency = 1
    state.apdex_experience = False
    state.apdex_experience_concurrency = EXPERIENCE_MAX_CONCURRENCY
    return console, state, saved, destination


def _fake_navigation_inputs(monkeypatch, selected: int, pacing: float, *, approval=True):
    gates = []
    prompts = []

    monkeypatch.setattr(apdex, "_yes_no", lambda label, current: current)
    monkeypatch.setattr(apdex, "_required_positive", lambda label, current: current)

    def number(label, current, **kwargs):
        prompts.append(label)
        if label.startswith("Concorrência ("):
            return selected
        if label.startswith("Delay mínimo entre inícios"):
            return pacing
        return current
    monkeypatch.setattr(apdex, "_number", number)

    def confirm(phrase, *, action_label, **kwargs):
        gates.append((phrase, action_label))
        return approval
    monkeypatch.setattr(apdex, "confirm_sensitive", confirm)

    def answer(prompt=""):
        if prompt.startswith("Escolha"):
            return "1"  # positive edits remain in session, never write INI
        raise AssertionError(f"unexpected interactive prompt: {prompt}")
    monkeypatch.setattr(builtins, "input", answer)
    return prompts, gates


@pytest.mark.parametrize("concurrency,expected_risk,expected_gate", [
    (1, "BAIXO / RECOMENDADO", False),
    (3, "MODERADO", False),
    (4, "ALTO / AVANÇADO", True),
])
def test_effective_system_defaults_editor_enforces_navigation_risk(
    monkeypatch, effective_console, concurrency, expected_risk, expected_gate,
):
    console, state, saved, ini = effective_console
    prompts, gates = _fake_navigation_inputs(monkeypatch, concurrency, 1.0)
    output = StringIO()
    with redirect_stdout(output):
        console._configure(state, "11")

    rendered = output.getvalue()
    assert "Baseline operacional RASAi" in rendered
    assert "150 amostras" in rendered
    assert "Concorrência (1-4)" in prompts
    assert "Concorrência (1-2)" not in prompts
    assert f"Grau de risco: {expected_risk}" in rendered
    assert len(gates) == int(expected_gate)
    if expected_gate:
        assert gates == [("CONCORRÊNCIA", "Usar concorrência Navigation 4 - ALTO / AVANÇADO")]
    assert state.apdex_concurrency == concurrency
    assert state.apdex_experience_concurrency == EXPERIENCE_MAX_CONCURRENCY
    assert state.apdex_delay == 1.0
    assert saved == []
    assert ini.read_text(encoding="utf-8") == "original-ini-content\n"
    if concurrency > 1:
        assert "DESTINO DA ALTERAÇÃO" in rendered


@pytest.mark.parametrize("concurrency,pacing", [
    (0, 1.0), (5, 1.0), (3, 0.5), (4, 0.0),
])
def test_invalid_navigation_or_unsafe_pacing_does_not_persist(
    monkeypatch, effective_console, concurrency, pacing,
):
    console, state, saved, ini = effective_console
    before = persistence._fingerprint(state)
    old_env = dict(os.environ)
    prompts, gates = _fake_navigation_inputs(monkeypatch, concurrency, pacing)
    output = StringIO()
    with redirect_stdout(output):
        console._configure(state, "11")
    assert "Concorrência (1-4)" in prompts
    assert state.error
    assert state.apdex_concurrency == 1
    assert state.apdex_delay == 1.0
    assert persistence._fingerprint(state) == before
    assert dict(os.environ) == old_env
    assert saved == []
    assert not gates
    assert "DESTINO DA ALTERAÇÃO" not in output.getvalue()
    assert ini.read_text(encoding="utf-8") == "original-ini-content\n"


def test_legacy_four_requires_sensitive_confirmation_and_cancel_is_atomic(
    monkeypatch, effective_console,
):
    console, state, saved, ini = effective_console
    state.apdex_concurrency = NAVIGATION_MAX_CONCURRENCY
    state.apdex_delay = 1.0
    before = persistence._fingerprint(state)
    old_env = dict(os.environ)
    _, gates = _fake_navigation_inputs(monkeypatch, 4, 1.0, approval=False)
    output = StringIO()
    with redirect_stdout(output):
        console._configure(state, "11")
    assert len(gates) == 1
    assert state.operation == "LOCAL:APDEX_EDIT_CANCELLED"
    assert state.apdex_concurrency == 4  # no silent downgrade
    assert persistence._fingerprint(state) == before
    assert dict(os.environ) == old_env
    assert saved == []
    assert "DESTINO DA ALTERAÇÃO" not in output.getvalue()
    assert ini.read_text(encoding="utf-8") == "original-ini-content\n"


def test_experience_limit_is_not_raised_by_navigation_policy():
    assert NAVIGATION_MAX_CONCURRENCY == 4
    assert EXPERIENCE_MAX_CONCURRENCY == 3
    validate_navigation_concurrency(4, 1.0)
