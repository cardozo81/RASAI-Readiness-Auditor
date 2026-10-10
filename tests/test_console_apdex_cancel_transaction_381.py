"""#381: cancellation must survive the effective console wrapper composition.

Only fake responses, synthetic environment overrides and a temporary INI are used.
There is no audit runner, browser navigation or external provider.
"""
from __future__ import annotations

import builtins
from contextlib import redirect_stdout
from io import StringIO
import os
from types import ModuleType

import pytest

from rasai import console_apdex_configuration as apdex
from rasai import console_ui_refactor as refactor
from rasai import system_defaults
from rasai.console_input_contract import EditCancelled
from rasai.console_m23 import State


@pytest.fixture(autouse=True)
def _reset_wrapper_metadata():
    refactor._SESSION_META.clear()
    try:
        yield
    finally:
        refactor._SESSION_META.clear()


def _state() -> State:
    state = State(device="desktop")
    state.synthetic_apdex = True
    state.apdex_threshold = 3.0
    state.apdex_samples = 10
    state.apdex_concurrency = 4
    state.apdex_delay = 1.0
    state.apdex_experience = True
    state.apdex_experience_profile_mode = "DYNATRACE_GUIDED"
    state.apdex_experience_architecture = "CSR_SPA"
    state.apdex_experience_concurrency = 3
    state.apdex_experience_delay = 1.0
    state.apdex_experience_satisfied = 5.0
    state.apdex_experience_frustrated = 20.0
    # Non-default value exposes the side effect of _ensure_mix before rollback.
    state.apdex_experience_device_mix = "mobile=50,desktop=50,tablet=0"
    state.operation = "LOCAL:APDEX_EDIT_CANCELLED"  # stale previous cancellation
    refactor._set_mix_inherited(state, False)
    return state


def _compose(monkeypatch, tmp_path):
    """Compose the two wrappers in the same order as the public entrypoint."""
    console = ModuleType("console_381")
    console._menu = lambda state: "Q"
    console.render_header = lambda state: None
    console._configure = lambda state, choice: apdex.configure_apdex(state) if choice == "11" else None
    console.mark_dirty = lambda state, value=True: None
    ini = tmp_path / "rasai-console.ini"
    ini.write_text("[existing]\nkeep = yes\n", encoding="utf-8")
    saved = []

    def save(state):
        saved.append(True)
        ini.write_text("[existing]\nkeep = changed\n", encoding="utf-8")
        return True

    console._save_configuration = save
    # Compose the real system-defaults *configure wrapper* without installing its
    # unrelated global environment-catalog patches into other pytest modules.
    # The latter pollute the Windows console-navigation aggregate test order.
    monkeypatch.setattr(system_defaults, "_patch_environment_catalog", lambda: None)
    monkeypatch.setattr(system_defaults, "_patch_apdex_guidance", lambda: None)
    system_defaults.install(console)
    refactor._install_configure_persistence(console)

    monkeypatch.setattr(apdex, "_show_experience_defaults", lambda: None)
    monkeypatch.setattr(apdex, "_configure_navigation", lambda state: setattr(state, "apdex_samples", 29))
    monkeypatch.setattr(apdex, "_number", lambda name, current, **kw: current)
    monkeypatch.setattr(apdex, "_choice", lambda name, current, allowed, *a: current)
    monkeypatch.setattr(apdex, "_required_positive", lambda name, current: current)
    monkeypatch.setattr(apdex, "confirm_sensitive", lambda *a, **kw: True)

    def profiles(device):
        os.environ["RASAI_APDEX_EXPERIENCE_PROFILE_TEST_381"] = device
    monkeypatch.setattr(apdex, "_configure_experience_runtime_profiles", profiles)

    def yes_no(label, current):
        if "Aplicar os 3 valores" in label:
            return apdex.prompt_yes_no(label, current)
        return current

    monkeypatch.setattr(apdex, "_yes_no", yes_no)
    return console, ini, saved


def _answer(monkeypatch, reply, *, allow_destination=False):
    def responder(prompt=""):
        if "Aplicar os 3 valores" in prompt:
            return reply
        if prompt.startswith("Escolha"):
            if not allow_destination:
                raise AssertionError("Cancelamento nunca deve oferecer DESTINO DA ALTERAÇÃO")
            return "2"
        raise AssertionError(f"Campo inesperado: {prompt}")
    monkeypatch.setattr(builtins, "input", responder)


