"""Durable evidence-version and AI-task governance.

This module is deliberately orthogonal to provider routing.  Provider selection,
retry/fallback, quarantine, pricing and token telemetry remain owned by the existing
AI runtime.  The structures below answer a different set of questions:

* which persisted evidence version was available before an AI purpose ran;
* which logical requirements belonged to that purpose;
* which requirements were accepted, rejected or still missing after each round; and
* when a previously accepted result became stale because its evidence changed.

The tables are additive.  Existing evidence, provider-attempt, raw-response and cost
records remain the source of truth for their respective concerns.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import sqlite3
from typing import Any, Iterable, Mapping, Sequence


CONTRACT_VERSION = "AI-GOVERNANCE-001"

TASK_PENDING = "PENDING"
TASK_READY = "READY"
TASK_RUNNING = "RUNNING"
TASK_PARTIAL = "PARTIAL"
TASK_COMPLETE = "COMPLETE"
TASK_BLOCKED = "BLOCKED"
TASK_FAILED = "FAILED"
TASK_SKIPPED = "SKIPPED"
TASK_STALE = "STALE"

ROUND_RUNNING = "RUNNING"
ROUND_COMPLETE = "COMPLETE"
ROUND_PARTIAL = "PARTIAL"
ROUND_FAILED = "FAILED"

TERMINAL_COLLECTION_STATES = frozenset(
    {
        "SUCCESS",
        "PARTIAL",
        "ERROR",
        "FAILED_RETRYABLE",
        "FAILED_PERMANENT",
        "BLOCKED",
        "SKIPPED",
        "DISABLED",
        "NOT_CONFIGURED",
        "NOT_APPLICABLE",
        "NO_DATA",
        "REQUESTED_NOT_EXECUTED",
        "SKIPPED_SOURCE_BLOCKER",
    }
)
NON_TERMINAL_COLLECTION_STATES = frozenset(
    {"PENDING", "RUNNING", "PROCESSING", "WAITING_FOR_DATA"}
)


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


def _new_id(prefix: str, *parts: Any) -> str:
    digest = hashlib.sha256("|".join(str(part) for part in parts).encode("utf-8")).hexdigest()
    return f"{prefix}-{digest[:32].upper()}"


def _connect(workspace: Any) -> sqlite3.Connection:
    connection = sqlite3.connect(workspace.database, timeout=5.0)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def ensure_schema(workspace: Any) -> None:
    connection = _connect(workspace)
    try:
        with connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS ai_evidence_versions(
                    evidence_snapshot_id TEXT PRIMARY KEY,
                    audit_id TEXT NOT NULL REFERENCES audits(audit_id) ON DELETE CASCADE,
                    version_number INTEGER NOT NULL,
                    fingerprint TEXT NOT NULL,
                    evidence_ids_json TEXT NOT NULL,
                    collection_states_json TEXT NOT NULL,
                    context_json TEXT NOT NULL,
                    supersedes_snapshot_id TEXT REFERENCES ai_evidence_versions(evidence_snapshot_id),
                    contract_version TEXT NOT NULL,
                    sealed_at TEXT NOT NULL,
                    UNIQUE(audit_id,version_number),
                    UNIQUE(audit_id,fingerprint)
                );

                CREATE INDEX IF NOT EXISTS idx_ai_evidence_versions_audit
                    ON ai_evidence_versions(audit_id,version_number DESC);

                CREATE TABLE IF NOT EXISTS ai_tasks(
                    ai_task_id TEXT PRIMARY KEY,
                    audit_id TEXT NOT NULL REFERENCES audits(audit_id) ON DELETE CASCADE,
                    purpose TEXT NOT NULL,
                    scope_type TEXT NOT NULL,
                    scope_key TEXT NOT NULL,
                    evidence_snapshot_id TEXT NOT NULL REFERENCES ai_evidence_versions(evidence_snapshot_id),
                    semantic_contract_version TEXT,
                    prompt_id TEXT,
                    prompt_version TEXT,
                    requirements_json TEXT NOT NULL,
                    accepted_json TEXT NOT NULL,
                    rejected_json TEXT NOT NULL,
                    missing_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    stale_reason TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(audit_id,purpose,scope_type,scope_key,evidence_snapshot_id)
                );

                CREATE INDEX IF NOT EXISTS idx_ai_tasks_audit_status
                    ON ai_tasks(audit_id,status,purpose);

                CREATE TABLE IF NOT EXISTS ai_request_rounds(
                    ai_round_id TEXT PRIMARY KEY,
                    ai_task_id TEXT NOT NULL REFERENCES ai_tasks(ai_task_id) ON DELETE CASCADE,
                    round_index INTEGER NOT NULL,
                    requested_requirements_json TEXT NOT NULL,
                    input_hash TEXT NOT NULL,
                    input_summary_json TEXT NOT NULL,
                    output_hash TEXT,
                    accepted_json TEXT NOT NULL,
                    rejected_json TEXT NOT NULL,
                    missing_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    finished_at TEXT,
                    UNIQUE(ai_task_id,round_index)
                );

                CREATE INDEX IF NOT EXISTS idx_ai_rounds_task
                    ON ai_request_rounds(ai_task_id,round_index);
                """
            )
    finally:
        connection.close()


