"""Evidence classification for optional SEO signals, without score changes.

This deliberately does not export a RuleResult, scoring factor or replacement
SCORE-GEO contract. It interprets only the source shape actually persisted by
M5. The optional signal's absence does not prove indexing harm.
"""
from __future__ import annotations

import json
from typing import Any, Mapping

_RULES = frozenset({"BR-GEO-003", "BR-GEO-013", "BR-GEO-017"})
_MAX_EVIDENCE_CHARS = 16384


def classify_seo_evidence(rule_id: str, observed_value: Any) -> str:
    """Classify physical evidence, never infer a website defect from a fetch failure.

    Return: OPTIONAL_ABSENCE, OBSERVED_CONFLICT, AVAILABLE or UNKNOWN.
    Only exact known M5 keys are accepted. UNKNOWN is the safe default.
    """
    if rule_id not in _RULES:
        return "UNKNOWN"
    if isinstance(observed_value, str):
        if len(observed_value) > _MAX_EVIDENCE_CHARS:
            return "UNKNOWN"
        try:
            data = json.loads(
                observed_value,
                object_pairs_hook=_reject_duplicate_keys,
                parse_constant=_reject_constant,
            )
        except (ValueError, TypeError):
            return "UNKNOWN"
    else:
        data = observed_value
    if not isinstance(data, Mapping):
        return "UNKNOWN"

    if rule_id == "BR-GEO-017":
        state = data.get("state")
        # An HTTP/acquisition error is not affirmative proof of an
        # intentionally absent optional robots file.
        if data.get("error") not in (None, ""):
            return "UNKNOWN"
        if state == "ABSENT":
            return "OPTIONAL_ABSENCE"
        if state == "OBTAINED":
            return "AVAILABLE"
        return "UNKNOWN"

    if rule_id == "BR-GEO-003":
        rows = data.get("sitemaps")
        if not isinstance(rows, list) or not rows or len(rows) > 100:
            return "UNKNOWN"
        states: list[str] = []
        for row in rows:
            if not isinstance(row, Mapping) or not isinstance(row.get("state"), str):
                return "UNKNOWN"
            if row.get("error") not in (None, ""):
                return "UNKNOWN"
            states.append(row["state"])
        if "NETWORK_ERROR" in states:
            return "UNKNOWN"
        if "INVALID" in states:
            return "OBSERVED_CONFLICT"
        if "HTTP_ERROR" in states:
            # HTTP failure alone does not prove absence across other paths.
            return "UNKNOWN"
        if "OBTAINED" in states:
            return "AVAILABLE"
        if all(state == "ABSENT" for state in states):
            return "OPTIONAL_ABSENCE"
        return "UNKNOWN"

    # BR-GEO-013: missing canonical is advisory only. A conflicting set or
    # invalid declaration is different, observed technical evidence.
    missing = data.get("canonicals")
    if missing == []:
        # A self-contradictory record (empty declared canonicals plus
        # another explicit invalid or normalized declaration) is UNKNOWN,
        # not a harmless optional omission.
        if any(data.get(key) not in (None, []) for key in (
            "declared", "invalid", "normalized",
        )):
            return "UNKNOWN"
        return "OPTIONAL_ABSENCE"
    invalid = data.get("invalid")
    normalized = data.get("normalized")
    declared = data.get("declared")
    if not isinstance(invalid, list) or not isinstance(normalized, list):
        return "UNKNOWN"
    if not isinstance(declared, list) or not declared:
        return "UNKNOWN"
    if any(not isinstance(item, str) for item in (*invalid, *normalized, *declared)):
        return "UNKNOWN"
    if invalid or len(set(normalized)) > 1:
        return "OBSERVED_CONFLICT"
    if len(normalized) == 1:
        return "AVAILABLE"
    return "UNKNOWN"


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("ambiguous duplicate JSON key")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ValueError("nonstandard JSON literal: " + value)
