"""SCORE-GEO-004 deterministic operational scoring contract.

SCORE-GEO-004 keeps the evidence, applicability and dimension arithmetic used by
the established RASAi scoring engine. It changes the operational Overall
contract introduced by SCORE-GEO-003: empirical calibration is no longer a
runtime prerequisite. The Overall is a transparent equal-weight mean of the
applicable dimension scores and can be consolidated from one audit when the
measurement itself has sufficient Coverage and Confidence.

SCORE-GEO-003 remains a historical calibrated method and its calibration
pipeline remains available for empirical validation/research. SCORE-GEO-004
never represents its deterministic Overall as a probability of citation.
"""
from __future__ import annotations


SCORING_VERSION = "SCORE-GEO-004"
CALIBRATED_PREVIOUS_VERSION = "SCORE-GEO-003"
LEGACY_SCORING_VERSION = "SCORE-GEO-002"
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
        "EMPIRICAL_CALIBRATION:OPTIONAL_NOT_SCORE_INPUT",
    )