@pytest.mark.parametrize("reply", ["V", "v", "N", ""])
def test_rejected_guided_rolls_back_before_save_prompt(monkeypatch, tmp_path, reply):
    console, ini, saved = _compose(monkeypatch, tmp_path)
    state = _state()
    initial_fingerprint = refactor._fingerprint(state)
    initial_mix_inherited = refactor._mix_inherited(state)
    initial_ini = ini.read_bytes()
    initial_env = dict(os.environ)

    _answer(monkeypatch, reply)
    output = StringIO()
    with redirect_stdout(output):
        console._configure(state, "11")

    assert state.operation == "LOCAL:APDEX_EDIT_CANCELLED"
    assert state.error == ""
    assert refactor._fingerprint(state) == initial_fingerprint
    assert refactor._mix_inherited(state) == initial_mix_inherited
    assert state.apdex_experience_device_mix == "mobile=50,desktop=50,tablet=0"
    assert state.apdex_samples == 10
    assert dict(os.environ) == initial_env
    assert ini.read_bytes() == initial_ini
    assert not saved
    assert "DESTINO DA ALTERAÇÃO" not in output.getvalue()


@pytest.mark.parametrize("cancel_at", ["navigation", "profile", "threshold", "sensitive", "invalid"])
def test_other_apdex_cancellation_and_validation_failures_cannot_persist(
    monkeypatch, tmp_path, cancel_at,
):
    console, ini, saved = _compose(monkeypatch, tmp_path)
    state = _state()
    if cancel_at == "navigation":
        monkeypatch.setattr(apdex, "_configure_navigation", lambda state: (_ for _ in ()).throw(EditCancelled()))
    elif cancel_at == "profile":
        def abort_profile(device):
            os.environ["RASAI_APDEX_EXPERIENCE_PROFILE_TEST_381"] = "partial"
            raise EditCancelled()
        monkeypatch.setattr(apdex, "_configure_experience_runtime_profiles", abort_profile)
    elif cancel_at in {"threshold", "invalid"}:
        state.apdex_experience_profile_mode = "CUSTOM"
        def reject_threshold(label, current):
            if "Satisfied" in label:
                if cancel_at == "threshold":
                    raise EditCancelled()
                raise ValueError("threshold inválido")
            return current
        monkeypatch.setattr(apdex, "_required_positive", reject_threshold)
    else:
        monkeypatch.setattr(apdex, "confirm_sensitive", lambda *a, **kw: False)

    before = refactor._fingerprint(state)
    original_ini = ini.read_bytes()
    original_env = dict(os.environ)
    _answer(monkeypatch, "V")
    output = StringIO()
    with redirect_stdout(output):
        console._configure(state, "11")

    assert refactor._fingerprint(state) == before
    assert refactor._mix_inherited(state) is False
    assert dict(os.environ) == original_env
    assert ini.read_bytes() == original_ini
    assert saved == []
    assert "DESTINO DA ALTERAÇÃO" not in output.getvalue()
    if cancel_at == "invalid":
        assert "threshold inválido" in state.error
    else:
        assert state.operation == "LOCAL:APDEX_EDIT_CANCELLED"


def test_explicit_guided_approval_retains_normal_save_path(monkeypatch, tmp_path):
    console, ini, saved = _compose(monkeypatch, tmp_path)
    state = _state()
    before = refactor._fingerprint(state)
    _answer(monkeypatch, "S", allow_destination=True)
    output = StringIO()
    with redirect_stdout(output):
        console._configure(state, "11")

    assert refactor._fingerprint(state) != before
    assert state.apdex_experience_kpm == "USER_ACTION_DURATION"
    assert state.apdex_experience_satisfied == 3.0
    assert state.apdex_experience_frustrated == 12.0
    assert refactor._mix_inherited(state) is True
    assert state.apdex_experience_device_mix == "mobile=0,desktop=100,tablet=0"
    assert saved == [True]
    assert "DESTINO DA ALTERAÇÃO" in output.getvalue()
    assert ini.read_text(encoding="utf-8").endswith("keep = changed\n")
