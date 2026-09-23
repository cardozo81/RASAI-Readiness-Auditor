"""Governança read-only das fontes do relatório consolidado.

Este módulo pertence exclusivamente ao domínio CONS. Ele não altera AUDs, fulfillment,
scoring ou catálogos; apenas inspeciona metadados persistidos e calcula hashes de
integridade para o pacote derivado.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from rasai.secret_safety import redact_value

GOVERNANCE_CONTRACT = "CONSOLIDATED-SOURCE-GOVERNANCE-003"

_SUCCESS_COMPLETION = {
    "COMPLETE",
    "COMPLETED",
    "SUCCESS",
    "COMPLETE_WITH_LIMITATIONS",
    "COMPLETED_WITH_LIMITATIONS",
}
_LIMITED_COMPLETION = {"COMPLETE_WITH_LIMITATIONS", "COMPLETED_WITH_LIMITATIONS"}
_SUCCESS_PROCESSING = {"COMPLETE", "COMPLETED", "COMPLETE_WITH_LIMITATIONS", "COMPLETED_WITH_LIMITATIONS"}
_SUCCESS_WORK_ITEM = {"SUCCESS", "NOT_APPLICABLE", "DISABLED"}
_RETRYABLE_WORK_ITEM = {
    "FAILED_RETRYABLE",
    "PENDING",
    "RUNNING",
    "WAITING_FOR_DATA",
    "NOT_CONFIGURED",
    "REQUESTED_NOT_EXECUTED",
}


def _table_exists(connection: sqlite3.Connection, table: str) -> bool:
    return connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (table,),
    ).fetchone() is not None


def _columns(connection: sqlite3.Connection, table: str) -> set[str]:
    if not _table_exists(connection, table):
        return set()
    return {
        str(row[1])
        for row in connection.execute(f'PRAGMA table_info("{table}")').fetchall()
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while True:
            block = stream.read(1024 * 1024)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def _live_source_fingerprint(database: Path) -> str:
    """Match report-catalog freshness semantics without mutating the AUD."""
    digest = hashlib.sha256()
    found = False
    for path in (database, database.with_name(database.name + "-wal")):
        if not path.is_file():
            continue
        found = True
        digest.update(path.name.encode("utf-8"))
        digest.update(b"\0")
        with path.open("rb") as stream:
            while True:
                block = stream.read(1024 * 1024)
                if not block:
                    break
                digest.update(block)
        digest.update(b"\0")
    if not found:
        raise FileNotFoundError(database)
    return digest.hexdigest()


def _logical_sqlite_digest(database: Path) -> str:
    """Hash logical SQLite contents so WAL/page-layout changes do not look like data changes."""
    connection = sqlite3.connect(
        f"file:{database.resolve().as_posix()}?mode=ro",
        uri=True,
        timeout=10.0,
    )
    try:
        digest = hashlib.sha256()
        tables = connection.execute(
            """SELECT name,COALESCE(sql,'') FROM sqlite_master
               WHERE type='table' AND name NOT LIKE 'sqlite_%'
               ORDER BY name"""
        ).fetchall()
        for table_name, schema_sql in tables:
            name = str(table_name)
            digest.update(name.encode("utf-8"))
            digest.update(b"\0")
            digest.update(str(schema_sql or "").encode("utf-8"))
            digest.update(b"\0")
            quoted = '"' + name.replace('"', '""') + '"'
            info = connection.execute(f"PRAGMA table_info({quoted})").fetchall()
            primary_key = sorted(
                (int(row[5]), str(row[1]))
                for row in info
                if int(row[5] or 0) > 0
            )
            order_by = (
                ",".join('"' + column.replace('"', '""') + '"' for _pos, column in primary_key)
                if primary_key
                else "rowid"
            )
            try:
                cursor = connection.execute(f"SELECT * FROM {quoted} ORDER BY {order_by}")
            except sqlite3.OperationalError:
                cursor = connection.execute(f"SELECT * FROM {quoted}")
            for row in cursor:
                values = []
                for value in row:
                    if value is None:
                        values.append(["null", None])
                    elif isinstance(value, bytes):
                        values.append(["bytes", value.hex()])
                    elif isinstance(value, float):
                        values.append(["float", repr(value)])
                    elif isinstance(value, int):
                        values.append(["int", value])
                    else:
                        values.append(["text", str(value)])
                digest.update(
                    json.dumps(
                        values,
                        ensure_ascii=False,
                        separators=(",", ":"),
                        sort_keys=False,
                    ).encode("utf-8")
                )
                digest.update(b"\0")
            digest.update(b"\xff")
        return digest.hexdigest()
    finally:
        connection.close()


def _report_catalog_freshness(database: Path) -> dict[str, Any]:
    """Describe whether a navigable report-catalog still represents the live AUD."""
    manifest_path = database.parent / "report-catalog" / "manifest.json"
    if not manifest_path.is_file():
        return {
            "report_catalog_present": False,
            "report_catalog_fresh": None,
            "report_catalog_state": "NOT_AVAILABLE",
        }
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {
            "report_catalog_present": True,
            "report_catalog_fresh": False,
            "report_catalog_state": "INVALID_MANIFEST",
        }
    if not isinstance(manifest, Mapping):
        return {
            "report_catalog_present": True,
            "report_catalog_fresh": False,
            "report_catalog_state": "INVALID_MANIFEST",
        }

    snapshot = manifest.get("audit_snapshot")
    logical_expected = (
        str(snapshot.get("source_logical_sha256") or snapshot.get("logical_sha256") or "")
        if isinstance(snapshot, Mapping)
        else ""
    )
    if logical_expected:
        try:
            logical_current = _logical_sqlite_digest(database)
        except (OSError, sqlite3.Error):
            return {
                "report_catalog_present": True,
                "report_catalog_fresh": False,
                "report_catalog_state": "FRESHNESS_NOT_PROVEN",
                "report_catalog_freshness_basis": "LOGICAL_SQLITE",
            }
        fresh = logical_current == logical_expected
        return {
            "report_catalog_present": True,
            "report_catalog_fresh": fresh,
            "report_catalog_state": "FRESH" if fresh else "STALE",
            "report_catalog_freshness_basis": "LOGICAL_SQLITE",
        }

    expected = str(manifest.get("source_fingerprint") or "")
    if not expected:
        return {
            "report_catalog_present": True,
            "report_catalog_fresh": False,
            "report_catalog_state": "FRESHNESS_NOT_PROVEN",
            "report_catalog_freshness_basis": "NONE",
        }
    try:
        current = _live_source_fingerprint(database)
    except OSError:
        return {
            "report_catalog_present": True,
            "report_catalog_fresh": False,
            "report_catalog_state": "FRESHNESS_NOT_PROVEN",
            "report_catalog_freshness_basis": "PHYSICAL_FALLBACK",
        }
    fresh = current == expected
    return {
        "report_catalog_present": True,
        "report_catalog_fresh": fresh,
        "report_catalog_state": "FRESH" if fresh else "STALE",
        "report_catalog_freshness_basis": "PHYSICAL_FALLBACK",
    }


def _parse_timestamp(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _source_revision_state(database: Path, audit_id: str, observation_at: str) -> dict[str, Any]:
    """Materialize immutable revision identity and post-observation RPR provenance."""
    logical_sha = _logical_sqlite_digest(database)
    state: dict[str, Any] = {
        "source_revision_id": f"REV-{logical_sha[:24].upper()}",
        "source_revision_logical_sha256": logical_sha,
        "observation_at": str(observation_at or ""),
        "revision_at": str(observation_at or ""),
        "revision_mode": "NONE",
        "reprocess_count_after_observation": 0,
        "post_observation_revision": False,
    }
    connection = sqlite3.connect(
        f"file:{database.resolve().as_posix()}?mode=ro",
        uri=True,
        timeout=2.0,
    )
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")
    try:
        if not _table_exists(connection, "audit_reprocess_runs"):
            return state
        run_columns = _columns(connection, "audit_reprocess_runs")
        if not {"reprocess_id", "audit_id", "completed_at"}.issubset(run_columns):
            return state
        material_filter = " AND successful_items>0" if "successful_items" in run_columns else ""
        runs = connection.execute(
            """SELECT reprocess_id,completed_at
               FROM audit_reprocess_runs
               WHERE audit_id=? AND completed_at IS NOT NULL"""
            + material_filter
            + " ORDER BY completed_at,reprocess_id",
            (audit_id,),
        ).fetchall()
        observation_dt = _parse_timestamp(observation_at)
        post_runs = [
            row for row in runs
            if observation_dt is not None
            and (completed := _parse_timestamp(row["completed_at"])) is not None
            and completed > observation_dt
        ]
        if not post_runs:
            return state

        modes: set[str] = set()
        if (
            _table_exists(connection, "audit_fulfillment_attempts")
            and _table_exists(connection, "audit_fulfillment_work_items")
            and "reprocess_id" in _columns(connection, "audit_fulfillment_attempts")
            and "work_item_id" in _columns(connection, "audit_fulfillment_attempts")
            and "temporal_mode" in _columns(connection, "audit_fulfillment_work_items")
        ):
            for row in post_runs:
                for mode_row in connection.execute(
                    """SELECT DISTINCT UPPER(COALESCE(w.temporal_mode,''))
                       FROM audit_fulfillment_attempts a
                       JOIN audit_fulfillment_work_items w
                         ON w.work_item_id=a.work_item_id AND w.audit_id=a.audit_id
                       WHERE a.audit_id=? AND a.reprocess_id=?""",
                    (audit_id, str(row["reprocess_id"] or "")),
                ).fetchall():
                    mode = str(mode_row[0] or "").upper()
                    if mode:
                        modes.add(mode)

        if "LIVE_RECOLLECTION" in modes:
            revision_mode = "LIVE_RECOLLECTION"
        elif modes and modes <= {"REPLAY_SAFE"}:
            revision_mode = "REPLAY_SAFE"
        elif "REPLAY_SAFE" in modes:
            revision_mode = "REPLAY_SAFE"
        else:
            revision_mode = "UNKNOWN"

        state.update({
            "revision_at": str(post_runs[-1]["completed_at"] or ""),
            "revision_mode": revision_mode,
            "reprocess_count_after_observation": len(post_runs),
            "post_observation_revision": True,
        })
        return state
    finally:
        connection.close()


def _sqlite_integrity(path: Path) -> dict[str, Any]:
    database_hash = _sha256(path)
    wal = Path(str(path) + "-wal")
    wal_hash = _sha256(wal) if wal.is_file() else None
    material = f"audit.db:{database_hash}|audit.db-wal:{wal_hash or '-'}"
    return {
        "source_sha256": database_hash,
        "wal_present": wal_hash is not None,
        "wal_sha256": wal_hash,
        "source_integrity_sha256": hashlib.sha256(material.encode("utf-8")).hexdigest(),
    }


def _db_path(root: Path, row: Mapping[str, Any]) -> Path:
    raw = Path(str(row.get("db_path") or ""))
    return raw if raw.is_absolute() else root / raw


def _read_health(path: Path, audit_id: str) -> dict[str, Any]:
    connection = sqlite3.connect(
        f"file:{path.resolve().as_posix()}?mode=ro",
        uri=True,
        timeout=2.0,
    )
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")
    try:
        audit_status = "UNKNOWN"
        completion_status: str | None = None
        audit_limitations: list[str] = []
        if {"audit_id", "status"} <= _columns(connection, "audits"):
            selected = ["status"]
            audit_columns = _columns(connection, "audits")
            if "completion_status" in audit_columns:
                selected.append("completion_status")
            if "limitations" in audit_columns:
                selected.append("limitations")
            row = connection.execute(
                f"SELECT {','.join(selected)} FROM audits WHERE audit_id=?",
                (audit_id,),
            ).fetchone()
            if row is not None:
                audit_status = str(row["status"] or "UNKNOWN").upper()
                if "completion_status" in row.keys():
                    completion_status = str(row["completion_status"] or "").upper() or None
                if "limitations" in row.keys() and row["limitations"] not in (None, ""):
                    try:
                        parsed = json.loads(str(row["limitations"]))
                    except (TypeError, ValueError, json.JSONDecodeError):
                        parsed = [str(row["limitations"])]
                    if isinstance(parsed, list):
                        audit_limitations = [str(item) for item in parsed if str(item).strip()]
                    elif str(parsed).strip():
                        audit_limitations = [str(parsed)]

        contract: dict[str, Any] | None = None
        if _table_exists(connection, "audit_fulfillment_contracts"):
            row = connection.execute(
                """SELECT processing_status,score_status,report_status,consolidation_eligible,
                          temporal_status,required_items,successful_items,pending_items,
                          blocked_items,expired_items,total_attempts,reprocess_count,completed_at
                   FROM audit_fulfillment_contracts WHERE audit_id=?""",
                (audit_id,),
            ).fetchone()
            if row is not None:
                contract = {key: row[key] for key in row.keys()}

        required_issues: list[dict[str, Any]] = []
        if _table_exists(connection, "audit_fulfillment_work_items"):
            rows = connection.execute(
                """SELECT component,scope_key,status,attempt_count,retryable,
                          last_error_class,last_error_code,last_error_message
                   FROM audit_fulfillment_work_items
                   WHERE audit_id=? AND required=1
                   ORDER BY component,scope_key""",
                (audit_id,),
            ).fetchall()
            for row in rows:
                status = str(row["status"] or "UNKNOWN").upper()
                if status in _SUCCESS_WORK_ITEM:
                    continue
                required_issues.append({
                    "component": str(row["component"] or ""),
                    "scope_key": str(row["scope_key"] or "AUDIT"),
                    "status": status,
                    "attempt_count": int(row["attempt_count"] or 0),
                    "retryable": bool(row["retryable"]),
                    "last_error_class": row["last_error_class"],
                    "last_error_code": row["last_error_code"],
                    "last_error_message": row["last_error_message"],
                })

        contract_present = contract is not None
        processing = str((contract or {}).get("processing_status") or "").upper()
        score_status = str((contract or {}).get("score_status") or "").upper()
        report_status = str((contract or {}).get("report_status") or "").upper()
        eligible = bool((contract or {}).get("consolidation_eligible"))
        pending = int((contract or {}).get("pending_items") or 0)
        blocked = int((contract or {}).get("blocked_items") or 0)
        expired = int((contract or {}).get("expired_items") or 0)

        proven_complete = (
            audit_status == "COMPLETED"
            and completion_status in _SUCCESS_COMPLETION
            and contract_present
            and processing in _SUCCESS_PROCESSING
            and score_status == "FINAL"
            and report_status == "FINAL"
            and eligible
            and pending == 0
            and blocked == 0
            and expired == 0
            and not required_issues
        )
        retry_recommended = any(
            item["status"] in _RETRYABLE_WORK_ITEM or bool(item["retryable"])
            for item in required_issues
        ) or processing == "PARTIAL_RETRYABLE"

        limited = completion_status in _LIMITED_COMPLETION or bool(audit_limitations)
        if proven_complete and limited:
            state = "SUCCESS_WITH_LIMITATIONS"
            label = "Concluída com limitações não bloqueantes"
        elif proven_complete:
            state = "SUCCESS"
            label = "Concluída e comprovada"
        elif retry_recommended:
            state = "REPROCESS_REQUIRED"
            label = "Reprocessamento recomendado"
        elif not contract_present:
            state = "NOT_PROVEN"
            label = "Conclusão não comprovada"
        else:
            state = "INCOMPLETE"
            label = "Concluída com pendências"

        return {
            "audit_id": audit_id,
            "audit_status": audit_status,
            "completion_status": completion_status,
            "fulfillment_contract_present": contract_present,
            "fulfillment": contract,
            "required_issues": required_issues,
            "source_limitations": audit_limitations,
            "source_state": state,
            "source_state_label": label,
            "conclusive": proven_complete,
            "reprocess_recommended": retry_recommended,
        }
    finally:
        connection.close()


def build_source_governance(
    audits_root: str | Path,
    rows: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    root = Path(audits_root)
    audits: list[dict[str, Any]] = []
    for source in rows:
        audit_id = str(source.get("audit_id") or "")
        path = _db_path(root, source)
        stat = path.stat()
        item = _read_health(path, audit_id)
        event_time = str(source.get("event_time") or "")
        item.update({
            "db_path": str(source.get("db_path") or ""),
            **_sqlite_integrity(path),
            **_report_catalog_freshness(path),
            **_source_revision_state(path, audit_id, event_time),
            "source_size_bytes": int(stat.st_size),
            "event_time": event_time,
        })
        audits.append(redact_value(item))

    ordered = sorted(
        audits,
        key=lambda item: (str(item.get("event_time") or ""), str(item.get("audit_id") or "")),
    )
    temporal_overlaps: list[dict[str, Any]] = []
    for item in audits:
        item["temporal_revision_overlap"] = False
        item["temporal_revision_overlap_with"] = None
        item["temporal_revision_overlap_state"] = "NONE"
    for index, item in enumerate(ordered[:-1]):
        next_item = ordered[index + 1]
        revision_at = _parse_timestamp(item.get("revision_at"))
        next_observation = _parse_timestamp(next_item.get("event_time"))
        if (
            item.get("post_observation_revision") is True
            and revision_at is not None
            and next_observation is not None
            and revision_at > next_observation
        ):
            mode = str(item.get("revision_mode") or "UNKNOWN").upper()
            overlap_state = (
                "LIVE_RECOLLECTION_AFTER_NEXT_OBSERVATION"
                if mode == "LIVE_RECOLLECTION"
                else "REPLAY_SAFE_AFTER_NEXT_OBSERVATION"
                if mode == "REPLAY_SAFE"
                else "UNKNOWN_REVISION_AFTER_NEXT_OBSERVATION"
            )
            item["temporal_revision_overlap"] = True
            item["temporal_revision_overlap_with"] = str(next_item.get("audit_id") or "")
            item["temporal_revision_overlap_state"] = overlap_state
            temporal_overlaps.append({
                "audit_id": str(item.get("audit_id") or ""),
                "source_revision_id": str(item.get("source_revision_id") or ""),
                "observation_at": str(item.get("observation_at") or item.get("event_time") or ""),
                "revision_at": str(item.get("revision_at") or ""),
                "revision_mode": mode,
                "next_audit_id": str(next_item.get("audit_id") or ""),
                "next_observation_at": str(next_item.get("event_time") or ""),
                "state": overlap_state,
            })

    non_conclusive = [item for item in audits if not item["conclusive"]]
    limited = [item for item in audits if item["conclusive"] and item["source_state"] == "SUCCESS_WITH_LIMITATIONS"]
    reprocess = [item["audit_id"] for item in audits if item["reprocess_recommended"]]
    if non_conclusive:
        conclusion_state = "NON_CONCLUSIVE"
        conclusion_label = "Série não conclusiva"
    elif limited:
        conclusion_state = "CONCLUSIVE_WITH_LIMITATIONS"
        conclusion_label = "Série conclusiva com limitações"
    else:
        conclusion_state = "CONCLUSIVE"
        conclusion_label = "Série conclusiva"

    return {
        "contract": GOVERNANCE_CONTRACT,
        "conclusion_state": conclusion_state,
        "conclusion_label": conclusion_label,
        "audit_count": len(audits),
        "conclusive_audits": len(audits) - len(non_conclusive),
        "non_conclusive_audits": len(non_conclusive),
        "limited_audits": len(limited),
        "reprocess_recommended_audit_ids": reprocess,
        "temporal_revision_overlap_count": len(temporal_overlaps),
        "temporal_revision_overlaps": temporal_overlaps,
        "temporal_revision_policy": {
            "REPLAY_SAFE_AFTER_NEXT_OBSERVATION": (
                "comparação contextual permitida; a revisão reutiliza evidência persistida da observação original"
            ),
            "LIVE_RECOLLECTION_AFTER_NEXT_OBSERVATION": (
                "comparação temporal direta não deve ser tratada como repetição do estado original sem qualificação"
            ),
            "UNKNOWN_REVISION_AFTER_NEXT_OBSERVATION": (
                "comparação exige revisão manual porque o modo temporal do RPR não foi comprovado"
            ),
        },
        "audits": audits,
        "interpretation_rule": (
            "Somente AUD fonte não final, não elegível ou com requisito obrigatório pendente torna a série não conclusiva. "
            "COMPLETE_WITH_LIMITATIONS permanece final quando fulfillment, score e relatório são finais e não há pendência obrigatória; "
            "as limitações devem ser explicitadas sem recomendar reprocessamento quando não existe trabalho pendente."
        ),
    }


__all__ = ["GOVERNANCE_CONTRACT", "build_source_governance"]
