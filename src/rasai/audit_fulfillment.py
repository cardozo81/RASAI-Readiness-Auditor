"""Durable fulfillment contract for one logical RASAi AUD.

One AUD is one analytical observation even when recovery requires multiple RPR runs.
The module persists the non-secret execution contract, required work-items,
append-only attempts and the effective state used to decide score/report finality and
consolidation eligibility.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import html
import json
import os
from pathlib import Path
import re
import sqlite3
from typing import Any, Iterable, Iterator, Mapping

from rasai.domain import new_id
from rasai.persistence import AuditWorkspace

CONTRACT_VERSION = "AUDIT-FULFILLMENT-001"

PENDING = "PENDING"
RUNNING = "RUNNING"
WAITING_FOR_DATA = "WAITING_FOR_DATA"
SUCCESS = "SUCCESS"
FAILED_RETRYABLE = "FAILED_RETRYABLE"
FAILED_PERMANENT = "FAILED_PERMANENT"
BLOCKED = "BLOCKED"
NOT_APPLICABLE = "NOT_APPLICABLE"
DISABLED = "DISABLED"

REPLAY_SAFE = "REPLAY_SAFE"
LIVE_RECOLLECTION = "LIVE_RECOLLECTION"

PROCESSING = "PROCESSING"
PARTIAL_RETRYABLE = "PARTIAL_RETRYABLE"
PARTIAL_BLOCKED = "PARTIAL_BLOCKED"
COMPLETE = "COMPLETE"
FAILED_FATAL = "FAILED_FATAL"
EXPIRED_FOR_COMPLETION = "EXPIRED_FOR_COMPLETION"

SCORE_PENDING = "PENDING"
SCORE_FINAL = "FINAL"
SCORE_UNAVAILABLE = "UNAVAILABLE"
REPORT_PRELIMINARY = "PRELIMINARY"
REPORT_FINAL = "FINAL"
REPORT_INCOMPLETE = "INCOMPLETE"
TEMPORAL_VALID = "VALID"
TEMPORAL_EXPIRED = "EXPIRED"

_TERMINAL_NON_SUCCESS = {FAILED_PERMANENT, BLOCKED}
_EXCLUDED_REQUIRED = {DISABLED, NOT_APPLICABLE}
_REPORT_MARKER = "<!-- RASAI_AUDIT_FULFILLMENT_STATUS -->"
_LIVE_WINDOW_ENV = "RASAI_REPROCESS_LIVE_VALIDITY_MINUTES"
_DEFAULT_LIVE_WINDOW_MINUTES = 1440


@dataclass(frozen=True, slots=True)
class WorkItem:
    work_item_id: str
    audit_id: str
    component: str
    scope_key: str
    required: bool
    temporal_mode: str
    status: str
    attempt_count: int
    retryable: bool
    last_error_class: str | None
    last_error_code: str | None
    last_error_message: str | None
    effective_result_ref: str | None
    source_captured_at: str | None
    valid_until: str | None
    configuration: dict[str, Any]


@dataclass(frozen=True, slots=True)
class FulfillmentSummary:
    audit_id: str
    processing_status: str
    score_status: str
    report_status: str
    consolidation_eligible: bool
    temporal_status: str
    required_items: int
    successful_items: int
    pending_items: int
    blocked_items: int
    expired_items: int
    total_attempts: int
    reprocess_count: int
    last_reprocess_id: str | None
    completed_at: str | None

    @property
    def is_final(self) -> bool:
        return self.processing_status == COMPLETE and self.consolidation_eligible


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _load(raw: Any, default: Any) -> Any:
    if raw in (None, ""):
        return default
    if isinstance(raw, (dict, list, tuple)):
        return raw
    try:
        return json.loads(str(raw))
    except (TypeError, ValueError, json.JSONDecodeError):
        return default


def _safe_mapping(value: Mapping[str, Any] | None) -> dict[str, Any]:
    if not value:
        return {}
    forbidden = (
        "api_key",
        "apikey",
        "token",
        "secret",
        "password",
        "credential",
        "authorization",
    )
    output: dict[str, Any] = {}
    for key, item in value.items():
        name = str(key)
        if any(part in name.casefold() for part in forbidden):
            continue
        if isinstance(item, Mapping):
            output[name] = _safe_mapping(item)
        elif isinstance(item, (list, tuple)):
            output[name] = [
                _safe_mapping(entry) if isinstance(entry, Mapping) else entry
                for entry in item
            ]
        else:
            output[name] = item
    return output


def _database_path(workspace: AuditWorkspace | Path | str) -> Path:
    if isinstance(workspace, AuditWorkspace):
        return workspace.database
    path = Path(workspace)
    return path if path.name == "audit.db" else path / "audit.db"


@contextmanager
def _connect(
    workspace: AuditWorkspace | Path | str,
    *,
    read_only: bool = False,
) -> Iterator[sqlite3.Connection]:
    """Open a short-lived SQLite handle and always close it at context exit.

    Explicit closure is required for Windows, where an outstanding handle prevents
    workspace cleanup, report replacement and controlled audit.db revision handling.
    """
    database = _database_path(workspace)
    if read_only:
        connection = sqlite3.connect(
            f"file:{database.resolve().as_posix()}?mode=ro",
            uri=True,
            timeout=2.0,
        )
        connection.execute("PRAGMA query_only = ON")
    else:
        connection = sqlite3.connect(database, timeout=5.0)
        connection.execute("PRAGMA foreign_keys = ON")
    connection.row_factory = sqlite3.Row
    try:
        yield connection
    finally:
        connection.close()


def ensure_schema(workspace: AuditWorkspace | Path | str) -> None:
    with _connect(workspace) as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS audit_fulfillment_contracts (
                audit_id TEXT PRIMARY KEY REFERENCES audits(audit_id) ON DELETE CASCADE,
                contract_version TEXT NOT NULL,
                configuration TEXT NOT NULL,
                processing_status TEXT NOT NULL,
                score_status TEXT NOT NULL,
                report_status TEXT NOT NULL,
                consolidation_eligible INTEGER NOT NULL,
                temporal_status TEXT NOT NULL,
                required_items INTEGER NOT NULL,
                successful_items INTEGER NOT NULL,
                pending_items INTEGER NOT NULL,
                blocked_items INTEGER NOT NULL,
                expired_items INTEGER NOT NULL,
                total_attempts INTEGER NOT NULL,
                reprocess_count INTEGER NOT NULL,
                last_reprocess_id TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                completed_at TEXT
            );

            CREATE TABLE IF NOT EXISTS audit_fulfillment_work_items (
                work_item_id TEXT PRIMARY KEY,
                audit_id TEXT NOT NULL REFERENCES audits(audit_id) ON DELETE CASCADE,
                component TEXT NOT NULL,
                scope_key TEXT NOT NULL,
                required INTEGER NOT NULL,
                temporal_mode TEXT NOT NULL,
                status TEXT NOT NULL,
                attempt_count INTEGER NOT NULL DEFAULT 0,
                retryable INTEGER NOT NULL DEFAULT 1,
                last_attempt_at TEXT,
                last_success_at TEXT,
                last_error_class TEXT,
                last_error_code TEXT,
                last_error_message TEXT,
                effective_result_ref TEXT,
                source_captured_at TEXT,
                valid_until TEXT,
                configuration TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(audit_id, component, scope_key)
            );

            CREATE TABLE IF NOT EXISTS audit_reprocess_runs (
                reprocess_id TEXT PRIMARY KEY,
                audit_id TEXT NOT NULL REFERENCES audits(audit_id) ON DELETE CASCADE,
                contract_version TEXT NOT NULL,
                status TEXT NOT NULL,
                attempted_items INTEGER NOT NULL DEFAULT 0,
                successful_items INTEGER NOT NULL DEFAULT 0,
                remaining_items INTEGER NOT NULL DEFAULT 0,
                source TEXT NOT NULL,
                started_at TEXT NOT NULL,
                completed_at TEXT,
                note TEXT
            );

            CREATE TABLE IF NOT EXISTS audit_fulfillment_attempts (
                attempt_id TEXT PRIMARY KEY,
                audit_id TEXT NOT NULL REFERENCES audits(audit_id) ON DELETE CASCADE,
                work_item_id TEXT NOT NULL REFERENCES audit_fulfillment_work_items(work_item_id) ON DELETE CASCADE,
                reprocess_id TEXT REFERENCES audit_reprocess_runs(reprocess_id) ON DELETE SET NULL,
                attempt_number INTEGER NOT NULL,
                status TEXT NOT NULL,
                started_at TEXT NOT NULL,
                finished_at TEXT,
                error_class TEXT,
                error_code TEXT,
                error_message TEXT,
                result_ref TEXT,
                metadata TEXT NOT NULL DEFAULT '{}'
            );

            CREATE TABLE IF NOT EXISTS audit_reprocess_derived_archive (
                archive_id TEXT PRIMARY KEY,
                audit_id TEXT NOT NULL REFERENCES audits(audit_id) ON DELETE CASCADE,
                reprocess_id TEXT NOT NULL REFERENCES audit_reprocess_runs(reprocess_id) ON DELETE CASCADE,
                component TEXT NOT NULL,
                entity_type TEXT NOT NULL,
                entity_id TEXT NOT NULL,
                payload TEXT NOT NULL,
                archived_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_fulfillment_work_audit
                ON audit_fulfillment_work_items(audit_id,required,status,component);
            CREATE INDEX IF NOT EXISTS idx_fulfillment_attempt_audit
                ON audit_fulfillment_attempts(audit_id,work_item_id,attempt_number);
            CREATE INDEX IF NOT EXISTS idx_reprocess_audit
                ON audit_reprocess_runs(audit_id,started_at);
            """
        )
        connection.commit()


