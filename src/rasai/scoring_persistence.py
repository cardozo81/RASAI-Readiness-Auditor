"""Additive SQLite persistence for M9 scores and contributions."""

from __future__ import annotations

import json
import sqlite3

from rasai.domain import DeviceContext, RuleResult
from rasai.persistence import AuditWorkspace
from rasai.scoring import ConsolidationStatus, Score, ScoreConfidence, ScoreContribution


class ScoringPersistence:
    def __init__(self, workspace: AuditWorkspace) -> None:
        self._connection = sqlite3.connect(workspace.database)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._initialize()

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> "ScoringPersistence":
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()

    def _initialize(self) -> None:
        with self._connection:
            self._connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS scores (
                    score_id TEXT PRIMARY KEY,
                    audit_id TEXT NOT NULL REFERENCES audits(audit_id) ON DELETE CASCADE,
                    dimension TEXT NOT NULL,
                    device TEXT NOT NULL,
                    value REAL,
                    coverage REAL NOT NULL,
                    confidence TEXT NOT NULL,
                    consolidation_status TEXT NOT NULL,
                    scoring_version TEXT NOT NULL,
                    calculated_at TEXT NOT NULL,
                    limitations TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS score_contributions (
                    contribution_id TEXT PRIMARY KEY,
                    score_id TEXT NOT NULL REFERENCES scores(score_id) ON DELETE CASCADE,
                    rule_id TEXT NOT NULL,
                    rule_execution_id TEXT NOT NULL REFERENCES rule_executions(rule_execution_id) ON DELETE CASCADE,
                    dimension TEXT NOT NULL,
                    device TEXT NOT NULL,
                    weight REAL NOT NULL,
                    result TEXT NOT NULL,
                    result_factor REAL,
                    effective_contribution REAL,
                    scoring_group TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_scores_audit_device ON scores(audit_id, device, dimension);
                CREATE INDEX IF NOT EXISTS idx_contributions_score ON score_contributions(score_id);
                """
            )

    def add_score(self, score: Score) -> None:
        with self._connection:
            self._connection.execute(
                "INSERT INTO scores VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    score.score_id, score.audit_id, score.dimension, score.device.value,
                    score.value, score.coverage, score.confidence.value,
                    score.consolidation_status.value, score.scoring_version,
                    score.calculated_at.isoformat(), json.dumps(list(score.limitations), ensure_ascii=False),
                ),
            )

    def add_contribution(self, contribution: ScoreContribution) -> None:
        with self._connection:
            self._connection.execute(
                "INSERT INTO score_contributions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    contribution.contribution_id, contribution.score_id, contribution.rule_id,
                    contribution.rule_execution_id, contribution.dimension, contribution.device.value,
                    contribution.weight, contribution.result.value, contribution.result_factor,
                    contribution.effective_contribution, contribution.scoring_group,
                ),
            )

    def get_score(self, score_id: str) -> Score | None:
        row = self._connection.execute("SELECT * FROM scores WHERE score_id = ?", (score_id,)).fetchone()
        if row is None:
            return None
        from datetime import datetime
        return Score(
            score_id=row["score_id"], audit_id=row["audit_id"], dimension=row["dimension"],
            device=DeviceContext(row["device"]), value=row["value"], coverage=float(row["coverage"]),
            confidence=ScoreConfidence(row["confidence"]), consolidation_status=ConsolidationStatus(row["consolidation_status"]),
            scoring_version=row["scoring_version"], calculated_at=datetime.fromisoformat(row["calculated_at"]),
            limitations=tuple(json.loads(row["limitations"])),
        )

    def list_scores(self, audit_id: str, device: DeviceContext | None = None) -> tuple[Score, ...]:
        if device is None:
            rows = self._connection.execute("SELECT score_id FROM scores WHERE audit_id = ? ORDER BY device, dimension", (audit_id,)).fetchall()
        else:
            rows = self._connection.execute("SELECT score_id FROM scores WHERE audit_id = ? AND device = ? ORDER BY dimension", (audit_id, device.value)).fetchall()
        return tuple(self.get_score(row["score_id"]) for row in rows if self.get_score(row["score_id"]) is not None)

    def list_contributions(self, score_id: str) -> tuple[ScoreContribution, ...]:
        rows = self._connection.execute("SELECT * FROM score_contributions WHERE score_id = ? ORDER BY contribution_id", (score_id,)).fetchall()
        return tuple(
            ScoreContribution(
                contribution_id=row["contribution_id"], score_id=row["score_id"], rule_id=row["rule_id"],
                rule_execution_id=row["rule_execution_id"], dimension=row["dimension"], device=DeviceContext(row["device"]),
                weight=float(row["weight"]), result=RuleResult(row["result"]),
                result_factor=float(row["result_factor"]) if row["result_factor"] is not None else None,
                effective_contribution=float(row["effective_contribution"]) if row["effective_contribution"] is not None else None,
                scoring_group=row["scoring_group"],
            )
            for row in rows
        )