def normalize_collection_state(value: Any) -> str:
    if value is True:
        return "SUCCESS"
    if value is False:
        return "PENDING"
    return str(value or "UNKNOWN").strip().upper()


def collection_state_is_terminal(value: Any) -> bool:
    state = normalize_collection_state(value)
    if state in TERMINAL_COLLECTION_STATES:
        return True
    if state in NON_TERMINAL_COLLECTION_STATES or state in {"", "UNKNOWN"}:
        return False
    # Unknown future states are fail-closed: a new state must be classified explicitly
    # before it can release an AI dependency gate.
    return False


def dependency_gate(
    *,
    expected: Iterable[str],
    present: Mapping[str, Any],
    success_required: Iterable[str] = (),
) -> tuple[bool, tuple[str, ...], tuple[str, ...]]:
    """Evaluate task dependencies without confusing terminal with successful.

    ``missing`` contains dependencies that have not reached a terminal state.
    ``degraded`` contains terminal dependencies that are not SUCCESS.  Callers may
    choose to block a task by placing a dependency in ``success_required`` while
    allowing unrelated optional terminal failures to remain provenance only.
    """

    expected_values = tuple(dict.fromkeys(str(item) for item in expected if str(item).strip()))
    required_success = {str(item) for item in success_required}
    missing: list[str] = []
    degraded: list[str] = []
    for name in expected_values:
        if name not in present:
            missing.append(name)
            continue
        state = normalize_collection_state(present[name])
        if not collection_state_is_terminal(state):
            missing.append(name)
            continue
        if state != "SUCCESS" and name in required_success:
            degraded.append(name)
    return not missing and not degraded, tuple(missing), tuple(degraded)


def _audit_evidence_ids(connection: sqlite3.Connection, audit_id: str) -> tuple[str, ...]:
    exists = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='evidence'"
    ).fetchone()
    if exists is None:
        return ()
    rows = connection.execute(
        "SELECT evidence_id FROM evidence WHERE audit_id=? ORDER BY evidence_id",
        (audit_id,),
    ).fetchall()
    return tuple(str(row[0]) for row in rows if row[0])


def _durable_collection_states(connection: sqlite3.Connection, audit_id: str) -> dict[str, str]:
    result: dict[str, str] = {}
    if connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='standards_service_runs'"
    ).fetchone():
        for row in connection.execute(
            "SELECT service_id,state FROM standards_service_runs WHERE audit_id=? ORDER BY service_id",
            (audit_id,),
        ):
            result[f"SERVICE:{row[0]}"] = normalize_collection_state(row[1])
    if connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='audit_fulfillment_work_items'"
    ).fetchone():
        for row in connection.execute(
            """SELECT component,scope_key,status FROM audit_fulfillment_work_items
               WHERE audit_id=? ORDER BY component,scope_key""",
            (audit_id,),
        ):
            result[f"WORK:{row[0]}:{row[1]}"] = normalize_collection_state(row[2])
    for table, component, column in (
        ("m21_runs", "WEB_PERFORMANCE", "status"),
        ("m23_runs", "SYNTHETIC_APDEX", "status"),
        ("m25_runs", "EXPERIENCE_APDEX", "status"),
        ("m24_runs", "CRAWLING_DISCOVERY", "status"),
    ):
        try:
            row = connection.execute(
                f"SELECT {column} FROM {table} WHERE audit_id=? LIMIT 1",
                (audit_id,),
            ).fetchone()
        except sqlite3.OperationalError:
            row = None
        if row is not None:
            result[component] = normalize_collection_state(row[0])
    return result


