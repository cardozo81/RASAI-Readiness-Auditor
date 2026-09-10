"""Provider-neutral OIDC/JWT primitives for the optional RASAi Web surface.

The module validates standards-based identities without introducing an RASAi password
store or proprietary bearer-token format. Hosted secrets remain environment-provided
and are never persisted in the control plane.
"""
from __future__ import annotations

import asyncio
import base64
from dataclasses import dataclass
import hashlib
import json
import os
import secrets
import time
from typing import Any, Awaitable, Callable, Mapping
from urllib.parse import urlencode, urlsplit


OIDC_ISSUER_ENV = "RASAI_OIDC_ISSUER"
OIDC_CLIENT_ID_ENV = "RASAI_OIDC_CLIENT_ID"
OIDC_AUDIENCE_ENV = "RASAI_OIDC_AUDIENCE"
OIDC_REDIRECT_URI_ENV = "RASAI_OIDC_REDIRECT_URI"
OIDC_SESSION_SECRET_ENV = "RASAI_OIDC_SESSION_SECRET"
OIDC_CLIENT_SECRET_ENV_REF = "RASAI_OIDC_CLIENT_SECRET_ENV"
OIDC_ALGORITHMS_ENV = "RASAI_OIDC_ALGORITHMS"
OIDC_SCOPES_ENV = "RASAI_OIDC_SCOPES"
OIDC_SESSION_TTL_ENV = "RASAI_OIDC_SESSION_TTL_SECONDS"


class OidcConfigurationError(RuntimeError):
    pass


class OidcUnavailableError(RuntimeError):
    pass


class OidcTokenError(ValueError):
    pass


def _absolute_https(value: str, *, field: str) -> str:
    text = value.strip()
    parts = urlsplit(text)
    if parts.scheme != "https" or not parts.hostname or parts.fragment:
        raise OidcConfigurationError(f"{field} must be an absolute HTTPS URL without fragment")
    return text


def _redirect_uri(value: str) -> str:
    text = value.strip()
    parts = urlsplit(text)
    if not parts.hostname or parts.fragment or parts.scheme not in {"https", "http"}:
        raise OidcConfigurationError("RASAI_OIDC_REDIRECT_URI must be an absolute HTTP(S) URL without fragment")
    if parts.scheme == "http" and parts.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise OidcConfigurationError("HTTP OIDC redirect URI is allowed only for loopback development")
    return text


def _csv(value: str, default: tuple[str, ...]) -> tuple[str, ...]:
    items = tuple(dict.fromkeys(item.strip() for item in value.split(",") if item.strip()))
    return items or default


