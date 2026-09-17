"""Additive SERP persistence using the existing per-audit SQLite database."""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from typing import Any

from .models import SearchIntelligenceResult, SerpDataMode

SERP_TEMPORAL_LIVE = "LIVE_RECOLLECTION"
SERP_TEMPORAL_REUSED = "REUSED_EVIDENCE"
SERP_TEMPORAL_NON_LIVE = "NON_LIVE_SOURCE"


def _dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _dt(value: datetime) -> str:
    return value.isoformat()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class SerpObservationRepository:
    """Persist SERP observations with explicit freshness/provenance semantics."""

    def __init__(self, database: Path, *, audit_id: str) -> None:
        self.database = Path(database)
        self.audit_id = audit_id
        self.connection = sqlite3.connect(self.database)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self._initialize()

    @classmethod
    def from_workspace(cls, workspace_root: Path) -> "SerpObservationRepository":
        root = Path(workspace_root)
        database = root / "audit.db"
        if not database.is_file():
            raise FileNotFoundError(f"audit database not found: {database}")
        connection = sqlite3.connect(database)
        try:
            rows = connection.execute("SELECT audit_id FROM audits ORDER BY created_at LIMIT 2").fetchall()
        finally:
            connection.close()
        if len(rows) != 1:
            raise ValueError(
                f"expected exactly one audit row in workspace {root}; found {len(rows)}"
            )
        return cls(database, audit_id=str(rows[0][0]))

    def __enter__(self) -> "SerpObservationRepository":
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()

    def close(self) -> None:
        self.connection.close()

    def _initialize(self) -> None:
        with self.connection:
            self.connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS serp_observations (
                    observation_id TEXT PRIMARY KEY,
                    audit_id TEXT NOT NULL REFERENCES audits(audit_id) ON DELETE CASCADE,
                    run_id TEXT NOT NULL,
                    query TEXT NOT NULL,
                    query_origin TEXT NOT NULL,
                    engine TEXT NOT NULL,
                    country TEXT NOT NULL,
                    region TEXT,
                    language TEXT NOT NULL,
                    device TEXT NOT NULL,
                    collected_at TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    provider_request_id TEXT,
                    requested_depth INTEGER NOT NULL,
                    result_count INTEGER NOT NULL,
                    data_mode TEXT NOT NULL,
                    observation_status TEXT NOT NULL,
                    domain_of_interest TEXT,
                    customer_position INTEGER,
                    domain_status TEXT NOT NULL,
                    raw_evidence_ref TEXT,
                    raw_evidence_sha256 TEXT,
                    config_metadata TEXT NOT NULL,
                    quality_metadata TEXT NOT NULL,
                    error_code TEXT,
                    error_message TEXT
                );

                CREATE TABLE IF NOT EXISTS serp_results (
                    observation_id TEXT NOT NULL REFERENCES serp_observations(observation_id) ON DELETE CASCADE,
                    position INTEGER NOT NULL,
                    domain TEXT NOT NULL,
                    url TEXT NOT NULL,
                    title TEXT,
                    snippet TEXT,
                    result_type TEXT NOT NULL,
                    serp_features TEXT NOT NULL,
                    metadata TEXT NOT NULL,
                    PRIMARY KEY (observation_id, position, url)
                );

                CREATE TABLE IF NOT EXISTS serp_evidence_provenance (
                    observation_id TEXT PRIMARY KEY REFERENCES serp_observations(observation_id) ON DELETE CASCADE,
                    audit_id TEXT NOT NULL REFERENCES audits(audit_id) ON DELETE CASCADE,
                    temporal_mode TEXT NOT NULL,
                    captured_at TEXT NOT NULL,
                    source_audit_id TEXT,
                    source_observation_id TEXT,
                    reused_at TEXT,
                    reuse_reason TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_serp_observations_audit_query_time
                    ON serp_observations(audit_id, query, collected_at);
                CREATE INDEX IF NOT EXISTS idx_serp_observations_run
                    ON serp_observations(run_id, collected_at);
                CREATE INDEX IF NOT EXISTS idx_serp_observations_domain_status
                    ON serp_observations(audit_id, domain_of_interest, domain_status, collected_at);
                CREATE INDEX IF NOT EXISTS idx_serp_results_observation_position
                    ON serp_results(observation_id, position);
                CREATE INDEX IF NOT EXISTS idx_serp_results_domain
                    ON serp_results(domain, observation_id, position);
                CREATE INDEX IF NOT EXISTS idx_serp_provenance_audit_mode
                    ON serp_evidence_provenance(audit_id, temporal_mode, captured_at);
                """
            )

    @staticmethod
    def _temporal_mode(data_mode: SerpDataMode) -> str:
        if data_mode in {SerpDataMode.OBSERVED_API, SerpDataMode.OBSERVED_SYNTHETIC}:
            return SERP_TEMPORAL_LIVE
        return SERP_TEMPORAL_NON_LIVE

    def save(self, result: SearchIntelligenceResult) -> None:
        observation = result.observation
        if observation is None:
            return
        temporal_mode = self._temporal_mode(observation.data_mode)
        with self.connection:
            self.connection.execute(
                """
                INSERT INTO serp_observations (
                    observation_id,audit_id,run_id,query,query_origin,engine,country,region,
                    language,device,collected_at,provider,provider_request_id,requested_depth,
                    result_count,data_mode,observation_status,domain_of_interest,customer_position,
                    domain_status,raw_evidence_ref,raw_evidence_sha256,config_metadata,
                    quality_metadata,error_code,error_message
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    observation.observation_id,
                    self.audit_id,
                    observation.run_id,
                    observation.query,
                    observation.query_origin.value,
                    observation.engine,
                    observation.country,
                    observation.region,
                    observation.language,
                    observation.device,
                    _dt(observation.collected_at),
                    observation.provider,
                    observation.provider_request_id,
                    observation.requested_depth,
                    observation.result_count,
                    observation.data_mode.value,
                    observation.status.value,
                    result.request.domain_of_interest,
                    result.customer_position,
                    result.domain_status.value,
                    observation.raw_evidence_ref,
                    observation.raw_evidence_sha256,
                    _dump(dict(observation.config_metadata)),
                    _dump(dict(observation.quality_metadata)),
                    result.error_code,
                    result.error_message,
                ),
            )
            self.connection.executemany(
                """
                INSERT INTO serp_results (
                    observation_id,position,domain,url,title,snippet,result_type,serp_features,metadata
                ) VALUES (?,?,?,?,?,?,?,?,?)
                """,
                [
                    (
                        observation.observation_id,
                        item.position,
                        item.domain,
                        item.url,
                        item.title,
                        item.snippet,
                        item.result_type,
                        _dump(item.serp_features),
                        _dump(dict(item.metadata)),
                    )
                    for item in observation.results
                ],
            )
            self.connection.execute(
                """INSERT INTO serp_evidence_provenance(
                    observation_id,audit_id,temporal_mode,captured_at,source_audit_id,
                    source_observation_id,reused_at,reuse_reason,created_at
                ) VALUES (?,?,?,?,?,?,?,?,?)
                ON CONFLICT(observation_id) DO NOTHING""",
                (
                    observation.observation_id,
                    self.audit_id,
                    temporal_mode,
                    _dt(observation.collected_at),
                    self.audit_id if temporal_mode == SERP_TEMPORAL_LIVE else None,
                    observation.observation_id if temporal_mode == SERP_TEMPORAL_LIVE else None,
                    None,
                    None,
                    _now(),
                ),
            )

    def mark_reused(
        self,
        observation_id: str,
        *,
        source_audit_id: str,
        source_observation_id: str,
        captured_at: str,
        reuse_reason: str,
        reused_at: str | None = None,
    ) -> None:
        """Explicitly classify an already-persisted observation as reused evidence."""
        reason = str(reuse_reason or "").strip()
        if not reason:
            raise ValueError("reused SERP evidence requires reuse_reason")
        source_audit = str(source_audit_id or "").strip()
        source_observation = str(source_observation_id or "").strip()
        if not source_audit or not source_observation:
            raise ValueError("reused SERP evidence requires source audit and observation ids")
        row = self.connection.execute(
            "SELECT 1 FROM serp_observations WHERE observation_id=? AND audit_id=?",
            (observation_id, self.audit_id),
        ).fetchone()
        if row is None:
            raise KeyError(f"SERP observation not found in audit: {observation_id}")
        with self.connection:
            self.connection.execute(
                """INSERT INTO serp_evidence_provenance(
                    observation_id,audit_id,temporal_mode,captured_at,source_audit_id,
                    source_observation_id,reused_at,reuse_reason,created_at
                ) VALUES (?,?,?,?,?,?,?,?,?)
                ON CONFLICT(observation_id) DO UPDATE SET
                    temporal_mode=excluded.temporal_mode,captured_at=excluded.captured_at,
                    source_audit_id=excluded.source_audit_id,source_observation_id=excluded.source_observation_id,
                    reused_at=excluded.reused_at,reuse_reason=excluded.reuse_reason""",
                (
                    observation_id,
                    self.audit_id,
                    SERP_TEMPORAL_REUSED,
                    captured_at,
                    source_audit,
                    source_observation,
                    reused_at or _now(),
                    reason,
                    _now(),
                ),
            )

    def observation_count(self) -> int:
        row = self.connection.execute(
            "SELECT COUNT(*) FROM serp_observations WHERE audit_id=?", (self.audit_id,)
        ).fetchone()
        return int(row[0])
