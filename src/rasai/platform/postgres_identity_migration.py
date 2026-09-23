"""Explicit PostgreSQL migration contract for external identity links."""
from __future__ import annotations

from typing import Any

IDENTITY_SCHEMA_VERSION = 1


def current_identity_schema_version(connection: Any) -> int:
    exists = connection.execute(
        "SELECT to_regclass('public.platform_identity_schema_migrations') AS table_name"
    ).fetchone()
    if exists is None or exists[0] is None:
        return 0
    row = connection.execute(
        "SELECT COALESCE(MAX(version),0) AS version FROM platform_identity_schema_migrations"
    ).fetchone()
    return int(row[0]) if row is not None else 0


def require_current_identity_schema(connection: Any) -> int:
    version = current_identity_schema_version(connection)
    if version == IDENTITY_SCHEMA_VERSION:
        return version
    if version > IDENTITY_SCHEMA_VERSION:
        raise RuntimeError(
            f"PostgreSQL identity schema {version} is newer than supported {IDENTITY_SCHEMA_VERSION}"
        )
    raise RuntimeError(
        "PostgreSQL identity schema is not current "
        f"(current={version}, supported={IDENTITY_SCHEMA_VERSION}); "
        "run 'rasai platform database migrate' before starting the PostgreSQL backend"
    )


def apply_identity_migrations(connection: Any) -> tuple[int, ...]:
    connection.execute(
        """CREATE TABLE IF NOT EXISTS platform_identity_schema_migrations (
            version INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            applied_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )"""
    )
    applied = {
        int(row[0])
        for row in connection.execute("SELECT version FROM platform_identity_schema_migrations")
    }
    unknown = sorted(version for version in applied if version > IDENTITY_SCHEMA_VERSION)
    if unknown:
        raise RuntimeError(
            f"PostgreSQL identity schema {max(unknown)} is newer than supported {IDENTITY_SCHEMA_VERSION}"
        )
    if 1 in applied:
        return ()
    with connection:
        connection.execute(
            """CREATE TABLE IF NOT EXISTS external_identities (
                external_identity_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                issuer TEXT NOT NULL,
                subject TEXT NOT NULL,
                email TEXT,
                created_at TEXT NOT NULL,
                UNIQUE(issuer, subject)
            )"""
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_external_identity_user ON external_identities(user_id,issuer)"
        )
        connection.execute(
            "INSERT INTO platform_identity_schema_migrations(version,name) VALUES(1,'external_identity_links')"
        )
        connection.execute(
            """INSERT INTO platform_extension_meta(key,value) VALUES('identity_schema','1')
               ON CONFLICT(key) DO UPDATE SET value=EXCLUDED.value"""
        )
    return (1,)