@dataclass(frozen=True, slots=True)
class EvidenceSnapshot:
    evidence_snapshot_id: str
    audit_id: str
    version_number: int
    fingerprint: str
    evidence_ids: tuple[str, ...]
    collection_states: dict[str, str]
    context: dict[str, Any]
    sealed_at: str


def seal_evidence(
    *,
    workspace: Any,
    audit_id: str,
    collection_states: Mapping[str, Any] | None = None,
    context: Mapping[str, Any] | None = None,
    evidence_ids: Sequence[str] | None = None,
) -> EvidenceSnapshot:
    """Create/reuse an immutable evidence version immediately before AI execution."""

    ensure_schema(workspace)
    connection = _connect(workspace)
    try:
        durable_ids = tuple(evidence_ids) if evidence_ids is not None else _audit_evidence_ids(connection, audit_id)
        durable_states = _durable_collection_states(connection, audit_id)
        durable_states.update(
            {
                str(key): normalize_collection_state(value)
                for key, value in (collection_states or {}).items()
            }
        )
        normalized_context = dict(context or {})
        fingerprint = _hash(
            {
                "evidence_ids": durable_ids,
                "collection_states": durable_states,
                "context": normalized_context,
            }
        )
        existing = connection.execute(
            "SELECT * FROM ai_evidence_versions WHERE audit_id=? AND fingerprint=?",
            (audit_id, fingerprint),
        ).fetchone()
        if existing is not None:
            return _snapshot_from_row(existing)
        latest = connection.execute(
            """SELECT * FROM ai_evidence_versions WHERE audit_id=?
               ORDER BY version_number DESC LIMIT 1""",
            (audit_id,),
        ).fetchone()
        version = int(latest["version_number"]) + 1 if latest is not None else 1
        supersedes = str(latest["evidence_snapshot_id"]) if latest is not None else None
        snapshot_id = _new_id("AIE", audit_id, version, fingerprint)
        sealed_at = _now()
        with connection:
            connection.execute(
                """INSERT INTO ai_evidence_versions(
                    evidence_snapshot_id,audit_id,version_number,fingerprint,evidence_ids_json,
                    collection_states_json,context_json,supersedes_snapshot_id,contract_version,sealed_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (
                    snapshot_id,
                    audit_id,
                    version,
                    fingerprint,
                    _canonical(durable_ids),
                    _canonical(durable_states),
                    _canonical(normalized_context),
                    supersedes,
                    CONTRACT_VERSION,
                    sealed_at,
                ),
            )
            if latest is not None and str(latest["fingerprint"]) != fingerprint:
                connection.execute(
                    """UPDATE ai_tasks SET status=?,stale_reason=?,updated_at=?
                       WHERE audit_id=? AND evidence_snapshot_id=? AND status IN (?,?,?)""",
                    (
                        TASK_STALE,
                        f"SUPERSEDED_BY:{snapshot_id}",
                        sealed_at,
                        audit_id,
                        str(latest["evidence_snapshot_id"]),
                        TASK_COMPLETE,
                        TASK_PARTIAL,
                        TASK_READY,
                    ),
                )
        return EvidenceSnapshot(
            snapshot_id,
            audit_id,
            version,
            fingerprint,
            durable_ids,
            durable_states,
            normalized_context,
            sealed_at,
        )
    finally:
        connection.close()


def _snapshot_from_row(row: sqlite3.Row) -> EvidenceSnapshot:
    return EvidenceSnapshot(
        evidence_snapshot_id=str(row["evidence_snapshot_id"]),
        audit_id=str(row["audit_id"]),
        version_number=int(row["version_number"]),
        fingerprint=str(row["fingerprint"]),
        evidence_ids=tuple(json.loads(str(row["evidence_ids_json"]))),
        collection_states=dict(json.loads(str(row["collection_states_json"]))),
        context=dict(json.loads(str(row["context_json"]))),
        sealed_at=str(row["sealed_at"]),
    )


def latest_evidence_snapshot(workspace: Any, audit_id: str) -> EvidenceSnapshot | None:
    ensure_schema(workspace)
    connection = _connect(workspace)
    try:
        row = connection.execute(
            """SELECT * FROM ai_evidence_versions WHERE audit_id=?
               ORDER BY version_number DESC LIMIT 1""",
            (audit_id,),
        ).fetchone()
        return _snapshot_from_row(row) if row is not None else None
    finally:
        connection.close()


def register_task(
    *,
    workspace: Any,
    audit_id: str,
    purpose: str,
    scope_type: str,
    scope_key: str,
    evidence_snapshot_id: str,
    requirements: Iterable[str],
    semantic_contract_version: str | None = None,
    prompt_id: str | None = None,
    prompt_version: str | None = None,
    status: str = TASK_READY,
) -> str:
    ensure_schema(workspace)
    requirement_values = tuple(
        dict.fromkeys(str(item) for item in requirements if str(item).strip())
    )
    task_id = _new_id(
        "AIT",
        audit_id,
        purpose,
        scope_type,
        scope_key,
        evidence_snapshot_id,
    )
    now = _now()
    connection = _connect(workspace)
    try:
        with connection:
            connection.execute(
                """INSERT INTO ai_tasks(
                    ai_task_id,audit_id,purpose,scope_type,scope_key,evidence_snapshot_id,
                    semantic_contract_version,prompt_id,prompt_version,requirements_json,
                    accepted_json,rejected_json,missing_json,status,stale_reason,created_at,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(ai_task_id) DO UPDATE SET
                    requirements_json=excluded.requirements_json,
                    semantic_contract_version=COALESCE(excluded.semantic_contract_version,ai_tasks.semantic_contract_version),
                    prompt_id=COALESCE(excluded.prompt_id,ai_tasks.prompt_id),
                    prompt_version=COALESCE(excluded.prompt_version,ai_tasks.prompt_version),
                    status=CASE WHEN ai_tasks.status=? THEN ai_tasks.status ELSE excluded.status END,
                    updated_at=excluded.updated_at""",
                (
                    task_id,
                    audit_id,
                    purpose,
                    scope_type,
                    scope_key,
                    evidence_snapshot_id,
                    semantic_contract_version,
                    prompt_id,
                    prompt_version,
                    _canonical(requirement_values),
                    _canonical({}),
                    _canonical({}),
                    _canonical(requirement_values),
                    status,
                    None,
                    now,
                    now,
                    TASK_COMPLETE,
                ),
            )
    finally:
        connection.close()
    return task_id


def begin_round(
    *,
    workspace: Any,
    ai_task_id: str,
    requested_requirements: Iterable[str],
    input_payload: Any,
    input_summary: Mapping[str, Any] | None = None,
) -> str:
    ensure_schema(workspace)
    requested = tuple(dict.fromkeys(str(item) for item in requested_requirements if str(item).strip()))
    connection = _connect(workspace)
    try:
        row = connection.execute(
            "SELECT COALESCE(MAX(round_index),0)+1 FROM ai_request_rounds WHERE ai_task_id=?",
            (ai_task_id,),
        ).fetchone()
        index = int(row[0]) if row is not None else 1
        round_id = _new_id("AIR", ai_task_id, index, _hash(input_payload))
        now = _now()
        with connection:
            connection.execute(
                """INSERT INTO ai_request_rounds(
                    ai_round_id,ai_task_id,round_index,requested_requirements_json,input_hash,
                    input_summary_json,output_hash,accepted_json,rejected_json,missing_json,
                    status,started_at,finished_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    round_id,
                    ai_task_id,
                    index,
                    _canonical(requested),
                    _hash(input_payload),
                    _canonical(dict(input_summary or {})),
                    None,
                    _canonical({}),
                    _canonical({}),
                    _canonical(requested),
                    ROUND_RUNNING,
                    now,
                    None,
                ),
            )
            connection.execute(
                "UPDATE ai_tasks SET status=?,updated_at=? WHERE ai_task_id=?",
                (TASK_RUNNING, now, ai_task_id),
            )
        return round_id
    finally:
        connection.close()


def complete_round(
    *,
    workspace: Any,
    ai_round_id: str,
    accepted: Mapping[str, Any] | None = None,
    rejected: Mapping[str, Any] | None = None,
    missing: Iterable[str] = (),
    output_payload: Any = None,
    failed: bool = False,
) -> None:
    """Merge one round without replacing previously accepted requirements."""

    ensure_schema(workspace)
    accepted_values = {str(key): value for key, value in (accepted or {}).items()}
    rejected_values = {str(key): value for key, value in (rejected or {}).items()}
    missing_values = tuple(dict.fromkeys(str(item) for item in missing if str(item).strip()))
    connection = _connect(workspace)
    try:
        row = connection.execute(
            """SELECT r.*,t.requirements_json,t.accepted_json,t.rejected_json
               FROM ai_request_rounds r JOIN ai_tasks t ON t.ai_task_id=r.ai_task_id
               WHERE r.ai_round_id=?""",
            (ai_round_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"AI round not found: {ai_round_id}")
        requirements = tuple(json.loads(str(row["requirements_json"])))
        task_accepted = dict(json.loads(str(row["accepted_json"])))
        task_rejected = dict(json.loads(str(row["rejected_json"])))
        # Accepted values are immutable for a given evidence snapshot.  A continuation
        # cannot rewrite a result that was already validated in a prior round.
        for key, value in accepted_values.items():
            task_accepted.setdefault(key, value)
            task_rejected.pop(key, None)
        for key, value in rejected_values.items():
            if key not in task_accepted:
                task_rejected[key] = value
        unresolved = tuple(
            item for item in requirements if item not in task_accepted
        )
        # Explicit missing is advisory; the canonical unresolved set is derived from
        # requirements minus accepted so an unsolicited model field cannot mark work done.
        if missing_values:
            unresolved = tuple(
                dict.fromkeys((*unresolved, *(item for item in missing_values if item not in task_accepted)))
            )
        if failed and not task_accepted:
            round_status = ROUND_FAILED
            task_status = TASK_FAILED
        elif unresolved:
            round_status = ROUND_PARTIAL if accepted_values else (ROUND_FAILED if failed else ROUND_PARTIAL)
            task_status = TASK_PARTIAL
        else:
            round_status = ROUND_COMPLETE
            task_status = TASK_COMPLETE
        now = _now()
        with connection:
            connection.execute(
                """UPDATE ai_request_rounds SET output_hash=?,accepted_json=?,rejected_json=?,
                   missing_json=?,status=?,finished_at=? WHERE ai_round_id=?""",
                (
                    _hash(output_payload) if output_payload is not None else None,
                    _canonical(accepted_values),
                    _canonical(rejected_values),
                    _canonical(missing_values),
                    round_status,
                    now,
                    ai_round_id,
                ),
            )
            connection.execute(
                """UPDATE ai_tasks SET accepted_json=?,rejected_json=?,missing_json=?,status=?,updated_at=?
                   WHERE ai_task_id=?""",
                (
                    _canonical(task_accepted),
                    _canonical(task_rejected),
                    _canonical(unresolved),
                    task_status,
                    now,
                    str(row["ai_task_id"]),
                ),
            )
    finally:
        connection.close()


def task_missing_requirements(workspace: Any, ai_task_id: str) -> tuple[str, ...]:
    ensure_schema(workspace)
    connection = _connect(workspace)
    try:
        row = connection.execute(
            "SELECT missing_json FROM ai_tasks WHERE ai_task_id=?",
            (ai_task_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"AI task not found: {ai_task_id}")
        return tuple(json.loads(str(row[0])))
    finally:
        connection.close()


def mark_task_blocked(workspace: Any, ai_task_id: str, reason: str) -> None:
    ensure_schema(workspace)
    connection = _connect(workspace)
    try:
        with connection:
            connection.execute(
                "UPDATE ai_tasks SET status=?,stale_reason=?,updated_at=? WHERE ai_task_id=?",
                (TASK_BLOCKED, str(reason)[:1000], _now(), ai_task_id),
            )
    finally:
        connection.close()


__all__ = [
    "CONTRACT_VERSION",
    "EvidenceSnapshot",
    "TERMINAL_COLLECTION_STATES",
    "NON_TERMINAL_COLLECTION_STATES",
    "TASK_PENDING",
    "TASK_READY",
    "TASK_RUNNING",
    "TASK_PARTIAL",
    "TASK_COMPLETE",
    "TASK_BLOCKED",
    "TASK_FAILED",
    "TASK_SKIPPED",
    "TASK_STALE",
    "collection_state_is_terminal",
    "dependency_gate",
    "ensure_schema",
    "seal_evidence",
    "latest_evidence_snapshot",
    "register_task",
    "begin_round",
    "complete_round",
    "task_missing_requirements",
    "mark_task_blocked",
]
