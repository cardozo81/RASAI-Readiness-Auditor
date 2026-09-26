"""Safe local management and deletion of persisted RASAi AUD workspaces.

The module is deliberately administrative. It never recalculates scores, reruns
collectors/providers, or mutates immutable AUD databases. Deletion is a two-phase
filesystem operation: every affected AUD/CONS is first moved into an audits-root
trash batch; only after the whole batch is staged is the deletion considered
logically committed and physical cleanup attempted.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
import json
import os
from pathlib import Path
import shutil
import sqlite3
from typing import Iterable
import uuid


ACTIVE_AUDIT_STATUSES = frozenset({
    "CREATED", "INITIALIZING", "DISCOVERING", "ACQUIRING", "ANALYZING",
    "COMPARING", "SCORING", "RECOMMENDING", "REPORTING",
    "RUNNING", "PROCESSING", "IN_PROGRESS", "STARTED",
})
ACTIVE_FULFILLMENT_STATUSES = frozenset({"PROCESSING"})
DELETION_LEDGER = "audit-deletions.jsonl"


@dataclass(frozen=True, slots=True)
class AuditInventoryItem:
    audit_id: str
    workspace: Path
    event_time: str | None
    created_at: str | None
    project_name: str
    status: str
    completion_status: str | None
    domains: tuple[str, ...]
    size_bytes: int
    execution_series_id: str | None
    consolidation_eligible: bool | None
    configuration_reusable: bool
    fulfillment_processing_status: str | None
    execution_active: bool | None = None
    metadata_error: str | None = None

    @property
    def is_active(self) -> bool:
        # New workspaces have an execution-session lease. It is authoritative because
        # an interrupted process may leave the business lifecycle status in ANALYZING,
        # SCORING, etc. indefinitely. Legacy workspaces fall back to status heuristics.
        if self.execution_active is not None:
            return self.execution_active
        return (
            self.status.upper() in ACTIVE_AUDIT_STATUSES
            or (self.fulfillment_processing_status or "").upper() in ACTIVE_FULFILLMENT_STATUSES
        )


@dataclass(frozen=True, slots=True)
class AuditInventoryFilter:
    date_from: date | None = None
    date_to: date | None = None
    domain: str | None = None
    project: str | None = None
    status: str | None = None


@dataclass(frozen=True, slots=True)
class ConsolidatedDependency:
    cons_id: str
    path: Path
    source_audits: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class DeletionImpact:
    audits: tuple[AuditInventoryItem, ...]
    consolidated: tuple[ConsolidatedDependency, ...]
    total_bytes: int
    series_ids: tuple[str, ...]
    reusable_configurations: int


@dataclass(frozen=True, slots=True)
class DeletionResult:
    status: str
    batch_id: str | None
    audit_ids: tuple[str, ...]
    consolidated_ids: tuple[str, ...]
    message: str
    cleanup_pending_bytes: int = 0
    rollback_failures: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class CleanupResult:
    removed_batches: int
    pending_batches: int
    pending_bytes: int
    errors: tuple[str, ...]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _table_exists(connection: sqlite3.Connection, name: str) -> bool:
    return connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1", (name,)
    ).fetchone() is not None


def _columns(connection: sqlite3.Connection, name: str) -> set[str]:
    if not _table_exists(connection, name):
        return set()
    return {str(row[1]) for row in connection.execute(f'PRAGMA table_info("{name}")').fetchall()}


def _read_only(database: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(
        f"file:{database.resolve().as_posix()}?mode=ro",
        uri=True,
        timeout=2.0,
    )
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")
    return connection


def _directory_size(path: Path) -> int:
    total = 0
    try:
        for root, directories, files in os.walk(path, followlinks=False):
            directories[:] = [name for name in directories if not (Path(root) / name).is_symlink()]
            for name in files:
                candidate = Path(root) / name
                try:
                    if not candidate.is_symlink():
                        total += candidate.stat().st_size
                except OSError:
                    continue
    except OSError:
        return total
    return total


def _audit_domains(connection: sqlite3.Connection, audit_id: str) -> tuple[str, ...]:
    values: list[str] = []
    if _table_exists(connection, "audit_targets"):
        cols = _columns(connection, "audit_targets")
        if {"audit_id", "normalized_origin"} <= cols:
            for row in connection.execute(
                "SELECT DISTINCT normalized_origin FROM audit_targets WHERE audit_id=?",
                (audit_id,),
            ).fetchall():
                value = str(row[0] or "").strip()
                if value:
                    values.append(value)
    if not values and _table_exists(connection, "pages"):
        cols = _columns(connection, "pages")
        if {"audit_id", "normalized_url"} <= cols:
            from urllib.parse import urlsplit

            for row in connection.execute(
                "SELECT DISTINCT normalized_url FROM pages WHERE audit_id=?",
                (audit_id,),
            ).fetchall():
                value = str(row[0] or "").strip()
                if not value:
                    continue
                host = urlsplit(value).hostname
                if host:
                    values.append(host)
    return tuple(sorted(dict.fromkeys(values)))


def _configuration_state(connection: sqlite3.Connection, audit_id: str) -> tuple[str | None, bool]:
    if not _table_exists(connection, "audit_execution_configurations"):
        return None, False
    cols = _columns(connection, "audit_execution_configurations")
    if "audit_id" not in cols:
        return None, False
    select = ["audit_id"]
    if "execution_series_id" in cols:
        select.append("execution_series_id")
    row = connection.execute(
        f"SELECT {','.join(select)} FROM audit_execution_configurations WHERE audit_id=? LIMIT 1",
        (audit_id,),
    ).fetchone()
    if row is None:
        return None, False
    series_id = str(row["execution_series_id"] or "").strip() if "execution_series_id" in row.keys() else ""
    return series_id or None, True


def _execution_active_state(connection: sqlite3.Connection, audit_id: str) -> bool | None:
    if not _table_exists(connection, "audit_execution_sessions"):
        return None
    cols = _columns(connection, "audit_execution_sessions")
    required = {"audit_id", "state", "pid", "host", "heartbeat_at"}
    if not required <= cols:
        return None
    rows = connection.execute(
        """SELECT state,pid,host,heartbeat_at FROM audit_execution_sessions
           WHERE audit_id=? AND state='RUNNING' ORDER BY started_at DESC""",
        (audit_id,),
    ).fetchall()
    if not rows:
        return False

    import socket

    local_host = socket.gethostname()
    now = datetime.now(timezone.utc)
    for row in rows:
        host = str(row["host"] or "")
        pid = int(row["pid"] or 0)
        if host == local_host and pid > 0:
            from rasai.audit_resume_runtime import process_is_alive

            if process_is_alive(pid):
                return True
            continue
        try:
            heartbeat = datetime.fromisoformat(str(row["heartbeat_at"] or "").replace("Z", "+00:00"))
            if heartbeat.tzinfo is None:
                heartbeat = heartbeat.replace(tzinfo=timezone.utc)
            if (now - heartbeat.astimezone(timezone.utc)).total_seconds() <= 45:
                return True
        except ValueError:
            continue
    return False


def _fulfillment_state(connection: sqlite3.Connection, audit_id: str) -> tuple[str | None, bool | None]:
    if not _table_exists(connection, "audit_fulfillment_contracts"):
        return None, None
    cols = _columns(connection, "audit_fulfillment_contracts")
    if "audit_id" not in cols:
        return None, None
    selected = ["audit_id"]
    if "processing_status" in cols:
        selected.append("processing_status")
    if "consolidation_eligible" in cols:
        selected.append("consolidation_eligible")
    row = connection.execute(
        f"SELECT {','.join(selected)} FROM audit_fulfillment_contracts WHERE audit_id=? LIMIT 1",
        (audit_id,),
    ).fetchone()
    if row is None:
        return None, None
    processing = str(row["processing_status"] or "").strip() if "processing_status" in row.keys() else ""
    eligible: bool | None = None
    if "consolidation_eligible" in row.keys() and row["consolidation_eligible"] is not None:
        eligible = bool(int(row["consolidation_eligible"]))
    return processing or None, eligible


def _read_inventory_item(workspace: Path) -> AuditInventoryItem:
    database = workspace / "audit.db"
    size = _directory_size(workspace)
    if not database.is_file():
        return AuditInventoryItem(
            audit_id=workspace.name,
            workspace=workspace,
            event_time=None,
            created_at=None,
            project_name="",
            status="UNKNOWN",
            completion_status=None,
            domains=(),
            size_bytes=size,
            execution_series_id=None,
            consolidation_eligible=None,
            configuration_reusable=False,
            fulfillment_processing_status=None,
            metadata_error="audit.db ausente",
        )
    try:
        connection = _read_only(database)
        try:
            if not _table_exists(connection, "audits"):
                raise ValueError("tabela audits ausente")
            row = connection.execute("SELECT * FROM audits ORDER BY created_at DESC LIMIT 1").fetchone()
            if row is None:
                raise ValueError("tabela audits vazia")
            audit = dict(row)
            audit_id = str(audit.get("audit_id") or workspace.name)
            created_at = str(audit.get("created_at") or "").strip() or None
            started_at = str(audit.get("started_at") or "").strip() or None
            completed_at = str(audit.get("completed_at") or "").strip() or None
            series_id, reusable = _configuration_state(connection, audit_id)
            fulfillment_processing, eligible = _fulfillment_state(connection, audit_id)
            execution_active = _execution_active_state(connection, audit_id)
            return AuditInventoryItem(
                audit_id=audit_id,
                workspace=workspace,
                event_time=completed_at or started_at or created_at,
                created_at=created_at,
                project_name=str(audit.get("project_name") or ""),
                status=str(audit.get("status") or "UNKNOWN"),
                completion_status=str(audit.get("completion_status") or "").strip() or None,
                domains=_audit_domains(connection, audit_id),
                size_bytes=size,
                execution_series_id=series_id,
                consolidation_eligible=eligible,
                configuration_reusable=reusable,
                fulfillment_processing_status=fulfillment_processing,
                execution_active=execution_active,
            )
        finally:
            connection.close()
    except (OSError, sqlite3.Error, ValueError) as exc:
        return AuditInventoryItem(
            audit_id=workspace.name,
            workspace=workspace,
            event_time=None,
            created_at=None,
            project_name="",
            status="UNKNOWN",
            completion_status=None,
            domains=(),
            size_bytes=size,
            execution_series_id=None,
            consolidation_eligible=None,
            configuration_reusable=False,
            fulfillment_processing_status=None,
            metadata_error=f"{type(exc).__name__}: {exc}",
        )


def inventory(audits_root: str | Path) -> tuple[AuditInventoryItem, ...]:
    root = Path(audits_root)
    if not root.is_dir():
        return ()
    items = [
        _read_inventory_item(path)
        for path in root.iterdir()
        if path.is_dir()
        and not path.is_symlink()
        and path.name.upper().startswith("AUD-")
        and (path / "audit.db").is_file()
    ]
    return tuple(sorted(items, key=lambda item: (item.event_time or "", item.audit_id), reverse=True))


def _event_date(item: AuditInventoryItem) -> date | None:
    if not item.event_time:
        return None
    try:
        return datetime.fromisoformat(item.event_time.replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return date.fromisoformat(item.event_time[:10])
        except ValueError:
            return None


def filter_inventory(
    items: Iterable[AuditInventoryItem],
    filters: AuditInventoryFilter,
) -> tuple[AuditInventoryItem, ...]:
    domain = (filters.domain or "").strip().casefold()
    project = (filters.project or "").strip().casefold()
    status = (filters.status or "").strip().casefold()
    output: list[AuditInventoryItem] = []
    for item in items:
        item_date = _event_date(item)
        if filters.date_from and (item_date is None or item_date < filters.date_from):
            continue
        if filters.date_to and (item_date is None or item_date > filters.date_to):
            continue
        if domain and not any(domain in value.casefold() for value in item.domains):
            continue
        if project and project not in item.project_name.casefold():
            continue
        statuses = {item.status.casefold(), (item.completion_status or "").casefold()}
        if status and status not in statuses:
            continue
        output.append(item)
    return tuple(output)


def consolidated_dependencies(
    audits_root: str | Path,
    audit_ids: Iterable[str],
) -> tuple[ConsolidatedDependency, ...]:
    selected = {str(value).strip().upper() for value in audit_ids if str(value).strip()}
    if not selected:
        return ()
    root = Path(audits_root) / "consolidated"
    if not root.is_dir():
        return ()
    dependencies: list[ConsolidatedDependency] = []
    for cons_root in sorted(root.glob("CONS-*")):
        if not cons_root.is_dir():
            continue
        if cons_root.is_symlink():
            raise RuntimeError(f"CONS simbólico não é elegível para exclusão coordenada: {cons_root.name}")
        manifest = cons_root / "manifest.json"
        try:
            raw = manifest.read_text(encoding="utf-8")
        except OSError as exc:
            raise RuntimeError(f"manifest de CONS não pôde ser lido: {cons_root.name}: {exc}") from exc
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            if any(audit_id in raw.upper() for audit_id in selected):
                raise RuntimeError(
                    f"manifest inválido impede validar dependência de {cons_root.name}"
                ) from exc
            continue
        sources = tuple(
            str(entry.get("audit_id") or "").strip().upper()
            for entry in payload.get("source_audits", [])
            if isinstance(entry, dict) and str(entry.get("audit_id") or "").strip()
        )
        if selected.intersection(sources):
            dependencies.append(
                ConsolidatedDependency(
                    cons_id=str(payload.get("cons_id") or cons_root.name),
                    path=cons_root,
                    source_audits=sources,
                )
            )
    return tuple(dependencies)


def plan_deletion(audits_root: str | Path, audit_ids: Iterable[str]) -> DeletionImpact:
    selected = tuple(dict.fromkeys(str(value).strip().upper() for value in audit_ids if str(value).strip()))
    if not selected:
        raise ValueError("nenhum AUD selecionado")
    by_id = {item.audit_id.upper(): item for item in inventory(audits_root)}
    missing = [audit_id for audit_id in selected if audit_id not in by_id]
    if missing:
        raise FileNotFoundError(f"AUD não encontrado: {', '.join(missing)}")
    audits = tuple(by_id[audit_id] for audit_id in selected)
    unreadable = [item.audit_id for item in audits if item.metadata_error]
    if unreadable:
        raise RuntimeError(
            "metadados não puderam ser validados para exclusão segura: " + ", ".join(unreadable)
        )
    active = [item.audit_id for item in audits if item.is_active]
    if active:
        raise RuntimeError("AUD em processamento não pode ser excluído: " + ", ".join(active))
    consolidated = consolidated_dependencies(audits_root, selected)
    series_ids = tuple(sorted({item.execution_series_id for item in audits if item.execution_series_id}))
    return DeletionImpact(
        audits=audits,
        consolidated=consolidated,
        total_bytes=sum(item.size_bytes for item in audits)
        + sum(_directory_size(item.path) for item in consolidated),
        series_ids=series_ids,
        reusable_configurations=sum(1 for item in audits if item.configuration_reusable),
    )


def _ledger_path(root: Path) -> Path:
    directory = root / ".rasai"
    directory.mkdir(parents=True, exist_ok=True)
    return directory / DELETION_LEDGER


def _write_ledger(root: Path, payload: dict[str, object]) -> None:
    path = _ledger_path(root)
    with path.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str))
        stream.write("\n")


def _refresh_consolidated_index(root: Path) -> str | None:
    try:
        from rasai.consolidation.index import ConsolidationIndex

        result = ConsolidationIndex(root).refresh()
        if result.issues:
            return "; ".join(f"{item.db_path}: {item.reason}" for item in result.issues[:5])
        return None
    except (ImportError, OSError, sqlite3.Error, RuntimeError, ValueError) as exc:
        return f"{type(exc).__name__}: {exc}"


def _move(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    os.replace(source, destination)


def _batch_size(path: Path) -> int:
    return _directory_size(path) if path.exists() else 0


def execute_deletion(audits_root: str | Path, impact: DeletionImpact) -> DeletionResult:
    root = Path(audits_root)
    batch_id = (
        "DEL-"
        + datetime.now().strftime("%Y%m%d-%H%M%S-%f")[:-3]
        + "-"
        + uuid.uuid4().hex[:6].upper()
    )
    trash_root = root / ".trash"
    batch_root = trash_root / batch_id
    staged: list[tuple[Path, Path]] = []

    sources: list[tuple[Path, Path]] = []
    for item in impact.audits:
        sources.append((item.workspace, batch_root / "audits" / item.workspace.name))
    for item in impact.consolidated:
        sources.append((item.path, batch_root / "consolidated" / item.path.name))

    for item in impact.audits:
        if not item.workspace.is_dir() or not (item.workspace / "audit.db").is_file():
            return DeletionResult(
                status="PREPARATION_FAILED",
                batch_id=None,
                audit_ids=tuple(audit.audit_id for audit in impact.audits),
                consolidated_ids=tuple(cons.cons_id for cons in impact.consolidated),
                message=f"workspace deixou de estar disponível antes da exclusão: {item.audit_id}",
            )
        current = _read_inventory_item(item.workspace)
        if current.metadata_error or current.is_active:
            return DeletionResult(
                status="PREPARATION_FAILED",
                batch_id=None,
                audit_ids=tuple(audit.audit_id for audit in impact.audits),
                consolidated_ids=tuple(cons.cons_id for cons in impact.consolidated),
                message=f"AUD não está seguro para exclusão neste momento: {item.audit_id}",
            )

    try:
        batch_root.mkdir(parents=True, exist_ok=False)
        for source, destination in sources:
            if not source.exists():
                raise FileNotFoundError(str(source))
            _move(source, destination)
            staged.append((source, destination))
    except (OSError, FileNotFoundError) as exc:
        rollback_failures: list[str] = []
        for source, destination in reversed(staged):
            try:
                if destination.exists():
                    _move(destination, source)
            except OSError as rollback_exc:
                rollback_failures.append(f"{source}: {rollback_exc}")
        if not rollback_failures:
            try:
                shutil.rmtree(batch_root)
            except OSError:
                pass
        return DeletionResult(
            status="ROLLBACK_FAILED" if rollback_failures else "ROLLBACK_COMPLETED",
            batch_id=batch_id,
            audit_ids=tuple(audit.audit_id for audit in impact.audits),
            consolidated_ids=tuple(cons.cons_id for cons in impact.consolidated),
            message=f"preparação falhou antes do commit lógico: {type(exc).__name__}: {exc}",
            rollback_failures=tuple(rollback_failures),
        )

    ledger_payload = {
        "batch_id": batch_id,
        "deleted_at": _utc_now(),
        "status": "LOGICALLY_DELETED",
        "audits": [
            {
                **{
                    key: value
                    for key, value in asdict(item).items()
                    if key not in {"workspace", "metadata_error"}
                },
                "workspace": item.workspace.name,
            }
            for item in impact.audits
        ],
        "consolidated": [
            {"cons_id": item.cons_id, "source_audits": list(item.source_audits)}
            for item in impact.consolidated
        ],
        "index_warning": None,
        "control_plane": "historical records are intentionally not deleted by local evidence cleanup",
    }
    try:
        _write_ledger(root, ledger_payload)
    except OSError as exc:
        rollback_failures: list[str] = []
        for source, destination in reversed(staged):
            try:
                if destination.exists():
                    _move(destination, source)
            except OSError as rollback_exc:
                rollback_failures.append(f"{source}: {rollback_exc}")
        if not rollback_failures:
            try:
                shutil.rmtree(batch_root)
            except OSError:
                pass
            _refresh_consolidated_index(root)
        return DeletionResult(
            status="ROLLBACK_FAILED" if rollback_failures else "ROLLBACK_COMPLETED",
            batch_id=batch_id,
            audit_ids=tuple(audit.audit_id for audit in impact.audits),
            consolidated_ids=tuple(cons.cons_id for cons in impact.consolidated),
            message=f"ledger de exclusão não pôde ser persistido; lote revertido: {exc}",
            rollback_failures=tuple(rollback_failures),
        )

    index_warning = _refresh_consolidated_index(root)

    try:
        shutil.rmtree(batch_root)
        try:
            if trash_root.is_dir() and not any(trash_root.iterdir()):
                trash_root.rmdir()
        except OSError:
            pass
        _write_ledger(
            root,
            {
                "batch_id": batch_id,
                "updated_at": _utc_now(),
                "status": "COMPLETED",
                "index_warning": index_warning,
            },
        )
        message = "exclusão concluída"
        if index_warning:
            message += f"; índice consolidado reportou aviso: {index_warning}"
        return DeletionResult(
            status="COMPLETED",
            batch_id=batch_id,
            audit_ids=tuple(audit.audit_id for audit in impact.audits),
            consolidated_ids=tuple(cons.cons_id for cons in impact.consolidated),
            message=message,
        )
    except OSError as exc:
        pending = _batch_size(batch_root)
        try:
            _write_ledger(
                root,
                {
                    "batch_id": batch_id,
                    "updated_at": _utc_now(),
                    "status": "PHYSICAL_CLEANUP_PENDING",
                    "pending_bytes": pending,
                    "error": f"{type(exc).__name__}: {exc}",
                    "index_warning": index_warning,
                },
            )
        except OSError:
            pass
        return DeletionResult(
            status="PHYSICAL_CLEANUP_PENDING",
            batch_id=batch_id,
            audit_ids=tuple(audit.audit_id for audit in impact.audits),
            consolidated_ids=tuple(cons.cons_id for cons in impact.consolidated),
            message=(
                f"exclusão lógica concluída; limpeza física pendente: {exc}"
                + (f"; índice consolidado: {index_warning}" if index_warning else "")
            ),
            cleanup_pending_bytes=pending,
        )


def cleanup_pending(audits_root: str | Path) -> CleanupResult:
    root = Path(audits_root)
    trash_root = root / ".trash"
    if not trash_root.is_dir():
        return CleanupResult(0, 0, 0, ())
    removed = 0
    errors: list[str] = []
    for batch in sorted(path for path in trash_root.glob("DEL-*") if path.is_dir()):
        try:
            shutil.rmtree(batch)
            removed += 1
            try:
                _write_ledger(
                    root,
                    {"batch_id": batch.name, "updated_at": _utc_now(), "status": "COMPLETED"},
                )
            except OSError:
                pass
        except OSError as exc:
            errors.append(f"{batch.name}: {type(exc).__name__}: {exc}")
    pending = tuple(path for path in trash_root.glob("DEL-*") if path.is_dir())
    pending_bytes = sum(_batch_size(path) for path in pending)
    try:
        if trash_root.is_dir() and not any(trash_root.iterdir()):
            trash_root.rmdir()
    except OSError:
        pass
    return CleanupResult(removed, len(pending), pending_bytes, tuple(errors))
