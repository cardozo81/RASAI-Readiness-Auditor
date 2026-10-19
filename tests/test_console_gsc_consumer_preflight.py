"""#523 physical INI GSC scope-policy reading with zero Google requests."""
from __future__ import annotations

import json
import os
from unittest.mock import patch

from rasai.console_gsc_consumer_preflight import inspect_gsc_consumers
from rasai.console_configuration_inventory import main as inventory_main


def _ini(tmp_path, *, target="https://shop.example.org/a", enabled="true",
         site="sc-domain:example.org", days="0", rows="20", lag="3"):
    path = tmp_path / "gsc.ini"
    path.write_text(
        "[console]\n"
        "target = " + target + "\n"
        "[environment]\n"
        "RASAI_GSC_ENABLED = " + enabled + "\n"
        "RASAI_GOOGLE_SEARCH_CONSOLE_SITE_URL = " + site + "\n"
        "RASAI_GSC_SEARCH_ANALYTICS_DAYS = " + days + "\n"
        "RASAI_GSC_SEARCH_MAX_ROWS = " + rows + "\n"
        "RASAI_GSC_FINAL_DATA_LAG_DAYS = " + lag + "\n",
        encoding="utf-8",
    )
    return path


def test_523_gsc_reuses_real_scope_and_policy_without_google_access(tmp_path, capsys):
    from rasai.gsc_oauth import ACCESS_TOKEN_ENV
    source = _ini(tmp_path)
    physical = source.read_bytes()
    # Inject OAuth only into a detached diagnostic environment, never INI.
    with patch.dict(os.environ, {}, clear=True):
        environment = {ACCESS_TOKEN_ENV: "oauth-local-fake-token"}
        result = inspect_gsc_consumers(source, environ=environment)
        assert result["status"] == "LOCAL_SCOPE_AND_OAUTH_CONFIG_VERIFIED"
        assert result["gsc_mode"] == "required"
        assert result["oauth_configuration_mode"] == "ACCESS_TOKEN"
        assert result["property_scope_compatible"] is True
        assert result["policy_bounds_verified"] is True
        assert result["canonical_gsc_ini_keys_restored"] is True
        assert result["authenticated_property_access_verified"] is False
        assert result["gsc_data_finality_verified"] is False
        assert result["provider_requests"] == result["audit_writes"] == 0
        assert "oauth-local-fake-token" not in json.dumps(result)
        assert "shop.example.org" not in json.dumps(result)
        assert "sc-domain:example.org" not in json.dumps(result)
        assert os.environ == {}
        assert source.read_bytes() == physical
        assert inventory_main(["--ini", str(source), "--verify-gsc"]) == 0
        output = json.loads(capsys.readouterr().out)
        assert output["gsc_offline_consumer_preflight"]["status"] == (
            "REQUIRED_OAUTH_NOT_CONFIGURED"
        )


def test_523_gsc_refresh_credentials_are_detected_but_not_exchanged(tmp_path):
    from rasai.gsc_oauth import CLIENT_ID_ENV, CLIENT_SECRET_ENV, REFRESH_TOKEN_ENV
    source = _ini(tmp_path)
    auth = {
        CLIENT_ID_ENV: "public-id",
        CLIENT_SECRET_ENV: "sensitive-client-secret",
        REFRESH_TOKEN_ENV: "sensitive-refresh",
    }
    with patch.dict(os.environ, {}, clear=True):
        outcome = inspect_gsc_consumers(source, environ=auth)
        assert outcome["status"] == "LOCAL_SCOPE_AND_OAUTH_CONFIG_VERIFIED"
        assert outcome["oauth_configuration_mode"] == "REFRESH_TOKEN"
        assert not outcome["authenticated_property_access_verified"]
        assert outcome["provider_requests"] == 0
        assert "sensitive" not in json.dumps(outcome)
        assert os.environ == {}


