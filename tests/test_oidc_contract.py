from __future__ import annotations

import asyncio

import pytest

from rasai.web.oidc import OidcRuntime, OidcSettings, OidcUnavailableError


def _settings(issuer: str = "https://login.example.test") -> OidcSettings:
    return OidcSettings(
        issuer=issuer,
        client_id="rasai-web",
        audience="rasai-api",
        redirect_uri="https://rasai.example.test/auth/callback",
    )


def test_discovery_requires_exact_issuer_match() -> None:
    settings = _settings()

    async def mismatched(_url: str):
        return {
            "issuer": settings.issuer + "/",
            "authorization_endpoint": "https://login.example.test/authorize",
            "token_endpoint": "https://login.example.test/token",
            "jwks_uri": "https://login.example.test/jwks",
        }

    runtime = OidcRuntime(settings, json_getter=mismatched)
    with pytest.raises(OidcUnavailableError, match="exactly"):
        asyncio.run(runtime.discovery())


def test_discovery_request_removes_only_request_separator_not_issuer_identity() -> None:
    settings = _settings("https://login.example.test/tenant/")
    observed: list[str] = []

    async def exact(url: str):
        observed.append(url)
        return {
            "issuer": settings.issuer,
            "authorization_endpoint": "https://login.example.test/tenant/authorize",
            "token_endpoint": "https://login.example.test/tenant/token",
            "jwks_uri": "https://login.example.test/tenant/jwks",
        }

    runtime = OidcRuntime(settings, json_getter=exact)
    document = asyncio.run(runtime.discovery())
    assert document["issuer"] == "https://login.example.test/tenant/"
    assert observed == ["https://login.example.test/tenant/.well-known/openid-configuration"]


def test_oidc_settings_reject_issuer_query(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RASAI_OIDC_ISSUER", "https://login.example.test?tenant=a")
    monkeypatch.setenv("RASAI_OIDC_CLIENT_ID", "rasai-web")
    monkeypatch.setenv("RASAI_OIDC_REDIRECT_URI", "https://rasai.example.test/auth/callback")
    with pytest.raises(Exception, match="query"):
        OidcSettings.from_environment()
