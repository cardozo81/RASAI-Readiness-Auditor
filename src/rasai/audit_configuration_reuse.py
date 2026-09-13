"""Reusable, secret-free configuration snapshots for completed AUD executions.

This module deliberately separates two concepts:

* AUD reprocessing completes missing work inside the same AUD identity;
* configuration reuse starts a new AUD using a completed AUD as configuration source.

Only audits accepted by the canonical consolidation eligibility gate may be used as
sources. Snapshots are stored inside ``audit.db`` so provenance travels with the
immutable audit evidence instead of depending on a console INI or control-plane row.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any, Mapping
from uuid import uuid4

from rasai.audit_fulfillment import consolidation_eligible

CONFIGURATION_SCHEMA_VERSION = "1"
KIND_CONSOLE = "CONSOLE"
KIND_AUDIT_PAYLOAD = "AUDIT_PAYLOAD"
_SUPPORTED_KINDS = frozenset({KIND_CONSOLE, KIND_AUDIT_PAYLOAD})

# Durable job provenance is intentionally not part of the execution configuration
# fingerprint. These fields describe where a configuration came from, not what the
# audit is configured to measure.
PROVENANCE_FIELDS = frozenset({
    "configuration_source_audit_id",
    "configuration_source_hash",
    "configuration_changed_fields",
    "execution_series_id",
})


@dataclass(frozen=True, slots=True)
class ReusableAuditConfiguration:
    audit_id: str
    kind: str
    configuration: dict[str, Any]
    configuration_hash: str
    execution_series_id: str
    source_audit_id: str | None
    source_configuration_hash: str | None
    changed_fields: tuple[str, ...]
    scope: dict[str, Any]
    created_at: str


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def configuration_hash(configuration: Mapping[str, Any]) -> str:
    payload = _canonical_json(dict(configuration)).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def strip_provenance(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if key not in PROVENANCE_FIELDS}


def _flatten(value: Any, prefix: str = "") -> dict[str, Any]:
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key in sorted(value):
            name = f"{prefix}.{key}" if prefix else str(key)
            result.update(_flatten(value[key], name))
        return result
    if isinstance(value, list):
        return {prefix: tuple(value)}
    return {prefix: value}


def changed_fields(source: Mapping[str, Any], effective: Mapping[str, Any]) -> tuple[str, ...]:
    before = _flatten(source)
    after = _flatten(effective)
    return tuple(
        key
        for key in sorted(set(before) | set(after))
        if before.get(key) != after.get(key)
    )


def _database(path: str | Path) -> Path:
    candidate = Path(path)
    if candidate.name == "audit.db":
        return candidate
    return candidate / "audit.db"


def _ensure_table(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS audit_execution_configurations (
            audit_id TEXT PRIMARY KEY REFERENCES audits(audit_id) ON DELETE CASCADE,
            schema_version TEXT NOT NULL,
            configuration_kind TEXT NOT NULL,
            configuration_json TEXT NOT NULL,
            configuration_hash TEXT NOT NULL,
            source_audit_id TEXT,
            source_configuration_hash TEXT,
            changed_fields_json TEXT NOT NULL,
            execution_series_id TEXT NOT NULL,
            scope_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )


def persist_audit_configuration(
    database_or_workspace: str | Path,
    *,
    audit_id: str,
    kind: str,
    configuration: Mapping[str, Any],
    source_audit_id: str | None = None,
    source_configuration_hash: str | None = None,
    changed: tuple[str, ...] = (),
    execution_series_id: str | None = None,
    scope: Mapping[str, Any] | None = None,
) -> ReusableAuditConfiguration:
    """Persist one complete, secret-free effective configuration for an AUD."""
    if kind not in _SUPPORTED_KINDS:
        raise ValueError(f"unsupported reusable configuration kind: {kind}")
    database = _database(database_or_workspace)
    if not database.is_file():
        raise FileNotFoundError(database)
    clean = dict(configuration)
    digest = configuration_hash(clean)
    series_id = (execution_series_id or "").strip() or f"SER-{uuid4().hex.upper()}"
    now = datetime.now(timezone.utc).isoformat()
    scope_payload = dict(scope or {})
    connection = sqlite3.connect(database, timeout=2.0)
    try:
        with connection:
            _ensure_table(connection)
            connection.execute(
                """
                INSERT OR REPLACE INTO audit_execution_configurations(
                    audit_id,schema_version,configuration_kind,configuration_json,
                    configuration_hash,source_audit_id,source_configuration_hash,
                    changed_fields_json,execution_series_id,scope_json,created_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    audit_id,
                    CONFIGURATION_SCHEMA_VERSION,
                    kind,
                    _canonical_json(clean),
                    digest,
                    source_audit_id,
                    source_configuration_hash,
                    _canonical_json(list(changed)),
                    series_id,
                    _canonical_json(scope_payload),
                    now,
                ),
            )
    finally:
        connection.close()
    return ReusableAuditConfiguration(
        audit_id=audit_id,
        kind=kind,
        configuration=clean,
        configuration_hash=digest,
        execution_series_id=series_id,
        source_audit_id=source_audit_id,
        source_configuration_hash=source_configuration_hash,
        changed_fields=tuple(changed),
        scope=scope_payload,
        created_at=now,
    )


