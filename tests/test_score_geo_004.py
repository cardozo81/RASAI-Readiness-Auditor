from __future__ import annotations

from datetime import datetime, timezone

from rasai.domain import DeviceContext, RuleExecution, RuleResult
from rasai.score_geo_004 import OVERALL_AGGREGATION_VERSION, SCORING_VERSION
from rasai.scoring import ConsolidationStatus
from rasai.scoring_v004 import ScoreGeo004Engine

_NOW = datetime(2026, 9, 7, 18, 0, tzinfo=timezone.utc)


def _execution(
    rule_id: str,
    result: RuleResult,
    *,
    page_id: str | None = "P1",
    suffix: str = "",
) -> RuleExecution:
    scope = page_id or "GLOBAL"
    return RuleExecution(
        rule_execution_id=f"REX-{rule_id}-{result.value}-{scope}-{suffix}",
        audit_id="AUD-004",
        rule_id=rule_id,
        rule_version="1",
        page_id=page_id,
        snapshot_id=None,
        device=DeviceContext.MOBILE if page_id is not None else None,
        result=result,
        observed_value={},
        expected_condition="fixture",
        evidence_ids=(f"EVD-{rule_id}-{scope}-{suffix}",),
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
        _execution("BR-GEO-057", RuleResult.PASS),
    )
    structured = tuple(
        _execution(f"BR-GEO-{number:03d}", RuleResult.NOT_APPLICABLE)
        for number in range(34, 38)
    )
    return (*base, *structured)


def test_score_geo_004_consolidates_without_external_validation_artifact() -> None:
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
    assert "EMPIRICAL_VALIDATION:NOT_SCORE_INPUT" in overall.limitations
    assert "DIMENSION_NOT_APPLICABLE:STRUCTURED_DATA" in overall.limitations
    assert "READINESS_STATUS:READY" in overall.limitations


def test_noncritical_missing_dimension_reduces_coverage_without_erasing_overall() -> None:
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
    assert overall.value == 100.0
    assert overall.coverage < 1.0
    assert overall.coverage >= 0.80
    assert "DIMENSION_MEASUREMENT_LIMITED:INTENT_COVERAGE" in overall.limitations


def test_missing_critical_dimension_blocks_consolidation() -> None:
    executions = tuple(
        item for item in _complete_executions()
        if item.rule_id != "BR-GEO-011"
    )
    result = ScoreGeo004Engine().score(
        audit_id="AUD-004",
        executions=executions,
        devices=(DeviceContext.MOBILE,),
    )
    overall = result.overall_by_device[DeviceContext.MOBILE]
    assert overall.value is not None
    assert overall.consolidation_status == ConsolidationStatus.NOT_CONSOLIDATED
    assert "CRITICAL_DIMENSION_NOT_CONSOLIDATED:INDEXABILITY" in overall.limitations


def test_page_count_does_not_change_global_group_weight() -> None:
    def audit_with_pages(count: int) -> tuple[RuleExecution, ...]:
        page_access = tuple(
            _execution("BR-GEO-005", RuleResult.PASS, page_id=f"P{index}", suffix=str(index))
            for index in range(1, count + 1)
        )
        robots = (_execution("BR-GEO-017", RuleResult.WARNING, page_id=None),)
        remaining = tuple(
            item for item in _complete_executions()
            if item.rule_id != "BR-GEO-005"
        )
        return (*page_access, *robots, *remaining)

    one = ScoreGeo004Engine().score(
        audit_id="AUD-004",
        executions=audit_with_pages(1),
        devices=(DeviceContext.MOBILE,),
    )
    hundred = ScoreGeo004Engine().score(
        audit_id="AUD-004",
        executions=audit_with_pages(100),
        devices=(DeviceContext.MOBILE,),
    )
    one_discovery = next(score for score in one.scores if score.dimension == "DISCOVERY_ACCESS")
    hundred_discovery = next(score for score in hundred.scores if score.dimension == "DISCOVERY_ACCESS")
    assert one_discovery.value == hundred_discovery.value
    assert one_discovery.coverage == hundred_discovery.coverage == 1.0
    assert one.overall_by_device[DeviceContext.MOBILE].value == hundred.overall_by_device[DeviceContext.MOBILE].value


def test_deterministic_result_has_precedence_over_ai_corroboration() -> None:
    executions = (
        *_complete_executions(),
        _execution("BR-GEO-017", RuleResult.PASS, page_id=None),
        _execution("BR-GEO-056", RuleResult.FAIL, page_id=None),
    )
    result = ScoreGeo004Engine().score(
        audit_id="AUD-004",
        executions=executions,
        devices=(DeviceContext.MOBILE,),
    )
    discovery = next(score for score in result.scores if score.dimension == "DISCOVERY_ACCESS")
    assert discovery.value == 100.0
    robots = [
        contribution
        for contribution in result.contributions
        if contribution.dimension == "DISCOVERY_ACCESS"
        and contribution.scoring_group == "ROBOTS"
    ]
    assert len(robots) == 1
    assert robots[0].rule_id == "BR-GEO-017"
    assert robots[0].result == RuleResult.PASS


def test_critical_gate_is_separate_from_numeric_score() -> None:
    executions = tuple(
        _execution("BR-GEO-011", RuleResult.FAIL)
        if item.rule_id == "BR-GEO-011"
        else item
        for item in _complete_executions()
    )
    result = ScoreGeo004Engine().score(
        audit_id="AUD-004",
        executions=executions,
        devices=(DeviceContext.MOBILE,),
    )
    overall = result.overall_by_device[DeviceContext.MOBILE]
    assert overall.value is not None
    assert overall.value < 100.0
    assert "CRITICAL_GATE:INDEXABILITY:BLOCKED" in overall.limitations
    assert "READINESS_STATUS:BLOCKED" in overall.limitations
    # Quality can be bad while measurement is still complete and reproducible.
    assert overall.consolidation_status == ConsolidationStatus.CONSOLIDATED


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
    assert (first.value, first.coverage, first.confidence, first.consolidation_status, first.limitations) == (
        second.value,
        second.coverage,
        second.confidence,
        second.consolidation_status,
        second.limitations,
    )
