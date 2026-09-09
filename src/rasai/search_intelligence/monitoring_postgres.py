"""PostgreSQL repository for recurring Search Intelligence monitoring."""
from __future__ import annotations

from dataclasses import replace

from rasai.platform.postgres_admin import require_current_postgres_schema
from rasai.platform.postgres_compat import connect_postgres, redact_postgres_url

from .monitoring import SearchMonitorQuery, SQLiteSearchMonitoringRepository, _now


class PostgreSQLSearchMonitoringRepository(SQLiteSearchMonitoringRepository):
    """PostgreSQL implementation of the existing SearchMonitoringRepository contract.

    The inherited mapping/read/write methods intentionally reuse the same serialized
    domain contract. Only connection validation and PostgreSQL-specific NULL equality
    are overridden. Schema migration is explicit at the Product Platform deployment
    boundary and never occurs as a side effect of Search monitoring startup.
    """

    backend = "postgresql"

    def __init__(self, database_url: str) -> None:
        self.database_url = database_url
        self.database = redact_postgres_url(database_url)
        self.connection = connect_postgres(database_url)
        try:
            require_current_postgres_schema(self.connection)
            self._validate_schema()
        except Exception:
            self.connection.close()
            raise

    @classmethod
    def open(cls, database_url: str) -> "PostgreSQLSearchMonitoringRepository":
        return cls(database_url)

    def _validate_schema(self) -> None:
        required = {"projects", "properties", "environments", "schedules", "search_monitor_queries", "search_monitor_runs"}
        rows = self.connection.execute(
            """SELECT table_name FROM information_schema.tables
               WHERE table_schema=current_schema()"""
        ).fetchall()
        existing = {str(row[0]) for row in rows}
        missing = sorted(required - existing)
        if missing:
            raise RuntimeError("PostgreSQL control plane is missing required Search monitoring tables: " + ", ".join(missing))

    def register_query(self, item: SearchMonitorQuery) -> SearchMonitorQuery:
        item.validate()
        self._validate_scope(item)
        duplicate = self.connection.execute(
            """SELECT query_id FROM search_monitor_queries
               WHERE project_id=? AND property_id=? AND environment_id=?
                 AND query=? AND engine=? AND country=? AND region IS NOT DISTINCT FROM ?
                 AND language=? AND device=? AND requested_depth=? AND domain_of_interest=?""",
            (
                item.project_id, item.property_id, item.environment_id, item.query,
                item.engine, item.country, item.region, item.language, item.device,
                item.requested_depth, item.domain_of_interest,
            ),
        ).fetchone()
        if duplicate is not None:
            raise ValueError(f"identical Search monitor query already registered: {duplicate[0]}")
        created = item.created_at or _now()
        stored = replace(item, created_at=created, updated_at=item.updated_at or created)
        with self.connection:
            self.connection.execute(
                """INSERT INTO search_monitor_queries(
                    query_id,project_id,property_id,environment_id,query,domain_of_interest,
                    engine,country,region,language,device,requested_depth,mode,provider,
                    competitive,compare_content,max_content_pages,ai_competitive,ai_provider,
                    ai_model,ymyl_mode,enabled,schedule_id,created_at,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    stored.query_id, stored.project_id, stored.property_id, stored.environment_id,
                    stored.query, stored.domain_of_interest, stored.engine, stored.country,
                    stored.region, stored.language, stored.device, stored.requested_depth,
                    stored.mode, stored.provider, int(stored.competitive), int(stored.compare_content),
                    stored.max_content_pages, int(stored.ai_competitive), stored.ai_provider,
                    stored.ai_model, stored.ymyl_mode, int(stored.enabled), stored.schedule_id,
                    stored.created_at, stored.updated_at,
                ),
            )
        return stored

    def scope_for_audit(self, audit_id: str) -> tuple[str, str] | None:
        row = self.connection.execute(
            """SELECT property_id,environment_id FROM audit_scope_links
               WHERE audit_id=? ORDER BY is_primary DESC LIMIT 1""",
            (audit_id,),
        ).fetchone()
        if row is not None:
            return str(row[0]), str(row[1])
        row = self.connection.execute(
            "SELECT property_id,environment_id FROM audit_index WHERE audit_id=?",
            (audit_id,),
        ).fetchone()
        return (str(row[0]), str(row[1])) if row is not None else None
