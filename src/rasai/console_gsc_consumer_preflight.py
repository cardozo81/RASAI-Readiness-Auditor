"""#523 GSC consumer preflight: policy, static property scope, OAuth presence only.

No Google API request, refresh exchange, browser, credential logging, AUD
mutation, or implicit execution authorization. A locally compatible property
does not prove its owner's Google permissions or data finality.
"""
from __future__ import annotations

from hashlib import sha256
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Mapping

from rasai.console_apdex_effective_validation import _verified_source

CONTRACT = "RASAI-GSC-INI-TO-CONSUMER-523-001"


def inspect_gsc_consumers(
    ini_path: Path, *, environ: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    base: dict[str, Any] = {
        "contract": CONTRACT, "status": "NOT_VERIFIABLE",
        "source_status": "SOURCE_UNAVAILABLE",
        "gsc_mode": None, "oauth_configuration_mode": None,
        "oauth_credentials_locally_configured": False,
        "property_scope_compatible": None,
        "policy_bounds_verified": False,
        "target_prepared": False,
        "gsc_data_finality_verified": False,
        "authenticated_property_access_verified": False,
        "real_gsc_api_usage_verified": False,
        "paid_request_authorized": False,
        "values_exposed": False, "audit_writes": 0,
        "ini_source_writes": 0, "provider_requests": 0,
    }
    source = Path(ini_path)
    raw, identity, status = _verified_source(source)
    if status != "READY":
        return {**base, "status": status, "source_status": status}
    assert raw is not None and identity is not None
    original_digest = sha256(raw).digest()
    original_environment = dict(os.environ)
    try:
        if environ is not None:
            os.environ.clear()
            os.environ.update(environ)
        from rasai import console_settings, gsc_scope, gsc_oauth
        from rasai import standards_gsc_policy as policy
        from rasai.console_search_intelligence import SearchConsoleState
        from rasai.console_complete_persistence import install
        from rasai.console_ui_refactor import _install_search_persistence
        from rasai.cli import validate_target

        _install_search_persistence()
        install()
        with TemporaryDirectory(prefix="rasai-gsc-preflight-523-") as folder:
            duplicate = Path(folder) / "detached.ini"
            duplicate.write_bytes(raw)
            state = SearchConsoleState()
            loaded = console_settings.load_console_config(state, duplicate)
            if loaded.created or loaded.warnings:
                return {**base, "status": "INI_LOAD_WARNINGS",
                        "source_status": "READY"}

            environment = dict(os.environ)
            mode = gsc_scope.gsc_request_mode(environment)
            oauth = gsc_oauth.credential_state(environment)
            if mode == gsc_scope.MODE_INVALID:
                result_state = "GSC_MODE_INVALID"
            else:
                result_state = "NOT_VERIFIABLE"
            # Resolve policy with the real runtime bounded functions, even
            # when GSC is OFF. A malformed policy is not silently normalized.
            bounded = (
                policy.search_analytics_days(environment.get(policy.GSC_SEARCH_ANALYTICS_DAYS_ENV)),
                policy.search_max_rows(environment.get(policy.GSC_SEARCH_MAX_ROWS_ENV)),
                policy.final_data_lag_days(environment.get(policy.GSC_FINAL_DATA_LAG_DAYS_ENV)),
            )
            policy_verified = all(type(item) is int for item in bounded)
            target = str(state.target or "").strip()
            target_prepared = bool(target)
            site_url = str(environment.get(gsc_scope.GSC_SITE_URL_ENV) or "").strip()
            covered: bool | None = None
            if mode == gsc_scope.MODE_DISABLED:
                result_state = "GSC_DISABLED_BY_CONFIGURATION"
            elif mode == gsc_scope.MODE_INVALID:
                result_state = "GSC_MODE_INVALID"
            elif not target_prepared:
                result_state = "TARGET_NOT_PREPARED"
            else:
                validated_target = validate_target(target)
                absolute_target = (
                    validated_target if "://" in validated_target
                    else "https://" + validated_target
                )
                if site_url:
                    try:
                        covered = gsc_scope.gsc_property_covers_url(
                            site_url, absolute_target,
                        )
                    except ValueError:
                        result_state = "GSC_PROPERTY_SCOPE_INVALID"
                    else:
                        if not covered:
                            result_state = "GSC_PROPERTY_TARGET_MISMATCH"
                        elif oauth.mode == gsc_oauth.MODE_INVALID:
                            result_state = "GSC_OAUTH_CONFIGURATION_INVALID"
                        elif not oauth.configured:
                            result_state = (
                                "REQUIRED_OAUTH_NOT_CONFIGURED"
                                if mode == gsc_scope.MODE_REQUIRED
                                else "AUTO_OAUTH_NOT_CONFIGURED"
                            )
                        else:
                            result_state = "LOCAL_SCOPE_AND_OAUTH_CONFIG_VERIFIED"
                elif mode == gsc_scope.MODE_REQUIRED:
                    result_state = "REQUIRED_PROPERTY_NOT_CONFIGURED"
                else:
                    result_state = "AUTO_PROPERTY_NOT_CONFIGURED"

        checked, after_identity, after_status = _verified_source(source)
        if (after_status != "READY" or after_identity != identity
                or checked is None
                or sha256(checked).digest() != original_digest):
            return {**base, "status": "SOURCE_CHANGED",
                    "source_status": "SOURCE_CHANGED"}
        return {
            **base, "status": result_state, "source_status": "READY",
            "gsc_mode": mode,
            "oauth_configuration_mode": oauth.mode,
            "oauth_credentials_locally_configured": bool(oauth.configured),
            "property_scope_compatible": covered,
            "policy_bounds_verified": policy_verified,
            "target_prepared": target_prepared,
        }
    except (OSError, ValueError, TypeError, OverflowError, UnicodeError):
        return {**base, "status": "INI_OR_GSC_POLICY_INVALID",
                "source_status": "READY"}
    finally:
        os.environ.clear()
        os.environ.update(original_environment)


__all__ = ["inspect_gsc_consumers", "CONTRACT"]
