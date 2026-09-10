"""Authentication boundary for the optional RASAi API.

RASAi never stores passwords and never invents a proprietary bearer-token format.
Hosted deployments can validate OIDC JWTs directly and map the provider's stable
``issuer + sub`` identity to an internal ``USR-*`` principal. ``trusted-header``
remains available for a separately authenticated gateway and local development.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Awaitable, Callable

from fastapi import HTTPException, Request, status

from rasai.platform.identity_directory import IdentityDirectory

from .authz import Principal
from .oidc import (
    OidcConfigurationError,
    OidcSettings,
    OidcTokenError,
    OidcUnavailableError,
    runtime_for_app,
    session_codec_for_app,
)

AUTH_MODE_ENV = "RASAI_API_AUTH_MODE"
TRUSTED_USER_HEADER_ENV = "RASAI_API_TRUSTED_USER_HEADER"


@dataclass(frozen=True, slots=True)
class ApiAuthSettings:
    mode: str = "deny"
    trusted_user_header: str = "x-rasai-user-id"
    oidc: OidcSettings | None = None

    @classmethod
    def from_environment(cls) -> "ApiAuthSettings":
        mode = os.getenv(AUTH_MODE_ENV, "deny").strip().casefold()
        if mode not in {"deny", "trusted-header", "oidc"}:
            raise ValueError(
                f"unsupported RASAi API auth mode: {mode}; supported: deny, trusted-header, oidc"
            )
        header = os.getenv(TRUSTED_USER_HEADER_ENV, "x-rasai-user-id").strip().casefold()
        if not header or any(character.isspace() for character in header):
            raise ValueError("RASAi API trusted user header must be a valid non-empty header name")
        oidc = None
        if mode == "oidc":
            try:
                oidc = OidcSettings.from_environment()
            except OidcConfigurationError as exc:
                raise ValueError(str(exc)) from exc
        return cls(mode=mode, trusted_user_header=header, oidc=oidc)


PrincipalResolver = Callable[[Request], Awaitable[Principal]]


def _trusted_header_principal(request: Request, settings: ApiAuthSettings) -> Principal:
    raw = request.headers.get(settings.trusted_user_header)
    if raw is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="authenticated user is required")
    user_id = raw.strip()
    if not user_id or len(user_id) > 200 or any(character.isspace() for character in user_id):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid authenticated user identity")
    return Principal(user_id=user_id)


def _bearer_token(request: Request) -> str | None:
    raw = request.headers.get("authorization")
    if raw is None:
        return None
    scheme, separator, token = raw.partition(" ")
    if not separator or scheme.casefold() != "bearer" or not token.strip():
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid Authorization header")
    return token.strip()


def _mapped_principal(request: Request, *, issuer: str, subject: str) -> Principal:
    store = request.app.state.store_factory()
    try:
        user_id = IdentityDirectory(store).resolve_user_id(issuer=issuer, subject=subject)
    finally:
        store.close()
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="authenticated identity is not linked to an active RASAi user",
        )
    return Principal(user_id=user_id)


def build_principal_resolver(settings: ApiAuthSettings) -> PrincipalResolver:
    async def resolve(request: Request) -> Principal:
        if settings.mode == "deny":
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="RASAi API authentication is not configured",
            )
        if settings.mode == "trusted-header":
            return _trusted_header_principal(request, settings)
        oidc = settings.oidc
        if oidc is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="RASAi OIDC authentication is not configured",
            )
        try:
            bearer = _bearer_token(request)
            if bearer is not None:
                claims = await runtime_for_app(request.app, oidc).verify_jwt(
                    bearer,
                    audience=oidc.audience,
                )
                return _mapped_principal(
                    request,
                    issuer=oidc.issuer,
                    subject=str(claims["sub"]),
                )
            session = request.cookies.get(oidc.session_cookie_name)
            if not session:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="OIDC authentication is required",
                )
            ticket = session_codec_for_app(request.app, oidc).decode(session)
            if ticket.get("issuer") != oidc.issuer:
                raise OidcTokenError("browser session issuer does not exactly match configured issuer")
            subject = ticket.get("sub")
            if not isinstance(subject, str) or not subject:
                raise OidcTokenError("browser session subject is missing")
            return _mapped_principal(request, issuer=oidc.issuer, subject=subject)
        except HTTPException:
            raise
        except OidcTokenError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="OIDC authentication failed",
            ) from exc
        except (OidcConfigurationError, OidcUnavailableError) as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="OIDC authentication service is unavailable",
            ) from exc

    return resolve
