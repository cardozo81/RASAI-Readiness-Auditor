"""Database composition for the Search Intelligence monitoring repository."""
from __future__ import annotations

from pathlib import Path

from rasai.platform.database import resolve_platform_database_config

from .monitoring import SQLiteSearchMonitoringRepository


def open_search_monitoring_repository(
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
        return SQLiteSearchMonitoringRepository(config.sqlite_database)
    from .monitoring_postgres import PostgreSQLSearchMonitoringRepository

    assert config.database_url is not None
    return PostgreSQLSearchMonitoringRepository(config.database_url)
