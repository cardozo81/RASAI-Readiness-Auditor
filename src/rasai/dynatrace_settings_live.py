"""#355: explicit, bounded, read-only Dynatrace Settings API effectiveValues.

The adapter inspects CONFIGURATION, never RUM events or the RASAi M25 engine.
No request is made without an explicit calling action and an API token.
"""
from __future__ import annotations

from contextlib import closing
import json
import math
import re
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request

from rasai.geo_competitor_pinned_egress import PublicWebPinnedOpener

from rasai.dynatrace_effective_values_adapter import (
    SCHEMA_TO_ACTION, extract_apdex_from_effective_values,
)


def _unique_settings_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """Reject duplicate keys anywhere in authenticated Settings API JSON."""
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("ambiguous duplicate Settings API JSON key")
        result[key] = value
    return result


def _reject_non_json_number(token: str) -> None:
    """Python's permissive JSON decoder otherwise accepts NaN/Infinity."""
    raise ValueError("non-JSON numeric constant in Settings API response")

_MAX_BODY = 1024 * 1024
_TENANT = re.compile(r"^[a-z0-9-]{1,80}\.live\.dynatrace\.com$", re.ASCII)


def _tenant_endpoint(base_url: str) -> str:
    # urlsplit strips embedded TAB/CR/LF in supported Python versions.
    # Deny ambiguous operator-provided URLs before any normalization or
    # authenticated request; an exact tenant URL is part of the trust gate.
    if (
        not isinstance(base_url, str) or base_url != base_url.strip()
        or any(ord(char) < 32 or ord(char) == 127 for char in base_url)
        or chr(92) in base_url
    ):
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


_READ_ENDPOINT_PATHS = frozenset({
    "/api/v2/settings/effectiveValues",
    "/api/v1/userSessionQueryLanguage/table",
})


class DynatracePinnedOpener:
    """SaaS-only GET adapter: public numeric TCP IP + original TLS identity.

    Delegates the network boundary to the already-tested COBS pinned
    transport. It never uses ambient HTTP proxies or follows redirects.
    A caller-supplied opener remains supported for offline tests only.
    """

    def __init__(self, resolver=None) -> None:
        self._transport = PublicWebPinnedOpener(resolver)

    def open(self, request: Request, timeout: float = 10.0):
        # Deny a future caller from sending an Api-Token header to an
        # arbitrary hostname/path, even before consulting DNS.
        try:
            parsed = urlsplit(request.full_url)
            _tenant_endpoint(f"{parsed.scheme}://{parsed.netloc}")
            if (
                request.get_method() != "GET"
                or parsed.path not in _READ_ENDPOINT_PATHS
                or not parsed.query
                or parsed.fragment
            ):
                raise ValueError("Dynatrace GET endpoint outside approved scope")
        except (TypeError, AttributeError, ValueError):
            raise ValueError("Dynatrace GET endpoint outside approved scope") from None
        return closing(self._transport(request, timeout=timeout))


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
        or any(ord(char) < 32 or ord(char) == 127 for char in api_token)
    ):
        raise ValueError("Dynatrace settings.read API token not configured")
    if (type(timeout_seconds) not in (int, float)
            or not math.isfinite(timeout_seconds)
            or not 0 < timeout_seconds <= 30):
        raise ValueError("Dynatrace request timeout outside allowed bounds")
    # Validate application scope before any request; this pure adapter has
    # no side effects and performs the same guard as the offline parser.
    from rasai.dynatrace_effective_values_adapter import (
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
    client = opener if opener is not None else DynatracePinnedOpener()
    try:
        with client.open(request, timeout=timeout_seconds) as response:
            if response.getcode() != 200:
                raise ValueError("Dynatrace Settings API did not return HTTP 200")
            # A successful JSON-shaped body is not proof that Settings 2.0
            # returned its documented JSON media type. Keep the same strict
            # boundary as the opt-in USQL aggregate reader.
            media = str(response.headers.get("Content-Type", "")).split(
                ";", 1
            )[0].strip().casefold()
            if media != "application/json":
                raise ValueError("Dynatrace Settings API response is not JSON")
            # A fully parseable JSON prefix of a truncated HTTP response is
            # not authoritative tenant configuration. If the server supplies
            # Content-Length, require exact bounded entity-body bytes.
            # Reject malformed/ambiguous lengths *before* allocating a body.
            expected_raw = response.headers.get("Content-Length")
            expected = None
            if expected_raw is not None:
                if (
                    not isinstance(expected_raw, str)
                    or not expected_raw.isascii()
                    or not expected_raw.isdecimal()
                    or len(expected_raw) > 12
                ):
                    raise ValueError("Dynatrace Settings API content length invalid")
                expected = int(expected_raw)
                if expected > _MAX_BODY:
                    raise ValueError("Dynatrace settings response exceeds bounded size")
            raw = response.read(_MAX_BODY + 1)
            if expected is not None and len(raw) != expected:
                raise ValueError("Dynatrace Settings API response length mismatch")
    except (HTTPError, URLError, OSError, TimeoutError) as exc:
        # Never leak request headers, tenant URL, token or remote error body.
        raise ValueError("Dynatrace Settings API unavailable or refused read-only request") from None
    if len(raw) > _MAX_BODY:
        raise ValueError("Dynatrace settings response exceeds bounded size")
    try:
        decoded = json.loads(
            raw, object_pairs_hook=_unique_settings_json_object,
            parse_constant=_reject_non_json_number,
        )
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
