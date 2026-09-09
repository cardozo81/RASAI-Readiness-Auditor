"""Runtime engine for the canonical SCORE-GEO-004 contract."""
from __future__ import annotations

from dataclasses import replace

from rasai.domain import DeviceContext, RuleExecution, RuleResult
from rasai.score_geo_004 import FEATURE_ORDER, SCORING_VERSION
from rasai.scoring import DIMENSIONS, ScoringEngine, ScoringResult


if DIMENSIONS != FEATURE_ORDER:
    raise RuntimeError("SCORE-GEO-004 dimension contract must match scoring dimensions")


def _effective_v004_execution(execution: RuleExecution) -> RuleExecution:
    """Apply version-owned applicability policy to a persisted RuleExecution.

    The source RuleExecution remains immutable evidence. SCORE-GEO-004 owns the
    interpretation that absence of Structured Data is not a universal readiness
    requirement, so BR-GEO-034 becomes NOT_APPLICABLE for scoring when its own
    persisted observation explicitly says Structured Data is absent.

    Keeping this policy in the version adapter is essential for reopenability:
    scoring the same persisted RuleExecutions later must reproduce the same result
    without relying on an in-memory transformation performed by the audit runner.
    """
    if execution.rule_id != "BR-GEO-034" or execution.result is RuleResult.NOT_APPLICABLE:
        return execution
    observed = execution.observed_value
    if not isinstance(observed, dict) or observed.get("present") is not False:
        return execution
    return replace(
        execution,
        result=RuleResult.NOT_APPLICABLE,
        observed_value={
            **observed,
            "reason": "STRUCTURED_DATA_ABSENT_NOT_UNIVERSAL_SARI_REQUIREMENT",
            "source_rule_result": execution.result.value,
        },
    )


class ScoreGeo004Engine:
    """Version-aware adapter over the single canonical scoring engine.

    SCORE-GEO-004 used to duplicate the Overall calculation in this module and in
    ``scoring.py``. The pre-release recalibration intentionally removes that
    split-brain risk: dimension, Overall, Coverage, Confidence and critical-gate
    behavior comes from ``ScoringEngine`` while version-specific applicability
    interpretation remains here so persisted RuleExecutions are reopenable.
    """

    def score(
        self,
        *,
        audit_id: str,
        executions: tuple[RuleExecution, ...] | list[RuleExecution],
        devices: tuple[DeviceContext, ...] | list[DeviceContext] | None = None,
    ) -> ScoringResult:
        effective_executions = tuple(_effective_v004_execution(item) for item in executions)
        calculated = ScoringEngine().score(
            audit_id=audit_id,
            executions=effective_executions,
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
