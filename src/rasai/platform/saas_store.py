"""Composition adapters that add SaaS management without changing legacy stores."""
from __future__ import annotations

from pathlib import Path

from .saas_management import SaaSManagementMixin
from .secure_store import SecurePlatformStore


class SaaSSecurePlatformStore(SaaSManagementMixin, SecurePlatformStore):
    """SQLite control plane with additive SaaS scheduling/analytics schema."""

    def __init__(self, database: str | Path) -> None:
        super().__init__(database)
        self._initialize_saas_management_extensions()


class SaaSPostgreSQLStoreMixin(SaaSManagementMixin):
    """Marker mixin for PostgreSQL composition; migrations remain explicit."""

    pass
