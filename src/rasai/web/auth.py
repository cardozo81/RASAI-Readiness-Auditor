"""Authentication boundary for the optional RASAi API.

The foundation intentionally does not invent a password database or custom token format.
Hosted deployments may use an authenticated reverse proxy/gateway and pass the mapped
RASAi user id through a trusted header. OIDC/JWT adapters can implement the same
principal resolver later without changing authorization/domain code.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Awaitable, Callable

from fastapi import HTTPException, Request, status

from .authz import Principal

AUTH_MODE_ENV = "RASAI_API_AUTH_MODE"
TRUSTED_USER_HEADER_ENV = "RASAI_API_TRUSTED_USER_HEADER"


@dataclass(frozen=True, slots=True)
class ApiAuthSettings:
    mode: str = "deny"
    trusted_user_header: str = "x-rasai-user-id"

    @classmethod
    def from_environment(cls) -> "ApiAuthSettings":
        mode = os.getenv(AUTH_MODE_ENV, "deny").strip().casefold()
        if mode not in {"deny", "trusted-header"}:
            raise ValueError(
                f"unsupported RASAi API auth mode: {mode}; supported: deny, trusted-header"
            )
        header = os.getenv(TRUSTED_USER_HEADER_ENV, "x-rasai-user-id").strip().casefold()
        if not header or any(character.isspace() for character in header):
            raise ValueError("RASAi API trusted user header must be a valid non-empty header name")
        return cls(mode=mode, trusted_user_header=header)


PrincipalResolver = Callable[[Request], Awaitable[Principal]]


def build_principal_resolver(settings: ApiAuthSettings) -> PrincipalResolver:
    async def resolve(request: Request) -> Principal:
        if settings.mode == "deny":
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="RASAi API authentication is not configured",
            )
        raw = request.headers.get(settings.trusted_user_header)
        if raw is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="authenticated user is required")
        user_id = raw.strip()
        if not user_id or len(user_id) > 200 or any(character.isspace() for character in user_id):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid authenticated user identity")
        return Principal(user_id=user_id)

    return resolve
