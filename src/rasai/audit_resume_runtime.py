"""Durable interruption recovery contract for one logical RASAi AUD.

The module does not resume a Python instruction pointer. It resumes from durable
checkpoints already persisted in audit.db. One AUD remains one observation; every
recovery execution is still represented by an RPR run.

Responsibilities kept here are intentionally operational:
- persist a secret-free resume plan before expensive collection starts;
- keep a local execution lease/session with heartbeat so an active AUD cannot be
  reprocessed concurrently;
- reconcile orphan fulfillment attempts left RUNNING by a killed process;
- expose the configured device universe so missing render contexts can be
  materialized by core_reprocessing;
- complete deterministic final derivations and CORE_AUDIT only after every other
  required work-item is satisfied.

No scoring formula, provider policy or live-evidence validity rule is changed here.
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, replace
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import socket
import sqlite3
import threading
from typing import Any, Iterator, Mapping, Sequence

from rasai.audit_fulfillment import (
    BLOCKED,
    FAILED_RETRYABLE,
    SUCCESS,
    ensure_schema as ensure_fulfillment_schema,
    list_work_items,
    merge_contract_configuration,
    recalculate,
    set_work_item_status,
)
from rasai.operational_log import try_append_operational_event
from rasai.persistence import AuditPersistence, AuditWorkspace

RESUME_PLAN_VERSION = "AUDIT-RESUME-001"
SESSION_SCHEMA_VERSION = "AUDIT-EXECUTION-SESSION-001"
INTERRUPTED = "INTERRUPTED"
_ACTIVE = "RUNNING"
_HEARTBEAT_SECONDS = 10.0
_REMOTE_STALE_SECONDS = 45.0
_INTERRUPTABLE_AUDIT_STATUSES = frozenset(
    {
        "CREATED",
        "INITIALIZING",
        "DISCOVERING",
        "ACQUIRING",
        "ANALYZING",
        "COMPARING",
        "SCORING",
        "RECOMMENDING",
        "REPORTING",
        "FAILED",
        "CANCELLED",
    }
)
_RESOLVED = frozenset({SUCCESS, "DISABLED", "NOT_APPLICABLE"})
_SESSION_THREADS: dict[str, tuple[threading.Event, threading.Thread]] = {}
_SESSION_LOCK = threading.Lock()
_PLAN_OPTIONS: ContextVar[dict[str, Any] | None] = ContextVar(
    "rasai_audit_resume_plan_options",
    default=None,
)
_INSTALLED = False


@contextmanager
def resume_plan_options(options: Mapping[str, Any]) -> Iterator[None]:
    """Bind effective non-secret execution options before the AUD workspace exists."""
    merged = dict(_PLAN_OPTIONS.get() or {})
    for key, value in dict(options or {}).items():
        if value is not None:
            merged[str(key)] = value
    token = _PLAN_OPTIONS.set(merged)
    try:
        yield
    finally:
        _PLAN_OPTIONS.reset(token)


@dataclass(frozen=True, slots=True)
class ExecutionSession:
    execution_id: str
    audit_id: str
    kind: str
    source: str
    pid: int
    host: str


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _table_exists(connection: sqlite3.Connection, name: str) -> bool:
    return connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (name,),
    ).fetchone() is not None


def ensure_execution_schema(workspace: AuditWorkspace | Path | str) -> None:
    root = Path(workspace.root) if isinstance(workspace, AuditWorkspace) else Path(workspace)
    database = root / "audit.db" if root.is_dir() else root
    connection = sqlite3.connect(database)
    try:
        with connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS audit_execution_sessions(
                    execution_id TEXT PRIMARY KEY,
                    audit_id TEXT NOT NULL,
                    schema_version TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    source TEXT NOT NULL,
                    state TEXT NOT NULL,
                    pid INTEGER NOT NULL,
                    host TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    heartbeat_at TEXT NOT NULL,
                    finished_at TEXT,
                    note TEXT
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_audit_execution_sessions_audit "
                "ON audit_execution_sessions(audit_id,started_at)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_audit_execution_sessions_state "
                "ON audit_execution_sessions(audit_id,state,heartbeat_at)"
            )
    finally:
        connection.close()


def process_is_alive(pid: int) -> bool:
    """Probe process liveness without sending a destructive signal on Windows."""
    if pid <= 0:
        return False
    if os.name == "nt":
        try:
            import ctypes

            process_query_limited_information = 0x1000
            handle = ctypes.windll.kernel32.OpenProcess(  # type: ignore[attr-defined]
                process_query_limited_information,
                False,
                int(pid),
            )
            if not handle:
                return False
            ctypes.windll.kernel32.CloseHandle(handle)  # type: ignore[attr-defined]
            return True
        except (AttributeError, OSError):
            return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _session_active(row: sqlite3.Row) -> bool:
    if str(row["state"] or "").upper() != _ACTIVE:
        return False
    host = str(row["host"] or "")
    pid = int(row["pid"] or 0)
    if host == socket.gethostname():
        return process_is_alive(pid)
    heartbeat = _parse_time(str(row["heartbeat_at"] or ""))
    if heartbeat is None:
        return False
    age = (datetime.now(timezone.utc) - heartbeat).total_seconds()
    return age <= _REMOTE_STALE_SECONDS


def reconcile_abandoned_sessions(workspace: AuditWorkspace, audit_id: str) -> int:
    """Mark dead RUNNING sessions interrupted while preserving their history."""
    ensure_execution_schema(workspace)
    connection = sqlite3.connect(workspace.database)
    connection.row_factory = sqlite3.Row
    interrupted = 0
    try:
        rows = connection.execute(
            """SELECT * FROM audit_execution_sessions
               WHERE audit_id=? AND state='RUNNING'
               ORDER BY started_at""",
            (audit_id,),
        ).fetchall()
        now = _now()
        with connection:
            for row in rows:
                if _session_active(row):
                    continue
                connection.execute(
                    """UPDATE audit_execution_sessions
                       SET state=?,finished_at=?,heartbeat_at=?,
                           note=COALESCE(note,'processo anterior não estava mais ativo')
                       WHERE execution_id=? AND state='RUNNING'""",
                    (INTERRUPTED, now, now, str(row["execution_id"])),
                )
                interrupted += 1
    finally:
        connection.close()
    if interrupted:
        try_append_operational_event(
            workspace,
            "AUDIT_EXECUTION_SESSION_RECONCILED",
            level="WARNING",
            audit_id=audit_id,
            interrupted_sessions=interrupted,
        )
    return interrupted


def assert_no_active_execution(workspace: AuditWorkspace, audit_id: str) -> None:
    reconcile_abandoned_sessions(workspace, audit_id)
    connection = sqlite3.connect(workspace.database)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
            """SELECT * FROM audit_execution_sessions
               WHERE audit_id=? AND state='RUNNING'
               ORDER BY started_at DESC""",
            (audit_id,),
        ).fetchall()
    finally:
        connection.close()
    active = next((row for row in rows if _session_active(row)), None)
    if active is None:
        return
    raise RuntimeError(
        "a auditoria possui uma execução ativa; a retomada concorrente foi bloqueada "
        f"(execution_id={active['execution_id']}, pid={active['pid']}, host={active['host']})"
    )


def _heartbeat_loop(workspace: AuditWorkspace, execution_id: str, stop: threading.Event) -> None:
    while not stop.wait(_HEARTBEAT_SECONDS):
        try:
            connection = sqlite3.connect(workspace.database, timeout=5)
            try:
                with connection:
                    connection.execute(
                        """UPDATE audit_execution_sessions SET heartbeat_at=?
                           WHERE execution_id=? AND state='RUNNING'""",
                        (_now(), execution_id),
                    )
            finally:
                connection.close()
        except sqlite3.Error:
            # A transient SQLite lock must not terminate the audit. The next heartbeat
            # retries; final ownership is checked again before a later RPR can start.
            continue


def start_execution_session(
    workspace: AuditWorkspace,
    audit_id: str,
    *,
    kind: str,
    source: str,
    reject_active: bool = True,
) -> ExecutionSession:
    """Acquire one local AUD execution lease and start a lightweight heartbeat."""
    ensure_execution_schema(workspace)

    from rasai.domain import new_id

    session = ExecutionSession(
        execution_id=new_id("EXE"),
        audit_id=audit_id,
        kind=str(kind).upper(),
        source=str(source).upper(),
        pid=os.getpid(),
        host=socket.gethostname(),
    )
    now = _now()
    interrupted_sessions = 0
    connection = sqlite3.connect(workspace.database, timeout=10)
    connection.row_factory = sqlite3.Row
    try:
        # BEGIN IMMEDIATE serializes the check-and-acquire operation. Without this,
        # two processes could both observe "no active session" and then insert leases.
        connection.execute("BEGIN IMMEDIATE")
        rows = connection.execute(
            """SELECT * FROM audit_execution_sessions
               WHERE audit_id=? AND state='RUNNING'
               ORDER BY started_at DESC""",
            (audit_id,),
        ).fetchall()
        if reject_active:
            active = next((row for row in rows if _session_active(row)), None)
            if active is not None:
                connection.rollback()
                raise RuntimeError(
                    "a auditoria possui uma execução ativa; a retomada concorrente foi bloqueada "
                    f"(execution_id={active['execution_id']}, pid={active['pid']}, host={active['host']})"
                )
        for row in rows:
            if _session_active(row):
                continue
            connection.execute(
                """UPDATE audit_execution_sessions
                   SET state=?,finished_at=?,heartbeat_at=?,
                       note=COALESCE(note,'processo anterior não estava mais ativo')
                   WHERE execution_id=? AND state='RUNNING'""",
                (INTERRUPTED, now, now, str(row["execution_id"])),
            )
            interrupted_sessions += 1
        connection.execute(
            """INSERT INTO audit_execution_sessions(
                execution_id,audit_id,schema_version,kind,source,state,pid,host,
                started_at,heartbeat_at,finished_at,note
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                session.execution_id,
                session.audit_id,
                SESSION_SCHEMA_VERSION,
                session.kind,
                session.source,
                _ACTIVE,
                session.pid,
                session.host,
                now,
                now,
                None,
                None,
            ),
        )
        connection.commit()
    except BaseException:
        if connection.in_transaction:
            connection.rollback()
        raise
    finally:
        connection.close()

    if interrupted_sessions:
        try_append_operational_event(
            workspace,
            "AUDIT_EXECUTION_SESSION_RECONCILED",
            level="WARNING",
            audit_id=audit_id,
            interrupted_sessions=interrupted_sessions,
        )

    stop = threading.Event()
    thread = threading.Thread(
        target=_heartbeat_loop,
        args=(workspace, session.execution_id, stop),
        name=f"rasai-audit-heartbeat-{session.execution_id}",
        daemon=True,
    )
    with _SESSION_LOCK:
        _SESSION_THREADS[session.execution_id] = (stop, thread)
    thread.start()
    try_append_operational_event(
        workspace,
        "AUDIT_EXECUTION_SESSION_STARTED",
        audit_id=audit_id,
        execution_id=session.execution_id,
        execution_kind=session.kind,
        source=session.source,
        pid=session.pid,
        host=session.host,
    )
    return session


