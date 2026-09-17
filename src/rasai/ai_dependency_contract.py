"""Durable dependency snapshots proving which context existed before an AI purpose ran.

This table is governance metadata, not website evidence. It records the declared
prerequisites, their effective states and a content/evidence fingerprint immediately
before the provider boundary. A NOT_READY snapshot must never be followed by the
corresponding provider call in the wrappers installed by :mod:`ai_dependency_runtime`.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import sqlite3
from typing import Any, Iterable, Mapping

from rasai.audit_fulfillment import DISABLED, NOT_APPLICABLE, SUCCESS, list_work_items

CONTRACT_VERSION="AI-DEPENDENCY-001"
_READY_STATES={SUCCESS,NOT_APPLICABLE,DISABLED}


def _canonical(value: Any) -> str:
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":"),default=str)


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _now() -> str:return datetime.now(timezone.utc).isoformat()


def _id(audit_id: str,purpose: str,scope_key: str,fingerprint: str) -> str:
    return "AID-"+hashlib.sha256(f"{audit_id}|{purpose}|{scope_key}|{fingerprint}".encode()).hexdigest()[:32].upper()


def record_dependency_snapshot(
    *,workspace: Any,audit_id: str,purpose: str,scope_key: str="AUDIT",
    expected: Iterable[str],present: Mapping[str,Any],evidence_ids: Iterable[str]=(),
    context_fingerprint_input: Any=None,ready: bool,
) -> str:
    expected_values=tuple(dict.fromkeys(str(v) for v in expected if str(v).strip()))
    present_values={str(k):v for k,v in present.items()}
    missing=tuple(name for name in expected_values if name not in present_values or str(present_values[name]).upper() not in _READY_STATES and present_values[name] is not True)
    ids=tuple(dict.fromkeys(str(v) for v in evidence_ids if str(v).strip()))
    fingerprint=_hash({"expected":expected_values,"present":present_values,"evidence_ids":ids,"context":context_fingerprint_input})
    snapshot_id=_id(audit_id,purpose,scope_key,fingerprint)
    connection=sqlite3.connect(workspace.database)
    try:
        with connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS ai_dependency_snapshots(
                    dependency_snapshot_id TEXT PRIMARY KEY,
                    audit_id TEXT NOT NULL REFERENCES audits(audit_id) ON DELETE CASCADE,
                    purpose TEXT NOT NULL,
                    scope_key TEXT NOT NULL,
                    expected_json TEXT NOT NULL,
                    present_json TEXT NOT NULL,
                    missing_json TEXT NOT NULL,
                    evidence_ids_json TEXT NOT NULL,
                    context_fingerprint TEXT NOT NULL,
                    ready INTEGER NOT NULL,
                    contract_version TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_ai_dependencies_audit_purpose
                    ON ai_dependency_snapshots(audit_id,purpose,created_at);
                """
            )
            connection.execute(
                """INSERT OR IGNORE INTO ai_dependency_snapshots VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                (snapshot_id,audit_id,purpose,scope_key,_canonical(expected_values),_canonical(present_values),
                 _canonical(missing),_canonical(ids),fingerprint,1 if ready else 0,CONTRACT_VERSION,_now()),
            )
    finally:connection.close()
    return snapshot_id


def fulfillment_dependency_state(workspace: Any,audit_id: str,*,exclude_components: Iterable[str]=()) -> tuple[tuple[str,...],dict[str,str],bool]:
    excluded={str(value).upper() for value in exclude_components}
    items=tuple(item for item in list_work_items(workspace,audit_id) if item.required and item.component not in excluded and item.status not in {DISABLED,NOT_APPLICABLE})
    expected=tuple(dict.fromkeys(item.component for item in items))
    present={item.component:item.status for item in items}
    ready=all(item.status==SUCCESS for item in items)
    return expected,present,ready


def latest_dependency_snapshot(database: Any,audit_id: str,purpose: str) -> dict[str,Any]|None:
    connection=sqlite3.connect(database);connection.row_factory=sqlite3.Row
    try:
        exists=connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='ai_dependency_snapshots'").fetchone()
        if not exists:return None
        row=connection.execute("SELECT * FROM ai_dependency_snapshots WHERE audit_id=? AND purpose=? ORDER BY created_at DESC,rowid DESC LIMIT 1",(audit_id,purpose)).fetchone()
        return dict(row) if row is not None else None
    finally:connection.close()


__all__=["CONTRACT_VERSION","record_dependency_snapshot","fulfillment_dependency_state","latest_dependency_snapshot"]
