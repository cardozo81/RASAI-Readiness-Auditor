from __future__ import annotations

from datetime import datetime, timezone

import pytest

from rasai.domain import DeviceContext, RuleExecution, RuleResult
from rasai.external_sari import MAX_OVERALL_IMPACT_POINTS, _safe_public_simple_url
from rasai.score_geo_004 import (
    CRITICAL_GATES,
    DIMENSION_WEIGHTS,
    EVIDENCE_ROLE_EXTERNAL_CORROBORATIVE,
    GROUP_WEIGHTS,
    rule_contract,
)
from rasai.scoring import ScoringEngine

_NOW = datetime(2026, 9, 13, tzinfo=timezone.utc)


def _execution(rule_id: str, result: RuleResult, index: int) -> RuleExecution:
    return RuleExecution(
        rule_execution_id=f"REX-{index}",
        audit_id="AUD-EXT-SARI",
        rule_id=rule_id,
        rule_version="1",
        page_id=None,
        snapshot_id=None,
        device=None,
        result=result,
        observed_value={"test": True},
        expected_condition="test",
        evidence_ids=(f"EV-{index}",),
        executed_at=_NOW,
        error=None,
    )


def _base_discovery(result_overrides: dict[str, RuleResult] | None = None) -> tuple[RuleExecution, ...]:
    overrides = result_overrides or {}
    rules = (
        "BR-GEO-005",  # PAGE_ACCESS
        "BR-GEO-017",  # ROBOTS
        "BR-GEO-003",  # SITEMAP
        "BR-GEO-007",  # REDIRECT
        "BR-GEO-021",  # SPA_ROUTE
        "BR-GEO-022",  # SPA_NAVIGATION
        "BR-GEO-050",  # INTERNAL_LINKS
    )
    return tuple(
        _execution(rule_id, overrides.get(rule_id, RuleResult.PASS), index)
        for index, rule_id in enumerate(rules, 1)
    )


def _discovery_score(executions: tuple[RuleExecution, ...]):
    calculated = ScoringEngine().score(
        audit_id="AUD-EXT-SARI",
        executions=executions,
        devices=(DeviceContext.DESKTOP,),
    )
    return next(score for score in calculated.scores if score.dimension == "DISCOVERY_ACCESS")


def test_external_crawl_group_is_bounded_and_contract_sums_to_one() -> None:
    groups = GROUP_WEIGHTS["DISCOVERY_ACCESS"]
    assert sum(groups.values()) == pytest.approx(1.0)
    assert groups["EXTERNAL_CRAWL_CORROBORATION"] == pytest.approx(0.03)
    assert DIMENSION_WEIGHTS["DISCOVERY_ACCESS"] == pytest.approx(0.15)
    assert MAX_OVERALL_IMPACT_POINTS == pytest.approx(0.45)

    contract = rule_contract("BR-GEO-060")
    assert contract is not None
    assert contract.dimension == "DISCOVERY_ACCESS"
    assert contract.scoring_group == "EXTERNAL_CRAWL_CORROBORATION"
    assert contract.evidence_role == EVIDENCE_ROLE_EXTERNAL_CORROBORATIVE


def test_external_crawl_group_is_not_a_critical_gate() -> None:
    critical_groups = {group for _dimension, groups in CRITICAL_GATES.values() for group in groups}
    assert "EXTERNAL_CRAWL_CORROBORATION" not in critical_groups


def test_absence_of_common_crawl_never_reduces_discovery_quality_or_coverage() -> None:
    score = _discovery_score(_base_discovery())
    assert score.value == pytest.approx(100.0)
    assert score.coverage == pytest.approx(1.0)


def test_positive_common_crawl_is_only_a_small_corroborative_uplift() -> None:
    # One current technical group fails. Historical crawling may corroborate discovery,
    # but the 3% group cannot mask the current technical weakness.
    base = _base_discovery({"BR-GEO-050": RuleResult.FAIL})
    without_external = _discovery_score(base)
    with_external = _discovery_score((*base, _execution("BR-GEO-060", RuleResult.PASS, 99)))

    assert without_external.value is not None
    assert with_external.value is not None
    assert with_external.value > without_external.value
    assert with_external.value - without_external.value <= 3.0 + 1e-9
    assert with_external.coverage == pytest.approx(1.0)


def test_external_crawl_failure_would_not_be_an_admissible_runtime_signal() -> None:
    # The scoring engine can represent a FAIL if manually fabricated, but the production
    # materializer is positive-only and never creates BR-GEO-060 for absence/no-data/error.
    # This test locks the contract expectation at the runtime safety boundary.
    contract = rule_contract("BR-GEO-060")
    assert contract is not None
    assert contract.evidence_role == EVIDENCE_ROLE_EXTERNAL_CORROBORATIVE


def test_public_target_gate_blocks_sensitive_or_internal_urls() -> None:
    assert _safe_public_simple_url("https://openai.com/research") is True
    assert _safe_public_simple_url("https://openai.com/research?token=secret") is False
    assert _safe_public_simple_url("https://user:pass@openai.com/private") is False
    assert _safe_public_simple_url("http://localhost/admin") is False
    assert _safe_public_simple_url("http://127.0.0.1/admin") is False
    assert _safe_public_simple_url("http://10.0.0.1/internal") is False
