from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import tempfile

import pytest

from rasai.platform.database import open_platform_store
from rasai.platform.saas_scheduling import next_occurrences, normalize_recurrence, normalize_scheduled_urls


def _scope(store):
    organization, workspace, project, prop, environment = store.ensure_local_hierarchy(
        project_name="SaaS Scheduling",
        origin="https://schedule.example.test",
    )
    user = store.get_or_create_user("Operator", email="operator-schedule@example.test")
    store.add_membership(
        organization.organization_id,
        user.user_id,
        "OPERATOR",
        workspace_id=workspace.workspace_id,
        project_id=project.project_id,
    )
    return organization, workspace, project, prop, environment, user


def test_calendar_recurrence_supports_multiple_times_weekdays_month_days_and_last_day() -> None:
    recurrence = normalize_recurrence(
        {
            "times": ["08:00", "18:00", "08:00"],
            "weekdays": [1, 2, 3, 4, 5],
        }
    )
    assert recurrence["times"] == ["08:00", "18:00"]
    occurrences = next_occurrences(
        recurrence,
        "America/Sao_Paulo",
        after="2026-09-10T16:00:00-03:00",
        count=3,
    )
    local = [datetime.fromisoformat(item).astimezone(__import__("zoneinfo").ZoneInfo("America/Sao_Paulo")) for item in occurrences]
    assert [(item.date().isoformat(), item.strftime("%H:%M")) for item in local] == [
        ("2026-09-10", "18:00"),
        ("2026-09-11", "08:00"),
        ("2026-09-11", "18:00"),
    ]

    monthly = normalize_recurrence({"times": ["06:00"], "month_days": [1, 15], "last_day": True})
    occurrences = next_occurrences(
        monthly,
        "America/Sao_Paulo",
        after="2026-09-29T12:00:00-03:00",
        count=3,
    )
    days = [datetime.fromisoformat(item).astimezone(__import__("zoneinfo").ZoneInfo("America/Sao_Paulo")).day for item in occurrences]
    assert days == [30, 1, 15]


def test_interval_window_and_dst_never_duplicate_or_shift_nonexistent_wall_time() -> None:
    recurrence = normalize_recurrence(
        {"every_minutes": 240, "window_start": "08:00", "window_end": "20:00", "weekdays": [6]}
    )
    occurrences = next_occurrences(
        recurrence,
        "America/Sao_Paulo",
        after="2026-09-11T23:59:00-03:00",
        count=4,
    )
    from zoneinfo import ZoneInfo

    local = [datetime.fromisoformat(item).astimezone(ZoneInfo("America/Sao_Paulo")) for item in occurrences]
    assert [item.strftime("%H:%M") for item in local] == ["08:00", "12:00", "16:00", "20:00"]
    assert all(item.isoweekday() == 6 for item in local)

    nonexistent = normalize_recurrence({"times": ["02:30"]})
    spring = next_occurrences(
        nonexistent,
        "America/New_York",
        after="2026-03-08T00:00:00-05:00",
        count=1,
    )[0]
    local_spring = datetime.fromisoformat(spring).astimezone(ZoneInfo("America/New_York"))
    assert local_spring.date().isoformat() == "2026-03-09"
    assert local_spring.strftime("%H:%M") == "02:30"


def test_scheduled_urls_are_same_property_normalized_and_deduplicated() -> None:
    urls = normalize_scheduled_urls(
        ["/a", "https://schedule.example.test/a#fragment", "https://schedule.example.test/b?q=1"],
        property_hostname="schedule.example.test",
        environment_origin="https://schedule.example.test",
    )
    assert urls == (
        "https://schedule.example.test/a",
        "https://schedule.example.test/b?q=1",
    )
    with pytest.raises(ValueError, match="outside Property"):
        normalize_scheduled_urls(
            ["https://other.example.test/a"],
            property_hostname="schedule.example.test",
            environment_origin="https://schedule.example.test",
        )


