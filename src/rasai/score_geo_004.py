"""Canonical pre-release contract for SARI-001 / SCORE-GEO-004.

SCORE-GEO-004 remains the sole runtime scoring identifier while RASAi is still in
pre-production.  This module is the single source of truth for the current
hierarchical weighting model, rule-to-group mapping, evidence precedence and
critical readiness gates.

The contract deliberately separates:

* quality score (0..100);
* measurement Coverage/Confidence/Consolidation;
* critical readiness gate state;
* external metrics and observed outcomes, which are not score inputs by default.
"""
from __future__ import annotations

from dataclasses import dataclass


SCORING_VERSION = "SCORE-GEO-004"
OVERALL_AGGREGATION_VERSION = "HIERARCHICAL_WEIGHTED_READINESS_V1"
DIMENSION_WEIGHT_VERSION = "SARI_DIMENSION_WEIGHTS_V1"
GROUP_WEIGHT_VERSION = "SARI_GROUP_WEIGHTS_V1"
CRITICAL_GATE_VERSION = "SARI_CRITICAL_GATES_V1"
MEASUREMENT_CONFIDENCE_VERSION = "WEIGHTED_MEASUREMENT_CONFIDENCE_V1"

MIN_OVERALL_COVERAGE = 0.80
MIN_PARTIAL_COVERAGE = 0.50

EVIDENCE_ROLE_DETERMINISTIC_PRIMARY = "DETERMINISTIC_PRIMARY"
EVIDENCE_ROLE_AI_CORROBORATIVE = "AI_CORROBORATIVE"

FEATURE_ORDER = (
    "DISCOVERY_ACCESS",
    "INDEXABILITY",
    "CONTENT_EXTRACTABILITY",
    "SEMANTIC_STRUCTURE",
    "ENTITY_CLARITY",
    "STRUCTURED_DATA",
    "ANSWERABILITY",
    "CITATION_READINESS",
    "EVIDENCE_TRUST",
    "INTENT_COVERAGE",
    "CONTENT_VALUE",
)

# Public SARI weight.  These values are fixed by the scoring contract, not by an
# audit configuration.  Legitimately NOT_APPLICABLE dimensions leave the
# denominator and the remaining weights are normalized.
DIMENSION_WEIGHTS: dict[str, float] = {
    "DISCOVERY_ACCESS": 0.15,
    "INDEXABILITY": 0.15,
    "CONTENT_EXTRACTABILITY": 0.15,
    "SEMANTIC_STRUCTURE": 0.07,
    "ENTITY_CLARITY": 0.08,
    "STRUCTURED_DATA": 0.05,
    "ANSWERABILITY": 0.07,
    "CITATION_READINESS": 0.07,
    "EVIDENCE_TRUST": 0.08,
    "INTENT_COVERAGE": 0.05,
    "CONTENT_VALUE": 0.08,
}

MACRO_COMPONENTS: dict[str, tuple[str, ...]] = {
    "DISCOVERY_AND_CRAWLER_ACCESS": ("DISCOVERY_ACCESS",),
    "INDEXABILITY_AND_CANONICALIZATION": ("INDEXABILITY",),
    "RENDERING_AND_EXTRACTABILITY": ("CONTENT_EXTRACTABILITY",),
    "SEMANTIC_UNDERSTANDABILITY": ("SEMANTIC_STRUCTURE", "ENTITY_CLARITY"),
    "CONTENT_UTILITY_AND_INTENT": ("ANSWERABILITY", "INTENT_COVERAGE", "CONTENT_VALUE"),
    "EVIDENCE_TRUST_AND_CITATION": ("CITATION_READINESS", "EVIDENCE_TRUST"),
    "STRUCTURED_DATA": ("STRUCTURED_DATA",),
}