def _read_row(database: Path, audit_id: str) -> sqlite3.Row | None:
    connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True, timeout=1.0)
    connection.row_factory = sqlite3.Row
    try:
        exists = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='audit_execution_configurations'"
        ).fetchone()
        if not exists:
            return None
        return connection.execute(
            "SELECT * FROM audit_execution_configurations WHERE audit_id=?",
            (audit_id,),
        ).fetchone()
    finally:
        connection.close()


def load_reusable_audit_configuration(
    audits_root: str | Path,
    audit_id: str,
    *,
    expected_kind: str | None = None,
) -> ReusableAuditConfiguration:
    """Load a reusable configuration, failing closed on incomplete/non-final AUDs."""
    normalized_id = str(audit_id).strip().upper()
    if not normalized_id.startswith("AUD-"):
        raise ValueError("informe um Audit ID válido no formato AUD-*")
    workspace = Path(audits_root) / normalized_id
    database = workspace / "audit.db"
    if not database.is_file():
        raise FileNotFoundError(f"audit não encontrado: {normalized_id}")
    if not consolidation_eligible(database, normalized_id):
        raise ValueError(
            f"{normalized_id} não pode ser usado como configuração: "
            "somente AUDs com consolidação geral concluída e elegível são aceitos"
        )
    row = _read_row(database, normalized_id)
    if row is None:
        raise ValueError(
            f"{normalized_id} é elegível para consolidação, mas não possui snapshot "
            "canônico de configuração reutilizável; execute-o com uma versão que suporte este contrato"
        )
    kind = str(row["configuration_kind"])
    if expected_kind is not None and kind != expected_kind:
        raise ValueError(
            f"{normalized_id} possui configuração {kind}; esta superfície exige {expected_kind}"
        )
    if str(row["schema_version"]) != CONFIGURATION_SCHEMA_VERSION:
        raise ValueError(
            f"snapshot de configuração de {normalized_id} usa schema incompatível: "
            f"{row['schema_version']}"
        )
    try:
        configuration = json.loads(str(row["configuration_json"]))
        changed = json.loads(str(row["changed_fields_json"]))
        scope = json.loads(str(row["scope_json"]))
    except json.JSONDecodeError as exc:
        raise ValueError(f"snapshot de configuração corrompido em {normalized_id}") from exc
    if not isinstance(configuration, dict) or not isinstance(scope, dict) or not isinstance(changed, list):
        raise ValueError(f"snapshot de configuração inválido em {normalized_id}")
    digest = configuration_hash(configuration)
    persisted_digest = str(row["configuration_hash"])
    if digest != persisted_digest:
        raise ValueError(f"hash do snapshot de configuração não confere em {normalized_id}")
    return ReusableAuditConfiguration(
        audit_id=normalized_id,
        kind=kind,
        configuration=configuration,
        configuration_hash=persisted_digest,
        execution_series_id=str(row["execution_series_id"]),
        source_audit_id=str(row["source_audit_id"]) if row["source_audit_id"] else None,
        source_configuration_hash=(
            str(row["source_configuration_hash"])
            if row["source_configuration_hash"]
            else None
        ),
        changed_fields=tuple(str(item) for item in changed),
        scope=scope,
        created_at=str(row["created_at"]),
    )