def initialize_contract(
    workspace: AuditWorkspace | Path | str,
    audit_id: str,
    configuration: Mapping[str, Any] | None = None,
) -> None:
    ensure_schema(workspace)
    now = _utc_now()
    safe = _safe_mapping(configuration)
    with _connect(workspace) as connection:
        row = connection.execute(
            "SELECT configuration FROM audit_fulfillment_contracts WHERE audit_id=?",
            (audit_id,),
        ).fetchone()
        if row is None:
            connection.execute(
                """INSERT INTO audit_fulfillment_contracts(
                    audit_id,contract_version,configuration,processing_status,score_status,
                    report_status,consolidation_eligible,temporal_status,required_items,
                    successful_items,pending_items,blocked_items,expired_items,total_attempts,
                    reprocess_count,last_reprocess_id,created_at,updated_at,completed_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    audit_id,
                    CONTRACT_VERSION,
                    _dump(safe),
                    PROCESSING,
                    SCORE_PENDING,
                    REPORT_PRELIMINARY,
                    0,
                    TEMPORAL_VALID,
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                    None,
                    now,
                    now,
                    None,
                ),
            )
        elif safe:
            current = _load(row["configuration"], {})
            if not isinstance(current, dict):
                current = {}
            current.update(safe)
            connection.execute(
                "UPDATE audit_fulfillment_contracts SET configuration=?,updated_at=? WHERE audit_id=?",
                (_dump(current), now, audit_id),
            )
        connection.commit()
    recalculate(workspace, audit_id)


def merge_contract_configuration(
    workspace: AuditWorkspace | Path | str,
    audit_id: str,
    **values: Any,
) -> None:
    initialize_contract(workspace, audit_id, values)


def live_valid_until(started_at: str | None = None) -> str:
    raw = (os.getenv(_LIVE_WINDOW_ENV) or "").strip()
    try:
        minutes = int(raw) if raw else _DEFAULT_LIVE_WINDOW_MINUTES
    except ValueError:
        minutes = _DEFAULT_LIVE_WINDOW_MINUTES
    minutes = max(1, min(minutes, 10080))
    base = _parse_time(started_at) or datetime.now(timezone.utc)
    return (base + timedelta(minutes=minutes)).isoformat()


def register_work_item(
    workspace: AuditWorkspace | Path | str,
    *,
    audit_id: str,
    component: str,
    scope_key: str = "AUDIT",
    required: bool = True,
    temporal_mode: str = REPLAY_SAFE,
    status: str = PENDING,
    retryable: bool = True,
    configuration: Mapping[str, Any] | None = None,
    source_captured_at: str | None = None,
    valid_until: str | None = None,
) -> str:
    initialize_contract(workspace, audit_id)
    component = component.strip().upper()
    scope_key = scope_key.strip() or "AUDIT"
    if temporal_mode not in {REPLAY_SAFE, LIVE_RECOLLECTION}:
        raise ValueError(f"invalid temporal_mode: {temporal_mode}")
    if temporal_mode == LIVE_RECOLLECTION and valid_until is None:
        valid_until = live_valid_until(source_captured_at)
    now = _utc_now()
    safe_config = _safe_mapping(configuration)
    with _connect(workspace) as connection:
        existing = connection.execute(
            """SELECT * FROM audit_fulfillment_work_items
               WHERE audit_id=? AND component=? AND scope_key=?""",
            (audit_id, component, scope_key),
        ).fetchone()
        if existing is None:
            work_item_id = new_id("WKI")
            connection.execute(
                """INSERT INTO audit_fulfillment_work_items(
                    work_item_id,audit_id,component,scope_key,required,temporal_mode,status,
                    attempt_count,retryable,last_attempt_at,last_success_at,last_error_class,
                    last_error_code,last_error_message,effective_result_ref,source_captured_at,
                    valid_until,configuration,created_at,updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    work_item_id,
                    audit_id,
                    component,
                    scope_key,
                    int(required),
                    temporal_mode,
                    status,
                    0,
                    int(retryable),
                    None,
                    now if status == SUCCESS else None,
                    None,
                    None,
                    None,
                    None,
                    source_captured_at,
                    valid_until,
                    _dump(safe_config),
                    now,
                    now,
                ),
            )
        else:
            work_item_id = str(existing["work_item_id"])
            old_config = _load(existing["configuration"], {})
            if not isinstance(old_config, dict):
                old_config = {}
            old_config.update(safe_config)
            effective_status = str(existing["status"])
            if effective_status != SUCCESS and status in {DISABLED, NOT_APPLICABLE}:
                effective_status = status
            connection.execute(
                """UPDATE audit_fulfillment_work_items SET
                    required=?,temporal_mode=?,status=?,retryable=?,
                    source_captured_at=COALESCE(source_captured_at,?),
                    valid_until=COALESCE(valid_until,?),configuration=?,updated_at=?
                   WHERE work_item_id=?""",
                (
                    int(required),
                    temporal_mode,
                    effective_status,
                    int(retryable),
                    source_captured_at,
                    valid_until,
                    _dump(old_config),
                    now,
                    work_item_id,
                ),
            )
        connection.commit()
    recalculate(workspace, audit_id)
    return work_item_id


