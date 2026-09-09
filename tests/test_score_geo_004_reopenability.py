from __future__ import annotations

from datetime import datetime, timezone

from rasai.domain import DeviceContext, RuleExecution, RuleResult
from rasai.scoring import ConsolidationStatus
from rasai.scoring_v004 import ScoreGeo004Engine, _effective_v004_execution


_NOW = datetime(2026, 9, 9, 12, 0, tzinfo=timezone.utc)


def _absent_structured_data_execution() -> RuleExecution:
    return RuleExecution(
        rule_execution_id="REX-SD-ABSENT",
        audit_id="AUD-REOPEN",
        rule_id="BR-GEO-034",
        rule_version="1",
        page_id="PAGE-1",
        snapshot_id="SNAP-1",
        device=DeviceContext.MOBILE,
        result=RuleResult.WARNING,
        observed_value={"present": False, "syntax_valid": None},
        expected_condition="Structured Data is interpretable when present",
        evidence_ids=("EVD-SD-ABSENT",),
        executed_at=_NOW,
        error=None,
    )


def test_v004_reapplies_structured_data_absence_policy_after_reopen() -> None:
    persisted = _absent_structured_data_execution()

    result = ScoreGeo004Engine().score(
        audit_id=persisted.audit_id,
        executions=(persisted,),
        devices=(DeviceContext.MOBILE,),
    )

    structured = next(
        score
        for score in result.scores
        if score.device is DeviceContext.MOBILE and score.dimension == "STRUCTURED_DATA"
    )
    assert structured.value is None
    assert structured.consolidation_status is ConsolidationStatus.NOT_APPLICABLE

    # The source RuleExecution remains immutable evidence; interpretation belongs
    # to SCORE-GEO-004 and is reapplied whenever the persisted input is reopened.
    assert persisted.result is RuleResult.WARNING
    assert persisted.observed_value == {"present": False, "syntax_valid": None}


def test_v004_applicability_projection_is_idempotent() -> None:
    persisted = _absent_structured_data_execution()
    effective = _effective_v004_execution(persisted)
    second = _effective_v004_execution(effective)

    assert effective.result is RuleResult.NOT_APPLICABLE
    assert effective.observed_value["source_rule_result"] == "WARNING"
    assert second == effective
