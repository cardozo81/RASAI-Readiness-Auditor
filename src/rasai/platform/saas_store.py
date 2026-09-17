"""Composition adapters for SaaS management, scheduling and usage analytics."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from rasai.execution_contract import validate_execution_job_payload

from .consumption import usage_analytics as aggregate_usage
from .property_semantic_profiles import PropertySemanticProfileStoreMixin
from .saas_management import SaaSManagementMixin
from .saas_scheduler_runtime import materialize_due_schedules
from .secure_store import SecurePlatformStore

_PROPERTY_PROFILE_TO_AUDIT_PAYLOAD = {
    "business_sector": "property_business_sector",
    "business_description": "property_business_description",
    "primary_offering": "property_primary_offering",
    "target_audience_profile": "property_target_audience_profile",
    "primary_goal": "property_primary_goal",
    "positioning": "property_positioning",
}


class _SaaSRuntimeMixin:
    def _effective_audit_payload(self, property_id: str, payload: dict[str, Any] | None) -> dict[str, Any]:
        """Materialize Property profile values without overriding explicit job choices.

        The durable execution job is the boundary: after this method returns, the job
        contains the exact six semantic values that the worker/AUD will use. Later edits
        to the reusable Property profile therefore cannot mutate an already queued AUD.
        An explicitly supplied ``auto`` is an intentional override and is preserved.
        """
        effective = dict(payload or {})
        profile = self.get_property_semantic_profile(property_id)
        for profile_name, payload_name in _PROPERTY_PROFILE_TO_AUDIT_PAYLOAD.items():
            if payload_name not in effective:
                effective[payload_name] = str(profile.get(profile_name) or "auto")
        return effective

    def enqueue_execution_job(self, **kwargs: Any):
        if str(kwargs.get("job_type") or "").strip().upper() == "AUDIT":
            property_id = str(kwargs.get("property_id") or "").strip()
            kwargs["payload"] = self._effective_audit_payload(property_id, kwargs.get("payload"))
        return super().enqueue_execution_job(**kwargs)  # type: ignore[misc]

    def create_managed_schedule(self, **kwargs: Any) -> dict[str, Any]:
        validate_execution_job_payload(kwargs.get("job_type", ""), kwargs.get("payload") or {})
        return super().create_managed_schedule(**kwargs)  # type: ignore[misc]

    def update_managed_schedule(self, schedule_id: str, **kwargs: Any) -> dict[str, Any]:
        if kwargs.get("payload") is not None:
            current = self.get_managed_schedule(schedule_id)
            if current is None:
                raise KeyError(f"schedule not found: {schedule_id}")
            validate_execution_job_payload(current["job_type"], kwargs["payload"])
        return super().update_managed_schedule(schedule_id, **kwargs)  # type: ignore[misc]

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


class SaaSSecurePlatformStore(
    _SaaSRuntimeMixin,
    PropertySemanticProfileStoreMixin,
    SaaSManagementMixin,
    SecurePlatformStore,
):
    """SQLite control plane with SaaS scheduling, analytics and property context."""

    def __init__(self, database: str | Path) -> None:
        super().__init__(database)
        self._initialize_saas_management_extensions()
        self._initialize_property_semantic_profiles_sqlite()


class SaaSPostgreSQLStoreMixin(
    _SaaSRuntimeMixin,
    PropertySemanticProfileStoreMixin,
    SaaSManagementMixin,
):
    """PostgreSQL mixin; schema changes remain explicit through migrations."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)  # type: ignore[misc]
        from .postgres_semantic_profile_migration import require_current_semantic_profile_schema

        require_current_semantic_profile_schema(self._connection)
