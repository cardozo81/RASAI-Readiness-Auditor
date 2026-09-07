"""RASAI product-platform layer.

This package adds SaaS-ready, multi-organization product metadata without
mutating immutable AUD workspaces. The local Windows implementation uses a
central SQLite sidecar and keeps storage/execution contracts intentionally
separate so a future PostgreSQL/API adapter can replace the control plane.
"""

from .models import (
    AlertRule,
    AuditIndexRecord,
    DeploymentPair,
    Environment,
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
from .store import PlatformStore, default_platform_database

__all__ = [
    "AlertRule",
    "AuditIndexRecord",
    "DeploymentPair",
    "Environment",
    "Integration",
    "Milestone",
    "Organization",
    "PageIdentity",
    "PlatformStore",
    "Project",
    "Property",
    "Schedule",
    "UsageEvent",
    "User",
    "Workspace",
    "default_platform_database",
]
