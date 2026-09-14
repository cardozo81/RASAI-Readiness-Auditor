"""OAuth credential resolution for Google Search Console.

RASAi accepts either a short-lived OAuth access token or a refresh-token credential set.
When the refresh credential set is complete, the access token is obtained in memory from
Google's OAuth token endpoint and is never persisted to audit artifacts, diagnostics or
configuration files.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ACCESS_TOKEN_ENV = "RASAI_GOOGLE_SEARCH_CONSOLE_ACCESS_TOKEN"
CLIENT_ID_ENV = "RASAI_GOOGLE_SEARCH_CONSOLE_CLIENT_ID"
CLIENT_SECRET_ENV = "RASAI_GOOGLE_SEARCH_CONSOLE_CLIENT_SECRET"
REFRESH_TOKEN_ENV = "RASAI_GOOGLE_SEARCH_CONSOLE_REFRESH_TOKEN"
SITE_URL_ENV = "RASAI_GOOGLE_SEARCH_CONSOLE_SITE_URL"
TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"

MODE_ACCESS_TOKEN = "ACCESS_TOKEN"
MODE_REFRESH_TOKEN = "REFRESH_TOKEN"
MODE_MISSING = "MISSING"
MODE_INCOMPLETE = "INCOMPLETE"
MODE_INVALID = "INVALID"

CATEGORY_AUTHENTICATION = "AUTHENTICATION"
CATEGORY_CONFIGURATION = "CONFIGURATION"
CATEGORY_TRANSIENT = "TRANSIENT"
CATEGORY_PROVIDER = "PROVIDER"

Opener = Callable[..., Any]


@dataclass(frozen=True, slots=True)
class GscOAuthState:
    mode: str
    configured: bool
    missing: tuple[str, ...] = ()
    detail: str = ""


class GscOAuthError(RuntimeError):
    def __init__(self, category: str, code: str, message: str, *, http_status: int | None = None) -> None:
        super().__init__(message)
        self.category = category
        self.code = code
        self.http_status = http_status


def _value(env: Mapping[str, str], name: str) -> str:
    return str(env.get(name) or "").strip()


def credential_state(env: Mapping[str, str]) -> GscOAuthState:
    """Describe the configured OAuth mode without contacting Google."""
    access = _value(env, ACCESS_TOKEN_ENV)
    client_id = _value(env, CLIENT_ID_ENV)
    client_secret = _value(env, CLIENT_SECRET_ENV)
    refresh = _value(env, REFRESH_TOKEN_ENV)
    refresh_values = {
        CLIENT_ID_ENV: client_id,
        CLIENT_SECRET_ENV: client_secret,
        REFRESH_TOKEN_ENV: refresh,
    }
    supplied_refresh = tuple(name for name, value in refresh_values.items() if value)
    missing_refresh = tuple(name for name, value in refresh_values.items() if not value)

    if access.startswith("AIza"):
        return GscOAuthState(
            MODE_INVALID,
            False,
            detail=(
                f"{ACCESS_TOKEN_ENV} contém uma Google API Key; Search Console exige OAuth 2.0 Bearer token"
            ),
        )
    if not missing_refresh:
        return GscOAuthState(MODE_REFRESH_TOKEN, True)
    if access:
        # A complete manual access token remains a valid current configuration even
        # when optional refresh-token fields are only partially filled.
        return GscOAuthState(MODE_ACCESS_TOKEN, True)
    if supplied_refresh:
        return GscOAuthState(
            MODE_INCOMPLETE,
            False,
            missing=missing_refresh,
            detail="credenciais OAuth de renovação foram preenchidas parcialmente",
        )
    return GscOAuthState(
        MODE_MISSING,
        False,
        missing=(ACCESS_TOKEN_ENV, CLIENT_ID_ENV, CLIENT_SECRET_ENV, REFRESH_TOKEN_ENV),
        detail="informe um access token OAuth ou o conjunto Client ID + Client Secret + Refresh Token",
    )


def auth_configured(env: Mapping[str, str]) -> bool:
    return credential_state(env).configured


def _read_response(response: Any) -> tuple[int, bytes]:
    status = int(getattr(response, "status", None) or response.getcode())
    body = response.read(65536)
    close = getattr(response, "close", None)
    if callable(close):
        close()
    return status, body


def _provider_error(payload: Any) -> tuple[str, str]:
    if not isinstance(payload, Mapping):
        return "", ""
    code = str(payload.get("error") or "")
    detail = str(payload.get("error_description") or payload.get("error_message") or "")
    return code, detail


def _decode(body: bytes) -> Any:
    if not body:
        return None
    try:
        return json.loads(body.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        return None


def _exchange_refresh_token(
    env: Mapping[str, str],
    *,
    timeout: float,
    opener: Opener,
) -> str:
    body = urlencode(
        {
            "client_id": _value(env, CLIENT_ID_ENV),
            "client_secret": _value(env, CLIENT_SECRET_ENV),
            "refresh_token": _value(env, REFRESH_TOKEN_ENV),
            "grant_type": "refresh_token",
        }
    ).encode("utf-8")
    request = Request(
        TOKEN_ENDPOINT,
        data=body,
        method="POST",
        headers={
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "RASAi/integration",
        },
    )
    try:
        response = opener(request, timeout=timeout)
        status, raw = _read_response(response)
    except HTTPError as exc:
        status = int(exc.code)
        try:
            raw = exc.read(65536)
        except OSError:
            raw = b""
    except (TimeoutError, URLError, OSError) as exc:
        raise GscOAuthError(
            CATEGORY_TRANSIENT,
            "OAUTH_TOKEN_ENDPOINT_UNREACHABLE",
            f"endpoint OAuth indisponível temporariamente ({type(exc).__name__})",
        ) from exc

    payload = _decode(raw)
    error_code, error_detail = _provider_error(payload)
    if status == 200 and isinstance(payload, Mapping):
        token = str(payload.get("access_token") or "").strip()
        if token:
            return token
        raise GscOAuthError(
            CATEGORY_PROVIDER,
            "OAUTH_ACCESS_TOKEN_MISSING",
            "Google respondeu ao refresh, mas não retornou access_token",
            http_status=status,
        )
    if status == 400 and error_code in {"invalid_grant", "invalid_client", "unauthorized_client"}:
        raise GscOAuthError(
            CATEGORY_AUTHENTICATION,
            error_code.upper(),
            "Google recusou as credenciais OAuth de renovação" + (f": {error_detail}" if error_detail else ""),
            http_status=status,
        )
    if status in {401, 403}:
        raise GscOAuthError(
            CATEGORY_AUTHENTICATION,
            error_code.upper() or f"HTTP_{status}",
            "Google recusou as credenciais OAuth de renovação",
            http_status=status,
        )
    if status == 429 or status >= 500:
        raise GscOAuthError(
            CATEGORY_TRANSIENT,
            error_code.upper() or f"HTTP_{status}",
            "endpoint OAuth do Google respondeu com indisponibilidade/quota temporária",
            http_status=status,
        )
    raise GscOAuthError(
        CATEGORY_CONFIGURATION,
        error_code.upper() or f"HTTP_{status}",
        "não foi possível renovar o access token com a configuração OAuth informada",
        http_status=status,
    )


def resolve_access_token(
    env: Mapping[str, str],
    *,
    timeout: float = 15.0,
    opener: Opener = urlopen,
) -> str:
    """Return an OAuth access token, refreshing it in memory when configured."""
    state = credential_state(env)
    if state.mode == MODE_ACCESS_TOKEN:
        return _value(env, ACCESS_TOKEN_ENV)
    if state.mode == MODE_REFRESH_TOKEN:
        return _exchange_refresh_token(env, timeout=timeout, opener=opener)
    code = "GSC_OAUTH_INCOMPLETE" if state.mode == MODE_INCOMPLETE else "GSC_OAUTH_NOT_CONFIGURED"
    if state.mode == MODE_INVALID:
        code = "GSC_ACCESS_TOKEN_WRONG_CREDENTIAL_TYPE"
    raise GscOAuthError(CATEGORY_CONFIGURATION, code, state.detail or "OAuth do Search Console não configurado")


def environment_with_access_token(
    env: Mapping[str, str],
    *,
    timeout: float = 15.0,
    opener: Opener = urlopen,
) -> dict[str, str]:
    """Copy ``env`` and add the effective access token only to the in-memory copy."""
    effective = {str(key): str(value) for key, value in env.items()}
    effective[ACCESS_TOKEN_ENV] = resolve_access_token(env, timeout=timeout, opener=opener)
    return effective
