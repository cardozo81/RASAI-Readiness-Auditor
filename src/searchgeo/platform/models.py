"""Stable data contracts for the RASAi product control plane.

The control plane is deliberately separate from ``audit.db``. These records
represent ownership, product organization, milestones, schedules and external
operational metadata. They never redefine persisted audit evidence or scoring.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

Role = Literal["OWNER", "ADMIN", "ANALYST", "OPERATOR", "VIEWER", "INTEGRATION_MANAGER", "BILLING"]
EnvironmentKind = Literal["PRODUCTION", "STAGING", "QA", "PREVIEW", "DEVELOPMENT", "OTHER"]
MilestoneKind = Literal[
    "DEPLOYMENT",
    "RELEASE",
    "CMS_MIGRATION",
    "REDESIGN",
    "CONTENT_RELEASE",
    "SEO_CHANGE",
    "INFRASTRUCTURE",
    "INCIDENT",
    "CAMPAIGN",
    "MANUAL",
    "OTHER",
]
ScheduleKind = Literal["INTERVAL", "DAILY", "MANUAL", "DEPLOYMENT_TRIGGERED", "API_TRIGGERED"]
AlertDestination = Literal["NONE", "WEBHOOK", "JSON"]


@dataclass(frozen=True, slots=True)
class Organization:
    organization_id: str
    name: str
    slug: str
    created_at: str
    status: str = "ACTIVE"


@dataclass(frozen=True, slots=True)
class User:
    user_id: str
    display_name: str
    email: str | None
    created_at: str
    status: str = "ACTIVE"


@dataclass(frozen=True, slots=True)
class Membership:
    membership_id: str
    organization_id: str
    user_id: str
    role: Role
    workspace_id: str | None = None
    project_id: str | None = None
    created_at: str = ""


@dataclass(frozen=True, slots=True)
class Workspace:
    workspace_id: str
    organization_id: str
    name: str
    slug: str
    created_at: str
    status: str = "ACTIVE"


@dataclass(frozen=True, slots=True)
class Project:
    project_id: str
    workspace_id: str
    name: str
    slug: str
    created_at: str
    status: str = "ACTIVE"


@dataclass(frozen=True, slots=True)
class Property:
    property_id: str
    project_id: str
    name: str
    canonical_origin: str
    hostname: str
    created_at: str
    status: str = "ACTIVE"
    is_competitor: bool = False


@dataclass(frozen=True, slots=True)
class Environment:
    environment_id: str
    property_id: str
    name: str
    kind: EnvironmentKind
    base_origin: str
    created_at: str
    status: str = "ACTIVE"


@dataclass(frozen=True, slots=True)
class AuditIndexRecord:
    audit_id: str
    property_id: str
    environment_id: str
    workspace_path: str
    audit_db_sha256: str
    event_time: str
    status: str
    completion_status: str | None
    project_name: str
    auditor_version: str
    ruleset_version: str
    scoring_versions: tuple[str, ...]
    domains: tuple[str, ...]
    devices: tuple[str, ...]
    url_count: int
    indexed_at: str


@dataclass(frozen=True, slots=True)
class Milestone:
    milestone_id: str
    project_id: str
    property_id: str
    environment_id: str
    kind: MilestoneKind
    occurred_at: str
    title: str
    description: str | None
    release: str | None
    commit_sha: str | None
    branch: str | None
    source: str
    created_at: str
    created_by: str | None = None
    tags: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class DeploymentPair:
    milestone: Milestone
    baseline_audit_id: str | None
    current_audit_id: str | None
    baseline_reason: str
    current_reason: str
    comparable: bool | None
    compatibility_notes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class PageIdentity:
    page_identity_id: str
    property_id: str
    canonical_name: str
    created_at: str
    status: str = "ACTIVE"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Schedule:
    schedule_id: str
    project_id: str
    property_id: str
    environment_id: str
    name: str
    kind: ScheduleKind
    command_argv: tuple[str, ...]
    enabled: bool
    created_at: str
    interval_minutes: int | None = None
    daily_time: str | None = None
    next_run_at: str | None = None
    last_run_at: str | None = None
    last_status: str | None = None


@dataclass(frozen=True, slots=True)
class AlertRule:
    alert_rule_id: str
    project_id: str
    property_id: str
    environment_id: str
    name: str
    enabled: bool
    event_statuses: tuple[str, ...]
    min_severity: str
    destination: AlertDestination
    destination_env: str | None
    created_at: str


@dataclass(frozen=True, slots=True)
class Integration:
    integration_id: str
    organization_id: str
    workspace_id: str | None
    project_id: str | None
    property_id: str | None
    provider: str
    name: str
    secret_env: str | None
    configuration: dict[str, Any]
    created_at: str
    status: str = "ACTIVE"


@dataclass(frozen=True, slots=True)
class UsageEvent:
    usage_event_id: str
    organization_id: str
    project_id: str | None
    property_id: str | None
    audit_id: str | None
    occurred_at: str
    category: str
    quantity: float
    unit: str
    cost_estimate: float | None
    currency: str | None
    provider: str | None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ExternalDataset:
    dataset_id: str
    organization_id: str
    project_id: str
    property_id: str
    environment_id: str
    source_type: str
    period_start: str | None
    period_end: str | None
    captured_at: str
    artifact_path: str | None
    artifact_sha256: str | None
    row_count: int
    metadata: dict[str, Any] = field(default_factory=dict)
