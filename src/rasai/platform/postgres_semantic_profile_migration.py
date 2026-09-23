"""PostgreSQL schema for reusable property semantic profiles."""
from __future__ import annotations

from typing import Any

from .postgres_compat import PostgresConnectionAdapter

SEMANTIC_PROFILE_SCHEMA_VERSION = 1

_STATEMENTS: tuple[str, ...] = (
    """CREATE TABLE IF NOT EXISTS semantic_profile_schema_migrations (
        version INTEGER PRIMARY KEY,
        applied_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
    )""",
    """CREATE TABLE IF NOT EXISTS property_semantic_profiles (
        property_id TEXT PRIMARY KEY REFERENCES properties(property_id) ON DELETE CASCADE,
        business_sector TEXT NOT NULL DEFAULT 'auto',
        business_description TEXT NOT NULL DEFAULT 'auto',
        primary_offering TEXT NOT NULL DEFAULT 'auto',
        target_audience_profile TEXT NOT NULL DEFAULT 'auto',
        primary_goal TEXT NOT NULL DEFAULT 'auto',
        positioning TEXT NOT NULL DEFAULT 'auto',
        revision INTEGER NOT NULL DEFAULT 1 CHECK (revision >= 1),
        updated_at TEXT NOT NULL,
        updated_by TEXT REFERENCES users(user_id) ON DELETE SET NULL
    )""",
)


def current_semantic_profile_schema_version(connection: Any) -> int:
    exists = connection.execute(
        "SELECT to_regclass('public.semantic_profile_schema_migrations') AS table_name"
    ).fetchone()
    if exists is None or exists[0] is None:
        return 0
    row = connection.execute(
        "SELECT COALESCE(MAX(version),0) AS version FROM semantic_profile_schema_migrations"
    ).fetchone()
    return int(row[0]) if row is not None else 0


def apply_semantic_profile_migrations(connection: PostgresConnectionAdapter) -> tuple[int, ...]:
    current = current_semantic_profile_schema_version(connection)
    if current > SEMANTIC_PROFILE_SCHEMA_VERSION:
        raise RuntimeError(
            f"PostgreSQL semantic profile schema {current} is newer than supported {SEMANTIC_PROFILE_SCHEMA_VERSION}"
        )
    if current == SEMANTIC_PROFILE_SCHEMA_VERSION:
        return ()
    with connection:
        for statement in _STATEMENTS:
            connection.execute(statement)
        connection.execute(
            "INSERT INTO semantic_profile_schema_migrations(version) VALUES(?) ON CONFLICT(version) DO NOTHING",
            (SEMANTIC_PROFILE_SCHEMA_VERSION,),
        )
    return (SEMANTIC_PROFILE_SCHEMA_VERSION,)


def require_current_semantic_profile_schema(connection: Any) -> int:
    version = current_semantic_profile_schema_version(connection)
    if version != SEMANTIC_PROFILE_SCHEMA_VERSION:
        raise RuntimeError(
            "PostgreSQL semantic profile schema is not current "
            f"(current={version}, supported={SEMANTIC_PROFILE_SCHEMA_VERSION}); "
            "run 'rasai platform database migrate' before starting the PostgreSQL backend"
        )
    return version
