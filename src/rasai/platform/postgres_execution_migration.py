"""Explicit PostgreSQL migration contract for durable execution jobs."""
from __future__ import annotations

from typing import Any

EXECUTION_SCHEMA_VERSION = 1


def current_execution_schema_version(connection: Any) -> int:
    exists = connection.execute(
        "SELECT to_regclass('public.platform_execution_schema_migrations') AS table_name"
    ).fetchone()
    if exists is None or exists[0] is None:
        return 0
    row = connection.execute(
        "SELECT COALESCE(MAX(version),0) AS version FROM platform_execution_schema_migrations"
    ).fetchone()
    return int(row[0]) if row is not None else 0


def require_current_execution_schema(connection: Any) -> int:
    version = current_execution_schema_version(connection)
    if version == EXECUTION_SCHEMA_VERSION:
        return version
    if version > EXECUTION_SCHEMA_VERSION:
        raise RuntimeError(
            f"PostgreSQL execution schema {version} is newer than supported {EXECUTION_SCHEMA_VERSION}"
        )
    raise RuntimeError(
        "PostgreSQL execution schema is not current "
        f"(current={version}, supported={EXECUTION_SCHEMA_VERSION}); "
        "run 'rasai platform database migrate' before starting the PostgreSQL backend"
    )


def apply_execution_migrations(connection: Any) -> tuple[int, ...]:
    connection.execute(
        """CREATE TABLE IF NOT EXISTS platform_execution_schema_migrations (
            version INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            applied_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )"""
    )
    applied = {
        int(row[0])
        for row in connection.execute("SELECT version FROM platform_execution_schema_migrations")
    }
    unknown = sorted(version for version in applied if version > EXECUTION_SCHEMA_VERSION)
    if unknown:
        raise RuntimeError(
            f"PostgreSQL execution schema {max(unknown)} is newer than supported {EXECUTION_SCHEMA_VERSION}"
        )
    if 1 in applied:
        return ()
    with connection:
        connection.execute(
            """CREATE TABLE IF NOT EXISTS execution_jobs (
                job_id TEXT PRIMARY KEY,
                organization_id TEXT NOT NULL REFERENCES organizations(organization_id) ON DELETE CASCADE,
                project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
                property_id TEXT NOT NULL REFERENCES properties(property_id) ON DELETE CASCADE,
                environment_id TEXT NOT NULL REFERENCES environments(environment_id) ON DELETE CASCADE,
                job_type TEXT NOT NULL,
                payload_json TEXT NOT NULL DEFAULT '{}',
                status TEXT NOT NULL,
                requested_by TEXT REFERENCES users(user_id) ON DELETE SET NULL,
                idempotency_key TEXT,
                priority INTEGER NOT NULL DEFAULT 100,
                attempts INTEGER NOT NULL DEFAULT 0,
                max_attempts INTEGER NOT NULL DEFAULT 3,
                available_at TEXT NOT NULL,
                claimed_at TEXT,
                claimed_by TEXT,
                lease_until TEXT,
                started_at TEXT,
                completed_at TEXT,
                result_ref TEXT,
                result_metadata_json TEXT NOT NULL DEFAULT '{}',
                last_error TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(project_id, idempotency_key),
                CHECK (status IN ('QUEUED','CLAIMED','RUNNING','SUCCEEDED','FAILED','CANCELLED')),
                CHECK (job_type IN ('AUDIT','SEARCH_MONITOR','REPORT_REFRESH')),
                CHECK (priority BETWEEN 0 AND 1000),
                CHECK (max_attempts BETWEEN 1 AND 100)
            )"""
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_execution_jobs_ready ON execution_jobs(status,available_at,priority,created_at)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_execution_jobs_scope ON execution_jobs(project_id,property_id,environment_id,created_at)"
        )
        connection.execute(
            "INSERT INTO platform_execution_schema_migrations(version,name) VALUES(1,'durable_execution_jobs')"
        )
        connection.execute(
            """INSERT INTO platform_extension_meta(key,value) VALUES('execution_jobs_schema','1')
               ON CONFLICT(key) DO UPDATE SET value=EXCLUDED.value"""
        )
    return (1,)
