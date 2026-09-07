"""Central local control-plane database for RASAi.

``platform.db`` is a product/portfolio sidecar. It centralizes multi-user,
multi-workspace, multi-project and multi-domain metadata while keeping every
``AUD-*/audit.db`` immutable. The schema is intentionally relational and uses
stable IDs so a future PostgreSQL adapter can preserve the same contracts.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import re
import sqlite3
from typing import Any, Iterable, Iterator, Sequence
from urllib.parse import urlsplit
from uuid import uuid4

from .models import (
    AlertRule,
    AuditIndexRecord,
    Environment,
    ExternalDataset,
    Integration,
    Milestone,
    Organization,
    PageIdentity,
    Project,
    Property,
    Schedule,
    UsageEvent,
    User,
    Workspace,
)

_SCHEMA_VERSION = 1
_PLATFORM_DIR = ".rasai"
_PLATFORM_DB = "platform.db"


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex.upper()}"


def slugify(value: str, fallback: str = "item") -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", value.strip().casefold()).strip("-")
    return normalized or fallback


def normalize_origin(value: str) -> str:
    text = value.strip()
    if not text:
        raise ValueError("origin cannot be empty")
    if "://" not in text:
        text = "https://" + text
    parts = urlsplit(text)
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        raise ValueError(f"invalid HTTP(S) origin: {value}")
    port = f":{parts.port}" if parts.port else ""
    return f"{parts.scheme.lower()}://{parts.hostname.lower()}{port}"


def default_platform_database(audits_root: str | Path = "audits") -> Path:
    return Path(audits_root) / _PLATFORM_DIR / _PLATFORM_DB


def file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _load(value: str | None, default: Any) -> Any:
    if value is None:
        return default
    try:
        return json.loads(value)
    except (TypeError, ValueError, json.JSONDecodeError):
        return default


class PlatformStore:
    """SQLite implementation of the RASAi product control plane.

    The class exposes domain-level methods rather than leaking SQL to callers.
    WAL, foreign keys, a busy timeout and explicit transactions make concurrent
    local readers/writers materially safer than ad-hoc sidecar access.
    """

    def __init__(self, database: str | Path) -> None:
        self.database = Path(database)
        self.database.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(str(self.database), timeout=10.0)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys=ON")
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.execute("PRAGMA synchronous=NORMAL")
        self._connection.execute("PRAGMA busy_timeout=10000")
        self._initialize()

    @classmethod
    def open(cls, audits_root: str | Path = "audits", *, database: str | Path | None = None) -> "PlatformStore":
        return cls(database or default_platform_database(audits_root))

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> "PlatformStore":
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        try:
            self._connection.execute("BEGIN IMMEDIATE")
            yield self._connection
            self._connection.commit()
        except Exception:
            self._connection.rollback()
            raise

    def _initialize(self) -> None:
        self._connection.execute(
            "CREATE TABLE IF NOT EXISTS platform_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        row = self._connection.execute(
            "SELECT value FROM platform_meta WHERE key='schema_version'"
        ).fetchone()
        current = int(row[0]) if row else 0
        if current > _SCHEMA_VERSION:
            raise RuntimeError(
                f"platform.db schema {current} is newer than supported {_SCHEMA_VERSION}"
            )
        if current < 1:
            self._create_v1()
            current = 1
        self._connection.execute(
            "INSERT INTO platform_meta(key,value) VALUES('schema_version',?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (str(current),),
        )
        self._connection.commit()

    def _create_v1(self) -> None:
        self._connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS organizations (
                organization_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                slug TEXT NOT NULL UNIQUE,
                status TEXT NOT NULL DEFAULT 'ACTIVE',
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                display_name TEXT NOT NULL,
                email TEXT UNIQUE,
                status TEXT NOT NULL DEFAULT 'ACTIVE',
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS workspaces (
                workspace_id TEXT PRIMARY KEY,
                organization_id TEXT NOT NULL REFERENCES organizations(organization_id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                slug TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'ACTIVE',
                created_at TEXT NOT NULL,
                UNIQUE(organization_id, slug)
            );
            CREATE TABLE IF NOT EXISTS projects (
                project_id TEXT PRIMARY KEY,
                workspace_id TEXT NOT NULL REFERENCES workspaces(workspace_id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                slug TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'ACTIVE',
                created_at TEXT NOT NULL,
                UNIQUE(workspace_id, slug)
            );
            CREATE TABLE IF NOT EXISTS properties (
                property_id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                canonical_origin TEXT NOT NULL,
                hostname TEXT NOT NULL,
                is_competitor INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'ACTIVE',
                created_at TEXT NOT NULL,
                UNIQUE(project_id, canonical_origin)
            );
            CREATE TABLE IF NOT EXISTS environments (
                environment_id TEXT PRIMARY KEY,
                property_id TEXT NOT NULL REFERENCES properties(property_id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                kind TEXT NOT NULL,
                base_origin TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'ACTIVE',
                created_at TEXT NOT NULL,
                UNIQUE(property_id, name),
                UNIQUE(property_id, base_origin)
            );
            CREATE TABLE IF NOT EXISTS memberships (
                membership_id TEXT PRIMARY KEY,
                organization_id TEXT NOT NULL REFERENCES organizations(organization_id) ON DELETE CASCADE,
                user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                role TEXT NOT NULL,
                workspace_id TEXT REFERENCES workspaces(workspace_id) ON DELETE CASCADE,
                project_id TEXT REFERENCES projects(project_id) ON DELETE CASCADE,
                created_at TEXT NOT NULL,
                UNIQUE(organization_id, user_id, role, workspace_id, project_id)
            );
            CREATE TABLE IF NOT EXISTS audit_index (
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
            );
            CREATE INDEX IF NOT EXISTS idx_audit_property_environment_time
                ON audit_index(property_id, environment_id, event_time);
            CREATE TABLE IF NOT EXISTS milestones (
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
            );
            CREATE INDEX IF NOT EXISTS idx_milestone_property_environment_time
                ON milestones(property_id, environment_id, occurred_at);
            CREATE TABLE IF NOT EXISTS golden_baselines (
                property_id TEXT NOT NULL REFERENCES properties(property_id) ON DELETE CASCADE,
                environment_id TEXT NOT NULL REFERENCES environments(environment_id) ON DELETE CASCADE,
                audit_id TEXT NOT NULL REFERENCES audit_index(audit_id) ON DELETE RESTRICT,
                label TEXT,
                set_at TEXT NOT NULL,
                set_by TEXT REFERENCES users(user_id) ON DELETE SET NULL,
                PRIMARY KEY(property_id, environment_id)
            );
            CREATE TABLE IF NOT EXISTS page_identities (
                page_identity_id TEXT PRIMARY KEY,
                property_id TEXT NOT NULL REFERENCES properties(property_id) ON DELETE CASCADE,
                canonical_name TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'ACTIVE',
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                UNIQUE(property_id, canonical_name)
            );
            CREATE TABLE IF NOT EXISTS page_identity_urls (
                page_identity_id TEXT NOT NULL REFERENCES page_identities(page_identity_id) ON DELETE CASCADE,
                environment_id TEXT NOT NULL REFERENCES environments(environment_id) ON DELETE CASCADE,
                normalized_url TEXT NOT NULL,
                valid_from TEXT,
                valid_to TEXT,
                source TEXT NOT NULL DEFAULT 'MANUAL',
                created_at TEXT NOT NULL,
                PRIMARY KEY(page_identity_id, environment_id, normalized_url)
            );
            CREATE INDEX IF NOT EXISTS idx_page_identity_url
                ON page_identity_urls(environment_id, normalized_url);
            CREATE TABLE IF NOT EXISTS comparison_runs (
                comparison_id TEXT PRIMARY KEY,
                milestone_id TEXT REFERENCES milestones(milestone_id) ON DELETE SET NULL,
                baseline_audit_id TEXT NOT NULL REFERENCES audit_index(audit_id) ON DELETE RESTRICT,
                current_audit_id TEXT NOT NULL REFERENCES audit_index(audit_id) ON DELETE RESTRICT,
                comparison_type TEXT NOT NULL,
                comparable INTEGER,
                material_regressions INTEGER NOT NULL DEFAULT 0,
                material_improvements INTEGER NOT NULL DEFAULT 0,
                gate_status TEXT,
                report_path TEXT,
                manifest_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS schedules (
                schedule_id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
                property_id TEXT NOT NULL REFERENCES properties(property_id) ON DELETE CASCADE,
                environment_id TEXT NOT NULL REFERENCES environments(environment_id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                kind TEXT NOT NULL,
                command_argv_json TEXT NOT NULL,
                interval_minutes INTEGER,
                daily_time TEXT,
                enabled INTEGER NOT NULL DEFAULT 1,
                next_run_at TEXT,
                last_run_at TEXT,
                last_status TEXT,
                created_at TEXT NOT NULL,
                UNIQUE(project_id, name)
            );
            CREATE TABLE IF NOT EXISTS alert_rules (
                alert_rule_id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
                property_id TEXT NOT NULL REFERENCES properties(property_id) ON DELETE CASCADE,
                environment_id TEXT NOT NULL REFERENCES environments(environment_id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1,
                event_statuses_json TEXT NOT NULL,
                min_severity TEXT NOT NULL,
                destination TEXT NOT NULL,
                destination_env TEXT,
                created_at TEXT NOT NULL,
                UNIQUE(project_id, name)
            );
            CREATE TABLE IF NOT EXISTS notifications (
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
            );
            CREATE TABLE IF NOT EXISTS integrations (
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
            );
            CREATE TABLE IF NOT EXISTS external_datasets (
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
            );
            CREATE INDEX IF NOT EXISTS idx_external_dataset_scope_time
                ON external_datasets(property_id, environment_id, source_type, captured_at);
            CREATE TABLE IF NOT EXISTS external_records (
                dataset_id TEXT NOT NULL REFERENCES external_datasets(dataset_id) ON DELETE CASCADE,
                record_id TEXT NOT NULL,
                observed_at TEXT,
                normalized_url TEXT,
                dimensions_json TEXT NOT NULL DEFAULT '{}',
                metrics_json TEXT NOT NULL DEFAULT '{}',
                metadata_json TEXT NOT NULL DEFAULT '{}',
                PRIMARY KEY(dataset_id, record_id)
            );
            CREATE INDEX IF NOT EXISTS idx_external_records_url
                ON external_records(normalized_url);
            CREATE TABLE IF NOT EXISTS usage_events (
                usage_event_id TEXT PRIMARY KEY,
                organization_id TEXT NOT NULL REFERENCES organizations(organization_id) ON DELETE CASCADE,
                project_id TEXT REFERENCES projects(project_id) ON DELETE SET NULL,
                property_id TEXT REFERENCES properties(property_id) ON DELETE SET NULL,
                audit_id TEXT,
                occurred_at TEXT NOT NULL,
                category TEXT NOT NULL,
                quantity REAL NOT NULL,
                unit TEXT NOT NULL,
                cost_estimate REAL,
                currency TEXT,
                provider TEXT,
                metadata_json TEXT NOT NULL DEFAULT '{}'
            );
            CREATE INDEX IF NOT EXISTS idx_usage_org_time
                ON usage_events(organization_id, occurred_at);
            """
        )

    # --- identity / hierarchy -------------------------------------------------
    def ensure_local_hierarchy(
        self,
        *,
        project_name: str,
        origin: str,
        environment_name: str = "Production",
        environment_kind: str = "PRODUCTION",
    ) -> tuple[Organization, Workspace, Project, Property, Environment]:
        """Get/create a deterministic local hierarchy for legacy Windows AUDs."""
        organization = self.get_or_create_organization("Local RASAi", slug="local-rasai")
        workspace = self.get_or_create_workspace(organization.organization_id, "Local", slug="local")
        project = self.get_or_create_project(workspace.workspace_id, project_name or "Default Project")
        normalized_origin = normalize_origin(origin)
        hostname = urlsplit(normalized_origin).hostname or normalized_origin
        prop = self.get_or_create_property(
            project.project_id,
            hostname,
            normalized_origin,
        )
        environment = self.get_or_create_environment(
            prop.property_id,
            environment_name,
            environment_kind,
            normalized_origin,
        )
        return organization, workspace, project, prop, environment

    def get_or_create_organization(self, name: str, *, slug: str | None = None) -> Organization:
        key = slugify(slug or name, "organization")
        row = self._connection.execute("SELECT * FROM organizations WHERE slug=?", (key,)).fetchone()
        if row:
            return self._organization(row)
        item = Organization(new_id("ORG"), name.strip() or "Organization", key, utc_now())
        with self._connection:
            self._connection.execute(
                "INSERT INTO organizations(organization_id,name,slug,status,created_at) VALUES(?,?,?,?,?)",
                (item.organization_id, item.name, item.slug, item.status, item.created_at),
            )
        return item

    def list_organizations(self) -> list[Organization]:
        return [self._organization(row) for row in self._connection.execute("SELECT * FROM organizations ORDER BY name")]

    def get_or_create_user(self, display_name: str, *, email: str | None = None) -> User:
        row = None
        if email:
            row = self._connection.execute("SELECT * FROM users WHERE lower(email)=lower(?)", (email,)).fetchone()
        if row:
            return self._user(row)
        item = User(new_id("USR"), display_name.strip() or "User", email, utc_now())
        with self._connection:
            self._connection.execute(
                "INSERT INTO users(user_id,display_name,email,status,created_at) VALUES(?,?,?,?,?)",
                (item.user_id, item.display_name, item.email, item.status, item.created_at),
            )
        return item

    def add_membership(
        self,
        organization_id: str,
        user_id: str,
        role: str,
        *,
        workspace_id: str | None = None,
        project_id: str | None = None,
    ) -> str:
        membership_id = new_id("MBR")
        with self._connection:
            self._connection.execute(
                """INSERT INTO memberships(
                    membership_id,organization_id,user_id,role,workspace_id,project_id,created_at
                ) VALUES(?,?,?,?,?,?,?)""",
                (membership_id, organization_id, user_id, role.upper(), workspace_id, project_id, utc_now()),
            )
        return membership_id

    def get_or_create_workspace(self, organization_id: str, name: str, *, slug: str | None = None) -> Workspace:
        key = slugify(slug or name, "workspace")
        row = self._connection.execute(
            "SELECT * FROM workspaces WHERE organization_id=? AND slug=?",
            (organization_id, key),
        ).fetchone()
        if row:
            return self._workspace(row)
        item = Workspace(new_id("WSP"), organization_id, name.strip() or "Workspace", key, utc_now())
        with self._connection:
            self._connection.execute(
                "INSERT INTO workspaces(workspace_id,organization_id,name,slug,status,created_at) VALUES(?,?,?,?,?,?)",
                (item.workspace_id, item.organization_id, item.name, item.slug, item.status, item.created_at),
            )
        return item

    def list_workspaces(self, organization_id: str | None = None) -> list[Workspace]:
        if organization_id:
            rows = self._connection.execute(
                "SELECT * FROM workspaces WHERE organization_id=? ORDER BY name", (organization_id,)
            )
        else:
            rows = self._connection.execute("SELECT * FROM workspaces ORDER BY name")
        return [self._workspace(row) for row in rows]

    def get_or_create_project(self, workspace_id: str, name: str, *, slug: str | None = None) -> Project:
        key = slugify(slug or name, "project")
        row = self._connection.execute(
            "SELECT * FROM projects WHERE workspace_id=? AND slug=?", (workspace_id, key)
        ).fetchone()
        if row:
            return self._project(row)
        item = Project(new_id("PRJ"), workspace_id, name.strip() or "Project", key, utc_now())
        with self._connection:
            self._connection.execute(
                "INSERT INTO projects(project_id,workspace_id,name,slug,status,created_at) VALUES(?,?,?,?,?,?)",
                (item.project_id, item.workspace_id, item.name, item.slug, item.status, item.created_at),
            )
        return item

    def list_projects(self, workspace_id: str | None = None) -> list[Project]:
        if workspace_id:
            rows = self._connection.execute(
                "SELECT * FROM projects WHERE workspace_id=? ORDER BY name", (workspace_id,)
            )
        else:
            rows = self._connection.execute("SELECT * FROM projects ORDER BY name")
        return [self._project(row) for row in rows]

    def get_or_create_property(
        self,
        project_id: str,
        name: str,
        canonical_origin: str,
        *,
        is_competitor: bool = False,
    ) -> Property:
        origin = normalize_origin(canonical_origin)
        row = self._connection.execute(
            "SELECT * FROM properties WHERE project_id=? AND canonical_origin=?", (project_id, origin)
        ).fetchone()
        if row:
            return self._property(row)
        hostname = urlsplit(origin).hostname or origin
        item = Property(new_id("PTY"), project_id, name.strip() or hostname, origin, hostname, utc_now(), is_competitor=is_competitor)
        with self._connection:
            self._connection.execute(
                """INSERT INTO properties(
                    property_id,project_id,name,canonical_origin,hostname,is_competitor,status,created_at
                ) VALUES(?,?,?,?,?,?,?,?)""",
                (
                    item.property_id,
                    item.project_id,
                    item.name,
                    item.canonical_origin,
                    item.hostname,
                    int(item.is_competitor),
                    item.status,
                    item.created_at,
                ),
            )
        return item

    def list_properties(self, project_id: str | None = None) -> list[Property]:
        if project_id:
            rows = self._connection.execute(
                "SELECT * FROM properties WHERE project_id=? ORDER BY name", (project_id,)
            )
        else:
            rows = self._connection.execute("SELECT * FROM properties ORDER BY name")
        return [self._property(row) for row in rows]

    def get_or_create_environment(
        self,
        property_id: str,
        name: str,
        kind: str,
        base_origin: str,
    ) -> Environment:
        origin = normalize_origin(base_origin)
        row = self._connection.execute(
            "SELECT * FROM environments WHERE property_id=? AND (name=? OR base_origin=?) ORDER BY created_at LIMIT 1",
            (property_id, name, origin),
        ).fetchone()
        if row:
            return self._environment(row)
        item = Environment(new_id("ENV"), property_id, name.strip() or "Environment", kind.upper(), origin, utc_now())  # type: ignore[arg-type]
        with self._connection:
            self._connection.execute(
                "INSERT INTO environments(environment_id,property_id,name,kind,base_origin,status,created_at) VALUES(?,?,?,?,?,?,?)",
                (item.environment_id, item.property_id, item.name, item.kind, item.base_origin, item.status, item.created_at),
            )
        return item

    def list_environments(self, property_id: str | None = None) -> list[Environment]:
        if property_id:
            rows = self._connection.execute(
                "SELECT * FROM environments WHERE property_id=? ORDER BY name", (property_id,)
            )
        else:
            rows = self._connection.execute("SELECT * FROM environments ORDER BY name")
        return [self._environment(row) for row in rows]

    def hierarchy_for_property(self, property_id: str) -> sqlite3.Row:
        row = self._connection.execute(
            """SELECT p.*, pr.name AS project_name, pr.project_id, w.workspace_id, w.name AS workspace_name,
                      o.organization_id, o.name AS organization_name
               FROM properties p
               JOIN projects pr ON pr.project_id=p.project_id
               JOIN workspaces w ON w.workspace_id=pr.workspace_id
               JOIN organizations o ON o.organization_id=w.organization_id
               WHERE p.property_id=?""",
            (property_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"property not found: {property_id}")
        return row

    # --- audit index ----------------------------------------------------------
    def upsert_audit(self, record: AuditIndexRecord) -> None:
        existing = self._connection.execute(
            "SELECT audit_db_sha256,property_id,environment_id FROM audit_index WHERE audit_id=?",
            (record.audit_id,),
        ).fetchone()
        if existing and str(existing["audit_db_sha256"]) != record.audit_db_sha256:
            raise RuntimeError(
                f"immutable audit {record.audit_id} changed on disk: indexed SHA-256 differs from current audit.db"
            )
        with self._connection:
            self._connection.execute(
                """INSERT INTO audit_index(
                    audit_id,property_id,environment_id,workspace_path,audit_db_sha256,event_time,status,
                    completion_status,project_name,auditor_version,ruleset_version,scoring_versions_json,
                    domains_json,devices_json,url_count,indexed_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(audit_id) DO UPDATE SET
                    property_id=excluded.property_id,
                    environment_id=excluded.environment_id,
                    workspace_path=excluded.workspace_path,
                    event_time=excluded.event_time,
                    status=excluded.status,
                    completion_status=excluded.completion_status,
                    project_name=excluded.project_name,
                    auditor_version=excluded.auditor_version,
                    ruleset_version=excluded.ruleset_version,
                    scoring_versions_json=excluded.scoring_versions_json,
                    domains_json=excluded.domains_json,
                    devices_json=excluded.devices_json,
                    url_count=excluded.url_count,
                    indexed_at=excluded.indexed_at""",
                (
                    record.audit_id,
                    record.property_id,
                    record.environment_id,
                    record.workspace_path,
                    record.audit_db_sha256,
                    record.event_time,
                    record.status,
                    record.completion_status,
                    record.project_name,
                    record.auditor_version,
                    record.ruleset_version,
                    _dump(record.scoring_versions),
                    _dump(record.domains),
                    _dump(record.devices),
                    record.url_count,
                    record.indexed_at,
                ),
            )

    def get_audit(self, audit_id: str) -> AuditIndexRecord | None:
        row = self._connection.execute("SELECT * FROM audit_index WHERE audit_id=?", (audit_id,)).fetchone()
        return self._audit(row) if row else None

    def list_audits(
        self,
        *,
        property_id: str | None = None,
        environment_id: str | None = None,
    ) -> list[AuditIndexRecord]:
        clauses: list[str] = []
        values: list[Any] = []
        if property_id:
            clauses.append("property_id=?")
            values.append(property_id)
        if environment_id:
            clauses.append("environment_id=?")
            values.append(environment_id)
        sql = "SELECT * FROM audit_index"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY event_time"
        return [self._audit(row) for row in self._connection.execute(sql, values)]

    def validate_audit_immutability(self, audit_id: str) -> tuple[bool, str, str]:
        record = self.get_audit(audit_id)
        if record is None:
            raise KeyError(f"audit is not indexed: {audit_id}")
        current = file_sha256(Path(record.workspace_path) / "audit.db")
        return current == record.audit_db_sha256, record.audit_db_sha256, current

    # --- milestones / deployment --------------------------------------------
    def add_milestone(
        self,
        *,
        project_id: str,
        property_id: str,
        environment_id: str,
        kind: str,
        occurred_at: str,
        title: str,
        description: str | None = None,
        release: str | None = None,
        commit_sha: str | None = None,
        branch: str | None = None,
        source: str = "MANUAL",
        created_by: str | None = None,
        tags: Sequence[str] = (),
        metadata: dict[str, Any] | None = None,
    ) -> Milestone:
        # ISO parsing is an input-validation boundary; timezone-naive values are
        # accepted for Windows local usage but retained exactly as supplied.
        datetime.fromisoformat(occurred_at.replace("Z", "+00:00"))
        item = Milestone(
            new_id("MLS"),
            project_id,
            property_id,
            environment_id,
            kind.upper(),  # type: ignore[arg-type]
            occurred_at,
            title.strip() or kind.title(),
            description,
            release,
            commit_sha,
            branch,
            source.upper(),
            utc_now(),
            created_by,
            tuple(tags),
            metadata or {},
        )
        with self._connection:
            self._connection.execute(
                """INSERT INTO milestones(
                    milestone_id,project_id,property_id,environment_id,kind,occurred_at,title,description,
                    release,commit_sha,branch,source,created_by,tags_json,metadata_json,created_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    item.milestone_id,
                    item.project_id,
                    item.property_id,
                    item.environment_id,
                    item.kind,
                    item.occurred_at,
                    item.title,
                    item.description,
                    item.release,
                    item.commit_sha,
                    item.branch,
                    item.source,
                    item.created_by,
                    _dump(item.tags),
                    _dump(item.metadata),
                    item.created_at,
                ),
            )
        return item

    def get_milestone(self, milestone_id: str) -> Milestone | None:
        row = self._connection.execute("SELECT * FROM milestones WHERE milestone_id=?", (milestone_id,)).fetchone()
        return self._milestone(row) if row else None

    def list_milestones(
        self,
        *,
        project_id: str | None = None,
        property_id: str | None = None,
        environment_id: str | None = None,
    ) -> list[Milestone]:
        clauses: list[str] = []
        values: list[Any] = []
        for field, value in (("project_id", project_id), ("property_id", property_id), ("environment_id", environment_id)):
            if value:
                clauses.append(f"{field}=?")
                values.append(value)
        sql = "SELECT * FROM milestones"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY occurred_at"
        return [self._milestone(row) for row in self._connection.execute(sql, values)]

    def set_golden_baseline(
        self,
        property_id: str,
        environment_id: str,
        audit_id: str,
        *,
        label: str | None = None,
        set_by: str | None = None,
    ) -> None:
        audit = self.get_audit(audit_id)
        if audit is None:
            raise KeyError(f"audit is not indexed: {audit_id}")
        if audit.property_id != property_id or audit.environment_id != environment_id:
            raise ValueError("golden baseline must belong to the same property/environment")
        with self._connection:
            self._connection.execute(
                """INSERT INTO golden_baselines(property_id,environment_id,audit_id,label,set_at,set_by)
                   VALUES(?,?,?,?,?,?)
                   ON CONFLICT(property_id,environment_id) DO UPDATE SET
                       audit_id=excluded.audit_id,label=excluded.label,set_at=excluded.set_at,set_by=excluded.set_by""",
                (property_id, environment_id, audit_id, label, utc_now(), set_by),
            )

    def get_golden_baseline(self, property_id: str, environment_id: str) -> str | None:
        row = self._connection.execute(
            "SELECT audit_id FROM golden_baselines WHERE property_id=? AND environment_id=?",
            (property_id, environment_id),
        ).fetchone()
        return str(row[0]) if row else None

    def record_comparison(
        self,
        *,
        baseline_audit_id: str,
        current_audit_id: str,
        comparison_type: str,
        comparable: bool | None,
        material_regressions: int,
        material_improvements: int,
        milestone_id: str | None = None,
        gate_status: str | None = None,
        report_path: str | None = None,
        manifest: dict[str, Any] | None = None,
    ) -> str:
        comparison_id = new_id("CMP")
        with self._connection:
            self._connection.execute(
                """INSERT INTO comparison_runs(
                    comparison_id,milestone_id,baseline_audit_id,current_audit_id,comparison_type,comparable,
                    material_regressions,material_improvements,gate_status,report_path,manifest_json,created_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    comparison_id,
                    milestone_id,
                    baseline_audit_id,
                    current_audit_id,
                    comparison_type,
                    None if comparable is None else int(comparable),
                    material_regressions,
                    material_improvements,
                    gate_status,
                    report_path,
                    _dump(manifest or {}),
                    utc_now(),
                ),
            )
        return comparison_id

    # --- page identity --------------------------------------------------------
    def create_page_identity(
        self,
        property_id: str,
        canonical_name: str,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> PageIdentity:
        row = self._connection.execute(
            "SELECT * FROM page_identities WHERE property_id=? AND canonical_name=?",
            (property_id, canonical_name),
        ).fetchone()
        if row:
            return self._page_identity(row)
        item = PageIdentity(new_id("PID"), property_id, canonical_name, utc_now(), metadata=metadata or {})
        with self._connection:
            self._connection.execute(
                "INSERT INTO page_identities(page_identity_id,property_id,canonical_name,status,metadata_json,created_at) VALUES(?,?,?,?,?,?)",
                (item.page_identity_id, item.property_id, item.canonical_name, item.status, _dump(item.metadata), item.created_at),
            )
        return item

    def link_page_url(
        self,
        page_identity_id: str,
        environment_id: str,
        normalized_url: str,
        *,
        valid_from: str | None = None,
        valid_to: str | None = None,
        source: str = "MANUAL",
    ) -> None:
        parts = urlsplit(normalized_url)
        if parts.scheme not in {"http", "https"} or not parts.hostname:
            raise ValueError("page identity URL must be an absolute HTTP(S) URL")
        with self._connection:
            self._connection.execute(
                """INSERT INTO page_identity_urls(
                    page_identity_id,environment_id,normalized_url,valid_from,valid_to,source,created_at
                ) VALUES(?,?,?,?,?,?,?)
                ON CONFLICT(page_identity_id,environment_id,normalized_url) DO UPDATE SET
                    valid_from=excluded.valid_from,valid_to=excluded.valid_to,source=excluded.source""",
                (page_identity_id, environment_id, normalized_url, valid_from, valid_to, source, utc_now()),
            )

    def page_identity_urls(self, page_identity_id: str) -> list[dict[str, Any]]:
        rows = self._connection.execute(
            "SELECT * FROM page_identity_urls WHERE page_identity_id=? ORDER BY valid_from,created_at",
            (page_identity_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def list_page_identities(self, property_id: str | None = None) -> list[PageIdentity]:
        if property_id:
            rows = self._connection.execute(
                "SELECT * FROM page_identities WHERE property_id=? ORDER BY canonical_name", (property_id,)
            )
        else:
            rows = self._connection.execute("SELECT * FROM page_identities ORDER BY canonical_name")
        return [self._page_identity(row) for row in rows]

    # --- schedules ------------------------------------------------------------
    def add_schedule(
        self,
        *,
        project_id: str,
        property_id: str,
        environment_id: str,
        name: str,
        kind: str,
        command_argv: Sequence[str],
        interval_minutes: int | None = None,
        daily_time: str | None = None,
        next_run_at: str | None = None,
        enabled: bool = True,
    ) -> Schedule:
        if not command_argv:
            raise ValueError("schedule command argv cannot be empty")
        if kind.upper() == "INTERVAL" and (interval_minutes is None or interval_minutes < 1):
            raise ValueError("INTERVAL schedule requires interval_minutes >= 1")
        if kind.upper() == "DAILY" and not daily_time:
            raise ValueError("DAILY schedule requires daily_time HH:MM")
        item = Schedule(
            new_id("SCH"),
            project_id,
            property_id,
            environment_id,
            name,
            kind.upper(),  # type: ignore[arg-type]
            tuple(command_argv),
            enabled,
            utc_now(),
            interval_minutes,
            daily_time,
            next_run_at,
        )
        with self._connection:
            self._connection.execute(
                """INSERT INTO schedules(
                    schedule_id,project_id,property_id,environment_id,name,kind,command_argv_json,
                    interval_minutes,daily_time,enabled,next_run_at,last_run_at,last_status,created_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    item.schedule_id,
                    item.project_id,
                    item.property_id,
                    item.environment_id,
                    item.name,
                    item.kind,
                    _dump(item.command_argv),
                    item.interval_minutes,
                    item.daily_time,
                    int(item.enabled),
                    item.next_run_at,
                    item.last_run_at,
                    item.last_status,
                    item.created_at,
                ),
            )
        return item

    def list_schedules(self, *, due_before: str | None = None, enabled_only: bool = False) -> list[Schedule]:
        clauses: list[str] = []
        values: list[Any] = []
        if enabled_only:
            clauses.append("enabled=1")
        if due_before:
            clauses.append("next_run_at IS NOT NULL AND next_run_at<=?")
            values.append(due_before)
        sql = "SELECT * FROM schedules"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY COALESCE(next_run_at,'9999')"
        return [self._schedule(row) for row in self._connection.execute(sql, values)]

    def update_schedule_run(self, schedule_id: str, *, last_run_at: str, last_status: str, next_run_at: str | None) -> None:
        with self._connection:
            self._connection.execute(
                "UPDATE schedules SET last_run_at=?,last_status=?,next_run_at=? WHERE schedule_id=?",
                (last_run_at, last_status, next_run_at, schedule_id),
            )

    # --- alerts ---------------------------------------------------------------
    def add_alert_rule(
        self,
        *,
        project_id: str,
        property_id: str,
        environment_id: str,
        name: str,
        event_statuses: Sequence[str],
        min_severity: str = "HIGH",
        destination: str = "NONE",
        destination_env: str | None = None,
        enabled: bool = True,
    ) -> AlertRule:
        item = AlertRule(
            new_id("ALT"),
            project_id,
            property_id,
            environment_id,
            name,
            enabled,
            tuple(status.upper() for status in event_statuses),
            min_severity.upper(),
            destination.upper(),  # type: ignore[arg-type]
            destination_env,
            utc_now(),
        )
        with self._connection:
            self._connection.execute(
                """INSERT INTO alert_rules(
                    alert_rule_id,project_id,property_id,environment_id,name,enabled,event_statuses_json,
                    min_severity,destination,destination_env,created_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    item.alert_rule_id,
                    item.project_id,
                    item.property_id,
                    item.environment_id,
                    item.name,
                    int(item.enabled),
                    _dump(item.event_statuses),
                    item.min_severity,
                    item.destination,
                    item.destination_env,
                    item.created_at,
                ),
            )
        return item

    def list_alert_rules(self, *, property_id: str | None = None, enabled_only: bool = False) -> list[AlertRule]:
        clauses: list[str] = []
        values: list[Any] = []
        if property_id:
            clauses.append("property_id=?")
            values.append(property_id)
        if enabled_only:
            clauses.append("enabled=1")
        sql = "SELECT * FROM alert_rules"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY name"
        return [self._alert_rule(row) for row in self._connection.execute(sql, values)]

    def add_notification(
        self,
        *,
        alert_rule_id: str | None,
        comparison_id: str | None,
        milestone_id: str | None,
        status: str,
        payload: dict[str, Any],
        destination: str,
        delivery_error: str | None = None,
        delivered_at: str | None = None,
    ) -> str:
        notification_id = new_id("NTF")
        with self._connection:
            self._connection.execute(
                """INSERT INTO notifications(
                    notification_id,alert_rule_id,comparison_id,milestone_id,status,payload_json,destination,
                    delivery_error,created_at,delivered_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (
                    notification_id,
                    alert_rule_id,
                    comparison_id,
                    milestone_id,
                    status,
                    _dump(payload),
                    destination,
                    delivery_error,
                    utc_now(),
                    delivered_at,
                ),
            )
        return notification_id

    # --- integrations / external datasets -----------------------------------
    def add_integration(
        self,
        *,
        organization_id: str,
        provider: str,
        name: str,
        secret_env: str | None = None,
        workspace_id: str | None = None,
        project_id: str | None = None,
        property_id: str | None = None,
        configuration: dict[str, Any] | None = None,
    ) -> Integration:
        item = Integration(
            new_id("INT"),
            organization_id,
            workspace_id,
            project_id,
            property_id,
            provider.upper(),
            name,
            secret_env,
            configuration or {},
            utc_now(),
        )
        with self._connection:
            self._connection.execute(
                """INSERT INTO integrations(
                    integration_id,organization_id,workspace_id,project_id,property_id,provider,name,
                    secret_env,configuration_json,status,created_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    item.integration_id,
                    item.organization_id,
                    item.workspace_id,
                    item.project_id,
                    item.property_id,
                    item.provider,
                    item.name,
                    item.secret_env,
                    _dump(item.configuration),
                    item.status,
                    item.created_at,
                ),
            )
        return item

    def list_integrations(self, *, organization_id: str | None = None, property_id: str | None = None) -> list[Integration]:
        clauses: list[str] = []
        values: list[Any] = []
        if organization_id:
            clauses.append("organization_id=?")
            values.append(organization_id)
        if property_id:
            clauses.append("property_id=?")
            values.append(property_id)
        sql = "SELECT * FROM integrations"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY provider,name"
        return [self._integration(row) for row in self._connection.execute(sql, values)]

    def add_external_dataset(
        self,
        dataset: ExternalDataset,
        records: Iterable[dict[str, Any]],
    ) -> None:
        with self.transaction() as connection:
            connection.execute(
                """INSERT INTO external_datasets(
                    dataset_id,organization_id,project_id,property_id,environment_id,source_type,period_start,
                    period_end,captured_at,artifact_path,artifact_sha256,row_count,metadata_json
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    dataset.dataset_id,
                    dataset.organization_id,
                    dataset.project_id,
                    dataset.property_id,
                    dataset.environment_id,
                    dataset.source_type,
                    dataset.period_start,
                    dataset.period_end,
                    dataset.captured_at,
                    dataset.artifact_path,
                    dataset.artifact_sha256,
                    dataset.row_count,
                    _dump(dataset.metadata),
                ),
            )
            for index, record in enumerate(records, start=1):
                connection.execute(
                    """INSERT INTO external_records(
                        dataset_id,record_id,observed_at,normalized_url,dimensions_json,metrics_json,metadata_json
                    ) VALUES(?,?,?,?,?,?,?)""",
                    (
                        dataset.dataset_id,
                        str(record.get("record_id") or index),
                        record.get("observed_at"),
                        record.get("normalized_url"),
                        _dump(record.get("dimensions") or {}),
                        _dump(record.get("metrics") or {}),
                        _dump(record.get("metadata") or {}),
                    ),
                )

    def list_external_datasets(
        self,
        *,
        property_id: str | None = None,
        source_type: str | None = None,
    ) -> list[ExternalDataset]:
        clauses: list[str] = []
        values: list[Any] = []
        if property_id:
            clauses.append("property_id=?")
            values.append(property_id)
        if source_type:
            clauses.append("source_type=?")
            values.append(source_type)
        sql = "SELECT * FROM external_datasets"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY captured_at"
        return [self._external_dataset(row) for row in self._connection.execute(sql, values)]

    def external_records(self, dataset_id: str) -> list[dict[str, Any]]:
        rows = self._connection.execute(
            "SELECT * FROM external_records WHERE dataset_id=? ORDER BY record_id", (dataset_id,)
        ).fetchall()
        return [
            {
                "dataset_id": row["dataset_id"],
                "record_id": row["record_id"],
                "observed_at": row["observed_at"],
                "normalized_url": row["normalized_url"],
                "dimensions": _load(row["dimensions_json"], {}),
                "metrics": _load(row["metrics_json"], {}),
                "metadata": _load(row["metadata_json"], {}),
            }
            for row in rows
        ]

    # --- usage ---------------------------------------------------------------
    def add_usage_event(
        self,
        *,
        organization_id: str,
        category: str,
        quantity: float,
        unit: str,
        project_id: str | None = None,
        property_id: str | None = None,
        audit_id: str | None = None,
        cost_estimate: float | None = None,
        currency: str | None = None,
        provider: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> UsageEvent:
        item = UsageEvent(
            new_id("USE"),
            organization_id,
            project_id,
            property_id,
            audit_id,
            utc_now(),
            category,
            float(quantity),
            unit,
            cost_estimate,
            currency,
            provider,
            metadata or {},
        )
        with self._connection:
            self._connection.execute(
                """INSERT INTO usage_events(
                    usage_event_id,organization_id,project_id,property_id,audit_id,occurred_at,category,
                    quantity,unit,cost_estimate,currency,provider,metadata_json
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    item.usage_event_id,
                    item.organization_id,
                    item.project_id,
                    item.property_id,
                    item.audit_id,
                    item.occurred_at,
                    item.category,
                    item.quantity,
                    item.unit,
                    item.cost_estimate,
                    item.currency,
                    item.provider,
                    _dump(item.metadata),
                ),
            )
        return item

    def usage_summary(self, organization_id: str | None = None) -> list[dict[str, Any]]:
        if organization_id:
            rows = self._connection.execute(
                """SELECT category,unit,provider,currency,SUM(quantity) AS quantity,SUM(cost_estimate) AS cost
                   FROM usage_events WHERE organization_id=? GROUP BY category,unit,provider,currency
                   ORDER BY category,provider""",
                (organization_id,),
            )
        else:
            rows = self._connection.execute(
                """SELECT category,unit,provider,currency,SUM(quantity) AS quantity,SUM(cost_estimate) AS cost
                   FROM usage_events GROUP BY category,unit,provider,currency ORDER BY category,provider"""
            )
        return [dict(row) for row in rows]

    # --- status --------------------------------------------------------------
    def counts(self) -> dict[str, int]:
        tables = (
            "organizations",
            "users",
            "workspaces",
            "projects",
            "properties",
            "environments",
            "audit_index",
            "milestones",
            "page_identities",
            "schedules",
            "alert_rules",
            "integrations",
            "external_datasets",
            "usage_events",
        )
        return {
            table: int(self._connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            for table in tables
        }

    # --- row mapping ---------------------------------------------------------
    @staticmethod
    def _organization(row: sqlite3.Row) -> Organization:
        return Organization(row["organization_id"], row["name"], row["slug"], row["created_at"], row["status"])

    @staticmethod
    def _user(row: sqlite3.Row) -> User:
        return User(row["user_id"], row["display_name"], row["email"], row["created_at"], row["status"])

    @staticmethod
    def _workspace(row: sqlite3.Row) -> Workspace:
        return Workspace(row["workspace_id"], row["organization_id"], row["name"], row["slug"], row["created_at"], row["status"])

    @staticmethod
    def _project(row: sqlite3.Row) -> Project:
        return Project(row["project_id"], row["workspace_id"], row["name"], row["slug"], row["created_at"], row["status"])

    @staticmethod
    def _property(row: sqlite3.Row) -> Property:
        return Property(
            row["property_id"],
            row["project_id"],
            row["name"],
            row["canonical_origin"],
            row["hostname"],
            row["created_at"],
            row["status"],
            bool(row["is_competitor"]),
        )

    @staticmethod
    def _environment(row: sqlite3.Row) -> Environment:
        return Environment(
            row["environment_id"], row["property_id"], row["name"], row["kind"], row["base_origin"], row["created_at"], row["status"]
        )

    @staticmethod
    def _audit(row: sqlite3.Row) -> AuditIndexRecord:
        return AuditIndexRecord(
            row["audit_id"],
            row["property_id"],
            row["environment_id"],
            row["workspace_path"],
            row["audit_db_sha256"],
            row["event_time"],
            row["status"],
            row["completion_status"],
            row["project_name"],
            row["auditor_version"],
            row["ruleset_version"],
            tuple(_load(row["scoring_versions_json"], [])),
            tuple(_load(row["domains_json"], [])),
            tuple(_load(row["devices_json"], [])),
            int(row["url_count"]),
            row["indexed_at"],
        )

    @staticmethod
    def _milestone(row: sqlite3.Row) -> Milestone:
        return Milestone(
            row["milestone_id"],
            row["project_id"],
            row["property_id"],
            row["environment_id"],
            row["kind"],
            row["occurred_at"],
            row["title"],
            row["description"],
            row["release"],
            row["commit_sha"],
            row["branch"],
            row["source"],
            row["created_at"],
            row["created_by"],
            tuple(_load(row["tags_json"], [])),
            _load(row["metadata_json"], {}),
        )

    @staticmethod
    def _page_identity(row: sqlite3.Row) -> PageIdentity:
        return PageIdentity(
            row["page_identity_id"],
            row["property_id"],
            row["canonical_name"],
            row["created_at"],
            row["status"],
            _load(row["metadata_json"], {}),
        )

    @staticmethod
    def _schedule(row: sqlite3.Row) -> Schedule:
        return Schedule(
            row["schedule_id"],
            row["project_id"],
            row["property_id"],
            row["environment_id"],
            row["name"],
            row["kind"],
            tuple(_load(row["command_argv_json"], [])),
            bool(row["enabled"]),
            row["created_at"],
            row["interval_minutes"],
            row["daily_time"],
            row["next_run_at"],
            row["last_run_at"],
            row["last_status"],
        )

    @staticmethod
    def _alert_rule(row: sqlite3.Row) -> AlertRule:
        return AlertRule(
            row["alert_rule_id"],
            row["project_id"],
            row["property_id"],
            row["environment_id"],
            row["name"],
            bool(row["enabled"]),
            tuple(_load(row["event_statuses_json"], [])),
            row["min_severity"],
            row["destination"],
            row["destination_env"],
            row["created_at"],
        )

    @staticmethod
    def _integration(row: sqlite3.Row) -> Integration:
        return Integration(
            row["integration_id"],
            row["organization_id"],
            row["workspace_id"],
            row["project_id"],
            row["property_id"],
            row["provider"],
            row["name"],
            row["secret_env"],
            _load(row["configuration_json"], {}),
            row["created_at"],
            row["status"],
        )

    @staticmethod
    def _external_dataset(row: sqlite3.Row) -> ExternalDataset:
        return ExternalDataset(
            row["dataset_id"],
            row["organization_id"],
            row["project_id"],
            row["property_id"],
            row["environment_id"],
            row["source_type"],
            row["period_start"],
            row["period_end"],
            row["captured_at"],
            row["artifact_path"],
            row["artifact_sha256"],
            int(row["row_count"]),
            _load(row["metadata_json"], {}),
        )
