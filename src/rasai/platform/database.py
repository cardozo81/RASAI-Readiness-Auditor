"""Control-plane database composition for local SQLite and hosted PostgreSQL."""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Literal

from .saas_store import SaaSSecurePlatformStore
from .store import default_platform_database


PLATFORM_BACKEND_ENV = "RASAI_PLATFORM_DB_BACKEND"
PLATFORM_DATABASE_URL_ENV = "RASAI_PLATFORM_DATABASE_URL"
PlatformBackend = Literal["sqlite", "postgresql"]


@dataclass(frozen=True, slots=True)
class PlatformDatabaseConfig:
    backend: PlatformBackend
    sqlite_database: Path | None = None
    database_url: str | None = None

    @property
    def display(self) -> str:
        if self.backend == "sqlite":
            return str(self.sqlite_database)
        from .postgres_compat import redact_postgres_url

        return redact_postgres_url(str(self.database_url))


def normalize_backend(value: str | None) -> PlatformBackend:
    normalized = (value or "sqlite").strip().casefold()
    aliases = {"postgres": "postgresql", "pg": "postgresql"}
    normalized = aliases.get(normalized, normalized)
    if normalized not in {"sqlite", "postgresql"}:
        raise ValueError(f"unsupported RASAi control-plane database backend: {value}")
    return normalized  # type: ignore[return-value]


def resolve_platform_database_config(
    *,
    audits_root: str | Path = "audits",
    platform_db: str | Path | None = None,
    backend: str | None = None,
    database_url: str | None = None,
) -> PlatformDatabaseConfig:
    selected = normalize_backend(backend if backend is not None else os.getenv(PLATFORM_BACKEND_ENV))
    if selected == "sqlite":
        path = Path(platform_db) if platform_db is not None else default_platform_database(audits_root)
        return PlatformDatabaseConfig("sqlite", sqlite_database=path)
    if platform_db is not None:
        raise ValueError(
            "--platform-db is SQLite-only; PostgreSQL uses RASAI_PLATFORM_DATABASE_URL and never falls back to SQLite"
        )
    from .postgres_compat import require_postgres_url

    url = require_postgres_url(database_url if database_url is not None else os.getenv(PLATFORM_DATABASE_URL_ENV))
    return PlatformDatabaseConfig("postgresql", database_url=url)


def open_platform_store(
    *,
    audits_root: str | Path = "audits",
    platform_db: str | Path | None = None,
    backend: str | None = None,
    database_url: str | None = None,
):
    config = resolve_platform_database_config(
        audits_root=audits_root,
        platform_db=platform_db,
        backend=backend,
        database_url=database_url,
    )
    if config.backend == "sqlite":
        assert config.sqlite_database is not None
        return SaaSSecurePlatformStore(config.sqlite_database)
    from .saas_postgres_store import SaaSPostgreSQLPlatformStore

    assert config.database_url is not None
    return SaaSPostgreSQLPlatformStore(config.database_url)
