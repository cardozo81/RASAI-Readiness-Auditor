"""#523 Windows smoke regression: legacy CAT-07 device_mix vs guarded save.

Only disposable INI files and in-memory environment are used. No audit or API.
"""
from __future__ import annotations

from configparser import ConfigParser
import os
from unittest.mock import patch

import pytest

from rasai import console_settings
from rasai.console_complete_persistence import install as install_complete
from rasai.console_search_intelligence import SearchConsoleState
from rasai.console_ui_refactor import _ensure_mix, _install_search_persistence


def _parser(path):
    parser = ConfigParser(interpolation=None)
    parser.optionxform = str
    parser.read(path, encoding="utf-8")
    return parser


def _setup_contract():
    _install_search_persistence()
    install_complete()


def test_first_ini_save_never_writes_derived_device_mix(tmp_path):
    """Operator's first save must use the same schema as all later saves."""
    _setup_contract()
    with patch.dict(os.environ, {}, clear=True):
        state = SearchConsoleState()
        path = tmp_path / "smoke-523.ini"
        console_settings.save_console_config(state, path)

        initial = _parser(path)
        assert initial.get("console", "device") == "mobile"
        assert not initial.has_option("synthetic_apdex_experience", "device_mix")

        _ensure_mix(state)
        state.device = "desktop"
        console_settings.save_console_config(state, path)
        persisted = _parser(path)
        assert persisted.get("console", "device") == "desktop"
        assert persisted.get("environment", "RASAI_DEVICE_CONTEXT") == "desktop"
        assert not persisted.has_option("synthetic_apdex_experience", "device_mix")


def test_legacy_derived_mix_is_migrated_on_explicit_save_without_data_loss(tmp_path):
    """Existing INI with the historical key must not lock out Device edits."""
    _setup_contract()
    with patch.dict(os.environ, {}, clear=True):
        state = SearchConsoleState()
        path = tmp_path / "legacy-smoke-523.ini"
        console_settings.save_console_config(state, path)
        legacy = _parser(path)
        legacy.set(
            "synthetic_apdex_experience", "device_mix",
            "mobile=100,desktop=0,tablet=0",
        )
        with path.open("w", encoding="utf-8") as output:
            legacy.write(output)
        _ensure_mix(state)
        state.device = "desktop"
        state.apdex_samples = 7
        state.apdex_experience_architecture = "CSR_SPA"
        console_settings.save_console_config(state, path)

        migrated = _parser(path)
        assert not migrated.has_option("synthetic_apdex_experience", "device_mix")
        assert migrated.get("console", "device") == "desktop"
        assert migrated.get("synthetic_apdex", "samples_per_context") == "7"
        assert migrated.get("synthetic_apdex_experience", "architecture") == "CSR_SPA"
        assert migrated.get("environment", "RASAI_DEVICE_CONTEXT") == "desktop"

        os.environ.clear()
        restored = SearchConsoleState()
        loaded = console_settings.load_console_config(restored, path)
        assert not loaded.created and not loaded.warnings
        assert restored.device == "desktop"
        assert restored.apdex_samples == 7
        assert restored.apdex_experience_architecture == "CSR_SPA"


@pytest.mark.parametrize("extra_section,extra_key", [
    ("synthetic_apdex_experience", "unregistered_setting"),
    ("unknown_section", "custom_value"),
])
def test_guard_still_rejects_unknown_with_legacy_mix(
    tmp_path, extra_section, extra_key,
):
    """Validated migration never becomes permission to discard unknown INI data."""
    _setup_contract()
    with patch.dict(os.environ, {}, clear=True):
        state = SearchConsoleState()
        path = tmp_path / "unrecognized-523.ini"
        console_settings.save_console_config(state, path)
        original = _parser(path)
        original.set(
            "synthetic_apdex_experience", "device_mix",
            "mobile=100,desktop=0,tablet=0",
        )
        if not original.has_section(extra_section):
            original.add_section(extra_section)
        original.set(extra_section, extra_key, "PRESERVE_THIS_SETTING_523")
        with path.open("w", encoding="utf-8") as output:
            original.write(output)
        before = path.read_bytes()
        _ensure_mix(state)
        state.device = "desktop"
        with pytest.raises(ValueError, match="desconhecidas ou nao persistiveis"):
            console_settings.save_console_config(state, path)
        assert path.read_bytes() == before


def test_guard_rejects_invalid_legacy_device_mix(tmp_path):
    _setup_contract()
    with patch.dict(os.environ, {}, clear=True):
        state = SearchConsoleState()
        path = tmp_path / "invalid-523.ini"
        console_settings.save_console_config(state, path)
        original = _parser(path)
        original.set("synthetic_apdex_experience", "device_mix", "not-a-mix")
        with path.open("w", encoding="utf-8") as output:
            original.write(output)
        before = path.read_bytes()
        _ensure_mix(state)
        with pytest.raises(ValueError, match="device_mix invalido"):
            console_settings.save_console_config(state, path)
        assert path.read_bytes() == before
