"""Additive SQLite persistence for M10 remediation groups and recommendations."""

from __future__ import annotations

from datetime import datetime
import json
import sqlite3

from rasai.domain import FindingDevice, Severity
from rasai.persistence import AuditWorkspace
from rasai.prioritization import (
    Effort,
    Impact,
    PriorityClass,
    PriorityConfidence,
    Recommendation,
    RemediationGroup,
)


class RecommendationPersistence:
    def __init__(self, workspace: AuditWorkspace) -> None:
        self._connection = sqlite3.connect(workspace.database)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._initialize()

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> "RecommendationPersistence":
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()

    def _initialize(self) -> None:
        with self._connection:
            self._connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS remediation_groups (
                    group_id TEXT PRIMARY KEY,
                    audit_id TEXT NOT NULL REFERENCES audits(audit_id) ON DELETE CASCADE,
                    rule_id TEXT NOT NULL,
                    root_cause TEXT NOT NULL,
                    affected_findings TEXT NOT NULL,
                    affected_pages TEXT NOT NULL,
                    devices TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    impact TEXT NOT NULL,
                    confidence TEXT NOT NULL,
                    effort TEXT NOT NULL,
                    priority_score REAL NOT NULL,
                    priority_class TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS recommendations (
                    recommendation_id TEXT PRIMARY KEY,
                    audit_id TEXT NOT NULL REFERENCES audits(audit_id) ON DELETE CASCADE,
                    finding_id TEXT REFERENCES findings(finding_id) ON DELETE CASCADE,
                    remediation_group_id TEXT REFERENCES remediation_groups(group_id) ON DELETE CASCADE,
                    device TEXT NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL,
                    impact TEXT NOT NULL,
                    effort TEXT NOT NULL,
                    confidence TEXT NOT NULL,
                    priority_score REAL NOT NULL,
                    priority_class TEXT NOT NULL,
                    status TEXT NOT NULL,
                    CHECK ((finding_id IS NOT NULL) != (remediation_group_id IS NOT NULL))
                );
                CREATE INDEX IF NOT EXISTS idx_remediation_groups_audit_priority
                    ON remediation_groups(audit_id, priority_score DESC);
                CREATE INDEX IF NOT EXISTS idx_recommendations_audit_priority
                    ON recommendations(audit_id, priority_score DESC);
                """
            )

    def add_group(self, *, audit_id: str, group: RemediationGroup) -> None:
        self._validate_finding_refs(audit_id=audit_id, finding_ids=group.affected_findings)
        with self._connection:
            self._connection.execute(
                "INSERT INTO remediation_groups VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    group.group_id,
                    audit_id,
                    group.rule_id,
                    group.root_cause,
                    json.dumps(list(group.affected_findings), ensure_ascii=False),
                    json.dumps(list(group.affected_pages), ensure_ascii=False),
                    json.dumps([device.value for device in group.devices], ensure_ascii=False),
                    group.severity.value,
                    group.impact.value,
                    group.confidence.value,
                    group.effort.value,
                    group.priority_score,
                    group.priority_class.value,
                ),
            )

    def add_recommendation(self, recommendation: Recommendation) -> None:
        with self._connection:
            self._connection.execute(
                "INSERT INTO recommendations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    recommendation.recommendation_id,
                    recommendation.audit_id,
                    recommendation.finding_id,
                    recommendation.remediation_group_id,
                    recommendation.device.value,
                    recommendation.title,
                    recommendation.description,
                    recommendation.impact.value,
                    recommendation.effort.value,
                    recommendation.confidence.value,
                    recommendation.priority_score,
                    recommendation.priority_class.value,
                    recommendation.status,
                ),
            )

    def get_group(self, group_id: str) -> RemediationGroup | None:
        row = self._connection.execute(
            "SELECT * FROM remediation_groups WHERE group_id = ?", (group_id,)
        ).fetchone()
        if row is None:
            return None
        return RemediationGroup(
            group_id=row["group_id"],
            rule_id=row["rule_id"],
            root_cause=row["root_cause"],
            affected_findings=tuple(json.loads(row["affected_findings"])),
            affected_pages=tuple(json.loads(row["affected_pages"])),
            devices=tuple(FindingDevice(value) for value in json.loads(row["devices"])),
            severity=Severity(row["severity"]),
            impact=Impact(row["impact"]),
            confidence=PriorityConfidence(row["confidence"]),
            effort=Effort(row["effort"]),
            priority_score=float(row["priority_score"]),
            priority_class=PriorityClass(row["priority_class"]),
        )

    def get_recommendation(self, recommendation_id: str) -> Recommendation | None:
        row = self._connection.execute(
            "SELECT * FROM recommendations WHERE recommendation_id = ?", (recommendation_id,)
        ).fetchone()
        if row is None:
            return None
        return Recommendation(
            recommendation_id=row["recommendation_id"],
            audit_id=row["audit_id"],
            finding_id=row["finding_id"],
            remediation_group_id=row["remediation_group_id"],
            device=FindingDevice(row["device"]),
            title=row["title"],
            description=row["description"],
            impact=Impact(row["impact"]),
            effort=Effort(row["effort"]),
            confidence=PriorityConfidence(row["confidence"]),
            priority_score=float(row["priority_score"]),
            priority_class=PriorityClass(row["priority_class"]),
            status=row["status"],
        )

    def list_groups(self, audit_id: str) -> tuple[RemediationGroup, ...]:
        rows = self._connection.execute(
            "SELECT group_id FROM remediation_groups WHERE audit_id = ? ORDER BY priority_score DESC, rule_id, group_id",
            (audit_id,),
        ).fetchall()
        return tuple(group for row in rows if (group := self.get_group(row["group_id"])) is not None)

    def list_recommendations(self, audit_id: str) -> tuple[Recommendation, ...]:
        rows = self._connection.execute(
            "SELECT recommendation_id FROM recommendations WHERE audit_id = ? ORDER BY priority_score DESC, recommendation_id",
            (audit_id,),
        ).fetchall()
        return tuple(
            recommendation
            for row in rows
            if (recommendation := self.get_recommendation(row["recommendation_id"])) is not None
        )

    def _validate_finding_refs(self, *, audit_id: str, finding_ids: tuple[str, ...]) -> None:
        if not finding_ids:
            raise sqlite3.IntegrityError("remediation group must reference at least one finding")
        placeholders = ",".join("?" for _ in finding_ids)
        rows = self._connection.execute(
            f"SELECT finding_id, audit_id FROM findings WHERE finding_id IN ({placeholders})",
            finding_ids,
        ).fetchall()
        found = {row["finding_id"]: row["audit_id"] for row in rows}
        missing = [finding_id for finding_id in finding_ids if finding_id not in found]
        if missing:
            raise sqlite3.IntegrityError(f"unknown finding references: {missing}")
        foreign = [finding_id for finding_id, owner in found.items() if owner != audit_id]
        if foreign:
            raise sqlite3.IntegrityError(f"finding references belong to another audit: {foreign}")