def finish_execution_session(
    workspace: AuditWorkspace,
    session: ExecutionSession | None,
    *,
    state: str,
    note: str | None = None,
) -> None:
    if session is None:
        return
    with _SESSION_LOCK:
        runtime = _SESSION_THREADS.pop(session.execution_id, None)
    if runtime is not None:
        stop, thread = runtime
        stop.set()
        thread.join(timeout=1.0)
    ensure_execution_schema(workspace)
    now = _now()
    connection = sqlite3.connect(workspace.database)
    try:
        with connection:
            connection.execute(
                """UPDATE audit_execution_sessions
                   SET state=?,heartbeat_at=?,finished_at=?,note=COALESCE(?,note)
                   WHERE execution_id=?""",
                (str(state).upper(), now, now, (note or "")[:1000] or None, session.execution_id),
            )
    finally:
        connection.close()
    try_append_operational_event(
        workspace,
        "AUDIT_EXECUTION_SESSION_FINISHED",
        level="INFO" if str(state).upper() == "COMPLETED" else "WARNING",
        audit_id=session.audit_id,
        execution_id=session.execution_id,
        execution_kind=session.kind,
        state=str(state).upper(),
        note=(note or "")[:512] or None,
    )


def persist_resume_plan(
    workspace: AuditWorkspace,
    audit_id: str,
    *,
    targets: Sequence[str],
    target_type: str,
    language: str,
    market: str,
    max_pages: int,
    device_context: str,
    content_remediation: bool,
    technical_remediation: bool,
) -> dict[str, Any]:
    """Persist the minimum canonical, secret-free plan needed by recovery."""
    plan = {
        "schema_version": RESUME_PLAN_VERSION,
        "targets": [str(value) for value in targets],
        "target_type": str(target_type),
        "language": str(language),
        "market": str(market),
        "max_pages": int(max_pages),
        "device_context": str(device_context),
        "content_remediation": bool(content_remediation),
        "technical_remediation": bool(technical_remediation),
    }
    merge_contract_configuration(workspace, audit_id, resume_plan=plan)
    try:
        from rasai.audit_configuration_reuse_runtime import persist_current_configuration

        persist_current_configuration(workspace.root, audit_id)
    except Exception as exc:
        # The resume plan above is the mandatory fallback. A console/SaaS configuration
        # snapshot may not exist for direct Python callers.
        try_append_operational_event(
            workspace,
            "AUDIT_CONFIGURATION_EARLY_PERSISTENCE_UNAVAILABLE",
            level="WARNING",
            audit_id=audit_id,
            error_type=type(exc).__name__,
        )
    return plan


