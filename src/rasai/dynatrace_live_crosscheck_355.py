"""#355: two explicit read-only calls against one validated Dynatrace SaaS tenant.

Same tenant + application scope is NOT same browser session, target-page
instrumentation, raw RUM census or synthetic M23/M25 Apdex equivalence.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from typing import Any, Callable, Sequence

from rasai.dynatrace_apdex_arch_advisory import (
    ARCHITECTURES, assess_dynatrace_apdex_architecture,
    explain_dynatrace_apdex_pt_br,
)
from rasai.dynatrace_population_crosscheck_355 import (
    compare_dynatrace_settings_and_rum,
)
from rasai.dynatrace_rum_population import (
    _APPLICATION_ID, _DEVICE, read_live_dynatrace_action_population,
)
from rasai.dynatrace_settings_live_355 import (
    _tenant_endpoint, read_live_dynatrace_apdex_settings,
)
from rasai.geo_observation import _canonical_url

_FLAG = {"observed": True, "not-observed": False, "unknown": None}


def inspect_live_dynatrace_apdex_coverage(
    *, base_url: str, application_id: str, target_url: str,
    dynatrace_device: str, start_timestamp_ms: int, end_timestamp_ms: int,
    architecture: str, architecture_evidence_id: str | None,
    soft_navigation_observed: bool | None,
    async_requests_observed: bool | None,
    settings_api_token: str, usql_api_token: str,
    settings_reader: Callable[..., dict[str, Any]] = read_live_dynatrace_apdex_settings,
    rum_reader: Callable[..., dict[str, Any]] = read_live_dynatrace_action_population,
) -> dict[str, Any]:
    """Validate both requests before either can reach the network.

    Injected readers are only intended for isolated contract tests.
    Never store or echo either token.
    """
    _tenant_endpoint(base_url)
    if not isinstance(application_id, str) or not _APPLICATION_ID.fullmatch(application_id):
        raise ValueError("Dynatrace application scope invalid")
    if (not isinstance(target_url, str)
            or _canonical_url(target_url) != target_url
            or any(char in target_url for char in ('"', "'", "\\"))
            or len(target_url) > 1024):
        raise ValueError("exact target URL invalid")
    if not isinstance(dynatrace_device, str) or not _DEVICE.fullmatch(dynatrace_device):
        raise ValueError("Dynatrace RUM device filter invalid")
    if (type(start_timestamp_ms) is not int or type(end_timestamp_ms) is not int
            or not 1_000_000_000_000 <= start_timestamp_ms < end_timestamp_ms
            or end_timestamp_ms - start_timestamp_ms > 86_400_000
            or end_timestamp_ms > 4_102_444_800_000):
        raise ValueError("Dynatrace UTC time window invalid")
    for token in (settings_api_token, usql_api_token):
        if (not isinstance(token, str) or not token or token != token.strip()
                or "\r" in token or "\n" in token):
            raise ValueError("both separate read-only Dynatrace tokens required")
    # Do not let one all-scopes credential silently satisfy both explicit
    # grants. Distinct credential material is a local policy gate, not proof
    # of Dynatrace permissions (which remain server-side).
    if settings_api_token == usql_api_token:
        raise ValueError("distinct read-only Dynatrace tokens required")
    if (architecture not in ARCHITECTURES
            or any(type(flag) not in (bool, type(None))
                   for flag in (soft_navigation_observed, async_requests_observed))
            or not isinstance(architecture_evidence_id, str)
            or not architecture_evidence_id.strip()):
        raise ValueError("explicit RASAi architecture declaration required")

    # Each underlying reader enforces GET-only, HTTPS SaaS, bounded payload,
    # redirects disabled and the application's respective API scope.
    # The second request is not made if the first fails.
    try:
        settings_result = settings_reader(
            base_url=base_url, application_scope=application_id,
            api_token=settings_api_token,
        )
        rum_result = rum_reader(
            base_url=base_url, application_id=application_id,
            target_url=target_url, dynatrace_device=dynatrace_device,
            start_timestamp_ms=start_timestamp_ms,
            end_timestamp_ms=end_timestamp_ms, api_token=usql_api_token,
        )
    except (ValueError, OSError, TimeoutError) as exc:
        # Do not forward upstream error bodies or any potentially secret URL.
        raise ValueError("Dynatrace same-tenant read-only evidence unavailable") from None

    if (not isinstance(settings_result, dict) or not isinstance(rum_result, dict)
            or settings_result.get("settings_provenance")
            != "LIVE_DYNATRACE_SETTINGS_API_EFFECTIVE_VALUES"
            or settings_result.get("actual_dynatrace_tenant_consulted") is not True
            or settings_result.get("declared_application_scope") != application_id
            or settings_result.get("dynatrace_provider_requests") != 1
            or rum_result.get("application_id") != application_id
            or rum_result.get("target_url") != target_url
            or rum_result.get("declared_dynatrace_device_filter") != dynatrace_device
            or rum_result.get("population_query_scoped_to_exact_url_device_window")
            is not True
            or rum_result.get("rum_action_aggregate_returned") is not True
            or rum_result.get("period_start_utc") != datetime.fromtimestamp(
                start_timestamp_ms / 1000, timezone.utc
            ).isoformat()
            or rum_result.get("period_end_utc") != datetime.fromtimestamp(
                end_timestamp_ms / 1000, timezone.utc
            ).isoformat()
            or rum_result.get("provider_requests") != 1):
        raise ValueError("Dynatrace responses do not attest requested bounded scope")

    advice = assess_dynatrace_apdex_architecture(
        architecture=architecture,
        architecture_evidence_id=architecture_evidence_id,
        soft_navigation_observed=soft_navigation_observed,
        async_requests_observed=async_requests_observed,
        settings=settings_result.get("settings"),
    )
    advice["settings_provenance"] = settings_result["settings_provenance"]
    advice["actual_dynatrace_tenant_consulted"] = True
    advice["input_source"] = "AUTHENTICATED_LIVE_DYNATRACE_EFFECTIVE_VALUES"
    advice["effective_values_export"] = {
        key: value for key, value in settings_result.items() if key != "settings"
    }
    comparison = compare_dynatrace_settings_and_rum(advice, rum_result)
    if comparison["status"] != "CLAIMED_LIVE_APPLICATION_ID_MATCH":
        raise ValueError("Dynatrace joint RUM/configuration scope not comparable")
    # Unlike two downloaded JSON files, this adapter invokes both authenticated
    # readers under the SAME validated hostname/application in one operation.
    # This is transport-scoped evidence only, NOT an RUM/M6 session match.
    comparison["status"] = "SAME_LIVE_TENANT_APPLICATION_SCOPE_ONLY"
    comparison["application_scope_verified_across_sources"] = True
    comparison["authenticated_same_live_tenant_and_application_request"] = True
    comparison["rasai_same_browser_sample_verified"] = False
    comparison["rum_observation_matches_architecture_sample"] = False
    comparison["provider_requests"] = 2
    comparison["review_findings"].append(
        "SAME_TENANT_APP_REQUESTS_DO_NOT_PROVE_SAME_RASAI_BROWSER_SESSION"
    )
    return {
        "contract_version": "RASAI-DYNATRACE-LIVE-CROSSCHECK-355-001",
        "status": comparison["status"],
        "application_id": application_id,
        "architecture_declared_by_operator": architecture,
        "architecture_evidence_id_declared_by_operator": architecture_evidence_id,
        "settings_advisory": {
            "status": advice["status"],
            "reasons": advice["reasons"],
            "observed_kpm": advice["observed_kpm"],
            "guidance_pt_br": explain_dynatrace_apdex_pt_br(advice),
        },
        "comparison": comparison,
        "rum_population": {
            "action_counts": rum_result["action_counts"],
            "usql_extrapolation_level": rum_result["usql_extrapolation_level"],
            "usql_reported_counts_extrapolated": rum_result[
                "usql_reported_counts_extrapolated"
            ],
            "period_start_utc": rum_result["period_start_utc"],
            "period_end_utc": rum_result["period_end_utc"],
        },
        "actual_authenticated_dynatrace_get_requests": 2,
        "provider_requests": 2,
        "audit_writes": 0,
        "synthetic_m23_m25_changed": False,
        "rasai_same_browser_sample_verified": False,
        "new_apdex_score": None,
        "recommended_numeric_thresholds": None,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Read two Dynatrace APIs in one explicit tenant/app scope (#355)."
    )
    parser.add_argument("--live-base-url", required=True)
    parser.add_argument("--application-id", required=True)
    parser.add_argument("--target-url", required=True)
    parser.add_argument("--dynatrace-device", required=True)
    parser.add_argument("--start-timestamp-ms", type=int, required=True)
    parser.add_argument("--end-timestamp-ms", type=int, required=True)
    parser.add_argument("--architecture", choices=sorted(ARCHITECTURES), required=True)
    parser.add_argument("--architecture-evidence-id", required=True)
    parser.add_argument("--soft-navigation", choices=tuple(_FLAG), default="unknown")
    parser.add_argument("--async-requests", choices=tuple(_FLAG), default="unknown")
    parser.add_argument("--allow-live-settings-read", action="store_true")
    parser.add_argument("--allow-live-usql-read", action="store_true")
    args = parser.parse_args(argv)
    if not args.allow_live_settings_read or not args.allow_live_usql_read:
        parser.error("both explicit read-only Dynatrace API authorizations required")
    try:
        result = inspect_live_dynatrace_apdex_coverage(
            base_url=args.live_base_url,
            application_id=args.application_id, target_url=args.target_url,
            dynatrace_device=args.dynatrace_device,
            start_timestamp_ms=args.start_timestamp_ms,
            end_timestamp_ms=args.end_timestamp_ms,
            architecture=args.architecture,
            architecture_evidence_id=args.architecture_evidence_id,
            soft_navigation_observed=_FLAG[args.soft_navigation],
            async_requests_observed=_FLAG[args.async_requests],
            settings_api_token=os.environ.get("DYNATRACE_API_TOKEN"),
            usql_api_token=os.environ.get("DYNATRACE_USQL_API_TOKEN"),
        )
    except ValueError:
        parser.error("Dynatrace authenticated crosscheck unavailable or invalid")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
