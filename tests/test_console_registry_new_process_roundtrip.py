"""Registry-wide new-process persistence proof with no real credentials or APIs.

Only temporary INI, ephemeral process environment and public setting names.
This is a persistence/rehydration gate, not proof that every catalog consumer
executes a side effect; consumer adapters have separate focused tests.
"""
from __future__ import annotations

from configparser import ConfigParser
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
from unittest.mock import patch

from rasai.console_search_intelligence import SearchConsoleState
from rasai.console_provider_environment import refresh_specs
from rasai.console_config import is_secret
from rasai.console_ui_refactor import _install_search_persistence
from rasai.console_complete_persistence import install as install_complete_persistence
from rasai import console_settings


def test_every_registered_public_setting_rehydrates_in_new_python_process(tmp_path):
    _install_search_persistence()
    install_complete_persistence()
    names = {spec.name for spec in refresh_specs()
             if not spec.sensitive and not is_secret(spec.name)}
    outer_environment = dict(os.environ)
    with patch.dict(os.environ, {}, clear=True):
        settings = SearchConsoleState()
        settings.device = "desktop"
        settings.apdex_experience_architecture = "CSR_SPA"
        settings.apdex_experience_profile_mode = "DYNATRACE_GUIDED"
        settings.apdex_experience_xhr_capture = False
        settings.apdex_experience_fetch_capture = True
        settings.apdex_threshold = 2.25
        settings.search_queries = ("offline-test",)
        settings.perplexity_queries = ("saved-draft-not-authorized",)
        path = tmp_path / "registry.ini"
        console_settings.save_console_config(settings, path)
        original = path.read_bytes()
        parser = ConfigParser(interpolation=None)
        parser.optionxform = str
        parser.read(path, encoding="utf-8")
        stored = dict(parser["environment"])
        assert set(stored) == names
        # Never include site data or secret credentials as part of the test.
        assert "PERPLEXITY_API_KEY" not in stored
        assert "RASAI_DYNATRACE_API_TOKEN" not in stored

        code = r"""
import json,os,sys
from pathlib import Path
from rasai.console_search_intelligence import SearchConsoleState
from rasai.console_ui_refactor import _install_search_persistence
from rasai.console_complete_persistence import install as install_complete_persistence
from rasai.console_settings import load_console_config, _state_values
_install_search_persistence()
install_complete_persistence()
state = SearchConsoleState()
loaded = load_console_config(state, Path(sys.argv[1]))
from configparser import ConfigParser
parser=ConfigParser(interpolation=None);parser.optionxform=str
parser.read(sys.argv[1],encoding="utf-8")
stored=dict(parser["environment"])
missing=[name for name,value in stored.items()
         if value.strip() and os.environ.get(name)!=value.strip()]
unexpected=[name for name,value in stored.items()
            if not value.strip() and os.environ.get(name)]
assert loaded.created is False
assert not loaded.warnings, len(loaded.warnings)
typed=_state_values(state)
# Assert APDEX serialized typed values survive in an independent process.
apdex_mismatches=[]
for section in ("synthetic_apdex", "synthetic_apdex_experience"):
    for option, saved_value in parser[section].items():
        if option == "device_mix":
            continue
        actual=typed[section].get(option)
        if actual != saved_value:
            apdex_mismatches.append({"section":section,"option":option,
                                     "expected":saved_value,"actual":actual})
assert not apdex_mismatches, apdex_mismatches
assert typed["synthetic_apdex_experience"]["architecture"]=="CSR_SPA"
assert typed["synthetic_apdex_experience"]["profile_mode"]=="DYNATRACE_GUIDED"
assert state.perplexity_queries == ()
assert state.perplexity_draft_queries == ("saved-draft-not-authorized",)
print(json.dumps({"missing":missing,"unexpected":unexpected,
                  "count":len(stored),"apdex_fields_checked":sum(
                      len(parser[section]) - (1 if section == "synthetic_apdex_experience" else 0)
                      for section in ("synthetic_apdex","synthetic_apdex_experience")),
                  "nonsecret":True},sort_keys=True))
"""
        # A new process with Windows/Python bootstrap variables only, no RASAI/provider secrets.
        child_env = {
            name: value for name, value in outer_environment.items()
            if name.upper() in {"SYSTEMROOT", "WINDIR", "PATH", "PATHEXT",
                                "TEMP", "TMP", "HOME", "USERPROFILE",
                                "VIRTUAL_ENV", "PYTHONPATH"}
        }
        completed = subprocess.run(
            [sys.executable, "-c", code, str(path)],
            cwd=Path.cwd(), env=child_env,
            capture_output=True, text=True, timeout=35, check=True,
        )
        restored = json.loads(completed.stdout)
        assert restored["count"] == len(names)
        assert restored["apdex_fields_checked"] >= 20
        assert restored["missing"] == [], restored["missing"]
        assert restored["unexpected"] == [], restored["unexpected"]
        assert path.read_bytes() == original



