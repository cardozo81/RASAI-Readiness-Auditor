"""#355: reconcile independently captured Settings 2.0 and RUM Classic USQL.

Offline, read-only; no synthetic M25, provider, score, AUD or settings write.
Same application scope is not same browser/device/time population proof.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from rasai.dynatrace_apdex_arch_advisory_355 import (
    KPM_BY_ACTION, VERSION as _SETTINGS_ADVISORY_VERSION,
)
from rasai.dynatrace_rum_population_355 import _APPLICATION_ID, _DEVICE
from rasai.geo_observation import _canonical_url

_RUM_CONTRACT = "RASAI-DYNATRACE-RUM-USQL-ACTIONS-001"
_MAX_SETTINGS_BYTES = 1024 * 1024
_MAX_RUM_BYTES = 256 * 1024
_ACTIONS = ("load", "xhr", "custom", "other")


def _utc_clock(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None or dt.utcoffset() is None:
            return None
        # JSON fields explicitly promise UTC, not an arbitrary offset.
        if dt.utcoffset().total_seconds() != 0:
            return None
        return dt.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError):
        return None


def compare_dynatrace_settings_and_rum(
    settings_advisory: Mapping[str, Any],
    rum_population: Mapping[str, Any],
) -> dict[str, Any]:
    """Never inject USQL extrapolated counts into Apdex config or scores."""
    base = {
        "contract_version": "RASAI-DYNATRACE-RUM-SETTINGS-COMPARISON-355-002",
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
    # This offline comparison does not attest the tenant; however it must
    # at least refuse internally inconsistent JSON claims about an exact
    # URL/device/time-scoped aggregation. Previously even missing periods and
    # flags could be promoted to a declared matching application scope.
    target = rum_population.get("target_url")
    device = rum_population.get("declared_dynatrace_device_filter")
    started = _utc_clock(rum_population.get("period_start_utc"))
    finished = _utc_clock(rum_population.get("period_end_utc"))
    if (
        rum_population.get("population_query_scoped_to_exact_url_device_window") is not True
        or rum_population.get("rum_action_aggregate_returned") is not True
        or not isinstance(target, str) or len(target) > 1024
        or not target or _canonical_url(target) != target
        or not isinstance(device, str) or not _DEVICE.fullmatch(device)
        or started is None or finished is None
        or not 0 < (finished - started).total_seconds() <= 86400
    ):
        return abstain("RUM_EXACT_POPULATION_SCOPE_UNVERIFIABLE")
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
    if (not isinstance(application_id, str)
            or not _APPLICATION_ID.fullmatch(application_id)
            or not isinstance(scope, str) or scope != application_id):
        return abstain("APPLICATION_SCOPE_NOT_MATCHED")
    if settings_advisory.get("status") in {
        "INVALID_SETTINGS_SNAPSHOT", "NOT_EVALUABLE",
    }:
        return abstain("SETTINGS_ADVISORY_NOT_ELIGIBLE")
    observed_kpm = settings_advisory.get("observed_kpm")
    if not isinstance(observed_kpm, Mapping) or not observed_kpm:
        return abstain("SETTINGS_KPM_NOT_AVAILABLE")
    # Offline projections can be edited independently of authenticated
    # Settings evidence. Only action-specific documented KPM enums qualify.
    if any(
        not isinstance(category, str)
        or category not in KPM_BY_ACTION
        or not isinstance(kpm, str)
        or kpm not in KPM_BY_ACTION[category]
        for category, kpm in observed_kpm.items()
    ):
        return abstain("SETTINGS_KPM_PROJECTION_UNVERIFIABLE")
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


def _unique_evidence_json_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """A local export with duplicated scope/count fields is not evidence."""
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate evidence JSON field")
        result[key] = value
    return result


def _reject_nonstandard_json_constant(value: str) -> None:
    raise ValueError("nonstandard evidence JSON number")


def _load(path: Path, max_bytes: int) -> Mapping[str, Any]:
    """Read exactly one bounded local UTF-8 file, never a changed subset."""
    if path.is_symlink() or not path.is_file():
        raise ValueError("bounded regular JSON evidence file required")
    initial_size = path.stat().st_size
    if initial_size > max_bytes:
        raise ValueError("bounded regular JSON evidence file required")
    try:
        with path.open("rb") as handle:
            raw = handle.read(max_bytes + 1)
        if len(raw) != initial_size or path.stat().st_size != initial_size:
            raise ValueError("evidence size changed during physical read")
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_unique_evidence_json_pairs,
            parse_constant=_reject_nonstandard_json_constant,
        )
    except (OSError, UnicodeError, ValueError, TypeError):
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
    parser.add_argument(
        "--format", choices=("json", "html"), default="json",
        help="HTML is an offline advisory only, not an Apdex score.",
    )
    args = parser.parse_args(argv)
    try:
        result = compare_dynatrace_settings_and_rum(
            _load(args.settings_advisory_json, _MAX_SETTINGS_BYTES),
            _load(args.rum_population_json, _MAX_RUM_BYTES),
        )
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    if args.format == "html":
        from rasai.dynatrace_population_crosscheck_html_355 import (
            render_dynatrace_population_crosscheck_html,
        )
        print(render_dynatrace_population_crosscheck_html(result))
    else:
        print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