# Weights are stable inside each dimension.  Page count never multiplies a
# group's importance: the group weight is divided across its applicable scopes.
GROUP_WEIGHTS: dict[str, dict[str, float]] = {
    "DISCOVERY_ACCESS": {
        "PAGE_ACCESS": 0.30,
        "ROBOTS": 0.15,
        "SITEMAP": 0.05,
        "REDIRECT": 0.10,
        "SPA_ROUTE": 0.10,
        "SPA_NAVIGATION": 0.10,
        "INTERNAL_LINKS": 0.20,
    },
    "INDEXABILITY": {
        "INDEX_DIRECTIVES": 0.35,
        "CANONICAL": 0.30,
        "SOFT_ERROR": 0.35,
    },
    "CONTENT_EXTRACTABILITY": {
        "RENDER_ACCESS": 0.30,
        "JS_CONTENT": 0.25,
        "CONTENT_EXTRACTION": 0.35,
        "DUPLICATE_CONTENT": 0.10,
    },
    "SEMANTIC_STRUCTURE": {
        "SEMANTIC_TITLE": 0.30,
        "SEMANTIC_HIERARCHY": 0.30,
        "SEMANTIC_TOPIC": 0.40,
    },
    "ENTITY_CLARITY": {
        "ENTITY_PRIMARY": 0.35,
        "ENTITY_CONTEXT": 0.40,
        "ENTITY_AMBIGUITY": 0.25,
    },
    "STRUCTURED_DATA": {
        "STRUCTURED_DATA_SYNTAX": 0.40,
        "STRUCTURED_DATA_CONSISTENCY": 0.60,
    },
    "ANSWERABILITY": {
        "PRIMARY_INTENT": 0.35,
        "PRIMARY_ANSWERS": 0.65,
    },
    "CITATION_READINESS": {
        "FACTUAL_CLAIMS": 0.20,
        "FACTUAL_CONTEXT": 0.45,
        "INFERENCE_LOAD": 0.35,
    },
    "EVIDENCE_TRUST": {
        "ATTRIBUTION": 0.40,
        "RESPONSIBILITY": 0.35,
        "FRESHNESS": 0.25,
    },
    "INTENT_COVERAGE": {
        "INTENT_SET": 0.45,
        "INTENT_GAPS": 0.55,
    },
    "CONTENT_VALUE": {
        "CONTENT_USEFULNESS": 0.40,
        "CONTENT_DIFFERENTIATION": 0.30,
        "CONTENT_DEPTH": 0.30,
    },
}

CRITICAL_GATES: dict[str, tuple[str, tuple[str, ...]]] = {
    "DISCOVERY": (
        "DISCOVERY_ACCESS",
        ("PAGE_ACCESS", "ROBOTS", "REDIRECT"),
    ),
    "INDEXABILITY": (
        "INDEXABILITY",
        ("INDEX_DIRECTIVES", "CANONICAL", "SOFT_ERROR"),
    ),
    "EXTRACTION": (
        "CONTENT_EXTRACTABILITY",
        ("RENDER_ACCESS", "JS_CONTENT", "CONTENT_EXTRACTION"),
    ),
}

CRITICAL_DIMENSIONS = frozenset(dimension for dimension, _groups in CRITICAL_GATES.values())


@dataclass(frozen=True, slots=True)
class RuleContract:
    dimension: str
    scoring_group: str
    warning_factor: float = 0.50
    evidence_role: str = EVIDENCE_ROLE_DETERMINISTIC_PRIMARY

    @property
    def group_weight(self) -> float:
        return GROUP_WEIGHTS[self.dimension][self.scoring_group]


def _rule(
    dimension: str,
    group: str,
    *,
    warning_factor: float = 0.50,
    evidence_role: str = EVIDENCE_ROLE_DETERMINISTIC_PRIMARY,
) -> RuleContract:
    return RuleContract(
        dimension=dimension,
        scoring_group=group,
        warning_factor=warning_factor,
        evidence_role=evidence_role,
    )


