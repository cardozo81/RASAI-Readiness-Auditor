"""Deterministic actionability classification for M14 reporting.

Actionability is deliberately independent from the raw RuleResult.  It answers
whether a website change is justified by the evidence, while RuleResult keeps
its original scoring semantics.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from rasai.domain import RuleResult


class Actionability(StrEnum):
    REQUIRED_FIX = "REQUIRED_FIX"
    REVIEW_RECOMMENDED = "REVIEW_RECOMMENDED"
    OPTIONAL_IMPROVEMENT = "OPTIONAL_IMPROVEMENT"
    NO_ACTION = "NO_ACTION"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


ACTIONABILITY_LABELS = {
    Actionability.REQUIRED_FIX: "AÇÃO NECESSÁRIA",
    Actionability.REVIEW_RECOMMENDED: "REVISÃO RECOMENDADA",
    Actionability.OPTIONAL_IMPROVEMENT: "MELHORIA OPCIONAL",
    Actionability.NO_ACTION: "NENHUMA AÇÃO NECESSÁRIA",
    Actionability.INSUFFICIENT_EVIDENCE: "AÇÃO NO SITE NÃO DETERMINADA",
}

# These rules may expose an intentional policy or contextual difference.  A
# negative/partial technical result is not sufficient to order a site change.
_REVIEW_RULES = frozenset({
    "BR-GEO-012",  # noindex can be intentional
    "BR-GEO-018",  # crawler access is an organizational policy decision
    "BR-GEO-052",  # Desktop/Mobile difference is not automatically a defect
})


def classify_actionability(
    result: RuleResult | str,
    *,
    rule_id: str,
    observed_value: Any = None,
) -> Actionability:
    """Classify the action justified by one persisted rule result.

    The function never changes RuleResult and never feeds scoring.  It is a
    deterministic projection used by recommendations/reporting.
    """

    normalized = result if isinstance(result, RuleResult) else RuleResult(str(result))

    if normalized in {RuleResult.PASS, RuleResult.NOT_APPLICABLE}:
        return Actionability.NO_ACTION
    if normalized in {RuleResult.UNKNOWN, RuleResult.ERROR}:
        return Actionability.INSUFFICIENT_EVIDENCE
    if rule_id in _REVIEW_RULES:
        return Actionability.REVIEW_RECOMMENDED

    # BR-GEO-003 explicitly says that absence of a sitemap is not an automatic
    # failure.  When an implementation records that absence as a warning, keep
    # it non-blocking and label it as an optional capability improvement.
    if rule_id == "BR-GEO-003" and normalized is RuleResult.WARNING:
        state = _observed_state(observed_value)
        if state in {"ABSENT", "NOT_FOUND", "NÃO LOCALIZADO", "NAO LOCALIZADO"}:
            return Actionability.OPTIONAL_IMPROVEMENT

    if normalized is RuleResult.FAIL:
        return Actionability.REQUIRED_FIX
    return Actionability.REVIEW_RECOMMENDED


def label_for(actionability: Actionability) -> str:
    return ACTIONABILITY_LABELS[actionability]


def _observed_state(value: Any) -> str:
    if isinstance(value, dict):
        for key in ("state", "status", "sitemap_state"):
            candidate = value.get(key)
            if candidate is not None:
                return str(candidate).strip().upper()
    return ""
