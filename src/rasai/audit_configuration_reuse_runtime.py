"""Execution-scoped bridge for persisting configuration before AUD indexing.

The control plane hashes ``audit.db`` after the canonical audit finalizer returns.
Configuration lineage must therefore be written from inside that finalization window,
never by console/worker code after the entrypoint has already indexed the AUD.

The local interactive console starts the audit engine in a child Python process.
``ContextVar`` state is process-local, so console configurations also use a short-lived,
secret-free JSON handoff inherited by that child. The handoff only transports the
configuration already bound by ``configuration_context``; canonical persistence still
happens inside the audit process before indexing.
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Iterator, Mapping

from rasai.audit_configuration_reuse import KIND_CONSOLE, persist_audit_configuration

_HANDOFF_ENV = "_RASAI_AUD_CONFIGURATION_HANDOFF"
_HANDOFF_SCHEMA_VERSION = 1
_HANDOFF_MAX_BYTES = 4 * 1024 * 1024


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


def _handoff_payload(pending: PendingAuditConfiguration) -> dict[str, Any]:
    return {
        "schema_version": _HANDOFF_SCHEMA_VERSION,
        "kind": pending.kind,
        "configuration": pending.configuration,
        "source_audit_id": pending.source_audit_id,
        "source_configuration_hash": pending.source_configuration_hash,
        "changed_fields": list(pending.changed_fields),
        "execution_series_id": pending.execution_series_id,
        "scope": pending.scope,
    }


def _pending_from_handoff_payload(payload: Any) -> PendingAuditConfiguration:
    if not isinstance(payload, Mapping):
        raise ValueError("handoff de configuração do console possui payload inválido")
    if payload.get("schema_version") != _HANDOFF_SCHEMA_VERSION:
        raise ValueError("handoff de configuração do console usa schema incompatível")

    kind = str(payload.get("kind") or "").strip()
    configuration = payload.get("configuration")
    changed = payload.get("changed_fields", [])
    scope = payload.get("scope", {})
    if kind != KIND_CONSOLE or not isinstance(configuration, dict):
        raise ValueError("handoff de configuração do console está incompleto ou possui tipo inválido")
    if not isinstance(changed, list) or not isinstance(scope, dict):
        raise ValueError("handoff de configuração do console possui estrutura inválida")

    def optional_text(name: str) -> str | None:
        value = payload.get(name)
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError(f"handoff de configuração do console possui {name} inválido")
        normalized = value.strip()
        return normalized or None

    return PendingAuditConfiguration(
        kind=kind,
        configuration=dict(configuration),
        source_audit_id=optional_text("source_audit_id"),
        source_configuration_hash=optional_text("source_configuration_hash"),
        changed_fields=tuple(str(item) for item in changed),
        execution_series_id=optional_text("execution_series_id"),
        scope=dict(scope),
    )


def _write_subprocess_handoff(pending: PendingAuditConfiguration) -> Path:
    payload = _handoff_payload(pending)
    descriptor, raw_path = tempfile.mkstemp(prefix="rasai-aud-config-", suffix=".json")
    path = Path(raw_path)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(
                payload,
                stream,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            stream.write("\n")
    except Exception:
        try:
            os.close(descriptor)
        except OSError:
            pass
        path.unlink(missing_ok=True)
        raise
    return path


@contextmanager
def _subprocess_handoff_context(
    pending: PendingAuditConfiguration,
) -> Iterator[None]:
    """Expose a console snapshot to child processes for the lifetime of this context."""
    if pending.kind != KIND_CONSOLE:
        yield
        return

    path = _write_subprocess_handoff(pending)
    previous = os.environ.get(_HANDOFF_ENV)
    os.environ[_HANDOFF_ENV] = str(path)
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop(_HANDOFF_ENV, None)
        else:
            os.environ[_HANDOFF_ENV] = previous
        path.unlink(missing_ok=True)


def load_subprocess_configuration_handoff() -> PendingAuditConfiguration | None:
    """Load the inherited console handoff, if this process was started by the console."""
    raw_path = (os.environ.get(_HANDOFF_ENV) or "").strip()
    if not raw_path:
        return None

    path = Path(raw_path)
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise ValueError("handoff de configuração do console não está acessível") from exc
    if size <= 0 or size > _HANDOFF_MAX_BYTES:
        raise ValueError("handoff de configuração do console possui tamanho inválido")

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("handoff de configuração do console está corrompido") from exc
    return _pending_from_handoff_payload(payload)


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
        with _subprocess_handoff_context(pending):
            yield
    finally:
        _CURRENT.reset(token)


def current_configuration() -> PendingAuditConfiguration | None:
    return _CURRENT.get()


def persist_current_configuration(workspace: str | Path, audit_id: str) -> bool:
    """Persist the bound or inherited snapshot while audit.db is still mutable."""
    pending = _CURRENT.get()
    if pending is None:
        pending = load_subprocess_configuration_handoff()
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
