"""Ordered PostgreSQL schema migrations for the RASAi product control plane.

These migrations intentionally preserve the current domain serialization contract:
ISO-8601 timestamps and canonical JSON remain text at this compatibility stage and
SQLite-style booleans remain constrained 0/1 integers.  That gives exact behavioral
parity while PostgreSQL becomes an authoritative relational backend.  Native JSONB,
boolean and timestamptz conversions can be introduced later as explicit migrations
with dedicated semantic-parity tests.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .postgres_compat import PostgresConnectionAdapter


POSTGRES_SCHEMA_VERSION = 4


@dataclass(frozen=True, slots=True)
class PostgreSQLMigration:
    version: int
    name: str
    statements: tuple[str, ...]


MIGRATIONS: tuple[PostgreSQLMigration, ...] = (
    PostgreSQLMigration(
        1,
        "control_plane_v1",
        (
            """CREATE TABLE IF NOT EXISTS platform_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )""",
            """CREATE TABLE IF NOT EXISTS organizations (
                organization_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                slug TEXT NOT NULL UNIQUE,
                status TEXT NOT NULL DEFAULT 'ACTIVE',
                created_at TEXT NOT NULL
            )""",
            """CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                display_name TEXT NOT NULL,
                email TEXT UNIQUE,
                status TEXT NOT NULL DEFAULT 'ACTIVE',
                created_at TEXT NOT NULL
            )""",
            """CREATE TABLE IF NOT EXISTS workspaces (
                workspace_id TEXT PRIMARY KEY,
                organization_id TEXT NOT NULL REFERENCES organizations(organization_id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                slug TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'ACTIVE',
                created_at TEXT NOT NULL,
                UNIQUE(organization_id, slug)
            )""",
            """CREATE TABLE IF NOT EXISTS projects (
                project_id TEXT PRIMARY KEY,
                workspace_id TEXT NOT NULL REFERENCES workspaces(workspace_id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                slug TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'ACTIVE',
                created_at TEXT NOT NULL,
                UNIQUE(workspace_id, slug)
            )""",
            """CREATE TABLE IF NOT EXISTS properties (
                property_id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                canonical_origin TEXT NOT NULL,
                hostname TEXT NOT NULL,
                is_competitor INTEGER NOT NULL DEFAULT 0 CHECK (is_competitor IN (0,1)),
                status TEXT NOT NULL DEFAULT 'ACTIVE',
                created_at TEXT NOT NULL,
                UNIQUE(project_id, canonical_origin)
            )""",
            """CREATE TABLE IF NOT EXISTS environments (
                environment_id TEXT PRIMARY KEY,
                property_id TEXT NOT NULL REFERENCES properties(property_id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                kind TEXT NOT NULL,
                base_origin TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'ACTIVE',
                created_at TEXT NOT NULL,
                UNIQUE(property_id, name),
                UNIQUE(property_id, base_origin)
            )""",
            """CREATE TABLE IF NOT EXISTS memberships (
                membership_id TEXT PRIMARY KEY,
                organization_id TEXT NOT NULL REFERENCES organizations(organization_id) ON DELETE CASCADE,
                user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                role TEXT NOT NULL,
                workspace_id TEXT REFERENCES workspaces(workspace_id) ON DELETE CASCADE,
                project_id TEXT REFERENCES projects(project_id) ON DELETE CASCADE,
                created_at TEXT NOT NULL,
                UNIQUE(organization_id, user_id, role, workspace_id, project_id)
            )""",
            """CREATE TABLE IF NOT EXISTS audit_index (
                audit_id TEXT PRIMARY KEY,
                property_id TEXT NOT NULL REFERENCES properties(property_id) ON DELETE RESTRICT,
                environment_id TEXT NOT NULL REFERENCES environments(environment_id) ON DELETE RESTRICT,
                workspace_path TEXT NOT NULL UNIQUE,
                audit_db_sha256 TEXT NOT NULL,
                event_time TEXT NOT NULL,
                status TEXT NOT NULL,
                completion_status TEXT,
                project_name TEXT NOT NULL,
                auditor_version TEXT NOT NULL,
                ruleset_version TEXT NOT NULL,
                scoring_versions_json TEXT NOT NULL,
                domains_json TEXT NOT NULL,
                devices_json TEXT NOT NULL,
                url_count INTEGER NOT NULL,
                indexed_at TEXT NOT NULL
            )""",
            "CREATE INDEX IF NOT EXISTS idx_audit_property_environment_time ON audit_index(property_id, environment_id, event_time)",
            """CREATE TABLE IF NOT EXISTS milestones (
                milestone_id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
                property_id TEXT NOT NULL REFERENCES properties(property_id) ON DELETE CASCADE,
                environment_id TEXT NOT NULL REFERENCES environments(environment_id) ON DELETE CASCADE,
                kind TEXT NOT NULL,
                occurred_at TEXT NOT NULL,
                title TEXT NOT NULL,
                description TEXT,
                release TEXT,
                commit_sha TEXT,
                branch TEXT,
                source TEXT NOT NULL,
                created_by TEXT REFERENCES users(user_id) ON DELETE SET NULL,
                tags_json TEXT NOT NULL DEFAULT '[]',
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL
            )""",
            "CREATE INDEX IF NOT EXISTS idx_milestone_property_environment_time ON milestones(property_id, environment_id, occurred_at)",
            """CREATE TABLE IF NOT EXISTS golden_baselines (
                property_id TEXT NOT NULL REFERENCES properties(property_id) ON DELETE CASCADE,
                environment_id TEXT NOT NULL REFERENCES environments(environment_id) ON DELETE CASCADE,
                audit_id TEXT NOT NULL REFERENCES audit_index(audit_id) ON DELETE RESTRICT,
                label TEXT,
                set_at TEXT NOT NULL,
                set_by TEXT REFERENCES users(user_id) ON DELETE SET NULL,
                PRIMARY KEY(property_id, environment_id)
            )""",
            """CREATE TABLE IF NOT EXISTS page_identities (
                page_identity_id TEXT PRIMARY KEY,
                property_id TEXT NOT NULL REFERENCES properties(property_id) ON DELETE CASCADE,
                canonical_name TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'ACTIVE',
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                UNIQUE(property_id, canonical_name)
            )""",
            """CREATE TABLE IF NOT EXISTS page_identity_urls (
                page_identity_id TEXT NOT NULL REFERENCES page_identities(page_identity_id) ON DELETE CASCADE,
                environment_id TEXT NOT NULL REFERENCES environments(environment_id) ON DELETE CASCADE,
                normalized_url TEXT NOT NULL,
                valid_from TEXT,
                valid_to TEXT,
                source TEXT NOT NULL DEFAULT 'MANUAL',
                created_at TEXT NOT NULL,
                PRIMARY KEY(page_identity_id, environment_id, normalized_url)
            )""",
            "CREATE INDEX IF NOT EXISTS idx_page_identity_url ON page_identity_urls(environment_id, normalized_url)",
            """CREATE TABLE IF NOT EXISTS comparison_runs (
                comparison_id TEXT PRIMARY KEY,
                milestone_id TEXT REFERENCES milestones(milestone_id) ON DELETE SET NULL,
                baseline_audit_id TEXT NOT NULL REFERENCES audit_index(audit_id) ON DELETE RESTRICT,
                current_audit_id TEXT NOT NULL REFERENCES audit_index(audit_id) ON DELETE RESTRICT,
                comparison_type TEXT NOT NULL,
                comparable INTEGER CHECK (comparable IS NULL OR comparable IN (0,1)),
                material_regressions INTEGER NOT NULL DEFAULT 0,
                material_improvements INTEGER NOT NULL DEFAULT 0,
                gate_status TEXT,
                report_path TEXT,
                manifest_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL
            )""",
            """CREATE TABLE IF NOT EXISTS schedules (
                schedule_id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
                property_id TEXT NOT NULL REFERENCES properties(property_id) ON DELETE CASCADE,
                environment_id TEXT NOT NULL REFERENCES environments(environment_id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                kind TEXT NOT NULL,
                command_argv_json TEXT NOT NULL,
                interval_minutes INTEGER,
                daily_time TEXT,
                enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0,1)),
                next_run_at TEXT,
                last_run_at TEXT,
                last_status TEXT,
                created_at TEXT NOT NULL,
                UNIQUE(project_id, name)
            )""",
            """CREATE TABLE IF NOT EXISTS alert_rules (
                alert_rule_id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
                property_id TEXT NOT NULL REFERENCES properties(property_id) ON DELETE CASCADE,
                environment_id TEXT NOT NULL REFERENCES environments(environment_id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0,1)),
                event_statuses_json TEXT NOT NULL,
                min_severity TEXT NOT NULL,
                destination TEXT NOT NULL,
                destination_env TEXT,
                created_at TEXT NOT NULL,
                UNIQUE(project_id, name)
            )""",
            """CREATE TABLE IF NOT EXISTS notifications (
                notification_id TEXT PRIMARY KEY,
                alert_rule_id TEXT REFERENCES alert_rules(alert_rule_id) ON DELETE SET NULL,
                comparison_id TEXT REFERENCES comparison_runs(comparison_id) ON DELETE SET NULL,
                milestone_id TEXT REFERENCES milestones(milestone_id) ON DELETE SET NULL,
                status TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                destination TEXT NOT NULL,
                delivery_error TEXT,
                created_at TEXT NOT NULL,
                delivered_at TEXT
            )""",
            """CREATE TABLE IF NOT EXISTS integrations (
                integration_id TEXT PRIMARY KEY,
                organization_id TEXT NOT NULL REFERENCES organizations(organization_id) ON DELETE CASCADE,
                workspace_id TEXT REFERENCES workspaces(workspace_id) ON DELETE CASCADE,
                project_id TEXT REFERENCES projects(project_id) ON DELETE CASCADE,
                property_id TEXT REFERENCES properties(property_id) ON DELETE CASCADE,
                provider TEXT NOT NULL,
                name TEXT NOT NULL,
                secret_env TEXT,
                configuration_json TEXT NOT NULL DEFAULT '{}',
                status TEXT NOT NULL DEFAULT 'ACTIVE',
                created_at TEXT NOT NULL
            )""",
            """CREATE TABLE IF NOT EXISTS external_datasets (
                dataset_id TEXT PRIMARY KEY,
                organization_id TEXT NOT NULL REFERENCES organizations(organization_id) ON DELETE CASCADE,
                project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
                property_id TEXT NOT NULL REFERENCES properties(property_id) ON DELETE CASCADE,
                environment_id TEXT NOT NULL REFERENCES environments(environment_id) ON DELETE CASCADE,
                source_type TEXT NOT NULL,
                period_start TEXT,
                period_end TEXT,
                captured_at TEXT NOT NULL,
                artifact_path TEXT,
                artifact_sha256 TEXT,
                row_count INTEGER NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}'
            )""",
            "CREATE INDEX IF NOT EXISTS idx_external_dataset_scope_time ON external_datasets(property_id, environment_id, source_type, captured_at)",
            """CREATE TABLE IF NOT EXISTS external_records (
                dataset_id TEXT NOT NULL REFERENCES external_datasets(dataset_id) ON DELETE CASCADE,
                record_id TEXT NOT NULL,
                observed_at TEXT,
                normalized_url TEXT,
                dimensions_json TEXT NOT NULL DEFAULT '{}',
                metrics_json TEXT NOT NULL DEFAULT '{}',
                metadata_json TEXT NOT NULL DEFAULT '{}',
                PRIMARY KEY(dataset_id, record_id)
            )""",
            "CREATE INDEX IF NOT EXISTS idx_external_records_url ON external_records(normalized_url)",
            """CREATE TABLE IF NOT EXISTS usage_events (
                usage_event_id TEXT PRIMARY KEY,
                organization_id TEXT NOT NULL REFERENCES organizations(organization_id) ON DELETE CASCADE,
                project_id TEXT REFERENCES projects(project_id) ON DELETE SET NULL,
                property_id TEXT REFERENCES properties(property_id) ON DELETE SET NULL,
                audit_id TEXT,
                occurred_at TEXT NOT NULL,
                category TEXT NOT NULL,
                quantity DOUBLE PRECISION NOT NULL,
                unit TEXT NOT NULL,
                cost_estimate DOUBLE PRECISION,
                currency TEXT,
                provider TEXT,
                metadata_json TEXT NOT NULL DEFAULT '{}'
            )""",
            "CREATE INDEX IF NOT EXISTS idx_usage_org_time ON usage_events(organization_id, occurred_at)",
            """INSERT INTO platform_meta(key,value) VALUES('schema_version','1')
               ON CONFLICT(key) DO UPDATE SET value=EXCLUDED.value""",
        ),
    ),
    PostgreSQLMigration(
        2,
        "canonical_scope_extensions",
        (
            """CREATE TABLE IF NOT EXISTS platform_extension_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )""",
            """CREATE TABLE IF NOT EXISTS audit_scope_links (
                audit_id TEXT NOT NULL REFERENCES audit_index(audit_id) ON DELETE CASCADE,
                property_id TEXT NOT NULL REFERENCES properties(property_id) ON DELETE RESTRICT,
                environment_id TEXT NOT NULL REFERENCES environments(environment_id) ON DELETE RESTRICT,
                origin TEXT NOT NULL,
                is_primary INTEGER NOT NULL DEFAULT 0 CHECK (is_primary IN (0,1)),
                linked_at TEXT NOT NULL,
                PRIMARY KEY(audit_id, property_id, environment_id)
            )""",
            "CREATE INDEX IF NOT EXISTS idx_audit_scope_property_environment ON audit_scope_links(property_id, environment_id, audit_id)",
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_audit_scope_single_primary ON audit_scope_links(audit_id) WHERE is_primary=1",
            """INSERT INTO audit_scope_links(audit_id,property_id,environment_id,origin,is_primary,linked_at)
               SELECT a.audit_id,a.property_id,a.environment_id,e.base_origin,1,a.indexed_at
               FROM audit_index a JOIN environments e ON e.environment_id=a.environment_id
               ON CONFLICT(audit_id,property_id,environment_id) DO NOTHING""",
            """INSERT INTO platform_extension_meta(key,value) VALUES('canonical_schema','2')
               ON CONFLICT(key) DO UPDATE SET value=EXCLUDED.value""",
        ),
    ),
    PostgreSQLMigration(
        3,
        "search_monitoring",
        (
            """CREATE TABLE IF NOT EXISTS search_monitor_queries (
                query_id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
                property_id TEXT NOT NULL REFERENCES properties(property_id) ON DELETE CASCADE,
                environment_id TEXT NOT NULL REFERENCES environments(environment_id) ON DELETE CASCADE,
                query TEXT NOT NULL,
                domain_of_interest TEXT NOT NULL,
                engine TEXT NOT NULL,
                country TEXT NOT NULL,
                region TEXT,
                language TEXT NOT NULL,
                device TEXT NOT NULL,
                requested_depth INTEGER NOT NULL,
                mode TEXT NOT NULL,
                provider TEXT NOT NULL,
                competitive INTEGER NOT NULL DEFAULT 1 CHECK (competitive IN (0,1)),
                compare_content INTEGER NOT NULL DEFAULT 0 CHECK (compare_content IN (0,1)),
                max_content_pages INTEGER NOT NULL DEFAULT 3,
                ai_competitive INTEGER NOT NULL DEFAULT 0 CHECK (ai_competitive IN (0,1)),
                ai_provider TEXT NOT NULL DEFAULT 'none',
                ai_model TEXT,
                ymyl_mode TEXT NOT NULL DEFAULT 'AUTO',
                enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0,1)),
                schedule_id TEXT REFERENCES schedules(schedule_id) ON DELETE SET NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )""",
            "CREATE INDEX IF NOT EXISTS idx_search_monitor_query_scope ON search_monitor_queries(property_id,environment_id,enabled,query)",
            """CREATE TABLE IF NOT EXISTS search_monitor_runs (
                monitor_run_id TEXT PRIMARY KEY,
                query_id TEXT NOT NULL REFERENCES search_monitor_queries(query_id) ON DELETE CASCADE,
                started_at TEXT NOT NULL,
                completed_at TEXT NOT NULL,
                status TEXT NOT NULL,
                observation_id TEXT,
                collected_at TEXT,
                provider TEXT NOT NULL,
                data_mode TEXT,
                observation_status TEXT,
                domain_status TEXT NOT NULL,
                customer_position INTEGER,
                result_count INTEGER NOT NULL,
                competitor_domains_ahead_json TEXT NOT NULL,
                raw_evidence_ref TEXT,
                raw_evidence_sha256 TEXT,
                comparison_status TEXT,
                gap_codes_json TEXT NOT NULL,
                query_body_coverage DOUBLE PRECISION,
                query_title_coverage DOUBLE PRECISION,
                query_heading_coverage DOUBLE PRECISION,
                word_count INTEGER,
                jsonld_types_json TEXT NOT NULL,
                ai_state TEXT,
                ai_provider TEXT,
                ai_model TEXT,
                ai_opportunity_count INTEGER NOT NULL DEFAULT 0,
                changes_json TEXT NOT NULL,
                comparable_to_previous INTEGER CHECK (comparable_to_previous IS NULL OR comparable_to_previous IN (0,1)),
                comparison_note TEXT,
                serp_http_requests INTEGER NOT NULL DEFAULT 0,
                content_http_requests INTEGER NOT NULL DEFAULT 0,
                ai_provider_calls INTEGER NOT NULL DEFAULT 0,
                manifest_ref TEXT,
                manifest_sha256 TEXT,
                error_code TEXT,
                error_message TEXT
            )""",
            "CREATE INDEX IF NOT EXISTS idx_search_monitor_runs_query_time ON search_monitor_runs(query_id,completed_at DESC)",
            "CREATE INDEX IF NOT EXISTS idx_search_monitor_runs_observation ON search_monitor_runs(observation_id)",
            """INSERT INTO platform_extension_meta(key,value) VALUES('search_monitor_schema','1')
               ON CONFLICT(key) DO UPDATE SET value=EXCLUDED.value""",
        ),
    ),
    PostgreSQLMigration(
        4,
        "saas_scheduling_consumption",
        (
            """CREATE TABLE IF NOT EXISTS schedule_definitions (
                schedule_id TEXT PRIMARY KEY REFERENCES schedules(schedule_id) ON DELETE CASCADE,
                organization_id TEXT NOT NULL REFERENCES organizations(organization_id) ON DELETE CASCADE,
                job_type TEXT NOT NULL CHECK (job_type IN ('AUDIT','SEARCH_MONITOR','REPORT_REFRESH')),
                payload_json TEXT NOT NULL DEFAULT '{}',
                recurrence_json TEXT NOT NULL,
                timezone TEXT NOT NULL,
                overlap_policy TEXT NOT NULL DEFAULT 'SKIP' CHECK (overlap_policy IN ('SKIP','QUEUE')),
                urls_json TEXT NOT NULL DEFAULT '[]',
                status TEXT NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE','PAUSED','DISABLED','COMPLETED','ERROR')),
                priority INTEGER NOT NULL DEFAULT 100 CHECK (priority BETWEEN 0 AND 1000),
                max_attempts INTEGER NOT NULL DEFAULT 3 CHECK (max_attempts BETWEEN 1 AND 100),
                next_run_at TEXT,
                created_by TEXT REFERENCES users(user_id) ON DELETE SET NULL,
                updated_by TEXT REFERENCES users(user_id) ON DELETE SET NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )""",
            "CREATE INDEX IF NOT EXISTS idx_schedule_definitions_due ON schedule_definitions(status,next_run_at,schedule_id)",
            """CREATE TABLE IF NOT EXISTS schedule_occurrences (
                occurrence_id TEXT PRIMARY KEY,
                schedule_id TEXT NOT NULL REFERENCES schedules(schedule_id) ON DELETE CASCADE,
                scheduled_for TEXT NOT NULL,
                status TEXT NOT NULL,
                job_id TEXT,
                reason TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(schedule_id,scheduled_for)
            )""",
            "CREATE INDEX IF NOT EXISTS idx_schedule_occurrences_schedule ON schedule_occurrences(schedule_id,scheduled_for DESC)",
            """CREATE TABLE IF NOT EXISTS schedule_events (
                event_id TEXT PRIMARY KEY,
                schedule_id TEXT NOT NULL REFERENCES schedules(schedule_id) ON DELETE CASCADE,
                action TEXT NOT NULL,
                actor_user_id TEXT REFERENCES users(user_id) ON DELETE SET NULL,
                details_json TEXT NOT NULL DEFAULT '{}',
                occurred_at TEXT NOT NULL
            )""",
            "CREATE INDEX IF NOT EXISTS idx_schedule_events_schedule ON schedule_events(schedule_id,occurred_at DESC)",
            """CREATE TABLE IF NOT EXISTS usage_import_keys (
                source_key TEXT PRIMARY KEY,
                usage_event_id TEXT NOT NULL,
                created_at TEXT NOT NULL
            )""",
            """INSERT INTO platform_extension_meta(key,value) VALUES('saas_management_schema','1')
               ON CONFLICT(key) DO UPDATE SET value=EXCLUDED.value""",
        ),
    ),
)


def _applied_versions(connection: PostgresConnectionAdapter) -> set[int]:
    connection.execute(
        """CREATE TABLE IF NOT EXISTS platform_schema_migrations (
            version INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            applied_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )"""
    )
    return {int(row[0]) for row in connection.execute("SELECT version FROM platform_schema_migrations")}


def apply_postgres_migrations(connection: PostgresConnectionAdapter) -> tuple[int, ...]:
    """Apply all pending migrations atomically one migration at a time."""

    applied = _applied_versions(connection)
    unknown = sorted(version for version in applied if version > POSTGRES_SCHEMA_VERSION)
    if unknown:
        raise RuntimeError(
            f"PostgreSQL control-plane schema {max(unknown)} is newer than supported {POSTGRES_SCHEMA_VERSION}"
        )
    newly_applied: list[int] = []
    for migration in MIGRATIONS:
        if migration.version in applied:
            continue
        with connection:
            for statement in migration.statements:
                connection.execute(statement)
            connection.execute(
                "INSERT INTO platform_schema_migrations(version,name) VALUES(?,?)",
                (migration.version, migration.name),
            )
        newly_applied.append(migration.version)
    return tuple(newly_applied)


def migration_versions() -> tuple[int, ...]:
    return tuple(migration.version for migration in MIGRATIONS)
