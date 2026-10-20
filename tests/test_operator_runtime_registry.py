"""Reconciliation of active operator INI settings with explicit runtime readers.

Tests use disposable INIs; they never call external providers or create an AUD.
"""
from __future__ import annotations

from configparser import ConfigParser
from hashlib import sha256
import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

import pytest

from rasai.console_config import is_secret
from rasai.console_provider_environment import _ADDITIONAL_RUNTIME_INPUTS, refresh_specs
from rasai.console_search_intelligence import SearchConsoleState
from rasai import console_settings
from rasai.console_complete_persistence import install as install_complete_persistence
from rasai.console_ui_refactor import _install_search_persistence


# All settings are synthetic and public; no operator data or credentials.
RUNTIME_INPUTS = {
    "RASAI_AI_ANALYSIS_LANGUAGE": "pt-BR",
    "RASAI_AI_MODELS_FILE": "models-custom.toml",
    "RASAI_AI_MODELS_SOURCE": "auto",
    "RASAI_AI_PRICING_FILE": "pricing-custom.toml",
    "RASAI_AI_PRICING_SOURCE": "auto",
    "RASAI_AI_TASK_PROFILES_FILE": "profiles-custom.toml",
    "RASAI_AI_TASK_PROFILES_SOURCE": "auto",
    "RASAI_GOOGLE_SEARCH_CONSOLE_CLIENT_ID": "synthetic-public-client-id",
    "RASAI_GSC_ENABLED": "false",
    "RASAI_GOOGLE_SEARCH_CONSOLE_SITE_URL": "sc-domain:example.test",
    "RASAI_GSC_SEARCH_ANALYTICS_DAYS": "14",
    "RASAI_GSC_SEARCH_MAX_ROWS": "1000",
    "RASAI_GSC_FINAL_DATA_LAG_DAYS": "2",
    "RASAI_IMPROVEMENT_AI_TIMEOUT_SECONDS": "51",
    "RASAI_IMPROVEMENT_DOMAINS": "TECHNICAL_HTML,CONTENT",
    "RASAI_IMPROVEMENT_INTELLIGENCE": "false",
    "RASAI_IMPROVEMENT_MAX_RECOMMENDATIONS": "13",
    "RASAI_PASSIVE_SECURITY": "true",
    "RASAI_PRESENTATION_TIMEZONE": "America/Sao_Paulo",
    "RASAI_SECURITY_CISA_KEV": "false",
    "RASAI_SECURITY_COOKIES": "true",
    "RASAI_SECURITY_EXTERNAL_TIMEOUT_SECONDS": "19",
    "RASAI_SECURITY_HEADERS": "true",
    "RASAI_SECURITY_OSV": "false",
    "RASAI_SECURITY_RESOURCES": "true",
    "RASAI_SECURITY_RUNTIME_CORRELATION": "false",
    "RASAI_SECURITY_THIRD_PARTY": "true",
}


def _write_ini(path: Path, values: dict[str, str]) -> None:
    parser = ConfigParser(interpolation=None)
    parser.optionxform = str
    parser["environment"] = values
    with path.open("w", encoding="utf-8") as stream:
        parser.write(stream)


def test_all_reconciled_runtime_names_are_public_unique_and_visible() -> None:
    specs = refresh_specs()
    names = [spec.name for spec in specs]
    assert len(names) == len(set(names))
    assert {entry[0] for entry in _ADDITIONAL_RUNTIME_INPUTS} == set(RUNTIME_INPUTS)
    assert set(RUNTIME_INPUTS) <= set(names)
    indexed = {spec.name: spec for spec in specs}
    for name in RUNTIME_INPUTS:
        spec = indexed[name]
        assert spec.category
        # Guidance can point to curated documentation instead of source code.
        assert spec.source
        assert spec.sensitive is False
        assert is_secret(name) is False
        assert name in console_settings._known_nonsecret_environment_names()


@pytest.mark.parametrize(
    ("name", "raw", "normalized"),
    [
        ("RASAI_AI_MODELS_SOURCE", "FILE", "file"),
        ("RASAI_SECURITY_COOKIES", "FALSE", "false"),
        ("RASAI_IMPROVEMENT_MAX_RECOMMENDATIONS", "11", "11"),
        ("RASAI_IMPROVEMENT_AI_TIMEOUT_SECONDS", "1.5", "1.5"),
        ("RASAI_PRESENTATION_TIMEZONE", "America/Sao_Paulo", "America/Sao_Paulo"),
    ],
)
def test_public_runtime_menu_validation(name: str, raw: str, normalized: str) -> None:
    from rasai.console_provider_environment import _validate
    assert _validate(name, raw) == normalized


@pytest.mark.parametrize(
    ("name", "raw"),
    [
        ("RASAI_AI_PRICING_SOURCE", "download"),
        ("RASAI_SECURITY_COOKIES", "maybe"),
        ("RASAI_IMPROVEMENT_MAX_RECOMMENDATIONS", "0"),
        ("RASAI_SECURITY_EXTERNAL_TIMEOUT_SECONDS", "nan"),
        ("RASAI_PRESENTATION_TIMEZONE", "Invalid/Timezone"),
    ],
)
def test_public_runtime_menu_rejects_invalid_settings(name: str, raw: str) -> None:
    from rasai.console_provider_environment import _validate
    with pytest.raises((ValueError, OverflowError)):
        _validate(name, raw)


