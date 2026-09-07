"""Runtime engine for SCORE-GEO-003.

The established deterministic dimension calculator remains untouched. This
adapter reuses its evidence/applicability semantics, versions the resulting
dimensions as SCORE-GEO-003 and replaces only Overall aggregation with the
validated calibrated model.
"""
from __future__ import annotations

from dataclasses import replace

from searchgeo.domain import DeviceContext, RuleExecution, new_id, utc_now
from searchgeo.score_geo_003 import (
    CalibrationModel,
    FEATURE_ORDER,
    SCORING_VERSION,
    model_trace_limitations,
)
from searchgeo.scoring import (
    ConsolidationStatus,
    DIMENSIONS,
    Score,
    ScoreConfidence,
    ScoringEngine as LegacyScoringEngine,
    ScoringResult,
)


if DIMENSIONS != FEATURE_ORDER:
    raise RuntimeError("SCORE-GEO-003 feature contract must match scoring dimensions")


class ScoreGeo003Engine:
    """Calibrated default scoring engine.

    A validated model is mandatory for a consolidated Overall. Missing or
    experimental calibration never falls back silently to SCORE-GEO-002.
    """

    def __init__(self, *, calibration_model: CalibrationModel | None = None) -> None:
        self.calibration_model = calibration_model if calibration_model is not None and calibration_model.validated else None

    def score(
        self,
        *,
        audit_id: str,
        executions: tuple[RuleExecution, ...] | list[RuleExecution],
        devices: tuple[DeviceContext, ...] | list[DeviceContext] | None = None,
    ) -> ScoringResult:
        legacy = LegacyScoringEngine().score(audit_id=audit_id, executions=executions, devices=devices)
        dimensions = tuple(replace(score, scoring_version=SCORING_VERSION) for score in legacy.scores)
        overall = {
            device: self._overall(audit_id, device, tuple(score for score in dimensions if score.device is device))
            for device in legacy.overall_by_device
        }
        return ScoringResult(dimensions, legacy.contributions, overall)

    def _overall(self, audit_id: str, device: DeviceContext, dimensions: tuple[Score, ...]) -> Score:
        applicable = tuple(
            item for item in dimensions
            if item.consolidation_status is not ConsolidationStatus.NOT_APPLICABLE
        )
        enough = (
            len(dimensions) == len(DIMENSIONS)
            and bool(applicable)
            and all(
                item.consolidation_status is not ConsolidationStatus.NOT_CONSOLIDATED
                and item.value is not None
                for item in applicable
            )
        )
        coverage = sum(item.coverage for item in applicable) / len(applicable) if applicable else 0.0
        limitations: list[str] = [
            f"DIMENSION_NOT_APPLICABLE:{item.dimension}"
            for item in dimensions
            if item.consolidation_status is ConsolidationStatus.NOT_APPLICABLE
        ]
        limitations.extend(
            f"DIMENSION_NOT_CONSOLIDATED:{item.dimension}"
            for item in applicable
            if item.consolidation_status is ConsolidationStatus.NOT_CONSOLIDATED
        )

        if not enough:
            confidence = min((item.confidence for item in applicable), key=_confidence_rank) if applicable else ScoreConfidence.UNAVAILABLE
            return Score(
                score_id=new_id("SCR"), audit_id=audit_id, dimension="OVERALL_READINESS", device=device,
                value=None, coverage=round(coverage, 6), confidence=confidence,
                consolidation_status=ConsolidationStatus.NOT_CONSOLIDATED,
                scoring_version=SCORING_VERSION, calculated_at=utc_now(), limitations=tuple(limitations),
            )

        if self.calibration_model is None:
            limitations.append("CALIBRATION_MODEL_UNAVAILABLE:SCORE-GEO-003")
            return Score(
                score_id=new_id("SCR"), audit_id=audit_id, dimension="OVERALL_READINESS", device=device,
                value=None, coverage=round(coverage, 6), confidence=ScoreConfidence.UNAVAILABLE,
                consolidation_status=ConsolidationStatus.NOT_CONSOLIDATED,
                scoring_version=SCORING_VERSION, calculated_at=utc_now(), limitations=tuple(limitations),
            )

        by_dimension = {item.dimension: item for item in dimensions}
        features: dict[str, float | None] = {}
        for feature in FEATURE_ORDER:
            item = by_dimension[feature]
            features[feature] = None if item.consolidation_status is ConsolidationStatus.NOT_APPLICABLE else float(item.value) / 100.0

        value = self.calibration_model.predict_probability(features) * 100.0
        dimension_confidence = min((item.confidence for item in applicable), key=_confidence_rank)
        calibration_confidence = ScoreConfidence(self.calibration_model.calibration_confidence)
        confidence = min((dimension_confidence, calibration_confidence), key=_confidence_rank)
        consolidation = (
            ConsolidationStatus.CONSOLIDATED
            if confidence in {ScoreConfidence.HIGH, ScoreConfidence.MEDIUM}
            else ConsolidationStatus.PARTIAL
        )
        limitations.extend(model_trace_limitations(self.calibration_model))
        return Score(
            score_id=new_id("SCR"), audit_id=audit_id, dimension="OVERALL_READINESS", device=device,
            value=round(value, 6), coverage=round(coverage, 6), confidence=confidence,
            consolidation_status=consolidation, scoring_version=SCORING_VERSION,
            calculated_at=utc_now(), limitations=tuple(limitations),
        )


def _confidence_rank(value: ScoreConfidence) -> int:
    return {
        ScoreConfidence.UNAVAILABLE: 0,
        ScoreConfidence.LOW: 1,
        ScoreConfidence.MEDIUM: 2,
        ScoreConfidence.HIGH: 3,
    }[value]
