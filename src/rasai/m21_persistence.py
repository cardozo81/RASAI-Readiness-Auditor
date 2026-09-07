"""SQLite persistence for M21 external web performance evidence."""

from __future__ import annotations

from dataclasses import dataclass
import json
import sqlite3
from typing import Any

from rasai.persistence import AuditWorkspace


def _dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


@dataclass(frozen=True, slots=True)
class WebPerformanceRun:
    audit_id: str
    enabled: bool
    status: str
    field_source: str
    page_limit: int
    pages_considered: int
    context_attempts: int
    successful_contexts: int
    pagespeed_successes: int
    crux_successes: int
    categories: tuple[str, ...]
    reason: str | None
    updated_at: str


@dataclass(frozen=True, slots=True)
class WebPerformanceObservation:
    observation_id: str
    audit_id: str
    page_id: str
    snapshot_id: str
    device: str
    url: str
    strategy: str
    status: str
    lighthouse_version: str | None
    lighthouse_fetch_time: str | None
    performance_score: float | None
    accessibility_score: float | None
    best_practices_score: float | None
    seo_score: float | None
    fcp_lab_ms: float | None
    speed_index_lab_ms: float | None
    lcp_lab_ms: float | None
    tbt_lab_ms: float | None
    cls_lab: float | None
    field_source: str | None
    field_scope: str | None
    lcp_p75_ms: float | None
    inp_p75_ms: float | None
    cls_p75: float | None
    lcp_assessment: str | None
    inp_assessment: str | None
    cls_assessment: str | None
    cwv_assessment: str
    pagespeed_http_status: int | None
    crux_http_status: int | None
    pagespeed_artifact_reference: str | None
    crux_artifact_reference: str | None
    error_summary: str | None
    captured_at: str


@dataclass(frozen=True, slots=True)
class WebPerformanceAttempt:
    attempt_id: str
    audit_id: str
    page_id: str
    snapshot_id: str
    device: str
    url: str
    service: str
    status: str
    http_status: int | None
    duration_ms: int
    error_code: str | None
    error_message: str | None
    artifact_reference: str | None
    created_at: str