# Explicit rule manifest.  Non-scoring acquisition/auditor-integrity rules are
# intentionally absent instead of being inferred from BR-GEO number ranges.
RULE_SCORING_CONTRACT: dict[str, RuleContract] = {
    "BR-GEO-003": _rule("DISCOVERY_ACCESS", "SITEMAP", warning_factor=0.80),
    "BR-GEO-005": _rule("DISCOVERY_ACCESS", "PAGE_ACCESS"),
    "BR-GEO-006": _rule("DISCOVERY_ACCESS", "PAGE_ACCESS"),
    "BR-GEO-007": _rule("DISCOVERY_ACCESS", "REDIRECT"),
    "BR-GEO-008": _rule("DISCOVERY_ACCESS", "REDIRECT"),
    "BR-GEO-009": _rule("CONTENT_EXTRACTABILITY", "RENDER_ACCESS"),
    "BR-GEO-010": _rule("CONTENT_EXTRACTABILITY", "RENDER_ACCESS"),
    "BR-GEO-011": _rule("INDEXABILITY", "INDEX_DIRECTIVES"),
    "BR-GEO-012": _rule("INDEXABILITY", "INDEX_DIRECTIVES"),
    "BR-GEO-013": _rule("INDEXABILITY", "CANONICAL"),
    "BR-GEO-014": _rule("INDEXABILITY", "CANONICAL"),
    "BR-GEO-015": _rule("INDEXABILITY", "INDEX_DIRECTIVES"),
    "BR-GEO-016": _rule("INDEXABILITY", "SOFT_ERROR"),
    "BR-GEO-017": _rule("DISCOVERY_ACCESS", "ROBOTS", warning_factor=0.60),
    "BR-GEO-018": _rule("DISCOVERY_ACCESS", "ROBOTS", warning_factor=0.60),
    "BR-GEO-019": _rule("CONTENT_EXTRACTABILITY", "JS_CONTENT"),
    "BR-GEO-020": _rule("CONTENT_EXTRACTABILITY", "JS_CONTENT"),
    "BR-GEO-021": _rule("DISCOVERY_ACCESS", "SPA_ROUTE"),
    "BR-GEO-022": _rule("DISCOVERY_ACCESS", "SPA_NAVIGATION"),
    "BR-GEO-023": _rule("INDEXABILITY", "SOFT_ERROR"),
    "BR-GEO-024": _rule("CONTENT_EXTRACTABILITY", "JS_CONTENT"),
    "BR-GEO-025": _rule("CONTENT_EXTRACTABILITY", "CONTENT_EXTRACTION"),
    "BR-GEO-026": _rule("CONTENT_EXTRACTABILITY", "CONTENT_EXTRACTION"),
    "BR-GEO-027": _rule("CONTENT_EXTRACTABILITY", "CONTENT_EXTRACTION"),
    "BR-GEO-028": _rule("SEMANTIC_STRUCTURE", "SEMANTIC_TITLE"),
    "BR-GEO-029": _rule("SEMANTIC_STRUCTURE", "SEMANTIC_HIERARCHY"),
    "BR-GEO-030": _rule("SEMANTIC_STRUCTURE", "SEMANTIC_TOPIC"),
    "BR-GEO-031": _rule("ENTITY_CLARITY", "ENTITY_PRIMARY"),
    "BR-GEO-032": _rule("ENTITY_CLARITY", "ENTITY_CONTEXT"),
    "BR-GEO-033": _rule("ENTITY_CLARITY", "ENTITY_AMBIGUITY"),
    "BR-GEO-034": _rule("STRUCTURED_DATA", "STRUCTURED_DATA_SYNTAX", warning_factor=0.80),
    "BR-GEO-035": _rule("STRUCTURED_DATA", "STRUCTURED_DATA_SYNTAX"),
    "BR-GEO-036": _rule("STRUCTURED_DATA", "STRUCTURED_DATA_CONSISTENCY"),
    "BR-GEO-037": _rule("STRUCTURED_DATA", "STRUCTURED_DATA_CONSISTENCY"),
    "BR-GEO-038": _rule("ANSWERABILITY", "PRIMARY_INTENT"),
    "BR-GEO-039": _rule("ANSWERABILITY", "PRIMARY_ANSWERS"),
    "BR-GEO-040": _rule("ANSWERABILITY", "PRIMARY_ANSWERS"),
    "BR-GEO-041": _rule("CITATION_READINESS", "FACTUAL_CLAIMS"),
    "BR-GEO-042": _rule("CITATION_READINESS", "FACTUAL_CONTEXT"),
    "BR-GEO-043": _rule("CITATION_READINESS", "FACTUAL_CONTEXT"),
    "BR-GEO-044": _rule("CITATION_READINESS", "INFERENCE_LOAD"),
    "BR-GEO-045": _rule("EVIDENCE_TRUST", "ATTRIBUTION"),
    "BR-GEO-046": _rule("EVIDENCE_TRUST", "RESPONSIBILITY"),
    "BR-GEO-047": _rule("EVIDENCE_TRUST", "FRESHNESS"),
    "BR-GEO-048": _rule("INTENT_COVERAGE", "INTENT_SET"),
    "BR-GEO-049": _rule("INTENT_COVERAGE", "INTENT_GAPS"),
    "BR-GEO-050": _rule("DISCOVERY_ACCESS", "INTERNAL_LINKS"),
    "BR-GEO-051": _rule("CONTENT_EXTRACTABILITY", "DUPLICATE_CONTENT"),
    "BR-GEO-055": _rule(
        "DISCOVERY_ACCESS",
        "SITEMAP",
        warning_factor=0.80,
        evidence_role=EVIDENCE_ROLE_AI_CORROBORATIVE,
    ),
    "BR-GEO-056": _rule(
        "DISCOVERY_ACCESS",
        "ROBOTS",
        warning_factor=0.60,
        evidence_role=EVIDENCE_ROLE_AI_CORROBORATIVE,
    ),
    "BR-GEO-057": _rule("CONTENT_VALUE", "CONTENT_USEFULNESS"),
    "BR-GEO-058": _rule("CONTENT_VALUE", "CONTENT_DIFFERENTIATION"),
    "BR-GEO-059": _rule("CONTENT_VALUE", "CONTENT_DEPTH"),
}


