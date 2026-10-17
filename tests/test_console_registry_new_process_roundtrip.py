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
assert typed["synthetic_apdex_experience"]["architecture"]=="CSR_SPA"
assert typed["synthetic_apdex_experience"]["profile_mode"]=="DYNATRACE_GUIDED"
assert state.perplexity_queries == ()
assert state.perplexity_draft_queries == ("saved-draft-not-authorized",)
print(json.dumps({"missing":missing,"unexpected":unexpected,
                  "count":len(stored),"nonsecret":True},sort_keys=True))
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
        assert restored["missing"] == [], restored["missing"]
        assert restored["unexpected"] == [], restored["unexpected"]
        assert path.read_bytes() == original
