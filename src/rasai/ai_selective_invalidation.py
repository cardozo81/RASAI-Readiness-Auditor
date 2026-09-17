"""Dependency-scoped AI staleness for evidence-version transitions.

The global evidence fingerprint versions an AUD but is intentionally not the invalidation
key for every AI purpose. A task records the evidence slice it actually consumed. When a
new evidence version is sealed, only tasks whose slice changed become STALE; unrelated
tasks remain valid and record the newer snapshot through which their dependency
fingerprint was revalidated.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import sqlite3
from typing import Any, Iterable

from rasai import ai_governance


_INSTALLED = False


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _connect(workspace: Any) -> sqlite3.Connection:
    connection = sqlite3.connect(workspace.database, timeout=5.0)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def ensure_schema(workspace: Any) -> None:
    ai_governance.ensure_schema(workspace)
    connection = _connect(workspace)
    try:
        with connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS ai_task_dependency_specs(
                    ai_task_id TEXT PRIMARY KEY REFERENCES ai_tasks(ai_task_id) ON DELETE CASCADE,
                    dependency_kind TEXT NOT NULL,
                    scope_key TEXT,
                    collection_keys_json TEXT NOT NULL,
                    dependency_fingerprint TEXT NOT NULL,
                    validated_snapshot_id TEXT NOT NULL REFERENCES ai_evidence_versions(evidence_snapshot_id),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_ai_task_dependencies_snapshot
                    ON ai_task_dependency_specs(validated_snapshot_id,dependency_kind);
                """
            )
    finally:
        connection.close()


def _table_exists(connection: sqlite3.Connection, name: str) -> bool:
    return connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone() is not None


def _technical_evidence_ids(connection: sqlite3.Connection, audit_id: str) -> tuple[str, ...]:
    if not _table_exists(connection, "m24_diagnostics"):
        return ()
    rows = connection.execute(
        "SELECT evidence_ids FROM m24_diagnostics WHERE audit_id=? ORDER BY rowid",
        (audit_id,),
    ).fetchall()
    values: list[str] = []
    for row in rows:
        try:
            raw = json.loads(str(row[0] or "[]"))
        except (TypeError, ValueError, json.JSONDecodeError):
            raw = []
        if not isinstance(raw, list):
            continue
        for value in raw:
            text = str(value).strip()
            if text and text not in values:
                values.append(text)
    return tuple(values)