def _work_item_row(
    connection: sqlite3.Connection,
    audit_id: str,
    component: str,
    scope_key: str,
) -> sqlite3.Row:
    row = connection.execute(
        "SELECT * FROM audit_fulfillment_work_items WHERE audit_id=? AND component=? AND scope_key=?",
        (audit_id, component.upper(), scope_key),
    ).fetchone()
    if row is None:
        raise KeyError(f"fulfillment work-item not found: {audit_id}/{component}/{scope_key}")
    return row


def begin_attempt(
    workspace: AuditWorkspace | Path | str,
    *,
    audit_id: str,
    component: str,
    scope_key: str = "AUDIT",
    reprocess_id: str | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> str:
    ensure_schema(workspace)
    now = _utc_now()
    with _connect(workspace) as connection:
        row = _work_item_row(connection, audit_id, component, scope_key)
        if str(row["status"]) == SUCCESS:
            raise ValueError("successful fulfillment work-items must not be attempted again")
        number = int(row["attempt_count"]) + 1
        attempt_id = new_id("WKA")
        connection.execute(
            """INSERT INTO audit_fulfillment_attempts(
                attempt_id,audit_id,work_item_id,reprocess_id,attempt_number,status,
                started_at,finished_at,error_class,error_code,error_message,result_ref,metadata
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                attempt_id,
                audit_id,
                row["work_item_id"],
                reprocess_id,
                number,
                RUNNING,
                now,
                None,
                None,
                None,
                None,
                None,
                _dump(_safe_mapping(metadata)),
            ),
        )
        connection.execute(
            """UPDATE audit_fulfillment_work_items
               SET status=?,attempt_count=?,last_attempt_at=?,updated_at=?
               WHERE work_item_id=?""",
            (RUNNING, number, now, now, row["work_item_id"]),
        )
        connection.commit()
    recalculate(workspace, audit_id)
    return attempt_id


def finish_attempt(
    workspace: AuditWorkspace | Path | str,
    attempt_id: str,
    *,
    status: str,
    result_ref: str | None = None,
    error_class: str | None = None,
    error_code: str | None = None,
    error_message: str | None = None,
    retryable: bool | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> None:
    ensure_schema(workspace)
    now = _utc_now()
    with _connect(workspace) as connection:
        attempt = connection.execute(
            "SELECT * FROM audit_fulfillment_attempts WHERE attempt_id=?",
            (attempt_id,),
        ).fetchone()
        if attempt is None:
            raise KeyError(f"fulfillment attempt not found: {attempt_id}")
        row = connection.execute(
            "SELECT * FROM audit_fulfillment_work_items WHERE work_item_id=?",
            (attempt["work_item_id"],),
        ).fetchone()
        if row is None:
            raise KeyError(f"fulfillment work-item disappeared: {attempt['work_item_id']}")
        if str(row["status"]) == SUCCESS and status != SUCCESS:
            return
        current_metadata = _load(attempt["metadata"], {})
        if not isinstance(current_metadata, dict):
            current_metadata = {}
        current_metadata.update(_safe_mapping(metadata))
        connection.execute(
            """UPDATE audit_fulfillment_attempts SET
               status=?,finished_at=?,error_class=?,error_code=?,error_message=?,result_ref=?,metadata=?
               WHERE attempt_id=?""",
            (
                status,
                now,
                error_class,
                error_code,
                (error_message or "")[:1000] or None,
                result_ref,
                _dump(current_metadata),
                attempt_id,
            ),
        )
        is_success = status == SUCCESS
        effective_retryable = int(row["retryable"] if retryable is None else bool(retryable))
        connection.execute(
            """UPDATE audit_fulfillment_work_items SET
               status=?,retryable=?,last_attempt_at=?,last_success_at=?,last_error_class=?,
               last_error_code=?,last_error_message=?,effective_result_ref=?,updated_at=?
               WHERE work_item_id=?""",
            (
                status,
                effective_retryable,
                now,
                now if is_success else row["last_success_at"],
                None if is_success else error_class,
                None if is_success else error_code,
                None if is_success else ((error_message or "")[:1000] or None),
                result_ref if is_success else row["effective_result_ref"],
                now,
                row["work_item_id"],
            ),
        )
        audit_id = str(attempt["audit_id"])
        connection.commit()
    recalculate(workspace, audit_id)


def set_work_item_status(
    workspace: AuditWorkspace | Path | str,
    *,
    audit_id: str,
    component: str,
    scope_key: str = "AUDIT",
    status: str,
    result_ref: str | None = None,
    error_class: str | None = None,
    error_code: str | None = None,
    error_message: str | None = None,
    retryable: bool | None = None,
) -> None:
    ensure_schema(workspace)
    now = _utc_now()
    with _connect(workspace) as connection:
        row = _work_item_row(connection, audit_id, component, scope_key)
        if str(row["status"]) == SUCCESS and status != SUCCESS:
            return
        connection.execute(
            """UPDATE audit_fulfillment_work_items SET
               status=?,retryable=?,last_success_at=?,last_error_class=?,last_error_code=?,
               last_error_message=?,effective_result_ref=?,updated_at=? WHERE work_item_id=?""",
            (
                status,
                int(row["retryable"] if retryable is None else bool(retryable)),
                now if status == SUCCESS else row["last_success_at"],
                None if status == SUCCESS else error_class,
                None if status == SUCCESS else error_code,
                None if status == SUCCESS else ((error_message or "")[:1000] or None),
                result_ref if status == SUCCESS else row["effective_result_ref"],
                now,
                row["work_item_id"],
            ),
        )
        connection.commit()
    recalculate(workspace, audit_id)


def list_work_items(
    workspace: AuditWorkspace | Path | str,
    audit_id: str,
    *,
    pending_only: bool = False,
) -> tuple[WorkItem, ...]:
    ensure_schema(workspace)
    with _connect(workspace, read_only=True) as connection:
        sql = "SELECT * FROM audit_fulfillment_work_items WHERE audit_id=?"
        params: list[Any] = [audit_id]
        if pending_only:
            sql += " AND required=1 AND status NOT IN ('SUCCESS','DISABLED','NOT_APPLICABLE')"
        sql += " ORDER BY component,scope_key"
        rows = connection.execute(sql, params).fetchall()
    return tuple(
        WorkItem(
            work_item_id=str(row["work_item_id"]),
            audit_id=str(row["audit_id"]),
            component=str(row["component"]),
            scope_key=str(row["scope_key"]),
            required=bool(row["required"]),
            temporal_mode=str(row["temporal_mode"]),
            status=str(row["status"]),
            attempt_count=int(row["attempt_count"]),
            retryable=bool(row["retryable"]),
            last_error_class=row["last_error_class"],
            last_error_code=row["last_error_code"],
            last_error_message=row["last_error_message"],
            effective_result_ref=row["effective_result_ref"],
            source_captured_at=row["source_captured_at"],
            valid_until=row["valid_until"],
            configuration=dict(_load(row["configuration"], {}) or {}),
        )
        for row in rows
    )


def _expired(row: sqlite3.Row, now: datetime) -> bool:
    if str(row["temporal_mode"]) != LIVE_RECOLLECTION or str(row["status"]) == SUCCESS:
        return False
    deadline = _parse_time(row["valid_until"])
    return bool(deadline and now > deadline)


def _summary_from_row(row: sqlite3.Row) -> FulfillmentSummary:
    return FulfillmentSummary(
        audit_id=str(row["audit_id"]),
        processing_status=str(row["processing_status"]),
        score_status=str(row["score_status"]),
        report_status=str(row["report_status"]),
        consolidation_eligible=bool(row["consolidation_eligible"]),
        temporal_status=str(row["temporal_status"]),
        required_items=int(row["required_items"]),
        successful_items=int(row["successful_items"]),
        pending_items=int(row["pending_items"]),
        blocked_items=int(row["blocked_items"]),
        expired_items=int(row["expired_items"]),
        total_attempts=int(row["total_attempts"]),
        reprocess_count=int(row["reprocess_count"]),
        last_reprocess_id=row["last_reprocess_id"],
        completed_at=row["completed_at"],
    )


def recalculate(
    workspace: AuditWorkspace | Path | str,
    audit_id: str,
) -> FulfillmentSummary:
    ensure_schema(workspace)
    now_text = _utc_now()
    now = _parse_time(now_text) or datetime.now(timezone.utc)
    with _connect(workspace) as connection:
        contract = connection.execute(
            "SELECT * FROM audit_fulfillment_contracts WHERE audit_id=?",
            (audit_id,),
        ).fetchone()
        if contract is None:
            connection.execute(
                """INSERT INTO audit_fulfillment_contracts(
                    audit_id,contract_version,configuration,processing_status,score_status,
                    report_status,consolidation_eligible,temporal_status,required_items,
                    successful_items,pending_items,blocked_items,expired_items,total_attempts,
                    reprocess_count,last_reprocess_id,created_at,updated_at,completed_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    audit_id,
                    CONTRACT_VERSION,
                    "{}",
                    PROCESSING,
                    SCORE_PENDING,
                    REPORT_PRELIMINARY,
                    0,
                    TEMPORAL_VALID,
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                    None,
                    now_text,
                    now_text,
                    None,
                ),
            )
            contract = connection.execute(
                "SELECT * FROM audit_fulfillment_contracts WHERE audit_id=?",
                (audit_id,),
            ).fetchone()
        rows = connection.execute(
            "SELECT * FROM audit_fulfillment_work_items WHERE audit_id=? AND required=1",
            (audit_id,),
        ).fetchall()
        relevant = [row for row in rows if str(row["status"]) not in _EXCLUDED_REQUIRED]
        expired = [row for row in relevant if _expired(row, now)]
        successful = [row for row in relevant if str(row["status"]) == SUCCESS]
        blocked = [
            row
            for row in relevant
            if str(row["status"]) != SUCCESS
            and (
                str(row["status"]) in _TERMINAL_NON_SUCCESS
                or not bool(row["retryable"])
            )
        ]
        blocked_ids = {str(row["work_item_id"]) for row in blocked}
        pending = [
            row
            for row in relevant
            if str(row["status"]) != SUCCESS
            and str(row["work_item_id"]) not in blocked_ids
        ]

        if expired:
            processing_status = EXPIRED_FOR_COMPLETION
            score_status = SCORE_UNAVAILABLE
            report_status = REPORT_PRELIMINARY
            temporal_status = TEMPORAL_EXPIRED
            eligible = False
        elif relevant and len(successful) == len(relevant):
            processing_status = COMPLETE
            score_status = SCORE_FINAL
            report_status = REPORT_FINAL
            temporal_status = TEMPORAL_VALID
            eligible = True
        elif blocked:
            processing_status = PARTIAL_BLOCKED
            score_status = SCORE_UNAVAILABLE
            report_status = REPORT_PRELIMINARY
            temporal_status = TEMPORAL_VALID
            eligible = False
        elif relevant:
            processing_status = PARTIAL_RETRYABLE
            score_status = SCORE_PENDING
            report_status = REPORT_PRELIMINARY
            temporal_status = TEMPORAL_VALID
            eligible = False
        else:
            processing_status = PROCESSING
            score_status = SCORE_PENDING
            report_status = REPORT_PRELIMINARY
            temporal_status = TEMPORAL_VALID
            eligible = False

        total_attempts = int(
            connection.execute(
                "SELECT count(*) FROM audit_fulfillment_attempts WHERE audit_id=?",
                (audit_id,),
            ).fetchone()[0]
        )
        reprocess_count = int(
            connection.execute(
                "SELECT count(*) FROM audit_reprocess_runs WHERE audit_id=?",
                (audit_id,),
            ).fetchone()[0]
        )
        completed_at = contract["completed_at"]
        if eligible and not completed_at:
            completed_at = now_text
        if not eligible:
            completed_at = None
        connection.execute(
            """UPDATE audit_fulfillment_contracts SET
               processing_status=?,score_status=?,report_status=?,consolidation_eligible=?,
               temporal_status=?,required_items=?,successful_items=?,pending_items=?,
               blocked_items=?,expired_items=?,total_attempts=?,reprocess_count=?,updated_at=?,
               completed_at=? WHERE audit_id=?""",
            (
                processing_status,
                score_status,
                report_status,
                int(eligible),
                temporal_status,
                len(relevant),
                len(successful),
                len(pending),
                len(blocked),
                len(expired),
                total_attempts,
                reprocess_count,
                now_text,
                completed_at,
                audit_id,
            ),
        )
        connection.commit()
        last = connection.execute(
            "SELECT * FROM audit_fulfillment_contracts WHERE audit_id=?",
            (audit_id,),
        ).fetchone()
        if last is None:
            raise RuntimeError(f"fulfillment summary disappeared for {audit_id}")
        summary = _summary_from_row(last)
    return summary


def read_summary(
    workspace: AuditWorkspace | Path | str,
    audit_id: str | None = None,
) -> FulfillmentSummary | None:
    database_path = _database_path(workspace)
    if not database_path.is_file():
        return None
    try:
        with _connect(database_path, read_only=True) as connection:
            exists = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='audit_fulfillment_contracts'"
            ).fetchone()
            if not exists:
                return None
            if audit_id is None:
                row = connection.execute(
                    "SELECT * FROM audit_fulfillment_contracts ORDER BY created_at DESC LIMIT 1"
                ).fetchone()
            else:
                row = connection.execute(
                    "SELECT * FROM audit_fulfillment_contracts WHERE audit_id=?",
                    (audit_id,),
                ).fetchone()
            if row is None:
                return None
            return _summary_from_row(row)
    except sqlite3.Error:
        return None


