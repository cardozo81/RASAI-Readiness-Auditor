"""#355: opt-in Dynatrace RUM Classic USQL aggregate action population.

Strictly separate from Settings 2.0 configuration and RASAi synthetic M25.
This reads *aggregate useraction counts* only, never individual sessions,
browser events, cookies, user IDs, IPs or personal fields.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
import re
from typing import Any, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request

from rasai.dynatrace_settings_live_355 import DynatracePinnedOpener, _tenant_endpoint
from rasai.geo_observation import _canonical_url

_APPLICATION_ID = re.compile(r"^APPLICATION-[A-F0-9]{16}$")
_DEVICE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{1,30}$")
_BODY_LIMIT = 256 * 1024
_MAX_ROWS = 20


def read_live_dynatrace_action_population(
    *, base_url: str, application_id: str, target_url: str,
    dynatrace_device: str, start_timestamp_ms: int, end_timestamp_ms: int,
    api_token: str, opener: Any | None = None,
    timeout_seconds: float = 10.0,
) -> dict[str, Any]:
    """One bounded GET to RUM Classic USQL, with explicit UTC period and scope.

    A successful response proves only the reported aggregation for the
    requested filters. It does not prove RASAi same-sample equivalence or
    that XHR/fetch instrumentation is enabled/disabled.
    """
    env = _tenant_endpoint(base_url).removesuffix(
        "/api/v2/settings/effectiveValues"
    )
    if not isinstance(application_id, str) or not _APPLICATION_ID.fullmatch(application_id):
        raise ValueError("Dynatrace application entity ID is invalid")
    if not isinstance(target_url, str) or (
        _canonical_url(target_url) != target_url
        or any(char in target_url for char in ('"', "'", "\\"))
        or len(target_url) > 1024
    ):
        raise ValueError("unambiguous exact target URL is required")
    if not isinstance(dynatrace_device, str) or not _DEVICE.fullmatch(dynatrace_device):
        raise ValueError("exact Dynatrace device value is required")
    if (
        type(start_timestamp_ms) is not int or type(end_timestamp_ms) is not int
        or not 1_000_000_000_000 <= start_timestamp_ms < end_timestamp_ms
        or end_timestamp_ms - start_timestamp_ms > 24 * 60 * 60 * 1000
        or end_timestamp_ms > 4_102_444_800_000
    ):
        raise ValueError("explicit bounded UTC start/end milliseconds are required")
    if (not isinstance(api_token, str) or not api_token
            or api_token != api_token.strip()
            or any(c in api_token for c in "\r\n")):
        raise ValueError("Dynatrace DTAQLAccess token not configured")
    if type(timeout_seconds) not in (int, float) or not 0 < timeout_seconds <= 10:
        raise ValueError("Dynatrace USQL timeout outside permitted bounds")

    # Exact-query matching, never wildcard LIKE. No raw useraction rows:
    # only aggregate counts by type, scoped to one application, URL, device
    # and explicit time window. Restrictive validators prevent USQL injection.
    query = (
        "SELECT type, COUNT(*) FROM useraction "
        f'WHERE useraction.internalApplicationId = "{application_id}" '
        f'AND useraction.targetUrl = "{target_url}" '
        f'AND usersession.device = "{dynatrace_device}" '
        "GROUP BY type"
    )
    params = urlencode({
        "query": query,
        "startTimestamp": start_timestamp_ms,
        "endTimestamp": end_timestamp_ms,
    })
    request = Request(
        env + "/api/v1/userSessionQueryLanguage/table?" + params,
        headers={
            "Authorization": "Api-Token " + api_token,
            "Accept": "application/json",
            "User-Agent": "RASAI-Dynatrace-USQL-Aggregates-Only/1.0",
        },
        method="GET",
    )
    client = opener if opener is not None else DynatracePinnedOpener()
    try:
        with client.open(request, timeout=timeout_seconds) as response:
            if response.getcode() != 200:
                raise ValueError("Dynatrace USQL query did not return HTTP 200")
            if "application/json" not in str(response.headers.get("Content-Type", "")).lower():
                raise ValueError("Dynatrace USQL response is not JSON")
            raw = response.read(_BODY_LIMIT + 1)
    except (HTTPError, URLError, OSError, TimeoutError):
        # Never expose tenant URL, remote response, query, header or token.
        raise ValueError("Dynatrace USQL aggregate request unavailable or refused") from None
    if len(raw) > _BODY_LIMIT:
        raise ValueError("Dynatrace USQL aggregate response exceeds size limit")
    try:
        payload = json.loads(raw)
    except (UnicodeError, ValueError, TypeError):
        raise ValueError("Dynatrace USQL response JSON invalid") from None
    if not isinstance(payload, dict):
        raise ValueError("Dynatrace USQL aggregate object required")
    # Dynatrace may return extrapolated aggregate counts rather than a
    # literal census of user actions. Null/absent extrapolationLevel is NOT
    # evidence of a raw count. Retain the estimated numbers but label their
    # epistemic status; reject malformed declarations.
    raw_extrapolation = payload.get("extrapolationLevel")
    if raw_extrapolation is not None and (
        type(raw_extrapolation) is not int
        or not 1 <= raw_extrapolation <= 1000
    ):
        raise ValueError("Dynatrace USQL extrapolation level invalid")
    columns = payload.get("columnNames")
    values = payload.get("values")
    if (
        not isinstance(columns, list) or len(columns) != 2
        or not all(isinstance(x, str) for x in columns)
        or [x.strip().casefold() for x in columns] != ["type", "count(*)"]
        or not isinstance(values, list) or len(values) > _MAX_ROWS
    ):
        raise ValueError("Dynatrace USQL aggregate schema/count is invalid")
    seen: set[str] = set()
    counts = {"load": 0, "xhr": 0, "custom": 0, "other": 0}
    for row in values:
        if not isinstance(row, list) or len(row) != 2 or not isinstance(row[0], str):
            raise ValueError("Dynatrace USQL action count row is invalid")
        # USQL label formatting cannot define a second physical action
        # population: "Load" and " load " are the same logical type.
        # Normalize *before* duplicate detection and categorization.
        action = row[0].strip().casefold()
        if (
            not action or len(action) > 80
            or action in seen
            or type(row[1]) is not int or not 0 <= row[1] <= 100_000_000
        ):
            raise ValueError("Dynatrace USQL action count row is invalid")
        seen.add(action)
        counts[action if action in counts and action != "other" else "other"] += row[1]
    return {
        "contract_version": "RASAI-DYNATRACE-RUM-USQL-ACTIONS-001",
        "source": "LIVE_RUM_CLASSIC_USQL_AGGREGATE_RESPONSE",
        "application_id": application_id,
        "target_url": target_url,
        "declared_dynatrace_device_filter": dynatrace_device,
        "period_start_utc": datetime.fromtimestamp(
            start_timestamp_ms / 1000, timezone.utc
        ).isoformat(),
        "period_end_utc": datetime.fromtimestamp(
            end_timestamp_ms / 1000, timezone.utc
        ).isoformat(),
        "action_counts": counts,
        "action_count_total": sum(counts.values()),
        "usql_extrapolation_level": raw_extrapolation,
        "usql_reported_counts_extrapolated": (
            raw_extrapolation > 1 if raw_extrapolation is not None else None
        ),
        "raw_rum_action_census_verified": False,
        "population_query_scoped_to_exact_url_device_window": True,
        "rum_action_aggregate_returned": True,
        "rasai_same_browser_sample_verified": False,
        "rasai_synthetic_apdex_unchanged": True,
        "m23_m25_changed": False,
        "audit_writes": 0,
        "provider_requests": 1,
        "limitations": (
            "Agregação USQL da população RUM Classic do filtro informado, "
            "não log de usuário nem evidência de ação na mesma sessão Playwright. "
            "Zero XHR no resultado não prova que captura XHR/Fetch esteja desabilitada. "
            "A API USQL pode extrapolar contagens de uma amostra; "
            "extrapolationLevel ausente não comprova contagem bruta física. "
            "Sampling, retenção e permissões do tenant podem reduzir a cobertura. "
            "Settings API e USQL usam tokens/permissões distintas; não extrapolar "
            "thresholds ou atribuir causa de Apdex por arquitetura."
        ),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Opt-in Dynatrace RUM Classic USQL action type counts (#355)."
    )
    parser.add_argument("--live-base-url", required=True)
    parser.add_argument("--application-id", required=True)
    parser.add_argument("--target-url", required=True)
    parser.add_argument("--dynatrace-device", required=True)
    parser.add_argument("--start-timestamp-ms", type=int, required=True)
    parser.add_argument("--end-timestamp-ms", type=int, required=True)
    parser.add_argument("--allow-live-usql-read", action="store_true")
    args = parser.parse_args(argv)
    if not args.allow_live_usql_read:
        parser.error("explicit --allow-live-usql-read is required")
    try:
        result = read_live_dynatrace_action_population(
            base_url=args.live_base_url,
            application_id=args.application_id,
            target_url=args.target_url,
            dynatrace_device=args.dynatrace_device,
            start_timestamp_ms=args.start_timestamp_ms,
            end_timestamp_ms=args.end_timestamp_ms,
            api_token=os.environ.get("DYNATRACE_USQL_API_TOKEN"),
        )
    except ValueError:
        parser.error("Dynatrace RUM USQL query unavailable or invalid")
    print(json.dumps(result, sort_keys=True, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
