"""PostgreSQL implementation of the canonical RASAi product control plane."""
from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator

from .postgres_admin import require_current_postgres_schema
from .postgres_compat import PostgresConnectionAdapter, connect_postgres, redact_postgres_url
from .postgres_migrations import POSTGRES_SCHEMA_VERSION
from .secure_store import SecurePlatformStore


class PostgreSQLPlatformStore(SecurePlatformStore):
    """Canonical control-plane store backed by PostgreSQL.

    Domain behavior and secret-safe persistence rules are inherited from the shared
    secure canonical store; only database composition, transaction semantics and
    backend-specific governance metadata live here. Schema changes are never applied
    implicitly by normal application startup; run ``rasai platform database migrate``
    as an explicit deployment operation. Immutable audit evidence remains in
    ``AUD-*/audit.db``.
    """

    backend = "postgresql"

    def __init__(self, database_url: str) -> None:
        self.database_url = database_url
        self.database = redact_postgres_url(database_url)
        self._connection: PostgresConnectionAdapter = connect_postgres(database_url)
        try:
            require_current_postgres_schema(self._connection)
            self._validate_server_contract()
        except Exception:
            self._connection.close()
            raise

    @classmethod
    def open(cls, database_url: str) -> "PostgreSQLPlatformStore":
        return cls(database_url)

    @contextmanager
    def transaction(self) -> Iterator[PostgresConnectionAdapter]:
        with self._connection:
            yield self._connection

    def _validate_server_contract(self) -> None:
        row = self._connection.execute(
            """SELECT current_database() AS database_name,
                      current_user AS database_user,
                      current_setting('server_encoding') AS server_encoding,
                      current_setting('TimeZone') AS timezone"""
        ).fetchone()
        if row is None:
            raise RuntimeError("PostgreSQL control plane did not return server identity")
        if str(row["server_encoding"]).upper() != "UTF8":
            raise RuntimeError("PostgreSQL control plane requires UTF8 server encoding")
        timezone = str(row["timezone"]).upper()
        if timezone not in {"UTC", "ETC/UTC"}:
            raise RuntimeError(f"PostgreSQL control plane requires UTC session timezone, got {row['timezone']}")

    def health(self) -> dict[str, Any]:
        row = self._connection.execute(
            """SELECT current_database() AS database_name,
                      current_user AS database_user,
                      current_setting('server_encoding') AS server_encoding,
                      current_setting('TimeZone') AS timezone,
                      version() AS version"""
        ).fetchone()
        if row is None:
            raise RuntimeError("PostgreSQL health query returned no row")
        migration = self._connection.execute(
            "SELECT COALESCE(MAX(version),0) AS version FROM platform_schema_migrations"
        ).fetchone()
        return {
            "backend": self.backend,
            "database": str(row["database_name"]),
            "database_user": str(row["database_user"]),
            "server_encoding": str(row["server_encoding"]),
            "timezone": str(row["timezone"]),
            "server_version": str(row["version"]),
            "schema_version": int(migration["version"]) if migration is not None else 0,
            "supported_schema_version": POSTGRES_SCHEMA_VERSION,
        }

    def data_governance_status(self) -> dict[str, Any]:
        return {
            "canonical_control_plane": self.database,
            "canonical_schema": 2,
            "database_backend": self.backend,
            "postgres_schema_version": POSTGRES_SCHEMA_VERSION,
            "legacy_analytical_cache": None,
            "legacy_analytical_cache_exists": False,
            "legacy_cache_role": "NOT_APPLICABLE_TO_POSTGRESQL_AUTHORITY",
            "audit_evidence_role": "IMMUTABLE_AUD_WORKSPACES_OR_OBJECTS",
        }
