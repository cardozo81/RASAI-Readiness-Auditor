from __future__ import annotations

import base64
from datetime import UTC, datetime, timedelta
from pathlib import Path
import tempfile
from urllib.parse import parse_qs, urlsplit

import pytest

pytest.importorskip("fastapi")
jwt = pytest.importorskip("jwt")
cryptography = pytest.importorskip("cryptography")

from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from rasai.platform.identity_directory import IdentityDirectory
from rasai.platform.secure_store import SecurePlatformStore
from rasai.web.app import ApiSettings
from rasai.web.auth import ApiAuthSettings
from rasai.web.oidc import OidcRuntime, OidcSettings
from rasai.web.pilot_app import create_app


def _uint(value: int) -> str:
    raw = value.to_bytes((value.bit_length() + 7) // 8, "big")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _fixture_runtime(settings: OidcSettings, private_key: object, nonce_holder: dict[str, str]) -> OidcRuntime:
    public = private_key.public_key().public_numbers()
    jwk = {
        "kty": "RSA",
        "kid": "test-key",
        "use": "sig",
        "alg": "RS256",
        "n": _uint(public.n),
        "e": _uint(public.e),
    }

    async def get_json(url: str):
        if url.endswith("/.well-known/openid-configuration"):
            return {
                "issuer": settings.issuer,
                "authorization_endpoint": settings.issuer + "/authorize",
                "token_endpoint": settings.issuer + "/token",
                "jwks_uri": settings.issuer + "/jwks",
            }
        if url.endswith("/jwks"):
            return {"keys": [jwk]}
        raise AssertionError(f"unexpected OIDC GET: {url}")

    async def post_form(url: str, data):
        assert url == settings.issuer + "/token"
        assert data["grant_type"] == "authorization_code"
        assert data["code_verifier"]
        now = datetime.now(UTC)
        token = jwt.encode(
            {
                "iss": settings.issuer,
                "aud": settings.client_id,
                "sub": "subject-a",
                "nonce": nonce_holder["nonce"],
                "iat": int(now.timestamp()),
                "exp": int((now + timedelta(minutes=5)).timestamp()),
            },
            private_key,
            algorithm="RS256",
            headers={"kid": "test-key"},
        )
        return {"id_token": token, "token_type": "Bearer"}

    return OidcRuntime(settings, json_getter=get_json, form_poster=post_form)


def _bearer(settings: OidcSettings, private_key: object, *, subject: str, expired: bool = False) -> str:
    now = datetime.now(UTC)
    expiration = now - timedelta(minutes=1) if expired else now + timedelta(minutes=5)
    return jwt.encode(
        {
            "iss": settings.issuer,
            "aud": settings.audience,
            "sub": subject,
            "iat": int(now.timestamp()),
            "exp": int(expiration.timestamp()),
        },
        private_key,
        algorithm="RS256",
        headers={"kid": "test-key"},
    )


def test_oidc_bearer_and_browser_session_use_explicit_identity_mapping(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = OidcSettings(
        issuer="https://login.example.test",
        client_id="rasai-web",
        audience="rasai-api",
        redirect_uri="https://rasai.example.test/auth/callback",
        session_secret_env="RASAI_TEST_SESSION_SECRET",
    )
    monkeypatch.setenv("RASAI_TEST_SESSION_SECRET", "0123456789abcdef0123456789abcdef")
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    nonce_holder: dict[str, str] = {}

    with tempfile.TemporaryDirectory() as directory:
        database = Path(directory) / "platform.db"
        seed = SecurePlatformStore(database)
        try:
            organization = seed.get_or_create_organization("Acme")
            workspace = seed.get_or_create_workspace(organization.organization_id, "Search")
            project = seed.get_or_create_project(workspace.workspace_id, "Site")
            user = seed.get_or_create_user("Analyst", email="analyst@example.test")
            seed.add_membership(organization.organization_id, user.user_id, "ANALYST", project_id=project.project_id)
            IdentityDirectory(seed).link(
                user_id=user.user_id,
                issuer=settings.issuer,
                subject="subject-a",
                email=user.email,
            )
        finally:
            seed.close()

        def store_factory():
            return SecurePlatformStore(database)

        app = create_app(
            ApiSettings(
                audits_root=Path(directory),
                auth=ApiAuthSettings(mode="oidc", oidc=settings),
            ),
            store_factory=store_factory,
        )
        app.state.oidc_runtime = _fixture_runtime(settings, private_key, nonce_holder)

        with TestClient(app, base_url="https://rasai.example.test", follow_redirects=False) as client:
            config = client.get("/auth/config")
            assert config.status_code == 200
            assert config.json() == {"mode": "oidc", "browser_login": True, "trusted_header": False}

            token = _bearer(settings, private_key, subject="subject-a")
            me = client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})
            assert me.status_code == 200
            assert me.json()["user_id"] == user.user_id

            unknown = _bearer(settings, private_key, subject="unlinked-subject")
            assert client.get(
                "/api/v1/me", headers={"Authorization": f"Bearer {unknown}"}
            ).status_code == 403

            expired = _bearer(settings, private_key, subject="subject-a", expired=True)
            assert client.get(
                "/api/v1/me", headers={"Authorization": f"Bearer {expired}"}
            ).status_code == 401

            app_redirect = client.get("/app")
            assert app_redirect.status_code == 302
            assert app_redirect.headers["location"] == "/auth/login"

            login = client.get("/auth/login")
            assert login.status_code == 302
            query = parse_qs(urlsplit(login.headers["location"]).query)
            nonce_holder["nonce"] = query["nonce"][0]
            state = query["state"][0]
            assert query["code_challenge_method"] == ["S256"]
            assert query["response_type"] == ["code"]

            callback = client.get(f"/auth/callback?code=test-code&state={state}")
            assert callback.status_code == 303
            assert callback.headers["location"] == "/app"

            session_me = client.get("/api/v1/me")
            assert session_me.status_code == 200
            assert session_me.json()["user_id"] == user.user_id

            blocked_logout = client.post("/auth/logout")
            assert blocked_logout.status_code == 403
            allowed_logout = client.post(
                "/auth/logout",
                headers={"Origin": "https://rasai.example.test"},
            )
            assert allowed_logout.status_code == 303
            assert client.get("/api/v1/me").status_code == 401


def test_oidc_settings_reject_non_tls_hosted_redirect(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RASAI_OIDC_ISSUER", "https://login.example.test")
    monkeypatch.setenv("RASAI_OIDC_CLIENT_ID", "rasai-web")
    monkeypatch.setenv("RASAI_OIDC_REDIRECT_URI", "http://rasai.example.test/auth/callback")
    with pytest.raises(Exception, match="loopback"):
        OidcSettings.from_environment()
