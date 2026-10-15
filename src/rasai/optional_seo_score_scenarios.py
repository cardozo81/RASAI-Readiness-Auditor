"""#602: strictly offline SCORE-GEO-004 sensitivity scenarios, not a policy migration.

An alternate disposition for optional SEO absence is simulated only in memory.
The canonical SCORE-GEO-004 score, RuleExecution, audit.db and all history remain
unchanged. Scenarios are not a prediction of a future scoring contract.
"""
from __future__ import annotations

from dataclasses import replace
from typing import Any, Iterable

from rasai.domain import DeviceContext, RuleExecution, RuleResult
from rasai.optional_seo_policy import classify_seo_evidence
from rasai.scoring_v004 import ScoreGeo004Engine

_MAX_RULES = 10000
_OPTIONAL_IDS = frozenset({"BR-GEO-003", "BR-GEO-013", "BR-GEO-017"})
_VARIANTS = {
    "CANONICAL_SCORE_GEO_004": None,
    "SENSITIVITY_OPTIONAL_ABSENCE_PASS": RuleResult.PASS,
    "SENSITIVITY_OPTIONAL_ABSENCE_NOT_APPLICABLE": RuleResult.NOT_APPLICABLE,
}


def _snapshot(result: Any, device: DeviceContext) -> dict[str, Any]:
    scores = {
        score.dimension: {
            "value": score.value,
            "coverage": score.coverage,
            "confidence": str(score.confidence),
            "consolidation_status": str(score.consolidation_status),
        }
        for score in result.scores if score.device is device
    }
    overall = result.overall_by_device[device]
    scores["OVERALL_READINESS"] = {
        "value": overall.value,
        "coverage": overall.coverage,
        "confidence": str(overall.confidence),
        "consolidation_status": str(overall.consolidation_status),
        "readiness_limitations": [
            str(item) for item in overall.limitations
            if str(item).startswith(("READINESS_STATUS:", "CRITICAL_GATE:"))
        ],
    }
    return scores


def preview_optional_seo_policy_sensitivity(
    audit_id: str,
    executions: Iterable[RuleExecution],
    *,
    device: DeviceContext,
) -> dict[str, Any]:
    """Re-score independent *in-memory* scenarios using the old engine.

    No persisted audit data is loaded, modified or generated. The old engine
    enforces the same dimensional weights in each scenario; NOT_APPLICABLE
    changes eligible denominators, so a delta is not simple point addition.
    """
    if not isinstance(audit_id, str) or not audit_id.startswith("AUD-"):
        raise ValueError("canonical AUD identity required")
    if not isinstance(device, DeviceContext):
        raise ValueError("one explicit scoring device required")
    source = tuple(executions)
    if len(source) > _MAX_RULES or not source:
        raise ValueError("bounded nonempty source RuleExecutions required")
    keys: set[str] = set()
    for row in source:
        if not isinstance(row, RuleExecution) or row.audit_id != audit_id:
            raise ValueError("source execution type or audit scope mismatch")
        if not row.rule_execution_id or row.rule_execution_id in keys:
            raise ValueError("ambiguous physical RuleExecution identifier")
        keys.add(row.rule_execution_id)

    optional_ids = {
        row.rule_execution_id
        for row in source
        if row.rule_id in _OPTIONAL_IDS
        and row.result is RuleResult.WARNING
        and classify_seo_evidence(row.rule_id, row.observed_value) == "OPTIONAL_ABSENCE"
    }
    scenarios: dict[str, dict[str, Any]] = {}
    for name, substitute in _VARIANTS.items():
        transformed = tuple(
            replace(row, result=substitute)
            if substitute is not None and row.rule_execution_id in optional_ids
            else row
            for row in source
        )
        calculated = ScoreGeo004Engine().score(
            audit_id=audit_id, executions=transformed, devices=(device,),
        )
        scenarios[name] = _snapshot(calculated, device)
    return {
        "contract": "RASAI-SEO-POLICY-SENSITIVITY-602-001",
        "canonical_scoring_version": "SCORE-GEO-004",
        "status": "EXPLORATORY_NOT_AUTHORIZED_FOR_PUBLISHED_SARI",
        "optional_absence_executions": len(optional_ids),
        "source_rule_executions": len(source),
        "scenarios": scenarios,
        "provider_requests": 0,
        "audit_writes": 0,
        "new_scoring_version_approved": False,
        "caveat": (
            "PASS and NOT_APPLICABLE are only opposite policy sensitivity "
            "boundaries, not an endorsed Google or RASAi normative interpretation. "
            "Gates, coverage, confidence and normalized weights must be considered "
            "together; this result is not a replacement public SARI."
        ),
    }


__all__ = ["preview_optional_seo_policy_sensitivity"]
