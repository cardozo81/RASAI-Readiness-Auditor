"""Dependency-free client for the hosted RASAi HTTP control plane.

Credentials are never accepted as command-line arguments or persisted. A bearer token
may be supplied through an environment-variable reference. The trusted-user header is
available only for explicit loopback development.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import os
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

from rasai.secret_safety import redact_text, validate_environment_reference


class RemoteApiError(RuntimeError):
    def __init__(self, status: int | None, detail: str) -> None:
        self.status = status
        super().__init__(redact_text(detail))


@dataclass(frozen=True, slots=True)
class RemoteSettings:
    base_url: str
    token_env: str | None = None
    loopback_user_id: str | None = None
    timeout_seconds: float = 30.0

    @classmethod
    def from_environment(cls, environment: Mapping[str, str] | None = None) -> "RemoteSettings":
        env = dict(os.environ if environment is None else environment)
        base = (env.get("RASAI_REMOTE_BASE_URL") or "").strip().rstrip("/")
        if not base:
            raise ValueError("RASAI_REMOTE_BASE_URL is required for remote mode")
        parsed = urlsplit(base)
        host = (parsed.hostname or "").casefold()
        loopback = host in {"localhost", "127.0.0.1", "::1"}
        if parsed.scheme != "https" and not (parsed.scheme == "http" and loopback):
            raise ValueError("remote RASAi API requires HTTPS; HTTP is allowed only on loopback")
        token_env = (env.get("RASAI_REMOTE_TOKEN_ENV") or "").strip() or None
        if token_env is not None:
            token_env = validate_environment_reference(token_env)
        user_id = (env.get("RASAI_REMOTE_USER_ID") or "").strip() or None
        if user_id and not loopback:
            raise ValueError("RASAI_REMOTE_USER_ID trusted-header development mode is loopback-only")
        timeout = float(env.get("RASAI_REMOTE_TIMEOUT_SECONDS") or "30")
        if timeout <= 0 or timeout > 300:
            raise ValueError("RASAI_REMOTE_TIMEOUT_SECONDS must be >0 and <=300")
        return cls(base_url=base, token_env=token_env, loopback_user_id=user_id, timeout_seconds=timeout)


class RemoteClient:
    def __init__(self, settings: RemoteSettings, *, environment: Mapping[str, str] | None = None) -> None:
        self.settings = settings
        self.environment = dict(os.environ if environment is None else environment)

    def _headers(self, *, json_body: bool = False) -> dict[str, str]:
        headers = {"Accept": "application/json", "User-Agent": "RASAi-Remote-Client/1"}
        if json_body:
            headers["Content-Type"] = "application/json"
        if self.settings.token_env:
            token = (self.environment.get(self.settings.token_env) or "").strip()
            if not token:
                raise RemoteApiError(None, f"remote bearer token environment {self.settings.token_env} is not configured")
            headers["Authorization"] = "Bearer " + token
        elif self.settings.loopback_user_id:
            headers["x-rasai-user-id"] = self.settings.loopback_user_id
        return headers

    def request(
        self,
        method: str,
        path: str,
        *,
        query: Mapping[str, Any] | None = None,
        body: Any | None = None,
    ) -> Any:
        if not path.startswith("/"):
            raise ValueError("remote API path must start with /")
        url = self.settings.base_url + path
        if query:
            pairs: list[tuple[str, str]] = []
            for key, value in query.items():
                if value is None:
                    continue
                if isinstance(value, (list, tuple)):
                    pairs.extend((key, str(item)) for item in value)
                else:
                    pairs.append((key, str(value)))
            if pairs:
                url += "?" + urlencode(pairs)
        data = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
        request = Request(url, data=data, method=method.upper(), headers=self._headers(json_body=body is not None))
        try:
            with urlopen(request, timeout=self.settings.timeout_seconds) as response:  # nosec B310: endpoint is policy-validated
                raw = response.read()
                if not raw:
                    return None
                content_type = response.headers.get("Content-Type", "")
                return json.loads(raw.decode("utf-8")) if "json" in content_type else raw.decode("utf-8")
        except HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            try:
                payload = json.loads(raw)
                detail = str(payload.get("detail") or f"HTTP {exc.code}") if isinstance(payload, dict) else f"HTTP {exc.code}"
            except json.JSONDecodeError:
                detail = f"HTTP {exc.code}"
            raise RemoteApiError(exc.code, detail) from exc
        except URLError as exc:
            raise RemoteApiError(None, f"remote API unavailable: {exc.reason}") from exc

    def get(self, path: str, *, query: Mapping[str, Any] | None = None) -> Any:
        return self.request("GET", path, query=query)

    def post(self, path: str, *, body: Any | None = None) -> Any:
        return self.request("POST", path, body=body)

    def patch(self, path: str, *, body: Any) -> Any:
        return self.request("PATCH", path, body=body)

    def delete(self, path: str) -> Any:
        return self.request("DELETE", path)
