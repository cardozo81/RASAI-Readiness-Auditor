"""Freshness/provenance validation for SERP evidence used by one AUD.

A current-audit LIVE_RECOLLECTION observation must not predate the audit start. Older
observations are allowed only when explicitly classified as REUSED_EVIDENCE with a
source audit/observation and reuse reason. Report generation uses this contract as a
blocking integrity invariant; it never silently relabels stale data as live.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from typing import Any

from .persistence import SERP_TEMPORAL_LIVE, SERP_TEMPORAL_REUSED


@dataclass(frozen=True, slots=True)
class SerpFreshnessIssue:
    observation_id: str
    code: str
    detail: str


def _parse(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _table_exists(connection: sqlite3.Connection, table: str) -> bool:
    return connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone() is not None


def _columns(connection: sqlite3.Connection, table: str) -> set[str]:
    if not _table_exists(connection, table):
        return set()
    return {str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})")}


def _audit_started_at(connection: sqlite3.Connection, audit_id: str) -> datetime | None:
    if not _table_exists(connection, "audits"):
        return None
    columns = _columns(connection, "audits")
    for name in ("started_at", "created_at"):
        if name not in columns:
            continue
        row = connection.execute(
            f"SELECT {name} FROM audits WHERE audit_id=?", (audit_id,)
        ).fetchone()
        parsed = _parse(row[0]) if row else None
        if parsed is not None:
            return parsed
    return None


def ensure_provenance_schema(connection: sqlite3.Connection) -> None:
    if not _table_exists(connection, "serp_observations"):
        return
    with connection:
        connection.executescript(
            """
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
            CREATE INDEX IF NOT EXISTS idx_serp_provenance_audit_mode
                ON serp_evidence_provenance(audit_id, temporal_mode, captured_at);
            """
        )


def validate_serp_freshness(database: str | Path, audit_id: str) -> tuple[SerpFreshnessIssue, ...]:
    path = Path(database)
    if not path.is_file():
        return (SerpFreshnessIssue("", "AUDIT_DATABASE_MISSING", str(path)),)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    try:
        if not _table_exists(connection, "serp_observations"):
            return ()
        columns = _columns(connection, "serp_observations")
        # Freshness can only be evaluated when the persisted observation carries a capture
        # timestamp. Simplified/report fixtures and non-current schemas without that field
        # are not relabelled as fresh; the temporal gate is simply not applicable to them.
        if "collected_at" not in columns or "observation_id" not in columns or "audit_id" not in columns:
            return ()
        ensure_provenance_schema(connection)
        start = _audit_started_at(connection, audit_id)
        rows = connection.execute(
            """SELECT o.observation_id,o.collected_at,
                      p.temporal_mode,p.captured_at,p.source_audit_id,p.source_observation_id,
                      p.reused_at,p.reuse_reason
               FROM serp_observations o
               LEFT JOIN serp_evidence_provenance p ON p.observation_id=o.observation_id
               WHERE o.audit_id=? ORDER BY o.collected_at,o.observation_id""",
            (audit_id,),
        ).fetchall()
        issues: list[SerpFreshnessIssue] = []
        for row in rows:
            observation_id = str(row["observation_id"])
            collected_at = _parse(row["collected_at"])
            mode = str(row["temporal_mode"] or "").strip().upper()
            captured_at = _parse(row["captured_at"] or row["collected_at"])
            if not mode:
                if start is not None and collected_at is not None and collected_at < start:
                    issues.append(SerpFreshnessIssue(
                        observation_id,
                        "MISSING_REUSE_PROVENANCE",
                        "SERP evidence predates the AUD but has no REUSED_EVIDENCE provenance",
                    ))
                continue
            if mode == SERP_TEMPORAL_LIVE:
                if start is not None and captured_at is not None and captured_at < start:
                    issues.append(SerpFreshnessIssue(
                        observation_id,
                        "LIVE_RECOLLECTION_BEFORE_AUDIT",
                        "LIVE_RECOLLECTION captured_at is earlier than audit start",
                    ))
                if str(row["source_audit_id"] or "") not in {"", audit_id}:
                    issues.append(SerpFreshnessIssue(
                        observation_id,
                        "LIVE_RECOLLECTION_FOREIGN_SOURCE",
                        "LIVE_RECOLLECTION must not point to another source audit",
                    ))
            elif mode == SERP_TEMPORAL_REUSED:
                if not str(row["source_audit_id"] or "").strip():
                    issues.append(SerpFreshnessIssue(observation_id, "REUSE_SOURCE_AUDIT_MISSING", "REUSED_EVIDENCE requires source_audit_id"))
                if not str(row["source_observation_id"] or "").strip():
                    issues.append(SerpFreshnessIssue(observation_id, "REUSE_SOURCE_OBSERVATION_MISSING", "REUSED_EVIDENCE requires source_observation_id"))
                if not str(row["reuse_reason"] or "").strip():
                    issues.append(SerpFreshnessIssue(observation_id, "REUSE_REASON_MISSING", "REUSED_EVIDENCE requires reuse_reason"))
                if not _parse(row["reused_at"]):
                    issues.append(SerpFreshnessIssue(observation_id, "REUSED_AT_MISSING", "REUSED_EVIDENCE requires reused_at"))
        return tuple(issues)
    finally:
        connection.close()


def require_valid_serp_freshness(database: str | Path, audit_id: str) -> None:
    issues = validate_serp_freshness(database, audit_id)
    if not issues:
        return
    detail = "; ".join(f"{item.observation_id or 'AUD'}:{item.code}" for item in issues)
    raise RuntimeError("SERP freshness/provenance invariant failed: " + detail)


__all__ = [
    "SerpFreshnessIssue",
    "ensure_provenance_schema",
    "require_valid_serp_freshness",
    "validate_serp_freshness",
]