def test_523_gsc_property_mismatch_and_missing_prerequisites(tmp_path):
    with patch.dict(os.environ, {}, clear=True):
        path = _ini(tmp_path, site="https://elsewhere.example.org/")
        outcome = inspect_gsc_consumers(path, environ={})
        assert outcome["status"] == "GSC_PROPERTY_TARGET_MISMATCH"
        assert outcome["property_scope_compatible"] is False
        disabled = _ini(tmp_path, enabled="false")
        assert inspect_gsc_consumers(disabled, environ={})["status"] == (
            "GSC_DISABLED_BY_CONFIGURATION"
        )
        incomplete = _ini(tmp_path, site="")
        assert inspect_gsc_consumers(incomplete, environ={})["status"] == (
            "REQUIRED_PROPERTY_NOT_CONFIGURED"
        )


def test_523_gsc_invalid_bounds_secret_in_ini_and_bad_source_are_refused(tmp_path):
    from rasai.gsc_oauth import ACCESS_TOKEN_ENV
    with patch.dict(os.environ, {}, clear=True):
        source = _ini(tmp_path, rows="0")
        assert inspect_gsc_consumers(source, environ={})["status"] == (
            "INI_LOAD_WARNINGS"
        )
        source = _ini(tmp_path)
        source.write_text(
            source.read_text(encoding="utf-8") + "\n"
            + ACCESS_TOKEN_ENV + " = bad-persisted-secret\n",
            encoding="utf-8",
        )
        outcome = inspect_gsc_consumers(source, environ={})
        assert outcome["status"] == "INI_LOAD_WARNINGS"
        assert "bad-persisted-secret" not in json.dumps(outcome)
        missing = tmp_path / "missing.ini"
        assert inspect_gsc_consumers(missing)["status"] == "SOURCE_UNAVAILABLE"
        assert not missing.exists()
        symlink = tmp_path / "symbolic.ini"
        try:
            symlink.symlink_to(source)
        except (OSError, NotImplementedError):
            return
        assert inspect_gsc_consumers(symlink)["status"] == "SOURCE_UNAVAILABLE"


def test_523_gsc_no_target_does_not_prove_property_scope(tmp_path):
    source = _ini(tmp_path, target="")
    with patch.dict(os.environ, {}, clear=True):
        result = inspect_gsc_consumers(source, environ={})
    assert result["status"] == "TARGET_NOT_PREPARED"
    assert result["property_scope_compatible"] is None
    assert result["target_prepared"] is False


def test_523_gsc_registry_is_complete_for_nonsecret_real_consumers():
    from rasai import console_provider_environment as facade
    from rasai.console_config import is_secret
    from rasai.gsc_scope import GSC_ENABLED_ENV, GSC_SITE_URL_ENV
    from rasai import standards_gsc_policy as policy

    declared = {
        GSC_ENABLED_ENV, GSC_SITE_URL_ENV,
        *policy.environment_names(),
    }
    specs = {spec.name: spec for spec in facade.refresh_specs()}
    assert declared.issubset(specs)
    assert all(not specs[name].sensitive and not is_secret(name)
               for name in declared)
    # Never allow an OAuth access token or refresh token in operator INI.
    from rasai.gsc_oauth import ACCESS_TOKEN_ENV, REFRESH_TOKEN_ENV
    assert ACCESS_TOKEN_ENV not in declared and REFRESH_TOKEN_ENV not in declared


