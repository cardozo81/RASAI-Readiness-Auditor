"""SCORE-GEO-004 deterministic operational scoring contract.

SCORE-GEO-004 is the sole runtime scoring method for new RASAi audits. Dimension
evidence, applicability, Coverage and Confidence remain deterministic and
reproducible. The Overall is a transparent equal-weight mean of applicable
dimension scores and can be consolidated from one audit when the measurement
itself has sufficient Coverage and Confidence.

External empirical validation may be performed independently, but it is never a
runtime prerequisite and never changes the score silently. SCORE-GEO-004 does
not represent its Overall as a probability of ranking or citation.
"""
from __future__ import annotations


SCORING_VERSION = "SCORE-GEO-004"
OVERALL_AGGREGATION_VERSION = "EQUAL_WEIGHT_APPLICABLE_DIMENSIONS_V1"
MIN_OVERALL_COVERAGE = 0.80
MIN_PARTIAL_COVERAGE = 0.50

FEATURE_ORDER = (
    "TECHNICAL_ACCESSIBILITY",
    "INDEXABILITY",
    "CONTENT_EXTRACTABILITY",
    "SEMANTIC_STRUCTURE",
    "ENTITY_CLARITY",
    "STRUCTURED_DATA",
    "ANSWERABILITY",
    "CITATION_READINESS",
    "EVIDENCE_TRUST",
    "INTENT_COVERAGE",
)


def method_trace_limitations() -> tuple[str, ...]:
    """Persist an explicit trace of the deterministic Overall contract."""
    return (
        f"OVERALL_AGGREGATION:{OVERALL_AGGREGATION_VERSION}",
        "EMPIRICAL_VALIDATION:NOT_SCORE_INPUT",
    )