@dataclass(frozen=True, slots=True)
class OidcSettings:
    issuer: str
    client_id: str
    audience: str
    redirect_uri: str
    algorithms: tuple[str, ...] = ("RS256", "ES256")
    scopes: tuple[str, ...] = ("openid", "profile", "email")
    session_secret_env: str = OIDC_SESSION_SECRET_ENV
    client_secret_env: str | None = None
    session_cookie_name: str = "rasai_session"
    transaction_cookie_name: str = "rasai_oidc_transaction"
    session_ttl_seconds: int = 28800
    request_timeout_seconds: float = 5.0
    clock_skew_seconds: int = 60

    @classmethod
    def from_environment(cls) -> "OidcSettings":
        issuer = _absolute_https(os.getenv(OIDC_ISSUER_ENV, ""), field=OIDC_ISSUER_ENV).rstrip("/")
        client_id = os.getenv(OIDC_CLIENT_ID_ENV, "").strip()
        if not client_id:
            raise OidcConfigurationError(f"{OIDC_CLIENT_ID_ENV} is required for oidc auth mode")
        audience = os.getenv(OIDC_AUDIENCE_ENV, client_id).strip()
        if not audience:
            raise OidcConfigurationError(f"{OIDC_AUDIENCE_ENV} cannot be empty")
        redirect_uri = _redirect_uri(os.getenv(OIDC_REDIRECT_URI_ENV, ""))
        algorithms = _csv(os.getenv(OIDC_ALGORITHMS_ENV, "RS256,ES256"), ("RS256", "ES256"))
        unsafe = sorted(set(algorithms) - {"RS256", "RS384", "RS512", "ES256", "ES384", "ES512"})
        if unsafe:
            raise OidcConfigurationError("unsupported OIDC signing algorithm(s): " + ", ".join(unsafe))
        scopes = _csv(os.getenv(OIDC_SCOPES_ENV, "openid,profile,email"), ("openid", "profile", "email"))
        if "openid" not in scopes:
            raise OidcConfigurationError("OIDC scopes must include openid")
        secret_ref = os.getenv(OIDC_CLIENT_SECRET_ENV_REF, "").strip() or None
        if secret_ref and (not secret_ref.replace("_", "").isalnum() or secret_ref[0].isdigit()):
            raise OidcConfigurationError(f"{OIDC_CLIENT_SECRET_ENV_REF} must name an environment variable")
        raw_ttl = os.getenv(OIDC_SESSION_TTL_ENV, "28800").strip()
        try:
            session_ttl = int(raw_ttl)
        except ValueError as exc:
            raise OidcConfigurationError(f"{OIDC_SESSION_TTL_ENV} must be an integer") from exc
        if session_ttl < 300 or session_ttl > 86400:
            raise OidcConfigurationError(f"{OIDC_SESSION_TTL_ENV} must be between 300 and 86400")
        return cls(
            issuer=issuer,
            client_id=client_id,
            audience=audience,
            redirect_uri=redirect_uri,
            algorithms=algorithms,
            scopes=scopes,
            client_secret_env=secret_ref,
            session_ttl_seconds=session_ttl,
        )

    @property
    def cookie_secure(self) -> bool:
        return urlsplit(self.redirect_uri).scheme == "https"

    @property
    def public_origin(self) -> str:
        parts = urlsplit(self.redirect_uri)
        return f"{parts.scheme}://{parts.netloc}"


JsonGetter = Callable[[str], Awaitable[Mapping[str, Any]]]
FormPoster = Callable[[str, Mapping[str, str]], Awaitable[Mapping[str, Any]]]


