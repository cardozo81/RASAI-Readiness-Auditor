"""PostgreSQL SaaS management composition.

The underlying PostgreSQL store still owns connection validation and explicit schema
governance. This class adds only domain methods; schema v4 must already be migrated.
"""
from __future__ import annotations

from .postgres_store import PostgreSQLPlatformStore
from .saas_management import SaaSManagementMixin


class SaaSPostgreSQLPlatformStore(SaaSManagementMixin, PostgreSQLPlatformStore):
    pass