def _load_json(raw: Any) -> Any:
    if raw in (None, ""):
        return {}
    if isinstance(raw, (dict, list)):
        return raw
    try:
        return json.loads(str(raw))
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}


def _find_key(value: Any, key: str) -> Any:
    if isinstance(value, dict):
        if key in value:
            return value[key]
        for child in value.values():
            found = _find_key(child, key)
            if found not in (None, ""):
                return found
    elif isinstance(value, list):
        for child in value:
            found = _find_key(child, key)
            if found not in (None, ""):
                return found
    return None


def load_resume_plan(workspace: AuditWorkspace, audit_id: str) -> dict[str, Any]:
    """Load the explicit plan, falling back conservatively to persisted configuration."""
    ensure_fulfillment_schema(workspace)
    connection = sqlite3.connect(workspace.database)
    connection.row_factory = sqlite3.Row
    try:
        row = connection.execute(
            "SELECT configuration FROM audit_fulfillment_contracts WHERE audit_id=?",
            (audit_id,),
        ).fetchone()
        config = _load_json(row["configuration"]) if row is not None else {}
        if isinstance(config, dict) and isinstance(config.get("resume_plan"), dict):
            return dict(config["resume_plan"])

        if not _table_exists(connection, "audit_execution_configurations"):
            return {}
        columns = {
            str(item[1])
            for item in connection.execute("PRAGMA table_info(audit_execution_configurations)").fetchall()
        }
        if "configuration_json" not in columns:
            return {}
        persisted = connection.execute(
            "SELECT configuration_json FROM audit_execution_configurations WHERE audit_id=?",
            (audit_id,),
        ).fetchone()
    finally:
        connection.close()
    raw = _load_json(persisted[0]) if persisted is not None else {}
    if not isinstance(raw, dict):
        return {}
    device = _find_key(raw, "device_context")
    urls = _find_key(raw, "urls")
    max_pages = _find_key(raw, "max_pages")
    plan: dict[str, Any] = {"schema_version": "LEGACY-CONFIG-FALLBACK"}
    if device not in (None, ""):
        plan["device_context"] = str(device)
    if isinstance(urls, list):
        plan["targets"] = [str(value) for value in urls]
    if max_pages not in (None, ""):
        try:
            plan["max_pages"] = int(max_pages)
        except (TypeError, ValueError):
            pass
    return plan if len(plan) > 1 else {}