def _evidence_slice(
    connection: sqlite3.Connection,
    *,
    audit_id: str,
    dependency_kind: str,
    scope_key: str | None,
) -> list[dict[str, Any]]:
    if not _table_exists(connection, "evidence"):
        return []
    kind = str(dependency_kind).upper()
    if kind == "SNAPSHOT_EVIDENCE":
        rows = connection.execute(
            "SELECT * FROM evidence WHERE audit_id=? AND snapshot_id=? ORDER BY evidence_id",
            (audit_id, str(scope_key or "")),
        ).fetchall()
    elif kind == "PAGE_EVIDENCE":
        rows = connection.execute(
            "SELECT * FROM evidence WHERE audit_id=? AND page_id=? ORDER BY evidence_id",
            (audit_id, str(scope_key or "")),
        ).fetchall()
    elif kind == "TECHNICAL_RESOURCE_EVIDENCE":
        ids = _technical_evidence_ids(connection, audit_id)
        if not ids:
            return []
        marks = ",".join("?" for _ in ids)
        rows = connection.execute(
            f"SELECT * FROM evidence WHERE audit_id=? AND evidence_id IN ({marks}) ORDER BY evidence_id",
            (audit_id, *ids),
        ).fetchall()
    else:
        rows = connection.execute(
            "SELECT * FROM evidence WHERE audit_id=? ORDER BY evidence_id",
            (audit_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def _snapshot_states(
    connection: sqlite3.Connection,
    snapshot_id: str,
    keys: Iterable[str],
) -> dict[str, str | None]:
    row = connection.execute(
        "SELECT collection_states_json FROM ai_evidence_versions WHERE evidence_snapshot_id=?",
        (snapshot_id,),
    ).fetchone()
    states: dict[str, Any] = {}
    if row is not None:
        try:
            raw = json.loads(str(row[0] or "{}"))
            if isinstance(raw, dict):
                states = raw
        except (TypeError, ValueError, json.JSONDecodeError):
            states = {}
    return {str(key): states.get(str(key)) for key in keys}


def dependency_fingerprint(
    *,
    workspace: Any,
    audit_id: str,
    evidence_snapshot_id: str,
    dependency_kind: str,
    scope_key: str | None = None,
    collection_keys: Iterable[str] = (),
) -> str:
    connection = _connect(workspace)
    try:
        keys = tuple(dict.fromkeys(str(key) for key in collection_keys if str(key).strip()))
        payload = {
            "kind": str(dependency_kind).upper(),
            "scope_key": scope_key,
            "evidence": _evidence_slice(
                connection,
                audit_id=audit_id,
                dependency_kind=dependency_kind,
                scope_key=scope_key,
            ),
            "collection_states": _snapshot_states(
                connection,
                evidence_snapshot_id,
                keys,
            ),
        }
        return _hash(payload)
    finally:
        connection.close()


def register_task_dependency(
    *,
    workspace: Any,
    ai_task_id: str,
    dependency_kind: str,
    scope_key: str | None = None,
    collection_keys: Iterable[str] = (),
) -> str:
    """Bind one AI task to the persisted evidence slice it actually consumes."""
    ensure_schema(workspace)
    connection = _connect(workspace)
    try:
        task = connection.execute(
            "SELECT audit_id,evidence_snapshot_id FROM ai_tasks WHERE ai_task_id=?",
            (ai_task_id,),
        ).fetchone()
        if task is None:
            raise KeyError(f"AI task not found: {ai_task_id}")
        audit_id = str(task["audit_id"])
        snapshot_id = str(task["evidence_snapshot_id"])
    finally:
        connection.close()
    keys = tuple(dict.fromkeys(str(key) for key in collection_keys if str(key).strip()))
    fingerprint = dependency_fingerprint(
        workspace=workspace,
        audit_id=audit_id,
        evidence_snapshot_id=snapshot_id,
        dependency_kind=dependency_kind,
        scope_key=scope_key,
        collection_keys=keys,
    )
    now = _now()
    connection = _connect(workspace)
    try:
        with connection:
            connection.execute(
                """INSERT INTO ai_task_dependency_specs(
                    ai_task_id,dependency_kind,scope_key,collection_keys_json,
                    dependency_fingerprint,validated_snapshot_id,created_at,updated_at
                ) VALUES(?,?,?,?,?,?,?,?)
                ON CONFLICT(ai_task_id) DO UPDATE SET
                    dependency_kind=excluded.dependency_kind,
                    scope_key=excluded.scope_key,
                    collection_keys_json=excluded.collection_keys_json,
                    dependency_fingerprint=excluded.dependency_fingerprint,
                    validated_snapshot_id=excluded.validated_snapshot_id,
                    updated_at=excluded.updated_at""",
                (
                    ai_task_id,
                    str(dependency_kind).upper(),
                    scope_key,
                    _canonical(keys),
                    fingerprint,
                    snapshot_id,
                    now,
                    now,
                ),
            )
    finally:
        connection.close()
    return fingerprint


def _task_state_before_seal(workspace: Any, audit_id: str, snapshot_id: str):
    ensure_schema(workspace)
    connection = _connect(workspace)
    try:
        rows = connection.execute(
            """SELECT t.ai_task_id,t.status,d.dependency_kind,d.scope_key,
                      d.collection_keys_json,d.dependency_fingerprint
               FROM ai_tasks t
               LEFT JOIN ai_task_dependency_specs d ON d.ai_task_id=t.ai_task_id
               WHERE t.audit_id=? AND t.evidence_snapshot_id=?""",
            (audit_id, snapshot_id),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        connection.close()


def _reconcile_staleness(
    *,
    workspace: Any,
    audit_id: str,
    prior_snapshot: Any,
    new_snapshot: Any,
    prior_tasks: list[dict[str, Any]],
) -> None:
    if prior_snapshot is None or prior_snapshot.evidence_snapshot_id == new_snapshot.evidence_snapshot_id:
        return
    now = _now()
    connection = _connect(workspace)
    try:
        for task in prior_tasks:
            task_id = str(task["ai_task_id"])
            kind = task.get("dependency_kind")
            if not kind:
                continue
            try:
                keys_raw = json.loads(str(task.get("collection_keys_json") or "[]"))
            except (TypeError, ValueError, json.JSONDecodeError):
                keys_raw = []
            keys = tuple(str(value) for value in keys_raw if str(value).strip())
            current = dependency_fingerprint(
                workspace=workspace,
                audit_id=audit_id,
                evidence_snapshot_id=new_snapshot.evidence_snapshot_id,
                dependency_kind=str(kind),
                scope_key=(
                    str(task["scope_key"])
                    if task.get("scope_key") is not None
                    else None
                ),
                collection_keys=keys,
            )
            previous = str(task.get("dependency_fingerprint") or "")
            if current == previous:
                with connection:
                    connection.execute(
                        "UPDATE ai_tasks SET status=?,stale_reason=NULL,updated_at=? WHERE ai_task_id=?",
                        (str(task["status"]), now, task_id),
                    )
                    connection.execute(
                        """UPDATE ai_task_dependency_specs
                           SET validated_snapshot_id=?,updated_at=? WHERE ai_task_id=?""",
                        (new_snapshot.evidence_snapshot_id, now, task_id),
                    )
            else:
                with connection:
                    connection.execute(
                        """UPDATE ai_tasks SET status=?,stale_reason=?,updated_at=?
                           WHERE ai_task_id=?""",
                        (
                            ai_governance.TASK_STALE,
                            f"DEPENDENCY_CHANGED:{new_snapshot.evidence_snapshot_id}",
                            now,
                            task_id,
                        ),
                    )
    finally:
        connection.close()


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    ensure_target = ai_governance.seal_evidence
    if bool(getattr(ensure_target, "_rasai_selective_invalidation", False)):
        _INSTALLED = True
        return

    def seal_evidence(*args: Any, **kwargs: Any):
        workspace = kwargs.get("workspace")
        audit_id = str(kwargs.get("audit_id") or "")
        if workspace is None or not audit_id:
            return ensure_target(*args, **kwargs)
        prior = ai_governance.latest_evidence_snapshot(workspace, audit_id)
        prior_tasks = (
            _task_state_before_seal(
                workspace,
                audit_id,
                prior.evidence_snapshot_id,
            )
            if prior is not None
            else []
        )
        current = ensure_target(*args, **kwargs)
        _reconcile_staleness(
            workspace=workspace,
            audit_id=audit_id,
            prior_snapshot=prior,
            new_snapshot=current,
            prior_tasks=prior_tasks,
        )
        return current

    seal_evidence._rasai_selective_invalidation = True
    seal_evidence._rasai_original = ensure_target
    ai_governance.seal_evidence = seal_evidence

    try:
        from rasai import audit_phase_runtime
        if getattr(audit_phase_runtime, "seal_evidence", None) is ensure_target:
            audit_phase_runtime.seal_evidence = seal_evidence
    except ImportError:
        pass
    _INSTALLED = True


__all__ = [
    "dependency_fingerprint",
    "ensure_schema",
    "install",
    "register_task_dependency",
]
