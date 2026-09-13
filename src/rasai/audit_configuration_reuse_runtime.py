"""Execution-scoped bridge for persisting configuration before AUD indexing.

The control plane hashes ``audit.db`` after the canonical audit finalizer returns.
Configuration lineage must therefore be written from inside that finalization window,
never by console/worker code after the entrypoint has already indexed the AUD.
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, Mapping

from rasai.audit_configuration_reuse import persist_audit_configuration


@dataclass(frozen=True, slots=True)
class PendingAuditConfiguration:
    kind: str
    configuration: dict[str, Any]
    source_audit_id: str | None
    source_configuration_hash: str | None
    changed_fields: tuple[str, ...]
    execution_series_id: str | None
    scope: dict[str, Any]


_CURRENT: ContextVar[PendingAuditConfiguration | None] = ContextVar(
    "rasai_pending_audit_configuration",
    default=None,
)


@contextmanager
def configuration_context(
    *,
    kind: str,
    configuration: Mapping[str, Any],
    source_audit_id: str | None = None,
    source_configuration_hash: str | None = None,
    changed_fields: tuple[str, ...] = (),
    execution_series_id: str | None = None,
    scope: Mapping[str, Any] | None = None,
) -> Iterator[None]:
    """Bind one execution's effective, secret-free configuration to its finalizer."""
    pending = PendingAuditConfiguration(
        kind=kind,
        configuration=dict(configuration),
        source_audit_id=source_audit_id,
        source_configuration_hash=source_configuration_hash,
        changed_fields=tuple(changed_fields),
        execution_series_id=execution_series_id,
        scope=dict(scope or {}),
    )
    token = _CURRENT.set(pending)
    try:
        yield
    finally:
        _CURRENT.reset(token)


def current_configuration() -> PendingAuditConfiguration | None:
    return _CURRENT.get()


def persist_current_configuration(workspace: str | Path, audit_id: str) -> bool:
    """Persist the bound snapshot while audit.db is still inside its mutable window."""
    pending = _CURRENT.get()
    if pending is None:
        return False
    persist_audit_configuration(
        workspace,
        audit_id=audit_id,
        kind=pending.kind,
        configuration=pending.configuration,
        source_audit_id=pending.source_audit_id,
        source_configuration_hash=pending.source_configuration_hash,
        changed=pending.changed_fields,
        execution_series_id=pending.execution_series_id,
        scope=pending.scope,
    )
    return True