class OidcRuntime:
    """OIDC discovery/JWKS client with bounded in-memory caching."""

    def __init__(
        self,
        settings: OidcSettings,
        *,
        json_getter: JsonGetter | None = None,
        form_poster: FormPoster | None = None,
        cache_ttl_seconds: int = 300,
    ) -> None:
        self.settings = settings
        self._json_getter = json_getter or self._default_get_json
        self._form_poster = form_poster or self._default_post_form
        self._cache_ttl = max(30, min(int(cache_ttl_seconds), 3600))
        self._discovery: tuple[float, dict[str, Any]] | None = None
        self._jwks: tuple[float, dict[str, Any]] | None = None
        self._lock = asyncio.Lock()

    async def _default_get_json(self, url: str) -> Mapping[str, Any]:
        try:
            import httpx
        except ImportError as exc:
            raise OidcConfigurationError("RASAi web dependencies are incomplete; install .[web]") from exc
        try:
            async with httpx.AsyncClient(timeout=self.settings.request_timeout_seconds, follow_redirects=False) as client:
                response = await client.get(url, headers={"Accept": "application/json"})
                response.raise_for_status()
                payload = response.json()
        except Exception as exc:
            raise OidcUnavailableError("OIDC metadata request failed") from exc
        if not isinstance(payload, dict):
            raise OidcUnavailableError("OIDC metadata response must be a JSON object")
        return payload

    async def _default_post_form(self, url: str, data: Mapping[str, str]) -> Mapping[str, Any]:
        try:
            import httpx
        except ImportError as exc:
            raise OidcConfigurationError("RASAi web dependencies are incomplete; install .[web]") from exc
        try:
            async with httpx.AsyncClient(timeout=self.settings.request_timeout_seconds, follow_redirects=False) as client:
                response = await client.post(
                    url,
                    data=dict(data),
                    headers={"Accept": "application/json"},
                )
                response.raise_for_status()
                payload = response.json()
        except Exception as exc:
            raise OidcUnavailableError("OIDC token exchange failed") from exc
        if not isinstance(payload, dict):
            raise OidcUnavailableError("OIDC token response must be a JSON object")
        return payload

    async def discovery(self, *, force_refresh: bool = False) -> dict[str, Any]:
        now = time.monotonic()
        if not force_refresh and self._discovery and self._discovery[0] > now:
            return dict(self._discovery[1])
        async with self._lock:
            now = time.monotonic()
            if not force_refresh and self._discovery and self._discovery[0] > now:
                return dict(self._discovery[1])
            url = self.settings.issuer + "/.well-known/openid-configuration"
            document = dict(await self._json_getter(url))
            if str(document.get("issuer", "")).rstrip("/") != self.settings.issuer:
                raise OidcUnavailableError("OIDC discovery issuer does not match configured issuer")
            for key in ("authorization_endpoint", "token_endpoint", "jwks_uri"):
                document[key] = _absolute_https(str(document.get(key, "")), field=f"OIDC {key}")
            self._discovery = (now + self._cache_ttl, document)
            return dict(document)

    async def jwks(self, *, force_refresh: bool = False) -> dict[str, Any]:
        now = time.monotonic()
        if not force_refresh and self._jwks and self._jwks[0] > now:
            return dict(self._jwks[1])
        document = await self.discovery(force_refresh=force_refresh)
        async with self._lock:
            now = time.monotonic()
            if not force_refresh and self._jwks and self._jwks[0] > now:
                return dict(self._jwks[1])
            payload = dict(await self._json_getter(str(document["jwks_uri"])))
            keys = payload.get("keys")
            if not isinstance(keys, list) or not keys:
                raise OidcUnavailableError("OIDC JWKS does not contain signing keys")
            self._jwks = (now + self._cache_ttl, payload)
            return dict(payload)

    async def _jwk_for_token(self, token: str) -> tuple[str, Mapping[str, Any]]:
        try:
            import jwt
            header = jwt.get_unverified_header(token)
        except Exception as exc:
            raise OidcTokenError("invalid JWT header") from exc
        algorithm = str(header.get("alg", ""))
        kid = str(header.get("kid", ""))
        if algorithm not in self.settings.algorithms:
            raise OidcTokenError("JWT signing algorithm is not allowed")
        if not kid:
            raise OidcTokenError("JWT kid header is required")
        for refresh in (False, True):
            payload = await self.jwks(force_refresh=refresh)
            for key in payload.get("keys", []):
                if isinstance(key, dict) and str(key.get("kid", "")) == kid:
                    key_alg = key.get("alg")
                    if key_alg and str(key_alg) != algorithm:
                        raise OidcTokenError("JWT key algorithm does not match token algorithm")
                    return algorithm, key
        raise OidcTokenError("JWT signing key was not found")

    async def verify_jwt(
        self,
        token: str,
        *,
        audience: str,
        nonce: str | None = None,
    ) -> dict[str, Any]:
        if not token or len(token) > 32768:
            raise OidcTokenError("invalid bearer token")
        algorithm, jwk = await self._jwk_for_token(token)
        try:
            import jwt
            key = jwt.PyJWK.from_dict(dict(jwk), algorithm=algorithm).key
            claims = jwt.decode(
                token,
                key=key,
                algorithms=[algorithm],
                audience=audience,
                issuer=self.settings.issuer,
                leeway=self.settings.clock_skew_seconds,
                options={"require": ["exp", "iss", "aud", "sub"]},
            )
        except Exception as exc:
            raise OidcTokenError("JWT validation failed") from exc
        subject = claims.get("sub")
        if not isinstance(subject, str) or not subject.strip():
            raise OidcTokenError("JWT subject is missing")
        if nonce is not None:
            actual = claims.get("nonce")
            if not isinstance(actual, str) or not secrets.compare_digest(actual, nonce):
                raise OidcTokenError("OIDC nonce validation failed")
        return dict(claims)

    async def authorization_url(self, *, state: str, nonce: str, code_challenge: str) -> str:
        document = await self.discovery()
        parameters = {
            "client_id": self.settings.client_id,
            "redirect_uri": self.settings.redirect_uri,
            "response_type": "code",
            "scope": " ".join(self.settings.scopes),
            "state": state,
            "nonce": nonce,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }
        return str(document["authorization_endpoint"]) + "?" + urlencode(parameters)

    async def exchange_code(self, *, code: str, code_verifier: str) -> dict[str, Any]:
        document = await self.discovery()
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "client_id": self.settings.client_id,
            "redirect_uri": self.settings.redirect_uri,
            "code_verifier": code_verifier,
        }
        if self.settings.client_secret_env:
            secret = os.getenv(self.settings.client_secret_env)
            if not secret:
                raise OidcConfigurationError(
                    f"configured OIDC client secret environment variable is not set: {self.settings.client_secret_env}"
                )
            data["client_secret"] = secret
        payload = dict(await self._form_poster(str(document["token_endpoint"]), data))
        if not isinstance(payload.get("id_token"), str):
            raise OidcTokenError("OIDC token response did not include id_token")
        return payload


def pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(48)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


class SessionCodec:
    """Encrypted/authenticated short-lived browser state using a deployment secret."""

    def __init__(self, secret: str) -> None:
        raw = secret.encode("utf-8")
        if len(raw) < 32:
            raise OidcConfigurationError("OIDC session secret must contain at least 32 UTF-8 bytes")
        try:
            from cryptography.fernet import Fernet
        except ImportError as exc:
            raise OidcConfigurationError("RASAi web crypto dependencies are incomplete; install .[web]") from exc
        key = base64.urlsafe_b64encode(hashlib.sha256(raw).digest())
        self._fernet = Fernet(key)

    @classmethod
    def from_settings(cls, settings: OidcSettings) -> "SessionCodec":
        secret = os.getenv(settings.session_secret_env)
        if not secret:
            raise OidcConfigurationError(
                f"OIDC session secret is required in environment variable {settings.session_secret_env}"
            )
        return cls(secret)

    def encode(self, payload: Mapping[str, Any], *, ttl_seconds: int) -> str:
        now = int(time.time())
        document = {"v": 1, "iat": now, "exp": now + int(ttl_seconds), **dict(payload)}
        raw = json.dumps(document, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode("utf-8")
        return self._fernet.encrypt(raw).decode("ascii")

    def decode(self, token: str) -> dict[str, Any]:
        try:
            from cryptography.fernet import InvalidToken
            raw = self._fernet.decrypt(token.encode("ascii"))
            document = json.loads(raw.decode("utf-8"))
        except (InvalidToken, UnicodeError, ValueError, json.JSONDecodeError) as exc:
            raise OidcTokenError("invalid browser session") from exc
        if not isinstance(document, dict) or document.get("v") != 1:
            raise OidcTokenError("invalid browser session")
        exp = document.get("exp")
        if not isinstance(exp, int) or exp < int(time.time()):
            raise OidcTokenError("browser session expired")
        return dict(document)


def runtime_for_app(app: Any, settings: OidcSettings) -> OidcRuntime:
    runtime = getattr(app.state, "oidc_runtime", None)
    if runtime is None:
        runtime = OidcRuntime(settings)
        app.state.oidc_runtime = runtime
    return runtime


def session_codec_for_app(app: Any, settings: OidcSettings) -> SessionCodec:
    codec = getattr(app.state, "oidc_session_codec", None)
    if codec is None:
        codec = SessionCodec.from_settings(settings)
        app.state.oidc_session_codec = codec
    return codec
