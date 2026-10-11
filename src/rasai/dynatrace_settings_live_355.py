"""#355: explicit, bounded, read-only Dynatrace Settings API effectiveValues.

The adapter inspects CONFIGURATION, never RUM events or the RASAi M25 engine.
No request is made without an explicit calling action and an API token.
"""
from __future__ import annotations

import json
import re
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from rasai.dynatrace_effective_values_adapter_355 import (
    SCHEMA_TO_ACTION, extract_apdex_from_effective_values,
)

_MAX_BODY = 1024 * 1024
_TENANT = re.compile(r"^[a-z0-9-]{1,80}\.live\.dynatrace\.com$", re.ASCII)


class _DenyRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _tenant_endpoint(base_url: str) -> str:
    if not isinstance(base_url, str) or base_url != base_url.strip():
        raise ValueError("Dynatrace environment URL is invalid")
    try:
        parsed = urlsplit(base_url)
        if (
            parsed.scheme != "https" or parsed.username is not None
            or parsed.password is not None or parsed.port is not None
            or not isinstance(parsed.hostname, str)
            or not _TENANT.fullmatch(parsed.hostname)
            or parsed.path not in ("", "/")
            or parsed.query or parsed.fragment or parsed.netloc != parsed.hostname
        ):
            raise ValueError("Dynatrace environment must be a supported HTTPS SaaS tenant")
    except ValueError as exc:
        raise ValueError("Dynatrace environment must be a supported HTTPS SaaS tenant") from None
    return "https://" + parsed.hostname + "/api/v2/settings/effectiveValues"


def read_live_dynatrace_apdex_settings(
    *, base_url: str, application_scope: str, api_token: str,
    opener: Any | None = None, timeout_seconds: float = 10.0,
) -> dict[str, Any]:
    """Get exactly one bounded effectiveValues page, then validate RUM schemas.

    The Settings 2.0 endpoint is read-only and evaluates inherited/default
    values. Pagination is denied rather than report incomplete settings.
    Network transport is injectable to run all CI tests without HTTP.
    """
    endpoint = _tenant_endpoint(base_url)
    if (
        not isinstance(api_token, str) or not api_token or api_token != api_token.strip()
        or "\n" in api_token or "\r" in api_token
    ):
        raise ValueError("Dynatrace settings.read API token not configured")
    if timeout_seconds <= 0 or timeout_seconds > 30:
        raise ValueError("Dynatrace request timeout outside allowed bounds")
    # Validate application scope before any request; this pure adapter has
    # no side effects and performs the same guard as the offline parser.
    from rasai.dynatrace_effective_values_adapter_355 import (
        extract_apdex_from_effective_values as parse,
    )
    parse({"items": [], "totalCount": 0}, declared_application_scope=application_scope)
    params = urlencode({
        "schemaIds": ",".join(SCHEMA_TO_ACTION),
        "scope": application_scope,
        "fields": "schemaId,schemaVersion,origin,value",
        "pageSize": "100",
    })
    request = Request(
        endpoint + "?" + params,
        headers={
            "Authorization": "Api-Token " + api_token,
            "Accept": "application/json",
            "User-Agent": "RASAI-Dynatrace-ReadOnly/1.0",
        },
        method="GET",
    )
    client = opener or build_opener(_DenyRedirect())
    try:
        with client.open(request, timeout=timeout_seconds) as response:
            if response.getcode() != 200:
                raise ValueError("Dynatrace Settings API did not return HTTP 200")
            raw = response.read(_MAX_BODY + 1)
    except (HTTPError, URLError, OSError, TimeoutError) as exc:
        # Never leak request headers, tenant URL, token or remote error body.
        raise ValueError("Dynatrace Settings API unavailable or refused read-only request") from None
    if len(raw) > _MAX_BODY:
        raise ValueError("Dynatrace settings response exceeds bounded size")
    try:
        decoded = json.loads(raw)
    except (UnicodeError, ValueError, TypeError):
        raise ValueError("Dynatrace Settings API response is not valid JSON") from None
    if not isinstance(decoded, dict):
        raise ValueError("Dynatrace Settings API did not return an object")
    result = extract_apdex_from_effective_values(
        decoded, declared_application_scope=application_scope
    )
    # The scope is authenticated at the Settings API endpoint; this does
    # not prove RUM collection or a RASAi URL/device/time match.
    result["settings_provenance"] = "LIVE_DYNATRACE_SETTINGS_API_EFFECTIVE_VALUES"
    result["scope_provenance"] = "AUTHENTICATED_SETTINGS_API_SCOPE_NOT_RUM_EVENTS"
    result["actual_dynatrace_tenant_consulted"] = True
    result["rum_action_population_verified"] = False
    result["rasai_same_page_device_time_verified"] = False
    result["dynatrace_provider_requests"] = 1
    return result
