"""#355: reconcile independently captured Settings 2.0 and RUM Classic USQL.

Offline, read-only; no synthetic M25, provider, score, AUD or settings write.
Same application scope is not same browser/device/time population proof.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from rasai.dynatrace_apdex_arch_advisory_355 import VERSION as _SETTINGS_ADVISORY_VERSION

_RUM_CONTRACT = "RASAI-DYNATRACE-RUM-USQL-ACTIONS-001"
_MAX_SETTINGS_BYTES = 1024 * 1024
_MAX_RUM_BYTES = 256 * 1024
_ACTIONS = ("load", "xhr", "custom", "other")


def compare_dynatrace_settings_and_rum(
    settings_advisory: Mapping[str, Any],
    rum_population: Mapping[str, Any],
) -> dict[str, Any]:
    """Never inject USQL extrapolated counts into Apdex config or scores."""
    base = {
        "contract_version": "RASAI-DYNATRACE-RUM-SETTINGS-COMPARISON-355-001",
        "status": "NOT_COMPARABLE", "reason": None,
        # Two JSON exports can claim one app without authenticating each
        # other. This pure reader cannot cryptographically attest a tenant.
        "application_scope_verified_across_sources": False,
        "rasai_same_browser_sample_verified": False,
        "rum_observation_matches_architecture_sample": False,
        "rum_counts_are_raw_population_census": False,
        "dynatrace_rum_vs_synthetic_apdex_distinct": True,
        "recommended_numeric_thresholds": None, "new_apdex_score": None,
        "synthetic_m23_m25_changed": False,
        "provider_requests": 0, "audit_writes": 0,
        "review_findings": [],
        "limitations": (
            "Application ID matching only reconciles declared scope of "
            "two separately supplied JSON documents; local JSON may be forged "
            "and cannot authenticate Dynatrace tenant or account ownership. "
            "It cannot prove identical tenant/URL/browser/device/clock "
            "as the RASAi physical architecture observation, causal "
            "quality, instrumented soft navigation or raw census."
        ),
    }
    def abstain(reason: str) -> dict[str, Any]:
        return {**base, "reason": reason}
    if (not isinstance(settings_advisory, Mapping)
            or not isinstance(rum_population, Mapping)):
        return abstain("INPUT_NOT_OBJECTS")
    if settings_advisory.get("contract_version") != _SETTINGS_ADVISORY_VERSION:
        return abstain("SETTINGS_ADVISORY_VERSION_UNSUPPORTED")
    if rum_population.get("contract_version") != _RUM_CONTRACT:
        return abstain("RUM_USQL_VERSION_UNSUPPORTED")
    if (rum_population.get("source") != "LIVE_RUM_CLASSIC_USQL_AGGREGATE_RESPONSE"
            or rum_population.get("rasai_same_browser_sample_verified") is not False
            or rum_population.get("raw_rum_action_census_verified") is not False):
        return abstain("RUM_USQL_PROVENANCE_NOT_VERIFIED")
    counts = rum_population.get("action_counts")
    if (not isinstance(counts, Mapping) or set(counts) != set(_ACTIONS)
            or any(type(counts[x]) is not int or not 0 <= counts[x] <= 100_000_000
                   for x in _ACTIONS)
            or type(rum_population.get("action_count_total")) is not int
            or rum_population["action_count_total"] != sum(counts.values())):
        return abstain("RUM_ACTION_COUNTS_INVALID")
    extrap = rum_population.get("usql_extrapolation_level")
    extrap_flag = rum_population.get("usql_reported_counts_extrapolated")
    if (extrap is not None and (type(extrap) is not int or not 1 <= extrap <= 1000)
            or extrap_flag is not (None if extrap is None else extrap > 1)):
        return abstain("RUM_EXTRAPOLATION_PROVENANCE_INVALID")
    application_id = rum_population.get("application_id")
    raw_settings = settings_advisory.get("effective_values_export")
    scope = (raw_settings.get("declared_application_scope")
             if isinstance(raw_settings, Mapping) else None)
    actual_settings = (
        settings_advisory.get("settings_provenance")
        == "LIVE_DYNATRACE_SETTINGS_API_EFFECTIVE_VALUES"
        and settings_advisory.get("actual_dynatrace_tenant_consulted") is True
        and settings_advisory.get("input_source")
        == "AUTHENTICATED_LIVE_DYNATRACE_EFFECTIVE_VALUES"
    )
    if (not isinstance(application_id, str) or not application_id.strip()
            or not isinstance(scope, str) or scope != application_id):
        return abstain("APPLICATION_SCOPE_NOT_MATCHED")
    if settings_advisory.get("status") in {
        "INVALID_SETTINGS_SNAPSHOT", "NOT_EVALUABLE",
    }:
        return abstain("SETTINGS_ADVISORY_NOT_ELIGIBLE")
    observed_kpm = settings_advisory.get("observed_kpm")
    if not isinstance(observed_kpm, Mapping):
        return abstain("SETTINGS_KPM_NOT_AVAILABLE")
    architecture = settings_advisory.get("architecture")
    notes = []
    if not actual_settings:
        notes.append("SETTINGS_SCOPE_IS_OPERATOR_DECLARED_NOT_AUTHENTICATED")
    if extrap is None:
        notes.append("RUM_EXTRAPOLATION_LEVEL_UNKNOWN")
    elif extrap > 1:
        notes.append("RUM_COUNTS_EXTRAPOLATED_NOT_RAW_CENSUS")
    if architecture in ("CSR_SPA", "HYDRATED", "MIXED"):
        if counts["xhr"] == 0:
            notes.append("NO_REPORTED_XHR_ACTIONS_DOES_NOT_PROVE_CAPTURE_DISABLED")
        if counts["xhr"] > 0 and "xhr_actions" not in observed_kpm:
            notes.append("XHR_ACTIONS_REPORTED_WITHOUT_MATCHING_KPM_SNAPSHOT")
        if "load_actions" in observed_kpm and counts["load"] > 0:
            notes.append("INITIAL_LOAD_COUNTS_DO_NOT_PROVE_SOFT_ROUTE_READINESS")
    elif architecture == "STATIC_OR_SSR" and counts["load"] > 0:
        notes.append("LOAD_ACTION_COUNTS_DO_NOT_PROVE_SAME_PAGE_SAMPLE")
    else:
        notes.append("ARCHITECTURE_NOT_COMPARABLE_WITH_RUM_ACTION_POPULATION")
    return {
        **base,
        "status": (
            "CLAIMED_LIVE_APPLICATION_ID_MATCH" if actual_settings
            else "DECLARED_APPLICATION_ID_MATCH"
        ),
        "application_scope_verified_across_sources": False,
        "settings_export_claims_live_origin": actual_settings,
        "application_id": application_id,
        "architecture": architecture,
        "declared_dynatrace_device_filter": rum_population.get(
            "declared_dynatrace_device_filter"
        ),
        "target_url": rum_population.get("target_url"),
        "period_start_utc": rum_population.get("period_start_utc"),
        "period_end_utc": rum_population.get("period_end_utc"),
        "action_counts_reported": {k: counts[k] for k in _ACTIONS},
        "usql_extrapolation_level": extrap,
        "action_apdex_kpm": {
            category: value
            for category, value in observed_kpm.items()
            if category in {"load_actions", "xhr_actions", "custom_actions"}
            and isinstance(value, str)
        },
        "review_findings": notes,
    }


def _load(path: Path, max_bytes: int) -> Mapping[str, Any]:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > max_bytes:
        raise ValueError("bounded regular JSON evidence file required")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError):
        raise ValueError("JSON evidence unreadable or invalid") from None
    if not isinstance(value, dict):
        raise ValueError("JSON evidence object required")
    return value


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Offline Dynatrace Settings/RUM coverage comparison (#355)."
    )
    parser.add_argument("--settings-advisory-json", type=Path, required=True)
    parser.add_argument("--rum-population-json", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = compare_dynatrace_settings_and_rum(
            _load(args.settings_advisory_json, _MAX_SETTINGS_BYTES),
            _load(args.rum_population_json, _MAX_RUM_BYTES),
        )
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