def test_real_loader_saver_and_consumers_restore_all_reconciled_inputs(tmp_path: Path) -> None:
    _install_search_persistence()
    install_complete_persistence()
    path = tmp_path / "operator-copy.ini"
    _write_ini(path, RUNTIME_INPUTS)
    original_hash = sha256(path.read_bytes()).hexdigest()

    with patch.dict(os.environ, {"RASAI_CONSOLE_INI": str(path)}, clear=True):
        state = SearchConsoleState()
        loaded = console_settings.load_console_config(state, path)
        assert loaded.warnings == ()
        assert sha256(path.read_bytes()).hexdigest() == original_hash
        for name, value in RUNTIME_INPUTS.items():
            assert os.environ.get(name) == value, name

        # These are actual catalog selection consumers, not merely the UI registry.
        from rasai.ai_model_catalog import model_runtime_settings
        from rasai.ai_pricing_catalog import pricing_runtime_settings
        from rasai.ai_task_profiles import task_profile_runtime_settings
        assert model_runtime_settings(env=os.environ, cwd=tmp_path)[0] == "auto"
        assert pricing_runtime_settings(env=os.environ, cwd=tmp_path)[0] == "auto"
        assert task_profile_runtime_settings(env=os.environ, cwd=tmp_path)[0] == "auto"

        from rasai.improvement_intelligence import (
            ImprovementConfig, configured_analysis_language,
        )
        improvement = ImprovementConfig.from_environment(os.environ)
        assert improvement.enabled is False
        assert improvement.timeout_seconds == 51
        assert improvement.max_recommendations == 13
        assert improvement.domains == ("TECHNICAL_HTML", "CONTENT")
        assert configured_analysis_language(os.environ) == "pt-BR"

        from rasai.passive_security import enabled, external_timeout
        assert enabled(os.environ) is True
        assert external_timeout(os.environ) == 19.0

        from rasai.gsc_oauth import MODE_INCOMPLETE, credential_state
        # OAuth client ID is public configuration, not proof of OAuth consent.
        assert credential_state(os.environ).mode == MODE_INCOMPLETE

        console_settings.save_console_config(state, path)
        parser = ConfigParser(interpolation=None)
        parser.optionxform = str
        parser.read(path, encoding="utf-8")
        for name, value in RUNTIME_INPUTS.items():
            assert parser._sections["environment"][name] == value, name
        after_save = path.read_bytes()
        assert b"synthetic-private-token" not in after_save

        # Simulate process restart with no inherited overrides.
        os.environ.clear()
        os.environ["RASAI_CONSOLE_INI"] = str(path)
        reloaded = SearchConsoleState()
        second = console_settings.load_console_config(reloaded, path)
        assert second.warnings == ()
        for name, value in RUNTIME_INPUTS.items():
            assert os.environ.get(name) == value, name
        assert path.read_bytes() == after_save


def test_new_interpreter_can_read_saved_runtime_inputs(tmp_path: Path) -> None:
    _install_search_persistence()
    install_complete_persistence()
    path = tmp_path / "operator-copy.ini"
    with patch.dict(os.environ, {"RASAI_CONSOLE_INI": str(path)}, clear=True):
        for name, value in RUNTIME_INPUTS.items():
            os.environ[name] = value
        state = SearchConsoleState()
        console_settings.save_console_config(state, path)
    baseline = sha256(path.read_bytes()).hexdigest()
    script = (
        "import json,os,sys;"
        "from pathlib import Path;"
        "from rasai.console_search_intelligence import SearchConsoleState;"
        "from rasai.console_settings import load_console_config;"
        "from rasai.console_ui_refactor import _install_search_persistence;"
        "from rasai.console_complete_persistence import install as install_complete_persistence;"
        "_install_search_persistence();install_complete_persistence();"
        "p=Path(sys.argv[1]);s=SearchConsoleState();r=load_console_config(s,p);"
        "print(json.dumps({'warnings':len(r.warnings),"
        "'models':os.environ.get('RASAI_AI_MODELS_SOURCE'),"
        "'security':os.environ.get('RASAI_SECURITY_COOKIES'),"
        "'timezone':os.environ.get('RASAI_PRESENTATION_TIMEZONE')}))"
    )
    environment = {name: value for name, value in os.environ.items()
                   if name not in RUNTIME_INPUTS}
    environment["RASAI_CONSOLE_INI"] = str(path)
    completed = subprocess.run(
        [sys.executable, "-c", script, str(path)],
        env=environment, capture_output=True, text=True, check=True, timeout=30,
    )
    import json
    assert json.loads(completed.stdout) == {
        "warnings": 0,
        "models": "auto",
        "security": "true",
        "timezone": "America/Sao_Paulo",
    }
    assert sha256(path.read_bytes()).hexdigest() == baseline