def test_cat06_cat07_nondefault_roundtrip_and_runtime_projection(tmp_path):
    """#523: operator changes must reach both restored session and runtime."""
    _install_search_persistence()
    install_complete_persistence()
    with patch.dict(os.environ, {}, clear=True):
        source = SearchConsoleState()
        source.device = "desktop"
        source.web_performance = True
        source.web_max_pages = 3
        source.web_timeout = 29.0
        source.synthetic_apdex = True
        source.apdex_samples = 4
        source.apdex_max_attempts = 6
        source.apdex_max_pages = 2
        source.apdex_concurrency = 2
        source.apdex_experience = True
        source.apdex_experience_architecture = "CSR_SPA"
        source.apdex_experience_profile_mode = "CUSTOM"
        source.apdex_experience_xhr_capture = False
        source.apdex_experience_fetch_capture = True
        source.apdex_experience_console_capture = False
        path = tmp_path / "cat06-cat07.ini"
        console_settings.save_console_config(source, path)
        first_bytes = path.read_bytes()
        parser = ConfigParser(interpolation=None)
        parser.optionxform = str
        parser.read(path, encoding="utf-8")
        expected = console_settings._state_values(source)

        # Simulate an independent session without any inherited operator
        # state or paid-service authorization.
        with patch.dict(os.environ, {}, clear=True):
            fresh = SearchConsoleState()
            result = console_settings.load_console_config(fresh, path)
            assert not result.created
            assert not result.warnings, result.warnings
            actual = console_settings._state_values(fresh)
            for section in ("web_performance", "synthetic_apdex",
                            "synthetic_apdex_experience"):
                for key, value in expected[section].items():
                    if key == "device_mix":
                        continue  # Derived from the selected canonical device.
                    assert actual[section][key] == value, (section, key)
                    assert parser.get(section, key) == value

            projected = console_settings._runtime_environment_projection(fresh)
            for name in (
                "RASAI_WEB_PERFORMANCE",
                "RASAI_SYNTHETIC_APDEX",
                "RASAI_APDEX_EXPERIENCE_ARCHITECTURE",
            ):
                assert os.environ.get(name) == projected.get(name), name

            assert "PERPLEXITY_API_KEY" not in os.environ
            assert "RASAI_DYNATRACE_API_TOKEN" not in os.environ
            assert path.read_bytes() == first_bytes


def test_failed_save_rolls_back_runtime_environment_and_preserves_ini(tmp_path):
    """A failed atomic file replacement cannot commit an environment mutation."""
    _install_search_persistence()
    install_complete_persistence()
    with patch.dict(os.environ, {}, clear=True):
        state = SearchConsoleState()
        path = tmp_path / "operator.ini"
        console_settings.save_console_config(state, path)
        original_bytes = path.read_bytes()
        state.web_performance = True
        state.apdex_experience_architecture = "CSR_SPA"
        os.environ["RASAI_WEB_PERFORMANCE"] = "false"
        os.environ["RASAI_APDEX_EXPERIENCE_ARCHITECTURE"] = "STATIC_OR_SSR"
        old_web = os.environ["RASAI_WEB_PERFORMANCE"]
        old_architecture = os.environ["RASAI_APDEX_EXPERIENCE_ARCHITECTURE"]
        with patch("rasai.console_settings.os.replace", side_effect=OSError("simulated disk error")):
            with pytest.raises(OSError, match="simulated disk error"):
                console_settings.save_console_config(state, path)
        assert os.environ["RASAI_WEB_PERFORMANCE"] == old_web
        assert os.environ["RASAI_APDEX_EXPERIENCE_ARCHITECTURE"] == old_architecture
        assert path.read_bytes() == original_bytes
        assert sorted(p.name for p in tmp_path.iterdir()) == ["operator.ini"]


def test_fresh_save_error_cannot_leave_partially_applied_runtime_override(tmp_path):
    """Even a missing writable parent must not alter the ambient session."""
    _install_search_persistence()
    install_complete_persistence()
    with patch.dict(os.environ, {}, clear=True):
        state = SearchConsoleState()
        state.synthetic_apdex = True
        with patch("rasai.console_settings.mkstemp", side_effect=OSError("no temporary file")):
            with pytest.raises(OSError, match="no temporary file"):
                console_settings.save_console_config(state, tmp_path / "operator.ini")
        assert "RASAI_SYNTHETIC_APDEX" not in os.environ
        assert not (tmp_path / "operator.ini").exists()
