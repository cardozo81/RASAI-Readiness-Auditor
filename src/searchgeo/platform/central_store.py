"""Canonical RASAI product control-plane store.

This extends the local SQLite implementation with cross-entity integrity and
true multi-property audit scopes. ``audit_index.property_id`` remains the
primary/legacy scope for backwards compatibility; ``audit_scope_links`` is the
canonical many-to-many relationship used by product-platform features.
"""
from __future__ import annotations

from pathlib import Path
import re
import sqlite3
from typing import Any, Iterable, Sequence

from .models import AlertRule, AuditIndexRecord, Environment, ExternalDataset, Integration, Milestone, Schedule, UsageEvent
from .store import PlatformStore as _BasePlatformStore, utc_now

_ALLOWED_ROLES = {
    "OWNER", "ADMIN", "ANALYST", "OPERATOR", "VIEWER", "INTEGRATION_MANAGER", "BILLING"
}
_ALLOWED_ENVIRONMENT_KINDS = {"PRODUCTION", "STAGING", "QA", "PREVIEW", "DEVELOPMENT", "OTHER"}
_ALLOWED_MILESTONE_KINDS = {
    "DEPLOYMENT", "RELEASE", "CMS_MIGRATION", "REDESIGN", "CONTENT_RELEASE", "SEO_CHANGE",
    "INFRASTRUCTURE", "INCIDENT", "CAMPAIGN", "MANUAL", "OTHER",
}
_ALLOWED_SCHEDULE_KINDS = {"INTERVAL", "DAILY", "MANUAL", "DEPLOYMENT_TRIGGERED", "API_TRIGGERED"}
_ALLOWED_ALERT_DESTINATIONS = {"NONE", "JSON", "WEBHOOK"}
_ALLOWED_ALERT_STATUSES = {"NEW", "RESOLVED", "REGRESSED", "IMPROVED", "CHANGED", "DATA_UNAVAILABLE", "NOT_COMPARABLE"}
_ALLOWED_SEVERITIES = {"INFO", "LOW", "MEDIUM", "HIGH", "CRITICAL"}
_DAILY_TIME_RE = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")


