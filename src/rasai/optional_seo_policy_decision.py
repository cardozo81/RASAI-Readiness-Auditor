"""#602: decision-ready, strictly descriptive SCORE-GEO sensitivity projection.

Consumes ONLY a baseline-verified, locally sealed replay projection.
No scorer call, RuleExecution modification, provider request, persistence or
normative decision. All deltas are relative to canonical SCORE-GEO-004.
"""
from __future__ import annotations

from math import isfinite
from typing import Any, Mapping

_CANONICAL = "CANONICAL_SCORE_GEO_004"
_VARIANTS = (
    "SENSITIVITY_OPTIONAL_ABSENCE_PASS",
    "SENSITIVITY_OPTIONAL_ABSENCE_NOT_APPLICABLE",
)


def _finite(value: object, *, ceiling: float) -> float | None:
    if type(value) not in (int, float):
        return None
    number = float(value)
    return number if isfinite(number) and 0 <= number <= ceiling else None


def _quality(value: object) -> str | None:
    if not isinstance(value, str) or not value or len(value) > 100:
        return None
    # These strings are the scorer's in-memory fields, not user-supplied
    # provider text. Exclude arbitrary control characters from JSON output.
    return value if all(32 <= ord(ch) < 127 for ch in value) else None


def _gates(row: Mapping[str, Any]) -> list[str] | None:
    raw = row.get("readiness_limitations")
    if not isinstance(raw, list) or len(raw) > 100:
        return None
    if any(
        not isinstance(item, str) or len(item) > 240
        or not item.startswith(("READINESS_STATUS:", "CRITICAL_GATE:"))
        or any(ord(ch) < 32 or ord(ch) == 127 for ch in item)
        for item in raw
    ):
        return None
    return list(raw)


def build_optional_seo_decision_matrix(replay: Mapping[str, Any]) -> dict[str, Any]:
    """Show exact scenario deltas, coverage and gate transitions, never a new SARI.

    The caller must first execute the physical, immutable SQLite replay and
    verify full baseline parity. Projection fields alone are not cryptographic
    proof of authenticity, and no external-market comparability is asserted.
    """
    if not isinstance(replay, Mapping):
        raise ValueError("verified optional SEO replay required")
    if (replay.get("contract") != "RASAI-SEO-POLICY-SENSITIVITY-602-001"
            or replay.get("canonical_scoring_version") != "SCORE-GEO-004"
            or replay.get("source_audit_db_replay_parity") != "VERIFIED_SCORE_GEO_004"
            or replay.get("published_score_mutated") is not False
            or replay.get("new_scoring_version_approved") is not False
            or replay.get("provider_requests") != 0
            or replay.get("audit_writes") != 0):
        raise ValueError("canonical read-only replay parity not verified")
    digest = replay.get("source_audit_db_sha256")
    if (not isinstance(digest, str) or len(digest) != 64
            or any(ch not in "0123456789abcdef" for ch in digest)):
        raise ValueError("physical source seal not verified")
    scenarios = replay.get("scenarios")
    if not isinstance(scenarios, Mapping):
        raise ValueError("three sensitivity scenarios required")
    if set(scenarios) != {_CANONICAL, *_VARIANTS}:
        raise ValueError("incomplete or ambiguous sensitivity scenario set")
    reference = scenarios[_CANONICAL]
    if (not isinstance(reference, Mapping)
            or "OVERALL_READINESS" not in reference
            or not 1 <= len(reference) <= 20
            or any(not isinstance(name, str) or len(name) > 100
                   for name in reference)):
        raise ValueError("invalid canonical dimensions")
    for name in (_CANONICAL, *_VARIANTS):
        if not isinstance(scenarios[name], Mapping) or set(scenarios[name]) != set(reference):
            raise ValueError("scenario dimensions differ from verified baseline")

    lines: list[dict[str, Any]] = []
    for variant in _VARIANTS:
        for dimension in sorted(reference):
            current = reference[dimension]
            alternative = scenarios[variant][dimension]
            if not isinstance(current, Mapping) or not isinstance(alternative, Mapping):
                raise ValueError("dimension data cannot be compared")
            before = _finite(current.get("value"), ceiling=100)
            after = _finite(alternative.get("value"), ceiling=100)
            coverage_before = _finite(current.get("coverage"), ceiling=1)
            coverage_after = _finite(alternative.get("coverage"), ceiling=1)
            confidence_before = _quality(current.get("confidence"))
            confidence_after = _quality(alternative.get("confidence"))
            consolidation_before = _quality(current.get("consolidation_status"))
            consolidation_after = _quality(alternative.get("consolidation_status"))
            pairs = (
                (before, after), (coverage_before, coverage_after),
                (confidence_before, confidence_after),
                (consolidation_before, consolidation_after),
            )
            quality_complete = all(left is not None and right is not None
                                   for left, right in pairs)
            gate_before = _gates(current) if dimension == "OVERALL_READINESS" else None
            gate_after = _gates(alternative) if dimension == "OVERALL_READINESS" else None
            if dimension == "OVERALL_READINESS" and (gate_before is None or gate_after is None):
                quality_complete = False
            lines.append({
                "scenario": variant, "dimension": dimension,
                "canonical_points": before, "scenario_points": after,
                "delta_points": round(after - before, 6)
                if before is not None and after is not None else None,
                "canonical_coverage": coverage_before,
                "scenario_coverage": coverage_after,
                "delta_coverage_fraction": round(coverage_after - coverage_before, 8)
                if coverage_before is not None and coverage_after is not None else None,
                "canonical_confidence": confidence_before,
                "scenario_confidence": confidence_after,
                "canonical_consolidation": consolidation_before,
                "scenario_consolidation": consolidation_after,
                "canonical_readiness_gates": gate_before,
                "scenario_readiness_gates": gate_after,
                "interpretation": (
                    "UNVERIFIABLE" if not quality_complete else
                    "CHANGED" if any(left != right for left, right in pairs)
                    or (dimension == "OVERALL_READINESS" and gate_before != gate_after)
                    else "NO_OBSERVED_CHANGE"
                ),
            })
    return {
        "contract": "RASAI-SEO-POLICY-DECISION-602-001",
        "status": "DECISION_SUPPORT_ONLY_NOT_NORMATIVE",
        "baseline_version": "SCORE-GEO-004",
        "baseline_replay_parity": "VERIFIED_SCORE_GEO_004",
        "source_audit_db_sha256": digest,
        "source_rule_executions": replay.get("source_rule_executions"),
        "optional_absence_executions": replay.get("optional_absence_executions"),
        "rows": lines,
        "all_values_non_additive": True,
        "provider_requests": 0,
        "audit_writes": 0,
        "published_score_mutated": False,
        "new_scoring_version_approved": False,
        "limits": (
            "PASS/NOT_APPLICABLE are policy sensitivity boundaries only. "
            "Changes in scores, coverage, confidence and readiness gates must "
            "be considered together; deltas cannot be added to SARI. "
            "No revised scoring policy, equivalence of historical scores, "
            "search-market result or generative citation is authorized."
        ),
    }


__all__ = ["build_optional_seo_decision_matrix"]
