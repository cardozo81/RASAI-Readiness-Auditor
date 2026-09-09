"""Secret-safe persistence boundary shared by SQLite and PostgreSQL control planes.

This layer deliberately sits above database adapters. Domain data that may legitimately
contain arbitrary metadata is sanitized before persistence, while durable configuration
surfaces reject inline credentials and accept only references to environment/secret
management. Immutable AUD evidence and scoring are outside this store.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
from typing import Any, Iterable, Sequence

from rasai.secret_safety import (
    redact_text,
    redact_value,
    validate_command_argv_secret_free,
    validate_environment_reference,
    validate_secret_free_mapping,
)

from .central_store import CentralPlatformStore
from .models import ExecutionJob, ExternalDataset, Integration, Milestone, PageIdentity, Schedule, UsageEvent
from .store import new_id, utc_now

_ALLOWED_EXECUTION_JOB_TYPES = {"AUDIT", "SEARCH_MONITOR", "REPORT_REFRESH"}
_ALLOWED_EXECUTION_JOB_STATUSES = {"QUEUED", "CLAIMED", "RUNNING", "SUCCEEDED", "FAILED", "CANCELLED"}


def _safe_mapping(value: dict[str, Any] | None) -> dict[str, Any]:
    if not value:
        return {}
    sanitized = redact_value(value)
    return dict(sanitized) if isinstance(sanitized, dict) else {}


def _safe_optional_text(value: str | None) -> str | None:
    return None if value is None else redact_text(value)


def _dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _load_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    try:
        loaded = json.loads(str(value or "{}"))
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return dict(loaded) if isinstance(loaded, dict) else {}


class SecurePlatformStore(CentralPlatformStore):
    """Canonical control-plane store with provider-neutral secret safety."""

    def __init__(self, database: str | Path) -> None:
        super().__init__(database)
        self._initialize_execution_extensions()

    def _initialize_execution_extensions(self) -> None:
        """Create SQLite-only additive execution tables.

        PostgreSQLPlatformStore deliberately does not call this initializer; hosted
        PostgreSQL schema changes are applied only by explicit versioned migrations.
        """
        with self._connection:
            self._connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS execution_jobs (
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
                    UNIQUE(project_id, idempotency_key)
                );
                CREATE INDEX IF NOT EXISTS idx_execution_jobs_ready
                    ON execution_jobs(status, available_at, priority, created_at);
                CREATE INDEX IF NOT EXISTS idx_execution_jobs_scope
                    ON execution_jobs(project_id, property_id, environment_id, created_at);
                """
            )
            self._connection.execute(
                """INSERT INTO platform_extension_meta(key,value) VALUES('execution_jobs_schema','1')
                   ON CONFLICT(key) DO UPDATE SET value=excluded.value"""
            )

    def add_milestone(self, **kwargs: Any) -> Milestone:
        kwargs["metadata"] = _safe_mapping(kwargs.get("metadata"))
        kwargs["description"] = _safe_optional_text(kwargs.get("description"))
        return super().add_milestone(**kwargs)

    def record_comparison(self, **kwargs: Any) -> str:
        kwargs["manifest"] = _safe_mapping(kwargs.get("manifest"))
        return super().record_comparison(**kwargs)

    def create_page_identity(
        self,
        property_id: str,
        canonical_name: str,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> PageIdentity:
        return super().create_page_identity(
            property_id,
            canonical_name,
            metadata=_safe_mapping(metadata),
        )

    def add_schedule(self, **kwargs: Any) -> Schedule:
        command_argv = tuple(str(item) for item in kwargs.get("command_argv") or ())
        validate_command_argv_secret_free(command_argv)
        kwargs["command_argv"] = command_argv
        return super().add_schedule(**kwargs)

    def add_alert_rule(self, **kwargs: Any):
        destination_env = kwargs.get("destination_env")
        if destination_env is not None:
            kwargs["destination_env"] = validate_environment_reference(str(destination_env))
        return super().add_alert_rule(**kwargs)

    def add_notification(self, **kwargs: Any) -> str:
        kwargs["payload"] = _safe_mapping(kwargs.get("payload"))
        kwargs["delivery_error"] = _safe_optional_text(kwargs.get("delivery_error"))
        destination = kwargs.get("destination")
        if isinstance(destination, str):
            kwargs["destination"] = redact_text(destination)
        return super().add_notification(**kwargs)

    def add_integration(self, **kwargs: Any) -> Integration:
        secret_env = kwargs.get("secret_env")
        if secret_env is not None:
            kwargs["secret_env"] = validate_environment_reference(str(secret_env))
        configuration = kwargs.get("configuration") or {}
        if not isinstance(configuration, dict):
            raise ValueError("integration configuration must be a mapping")
        validate_secret_free_mapping(configuration, context="integration configuration")
        kwargs["configuration"] = _safe_mapping(configuration)
        return super().add_integration(**kwargs)

    def add_external_dataset(
        self,
        dataset: ExternalDataset,
        records: Iterable[dict[str, Any]],
    ) -> None:
        safe_dataset = replace(dataset, metadata=_safe_mapping(dataset.metadata))
        safe_records: list[dict[str, Any]] = []
        for record in records:
            sanitized = redact_value(record)
            if not isinstance(sanitized, dict):
                raise ValueError("external dataset record must be a mapping")
            safe_records.append(dict(sanitized))
        super().add_external_dataset(safe_dataset, safe_records)

    def add_usage_event(self, **kwargs: Any) -> UsageEvent:
        kwargs["metadata"] = _safe_mapping(kwargs.get("metadata"))
        return super().add_usage_event(**kwargs)

    # --- durable execution queue --------------------------------------------
    def _execution_job(self, row: Any) -> ExecutionJob:
        return ExecutionJob(
            job_id=str(row["job_id"]),
            organization_id=str(row["organization_id"]),
            project_id=str(row["project_id"]),
            property_id=str(row["property_id"]),
            environment_id=str(row["environment_id"]),
            job_type=str(row["job_type"]),
            payload=_load_mapping(row["payload_json"]),
            status=str(row["status"]),
            requested_by=(str(row["requested_by"]) if row["requested_by"] is not None else None),
            idempotency_key=(str(row["idempotency_key"]) if row["idempotency_key"] is not None else None),
            priority=int(row["priority"]),
            attempts=int(row["attempts"]),
            max_attempts=int(row["max_attempts"]),
            available_at=str(row["available_at"]),
            claimed_at=(str(row["claimed_at"]) if row["claimed_at"] is not None else None),
            claimed_by=(str(row["claimed_by"]) if row["claimed_by"] is not None else None),
            lease_until=(str(row["lease_until"]) if row["lease_until"] is not None else None),
            started_at=(str(row["started_at"]) if row["started_at"] is not None else None),
            completed_at=(str(row["completed_at"]) if row["completed_at"] is not None else None),
            result_ref=(str(row["result_ref"]) if row["result_ref"] is not None else None),
            result_metadata=_load_mapping(row["result_metadata_json"]),
            last_error=(str(row["last_error"]) if row["last_error"] is not None else None),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )

    def enqueue_execution_job(
        self,
        *,
        project_id: str,
        property_id: str,
        environment_id: str,
        job_type: str,
        payload: dict[str, Any] | None = None,
        requested_by: str | None = None,
        idempotency_key: str | None = None,
        priority: int = 100,
        max_attempts: int = 3,
        available_at: str | None = None,
    ) -> ExecutionJob:
        self._scope_row(project_id, property_id, environment_id)
        normalized_type = job_type.strip().upper()
        if normalized_type not in _ALLOWED_EXECUTION_JOB_TYPES:
            raise ValueError(f"unsupported execution job type: {job_type}")
        safe_payload = payload or {}
        if not isinstance(safe_payload, dict):
            raise ValueError("execution job payload must be a mapping")
        validate_secret_free_mapping(safe_payload, context="execution job payload")
        safe_payload = _safe_mapping(safe_payload)
        if requested_by is not None:
            user = self._connection.execute("SELECT 1 FROM users WHERE user_id=?", (requested_by,)).fetchone()
            if user is None:
                raise KeyError(f"requested_by user not found: {requested_by}")
        normalized_key = idempotency_key.strip() if idempotency_key else None
        if normalized_key and len(normalized_key) > 200:
            raise ValueError("idempotency key cannot exceed 200 characters")
        if max_attempts < 1 or max_attempts > 100:
            raise ValueError("max_attempts must be between 1 and 100")
        if priority < 0 or priority > 1000:
            raise ValueError("priority must be between 0 and 1000")
        if normalized_key:
            existing = self._connection.execute(
                "SELECT * FROM execution_jobs WHERE project_id=? AND idempotency_key=?",
                (project_id, normalized_key),
            ).fetchone()
            if existing is not None:
                return self._execution_job(existing)
        organization_id = self._project_organization(project_id)
        now = utc_now()
        ready_at = available_at or now
        job_id = new_id("JOB")
        with self._connection:
            self._connection.execute(
                """INSERT INTO execution_jobs(
                    job_id,organization_id,project_id,property_id,environment_id,job_type,payload_json,status,
                    requested_by,idempotency_key,priority,attempts,max_attempts,available_at,created_at,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    job_id, organization_id, project_id, property_id, environment_id, normalized_type,
                    _dump(safe_payload), "QUEUED", requested_by, normalized_key, priority, 0, max_attempts,
                    ready_at, now, now,
                ),
            )
        item = self.get_execution_job(job_id)
        assert item is not None
        return item

    def get_execution_job(self, job_id: str) -> ExecutionJob | None:
        row = self._connection.execute("SELECT * FROM execution_jobs WHERE job_id=?", (job_id,)).fetchone()
        return self._execution_job(row) if row is not None else None

    def list_execution_jobs(
        self,
        *,
        project_id: str | None = None,
        statuses: Sequence[str] | None = None,
        limit: int = 100,
    ) -> tuple[ExecutionJob, ...]:
        if limit < 1 or limit > 1000:
            raise ValueError("execution job limit must be between 1 and 1000")
        clauses: list[str] = []
        values: list[Any] = []
        if project_id:
            clauses.append("project_id=?")
            values.append(project_id)
        if statuses:
            normalized = tuple(dict.fromkeys(str(status).strip().upper() for status in statuses))
            invalid = sorted(set(normalized) - _ALLOWED_EXECUTION_JOB_STATUSES)
            if invalid:
                raise ValueError("unsupported execution status(es): " + ", ".join(invalid))
            clauses.append("status IN (" + ",".join("?" for _ in normalized) + ")")
            values.extend(normalized)
        sql = "SELECT * FROM execution_jobs"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY priority ASC, created_at DESC LIMIT ?"
        values.append(limit)
        return tuple(self._execution_job(row) for row in self._connection.execute(sql, values))

    def cancel_execution_job(self, job_id: str) -> ExecutionJob:
        now = utc_now()
        with self._connection:
            cursor = self._connection.execute(
                """UPDATE execution_jobs SET status='CANCELLED',completed_at=?,updated_at=?
                   WHERE job_id=? AND status IN ('QUEUED','CLAIMED')""",
                (now, now, job_id),
            )
        if cursor.rowcount != 1:
            existing = self.get_execution_job(job_id)
            if existing is None:
                raise KeyError(f"execution job not found: {job_id}")
            raise ValueError(f"execution job cannot be cancelled from status {existing.status}")
        item = self.get_execution_job(job_id)
        assert item is not None
        return item

    def recover_expired_execution_jobs(self) -> tuple[int, int]:
        """Requeue expired active leases and fail jobs that exhausted attempts.

        Returns ``(requeued, failed)``. Recovery is deliberately idempotent and runs
        inside one control-plane transaction so crashed workers cannot leave durable
        jobs permanently stranded in CLAIMED/RUNNING.
        """
        now = utc_now()
        requeued = 0
        failed = 0
        with self.transaction() as connection:
            rows = connection.execute(
                """SELECT job_id,attempts,max_attempts FROM execution_jobs
                   WHERE status IN ('CLAIMED','RUNNING') AND lease_until IS NOT NULL AND lease_until<?""",
                (now,),
            ).fetchall()
            for row in rows:
                job_id = str(row["job_id"])
                attempts = int(row["attempts"])
                max_attempts = int(row["max_attempts"])
                if attempts >= max_attempts:
                    cursor = connection.execute(
                        """UPDATE execution_jobs SET status='FAILED',completed_at=?,claimed_at=NULL,
                           claimed_by=NULL,lease_until=NULL,last_error=?,updated_at=?
                           WHERE job_id=? AND status IN ('CLAIMED','RUNNING') AND lease_until<?""",
                        (now, "worker lease expired after maximum attempts", now, job_id, now),
                    )
                    failed += int(cursor.rowcount == 1)
                else:
                    cursor = connection.execute(
                        """UPDATE execution_jobs SET status='QUEUED',available_at=?,claimed_at=NULL,
                           claimed_by=NULL,lease_until=NULL,started_at=NULL,updated_at=?
                           WHERE job_id=? AND status IN ('CLAIMED','RUNNING') AND lease_until<?""",
                        (now, now, job_id, now),
                    )
                    requeued += int(cursor.rowcount == 1)
        return requeued, failed

    def claim_execution_job(
        self,
        worker_id: str,
        *,
        job_types: Sequence[str] | None = None,
        lease_seconds: int = 300,
    ) -> ExecutionJob | None:
        worker = worker_id.strip()
        if not worker:
            raise ValueError("worker_id cannot be empty")
        if lease_seconds < 30 or lease_seconds > 86400:
            raise ValueError("lease_seconds must be between 30 and 86400")
        types = tuple(dict.fromkeys(str(value).strip().upper() for value in (job_types or ())))
        invalid = sorted(set(types) - _ALLOWED_EXECUTION_JOB_TYPES)
        if invalid:
            raise ValueError("unsupported execution job type(s): " + ", ".join(invalid))
        self.recover_expired_execution_jobs()
        now_dt = datetime.now(UTC)
        now = now_dt.isoformat()
        lease_until = (now_dt + timedelta(seconds=lease_seconds)).isoformat()
        clauses = ["status='QUEUED'", "available_at<=?", "attempts<max_attempts"]
        values: list[Any] = [now]
        if types:
            clauses.append("job_type IN (" + ",".join("?" for _ in types) + ")")
            values.extend(types)
        select_sql = (
            "SELECT job_id FROM execution_jobs WHERE " + " AND ".join(clauses) +
            " ORDER BY priority ASC,available_at ASC,created_at ASC LIMIT 10"
        )
        with self.transaction() as connection:
            candidates = connection.execute(select_sql, values).fetchall()
            for candidate in candidates:
                job_id = str(candidate[0])
                cursor = connection.execute(
                    """UPDATE execution_jobs
                       SET status='CLAIMED',claimed_at=?,claimed_by=?,lease_until=?,attempts=attempts+1,updated_at=?
                       WHERE job_id=? AND status='QUEUED' AND attempts<max_attempts""",
                    (now, worker, lease_until, now, job_id),
                )
                if cursor.rowcount == 1:
                    row = connection.execute("SELECT * FROM execution_jobs WHERE job_id=?", (job_id,)).fetchone()
                    return self._execution_job(row)
        return None

    def start_execution_job(self, job_id: str, worker_id: str) -> ExecutionJob:
        now = utc_now()
        with self._connection:
            cursor = self._connection.execute(
                """UPDATE execution_jobs SET status='RUNNING',started_at=?,updated_at=?
                   WHERE job_id=? AND status='CLAIMED' AND claimed_by=?""",
                (now, now, job_id, worker_id),
            )
        if cursor.rowcount != 1:
            raise ValueError("execution job is not claimed by this worker")
        item = self.get_execution_job(job_id)
        assert item is not None
        return item

    def finish_execution_job(
        self,
        job_id: str,
        worker_id: str,
        *,
        succeeded: bool,
        result_ref: str | None = None,
        result_metadata: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> ExecutionJob:
        now = utc_now()
        safe_metadata = _safe_mapping(result_metadata)
        safe_ref = _safe_optional_text(result_ref)
        safe_error = _safe_optional_text(error)
        status = "SUCCEEDED" if succeeded else "FAILED"
        with self._connection:
            cursor = self._connection.execute(
                """UPDATE execution_jobs
                   SET status=?,completed_at=?,lease_until=NULL,result_ref=?,result_metadata_json=?,last_error=?,updated_at=?
                   WHERE job_id=? AND status IN ('CLAIMED','RUNNING') AND claimed_by=?""",
                (status, now, safe_ref, _dump(safe_metadata), safe_error, now, job_id, worker_id),
            )
        if cursor.rowcount != 1:
            raise ValueError("execution job is not active for this worker")
        item = self.get_execution_job(job_id)
        assert item is not None
        return item