"""PostgreSQL SaaS management composition.

The underlying PostgreSQL store still owns connection validation and explicit schema
governance. This class adds only domain methods; the SaaS schema must already be
migrated explicitly.
"""
from __future__ import annotations

from .postgres_store import PostgreSQLPlatformStore
from .saas_store import SaaSPostgreSQLStoreMixin


class SaaSPostgreSQLPlatformStore(SaaSPostgreSQLStoreMixin, PostgreSQLPlatformStore):
    pass
