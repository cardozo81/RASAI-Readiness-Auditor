"""M10 - Prioritization + deterministic recommendations."""

from __future__ import annotations

from dataclasses import dataclass
import sqlite3

from rasai.domain import Finding
from rasai.persistence import AuditPersistence, AuditWorkspace
from rasai.prioritization import PriorityEngine
from rasai.recommendation_persistence import RecommendationPersistence


@dataclass(frozen=True, slots=True)
class M10ExecutionResult:
    remediation_group_ids: tuple[str, ...]
    recommendation_ids: tuple[str, ...]


def execute_m10(
    *,
    audit_id: str,
    finding_ids: tuple[str, ...],
    persistence: AuditPersistence,
    workspace: AuditWorkspace,
) -> M10ExecutionResult:
    findings: list[Finding] = []
    for finding_id in dict.fromkeys(finding_ids):
        finding = persistence.findings.get(finding_id)
        if finding is None:
            raise ValueError(f"Finding is not re-openable for prioritization: {finding_id}")
        if finding.audit_id != audit_id:
            raise ValueError(f"Finding belongs to another audit: {finding_id}")
        findings.append(finding)

    total_pages = _count_pages(workspace=workspace, audit_id=audit_id)
    prioritized = PriorityEngine().prioritize(
        audit_id=audit_id,
        findings=findings,
        total_pages=total_pages,
    )

    group_ids: list[str] = []
    recommendation_ids: list[str] = []
    with RecommendationPersistence(workspace) as repository:
        for group in prioritized.groups:
            repository.add_group(audit_id=audit_id, group=group)
            group_ids.append(group.group_id)
        for recommendation in prioritized.recommendations:
            repository.add_recommendation(recommendation)
            recommendation_ids.append(recommendation.recommendation_id)

        persisted_groups = {group.group_id: group for group in repository.list_groups(audit_id)}
        expected_groups = {group.group_id: group for group in prioritized.groups}
        if persisted_groups != expected_groups:
            raise RuntimeError("persisted remediation groups are not reproducible")

        persisted_recommendations = {
            recommendation.recommendation_id: recommendation
            for recommendation in repository.list_recommendations(audit_id)
        }
        expected_recommendations = {
            recommendation.recommendation_id: recommendation
            for recommendation in prioritized.recommendations
        }
        if persisted_recommendations != expected_recommendations:
            raise RuntimeError("persisted recommendations are not reproducible")

    return M10ExecutionResult(
        remediation_group_ids=tuple(group_ids),
        recommendation_ids=tuple(recommendation_ids),
    )


def _count_pages(*, workspace: AuditWorkspace, audit_id: str) -> int:
    connection = sqlite3.connect(workspace.database)
    try:
        row = connection.execute("SELECT COUNT(*) FROM pages WHERE audit_id = ?", (audit_id,)).fetchone()
        return int(row[0]) if row is not None else 0
    finally:
        connection.close()
