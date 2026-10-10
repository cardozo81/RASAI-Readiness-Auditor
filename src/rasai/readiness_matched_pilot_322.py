"""#322: offline A/B readiness probe budget analysis, never an M25 gateway.

Analyze *declared* matched browser pilot pairs without reaching the network,
opening a browser, or modifying an AUD. A statistical comparison cannot
attest that production M25 sample_id, context_id and clock were reused.
Every outcome is PILOT ONLY; no threshold or Apdex score is changed.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

VERSION = "RASAI-READINESS-MATCHED-BROWSER-PILOT-001"
_ALLOWED = {"CSR_SPA", "HYDRATED", "MIXED"}
_KEYS = ("page_id", "device", "architecture", "browser_version",
         "network_profile", "cpu_profile", "context_profile", "navigation_url")
_MAX_PAIRS = 200
_MAX_MS = 600_000


def _duration(value: Any) -> bool:
    return (
        type(value) in (int, float) and math.isfinite(value)
        and 0 <= value <= _MAX_MS
    )


def _percentile(values: list[float], fraction: float) -> float:
    values = sorted(values)
    offset = (len(values) - 1) * fraction
    left = int(offset)
    return values[left] + (values[min(left + 1, len(values) - 1)] - values[left]) * (offset - left)


def assess_matched_readiness_pilot(
    pairs: Sequence[Mapping[str, Any]] | None,
    *, overhead_budget_ms: float = 30.0,
    min_pairs: int = 5,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "contract_version": VERSION,
        "status": "NOT_EVALUABLE",
        "pairs_accepted": 0,
        "measured_wall_delta_median_ms": None,
        "measured_wall_delta_p90_ms": None,
        "max_observed_probe_active_ms": None,
        "within_declared_overhead_budget": None,
        "budget_ms": overhead_budget_ms,
        "gateway_identity_attested": False,
        "m25_production_activation_approved": False,
        "m25_apdex_changed": False,
        "integration_boundary": "PILOT_ONLY_NOT_PRODUCTION_AUTHORIZATION",
        "provenance": "OPERATOR_DECLARED_PAIRS_NOT_M25_RUNTIME_ATTESTED",
        "reason": "INSUFFICIENT_OR_UNVERIFIED_PAIRING",
        "provider_requests": 0,
        "audit_writes": 0,
    }
    if (
        type(overhead_budget_ms) not in (int, float)
        or not math.isfinite(overhead_budget_ms)
        or not 0 < overhead_budget_ms <= 1000
        or type(min_pairs) is not int or not 2 <= min_pairs <= _MAX_PAIRS
    ):
        raise ValueError("invalid pilot budget or minimum sample pairs")
    if not isinstance(pairs, (list, tuple)) or not 0 < len(pairs) <= _MAX_PAIRS:
        return result
    seen: set[str] = set()
    identity = None
    overheads: list[float] = []
    measured: list[float] = []
    for pair in pairs:
        if not isinstance(pair, Mapping):
            result["reason"] = "INVALID_PAIR"
            return result
        context = tuple(pair.get(key) for key in _KEYS)
        if (
            not all(isinstance(x, str) and bool(x.strip()) and len(x) <= 300 for x in context)
            or pair.get("architecture") not in _ALLOWED
        ):
            result["reason"] = "UNVERIFIABLE_OR_INELIGIBLE_ARCHITECTURE_CONTEXT"
            return result
        if identity is not None and context != identity:
            result["reason"] = "UNMATCHED_BROWSER_CONTEXT_OR_URL"
            return result
        identity = context
        control, probe = pair.get("control"), pair.get("probe")
        if not isinstance(control, Mapping) or not isinstance(probe, Mapping):
            result["reason"] = "MISSING_CONTROL_OR_PROBE"
            return result
        control_id, probe_id = control.get("sample_id"), probe.get("sample_id")
        if (
            any(not isinstance(x, str) or not x.strip() or len(x) > 160
                for x in (control_id, probe_id))
            or control_id == probe_id
            or control_id in seen or probe_id in seen
        ):
            result["reason"] = "DUPLICATE_OR_UNVERIFIABLE_SAMPLE_ID"
            return result
        seen.update((control_id, probe_id))
        no_probe = control.get("load_duration_ms")
        probed = probe.get("load_duration_ms")
        cost = probe.get("active_probe_wall_ms")
        if not all(_duration(x) for x in (no_probe, probed, cost)):
            result["reason"] = "NONFINITE_OR_MISSING_MONOTONIC_DURATION"
            return result
        if (
            probe.get("enabled") is not True
            or probe.get("identity_proof") != "CALLER_DECLARED_NOT_ATTESTED_BY_M25"
            or probe.get("source_page_reused") is not True
        ):
            result["reason"] = "PROBE_IDENTITY_OR_OPT_IN_NOT_PROVEN"
            return result
        measured.append(round(float(probed) - float(no_probe), 3))
        overheads.append(float(cost))
    if len(pairs) < min_pairs:
        result["pairs_accepted"] = len(pairs)
        result["reason"] = "TOO_FEW_MATCHED_PAIRS"
        return result
    result["status"] = "MATCHED_LOCAL_PILOT_ASSESSED"
    result["pairs_accepted"] = len(pairs)
    result["measured_wall_delta_median_ms"] = round(_percentile(measured, .5), 3)
    result["measured_wall_delta_p90_ms"] = round(_percentile(measured, .9), 3)
    result["max_observed_probe_active_ms"] = round(max(overheads), 3)
    result["within_declared_overhead_budget"] = (
        result["measured_wall_delta_p90_ms"] <= overhead_budget_ms
        and result["max_observed_probe_active_ms"] <= overhead_budget_ms
    )
    result["reason"] = (
        "LOCAL_BUDGET_MET_BUT_PRODUCTION_GATE_REMAINS"
        if result["within_declared_overhead_budget"]
        else "LOCAL_PROBE_OVERHEAD_EXCEEDS_DECLARED_BUDGET"
    )
    return result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Read-only offline A/B probe-cost pilot, not M25 calibration."
    )
    parser.add_argument("--json", type=Path, required=True)
    parser.add_argument("--budget-ms", type=float, default=30.0)
    parser.add_argument("--min-pairs", type=int, default=5)
    args = parser.parse_args(argv)
    try:
        path = args.json
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 1024 * 1024:
            parser.error("local pilot JSON must be a regular file <= 1 MiB")
        obj = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError):
        parser.error("cannot load pilot JSON")
    if not isinstance(obj, dict):
        parser.error("pilot JSON must contain an object")
    try:
        result = assess_matched_readiness_pilot(
            obj.get("pairs"), overhead_budget_ms=args.budget_ms,
            min_pairs=args.min_pairs,
        )
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps(result, sort_keys=True, ensure_ascii=False, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