def expected_devices_for_audit(workspace: AuditWorkspace, audit_id: str) -> tuple[str, ...]:
    from rasai.device_context import devices_from_context

    plan = load_resume_plan(workspace, audit_id)
    configured = str(plan.get("device_context") or "").strip().casefold()
    if configured:
        try:
            return tuple(device.value for device in devices_from_context(configured))
        except ValueError:
            pass

    # Legacy audits may still carry the original device universe in a completed
    # snapshot. This is evidence-backed and therefore safe to reuse.
    connection = sqlite3.connect(workspace.database)
    try:
        rows = connection.execute(
            """SELECT ps.browser_metadata FROM page_snapshots ps
               JOIN pages p ON p.page_id=ps.page_id
               WHERE p.audit_id=? ORDER BY ps.captured_at""",
            (audit_id,),
        ).fetchall()
    except sqlite3.OperationalError:
        rows = ()
    finally:
        connection.close()
    devices: list[str] = []
    for row in rows:
        metadata = _load_json(row[0])
        values = metadata.get("audit_device_context") if isinstance(metadata, dict) else None
        if isinstance(values, list):
            for value in values:
                normalized = str(value).upper()
                if normalized in {"MOBILE", "DESKTOP"} and normalized not in devices:
                    devices.append(normalized)
    return tuple(devices)


