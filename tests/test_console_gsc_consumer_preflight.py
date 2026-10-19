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
            "INI_OR_GSC_POLICY_INVALID"
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
