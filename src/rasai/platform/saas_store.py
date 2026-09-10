"""Composition adapters that add SaaS management without changing legacy stores."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .saas_management import SaaSManagementMixin
from .saas_scheduler_runtime import materialize_due_schedules
from .secure_store import SecurePlatformStore


class SaaSSecurePlatformStore(SaaSManagementMixin, SecurePlatformStore):
    """SQLite control plane with additive SaaS scheduling/analytics schema."""

    def __init__(self, database: str | Path) -> None:
        super().__init__(database)
        self._initialize_saas_management_extensions()

    def materialize_due_schedules(self, *, now: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        return materialize_due_schedules(self, now=now, limit=limit)


class SaaSPostgreSQLStoreMixin(SaaSManagementMixin):
    """Marker mixin for PostgreSQL composition; migrations remain explicit."""

    def materialize_due_schedules(self, *, now: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        return materialize_due_schedules(self, now=now, limit=limit)