def test_523_gsc_policy_validation_is_shared_with_real_runtime():
    import pytest
    from rasai.console_provider_environment import _validate
    from rasai import standards_gsc_policy as policy
    assert _validate(policy.GSC_SEARCH_ANALYTICS_DAYS_ENV, "0") == "0"
    assert _validate(policy.GSC_SEARCH_MAX_ROWS_ENV, "50000") == "50000"
    assert _validate(policy.GSC_FINAL_DATA_LAG_DAYS_ENV, "30") == "30"
    for name, candidate in (
        (policy.GSC_SEARCH_ANALYTICS_DAYS_ENV, "32"),
        (policy.GSC_SEARCH_MAX_ROWS_ENV, "0"),
        (policy.GSC_FINAL_DATA_LAG_DAYS_ENV, "31"),
        (policy.GSC_SEARCH_MAX_ROWS_ENV, "-3"),
        (policy.GSC_SEARCH_MAX_ROWS_ENV, "Infinity"),
        (policy.GSC_SEARCH_MAX_ROWS_ENV, "7.5"),
    ):
        with pytest.raises(ValueError):
            _validate(name, candidate)
    with pytest.raises(ValueError):
        _validate("RASAI_GOOGLE_SEARCH_CONSOLE_SITE_URL",
                  "https://user:secret@shop.example.org/secret?token=x")
    assert _validate("RASAI_GOOGLE_SEARCH_CONSOLE_SITE_URL",
                     "sc-domain:example.org") == "sc-domain:example.org"


def test_523_gsc_physical_ini_reload_preserves_saved_nonsecret_limits(tmp_path):
    from rasai import console_settings
    from rasai.console_search_intelligence import SearchConsoleState
    from rasai.console_ui_refactor import _install_search_persistence
    from rasai.console_complete_persistence import install
    from rasai import standards_gsc_policy as policy
    _install_search_persistence()
    install()
    from rasai.gsc_scope import GSC_ENABLED_ENV, GSC_SITE_URL_ENV

    overrides = {
        GSC_ENABLED_ENV: "true",
        GSC_SITE_URL_ENV: "sc-domain:example.org",
        policy.GSC_SEARCH_ANALYTICS_DAYS_ENV: "0",
        policy.GSC_SEARCH_MAX_ROWS_ENV: "42",
        policy.GSC_FINAL_DATA_LAG_DAYS_ENV: "0",
    }
    with patch.dict(os.environ, overrides, clear=True):
        source = tmp_path / "save.ini"
        console_settings.save_console_config(SearchConsoleState(), source)
        saved = source.read_bytes()
        assert b"RASAI_GSC_SEARCH_MAX_ROWS = 42" in saved
        assert b"RASAI_GSC_SEARCH_ANALYTICS_DAYS = 0" in saved
        os.environ.clear()
        state = SearchConsoleState()
        loaded = console_settings.load_console_config(state, source)
        assert not loaded.created and not loaded.warnings
        for name, value in overrides.items():
            assert os.environ.get(name) == value
        assert source.read_bytes() == saved
        report = inspect_gsc_consumers(source, environ={})
        assert report["status"] == "TARGET_NOT_PREPARED"
        assert report["canonical_gsc_ini_keys_restored"] is True


def test_523_gsc_invalid_ini_value_is_rejected_before_environment_effect(tmp_path):
    from rasai import console_settings
    from rasai.console_search_intelligence import SearchConsoleState
    from rasai.console_ui_refactor import _install_search_persistence
    from rasai.console_complete_persistence import install
    from rasai.standards_gsc_policy import GSC_SEARCH_MAX_ROWS_ENV

    _install_search_persistence()
    install()
    source = _ini(tmp_path, rows="50001")
    previous = source.read_bytes()
    with patch.dict(os.environ, {}, clear=True):
        state = SearchConsoleState()
        load = console_settings.load_console_config(state, source)
        assert not load.created
        assert any("environment." + GSC_SEARCH_MAX_ROWS_ENV in warning
                   for warning in load.warnings)
        assert GSC_SEARCH_MAX_ROWS_ENV not in os.environ
        assert state.config_dirty is True
        assert source.read_bytes() == previous
        summary = inspect_gsc_consumers(source, environ={})
        assert summary["status"] == "INI_LOAD_WARNINGS"
        assert summary["source_status"] == "READY"
        assert source.read_bytes() == previous