@pytest.mark.parametrize("unknown", [
    "RASAI_UNREGISTERED_FUTURE_OPTION",
    "RASAI_FUTURE_PRIVATE_TOKEN",
])
def test_save_refuses_to_discard_unknown_ini_entries_without_leaking_them(
    tmp_path: Path, unknown: str
) -> None:
    _install_search_persistence()
    install_complete_persistence()
    ini = tmp_path / "operator-copy.ini"
    private_marker = "DO_NOT_ECHO_IN_PUBLIC_ERRORS"
    _write_ini(ini, {unknown: private_marker, **RUNTIME_INPUTS})
    before = ini.read_bytes()
    with patch.dict(os.environ, {}, clear=True):
        state = SearchConsoleState()
        with pytest.raises(ValueError, match="configuracoes desconhecidas") as caught:
            console_settings.save_console_config(state, ini)
        assert os.environ == {}
    assert ini.read_bytes() == before
    assert unknown not in str(caught.value)
    assert private_marker not in str(caught.value)


def test_apdex_preflight_accepts_reconciled_legacy_inputs_without_real_aud(
    tmp_path: Path,
) -> None:
    from rasai.console_apdex_effective_validation import inspect_apdex_consumers
    ini = tmp_path / "operator-copy.ini"
    _write_ini(ini, RUNTIME_INPUTS)
    original = sha256(ini.read_bytes()).hexdigest()
    with patch.dict(os.environ, {}, clear=True):
        report = inspect_apdex_consumers(ini, environ={})
    assert report["status"] == "ADAPTERS_VALIDATED_OFFLINE"
    assert report["load_warning_count"] == 0
    assert sum(report["load_warning_categories"].values()) == 0
    assert sum(report["load_warning_environment_reasons"].values()) == 0
    assert report["external_requests"] == report["audit_writes"] == 0
    assert report["values_exposed"] is False
    assert sha256(ini.read_bytes()).hexdigest() == original


@pytest.mark.parametrize("kind", ["unknown_section", "unknown_typed_option", "default"])
def test_save_preserves_unrecognized_typed_ini_content(
    tmp_path: Path, kind: str
) -> None:
    _install_search_persistence()
    install_complete_persistence()
    ini = tmp_path / "operator-copy.ini"
    parser = ConfigParser(interpolation=None)
    parser.optionxform = str
    parser["environment"] = {"RASAI_SECURITY_HEADERS": "false"}
    if kind == "unknown_section":
        parser["future_plugin"] = {"new_setting": "PRIVATE_FIXTURE"}
    elif kind == "unknown_typed_option":
        parser["console"] = {"unsupported_state": "PRIVATE_FIXTURE"}
    else:
        parser["DEFAULT"] = {"unsupported_global": "PRIVATE_FIXTURE"}
    with ini.open("w", encoding="utf-8") as stream:
        parser.write(stream)
    before = ini.read_bytes()
    with patch.dict(os.environ, {}, clear=True):
        with pytest.raises(ValueError) as caught:
            console_settings.save_console_config(SearchConsoleState(), ini)
    assert "PRIVATE_FIXTURE" not in str(caught.value)
    assert ini.read_bytes() == before


@pytest.mark.parametrize("preexisting", [True, False])
def test_save_aborts_when_physical_ini_changes_during_serialization(
    tmp_path: Path, monkeypatch, preexisting: bool
) -> None:
    _install_search_persistence()
    install_complete_persistence()
    ini = tmp_path / "operator-copy.ini"
    if preexisting:
        _write_ini(ini, {"RASAI_SECURITY_HEADERS": "false"})
    changed = b"[environment]\nRASAI_UNREGISTERED_FUTURE_OPTION = state-change\n"
    original_parser = console_settings._parser_for_state
    number_of_calls = 0

    def intervening_edit(state):
        nonlocal number_of_calls
        number_of_calls += 1
        result = original_parser(state)
        # First call occurs during the save guard, second during output generation.
        if (preexisting and number_of_calls == 2) or not preexisting:
            ini.write_bytes(changed)
        return result

    monkeypatch.setattr(console_settings, "_parser_for_state", intervening_edit)
    with patch.dict(os.environ, {}, clear=True):
        with pytest.raises(ValueError, match="origem mudou durante o save"):
            console_settings.save_console_config(SearchConsoleState(), ini)
    assert ini.read_bytes() == changed
    assert list(tmp_path.glob(".*.tmp")) == []


def test_save_does_not_touch_old_predictable_tmp_sibling(tmp_path: Path) -> None:
    _install_search_persistence()
    install_complete_persistence()
    ini = tmp_path / "operator-copy.ini"
    stale = tmp_path / "operator-copy.ini.tmp"
    stale.write_text("other process state", encoding="utf-8")
    with patch.dict(os.environ, {}, clear=True):
        console_settings.save_console_config(SearchConsoleState(), ini)
    assert stale.read_text(encoding="utf-8") == "other process state"
    assert ini.is_file()
