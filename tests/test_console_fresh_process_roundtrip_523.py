"""Issue #523: physical fresh-process console save/load/Apdex adapter gate.

Runs two short-lived Python processes against a disposable INI.  No AUD,
browser, vendor request, credential store or operator configuration is touched.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys



_CHILD = r"""
import json
import os
from pathlib import Path
import sys

from rasai import console_settings
from rasai.console_complete_persistence import install
from rasai.console_search_intelligence import SearchConsoleState
from rasai.console_ui_refactor import _install_search_persistence
from rasai.console_config import is_secret
from rasai.console_provider_environment import refresh_specs

_install_search_persistence()
install()
operation, report_path = sys.argv[1:]
state = SearchConsoleState()
if operation == "save":
    state.device = "desktop"
    state.synthetic_apdex = True
    state.apdex_threshold = 2.0
    state.apdex_samples = 7
    state.apdex_max_attempts = 10
    state.apdex_experience = True
    state.apdex_experience_samples = 7
    state.apdex_experience_max_attempts = 10
    state.apdex_experience_architecture = "HYDRATED"
    state.apdex_experience_profile_mode = "CUSTOM"
    state.apdex_experience_satisfied = 2.0
    state.apdex_experience_frustrated = 8.0
    state.search_queries = ("example audit query",)
    state.search_depth = 10
    state.search_device = "desktop"
    state.perplexity_queries = ("never persist paid search consent",)
    state.perplexity_search_type = "fast"
    os.environ["RASAI_SERP_MAX_REQUESTS"] = "17"
    os.environ["RASAI_PERPLEXITY_ENABLED"] = "true"
    os.environ["PERPLEXITY_API_KEY"] = "FAKE_SECRET_MUST_NOT_PERSIST"
    console_settings.save_console_config(state)
    result = {"typed": console_settings._state_values(state),
              "registered_nonsecret_names": sorted(
                  spec.name for spec in refresh_specs()
                  if not spec.sensitive and not is_secret(spec.name)
              )}
elif operation == "load":
    loaded = console_settings.load_console_config(state)
    console_settings.sync_nonsecret_runtime_environment(state)
    from rasai.console_apdex_effective_validation_523 import inspect_apdex_consumers
    preflight = inspect_apdex_consumers(loaded.path, environ={})
    result = {
        "typed": console_settings._state_values(state),
        "created": loaded.created,
        "warnings": list(loaded.warnings),
        "perplexity_queries_empty": not state.perplexity_queries,
        "perplexity_search_type": state.perplexity_search_type,
        "perplexity_api_key_present": bool(os.environ.get("PERPLEXITY_API_KEY")),
        "serp_max_requests": os.environ.get("RASAI_SERP_MAX_REQUESTS"),
        "perplexity_enabled": os.environ.get("RASAI_PERPLEXITY_ENABLED"),
        "apdex_preflight": preflight,
    }
else:
    raise ValueError("unsupported test operation")
Path(report_path).write_text(json.dumps(result, sort_keys=True), encoding="utf-8")
"""


def _isolated_python_env(root: Path, ini: Path) -> dict[str, str]:
    # Preserve only the platform keys needed to launch Python. Do not inherit
    # user credentials, RASAI overrides, or third-party configuration.
    keep = (
        "PATH", "SystemRoot", "WINDIR", "TEMP", "TMP", "TMPDIR",
        "HOME", "USERPROFILE", "LANG", "LC_ALL", "VIRTUAL_ENV",
    )
    env = {name: os.environ[name] for name in keep if name in os.environ}
    env["PYTHONPATH"] = str(root / "src")
    env["RASAI_CONSOLE_INI"] = str(ini)
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def _run_child(
    operation: str, output: Path, root: Path, env: dict[str, str]
) -> dict:
    finished = subprocess.run(
        [sys.executable, "-c", _CHILD, operation, str(output)],
        cwd=root,
        env=env,
        check=False,
        text=True,
        capture_output=True,
        timeout=60,
    )
    assert finished.returncode == 0, (
        f"{operation}: fresh interpreter exit {finished.returncode}; "
        f"stderr={finished.stderr[-2000:]}"
    )
    assert output.is_file()
    return json.loads(output.read_text(encoding="utf-8"))


def test_fresh_process_roundtrip_apdex_serp_and_explicit_perplexity_optin(tmp_path):
    root = Path(__file__).resolve().parents[1]
    ini = tmp_path / "isolated-operator.ini"
    env = _isolated_python_env(root, ini)
    first = _run_child("save", tmp_path / "saved.json", root, env)
    original_bytes = ini.read_bytes()

    # Verify the complete, dynamically registered INI allowlist on disk.
    from configparser import ConfigParser

    parsed = ConfigParser(interpolation=None)
    parsed.optionxform = str
    parsed.read(ini, encoding="utf-8")
    # The live registry is composed inside the console process; testing an
    # uncomposed pytest interpreter can produce a different allowlist.
    assert set(parsed["environment"]) == set(first["registered_nonsecret_names"])
    assert parsed.get("environment", "RASAI_SERP_MAX_REQUESTS") == "17"
    assert parsed.get("environment", "RASAI_PERPLEXITY_ENABLED") == "true"
    assert parsed.get("synthetic_apdex_experience", "architecture") == "HYDRATED"
    assert parsed.get("synthetic_apdex_experience", "profile_mode") == "CUSTOM"
    assert b"FAKE_SECRET_MUST_NOT_PERSIST" not in original_bytes
    assert b"never persist paid search consent" not in original_bytes
    assert b"PERPLEXITY_API_KEY" not in original_bytes
    assert b"perplexity_queries" not in original_bytes

    # A completely separate interpreter must restore every typed save field,
    # project the runtime environment, and validate the genuine CLI adapters.
    second = _run_child("load", tmp_path / "loaded.json", root, env)
    assert second["typed"] == first["typed"]
    assert second["created"] is False
    assert second["warnings"] == []
    assert second["serp_max_requests"] == "17"
    assert second["perplexity_enabled"] == "true"
    assert second["perplexity_queries_empty"] is True
    assert second["perplexity_search_type"] == "web"
    assert second["perplexity_api_key_present"] is False
    preflight = second["apdex_preflight"]
    assert preflight["status"] == "ADAPTERS_VALIDATED_OFFLINE"
    assert preflight["active_m23"] is True
    assert preflight["active_m25"] is True
    assert preflight["single_device_enforced"] is True
    assert preflight["external_requests"] == 0
    assert preflight["audit_writes"] == 0
    assert preflight["collector_execution_verified"] is False
    assert ini.read_bytes() == original_bytes