def test_523_gsc_save_does_not_destroy_operator_ini_on_invalid_override(tmp_path):
    import pytest
    from rasai import console_settings
    from rasai.console_search_intelligence import SearchConsoleState
    from rasai.console_ui_refactor import _install_search_persistence
    from rasai.console_complete_persistence import install
    from rasai.standards_gsc_policy import GSC_FINAL_DATA_LAG_DAYS_ENV

    _install_search_persistence()
    install()
    path = tmp_path / "existing.ini"
    with patch.dict(os.environ, {}, clear=True):
        state = SearchConsoleState()
        state.target = "https://shop.example.org"
        console_settings.save_console_config(state, path)
        before = path.read_bytes()
        os.environ[GSC_FINAL_DATA_LAG_DAYS_ENV] = "31"
        with pytest.raises(ValueError, match="environment\\." + GSC_FINAL_DATA_LAG_DAYS_ENV):
            console_settings.save_console_config(state, path)
        assert path.read_bytes() == before
        del os.environ[GSC_FINAL_DATA_LAG_DAYS_ENV]
        console_settings.save_console_config(state, path)
        assert path.read_bytes() == before


def test_523_gsc_invalid_member_must_abstain_entire_ini_group(tmp_path):
    """Invalid row caps cannot partially enable REQUIRED GSC on reload."""
    from rasai import console_settings, standards_gsc_policy as policy
    from rasai.gsc_scope import GSC_ENABLED_ENV, GSC_SITE_URL_ENV
    from rasai.console_search_intelligence import SearchConsoleState
    from rasai.console_ui_refactor import _install_search_persistence
    from rasai.console_complete_persistence import install
    _install_search_persistence()
    install()
    physical_source = _ini(tmp_path, rows="50001")
    saved = physical_source.read_bytes()
    with patch.dict(os.environ, {"RASAI_EXTERNAL_SESSION_FLAG": "intact"}, clear=True):
        state = SearchConsoleState()
        outcome = console_settings.load_console_config(state, physical_source)
        assert not outcome.created
        assert state.config_dirty is True
        assert any("environment.GSC: grupo GSC" in w for w in outcome.warnings)
        for key in (
            GSC_ENABLED_ENV, GSC_SITE_URL_ENV,
            policy.GSC_SEARCH_ANALYTICS_DAYS_ENV,
            policy.GSC_SEARCH_MAX_ROWS_ENV,
            policy.GSC_FINAL_DATA_LAG_DAYS_ENV,
        ):
            assert key not in os.environ
        assert os.environ["RASAI_EXTERNAL_SESSION_FLAG"] == "intact"
        assert physical_source.read_bytes() == saved


def test_523_gsc_override_precedence_preserved_for_existing_session_value(tmp_path):
    """An intentional session override is not overwritten by an older INI."""
    from rasai import console_settings, standards_gsc_policy as policy
    from rasai.console_search_intelligence import SearchConsoleState
    from rasai.console_ui_refactor import _install_search_persistence
    from rasai.console_complete_persistence import install
    _install_search_persistence()
    install()
    physical_source = _ini(tmp_path, rows="50001")
    physical = physical_source.read_bytes()
    with patch.dict(
        os.environ, {policy.GSC_SEARCH_MAX_ROWS_ENV: "20"}, clear=True,
    ):
        state = SearchConsoleState()
        result = console_settings.load_console_config(state, physical_source)
        assert not result.created
        assert not any("environment.GSC: grupo GSC" in x for x in result.warnings)
        assert os.environ[policy.GSC_SEARCH_MAX_ROWS_ENV] == "20"
        assert os.environ["RASAI_GSC_ENABLED"] == "true"
        assert os.environ["RASAI_GOOGLE_SEARCH_CONSOLE_SITE_URL"] == (
            "sc-domain:example.org"
        )
        assert physical_source.read_bytes() == physical