def start_reprocess_run(
    workspace: AuditWorkspace | Path | str,
    audit_id: str,
    *,
    source: str = "CLI",
    note: str | None = None,
) -> str:
    initialize_contract(workspace, audit_id)
    reprocess_id = new_id("RPR")
    now = _utc_now()
    with _connect(workspace) as connection:
        connection.execute(
            """INSERT INTO audit_reprocess_runs(
                reprocess_id,audit_id,contract_version,status,attempted_items,successful_items,
                remaining_items,source,started_at,completed_at,note
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (
                reprocess_id,
                audit_id,
                CONTRACT_VERSION,
                RUNNING,
                0,
                0,
                0,
                source,
                now,
                None,
                (note or "")[:1000] or None,
            ),
        )
        connection.execute(
            "UPDATE audit_fulfillment_contracts SET last_reprocess_id=?,updated_at=? WHERE audit_id=?",
            (reprocess_id, now, audit_id),
        )
        connection.commit()
    recalculate(workspace, audit_id)
    return reprocess_id


def finish_reprocess_run(
    workspace: AuditWorkspace | Path | str,
    reprocess_id: str,
    *,
    status: str,
    attempted_items: int,
    successful_items: int,
    note: str | None = None,
) -> FulfillmentSummary:
    ensure_schema(workspace)
    now = _utc_now()
    with _connect(workspace) as connection:
        row = connection.execute(
            "SELECT audit_id FROM audit_reprocess_runs WHERE reprocess_id=?",
            (reprocess_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"reprocess run not found: {reprocess_id}")
        audit_id = str(row["audit_id"])
        remaining = int(
            connection.execute(
                """SELECT count(*) FROM audit_fulfillment_work_items
                   WHERE audit_id=? AND required=1
                   AND status NOT IN ('SUCCESS','DISABLED','NOT_APPLICABLE')""",
                (audit_id,),
            ).fetchone()[0]
        )
        connection.execute(
            """UPDATE audit_reprocess_runs SET
               status=?,attempted_items=?,successful_items=?,remaining_items=?,completed_at=?,
               note=COALESCE(?,note) WHERE reprocess_id=?""",
            (
                status,
                attempted_items,
                successful_items,
                remaining,
                now,
                (note or "")[:1000] or None,
                reprocess_id,
            ),
        )
        connection.commit()
    return recalculate(workspace, audit_id)


def archive_rows(
    workspace: AuditWorkspace | Path | str,
    *,
    audit_id: str,
    reprocess_id: str,
    component: str,
    entity_type: str,
    id_field: str,
    rows: Iterable[Mapping[str, Any]],
) -> int:
    ensure_schema(workspace)
    now = _utc_now()
    count = 0
    with _connect(workspace) as connection:
        for item in rows:
            entity_id = str(item.get(id_field) or "")
            if not entity_id:
                continue
            connection.execute(
                """INSERT INTO audit_reprocess_derived_archive(
                    archive_id,audit_id,reprocess_id,component,entity_type,entity_id,payload,archived_at
                ) VALUES (?,?,?,?,?,?,?,?)""",
                (
                    new_id("ARC"),
                    audit_id,
                    reprocess_id,
                    component,
                    entity_type,
                    entity_id,
                    _dump(dict(item)),
                    now,
                ),
            )
            count += 1
        connection.commit()
    return count


def _banner(summary: FulfillmentSummary) -> str:
    if summary.is_final:
        title = "Processamento concluído — relatório final"
        text = (
            f"Todos os {summary.required_items} requisito(s) aplicáveis da configuração original foram "
            "atendidos. O score é final e este AUD está elegível para consolidação."
        )
        cls = "rasai-fulfillment-final"
    else:
        title = "Relatório preliminar — score final ainda não definido"
        text = (
            f"{summary.successful_items}/{summary.required_items} requisito(s) obrigatório(s) atendidos. "
            "Enquanto houver pendências, bloqueios ou validade temporal não satisfeita, este AUD não "
            "participa de score consolidado, tendências ou relatórios consolidados. Valores de componentes "
            "eventualmente exibidos são diagnósticos/parciais e não constituem score final."
        )
        cls = "rasai-fulfillment-preliminary"
    detail = (
        f"Status: {summary.processing_status} · score: {summary.score_status} · "
        f"consolidação: {'elegível' if summary.consolidation_eligible else 'não elegível'} · "
        f"reprocessamentos: {summary.reprocess_count}"
    )
    return (
        _REPORT_MARKER
        + f'<section class="rasai-fulfillment-banner {cls}" role="status" '
        'style="border:1px solid currentColor;border-radius:10px;padding:14px 16px;margin:12px 0;">'
        + f"<strong>{html.escape(title)}</strong><p>{html.escape(text)}</p>"
        + f"<small>{html.escape(detail)}</small></section>"
    )


def project_report_validity(
    *,
    audit_id: str,
    workspace: AuditWorkspace,
) -> FulfillmentSummary:
    summary = recalculate(workspace, audit_id)
    report_dir = workspace.root / "report"
    report_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "audit_id": summary.audit_id,
        "contract_version": CONTRACT_VERSION,
        "processing_status": summary.processing_status,
        "score_status": summary.score_status,
        "report_status": summary.report_status,
        "consolidation_eligible": summary.consolidation_eligible,
        "temporal_status": summary.temporal_status,
        "required_items": summary.required_items,
        "successful_items": summary.successful_items,
        "pending_items": summary.pending_items,
        "blocked_items": summary.blocked_items,
        "expired_items": summary.expired_items,
        "total_attempts": summary.total_attempts,
        "reprocess_count": summary.reprocess_count,
        "last_reprocess_id": summary.last_reprocess_id,
        "completed_at": summary.completed_at,
    }
    (report_dir / "processing-status.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
        newline="\n",
    )
    banner = _banner(summary)
    for path in report_dir.glob("*.html"):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
        if _REPORT_MARKER in text:
            text = re.sub(
                re.escape(_REPORT_MARKER)
                + r'<section class="rasai-fulfillment-banner.*?</section>',
                banner,
                text,
                count=1,
                flags=re.DOTALL,
            )
        else:
            body = re.search(r"<body(?:\s[^>]*)?>", text, flags=re.IGNORECASE)
            if body:
                text = text[: body.end()] + banner + text[body.end() :]
            else:
                text = banner + text
        try:
            path.write_text(text, encoding="utf-8", newline="\n")
        except OSError:
            continue
    return summary


def consolidation_eligible(
    database_or_workspace: Path | str,
    audit_id: str | None = None,
) -> bool:
    summary = read_summary(database_or_workspace, audit_id)
    return bool(summary and summary.consolidation_eligible)