def test_managed_schedule_lifecycle_occurrence_idempotency_overlap_and_usage() -> None:
    with tempfile.TemporaryDirectory() as directory:
        database = Path(directory) / "platform.db"
        with open_platform_store(platform_db=database) as store:
            organization, _workspace, project, prop, environment, user = _scope(store)
            schedule = store.create_managed_schedule(
                project_id=project.project_id,
                property_id=prop.property_id,
                environment_id=environment.environment_id,
                name="Business hours",
                job_type="AUDIT",
                recurrence={
                    "every_minutes": 240,
                    "window_start": "08:00",
                    "window_end": "20:00",
                    "weekdays": [1, 2, 3, 4, 5],
                },
                timezone="America/Sao_Paulo",
                urls=["/a", "/b"],
                payload={"max_pages": 10, "device_context": "mobile", "ai_provider": "none"},
                created_by=user.user_id,
            )
            assert schedule["status"] == "ACTIVE"
            assert schedule["urls"] == [
                "https://schedule.example.test/a",
                "https://schedule.example.test/b",
            ]
            assert schedule["overlap_policy"] == "SKIP"

            due = "2026-09-10T12:00:00+00:00"
            store._connection.execute(
                "UPDATE schedule_definitions SET next_run_at=? WHERE schedule_id=?",
                (due, schedule["schedule_id"]),
            )
            store._connection.commit()
            first = store.materialize_due_schedules(now="2026-09-10T12:01:00+00:00")
            assert first and first[0]["status"] == "ENQUEUED"
            job_id = first[0]["job_id"]
            job = store.get_execution_job(job_id)
            assert job is not None
            assert job.payload["urls"] == schedule["urls"]

            # Re-running the scheduler cannot duplicate the first occurrence/job.
            store._connection.execute(
                "UPDATE schedule_definitions SET next_run_at=? WHERE schedule_id=?",
                (due, schedule["schedule_id"]),
            )
            store._connection.commit()
            store.materialize_due_schedules(now="2026-09-10T12:02:00+00:00")
            rows = store._connection.execute(
                "SELECT * FROM schedule_occurrences WHERE schedule_id=? AND scheduled_for=?",
                (schedule["schedule_id"], due),
            ).fetchall()
            assert len(rows) == 1
            jobs = store.list_execution_jobs(project_id=project.project_id, limit=100)
            assert len([item for item in jobs if item.idempotency_key == f"schedule:{schedule['schedule_id']}:{due}"]) == 1

            # An active prior job causes a new due slot to SKIP under the default policy.
            next_due = "2026-09-10T16:00:00+00:00"
            store._connection.execute(
                "UPDATE schedule_definitions SET next_run_at=? WHERE schedule_id=?",
                (next_due, schedule["schedule_id"]),
            )
            store._connection.commit()
            second = store.materialize_due_schedules(now="2026-09-10T16:01:00+00:00")
            assert second and second[0]["status"] == "SKIPPED"

            paused = store.set_managed_schedule_status(schedule["schedule_id"], "PAUSED", actor_user_id=user.user_id)
            assert paused["next_run_at"] is None
            resumed = store.set_managed_schedule_status(schedule["schedule_id"], "ACTIVE", actor_user_id=user.user_id)
            assert resumed["next_run_at"] is not None
            duplicate = store.duplicate_managed_schedule(
                schedule["schedule_id"], name="Business hours copy", actor_user_id=user.user_id
            )
            assert duplicate["schedule_id"] != schedule["schedule_id"]
            assert duplicate["urls"] == schedule["urls"]

            store.record_usage_once(
                source_key="test:ai:1",
                organization_id=organization.organization_id,
                project_id=project.project_id,
                property_id=prop.property_id,
                category="AI_PROVIDER_CALL",
                quantity=1,
                unit="call",
                cost_estimate=0.25,
                currency="USD",
                provider="openai",
                metadata={
                    "environment_id": environment.environment_id,
                    "user_id": user.user_id,
                    "url": "https://schedule.example.test/a",
                    "domain": "schedule.example.test",
                    "operation": "SEMANTIC_ANALYSIS",
                    "resource_type": "AI",
                    "model": "example-model",
                    "status": "SUCCESS",
                    "input_tokens": 100,
                    "output_tokens": 20,
                    "total_tokens": 120,
                    "duration_ms": 500,
                },
                occurred_at="2026-09-10T10:00:00-03:00",
            )
            store.record_usage_once(
                source_key="test:integration:1",
                organization_id=organization.organization_id,
                project_id=project.project_id,
                property_id=prop.property_id,
                category="INTEGRATION_CALL",
                quantity=1,
                unit="call",
                provider="PAGESPEED_INSIGHTS",
                metadata={
                    "environment_id": environment.environment_id,
                    "user_id": user.user_id,
                    "url": "https://schedule.example.test/b",
                    "domain": "schedule.example.test",
                    "operation": "WEB_PERFORMANCE",
                    "resource_type": "INTEGRATION",
                    "status": "ERROR",
                },
                occurred_at="2026-09-10T11:00:00-03:00",
            )
            analytics = store.usage_analytics(
                organization.organization_id,
                project_id=project.project_id,
                property_id=prop.property_id,
                environment_id=environment.environment_id,
                start="2026-09-10T00:00:00-03:00",
                end="2026-09-11T00:00:00-03:00",
                group_by=("url", "user", "provider", "category"),
            )
            assert analytics["summary"]["event_count"] == 2
            assert analytics["summary"]["total_tokens"] == 120
            assert analytics["summary"]["cost_by_currency"] == {"USD": 0.25}
            assert analytics["summary"]["cost_unknown_events"] == 1
            assert analytics["summary"]["failure_count"] == 1
            assert analytics["coverage"]["with_url"] == 2
            assert len(analytics["groups"]) == 2