class CentralPlatformStore(_BasePlatformStore):
    """Canonical Windows-local control plane, ready for a PostgreSQL adapter.

    The base store owns stable v1 tables. This class owns additive product
    integrity extensions so existing local ``platform.db`` files are migrated
    without destructive rewrites.
    """

    def __init__(self, database: str | Path) -> None:
        super().__init__(database)
        self._initialize_canonical_extensions()

    @classmethod
    def open(
        cls,
        audits_root: str | Path = "audits",
        *,
        database: str | Path | None = None,
    ) -> "CentralPlatformStore":
        from .store import default_platform_database
        return cls(database or default_platform_database(audits_root))

    def _initialize_canonical_extensions(self) -> None:
        with self._connection:
            self._connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS platform_extension_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS audit_scope_links (
                    audit_id TEXT NOT NULL REFERENCES audit_index(audit_id) ON DELETE CASCADE,
                    property_id TEXT NOT NULL REFERENCES properties(property_id) ON DELETE RESTRICT,
                    environment_id TEXT NOT NULL REFERENCES environments(environment_id) ON DELETE RESTRICT,
                    origin TEXT NOT NULL,
                    is_primary INTEGER NOT NULL DEFAULT 0,
                    linked_at TEXT NOT NULL,
                    PRIMARY KEY(audit_id, property_id, environment_id)
                );
                CREATE INDEX IF NOT EXISTS idx_audit_scope_property_environment
                    ON audit_scope_links(property_id, environment_id, audit_id);
                CREATE UNIQUE INDEX IF NOT EXISTS idx_audit_scope_single_primary
                    ON audit_scope_links(audit_id) WHERE is_primary=1;
                """
            )
            self._connection.execute(
                """INSERT INTO platform_extension_meta(key,value) VALUES('canonical_schema','2')
                   ON CONFLICT(key) DO UPDATE SET value=excluded.value"""
            )
            # Backfill legacy single-scope records. New indexing replaces these
            # links with the complete multi-property scope set.
            self._connection.execute(
                """INSERT OR IGNORE INTO audit_scope_links(
                    audit_id,property_id,environment_id,origin,is_primary,linked_at
                )
                SELECT a.audit_id,a.property_id,a.environment_id,e.base_origin,1,a.indexed_at
                FROM audit_index a
                JOIN environments e ON e.environment_id=a.environment_id"""
            )

    # --- hierarchy integrity -------------------------------------------------
    def _scope_row(self, project_id: str, property_id: str, environment_id: str) -> sqlite3.Row:
        row = self._connection.execute(
            """SELECT p.project_id,e.property_id
               FROM properties p JOIN environments e ON e.property_id=p.property_id
               WHERE p.property_id=? AND e.environment_id=?""",
            (property_id, environment_id),
        ).fetchone()
        if row is None:
            raise ValueError("property/environment scope does not exist")
        if str(row["project_id"]) != project_id:
            raise ValueError("property does not belong to the supplied project")
        if str(row["property_id"]) != property_id:
            raise ValueError("environment does not belong to the supplied property")
        return row

    def _project_organization(self, project_id: str) -> str:
        row = self._connection.execute(
            """SELECT w.organization_id
               FROM projects p JOIN workspaces w ON w.workspace_id=p.workspace_id
               WHERE p.project_id=?""",
            (project_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"project not found: {project_id}")
        return str(row[0])

    def _workspace_organization(self, workspace_id: str) -> str:
        row = self._connection.execute(
            "SELECT organization_id FROM workspaces WHERE workspace_id=?", (workspace_id,)
        ).fetchone()
        if row is None:
            raise KeyError(f"workspace not found: {workspace_id}")
        return str(row[0])

    def _property_project(self, property_id: str) -> str:
        row = self._connection.execute(
            "SELECT project_id FROM properties WHERE property_id=?", (property_id,)
        ).fetchone()
        if row is None:
            raise KeyError(f"property not found: {property_id}")
        return str(row[0])

    def get_or_create_environment(self, property_id: str, name: str, kind: str, base_origin: str) -> Environment:
        normalized = kind.strip().upper()
        if normalized not in _ALLOWED_ENVIRONMENT_KINDS:
            raise ValueError(f"unsupported environment kind: {kind}")
        return super().get_or_create_environment(property_id, name, normalized, base_origin)

    # --- users / memberships -------------------------------------------------
    def list_users(self) -> list[dict[str, Any]]:
        return [dict(row) for row in self._connection.execute("SELECT * FROM users ORDER BY display_name,user_id")]

    def add_membership(
        self,
        organization_id: str,
        user_id: str,
        role: str,
        *,
        workspace_id: str | None = None,
        project_id: str | None = None,
    ) -> str:
        normalized_role = role.strip().upper()
        if normalized_role not in _ALLOWED_ROLES:
            raise ValueError(f"unsupported membership role: {role}")
        organization = self._connection.execute(
            "SELECT 1 FROM organizations WHERE organization_id=?", (organization_id,)
        ).fetchone()
        user = self._connection.execute("SELECT 1 FROM users WHERE user_id=?", (user_id,)).fetchone()
        if organization is None:
            raise KeyError(f"organization not found: {organization_id}")
        if user is None:
            raise KeyError(f"user not found: {user_id}")
        if workspace_id and self._workspace_organization(workspace_id) != organization_id:
            raise ValueError("workspace does not belong to membership organization")
        if project_id:
            if self._project_organization(project_id) != organization_id:
                raise ValueError("project does not belong to membership organization")
            if workspace_id:
                row = self._connection.execute(
                    "SELECT workspace_id FROM projects WHERE project_id=?", (project_id,)
                ).fetchone()
                if row is None or str(row[0]) != workspace_id:
                    raise ValueError("project does not belong to membership workspace")
        return super().add_membership(
            organization_id,
            user_id,
            normalized_role,
            workspace_id=workspace_id,
            project_id=project_id,
        )

    def list_memberships(
        self,
        *,
        organization_id: str | None = None,
        user_id: str | None = None,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        values: list[Any] = []
        if organization_id:
            clauses.append("m.organization_id=?")
            values.append(organization_id)
        if user_id:
            clauses.append("m.user_id=?")
            values.append(user_id)
        sql = """SELECT m.*,u.display_name,u.email,o.name AS organization_name,
                        w.name AS workspace_name,p.name AS project_name
                 FROM memberships m
                 JOIN users u ON u.user_id=m.user_id
                 JOIN organizations o ON o.organization_id=m.organization_id
                 LEFT JOIN workspaces w ON w.workspace_id=m.workspace_id
                 LEFT JOIN projects p ON p.project_id=m.project_id"""
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY o.name,u.display_name,m.role"
        return [dict(row) for row in self._connection.execute(sql, values)]

    # --- true multi-property AUD scope ---------------------------------------
    def replace_audit_scopes(
        self,
        audit_id: str,
        scopes: Sequence[tuple[str, str, str]],
        *,
        primary_property_id: str,
        primary_environment_id: str,
    ) -> None:
        if self.get_audit(audit_id) is None:
            raise KeyError(f"audit must be indexed before linking scopes: {audit_id}")
        normalized = list(dict.fromkeys(scopes))
        if not normalized:
            raise ValueError("an indexed audit must have at least one property/environment scope")
        if not any(p == primary_property_id and e == primary_environment_id for p, e, _ in normalized):
            raise ValueError("primary audit scope must be present in the scope set")
        for property_id, environment_id, _origin in normalized:
            project_id = self._property_project(property_id)
            self._scope_row(project_id, property_id, environment_id)
        with self.transaction() as connection:
            connection.execute("DELETE FROM audit_scope_links WHERE audit_id=?", (audit_id,))
            for property_id, environment_id, origin in normalized:
                connection.execute(
                    """INSERT INTO audit_scope_links(
                        audit_id,property_id,environment_id,origin,is_primary,linked_at
                    ) VALUES(?,?,?,?,?,?)""",
                    (
                        audit_id,
                        property_id,
                        environment_id,
                        origin,
                        int(property_id == primary_property_id and environment_id == primary_environment_id),
                        utc_now(),
                    ),
                )

    def audit_scopes(self, audit_id: str) -> list[dict[str, Any]]:
        return [
            dict(row)
            for row in self._connection.execute(
                """SELECT l.*,p.name AS property_name,p.hostname,e.name AS environment_name,e.kind
                   FROM audit_scope_links l
                   JOIN properties p ON p.property_id=l.property_id
                   JOIN environments e ON e.environment_id=l.environment_id
                   WHERE l.audit_id=? ORDER BY l.is_primary DESC,p.hostname,e.name""",
                (audit_id,),
            )
        ]

    def audit_belongs_to_scope(self, audit_id: str, property_id: str, environment_id: str) -> bool:
        row = self._connection.execute(
            """SELECT 1 FROM audit_scope_links
               WHERE audit_id=? AND property_id=? AND environment_id=?""",
            (audit_id, property_id, environment_id),
        ).fetchone()
        return row is not None

    def list_audits(
        self,
        *,
        property_id: str | None = None,
        environment_id: str | None = None,
    ) -> list[AuditIndexRecord]:
        if not property_id and not environment_id:
            return super().list_audits()
        clauses: list[str] = []
        values: list[Any] = []
        if property_id:
            clauses.append("l.property_id=?")
            values.append(property_id)
        if environment_id:
            clauses.append("l.environment_id=?")
            values.append(environment_id)
        sql = """SELECT DISTINCT a.* FROM audit_index a
                 JOIN audit_scope_links l ON l.audit_id=a.audit_id
                 WHERE """ + " AND ".join(clauses) + " ORDER BY a.event_time"
        return [self._audit(row) for row in self._connection.execute(sql, values)]

    def set_golden_baseline(
        self,
        property_id: str,
        environment_id: str,
        audit_id: str,
        *,
        label: str | None = None,
        set_by: str | None = None,
    ) -> None:
        if not self.audit_belongs_to_scope(audit_id, property_id, environment_id):
            raise ValueError("golden baseline must belong to the same property/environment scope")
        with self._connection:
            self._connection.execute(
                """INSERT INTO golden_baselines(property_id,environment_id,audit_id,label,set_at,set_by)
                   VALUES(?,?,?,?,?,?)
                   ON CONFLICT(property_id,environment_id) DO UPDATE SET
                     audit_id=excluded.audit_id,label=excluded.label,set_at=excluded.set_at,set_by=excluded.set_by""",
                (property_id, environment_id, audit_id, label, utc_now(), set_by),
            )

    # --- scoped writes --------------------------------------------------------
    def add_milestone(self, **kwargs: Any) -> Milestone:
        project_id = str(kwargs["project_id"])
        property_id = str(kwargs["property_id"])
        environment_id = str(kwargs["environment_id"])
        self._scope_row(project_id, property_id, environment_id)
        kind = str(kwargs.get("kind") or "").upper()
        if kind not in _ALLOWED_MILESTONE_KINDS:
            raise ValueError(f"unsupported milestone kind: {kind}")
        kwargs["kind"] = kind
        return super().add_milestone(**kwargs)

    def add_schedule(self, **kwargs: Any) -> Schedule:
        project_id = str(kwargs["project_id"])
        property_id = str(kwargs["property_id"])
        environment_id = str(kwargs["environment_id"])
        self._scope_row(project_id, property_id, environment_id)
        kind = str(kwargs.get("kind") or "").upper()
        if kind not in _ALLOWED_SCHEDULE_KINDS:
            raise ValueError(f"unsupported schedule kind: {kind}")
        daily_time = kwargs.get("daily_time")
        if kind == "DAILY" and (not isinstance(daily_time, str) or not _DAILY_TIME_RE.fullmatch(daily_time)):
            raise ValueError("DAILY schedule requires valid HH:MM (00:00-23:59)")
        kwargs["kind"] = kind
        return super().add_schedule(**kwargs)

    def add_alert_rule(self, **kwargs: Any) -> AlertRule:
        project_id = str(kwargs["project_id"])
        property_id = str(kwargs["property_id"])
        environment_id = str(kwargs["environment_id"])
        self._scope_row(project_id, property_id, environment_id)
        destination = str(kwargs.get("destination") or "NONE").upper()
        if destination not in _ALLOWED_ALERT_DESTINATIONS:
            raise ValueError(f"unsupported alert destination: {destination}")
        severity = str(kwargs.get("min_severity") or "HIGH").upper()
        if severity not in _ALLOWED_SEVERITIES:
            raise ValueError(f"unsupported alert severity: {severity}")
        statuses = tuple(str(item).upper() for item in kwargs.get("event_statuses") or ())
        invalid = sorted(set(statuses) - _ALLOWED_ALERT_STATUSES)
        if invalid:
            raise ValueError(f"unsupported alert event status(es): {', '.join(invalid)}")
        kwargs["destination"] = destination
        kwargs["min_severity"] = severity
        kwargs["event_statuses"] = statuses
        return super().add_alert_rule(**kwargs)

    def link_page_url(self, page_identity_id: str, environment_id: str, normalized_url: str, **kwargs: Any) -> None:
        row = self._connection.execute(
            """SELECT pi.property_id AS identity_property,e.property_id AS environment_property
               FROM page_identities pi JOIN environments e ON e.environment_id=?
               WHERE pi.page_identity_id=?""",
            (environment_id, page_identity_id),
        ).fetchone()
        if row is None:
            raise KeyError("page identity or environment not found")
        if str(row["identity_property"]) != str(row["environment_property"]):
            raise ValueError("PageIdentity environment must belong to the same Property")
        super().link_page_url(page_identity_id, environment_id, normalized_url, **kwargs)

    def add_external_dataset(self, dataset: ExternalDataset, records: Iterable[dict[str, Any]]) -> None:
        self._scope_row(dataset.project_id, dataset.property_id, dataset.environment_id)
        if self._project_organization(dataset.project_id) != dataset.organization_id:
            raise ValueError("external dataset organization/project scope mismatch")
        super().add_external_dataset(dataset, records)

    def add_integration(self, **kwargs: Any) -> Integration:
        organization_id = str(kwargs["organization_id"])
        workspace_id = kwargs.get("workspace_id")
        project_id = kwargs.get("project_id")
        property_id = kwargs.get("property_id")
        if workspace_id and self._workspace_organization(str(workspace_id)) != organization_id:
            raise ValueError("integration workspace is outside organization")
        if project_id and self._project_organization(str(project_id)) != organization_id:
            raise ValueError("integration project is outside organization")
        if property_id:
            property_project = self._property_project(str(property_id))
            if self._project_organization(property_project) != organization_id:
                raise ValueError("integration property is outside organization")
            if project_id and property_project != str(project_id):
                raise ValueError("integration property does not belong to supplied project")
        return super().add_integration(**kwargs)

    def add_usage_event(self, **kwargs: Any) -> UsageEvent:
        organization_id = str(kwargs["organization_id"])
        project_id = kwargs.get("project_id")
        property_id = kwargs.get("property_id")
        audit_id = kwargs.get("audit_id")
        if project_id and self._project_organization(str(project_id)) != organization_id:
            raise ValueError("usage project is outside organization")
        if property_id:
            property_project = self._property_project(str(property_id))
            if self._project_organization(property_project) != organization_id:
                raise ValueError("usage property is outside organization")
            if project_id and property_project != str(project_id):
                raise ValueError("usage property does not belong to supplied project")
        if audit_id:
            audit = self.get_audit(str(audit_id))
            if audit is None:
                raise KeyError(f"audit not indexed: {audit_id}")
            scopes = self.audit_scopes(str(audit_id))
            organizations = {
                self._project_organization(self._property_project(str(scope["property_id"])))
                for scope in scopes
            }
            if organization_id not in organizations:
                raise ValueError("usage audit is outside organization")
        return super().add_usage_event(**kwargs)

    # --- data governance ------------------------------------------------------
    def data_governance_status(self) -> dict[str, Any]:
        searchgeo_dir = self.database.parent
        legacy = searchgeo_dir / "consolidated-index.db"
        return {
            "canonical_control_plane": str(self.database),
            "canonical_schema": 2,
            "legacy_analytical_cache": str(legacy),
            "legacy_analytical_cache_exists": legacy.is_file(),
            "legacy_cache_role": "DERIVED_REBUILDABLE_COMPATIBILITY_CACHE",
            "audit_evidence_role": "IMMUTABLE_AUD_WORKSPACES",
        }
