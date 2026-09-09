"""Additive SERP persistence using the existing per-audit SQLite database."""
from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import sqlite3
from typing import Any

from .models import SearchIntelligenceResult


def _dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _dt(value: datetime) -> str:
    return value.isoformat()


class SerpObservationRepository:
    """Persist SERP observations without changing core audit/scoring tables."""

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
                """
            )

    def save(self, result: SearchIntelligenceResult) -> None:
        observation = result.observation
        if observation is None:
            return
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

    def observation_count(self) -> int:
        row = self.connection.execute(
            "SELECT COUNT(*) FROM serp_observations WHERE audit_id=?", (self.audit_id,)
        ).fetchone()
        return int(row[0])
