"""Additive persistence for evidence-bound Competitive AI analysis."""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from typing import Any

from .competitive_ai import CompetitiveAiResult


def _dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def competitive_ai_result_payload(result: CompetitiveAiResult) -> dict[str, Any]:
    assessment = result.assessment
    return {
        "state": result.state.value,
        "reason": result.reason,
        "assessment": (
            {
                "query_intent": assessment.query_intent,
                "ymyl_assessment": assessment.ymyl_assessment,
                "summary": assessment.summary,
                "provider": assessment.provider,
                "model": assessment.model,
                "contract_version": assessment.contract_version,
                "prompt_id": assessment.prompt_id,
                "prompt_version": assessment.prompt_version,
                "provider_request_id": assessment.provider_request_id,
                "opportunities": [
                    {
                        "category": item.category.value,
                        "priority": item.priority.value,
                        "title": item.title,
                        "recommendation": item.recommendation,
                        "rationale": item.rationale,
                        "evidence_ids": list(item.evidence_ids),
                        "confidence": item.confidence,
                        "causality_note": item.causality_note,
                    }
                    for item in assessment.opportunities
                ],
            }
            if assessment is not None
            else None
        ),
        "interpretation_policy": (
            "Competitive AI recommendations are evidence-bound hypotheses and remediation "
            "opportunities. They are not ranking-causality claims and do not affect SARI-001 "
            "or SCORE-GEO-004."
        ),
    }


class FilesystemCompetitiveAiEvidenceSink:
    def __init__(self, workspace_root: Path) -> None:
        self.workspace_root = Path(workspace_root)
        self.root = (
            self.workspace_root
            / "artifacts"
            / "search-intelligence"
            / "competitive-ai"
        )

    def write(self, observation_id: str, result: CompetitiveAiResult) -> tuple[str, str]:
        self.root.mkdir(parents=True, exist_ok=True)
        payload = _dump(competitive_ai_result_payload(result)).encode("utf-8")
        digest = sha256(payload).hexdigest()
        path = self.root / f"{observation_id}.json"
        path.write_bytes(payload)
        return path.relative_to(self.workspace_root).as_posix(), digest


class CompetitiveAiRepository:
    """Persist Competitive AI outputs without touching scoring or semantic-rule tables."""

    def __init__(self, database: Path, *, audit_id: str) -> None:
        self.database = Path(database)
        self.audit_id = audit_id
        self.connection = sqlite3.connect(self.database)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self._initialize()

    @classmethod
    def from_workspace(cls, workspace_root: Path) -> "CompetitiveAiRepository":
        root = Path(workspace_root)
        database = root / "audit.db"
        if not database.is_file():
            raise FileNotFoundError(f"audit database not found: {database}")
        connection = sqlite3.connect(database)
        try:
            rows = connection.execute(
                "SELECT audit_id FROM audits ORDER BY created_at LIMIT 2"
            ).fetchall()
        finally:
            connection.close()
        if len(rows) != 1:
            raise ValueError(
                f"expected exactly one audit row in workspace {root}; found {len(rows)}"
            )
        return cls(database, audit_id=str(rows[0][0]))

    def close(self) -> None:
        self.connection.close()

    def _initialize(self) -> None:
        with self.connection:
            self.connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS serp_competitive_ai_analyses (
                    observation_id TEXT PRIMARY KEY
                        REFERENCES serp_observations(observation_id) ON DELETE CASCADE,
                    audit_id TEXT NOT NULL REFERENCES audits(audit_id) ON DELETE CASCADE,
                    state TEXT NOT NULL,
                    reason TEXT,
                    provider TEXT,
                    model TEXT,
                    contract_version TEXT,
                    prompt_id TEXT,
                    prompt_version TEXT,
                    provider_request_id TEXT,
                    query_intent TEXT,
                    ymyl_assessment TEXT,
                    summary TEXT,
                    opportunity_count INTEGER NOT NULL,
                    opportunities_json TEXT NOT NULL,
                    evidence_ref TEXT,
                    evidence_sha256 TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_serp_competitive_ai_audit
                    ON serp_competitive_ai_analyses(audit_id, state);
                """
            )

    def save(
        self,
        observation_id: str,
        result: CompetitiveAiResult,
        *,
        evidence_ref: str | None = None,
        evidence_sha256: str | None = None,
    ) -> None:
        assessment = result.assessment
        opportunities = (
            [
                {
                    "category": item.category.value,
                    "priority": item.priority.value,
                    "title": item.title,
                    "recommendation": item.recommendation,
                    "rationale": item.rationale,
                    "evidence_ids": list(item.evidence_ids),
                    "confidence": item.confidence,
                    "causality_note": item.causality_note,
                }
                for item in assessment.opportunities
            ]
            if assessment is not None
            else []
        )
        with self.connection:
            self.connection.execute(
                """
                INSERT OR REPLACE INTO serp_competitive_ai_analyses (
                    observation_id,audit_id,state,reason,provider,model,contract_version,
                    prompt_id,prompt_version,provider_request_id,query_intent,
                    ymyl_assessment,summary,opportunity_count,opportunities_json,
                    evidence_ref,evidence_sha256
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    observation_id,
                    self.audit_id,
                    result.state.value,
                    result.reason,
                    assessment.provider if assessment is not None else None,
                    assessment.model if assessment is not None else None,
                    assessment.contract_version if assessment is not None else None,
                    assessment.prompt_id if assessment is not None else None,
                    assessment.prompt_version if assessment is not None else None,
                    assessment.provider_request_id if assessment is not None else None,
                    assessment.query_intent if assessment is not None else None,
                    assessment.ymyl_assessment if assessment is not None else None,
                    assessment.summary if assessment is not None else None,
                    len(opportunities),
                    _dump(opportunities),
                    evidence_ref,
                    evidence_sha256,
                ),
            )
