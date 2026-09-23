"""Additive SQLite persistence for M7 semantic domain entities."""

from __future__ import annotations

from dataclasses import dataclass
import json
import sqlite3
from typing import Any

from rasai.domain import RuleResult
from rasai.persistence import AuditWorkspace
from rasai.semantic import EntityType


@dataclass(frozen=True, slots=True)
class EntityObservation:
    entity_observation_id: str
    snapshot_id: str
    name: str
    entity_type: EntityType
    confidence: float
    evidence_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SemanticAssessment:
    assessment_id: str
    snapshot_id: str
    assessment_type: str
    result: RuleResult
    confidence: float
    evidence_ids: tuple[str, ...]
    prompt_id: str
    prompt_version: str
    provider: str
    model: str | None
    configuration_version: str
    reasoning_summary: str


def _dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _load(value: str) -> Any:
    return json.loads(value)


class SemanticPersistence:
    """Persist M7 entities in the same audit.db without coupling provider code to SQLite."""

    def __init__(self, workspace: AuditWorkspace) -> None:
        self._connection = sqlite3.connect(workspace.database)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._initialize()

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> "SemanticPersistence":
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()

    def _initialize(self) -> None:
        with self._connection:
            self._connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS entity_observations (
                    entity_observation_id TEXT PRIMARY KEY,
                    snapshot_id TEXT NOT NULL REFERENCES page_snapshots(snapshot_id) ON DELETE CASCADE,
                    name TEXT NOT NULL,
                    entity_type TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    evidence_ids TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS semantic_assessments (
                    assessment_id TEXT PRIMARY KEY,
                    snapshot_id TEXT NOT NULL REFERENCES page_snapshots(snapshot_id) ON DELETE CASCADE,
                    assessment_type TEXT NOT NULL,
                    result TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    evidence_ids TEXT NOT NULL,
                    prompt_id TEXT NOT NULL,
                    prompt_version TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    model TEXT,
                    configuration_version TEXT NOT NULL,
                    reasoning_summary TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_entity_observations_snapshot
                    ON entity_observations(snapshot_id);
                CREATE INDEX IF NOT EXISTS idx_semantic_assessments_snapshot
                    ON semantic_assessments(snapshot_id);
                """
            )

    def add_entity(self, observation: EntityObservation) -> None:
        self._validate_snapshot_evidence(observation.snapshot_id, observation.evidence_ids)
        if not 0 <= observation.confidence <= 1:
            raise ValueError("entity confidence must be between 0 and 1")
        with self._connection:
            self._connection.execute(
                "INSERT INTO entity_observations VALUES (?, ?, ?, ?, ?, ?)",
                (
                    observation.entity_observation_id,
                    observation.snapshot_id,
                    observation.name,
                    observation.entity_type.value,
                    observation.confidence,
                    _dump(list(observation.evidence_ids)),
                ),
            )

    def get_entity(self, entity_observation_id: str) -> EntityObservation | None:
        row = self._connection.execute(
            "SELECT * FROM entity_observations WHERE entity_observation_id = ?",
            (entity_observation_id,),
        ).fetchone()
        if row is None:
            return None
        return EntityObservation(
            entity_observation_id=row["entity_observation_id"],
            snapshot_id=row["snapshot_id"],
            name=row["name"],
            entity_type=EntityType(row["entity_type"]),
            confidence=float(row["confidence"]),
            evidence_ids=tuple(_load(row["evidence_ids"])),
        )

    def list_entities(self, snapshot_id: str) -> tuple[EntityObservation, ...]:
        rows = self._connection.execute(
            "SELECT * FROM entity_observations WHERE snapshot_id = ? ORDER BY entity_observation_id",
            (snapshot_id,),
        ).fetchall()
        return tuple(
            EntityObservation(
                entity_observation_id=row["entity_observation_id"],
                snapshot_id=row["snapshot_id"],
                name=row["name"],
                entity_type=EntityType(row["entity_type"]),
                confidence=float(row["confidence"]),
                evidence_ids=tuple(_load(row["evidence_ids"])),
            )
            for row in rows
        )

    def add_assessment(self, assessment: SemanticAssessment) -> None:
        self._validate_snapshot_evidence(assessment.snapshot_id, assessment.evidence_ids)
        if not 0 <= assessment.confidence <= 1:
            raise ValueError("assessment confidence must be between 0 and 1")
        with self._connection:
            self._connection.execute(
                "INSERT INTO semantic_assessments VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    assessment.assessment_id,
                    assessment.snapshot_id,
                    assessment.assessment_type,
                    assessment.result.value,
                    assessment.confidence,
                    _dump(list(assessment.evidence_ids)),
                    assessment.prompt_id,
                    assessment.prompt_version,
                    assessment.provider,
                    assessment.model,
                    assessment.configuration_version,
                    assessment.reasoning_summary,
                ),
            )

    def get_assessment(self, assessment_id: str) -> SemanticAssessment | None:
        row = self._connection.execute(
            "SELECT * FROM semantic_assessments WHERE assessment_id = ?",
            (assessment_id,),
        ).fetchone()
        if row is None:
            return None
        return self._map_assessment(row)

    def list_assessments(self, snapshot_id: str) -> tuple[SemanticAssessment, ...]:
        rows = self._connection.execute(
            "SELECT * FROM semantic_assessments WHERE snapshot_id = ? ORDER BY assessment_type, assessment_id",
            (snapshot_id,),
        ).fetchall()
        return tuple(self._map_assessment(row) for row in rows)

    @staticmethod
    def _map_assessment(row: sqlite3.Row) -> SemanticAssessment:
        return SemanticAssessment(
            assessment_id=row["assessment_id"],
            snapshot_id=row["snapshot_id"],
            assessment_type=row["assessment_type"],
            result=RuleResult(row["result"]),
            confidence=float(row["confidence"]),
            evidence_ids=tuple(_load(row["evidence_ids"])),
            prompt_id=row["prompt_id"],
            prompt_version=row["prompt_version"],
            provider=row["provider"],
            model=row["model"],
            configuration_version=row["configuration_version"],
            reasoning_summary=row["reasoning_summary"],
        )

    def _validate_snapshot_evidence(self, snapshot_id: str, evidence_ids: tuple[str, ...]) -> None:
        snapshot = self._connection.execute(
            "SELECT snapshot_id FROM page_snapshots WHERE snapshot_id = ?",
            (snapshot_id,),
        ).fetchone()
        if snapshot is None:
            raise sqlite3.IntegrityError(f"snapshot not found: {snapshot_id}")
        for evidence_id in evidence_ids:
            row = self._connection.execute(
                "SELECT snapshot_id FROM evidence WHERE evidence_id = ?",
                (evidence_id,),
            ).fetchone()
            if row is None or row["snapshot_id"] != snapshot_id:
                raise sqlite3.IntegrityError(
                    f"evidence {evidence_id} does not belong to snapshot {snapshot_id}"
                )
