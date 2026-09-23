"""Durable SaaS scheduling and consumption analytics over the canonical control plane.

The extension deliberately keeps the original ``schedules`` row as the canonical
schedule identity/scope record. Rich SaaS configuration is one-to-one in
``schedule_definitions``; the legacy local subprocess scheduler therefore remains
compatible and cannot accidentally execute SaaS schedules.
"""
from __future__ import annotations

from datetime import UTC, datetime
import json
from typing import Any, Sequence

from rasai.secret_safety import redact_value, validate_secret_free_mapping

from .saas_scheduling import (
    next_occurrences,
    normalize_overlap_policy,
    normalize_recurrence,
    normalize_scheduled_urls,
    normalize_timezone,
)
from .store import new_id, utc_now

_ALLOWED_JOB_TYPES = {"AUDIT", "SEARCH_MONITOR", "REPORT_REFRESH"}
_ALLOWED_SCHEDULE_STATES = {"ACTIVE", "PAUSED", "DISABLED", "COMPLETED", "ERROR"}
_ALLOWED_GROUPS = {
    "project", "property", "environment", "domain", "url", "user", "provider",
    "integration", "category", "operation", "status", "model", "job", "audit", "resource",
}


def _dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _load(value: Any, default: Any) -> Any:
    if value is None:
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return default


def _iso(value: str | None, *, field: str) -> str | None:
    if value is None:
        return None
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must include an explicit timezone")
    return parsed.astimezone(UTC).isoformat()


