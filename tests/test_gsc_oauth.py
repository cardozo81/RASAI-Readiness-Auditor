from __future__ import annotations

import json
from urllib.error import HTTPError

from rasai.gsc_oauth import (
    ACCESS_TOKEN_ENV,
    CLIENT_ID_ENV,
    CLIENT_SECRET_ENV,
    MODE_INVALID,
    MODE_REFRESH_TOKEN,
    REFRESH_TOKEN_ENV,
    SITE_URL_ENV,
    credential_state,
    resolve_access_token,
)
from rasai.gsc_oauth_runtime import install


class _Response:
    def __init__(self, payload: dict, status: int = 200) -> None:
        self.payload = payload
        self.status = status

    def getcode(self) -> int:
        return self.status

    def read(self, size: int = -1) -> bytes:
        del size
        return json.dumps(self.payload).encode("utf-8")

    def close(self) -> None:
        return None


def _refresh_env() -> dict[str, str]:
    return {
        CLIENT_ID_ENV: "client-id",
        CLIENT_SECRET_ENV: "client-secret",
        REFRESH_TOKEN_ENV: "refresh-token",
        SITE_URL_ENV: "sc-domain:example.test",
        "RASAI_GSC_ENABLED": "true",
    }


def test_api_key_is_rejected_as_wrong_gsc_credential_type() -> None:
    state = credential_state({ACCESS_TOKEN_ENV: "AIza-example", SITE_URL_ENV: "sc-domain:example.test"})
    assert state.mode == MODE_INVALID
    assert state.configured is False
    assert "API Key" in state.detail


def test_complete_refresh_credentials_are_preferred_and_exchanged_only_in_memory() -> None:
    env = _refresh_env()
    seen: list[tuple[str, str, bytes]] = []

    def opener(request, timeout=0):
        del timeout
        seen.append((request.full_url, request.method, bytes(request.data or b"")))
        return _Response({"access_token": "temporary-access-token", "expires_in": 3599, "token_type": "Bearer"})

    assert credential_state(env).mode == MODE_REFRESH_TOKEN
    token = resolve_access_token(env, opener=opener)
    assert token == "temporary-access-token"
    assert ACCESS_TOKEN_ENV not in env
    assert len(seen) == 1
    assert seen[0][0] == "https://oauth2.googleapis.com/token"
    assert seen[0][1] == "POST"
    assert b"grant_type=refresh_token" in seen[0][2]


def test_runtime_service_state_accepts_refresh_mode_without_manual_access_token() -> None:
    install()
    from rasai.standards_service_registry import service, service_state

    state = service_state(service("google-search-console"), _refresh_env())
    assert state["configured"] is True
    assert state["effective_enabled"] is True
    assert state["oauth_mode"] == MODE_REFRESH_TOKEN


def test_integration_diagnostic_refreshes_then_validates_configured_property() -> None:
    install()
    from rasai.integration_diagnostics import STATUS_OPERATIONAL, integration_specs, run_diagnostic

    calls: list[str] = []

    def opener(request, timeout=0):
        del timeout
        calls.append(request.full_url)
        if request.full_url == "https://oauth2.googleapis.com/token":
            return _Response({"access_token": "temporary-access-token", "expires_in": 3599})
        assert request.headers.get("Authorization") == "Bearer temporary-access-token"
        return _Response({"siteEntry": [{"siteUrl": "sc-domain:example.test", "permissionLevel": "siteOwner"}]})

    spec = next(item for item in integration_specs() if item.id == "service:google-search-console")
    names = {item.name for item in spec.dependencies}
    assert {ACCESS_TOKEN_ENV, CLIENT_ID_ENV, CLIENT_SECRET_ENV, REFRESH_TOKEN_ENV, SITE_URL_ENV} <= names
    result = run_diagnostic(spec, env=_refresh_env(), opener=opener)
    assert result.status == STATUS_OPERATIONAL
    assert calls == ["https://oauth2.googleapis.com/token", "https://www.googleapis.com/webmasters/v3/sites"]
    assert "temporary-access-token" not in result.detail
    assert "refresh-token" not in result.detail


def test_invalid_grant_is_authentication_error_not_network_failure() -> None:
    install()
    from rasai.integration_diagnostics import STATUS_AUTHENTICATION_ERROR, integration_specs, run_diagnostic

    def opener(request, timeout=0):
        del timeout
        if request.full_url == "https://oauth2.googleapis.com/token":
            body = json.dumps({"error": "invalid_grant", "error_description": "grant revoked"}).encode("utf-8")
            raise HTTPError(request.full_url, 400, "Bad Request", {}, NoneWithRead(body))
        raise AssertionError("GSC endpoint must not be called after invalid_grant")

    spec = next(item for item in integration_specs() if item.id == "service:google-search-console")
    result = run_diagnostic(spec, env=_refresh_env(), opener=opener)
    assert result.status == STATUS_AUTHENTICATION_ERROR
    assert "refresh-token" not in result.detail
    assert "client-secret" not in result.detail


class NoneWithRead:
    def __init__(self, body: bytes) -> None:
        self.body = body

    def read(self, size: int = -1) -> bytes:
        del size
        return self.body

    def close(self) -> None:
        return None
