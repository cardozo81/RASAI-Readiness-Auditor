"""Runtime engine for SCORE-GEO-004.

The dimension calculator remains deterministic and evidence-bound. SCORE-GEO-004
uses a transparent deterministic Overall so normal audits can publish a
consolidated readiness result without pretending that an empirical citation
model exists.
"""
from __future__ import annotations

from dataclasses import replace

from rasai.domain import DeviceContext, RuleExecution, new_id, utc_now
from rasai.score_geo_004 import (
    FEATURE_ORDER,
    MIN_OVERALL_COVERAGE,
    MIN_PARTIAL_COVERAGE,
    SCORING_VERSION,
    method_trace_limitations,
)
from rasai.scoring import (
    ConsolidationStatus,
    DIMENSIONS,
    Score,
    ScoreConfidence,
    ScoringEngine as LegacyScoringEngine,
    ScoringResult,
)


if DIMENSIONS != FEATURE_ORDER:
    raise RuntimeError("SCORE-GEO-004 dimension contract must match scoring dimensions")


class ScoreGeo004Engine:
    """Deterministic operational scoring engine for new audits."""

    def score(
        self,
        *,
        audit_id: str,
        executions: tuple[RuleExecution, ...] | list[RuleExecution],
        devices: tuple[DeviceContext, ...] | list[DeviceContext] | None = None,
    ) -> ScoringResult:
        base = LegacyScoringEngine().score(
            audit_id=audit_id,
            executions=executions,
            devices=devices,
        )
        dimensions = tuple(replace(score, scoring_version=SCORING_VERSION) for score in base.scores)
        overall = {
            device: self._overall(
                audit_id,
                device,
                tuple(score for score in dimensions if score.device is device),
            )
            for device in base.overall_by_device
        }
        return ScoringResult(dimensions, base.contributions, overall)

    def _overall(self, audit_id: str, device: DeviceContext, dimensions: tuple[Score, ...]) -> Score:
        applicable = tuple(
            item
            for item in dimensions
            if item.consolidation_status is not ConsolidationStatus.NOT_APPLICABLE
        )
        limitations: list[str] = [
            f"DIMENSION_NOT_APPLICABLE:{item.dimension}"
            for item in dimensions
            if item.consolidation_status is ConsolidationStatus.NOT_APPLICABLE
        ]
        blocking = tuple(
            item
            for item in applicable
            if item.consolidation_status is ConsolidationStatus.NOT_CONSOLIDATED
            or item.value is None
        )
        limitations.extend(f"DIMENSION_NOT_CONSOLIDATED:{item.dimension}" for item in blocking)

        coverage = (
            sum(item.coverage for item in applicable) / len(applicable)
            if applicable
            else 0.0
        )
        confidence = (
            min((item.confidence for item in applicable), key=_confidence_rank)
            if applicable
            else ScoreConfidence.UNAVAILABLE
        )
        complete_contract = len(dimensions) == len(DIMENSIONS) and bool(applicable) and not blocking

        if not complete_contract:
            return Score(
                score_id=new_id("SCR"),
                audit_id=audit_id,
                dimension="OVERALL_READINESS",
                device=device,
                value=None,
                coverage=round(coverage, 6),
                confidence=confidence,
                consolidation_status=ConsolidationStatus.NOT_CONSOLIDATED,
                scoring_version=SCORING_VERSION,
                calculated_at=utc_now(),
                limitations=tuple((*limitations, *method_trace_limitations())),
            )

        values = [float(item.value) for item in applicable if item.value is not None]
        value = sum(values) / len(values)
        if coverage >= MIN_OVERALL_COVERAGE and confidence in {
            ScoreConfidence.HIGH,
            ScoreConfidence.MEDIUM,
        }:
            consolidation = ConsolidationStatus.CONSOLIDATED
        elif coverage >= MIN_PARTIAL_COVERAGE and confidence is not ScoreConfidence.UNAVAILABLE:
            consolidation = ConsolidationStatus.PARTIAL
            limitations.append("OVERALL_MEASUREMENT_BELOW_CONSOLIDATION_GATE")
        else:
            consolidation = ConsolidationStatus.NOT_CONSOLIDATED
            limitations.append("OVERALL_MEASUREMENT_BELOW_MINIMUM_GATE")

        return Score(
            score_id=new_id("SCR"),
            audit_id=audit_id,
            dimension="OVERALL_READINESS",
            device=device,
            value=round(value, 6),
            coverage=round(coverage, 6),
            confidence=confidence,
            consolidation_status=consolidation,
            scoring_version=SCORING_VERSION,
            calculated_at=utc_now(),
            limitations=tuple((*limitations, *method_trace_limitations())),
        )


def _confidence_rank(value: ScoreConfidence) -> int:
    return {
        ScoreConfidence.UNAVAILABLE: 0,
        ScoreConfidence.LOW: 1,
        ScoreConfidence.MEDIUM: 2,
        ScoreConfidence.HIGH: 3,
    }[value]
