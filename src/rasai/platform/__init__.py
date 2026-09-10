"""RASAi product-platform layer.

This package provides multi-organization product metadata without mutating
immutable AUD workspaces. SQLite is the local control-plane backend and
PostgreSQL is available through the centralized control-plane composition.
Storage and execution contracts remain separate.
"""

from pathlib import Path

from rasai.runtime_paths import CANONICAL_RUNTIME_DIR, runtime_directory

# Bind the store module to the canonical local runtime directory before exposing
# the composed product-platform API.
from . import store as _store

_store._PLATFORM_DIR = CANONICAL_RUNTIME_DIR


def default_platform_database(audits_root: str | Path = "audits") -> Path:
    return runtime_directory(audits_root) / _store._PLATFORM_DB


_store.default_platform_database = default_platform_database

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
from .central_store import CentralPlatformStore, CentralPlatformStore as PlatformStore

__all__ = [
    "AlertRule",
    "AuditIndexRecord",
    "CentralPlatformStore",
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