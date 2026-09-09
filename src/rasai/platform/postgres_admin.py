"""Explicit schema administration for the PostgreSQL control plane.

Normal application startup validates schema compatibility but never mutates hosted
schema.  Migrations are an explicit deployment/development operation through this
module and the public platform CLI.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .postgres_compat import connect_postgres, redact_postgres_url
from .postgres_migrations import POSTGRES_SCHEMA_VERSION, apply_postgres_migrations


@dataclass(frozen=True, slots=True)
class PostgreSQLSchemaStatus:
    database: str
    current_version: int
    supported_version: int
    state: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "database": self.database,
            "current_version": self.current_version,
            "supported_version": self.supported_version,
            "state": self.state,
        }


def current_postgres_schema_version(connection: Any) -> int:
    exists = connection.execute(
        "SELECT to_regclass('public.platform_schema_migrations') AS table_name"
    ).fetchone()
    if exists is None or exists[0] is None:
        return 0
    row = connection.execute(
        "SELECT COALESCE(MAX(version),0) AS version FROM platform_schema_migrations"
    ).fetchone()
    return int(row[0]) if row is not None else 0


def schema_state(version: int) -> str:
    if version == POSTGRES_SCHEMA_VERSION:
        return "CURRENT"
    if version == 0:
        return "UNINITIALIZED"
    if version < POSTGRES_SCHEMA_VERSION:
        return "MIGRATION_REQUIRED"
    return "NEWER_THAN_RUNTIME"


def require_current_postgres_schema(connection: Any) -> int:
    version = current_postgres_schema_version(connection)
    state = schema_state(version)
    if state == "CURRENT":
        return version
    if state == "NEWER_THAN_RUNTIME":
        raise RuntimeError(
            f"PostgreSQL control-plane schema {version} is newer than supported {POSTGRES_SCHEMA_VERSION}"
        )
    raise RuntimeError(
        "PostgreSQL control-plane schema is not current "
        f"(current={version}, supported={POSTGRES_SCHEMA_VERSION}); "
        "run 'rasai platform database migrate' before starting the PostgreSQL backend"
    )


def postgres_schema_status(database_url: str) -> PostgreSQLSchemaStatus:
    connection = connect_postgres(database_url)
    try:
        version = current_postgres_schema_version(connection)
        return PostgreSQLSchemaStatus(
            database=redact_postgres_url(database_url),
            current_version=version,
            supported_version=POSTGRES_SCHEMA_VERSION,
            state=schema_state(version),
        )
    finally:
        connection.close()


def migrate_postgres(database_url: str) -> tuple[PostgreSQLSchemaStatus, tuple[int, ...]]:
    """Apply pending migrations explicitly and return the resulting schema state."""

    connection = connect_postgres(database_url)
    try:
        applied = apply_postgres_migrations(connection)
        version = require_current_postgres_schema(connection)
        return (
            PostgreSQLSchemaStatus(
                database=redact_postgres_url(database_url),
                current_version=version,
                supported_version=POSTGRES_SCHEMA_VERSION,
                state="CURRENT",
            ),
            applied,
        )
    finally:
        connection.close()
