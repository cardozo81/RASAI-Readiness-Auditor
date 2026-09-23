"""OIDC browser login/session routes for the RASAi Web pilot."""
from __future__ import annotations

import secrets
from typing import Any

from fastapi import HTTPException, Request, status
from fastapi.responses import JSONResponse, RedirectResponse

from rasai.platform.identity_directory import IdentityDirectory

from .auth import ApiAuthSettings
from .oidc import (
    OidcConfigurationError,
    OidcTokenError,
    OidcUnavailableError,
    pkce_pair,
    runtime_for_app,
    session_codec_for_app,
)


def _no_store(response: Any) -> Any:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


def _identity_user_id(request: Request, *, issuer: str, subject: str) -> str | None:
    store = request.app.state.store_factory()
    try:
        return IdentityDirectory(store).resolve_user_id(issuer=issuer, subject=subject)
    finally:
        store.close()


def install_identity_routes(app: Any, auth: ApiAuthSettings) -> None:
    """Install public auth metadata and OIDC login routes when configured."""

    @app.get("/auth/config", include_in_schema=False)
    def auth_config() -> JSONResponse:
        return _no_store(
            JSONResponse(
                {
                    "mode": auth.mode,
                    "browser_login": auth.mode == "oidc",
                    "trusted_header": auth.mode == "trusted-header",
                }
            )
        )

    if auth.mode != "oidc" or auth.oidc is None:
        return

    oidc = auth.oidc

    @app.middleware("http")
    async def oidc_session_csrf_guard(request: Request, call_next: Any):
        unsafe = request.method.upper() not in {"GET", "HEAD", "OPTIONS", "TRACE"}
        has_session = bool(request.cookies.get(oidc.session_cookie_name))
        has_bearer = request.headers.get("authorization", "").casefold().startswith("bearer ")
        if unsafe and has_session and not has_bearer:
            origin = request.headers.get("origin")
            if origin != oidc.public_origin:
                return JSONResponse(
                    status_code=status.HTTP_403_FORBIDDEN,
                    content={"detail": "browser session origin validation failed"},
                    headers={"Cache-Control": "no-store"},
                )
        return await call_next(request)

    @app.get("/auth/login", include_in_schema=False)
    async def login(request: Request) -> RedirectResponse:
        try:
            runtime = runtime_for_app(request.app, oidc)
            codec = session_codec_for_app(request.app, oidc)
            state = secrets.token_urlsafe(32)
            nonce = secrets.token_urlsafe(32)
            verifier, challenge = pkce_pair()
            transaction = codec.encode(
                {"state": state, "nonce": nonce, "verifier": verifier},
                ttl_seconds=600,
            )
            target = await runtime.authorization_url(
                state=state,
                nonce=nonce,
                code_challenge=challenge,
            )
        except (OidcConfigurationError, OidcUnavailableError) as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="OIDC login service is unavailable",
            ) from exc
        response = RedirectResponse(target, status_code=status.HTTP_302_FOUND)
        response.set_cookie(
            oidc.transaction_cookie_name,
            transaction,
            max_age=600,
            httponly=True,
            secure=oidc.cookie_secure,
            samesite="lax",
            path="/auth",
        )
        return _no_store(response)

    @app.get("/auth/callback", include_in_schema=False)
    async def callback(
        request: Request,
        code: str | None = None,
        state: str | None = None,
        error: str | None = None,
    ) -> RedirectResponse:
        if error:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="OIDC provider rejected authentication")
        transaction_cookie = request.cookies.get(oidc.transaction_cookie_name)
        if not transaction_cookie or not code or not state:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="OIDC callback is incomplete")
        try:
            codec = session_codec_for_app(request.app, oidc)
            transaction = codec.decode(transaction_cookie)
            expected_state = transaction.get("state")
            nonce = transaction.get("nonce")
            verifier = transaction.get("verifier")
            if not isinstance(expected_state, str) or not secrets.compare_digest(expected_state, state):
                raise OidcTokenError("OIDC state validation failed")
            if not isinstance(nonce, str) or not isinstance(verifier, str):
                raise OidcTokenError("OIDC transaction is invalid")
            runtime = runtime_for_app(request.app, oidc)
            token_response = await runtime.exchange_code(code=code, code_verifier=verifier)
            claims = await runtime.verify_jwt(
                str(token_response["id_token"]),
                audience=oidc.client_id,
                nonce=nonce,
            )
            subject = str(claims["sub"])
            user_id = _identity_user_id(request, issuer=oidc.issuer, subject=subject)
            if user_id is None:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="authenticated identity is not provisioned in RASAi",
                )
            session = codec.encode(
                {"issuer": oidc.issuer, "sub": subject},
                ttl_seconds=oidc.session_ttl_seconds,
            )
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
                detail="OIDC login service is unavailable",
            ) from exc
        response = RedirectResponse("/app", status_code=status.HTTP_303_SEE_OTHER)
        response.delete_cookie(oidc.transaction_cookie_name, path="/auth")
        response.set_cookie(
            oidc.session_cookie_name,
            session,
            max_age=oidc.session_ttl_seconds,
            httponly=True,
            secure=oidc.cookie_secure,
            samesite="lax",
            path="/",
        )
        return _no_store(response)

    @app.post("/auth/logout", include_in_schema=False)
    def logout() -> RedirectResponse:
        response = RedirectResponse("/app", status_code=status.HTTP_303_SEE_OTHER)
        response.delete_cookie(oidc.session_cookie_name, path="/")
        response.delete_cookie(oidc.transaction_cookie_name, path="/auth")
        return _no_store(response)
