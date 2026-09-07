from __future__ import annotations

from datetime import datetime, timezone

from rasai.domain import DeviceContext, RuleExecution, RuleResult
from rasai.score_geo_004 import OVERALL_AGGREGATION_VERSION, SCORING_VERSION
from rasai.scoring import ConsolidationStatus
from rasai.scoring_v004 import ScoreGeo004Engine

_NOW = datetime(2026, 9, 7, 18, 0, tzinfo=timezone.utc)


def _execution(rule_id: str, result: RuleResult) -> RuleExecution:
    return RuleExecution(
        rule_execution_id=f"REX-{rule_id}-{result.value}",
        audit_id="AUD-004",
        rule_id=rule_id,
        rule_version="1",
        page_id="P1",
        snapshot_id=None,
        device=DeviceContext.MOBILE,
        result=result,
        observed_value={},
        expected_condition="fixture",
        evidence_ids=("EVD-1",),
        executed_at=_NOW,
    )


def _complete_executions() -> tuple[RuleExecution, ...]:
    base = (
        _execution("BR-GEO-005", RuleResult.PASS),
        _execution("BR-GEO-011", RuleResult.PASS),
        _execution("BR-GEO-025", RuleResult.PASS),
        _execution("BR-GEO-028", RuleResult.PASS),
        _execution("BR-GEO-031", RuleResult.PASS),
        _execution("BR-GEO-038", RuleResult.PASS),
        _execution("BR-GEO-041", RuleResult.PASS),
        _execution("BR-GEO-045", RuleResult.PASS),
        _execution("BR-GEO-048", RuleResult.PASS),
    )
    structured = tuple(
        _execution(f"BR-GEO-{number:03d}", RuleResult.NOT_APPLICABLE)
        for number in range(34, 38)
    )
    return (*base, *structured)


def test_score_geo_004_consolidates_without_calibration_artifact() -> None:
    result = ScoreGeo004Engine().score(
        audit_id="AUD-004",
        executions=_complete_executions(),
        devices=(DeviceContext.MOBILE,),
    )
    overall = result.overall_by_device[DeviceContext.MOBILE]
    assert all(score.scoring_version == SCORING_VERSION for score in result.scores)
    assert overall.scoring_version == "SCORE-GEO-004"
    assert overall.value == 100.0
    assert overall.coverage == 1.0
    assert overall.confidence.value == "HIGH"
    assert overall.consolidation_status == ConsolidationStatus.CONSOLIDATED
    assert f"OVERALL_AGGREGATION:{OVERALL_AGGREGATION_VERSION}" in overall.limitations
    assert "EMPIRICAL_CALIBRATION:OPTIONAL_NOT_SCORE_INPUT" in overall.limitations
    assert "DIMENSION_NOT_APPLICABLE:STRUCTURED_DATA" in overall.limitations


def test_score_geo_004_keeps_missing_dimension_as_not_consolidated() -> None:
    executions = tuple(
        item for item in _complete_executions()
        if item.rule_id != "BR-GEO-048"
    )
    result = ScoreGeo004Engine().score(
        audit_id="AUD-004",
        executions=executions,
        devices=(DeviceContext.MOBILE,),
    )
    overall = result.overall_by_device[DeviceContext.MOBILE]
    assert overall.value is None
    assert overall.consolidation_status == ConsolidationStatus.NOT_CONSOLIDATED
    assert "DIMENSION_NOT_CONSOLIDATED:INTENT_COVERAGE" in overall.limitations


def test_score_geo_004_is_deterministic() -> None:
    first = ScoreGeo004Engine().score(
        audit_id="AUD-004",
        executions=_complete_executions(),
        devices=(DeviceContext.MOBILE,),
    ).overall_by_device[DeviceContext.MOBILE]
    second = ScoreGeo004Engine().score(
        audit_id="AUD-004",
        executions=_complete_executions(),
        devices=(DeviceContext.MOBILE,),
    ).overall_by_device[DeviceContext.MOBILE]
    assert (first.value, first.coverage, first.confidence, first.consolidation_status) == (
        second.value,
        second.coverage,
        second.confidence,
        second.consolidation_status,
    )