class SaaSManagementMixin:
    """Methods shared by SQLite and PostgreSQL canonical stores."""

    def _initialize_saas_management_extensions(self) -> None:
        """SQLite-only additive schema. PostgreSQL uses explicit migration v4."""
        with self._connection:
            self._connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS schedule_definitions (
                    schedule_id TEXT PRIMARY KEY REFERENCES schedules(schedule_id) ON DELETE CASCADE,
                    organization_id TEXT NOT NULL REFERENCES organizations(organization_id) ON DELETE CASCADE,
                    job_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    recurrence_json TEXT NOT NULL,
                    timezone TEXT NOT NULL,
                    overlap_policy TEXT NOT NULL DEFAULT 'SKIP',
                    urls_json TEXT NOT NULL DEFAULT '[]',
                    status TEXT NOT NULL DEFAULT 'ACTIVE',
                    priority INTEGER NOT NULL DEFAULT 100,
                    max_attempts INTEGER NOT NULL DEFAULT 3,
                    next_run_at TEXT,
                    created_by TEXT REFERENCES users(user_id) ON DELETE SET NULL,
                    updated_by TEXT REFERENCES users(user_id) ON DELETE SET NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_schedule_definitions_due
                    ON schedule_definitions(status,next_run_at,schedule_id);
                CREATE TABLE IF NOT EXISTS schedule_occurrences (
                    occurrence_id TEXT PRIMARY KEY,
                    schedule_id TEXT NOT NULL REFERENCES schedules(schedule_id) ON DELETE CASCADE,
                    scheduled_for TEXT NOT NULL,
                    status TEXT NOT NULL,
                    job_id TEXT,
                    reason TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(schedule_id,scheduled_for)
                );
                CREATE INDEX IF NOT EXISTS idx_schedule_occurrences_schedule
                    ON schedule_occurrences(schedule_id,scheduled_for DESC);
                CREATE TABLE IF NOT EXISTS schedule_events (
                    event_id TEXT PRIMARY KEY,
                    schedule_id TEXT NOT NULL REFERENCES schedules(schedule_id) ON DELETE CASCADE,
                    action TEXT NOT NULL,
                    actor_user_id TEXT REFERENCES users(user_id) ON DELETE SET NULL,
                    details_json TEXT NOT NULL DEFAULT '{}',
                    occurred_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_schedule_events_schedule
                    ON schedule_events(schedule_id,occurred_at DESC);
                CREATE TABLE IF NOT EXISTS usage_import_keys (
                    source_key TEXT PRIMARY KEY,
                    usage_event_id TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )
            self._connection.execute(
                """INSERT INTO platform_extension_meta(key,value) VALUES('saas_management_schema','1')
                   ON CONFLICT(key) DO UPDATE SET value=excluded.value"""
            )

    def _schedule_scope(self, project_id: str, property_id: str, environment_id: str) -> tuple[Any, Any]:
        self._scope_row(project_id, property_id, environment_id)
        prop = next((item for item in self.list_properties(project_id) if item.property_id == property_id), None)
        env = next((item for item in self.list_environments(property_id) if item.environment_id == environment_id), None)
        if prop is None or env is None:
            raise ValueError("schedule Property/Environment scope does not exist")
        return prop, env

    def _validate_actor(self, user_id: str | None) -> None:
        if user_id is None:
            return
        row = self._connection.execute("SELECT 1 FROM users WHERE user_id=?", (user_id,)).fetchone()
        if row is None:
            raise KeyError(f"user not found: {user_id}")

    def _schedule_definition_row(self, schedule_id: str) -> Any | None:
        return self._connection.execute(
            """SELECT s.schedule_id,s.project_id,s.property_id,s.environment_id,s.name,
                      d.organization_id,d.job_type,d.payload_json,d.recurrence_json,d.timezone,
                      d.overlap_policy,d.urls_json,d.status,d.priority,d.max_attempts,d.next_run_at,
                      d.created_by,d.updated_by,d.created_at,d.updated_at
               FROM schedules s JOIN schedule_definitions d ON d.schedule_id=s.schedule_id
               WHERE s.schedule_id=?""",
            (schedule_id,),
        ).fetchone()

    def _schedule_projection(self, row: Any) -> dict[str, Any]:
        schedule_id = str(row["schedule_id"])
        stats = self._connection.execute(
            """SELECT COUNT(*) AS occurrences,
                      SUM(CASE WHEN j.status='SUCCEEDED' THEN 1 ELSE 0 END) AS succeeded,
                      SUM(CASE WHEN j.status='FAILED' THEN 1 ELSE 0 END) AS failed,
                      MAX(CASE WHEN j.completed_at IS NOT NULL THEN j.completed_at ELSE NULL END) AS last_run_at
               FROM schedule_occurrences o LEFT JOIN execution_jobs j ON j.job_id=o.job_id
               WHERE o.schedule_id=?""",
            (schedule_id,),
        ).fetchone()
        latest = self._connection.execute(
            """SELECT o.status AS occurrence_status,j.status AS job_status,j.completed_at,j.last_error
               FROM schedule_occurrences o LEFT JOIN execution_jobs j ON j.job_id=o.job_id
               WHERE o.schedule_id=? ORDER BY o.scheduled_for DESC LIMIT 1""",
            (schedule_id,),
        ).fetchone()
        return {
            "schedule_id": schedule_id,
            "organization_id": str(row["organization_id"]),
            "project_id": str(row["project_id"]),
            "property_id": str(row["property_id"]),
            "environment_id": str(row["environment_id"]),
            "name": str(row["name"]),
            "job_type": str(row["job_type"]),
            "payload": _load(row["payload_json"], {}),
            "recurrence": _load(row["recurrence_json"], {}),
            "timezone": str(row["timezone"]),
            "overlap_policy": str(row["overlap_policy"]),
            "urls": list(_load(row["urls_json"], [])),
            "status": str(row["status"]),
            "priority": int(row["priority"]),
            "max_attempts": int(row["max_attempts"]),
            "next_run_at": row["next_run_at"],
            "created_by": row["created_by"],
            "updated_by": row["updated_by"],
            "created_at": str(row["created_at"]),
            "updated_at": str(row["updated_at"]),
            "run_count": int((stats["succeeded"] or 0) + (stats["failed"] or 0)) if stats is not None else 0,
            "occurrence_count": int(stats["occurrences"] or 0) if stats is not None else 0,
            "failure_count": int(stats["failed"] or 0) if stats is not None else 0,
            "last_run_at": stats["last_run_at"] if stats is not None else None,
            "last_status": (latest["job_status"] or latest["occurrence_status"]) if latest is not None else None,
            "last_error": latest["last_error"] if latest is not None else None,
        }

    def _schedule_event(self, schedule_id: str, action: str, actor: str | None, details: dict[str, Any] | None = None) -> None:
        safe = redact_value(details or {})
        self._connection.execute(
            """INSERT INTO schedule_events(event_id,schedule_id,action,actor_user_id,details_json,occurred_at)
               VALUES(?,?,?,?,?,?)""",
            (new_id("SCE"), schedule_id, action, actor, _dump(safe), utc_now()),
        )

    def create_managed_schedule(
        self,
        *,
        project_id: str,
        property_id: str,
        environment_id: str,
        name: str,
        job_type: str,
        recurrence: dict[str, Any],
        timezone: str,
        urls: Sequence[str] = (),
        payload: dict[str, Any] | None = None,
        overlap_policy: str = "SKIP",
        priority: int = 100,
        max_attempts: int = 3,
        created_by: str | None = None,
    ) -> dict[str, Any]:
        prop, env = self._schedule_scope(project_id, property_id, environment_id)
        self._validate_actor(created_by)
        normalized_type = str(job_type).strip().upper()
        if normalized_type not in _ALLOWED_JOB_TYPES:
            raise ValueError(f"unsupported schedule job type: {job_type}")
        if priority < 0 or priority > 1000:
            raise ValueError("priority must be between 0 and 1000")
        if max_attempts < 1 or max_attempts > 100:
            raise ValueError("max_attempts must be between 1 and 100")
        safe_payload = dict(payload or {})
        validate_secret_free_mapping(safe_payload, context="schedule payload")
        if normalized_type == "SEARCH_MONITOR" and set(safe_payload) != {"query_id"}:
            raise ValueError("SEARCH_MONITOR schedule payload must contain only query_id")
        if normalized_type == "REPORT_REFRESH" and set(safe_payload) - {"surface"}:
            raise ValueError("REPORT_REFRESH schedule accepts only payload.surface")
        normalized_recurrence = normalize_recurrence(recurrence)
        zone = normalize_timezone(timezone)
        overlap = normalize_overlap_policy(overlap_policy)
        normalized_urls = normalize_scheduled_urls(
            urls,
            property_hostname=prop.hostname,
            environment_origin=env.base_origin,
        )
        if normalized_type != "AUDIT" and urls:
            raise ValueError("explicit scheduled URLs are currently supported only for AUDIT schedules")
        now = utc_now()
        next_run = next_occurrences(normalized_recurrence, zone, after=now, count=1)[0]
        schedule_id = new_id("SCH")
        organization_id = self._project_organization(project_id)
        normalized_name = str(name).strip()
        if not normalized_name:
            raise ValueError("schedule name cannot be empty")
        with self.transaction() as connection:
            connection.execute(
                """INSERT INTO schedules(
                    schedule_id,project_id,property_id,environment_id,name,kind,command_argv_json,
                    interval_minutes,daily_time,enabled,next_run_at,last_run_at,last_status,created_at
                ) VALUES(?,?,?,?,?,'API_TRIGGERED','[]',NULL,NULL,0,NULL,NULL,NULL,?)""",
                (schedule_id, project_id, property_id, environment_id, normalized_name, now),
            )
            connection.execute(
                """INSERT INTO schedule_definitions(
                    schedule_id,organization_id,job_type,payload_json,recurrence_json,timezone,overlap_policy,
                    urls_json,status,priority,max_attempts,next_run_at,created_by,updated_by,created_at,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    schedule_id, organization_id, normalized_type, _dump(redact_value(safe_payload)),
                    _dump(normalized_recurrence), zone, overlap, _dump(normalized_urls), "ACTIVE",
                    priority, max_attempts, next_run, created_by, created_by, now, now,
                ),
            )
            self._schedule_event(schedule_id, "CREATED", created_by, {"next_run_at": next_run})
        return self.get_managed_schedule(schedule_id)  # type: ignore[return-value]

    def get_managed_schedule(self, schedule_id: str) -> dict[str, Any] | None:
        row = self._schedule_definition_row(schedule_id)
        return self._schedule_projection(row) if row is not None else None

    def list_managed_schedules(
        self,
        *,
        project_id: str | None = None,
        property_id: str | None = None,
        environment_id: str | None = None,
        statuses: Sequence[str] | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        if limit < 1 or limit > 1000 or offset < 0:
            raise ValueError("invalid schedule pagination")
        clauses: list[str] = []
        values: list[Any] = []
        for field, value in (("s.project_id", project_id), ("s.property_id", property_id), ("s.environment_id", environment_id)):
            if value:
                clauses.append(f"{field}=?")
                values.append(value)
        if statuses:
            normalized = tuple(dict.fromkeys(str(item).upper() for item in statuses))
            invalid = sorted(set(normalized) - _ALLOWED_SCHEDULE_STATES)
            if invalid:
                raise ValueError("unsupported schedule state(s): " + ", ".join(invalid))
            clauses.append("d.status IN (" + ",".join("?" for _ in normalized) + ")")
            values.extend(normalized)
        sql = """SELECT s.schedule_id,s.project_id,s.property_id,s.environment_id,s.name,
                        d.organization_id,d.job_type,d.payload_json,d.recurrence_json,d.timezone,
                        d.overlap_policy,d.urls_json,d.status,d.priority,d.max_attempts,d.next_run_at,
                        d.created_by,d.updated_by,d.created_at,d.updated_at
                 FROM schedules s JOIN schedule_definitions d ON d.schedule_id=s.schedule_id"""
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY COALESCE(d.next_run_at,'9999'),s.name LIMIT ? OFFSET ?"
        values.extend((limit, offset))
        return [self._schedule_projection(row) for row in self._connection.execute(sql, values)]

    def update_managed_schedule(
        self,
        schedule_id: str,
        *,
        actor_user_id: str | None,
        name: str | None = None,
        recurrence: dict[str, Any] | None = None,
        timezone: str | None = None,
        urls: Sequence[str] | None = None,
        payload: dict[str, Any] | None = None,
        overlap_policy: str | None = None,
        priority: int | None = None,
        max_attempts: int | None = None,
    ) -> dict[str, Any]:
        current = self.get_managed_schedule(schedule_id)
        if current is None:
            raise KeyError(f"schedule not found: {schedule_id}")
        self._validate_actor(actor_user_id)
        prop, env = self._schedule_scope(current["project_id"], current["property_id"], current["environment_id"])
        next_recurrence = normalize_recurrence(recurrence) if recurrence is not None else current["recurrence"]
        next_timezone = normalize_timezone(timezone) if timezone is not None else current["timezone"]
        next_overlap = normalize_overlap_policy(overlap_policy) if overlap_policy is not None else current["overlap_policy"]
        next_urls = (
            normalize_scheduled_urls(urls, property_hostname=prop.hostname, environment_origin=env.base_origin)
            if urls is not None else tuple(current["urls"])
        )
        next_payload = dict(payload) if payload is not None else dict(current["payload"])
        validate_secret_free_mapping(next_payload, context="schedule payload")
        if current["job_type"] == "SEARCH_MONITOR" and set(next_payload) != {"query_id"}:
            raise ValueError("SEARCH_MONITOR schedule payload must contain only query_id")
        next_priority = current["priority"] if priority is None else priority
        next_attempts = current["max_attempts"] if max_attempts is None else max_attempts
        if not 0 <= int(next_priority) <= 1000:
            raise ValueError("priority must be between 0 and 1000")
        if not 1 <= int(next_attempts) <= 100:
            raise ValueError("max_attempts must be between 1 and 100")
        now = utc_now()
        next_run = current["next_run_at"]
        if recurrence is not None or timezone is not None:
            next_run = next_occurrences(next_recurrence, next_timezone, after=now, count=1)[0]
        next_name = str(name).strip() if name is not None else current["name"]
        if not next_name:
            raise ValueError("schedule name cannot be empty")
        with self.transaction() as connection:
            connection.execute("UPDATE schedules SET name=? WHERE schedule_id=?", (next_name, schedule_id))
            connection.execute(
                """UPDATE schedule_definitions SET payload_json=?,recurrence_json=?,timezone=?,overlap_policy=?,
                          urls_json=?,priority=?,max_attempts=?,next_run_at=?,updated_by=?,updated_at=?
                   WHERE schedule_id=?""",
                (
                    _dump(redact_value(next_payload)), _dump(next_recurrence), next_timezone, next_overlap,
                    _dump(next_urls), int(next_priority), int(next_attempts), next_run, actor_user_id, now, schedule_id,
                ),
            )
            self._schedule_event(schedule_id, "UPDATED", actor_user_id, {"next_run_at": next_run})
        return self.get_managed_schedule(schedule_id)  # type: ignore[return-value]

    def set_managed_schedule_status(self, schedule_id: str, state: str, *, actor_user_id: str | None) -> dict[str, Any]:
        current = self.get_managed_schedule(schedule_id)
        if current is None:
            raise KeyError(f"schedule not found: {schedule_id}")
        self._validate_actor(actor_user_id)
        normalized = state.strip().upper()
        if normalized not in _ALLOWED_SCHEDULE_STATES:
            raise ValueError(f"unsupported schedule state: {state}")
        now = utc_now()
        next_run = current["next_run_at"]
        if normalized == "ACTIVE":
            next_run = next_occurrences(current["recurrence"], current["timezone"], after=now, count=1)[0]
        elif normalized in {"PAUSED", "DISABLED", "COMPLETED"}:
            next_run = None
        with self.transaction() as connection:
            connection.execute(
                "UPDATE schedule_definitions SET status=?,next_run_at=?,updated_by=?,updated_at=? WHERE schedule_id=?",
                (normalized, next_run, actor_user_id, now, schedule_id),
            )
            self._schedule_event(schedule_id, normalized, actor_user_id, {"next_run_at": next_run})
        return self.get_managed_schedule(schedule_id)  # type: ignore[return-value]

    def duplicate_managed_schedule(self, schedule_id: str, *, name: str, actor_user_id: str | None) -> dict[str, Any]:
        current = self.get_managed_schedule(schedule_id)
        if current is None:
            raise KeyError(f"schedule not found: {schedule_id}")
        return self.create_managed_schedule(
            project_id=current["project_id"],
            property_id=current["property_id"],
            environment_id=current["environment_id"],
            name=name,
            job_type=current["job_type"],
            recurrence=current["recurrence"],
            timezone=current["timezone"],
            urls=current["urls"],
            payload=current["payload"],
            overlap_policy=current["overlap_policy"],
            priority=current["priority"],
            max_attempts=current["max_attempts"],
            created_by=actor_user_id,
        )

    def schedule_next_occurrences(self, schedule_id: str, *, count: int = 10) -> tuple[str, ...]:
        item = self.get_managed_schedule(schedule_id)
        if item is None:
            raise KeyError(f"schedule not found: {schedule_id}")
        return next_occurrences(item["recurrence"], item["timezone"], after=utc_now(), count=count)

    def list_schedule_runs(self, schedule_id: str, *, limit: int = 100) -> list[dict[str, Any]]:
        if self.get_managed_schedule(schedule_id) is None:
            raise KeyError(f"schedule not found: {schedule_id}")
        rows = self._connection.execute(
            """SELECT o.occurrence_id,o.schedule_id,o.scheduled_for,o.status AS occurrence_status,
                      o.reason,o.created_at,o.updated_at,o.job_id,j.status AS job_status,j.attempts,
                      j.max_attempts,j.requested_by,j.started_at,j.completed_at,j.result_ref,j.last_error
               FROM schedule_occurrences o LEFT JOIN execution_jobs j ON j.job_id=o.job_id
               WHERE o.schedule_id=? ORDER BY o.scheduled_for DESC LIMIT ?""",
            (schedule_id, limit),
        ).fetchall()
        return [dict(row) for row in rows]

    def list_schedule_events(self, schedule_id: str, *, limit: int = 100) -> list[dict[str, Any]]:
        rows = self._connection.execute(
            "SELECT * FROM schedule_events WHERE schedule_id=? ORDER BY occurred_at DESC LIMIT ?",
            (schedule_id, limit),
        ).fetchall()
        return [
            {**dict(row), "details": _load(row["details_json"], {})}
            for row in rows
        ]

    def _active_overlap_exists(self, schedule_id: str, occurrence_id: str) -> bool:
        row = self._connection.execute(
            """SELECT 1 FROM schedule_occurrences o JOIN execution_jobs j ON j.job_id=o.job_id
               WHERE o.schedule_id=? AND o.occurrence_id<>?
                 AND j.status IN ('QUEUED','CLAIMED','RUNNING') LIMIT 1""",
            (schedule_id, occurrence_id),
        ).fetchone()
        return row is not None

    def materialize_due_schedules(self, *, now: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        """Turn due schedules into durable occurrences and idempotent execution jobs.

        The unique ``(schedule_id, scheduled_for)`` identity plus execution-job
        idempotency makes this safe when several scheduler/worker processes poll the
        same PostgreSQL authority. Missed historical slots do not burst after an
        outage: each poll materializes the current due slot and advances from ``now``.
        """
        cutoff = _iso(now, field="now") or utc_now()
        rows = self._connection.execute(
            """SELECT s.schedule_id FROM schedules s JOIN schedule_definitions d ON d.schedule_id=s.schedule_id
               WHERE d.status='ACTIVE' AND d.next_run_at IS NOT NULL AND d.next_run_at<=?
               ORDER BY d.next_run_at,s.schedule_id LIMIT ?""",
            (cutoff, limit),
        ).fetchall()
        results: list[dict[str, Any]] = []
        for selected in rows:
            schedule_id = str(selected["schedule_id"])
            item = self.get_managed_schedule(schedule_id)
            if item is None or not item["next_run_at"]:
                continue
            scheduled_for = str(item["next_run_at"])
            occurrence_id = new_id("OCC")
            created = utc_now()
            with self._connection:
                cursor = self._connection.execute(
                    """INSERT INTO schedule_occurrences(
                           occurrence_id,schedule_id,scheduled_for,status,job_id,reason,created_at,updated_at
                       ) VALUES(?,?,?,'PENDING',NULL,NULL,?,?)
                       ON CONFLICT(schedule_id,scheduled_for) DO NOTHING""",
                    (occurrence_id, schedule_id, scheduled_for, created, created),
                )
            if cursor.rowcount == 0:
                existing = self._connection.execute(
                    "SELECT occurrence_id FROM schedule_occurrences WHERE schedule_id=? AND scheduled_for=?",
                    (schedule_id, scheduled_for),
                ).fetchone()
                if existing is None:
                    continue
                occurrence_id = str(existing["occurrence_id"])
            next_run = next_occurrences(item["recurrence"], item["timezone"], after=cutoff, count=1)[0]
            with self._connection:
                self._connection.execute(
                    """UPDATE schedule_definitions SET next_run_at=?,updated_at=?
                       WHERE schedule_id=? AND next_run_at=? AND status='ACTIVE'""",
                    (next_run, utc_now(), schedule_id, scheduled_for),
                )
            occurrence = self._connection.execute(
                "SELECT * FROM schedule_occurrences WHERE occurrence_id=?", (occurrence_id,)
            ).fetchone()
            if occurrence is None or str(occurrence["status"]) != "PENDING":
                continue
            if item["overlap_policy"] == "SKIP" and self._active_overlap_exists(schedule_id, occurrence_id):
                with self._connection:
                    self._connection.execute(
                        "UPDATE schedule_occurrences SET status='SKIPPED',reason=?,updated_at=? WHERE occurrence_id=? AND status='PENDING'",
                        ("previous schedule execution is still active", utc_now(), occurrence_id),
                    )
                results.append({"occurrence_id": occurrence_id, "schedule_id": schedule_id, "status": "SKIPPED"})
                continue
            payload = dict(item["payload"])
            if item["job_type"] == "AUDIT":
                payload["urls"] = list(item["urls"])
            try:
                job = self.enqueue_execution_job(
                    project_id=item["project_id"],
                    property_id=item["property_id"],
                    environment_id=item["environment_id"],
                    job_type=item["job_type"],
                    payload=payload,
                    requested_by=item["created_by"],
                    idempotency_key=f"schedule:{schedule_id}:{scheduled_for}",
                    priority=item["priority"],
                    max_attempts=item["max_attempts"],
                )
            except Exception as exc:
                with self._connection:
                    self._connection.execute(
                        "UPDATE schedule_occurrences SET status='ERROR',reason=?,updated_at=? WHERE occurrence_id=?",
                        (str(exc)[:500], utc_now(), occurrence_id),
                    )
                results.append({"occurrence_id": occurrence_id, "schedule_id": schedule_id, "status": "ERROR"})
                continue
            with self._connection:
                self._connection.execute(
                    "UPDATE schedule_occurrences SET status='ENQUEUED',job_id=?,updated_at=? WHERE occurrence_id=?",
                    (job.job_id, utc_now(), occurrence_id),
                )
            results.append({"occurrence_id": occurrence_id, "schedule_id": schedule_id, "status": "ENQUEUED", "job_id": job.job_id})
        return results

    def reconcile_schedule_job(self, job_id: str) -> None:
        row = self._connection.execute(
            "SELECT occurrence_id,schedule_id FROM schedule_occurrences WHERE job_id=?", (job_id,)
        ).fetchone()
        if row is None:
            return
        job = self.get_execution_job(job_id)
        if job is None:
            return
        mapped = "COMPLETED" if job.status == "SUCCEEDED" else "FAILED" if job.status == "FAILED" else "ENQUEUED"
        with self._connection:
            self._connection.execute(
                "UPDATE schedule_occurrences SET status=?,reason=?,updated_at=? WHERE occurrence_id=?",
                (mapped, job.last_error, utc_now(), str(row["occurrence_id"])),
            )

    def record_usage_once(
        self,
        *,
        source_key: str,
        organization_id: str,
        category: str,
        quantity: float,
        unit: str,
        project_id: str | None = None,
        property_id: str | None = None,
        audit_id: str | None = None,
        cost_estimate: float | None = None,
        currency: str | None = None,
        provider: str | None = None,
        metadata: dict[str, Any] | None = None,
        occurred_at: str | None = None,
    ) -> dict[str, Any]:
        safe_metadata = dict(redact_value(metadata or {}))
        validate_secret_free_mapping(safe_metadata, context="usage metadata")
        source = source_key.strip()
        if not source or len(source) > 500:
            raise ValueError("usage source_key must contain 1..500 characters")
        if project_id and self._project_organization(project_id) != organization_id:
            raise ValueError("usage project is outside organization")
        if property_id and project_id and self._property_project(property_id) != project_id:
            raise ValueError("usage property is outside project")
        event_id = new_id("USE")
        timestamp = _iso(occurred_at, field="occurred_at") if occurred_at else utc_now()
        with self.transaction() as connection:
            marker = connection.execute(
                """INSERT INTO usage_import_keys(source_key,usage_event_id,created_at) VALUES(?,?,?)
                   ON CONFLICT(source_key) DO NOTHING""",
                (source, event_id, utc_now()),
            )
            if marker.rowcount == 0:
                existing = connection.execute(
                    """SELECT u.* FROM usage_import_keys k JOIN usage_events u ON u.usage_event_id=k.usage_event_id
                       WHERE k.source_key=?""",
                    (source,),
                ).fetchone()
                return dict(existing) if existing is not None else {"usage_event_id": None, "source_key": source}
            connection.execute(
                """INSERT INTO usage_events(
                    usage_event_id,organization_id,project_id,property_id,audit_id,occurred_at,category,
                    quantity,unit,cost_estimate,currency,provider,metadata_json
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    event_id, organization_id, project_id, property_id, audit_id, timestamp, category,
                    float(quantity), unit, cost_estimate, currency, provider, _dump(safe_metadata),
                ),
            )
        return {"usage_event_id": event_id, "source_key": source}

    def usage_analytics(
        self,
        organization_id: str,
        *,
        project_id: str | None = None,
        property_id: str | None = None,
        environment_id: str | None = None,
        url: str | None = None,
        user_id: str | None = None,
        provider: str | None = None,
        category: str | None = None,
        operation: str | None = None,
        status: str | None = None,
        start: str | None = None,
        end: str | None = None,
        group_by: Sequence[str] = ("category", "provider"),
        limit: int = 10000,
    ) -> dict[str, Any]:
        groups = tuple(dict.fromkeys(str(item).strip().lower() for item in group_by if str(item).strip()))
        invalid = sorted(set(groups) - _ALLOWED_GROUPS)
        if invalid:
            raise ValueError("unsupported usage group(s): " + ", ".join(invalid))
        start_iso = _iso(start, field="start")
        end_iso = _iso(end, field="end")
        clauses = ["organization_id=?"]
        values: list[Any] = [organization_id]
        for field, value in (("project_id", project_id), ("property_id", property_id), ("provider", provider), ("category", category)):
            if value:
                clauses.append(f"{field}=?")
                values.append(value)
        if start_iso:
            clauses.append("occurred_at>=?")
            values.append(start_iso)
        if end_iso:
            clauses.append("occurred_at<?")
            values.append(end_iso)
        sql = "SELECT * FROM usage_events WHERE " + " AND ".join(clauses) + " ORDER BY occurred_at DESC LIMIT ?"
        values.append(max(1, min(int(limit), 50000)))
        rows = self._connection.execute(sql, values).fetchall()
        events: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            metadata = _load(item.pop("metadata_json", None), {})
            item["metadata"] = metadata
            dimensions = {
                "project": item.get("project_id"),
                "property": item.get("property_id"),
                "environment": metadata.get("environment_id"),
                "domain": metadata.get("domain"),
                "url": metadata.get("url"),
                "user": metadata.get("user_id"),
                "provider": item.get("provider"),
                "integration": metadata.get("integration"),
                "category": item.get("category"),
                "operation": metadata.get("operation"),
                "status": metadata.get("status"),
                "model": metadata.get("model"),
                "job": metadata.get("job_id"),
                "audit": item.get("audit_id"),
                "resource": metadata.get("resource_type"),
            }
            if environment_id and dimensions["environment"] != environment_id:
                continue
            if url and dimensions["url"] != url:
                continue
            if user_id and dimensions["user"] != user_id:
                continue
            if operation and dimensions["operation"] != operation:
                continue
            if status and dimensions["status"] != status:
                continue
            item["dimensions"] = dimensions
            events.append(item)

        def blank() -> dict[str, Any]:
            return {
                "event_count": 0,
                "quantity_by_unit": {},
                "cost_by_currency": {},
                "cost_known_events": 0,
                "cost_unknown_events": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "reasoning_tokens": 0,
                "total_tokens": 0,
                "retry_count": 0,
                "fallback_count": 0,
                "failure_count": 0,
                "duration_ms": 0,
            }

        def add(bucket: dict[str, Any], event: dict[str, Any]) -> None:
            bucket["event_count"] += 1
            unit = str(event.get("unit") or "unknown")
            bucket["quantity_by_unit"][unit] = bucket["quantity_by_unit"].get(unit, 0.0) + float(event.get("quantity") or 0.0)
            cost = event.get("cost_estimate")
            currency = event.get("currency")
            if cost is None:
                bucket["cost_unknown_events"] += 1
            else:
                bucket["cost_known_events"] += 1
                key = str(currency or "UNSPECIFIED")
                bucket["cost_by_currency"][key] = bucket["cost_by_currency"].get(key, 0.0) + float(cost)
            metadata = event["metadata"]
            for key in ("input_tokens", "output_tokens", "reasoning_tokens", "total_tokens", "duration_ms"):
                value = metadata.get(key)
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    bucket[key] += value
            bucket["retry_count"] += int(bool(metadata.get("retry")) or str(metadata.get("decision", "")).upper() == "RETRY")
            bucket["fallback_count"] += int(bool(metadata.get("fallback_from_provider")) or str(metadata.get("decision", "")).upper().startswith("FALLBACK"))
            bucket["failure_count"] += int(str(metadata.get("status", "")).upper() in {"FAILED", "FAIL", "ERROR", "TIMEOUT"})

        summary = blank()
        grouped: dict[tuple[Any, ...], dict[str, Any]] = {}
        for event in events:
            add(summary, event)
            key = tuple(event["dimensions"].get(field) for field in groups)
            bucket = grouped.setdefault(key, blank())
            add(bucket, event)
        group_rows = []
        for key, bucket in grouped.items():
            group_rows.append({"dimensions": dict(zip(groups, key)), **bucket})
        group_rows.sort(key=lambda item: (-item["event_count"], str(item["dimensions"])))
        coverage = {
            "events": len(events),
            "with_url": sum(1 for item in events if item["dimensions"].get("url")),
            "with_user": sum(1 for item in events if item["dimensions"].get("user")),
            "with_environment": sum(1 for item in events if item["dimensions"].get("environment")),
            "with_provider": sum(1 for item in events if item.get("provider")),
            "with_cost": sum(1 for item in events if item.get("cost_estimate") is not None),
        }
        return {"summary": summary, "groups": group_rows, "coverage": coverage, "event_limit": limit}
