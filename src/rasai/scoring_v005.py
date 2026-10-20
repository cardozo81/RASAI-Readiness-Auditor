"""SCORE-GEO-005: optional SEO omission is not an indexing failure.

This version changes scoring applicability, not the persisted M5 evidence.
Old SCORE-GEO-004 replays retain the original adapter and interpretation.
Neither version issues HTTP calls or rewrites an AUD.
"""
from __future__ import annotations

from dataclasses import replace

from rasai.domain import DeviceContext, RuleExecution, RuleResult
from rasai.optional_seo_policy import classify_seo_evidence
from rasai.score_geo import SCORING_VERSION
from rasai.scoring import ScoringResult
from rasai.scoring_v004 import ScoreGeo004Engine

_OPTIONAL_RULES = frozenset({"BR-GEO-003", "BR-GEO-013", "BR-GEO-017"})
_OPTIONAL_POLICY = "OPTIONAL_SEO_OMISSION_NOT_APPLICABLE_V1"


def _effective_v005_execution(execution: RuleExecution) -> RuleExecution:
    """Translate only an evidenced optional absence for score computation.

    UNKNOWN and transport errors are not absence. Invalid published sitemap,
    conflicting canonical and crawler access failures remain fully evaluated.
    No PASS credit is awarded for an absent optional declaration.
    """
    if (
        execution.rule_id not in _OPTIONAL_RULES
        or execution.result is not RuleResult.WARNING
        or classify_seo_evidence(execution.rule_id, execution.observed_value)
        != "OPTIONAL_ABSENCE"
    ):
        return execution
    return replace(
        execution,
        result=RuleResult.NOT_APPLICABLE,
        observed_value={
            **execution.observed_value,
            "score_policy": _OPTIONAL_POLICY,
            "source_rule_result": execution.result.value,
        },
    )


class ScoreGeo005Engine:
    """Versioned, replayable scorer using the unchanged weighting engine.

    Only the three optional absence cases are reclassified. The 004 scorer
    preserves structured-data applicability; 005 assigns its own result
    version to all dimensions and Overall without modifying source records.
    """

    def score(
        self,
        *,
        audit_id: str,
        executions: tuple[RuleExecution, ...] | list[RuleExecution],
        devices: tuple[DeviceContext, ...] | list[DeviceContext] | None = None,
    ) -> ScoringResult:
        effective = tuple(_effective_v005_execution(row) for row in executions)
        previous = ScoreGeo004Engine().score(
            audit_id=audit_id, executions=effective, devices=devices,
        )
        return ScoringResult(
            tuple(replace(score, scoring_version=SCORING_VERSION)
                  for score in previous.scores),
            previous.contributions,
            {
                device: replace(score, scoring_version=SCORING_VERSION)
                for device, score in previous.overall_by_device.items()
            },
        )
