"""Composition adapters that add SaaS management without changing legacy stores."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .consumption import usage_analytics as aggregate_usage
from .saas_management import SaaSManagementMixin
from .saas_scheduler_runtime import materialize_due_schedules
from .secure_store import SecurePlatformStore


class _SaaSRuntimeMixin:
    def materialize_due_schedules(self, *, now: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        return materialize_due_schedules(self, now=now, limit=limit)

    def usage_analytics(self, organization_id: str, **kwargs: Any) -> dict[str, Any]:
        return aggregate_usage(self, organization_id, **kwargs)

    def _schedule_projection(self, row: Any) -> dict[str, Any]:
        item = super()._schedule_projection(row)  # type: ignore[misc]
        terminals = self._connection.execute(
            """SELECT j.status,j.result_ref,j.result_metadata_json,j.last_error,j.completed_at
               FROM schedule_occurrences o JOIN execution_jobs j ON j.job_id=o.job_id
               WHERE o.schedule_id=? AND j.status IN ('SUCCEEDED','FAILED','CANCELLED')
               ORDER BY o.scheduled_for DESC LIMIT 100""",
            (item["schedule_id"],),
        ).fetchall()
        consecutive_failures = 0
        for terminal in terminals:
            if str(terminal["status"]) != "FAILED":
                break
            consecutive_failures += 1
        item["consecutive_failures"] = consecutive_failures
        if terminals:
            latest = terminals[0]
            item["last_result_ref"] = latest["result_ref"]
            item["last_completed_at"] = latest["completed_at"]
        else:
            item["last_result_ref"] = None
            item["last_completed_at"] = None
        return item


class SaaSSecurePlatformStore(_SaaSRuntimeMixin, SaaSManagementMixin, SecurePlatformStore):
    """SQLite control plane with additive SaaS scheduling/analytics schema."""

    def __init__(self, database: str | Path) -> None:
        super().__init__(database)
        self._initialize_saas_management_extensions()


class SaaSPostgreSQLStoreMixin(_SaaSRuntimeMixin, SaaSManagementMixin):
    """PostgreSQL mixin; schema changes remain explicit through migrations."""

    pass
