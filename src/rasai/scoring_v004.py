"""Runtime engine for the canonical SCORE-GEO-004 contract."""
from __future__ import annotations

from dataclasses import replace

from rasai.domain import DeviceContext, RuleExecution
from rasai.score_geo_004 import FEATURE_ORDER, SCORING_VERSION
from rasai.scoring import DIMENSIONS, ScoringEngine, ScoringResult


if DIMENSIONS != FEATURE_ORDER:
    raise RuntimeError("SCORE-GEO-004 dimension contract must match scoring dimensions")


class ScoreGeo004Engine:
    """Thin version-aware adapter over the single canonical scoring engine.

    SCORE-GEO-004 used to duplicate the Overall calculation in this module and in
    ``scoring.py``.  The pre-release recalibration intentionally removes that
    split-brain risk: all dimension, Overall, Coverage, Confidence and critical
    gate behavior now comes from ``ScoringEngine``.
    """

    def score(
        self,
        *,
        audit_id: str,
        executions: tuple[RuleExecution, ...] | list[RuleExecution],
        devices: tuple[DeviceContext, ...] | list[DeviceContext] | None = None,
    ) -> ScoringResult:
        calculated = ScoringEngine().score(
            audit_id=audit_id,
            executions=executions,
            devices=devices,
        )
        dimensions = tuple(
            replace(score, scoring_version=SCORING_VERSION)
            for score in calculated.scores
        )
        overall = {
            device: replace(score, scoring_version=SCORING_VERSION)
            for device, score in calculated.overall_by_device.items()
        }
        return ScoringResult(dimensions, calculated.contributions, overall)