def rule_contract(rule_id: str) -> RuleContract | None:
    return RULE_SCORING_CONTRACT.get(rule_id)


def method_trace_limitations() -> tuple[str, ...]:
    """Persist an explicit trace of the active pre-release scoring contract."""
    return (
        f"OVERALL_AGGREGATION:{OVERALL_AGGREGATION_VERSION}",
        f"DIMENSION_WEIGHTS:{DIMENSION_WEIGHT_VERSION}",
        f"GROUP_WEIGHTS:{GROUP_WEIGHT_VERSION}",
        f"CRITICAL_GATES:{CRITICAL_GATE_VERSION}",
        f"MEASUREMENT_CONFIDENCE:{MEASUREMENT_CONFIDENCE_VERSION}",
        "EMPIRICAL_VALIDATION:NOT_SCORE_INPUT",
    )


def validate_contract() -> None:
    if tuple(DIMENSION_WEIGHTS) != FEATURE_ORDER:
        raise RuntimeError("dimension weight order must match FEATURE_ORDER")
    if abs(sum(DIMENSION_WEIGHTS.values()) - 1.0) > 1e-9:
        raise RuntimeError("SARI dimension weights must sum to 1.0")
    for dimension in FEATURE_ORDER:
        groups = GROUP_WEIGHTS.get(dimension)
        if not groups:
            raise RuntimeError(f"missing group weights for {dimension}")
        if abs(sum(groups.values()) - 1.0) > 1e-9:
            raise RuntimeError(f"group weights for {dimension} must sum to 1.0")
    for rule_id, contract in RULE_SCORING_CONTRACT.items():
        if contract.dimension not in DIMENSION_WEIGHTS:
            raise RuntimeError(f"{rule_id} references unknown dimension {contract.dimension}")
        if contract.scoring_group not in GROUP_WEIGHTS[contract.dimension]:
            raise RuntimeError(f"{rule_id} references unknown group {contract.scoring_group}")


validate_contract()