def has_recovery_basis(workspace: AuditWorkspace, audit_id: str) -> bool:
    if load_resume_plan(workspace, audit_id):
        return True
    connection = sqlite3.connect(workspace.database)
    try:
        pages = int(
            connection.execute("SELECT count(*) FROM pages WHERE audit_id=?", (audit_id,)).fetchone()[0]
        )
        snapshots = int(
            connection.execute(
                """SELECT count(*) FROM page_snapshots ps
                   JOIN pages p ON p.page_id=ps.page_id WHERE p.audit_id=?""",
                (audit_id,),
            ).fetchone()[0]
        )
        return pages > 0 or snapshots > 0
    except sqlite3.OperationalError:
        return False
    finally:
        connection.close()


def interrupted_core_projection(workspace: AuditWorkspace, audit_id: str, audit_status: str) -> tuple[str, bool]:
    status = str(audit_status or "").upper()
    if status == "COMPLETED":
        return SUCCESS, False
    if status in _INTERRUPTABLE_AUDIT_STATUSES and has_recovery_basis(workspace, audit_id):
        return FAILED_RETRYABLE, True
    return BLOCKED, False


def reconcile_interrupted_attempts(workspace: AuditWorkspace, audit_id: str) -> int:
    """Close orphan RUNNING attempts without discarding a separately persisted result."""
    ensure_fulfillment_schema(workspace)
    now = _now()
    connection = sqlite3.connect(workspace.database)
    connection.row_factory = sqlite3.Row
    reconciled = 0
    try:
        rows = connection.execute(
            """SELECT a.attempt_id,a.work_item_id,w.status
               FROM audit_fulfillment_attempts a
               JOIN audit_fulfillment_work_items w ON w.work_item_id=a.work_item_id
               WHERE a.audit_id=? AND a.status='RUNNING'""",
            (audit_id,),
        ).fetchall()
        with connection:
            for row in rows:
                connection.execute(
                    """UPDATE audit_fulfillment_attempts
                       SET status='INTERRUPTED',finished_at=?,
                           error_class=COALESCE(error_class,'EXECUTION_INTERRUPTED'),
                           error_code=COALESCE(error_code,'ATTEMPT_ABANDONED'),
                           error_message=COALESCE(error_message,'processo terminou antes do fechamento da tentativa')
                       WHERE attempt_id=? AND status='RUNNING'""",
                    (now, str(row["attempt_id"])),
                )
                if str(row["status"] or "").upper() == "RUNNING":
                    connection.execute(
                        """UPDATE audit_fulfillment_work_items
                           SET status='FAILED_RETRYABLE',retryable=1,
                               last_error_class='EXECUTION_INTERRUPTED',
                               last_error_code='ATTEMPT_ABANDONED',
                               last_error_message='tentativa interrompida; evidência persistida será reconciliada antes de novo retry',
                               updated_at=?
                           WHERE work_item_id=? AND status='RUNNING'""",
                        (now, str(row["work_item_id"])),
                    )
                reconciled += 1
    finally:
        connection.close()
    if reconciled:
        recalculate(workspace, audit_id)
        try_append_operational_event(
            workspace,
            "AUDIT_INTERRUPTED_ATTEMPTS_RECONCILED",
            level="WARNING",
            audit_id=audit_id,
            attempts=reconciled,
        )
    return reconciled