class M21Persistence:
    def __init__(self, workspace: AuditWorkspace) -> None:
        self._connection = sqlite3.connect(workspace.database)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._initialize()

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> "M21Persistence":
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()

    def _initialize(self) -> None:
        with self._connection:
            self._connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS web_performance_runs (
                    audit_id TEXT PRIMARY KEY REFERENCES audits(audit_id) ON DELETE CASCADE,
                    enabled INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    field_source TEXT NOT NULL,
                    page_limit INTEGER NOT NULL,
                    pages_considered INTEGER NOT NULL,
                    context_attempts INTEGER NOT NULL,
                    successful_contexts INTEGER NOT NULL,
                    pagespeed_successes INTEGER NOT NULL,
                    crux_successes INTEGER NOT NULL,
                    categories TEXT NOT NULL,
                    reason TEXT,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS web_performance_observations (
                    observation_id TEXT PRIMARY KEY,
                    audit_id TEXT NOT NULL REFERENCES audits(audit_id) ON DELETE CASCADE,
                    page_id TEXT NOT NULL REFERENCES pages(page_id) ON DELETE CASCADE,
                    snapshot_id TEXT NOT NULL REFERENCES page_snapshots(snapshot_id) ON DELETE CASCADE,
                    device TEXT NOT NULL,
                    url TEXT NOT NULL,
                    strategy TEXT NOT NULL,
                    status TEXT NOT NULL,
                    lighthouse_version TEXT,
                    lighthouse_fetch_time TEXT,
                    performance_score REAL,
                    accessibility_score REAL,
                    best_practices_score REAL,
                    seo_score REAL,
                    fcp_lab_ms REAL,
                    speed_index_lab_ms REAL,
                    lcp_lab_ms REAL,
                    tbt_lab_ms REAL,
                    cls_lab REAL,
                    field_source TEXT,
                    field_scope TEXT,
                    lcp_p75_ms REAL,
                    inp_p75_ms REAL,
                    cls_p75 REAL,
                    lcp_assessment TEXT,
                    inp_assessment TEXT,
                    cls_assessment TEXT,
                    cwv_assessment TEXT NOT NULL,
                    pagespeed_http_status INTEGER,
                    crux_http_status INTEGER,
                    pagespeed_artifact_reference TEXT,
                    crux_artifact_reference TEXT,
                    error_summary TEXT,
                    captured_at TEXT NOT NULL,
                    UNIQUE(audit_id,snapshot_id)
                );

                CREATE TABLE IF NOT EXISTS web_performance_attempts (
                    attempt_id TEXT PRIMARY KEY,
                    audit_id TEXT NOT NULL REFERENCES audits(audit_id) ON DELETE CASCADE,
                    page_id TEXT NOT NULL REFERENCES pages(page_id) ON DELETE CASCADE,
                    snapshot_id TEXT NOT NULL REFERENCES page_snapshots(snapshot_id) ON DELETE CASCADE,
                    device TEXT NOT NULL,
                    url TEXT NOT NULL,
                    service TEXT NOT NULL,
                    status TEXT NOT NULL,
                    http_status INTEGER,
                    duration_ms INTEGER NOT NULL,
                    error_code TEXT,
                    error_message TEXT,
                    artifact_reference TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_web_perf_obs_audit
                    ON web_performance_observations(audit_id,page_id,device);
                CREATE INDEX IF NOT EXISTS idx_web_perf_attempts_audit
                    ON web_performance_attempts(audit_id,created_at,service);
                """
            )

    def upsert_run(self, run: WebPerformanceRun) -> None:
        with self._connection:
            self._connection.execute(
                """
                INSERT INTO web_performance_runs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(audit_id) DO UPDATE SET
                    enabled=excluded.enabled,
                    status=excluded.status,
                    field_source=excluded.field_source,
                    page_limit=excluded.page_limit,
                    pages_considered=excluded.pages_considered,
                    context_attempts=excluded.context_attempts,
                    successful_contexts=excluded.successful_contexts,
                    pagespeed_successes=excluded.pagespeed_successes,
                    crux_successes=excluded.crux_successes,
                    categories=excluded.categories,
                    reason=excluded.reason,
                    updated_at=excluded.updated_at
                """,
                (
                    run.audit_id,
                    1 if run.enabled else 0,
                    run.status,
                    run.field_source,
                    run.page_limit,
                    run.pages_considered,
                    run.context_attempts,
                    run.successful_contexts,
                    run.pagespeed_successes,
                    run.crux_successes,
                    _dump(list(run.categories)),
                    run.reason,
                    run.updated_at,
                ),
            )

    def add_observation(self, item: WebPerformanceObservation) -> None:
        with self._connection:
            self._connection.execute(
                """
                INSERT OR REPLACE INTO web_performance_observations VALUES (
                    ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?
                )
                """,
                (
                    item.observation_id,
                    item.audit_id,
                    item.page_id,
                    item.snapshot_id,
                    item.device,
                    item.url,
                    item.strategy,
                    item.status,
                    item.lighthouse_version,
                    item.lighthouse_fetch_time,
                    item.performance_score,
                    item.accessibility_score,
                    item.best_practices_score,
                    item.seo_score,
                    item.fcp_lab_ms,
                    item.speed_index_lab_ms,
                    item.lcp_lab_ms,
                    item.tbt_lab_ms,
                    item.cls_lab,
                    item.field_source,
                    item.field_scope,
                    item.lcp_p75_ms,
                    item.inp_p75_ms,
                    item.cls_p75,
                    item.lcp_assessment,
                    item.inp_assessment,
                    item.cls_assessment,
                    item.cwv_assessment,
                    item.pagespeed_http_status,
                    item.crux_http_status,
                    item.pagespeed_artifact_reference,
                    item.crux_artifact_reference,
                    item.error_summary,
                    item.captured_at,
                ),
            )

    def add_attempt(self, item: WebPerformanceAttempt) -> None:
        with self._connection:
            self._connection.execute(
                """
                INSERT INTO web_performance_attempts VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    item.attempt_id,
                    item.audit_id,
                    item.page_id,
                    item.snapshot_id,
                    item.device,
                    item.url,
                    item.service,
                    item.status,
                    item.http_status,
                    item.duration_ms,
                    item.error_code,
                    item.error_message,
                    item.artifact_reference,
                    item.created_at,
                ),
            )
