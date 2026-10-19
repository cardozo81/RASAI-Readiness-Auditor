"""#523: real console bootstrap must not confuse INI inventory with OS overrides.

Read/write only disposable INIs. No audit execution, browser, vendor API, or secrets.
"""
from __future__ import annotations

from configparser import ConfigParser
import os
from unittest.mock import patch

from rasai import console_settings, interactive_console
from rasai.system_defaults import load_console_config_with_system_defaults


def _boot_without_running_an_audit(monkeypatch) -> dict[str, str]:
    observed: list[dict[str, str]] = []

    def menu(state):
        observed.append({
            "device": state.device,
            "samples": str(state.apdex_samples),
            "architecture": state.apdex_experience_architecture,
            "runtime_device": os.environ.get("RASAI_DEVICE_CONTEXT", "<absent>"),
            "runtime_samples": os.environ.get("RASAI_APDEX_SAMPLES_PER_CONTEXT", "<absent>"),
        })
        return "Q"

    # This is the same system-default-aware loader installed by the real entrypoint.
    monkeypatch.setattr(interactive_console, "load_console_config", load_console_config_with_system_defaults)
    monkeypatch.setattr(interactive_console, "_menu", menu)
    monkeypatch.setattr(interactive_console, "_confirm_exit", lambda state: True)
    assert interactive_console.main() == 0
    assert len(observed) == 1
    return observed[0]


def test_boot_restores_typed_device_and_cat06_cat07_instead_of_stale_ini_inventory(tmp_path, monkeypatch):
    """A previously written [environment] default must not masquerade as Windows/User."""
    ini = tmp_path / "operator-523.ini"
    with patch.dict(os.environ, {}, clear=True):
        console_settings.save_console_config(interactive_console.State(), ini)
        parser = ConfigParser(interpolation=None)
        parser.optionxform = str
        parser.read(ini, encoding="utf-8")
        assert parser.get("environment", "RASAI_DEVICE_CONTEXT") == "mobile"
        assert parser.get("environment", "RASAI_APDEX_SAMPLES_PER_CONTEXT") == "150"
        assert parser.get("environment", "RASAI_APDEX_EXPERIENCE_ARCHITECTURE") == "AUTO"

        # Reproduce a divergent physical INI: the operator's typed choices are
        # authoritative; the environment inventory reflects an older session.
        parser.set("console", "device", "desktop")
        parser.set("synthetic_apdex", "samples_per_context", "7")
        parser.set("synthetic_apdex_experience", "architecture", "CSR_SPA")
        with ini.open("w", encoding="utf-8") as output:
            parser.write(output)
        original = ini.read_bytes()

        os.environ.clear()
        os.environ["RASAI_CONSOLE_INI"] = str(ini)
        effective = _boot_without_running_an_audit(monkeypatch)
        assert effective == {
            "device": "desktop",
            "samples": "7",
            "architecture": "CSR_SPA",
            "runtime_device": "desktop",
            "runtime_samples": "7",
        }
        assert ini.read_bytes() == original


def test_boot_preserves_a_real_external_device_override(tmp_path, monkeypatch):
    """An actual environment override set before the loader still has precedence."""
    ini = tmp_path / "operator-external-523.ini"
    with patch.dict(os.environ, {}, clear=True):
        saved = interactive_console.State()
        saved.device = "desktop"
        console_settings.save_console_config(saved, ini)
        original = ini.read_bytes()

        os.environ.clear()
        os.environ["RASAI_CONSOLE_INI"] = str(ini)
        os.environ["RASAI_DEVICE_CONTEXT"] = "mobile"
        effective = _boot_without_running_an_audit(monkeypatch)
        assert effective["device"] == "mobile"
        assert effective["runtime_device"] == "mobile"
        assert ini.read_bytes() == original