def _core_was_finalized(workspace: AuditWorkspace, audit_id: str) -> bool:
    return any(
        item.component == "CORE_AUDIT"
        and item.scope_key == "AUDIT"
        and item.status == SUCCESS
        for item in list_work_items(workspace, audit_id)
    )


def _all_other_required_resolved(workspace: AuditWorkspace, audit_id: str) -> bool:
    for item in list_work_items(workspace, audit_id):
        if not item.required or item.component == "CORE_AUDIT":
            continue
        if item.status not in _RESOLVED:
            return False
    return True


def finalize_resumed_audit(
    workspace: AuditWorkspace,
    audit_id: str,
    *,
    reprocess_id: str | None,
) -> bool:
    """Finish missing replay-safe derivations and promote CORE_AUDIT only when safe."""
    if not _all_other_required_resolved(workspace, audit_id):
        return False

    # CORE_AUDIT is the durable proof that scoring/recommendation finalization reached
    # its checkpoint in the original execution. A process can die after persisting only
    # part of M9/M10; the mere existence of one score is therefore insufficient proof.
    # When CORE_AUDIT never finalized, rebuild these replay-safe derivations from the
    # effective persisted finding/rule set before promoting the same AUD to COMPLETE.
    if reprocess_id and not _core_was_finalized(workspace, audit_id):
        from rasai.reprocess_ai import recompute_derived_after_ai

        recompute_derived_after_ai(
            workspace=workspace,
            audit_id=audit_id,
            reprocess_id=reprocess_id,
            semantic_changed=False,
        )

    set_work_item_status(
        workspace,
        audit_id=audit_id,
        component="CORE_AUDIT",
        scope_key="AUDIT",
        status=SUCCESS,
        result_ref=f"audit:{audit_id}",
        retryable=False,
    )

    from rasai.domain import AuditStatus, CompletionStatus

    with AuditPersistence(workspace) as persistence:
        current = persistence.audits.get(audit_id)
        if current is not None and current.status is not AuditStatus.COMPLETED:
            completion = (
                CompletionStatus.COMPLETE_WITH_LIMITATIONS
                if current.limitations
                or current.audit_mode is None
                or getattr(current.audit_mode, "value", current.audit_mode) != "FULL"
                else CompletionStatus.COMPLETE
            )
            persistence.audits.complete(audit_id, completion)

    try:
        from rasai.recommendation_governance import evaluate_recommendations
        from rasai.m16_root_cause import materialize_root_causes
        from rasai.m17_precision import materialize_m17_precision

        evaluate_recommendations(workspace.database, audit_id)
        materialize_root_causes(audit_id=audit_id, workspace=workspace)
        materialize_m17_precision(audit_id=audit_id, workspace=workspace)
    except Exception as exc:
        try_append_operational_event(
            workspace,
            "AUDIT_RESUME_FINAL_DERIVATION_WARNING",
            level="WARNING",
            audit_id=audit_id,
            error_type=type(exc).__name__,
            error_message=str(exc)[:512],
        )

    summary = recalculate(workspace, audit_id)
    try_append_operational_event(
        workspace,
        "AUDIT_RESUME_COMPLETED",
        audit_id=audit_id,
        reprocess_id=reprocess_id,
        processing_status=summary.processing_status,
        score_status=summary.score_status,
        report_status=summary.report_status,
    )
    return summary.processing_status == "COMPLETE"


