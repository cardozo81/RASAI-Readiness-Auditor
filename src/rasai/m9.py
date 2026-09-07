"""Scoring + Reliability and BR-GEO-054 reproducibility."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from rasai.domain import EvidenceType, RuleExecution, RuleResult, new_id, utc_now
from rasai.evidence import EvidenceManager
from rasai.persistence import AuditPersistence, AuditWorkspace
from rasai.score_geo_003 import (
    CalibrationModel,
    SCORING_VERSION as SCORE_GEO_003_VERSION,
    resolve_model_path,
)
from rasai.score_geo_004 import LEGACY_SCORING_VERSION, SCORING_VERSION
from rasai.score_geo_004_reporting import write_score_geo_004_report
from rasai.scoring import ScoringEngine as LegacyScoringEngine, ScoringResult
from rasai.scoring_persistence import ScoringPersistence
from rasai.scoring_v003 import ScoreGeo003Engine
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
            workspace_root=workspace.root,
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
        rule_execution_id=new_id("REX"), audit_id=audit_id, rule_id="BR-GEO-054", rule_version="3",
        page_id=None, snapshot_id=None, device=None,
        result=RuleResult.PASS if integrity["reproducible"] else RuleResult.FAIL,
        observed_value=integrity,
        expected_condition=(
            f"scores are reconstructible from RuleExecutions, rule versions and {SCORING_VERSION} "
            "without website/AI re-execution or a calibration artifact"
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
    calibration_model: CalibrationModel | None = None,
    workspace_root: Path | None = None,
) -> dict[str, object]:
    original_versions = {
        score.scoring_version
        for score in (*original.scores, *original.overall_by_device.values())
    }
    if original_versions == {LEGACY_SCORING_VERSION}:
        recalculated = LegacyScoringEngine().score(
            audit_id=audit_id,
            executions=executions,
            devices=tuple(original.overall_by_device),
        )
        effective_version = LEGACY_SCORING_VERSION
    elif original_versions == {SCORE_GEO_003_VERSION}:
        recalculated = ScoreGeo003Engine(calibration_model=calibration_model).score(
            audit_id=audit_id,
            executions=executions,
            devices=tuple(original.overall_by_device),
        )
        effective_version = SCORE_GEO_003_VERSION
    else:
        recalculated = ScoreGeo004Engine().score(
            audit_id=audit_id,
            executions=executions,
            devices=tuple(original.overall_by_device),
        )
        effective_version = SCORING_VERSION

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
    persisted_ok = all(scoring.get_score(score.score_id) is not None for score in (*original.scores, *original.overall_by_device.values()))
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
        "scoring_version": effective_version,
        "calibration_model": calibration_model.model_version if effective_version == SCORE_GEO_003_VERSION and calibration_model else None,
        "calibration_dataset": calibration_model.dataset_version if effective_version == SCORE_GEO_003_VERSION and calibration_model else None,
        "calibration_model_path": str(resolve_model_path(workspace_root)) if effective_version == SCORE_GEO_003_VERSION else None,
        "overall_aggregation": "EQUAL_WEIGHT_APPLICABLE_DIMENSIONS_V1" if effective_version == SCORING_VERSION else None,
        "score_count": len(expected),
        "persisted_scores_reopenable": persisted_ok,
        "contributions_reopenable": contribution_refs_ok,
        "recalculation_equal": expected == actual,
    }
