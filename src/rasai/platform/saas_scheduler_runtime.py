"""Crash-safe schedule occurrence materialization into durable execution jobs."""
from __future__ import annotations

from typing import Any

from .saas_scheduling import next_occurrences
from .store import new_id, utc_now


def _advance(store: Any, item: dict[str, Any], scheduled_for: str, cutoff: str) -> str:
    next_run = next_occurrences(item["recurrence"], item["timezone"], after=cutoff, count=1)[0]
    with store._connection:
        store._connection.execute(
            """UPDATE schedule_definitions SET next_run_at=?,updated_at=?
               WHERE schedule_id=? AND next_run_at=? AND status='ACTIVE'""",
            (next_run, utc_now(), item["schedule_id"], scheduled_for),
        )
    return next_run


def _process_occurrence(store: Any, item: dict[str, Any], occurrence_id: str, scheduled_for: str) -> dict[str, Any]:
    if item["overlap_policy"] == "SKIP" and store._active_overlap_exists(item["schedule_id"], occurrence_id):
        with store._connection:
            store._connection.execute(
                "UPDATE schedule_occurrences SET status='SKIPPED',reason=?,updated_at=? WHERE occurrence_id=? AND status='PENDING'",
                ("previous schedule execution is still active", utc_now(), occurrence_id),
            )
        return {"occurrence_id": occurrence_id, "schedule_id": item["schedule_id"], "status": "SKIPPED"}

    payload = dict(item["payload"])
    if item["job_type"] == "AUDIT":
        payload["urls"] = list(item["urls"])
    try:
        job = store.enqueue_execution_job(
            project_id=item["project_id"],
            property_id=item["property_id"],
            environment_id=item["environment_id"],
            job_type=item["job_type"],
            payload=payload,
            requested_by=item["created_by"],
            idempotency_key=f"schedule:{item['schedule_id']}:{scheduled_for}",
            priority=item["priority"],
            max_attempts=item["max_attempts"],
        )
    except Exception as exc:
        with store._connection:
            store._connection.execute(
                "UPDATE schedule_occurrences SET status='ERROR',reason=?,updated_at=? WHERE occurrence_id=? AND status='PENDING'",
                (str(exc)[:500], utc_now(), occurrence_id),
            )
        return {"occurrence_id": occurrence_id, "schedule_id": item["schedule_id"], "status": "ERROR"}
    with store._connection:
        store._connection.execute(
            """UPDATE schedule_occurrences SET status='ENQUEUED',job_id=?,updated_at=?
               WHERE occurrence_id=? AND status='PENDING'""",
            (job.job_id, utc_now(), occurrence_id),
        )
    return {"occurrence_id": occurrence_id, "schedule_id": item["schedule_id"], "status": "ENQUEUED", "job_id": job.job_id}


def materialize_due_schedules(store: Any, *, now: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    """Materialize due schedules without losing an occurrence on process crash.

    Existing PENDING occurrences are recovered first. New occurrences are unique by
    ``schedule_id + scheduled_for`` and jobs are unique by the matching idempotency
    key. The schedule cursor advances only after the occurrence reaches a durable
    terminal/enqueued state.
    """
    cutoff = store._iso(now, field="now") if hasattr(store, "_iso") else None
    if cutoff is None:
        # SaaSManagementMixin keeps the parser module-private; all stored values are
        # already UTC ISO strings, while caller supplied values are validated here.
        if now is not None:
            from datetime import UTC, datetime
            parsed = datetime.fromisoformat(str(now).replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                raise ValueError("now must include an explicit timezone")
            cutoff = parsed.astimezone(UTC).isoformat()
        else:
            cutoff = utc_now()
    limit = max(1, min(int(limit), 1000))
    results: list[dict[str, Any]] = []

    # Recover any occurrence created before a scheduler process crashed.
    pending = store._connection.execute(
        """SELECT o.occurrence_id,o.schedule_id,o.scheduled_for
           FROM schedule_occurrences o JOIN schedule_definitions d ON d.schedule_id=o.schedule_id
           WHERE o.status='PENDING' AND d.status='ACTIVE'
           ORDER BY o.scheduled_for,o.occurrence_id LIMIT ?""",
        (limit,),
    ).fetchall()
    for row in pending:
        item = store.get_managed_schedule(str(row["schedule_id"]))
        if item is None:
            continue
        result = _process_occurrence(store, item, str(row["occurrence_id"]), str(row["scheduled_for"]))
        results.append(result)
        if item.get("next_run_at") == str(row["scheduled_for"]):
            _advance(store, item, str(row["scheduled_for"]), cutoff)

    remaining = max(0, limit - len(results))
    if remaining == 0:
        return results
    rows = store._connection.execute(
        """SELECT s.schedule_id FROM schedules s JOIN schedule_definitions d ON d.schedule_id=s.schedule_id
           WHERE d.status='ACTIVE' AND d.next_run_at IS NOT NULL AND d.next_run_at<=?
           ORDER BY d.next_run_at,s.schedule_id LIMIT ?""",
        (cutoff, remaining),
    ).fetchall()
    for selected in rows:
        schedule_id = str(selected["schedule_id"])
        item = store.get_managed_schedule(schedule_id)
        if item is None or not item["next_run_at"]:
            continue
        scheduled_for = str(item["next_run_at"])
        occurrence_id = new_id("OCC")
        created = utc_now()
        with store._connection:
            cursor = store._connection.execute(
                """INSERT INTO schedule_occurrences(
                       occurrence_id,schedule_id,scheduled_for,status,job_id,reason,created_at,updated_at
                   ) VALUES(?,?,?,'PENDING',NULL,NULL,?,?)
                   ON CONFLICT(schedule_id,scheduled_for) DO NOTHING""",
                (occurrence_id, schedule_id, scheduled_for, created, created),
            )
        if cursor.rowcount == 0:
            existing = store._connection.execute(
                "SELECT occurrence_id,status FROM schedule_occurrences WHERE schedule_id=? AND scheduled_for=?",
                (schedule_id, scheduled_for),
            ).fetchone()
            if existing is None:
                continue
            occurrence_id = str(existing["occurrence_id"])
            if str(existing["status"]) != "PENDING":
                _advance(store, item, scheduled_for, cutoff)
                continue
        result = _process_occurrence(store, item, occurrence_id, scheduled_for)
        results.append(result)
        _advance(store, item, scheduled_for, cutoff)
    return results