def _replace_result(result: Any, summary: Any) -> Any:
    try:
        return replace(
            result,
            processing_status=summary.processing_status,
            score_status=summary.score_status,
            report_status=summary.report_status,
            consolidation_eligible=summary.consolidation_eligible,
            remaining_items=summary.pending_items + summary.blocked_items,
            temporal_expired_items=summary.expired_items,
        )
    except TypeError:
        return result


def install() -> None:
    """Wrap the fully composed RPR entrypoint with interruption reconciliation/lease."""
    global _INSTALLED
    from rasai import audit_reprocess

    current = audit_reprocess.reprocess_audit
    if bool(getattr(current, "_rasai_interrupted_audit_resume", False)):
        _INSTALLED = True
        return

    def reprocess_with_resume_guard(
        audit_id: str,
        *,
        audits_root: str | Path = "audits",
        source: str = "CLI",
    ):
        workspace = AuditWorkspace.open(Path(audits_root) / audit_id)
        session = start_execution_session(
            workspace,
            audit_id,
            kind="REPROCESS",
            source=source,
            reject_active=True,
        )
        try:
            reconcile_interrupted_attempts(workspace, audit_id)
            result = current(audit_id, audits_root=audits_root, source=source)
            reprocess_id = str(getattr(result, "reprocess_id", "") or "") or None
            if finalize_resumed_audit(
                workspace,
                audit_id,
                reprocess_id=reprocess_id,
            ):
                if reprocess_id:
                    from rasai.audit_fulfillment import finish_reprocess_run

                    finish_reprocess_run(
                        workspace,
                        reprocess_id,
                        status=SUCCESS,
                        attempted_items=int(getattr(result, "attempted_items", 0) or 0),
                        successful_items=int(getattr(result, "successful_items", 0) or 0),
                        note="RPR concluiu a retomada segura da auditoria interrompida",
                    )
                summary = recalculate(workspace, audit_id)
                result = _replace_result(result, summary)

            # audit_execution_sessions belongs to audit.db and therefore participates
            # in the report source fingerprint. Close the mutable execution session
            # before the final catalog projection; otherwise the subsequent session
            # UPDATE would make the just-generated report stale immediately.
            finish_execution_session(workspace, session, state="COMPLETED")
            session = None
            try:
                from rasai.report_completion import materialize_catalog_report_projection

                materialize_catalog_report_projection(audit_id=audit_id, workspace=workspace)
            except Exception as exc:
                try_append_operational_event(
                    workspace,
                    "AUDIT_RESUME_REPORT_PROJECTION_WARNING",
                    level="WARNING",
                    audit_id=audit_id,
                    error_type=type(exc).__name__,
                    error_message=str(exc)[:512],
                )
            return result
        except BaseException as exc:
            state = "INTERRUPTED" if isinstance(exc, KeyboardInterrupt) else "FAILED"
            finish_execution_session(
                workspace,
                session,
                state=state,
                note=f"{type(exc).__name__}: {str(exc)[:512]}",
            )
            raise

    reprocess_with_resume_guard._rasai_interrupted_audit_resume = True
    reprocess_with_resume_guard._rasai_original = current
    audit_reprocess.reprocess_audit = reprocess_with_resume_guard
    _INSTALLED = True
