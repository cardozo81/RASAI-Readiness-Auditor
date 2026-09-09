"""Scoring + Reliability and BR-GEO-054 reproducibility."""

from __future__ import annotations

from dataclasses import dataclass

from rasai.content_value import materialize_content_value_executions
from rasai.domain import EvidenceType, RuleExecution, RuleResult, new_id, utc_now
from rasai.evidence import EvidenceManager
from rasai.persistence import AuditPersistence, AuditWorkspace
from rasai.score_geo_004 import OVERALL_AGGREGATION_VERSION, SCORING_VERSION
from rasai.score_geo_004_reporting import write_score_geo_004_report
from rasai.scoring import ScoringResult
from rasai.scoring_persistence import ScoringPersistence
from rasai.scoring_v004 import ScoreGeo004Engine


@dataclass(frozen=True, slots=True)
class M9ExecutionResult:
    score_ids: tuple[str, ...]
    contribution_ids: tuple[str, ...]
    overall_score_ids: tuple[str, ...]
    integrity_rule_execution_id: str


def execute_m9(
    *,
    audit_id: str,
    rule_execution_ids: tuple[str, ...],
    persistence: AuditPersistence,
    workspace: AuditWorkspace,
) -> M9ExecutionResult:
    executions: list[RuleExecution] = []
    for execution_id in dict.fromkeys(rule_execution_ids):
        execution = persistence.rule_executions.get(execution_id)
        if execution is None:
            raise ValueError(f"RuleExecution is not re-openable for scoring: {execution_id}")
        if execution.audit_id != audit_id:
            raise ValueError(f"RuleExecution belongs to another audit: {execution_id}")
        executions.append(execution)

    # CONTENT_VALUE is intentionally materialized immediately before scoring from
    # already-preserved main-content evidence.  This keeps the rule evidence-bound,
    # deterministic and independent from an optional LLM provider.  Unknown local
    # evidence reduces Coverage instead of being converted into a website failure.
    content_value = materialize_content_value_executions(
        audit_id=audit_id,
        source_executions=tuple(executions),
        persistence=persistence,
        workspace=workspace,
    )
    for execution_id in content_value.rule_execution_ids:
        execution = persistence.rule_executions.get(execution_id)
        if execution is None:
            raise ValueError(f"Content Value RuleExecution is not re-openable: {execution_id}")
        executions.append(execution)

    engine = ScoreGeo004Engine()
    active_devices = tuple(dict.fromkeys(
        execution.device for execution in executions if execution.device is not None
    ))
    calculated = engine.score(
        audit_id=audit_id,
        executions=executions,
        devices=active_devices or None,
    )
    score_ids: list[str] = []
    contribution_ids: list[str] = []
    with ScoringPersistence(workspace) as scoring:
        for score in calculated.scores:
            scoring.add_score(score)
            score_ids.append(score.score_id)
        for score in calculated.overall_by_device.values():
            scoring.add_score(score)
        for contribution in calculated.contributions:
            scoring.add_contribution(contribution)
            contribution_ids.append(contribution.contribution_id)

        integrity = _reproducibility_check(
            audit_id=audit_id,
            executions=tuple(executions),
            original=calculated,
            scoring=scoring,
        )

    manager = EvidenceManager(persistence)
    evidence = manager.record(
        audit_id=audit_id,
        page_id=None,
        snapshot_id=None,
        device=None,
        evidence_type=EvidenceType.COMPARISON,
        source="scoring:BR-GEO-054",
        observed_value=integrity,
    )
    integrity_execution = RuleExecution(
        rule_execution_id=new_id("REX"), audit_id=audit_id, rule_id="BR-GEO-054", rule_version="4",
        page_id=None, snapshot_id=None, device=None,
        result=RuleResult.PASS if integrity["reproducible"] else RuleResult.FAIL,
        observed_value=integrity,
        expected_condition=(
            f"scores are reconstructible from RuleExecutions, rule versions and {SCORING_VERSION} "
            "without website/AI re-execution or external calibration"
        ),
        evidence_ids=(evidence.evidence_id,), executed_at=utc_now(), error=None,
    )
    persistence.rule_executions.add(integrity_execution)
    write_score_geo_004_report(audit_id=audit_id, workspace=workspace)

    return M9ExecutionResult(
        score_ids=tuple(score_ids),
        contribution_ids=tuple(contribution_ids),
        overall_score_ids=tuple(score.score_id for score in calculated.overall_by_device.values()),
        integrity_rule_execution_id=integrity_execution.rule_execution_id,
    )


def _reproducibility_check(
    *,
    audit_id: str,
    executions: tuple[RuleExecution, ...],
    original: ScoringResult,
    scoring: ScoringPersistence,
) -> dict[str, object]:
    recalculated = ScoreGeo004Engine().score(
        audit_id=audit_id,
        executions=executions,
        devices=tuple(original.overall_by_device),
    )

    expected = {
        (score.dimension, score.device.value): (
            score.value, score.coverage, score.confidence.value,
            score.consolidation_status.value, score.scoring_version,
        )
        for score in (*original.scores, *original.overall_by_device.values())
    }
    actual = {
        (score.dimension, score.device.value): (
            score.value, score.coverage, score.confidence.value,
            score.consolidation_status.value, score.scoring_version,
        )
        for score in (*recalculated.scores, *recalculated.overall_by_device.values())
    }
    persisted_ok = all(
        scoring.get_score(score.score_id) is not None
        for score in (*original.scores, *original.overall_by_device.values())
    )
    contribution_refs_ok = all(
        scoring.list_contributions(score.score_id) == tuple(sorted(
            (
                contribution
                for contribution in original.contributions
                if contribution.score_id == score.score_id
            ),
            key=lambda contribution: contribution.contribution_id,
        ))
        for score in original.scores
    )
    return {
        "reproducible": expected == actual and persisted_ok and contribution_refs_ok,
        "scoring_version": SCORING_VERSION,
        "overall_aggregation": OVERALL_AGGREGATION_VERSION,
        "score_count": len(expected),
        "persisted_scores_reopenable": persisted_ok,
        "contributions_reopenable": contribution_refs_ok,
        "recalculation_equal": expected == actual,
        "content_value_baseline": "CONTENT-VALUE-BASELINE-001",
    }
