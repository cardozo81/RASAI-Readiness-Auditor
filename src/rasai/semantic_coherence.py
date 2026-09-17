"""Evidence-bound semantic-coherence contracts for CAT-03.

These assessments are diagnostic and deliberately independent from SARI/SCORE-GEO.
Page-level coherence is produced within the existing semantic provider call. Property-
level coherence is aggregated deterministically after every page result is persisted.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class CoherenceResult(StrEnum):
    COHERENT = "COHERENT"
    PARTIAL = "PARTIAL"
    INCOHERENT = "INCOHERENT"
    NOT_DETERMINABLE = "NOT_DETERMINABLE"
    NOT_APPLICABLE = "NOT_APPLICABLE"


PAGE_COHERENCE_CRITERIA: dict[str, str] = {
    "SC-P01": "title and visible main content express a consistent primary subject",
    "SC-P02": "headings and visible main content express a consistent semantic hierarchy",
    "SC-P03": "declared or interpreted page purpose is coherent with visible content and user intent",
    "SC-P04": "declared or interpreted audience is coherent with language, depth and terminology",
    "SC-P05": "declared primary offering is coherently represented when applicable",
    "SC-P06": "declared positioning is coherently represented when applicable",
    "SC-P07": "observed entities are coherent with the visible content",
    "SC-P08": "structured data is coherent with visible content",
    "SC-P09": "structured-data entities are coherent with entities observed in visible content",
    "SC-P10": "calls to action are coherent with page purpose and declared property goal when applicable",
    "SC-P11": "material claims expose sufficient observable support or qualification for their context",
    "SC-P12": "responsibility/authorship signals are coherent with editorial risk and trust requirements",
    "SC-P13": "freshness/publication signals are coherent with the page's temporal sensitivity",
}
PAGE_COHERENCE_IDS = tuple(PAGE_COHERENCE_CRITERIA)

PROPERTY_SIGNAL_NAMES = (
    "organization_identity",
    "business_sector",
    "primary_offering",
    "target_audience_profile",
    "primary_goal",
    "positioning",
)

PROPERTY_COHERENCE_CRITERIA: dict[str, str] = {
    "SC-X01": "organization identity remains coherent across audited pages",
    "SC-X02": "primary offering remains aligned across audited pages and declared property context",
    "SC-X03": "target audience remains aligned across audited pages and declared property context",
    "SC-X04": "positioning remains aligned across audited pages and declared property context",
    "SC-X05": "primary goal and calls to action remain aligned across audited pages",
    "SC-X06": "page purposes remain aligned with the property context without material contradiction",
}
PROPERTY_COHERENCE_IDS = tuple(PROPERTY_COHERENCE_CRITERIA)


@dataclass(frozen=True, slots=True)
class PageCoherenceAssessment:
    criterion_id: str
    result: CoherenceResult
    confidence: float
    declared_context: str
    observed_context: str
    evidence_ids: tuple[str, ...]
    reasoning_summary: str


@dataclass(frozen=True, slots=True)
class PropertySemanticSignal:
    signal_name: str
    value: str | None
    confidence: float
    evidence_ids: tuple[str, ...]


def page_coherence_output_schema(
    allowed_evidence_ids: frozenset[str] | None = None,
) -> dict[str, Any]:
    evidence_item: dict[str, Any] = {"type": "string"}
    if allowed_evidence_ids:
        evidence_item["enum"] = sorted(allowed_evidence_ids)
    return {
        "type": "array",
        "minItems": len(PAGE_COHERENCE_IDS),
        "maxItems": len(PAGE_COHERENCE_IDS),
        "items": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "criterion_id": {"type": "string", "enum": list(PAGE_COHERENCE_IDS)},
                "result": {"type": "string", "enum": [item.value for item in CoherenceResult]},
                "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                "declared_context": {"type": "string"},
                "observed_context": {"type": "string"},
                "evidence_ids": {"type": "array", "items": evidence_item},
                "reasoning_summary": {"type": "string"},
            },
            "required": [
                "criterion_id",
                "result",
                "confidence",
                "declared_context",
                "observed_context",
                "evidence_ids",
                "reasoning_summary",
            ],
        },
    }


def property_signal_output_schema(
    allowed_evidence_ids: frozenset[str] | None = None,
) -> dict[str, Any]:
    evidence_item: dict[str, Any] = {"type": "string"}
    if allowed_evidence_ids:
        evidence_item["enum"] = sorted(allowed_evidence_ids)
    return {
        "type": "array",
        "minItems": len(PROPERTY_SIGNAL_NAMES),
        "maxItems": len(PROPERTY_SIGNAL_NAMES),
        "items": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "signal_name": {"type": "string", "enum": list(PROPERTY_SIGNAL_NAMES)},
                "value": {"type": ["string", "null"]},
                "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                "evidence_ids": {"type": "array", "items": evidence_item},
            },
            "required": ["signal_name", "value", "confidence", "evidence_ids"],
        },
    }


def coherence_prompt_directive() -> str:
    criteria = "; ".join(f"{key}={value}" for key, value in PAGE_COHERENCE_CRITERIA.items())
    signals = ",".join(PROPERTY_SIGNAL_NAMES)
    return (
        "In the same response, evaluate page semantic coherence using exactly one item for every "
        f"criterion ({criteria}). Coherence compares declared context with supplied observable evidence; "
        "it does not create a ranking score. Use NOT_DETERMINABLE when evidence is insufficient and "
        "NOT_APPLICABLE only when a criterion genuinely does not apply. COHERENT, PARTIAL and INCOHERENT "
        "must cite supplied evidence_ids. Also return exactly one observed property signal for each of: "
        f"{signals}. A signal is an observed/inferred page-level descriptor, not a declared fact; use "
        "value=null with empty evidence_ids when it cannot be determined. Never invent hidden business "
        "facts, credentials, reputation, policies, audiences or offerings."
    )
