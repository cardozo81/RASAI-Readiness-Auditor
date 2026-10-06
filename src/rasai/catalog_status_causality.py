"""Deterministic causal read model for non-integral catalog states.

Report-only: reads persisted state/evidence; never collects, retries, calls AI,
changes fulfillment, or changes scoring.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
import sqlite3
from typing import Any, Mapping, Sequence
import unicodedata

from rasai.observability.store import observability_database_path


_SUCCESS = {"SUCCESS", "SUCCEEDED", "COMPLETE", "COMPLETED"}
_RETRYABLE_FAILURE = {"FAILED_RETRYABLE"}
_TERMINAL_FAILURE = {"FAILED_TERMINAL", "FAILED_PERMANENT"}
_BLOCKED = {"BLOCKED"}
_PENDING = {
    "REQUESTED", "REQUESTED_NOT_EXECUTED", "PENDING", "WAITING_FOR_DATA",
    "RUNNING", "IN_PROGRESS", "PARTIAL",
}


@dataclass(frozen=True, slots=True)
class CatalogStatusCause:
    catalog_id: str
    effective_status: str
    cause_code: str
    cause_class: str
    technical_explanation: str
    business_explanation: str
    retryable: bool
    terminal: bool
    evidence_references: tuple[str, ...]


def normalize_catalog_status(value: Any) -> str:
    """Normalize public/technical catalog states without losing accented letters."""
    decomposed = unicodedata.normalize("NFKD", str(value or ""))
    folded = "".join(char for char in decomposed if not unicodedata.combining(char))
    return re.sub(r"[^A-Z0-9]+", "_", folded.upper()).strip("_")


def _norm(value: Any) -> str:
    return normalize_catalog_status(value)


def _safe_json(value: Any, default: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    if value in (None, ""):
        return default
    try:
        return json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return default


def _table_exists(connection: sqlite3.Connection, table: str) -> bool:
    return connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone() is not None


def _columns(connection: sqlite3.Connection, table: str) -> set[str]:
    if not _table_exists(connection, table):
        return set()
    return {str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})")}


def _bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    try:
        return bool(int(value))
    except (TypeError, ValueError):
        return str(value).strip().casefold() in {"true", "yes", "on", "sim"}


def _safe_code(value: Any) -> str:
    text = str(value or "").strip()
    if not text or len(text) > 96:
        return ""
    return text if re.fullmatch(r"[A-Za-z0-9_.:-]+", text) else ""


def _work_item_causes(
    catalog_id: str,
    effective_status: str,
    work_items: Sequence[Mapping[str, Any]],
) -> list[CatalogStatusCause]:
    out: list[CatalogStatusCause] = []
    for item in work_items:
        state = _norm(item.get("status"))
        if not state or state in _SUCCESS:
            continue
        component = _norm(item.get("component")) or "COMPONENT"
        scope = str(item.get("scope_key") or "default")
        code = _safe_code(item.get("last_error_code"))
        error_class = _safe_code(item.get("last_error_class"))
        detail = ""
        if code:
            detail += f"; código={code}"
        if error_class:
            detail += f"; classe={error_class}"
        refs = (f"work-item:{component}:{scope}",)

        if state in _RETRYABLE_FAILURE:
            out.append(CatalogStatusCause(
                catalog_id, effective_status, f"{component}_FAILED_RETRYABLE",
                "EXECUTION_FAILURE",
                f"{component} está persistido como FAILED_RETRYABLE{detail}.",
                "O resultado deste componente não é integral; existe caminho de nova tentativa sem atribuir a causa ao site por inferência.",
                _bool(item.get("retryable"), True), False, refs,
            ))
        elif state in _TERMINAL_FAILURE:
            out.append(CatalogStatusCause(
                catalog_id, effective_status, f"{component}_{state}",
                "EXECUTION_FAILURE",
                f"{component} está persistido como {state}{detail}.",
                "A execução terminou sem resultado integral e o estado persistido não autoriza retry automático.",
                False, True, refs,
            ))
        elif state in _BLOCKED:
            out.append(CatalogStatusCause(
                catalog_id, effective_status, f"{component}_BLOCKED",
                "DEPENDENCY_BLOCK",
                f"{component} está persistido como BLOCKED{detail}.",
                "O catálogo depende de uma condição ainda não satisfeita; bloqueio não é evidência de defeito no site.",
                _bool(item.get("retryable"), False), False, refs,
            ))
        elif state in _PENDING:
            out.append(CatalogStatusCause(
                catalog_id, effective_status, f"{component}_{state}",
                "EXECUTION_INCOMPLETE",
                f"{component} está persistido como {state}{detail}.",
                "A etapa foi solicitada, mas ainda não possui resultado integral persistido.",
                _bool(item.get("retryable"), True), False, refs,
            ))
    return out


def _common_crawl_messages(database: Path) -> tuple[list[str], tuple[str, ...]]:
    obs_path = observability_database_path(database.parent)
    if not obs_path.is_file():
        return [], ()
    con = sqlite3.connect(obs_path)
    con.row_factory = sqlite3.Row
    try:
        if not _table_exists(con, "datasets"):
            return [], ()
        cols = _columns(con, "datasets")
        if "source_type" not in cols:
            return [], ()
        rows = list(con.execute(
            "SELECT * FROM datasets WHERE source_type='COMMON_CRAWL_CDX_HISTORY' ORDER BY rowid"
        ))
    finally:
        con.close()

    messages: list[str] = []
    refs: list[str] = []
    for raw_row in rows:
        row = dict(raw_row)
        metadata = _safe_json(row.get("metadata"), {})
        if isinstance(metadata, Mapping) and int(metadata.get("errors") or 0) > 0:
            messages.append(f"dataset errors={int(metadata.get('errors') or 0)}")
        artifact = str(row.get("artifact_path") or "").strip().replace("\\", "/")
        if not artifact:
            continue
        candidate = (database.parent / artifact).resolve()
        try:
            candidate.relative_to(database.parent.resolve())
        except ValueError:
            continue
        if not candidate.is_file() or candidate.suffix.casefold() != ".json":
            continue
        refs.append(f"artifact:{artifact}")
        try:
            payload = json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        if not isinstance(payload, Mapping):
            continue
        details = payload.get("error_details")
        if isinstance(details, list):
            for item in details:
                if not isinstance(item, Mapping):
                    continue
                for key in ("error_type", "message"):
                    value = str(item.get(key) or "").strip()
                    if value:
                        messages.append(value)
        legacy = payload.get("errors")
        if isinstance(legacy, list):
            messages.extend(str(value) for value in legacy if str(value).strip())
    return messages, tuple(dict.fromkeys(refs))


def _common_crawl_cause(
    database: Path,
    audit_id: str,
    effective_status: str,
) -> CatalogStatusCause | None:
    con = sqlite3.connect(database)
    con.row_factory = sqlite3.Row
    try:
        if not _table_exists(con, "standards_service_runs"):
            return None
        cols = _columns(con, "standards_service_runs")
        required = {"audit_id", "service_id", "requested", "effective_enabled", "state"}
        if not required.issubset(cols):
            return None
        row = con.execute(
            "SELECT * FROM standards_service_runs "
            "WHERE audit_id=? AND service_id='common-crawl' ORDER BY rowid DESC LIMIT 1",
            (audit_id,),
        ).fetchone()
    finally:
        con.close()

    if row is None or not _bool(row["requested"]) or not _bool(row["effective_enabled"]):
        return None
    state = _norm(row["state"])
    messages, artifact_refs = _common_crawl_messages(database)
    joined = " | ".join(messages)
    details = _safe_json(row["details_json"] if "details_json" in row.keys() else None, {})
    reason = _safe_code(details.get("reason") if isinstance(details, Mapping) else None)
    evidence = tuple(dict.fromkeys(("standards-service:common-crawl", *artifact_refs)))

    if re.search(r"\bHTTP\s+5\d\d\b", joined, re.I):
        return CatalogStatusCause(
            "CAT-05", effective_status, "COMMON_CRAWL_PROVIDER_5XX",
            "EXTERNAL_INTEGRATION",
            "O endpoint do Common Crawl respondeu HTTP 5xx durante a integração persistida.",
            "A indisponibilidade é externa ao site auditado; não deve ser apresentada como defeito do site.",
            True, False, evidence,
        )
    if re.search(r"\btimeout\b|timed\s*out", joined, re.I):
        return CatalogStatusCause(
            "CAT-05", effective_status, "COMMON_CRAWL_PROVIDER_TIMEOUT",
            "EXTERNAL_INTEGRATION",
            "A integração persistida do Common Crawl terminou por timeout.",
            "A indisponibilidade é externa ao site auditado e pode ser reprocessada sem alterar a URL auditada.",
            True, False, evidence,
        )
    if state in {"ERROR", "FAILED_RETRYABLE", "FAILED_PERMANENT", "BLOCKED", "NO_DATA"}:
        return CatalogStatusCause(
            "CAT-05", effective_status, reason or f"COMMON_CRAWL_{state}",
            "EXTERNAL_INTEGRATION",
            f"Common Crawl terminou com estado persistido {state}"
            + (f" e razão {reason}" if reason else "") + ".",
            "A fonte externa não produziu resultado integral; isso não comprova falha do site.",
            state != "FAILED_PERMANENT", state == "FAILED_PERMANENT", evidence,
        )
    return None


def _serp_terminal_causes(
    database: Path,
    audit_id: str,
    effective_status: str,
) -> list[CatalogStatusCause]:
    con = sqlite3.connect(database)
    con.row_factory = sqlite3.Row
    try:
        if not _table_exists(con, "serp_observations"):
            return []
        cols = _columns(con, "serp_observations")
        if not {"audit_id", "quality_metadata"}.issubset(cols):
            return []
        rows = list(con.execute(
            "SELECT * FROM serp_observations WHERE audit_id=? ORDER BY rowid", (audit_id,)
        ))
    finally:
        con.close()

    out: list[CatalogStatusCause] = []
    for raw_row in rows:
        row = dict(raw_row)
        quality = _safe_json(row.get("quality_metadata"), {})
        if not isinstance(quality, Mapping):
            continue
        if not (
            quality.get("requested_depth_complete") is False
            and quality.get("pagination_ended_before_requested_depth") is True
            and quality.get("request_budget_ended_before_requested_depth") is not True
            and quality.get("normalization_incomplete_for_requested_depth") is not True
            and not quality.get("error_code")
            and not quality.get("error_message")
            and _norm(row.get("observation_status") or "OBSERVED") == "OBSERVED"
        ):
            continue
        requested = row.get("requested_depth")
        observed = quality.get("observed_position_count")
        if observed in (None, ""):
            observed = quality.get("observed_position_ceiling")
        requested_text = str(requested) if requested not in (None, "") else "?"
        observed_text = str(observed) if observed not in (None, "") else "?"
        oid = str(row.get("observation_id") or "unknown")
        out.append(CatalogStatusCause(
            "CAT-05", effective_status, "SERP_TERMINAL_LIMITED",
            "COVERAGE_LIMITATION",
            f"A SERP persistida observou {observed_text} de {requested_text} posições solicitadas e o provedor encerrou naturalmente a paginação.",
            "A cobertura termina na profundidade observada; posições posteriores não foram observadas e não podem ser tratadas como ausência do domínio.",
            False, True, (f"serp-observation:{oid}",),
        ))
    return out


def explain_catalog_status(
    database: Path,
    data: Any,
    catalog_id: str,
    *,
    effective_status: str,
    work_items: Sequence[Mapping[str, Any]] = (),
) -> tuple[CatalogStatusCause, ...]:
    """Derive causal explanation only from persisted state/evidence."""
    if _norm(effective_status) in {"CONCLUIDO", "NAO_SOLICITADO"}:
        return ()

    causes: list[CatalogStatusCause] = []
    if catalog_id == "CAT-05":
        common_crawl = _common_crawl_cause(database, data.audit_id, effective_status)
        if common_crawl is not None:
            causes.append(common_crawl)
        causes.extend(_serp_terminal_causes(database, data.audit_id, effective_status))
    causes.extend(_work_item_causes(catalog_id, effective_status, work_items))

    deduped: list[CatalogStatusCause] = []
    seen: set[tuple[str, tuple[str, ...]]] = set()
    for cause in causes:
        key = (cause.cause_code, cause.evidence_references)
        if key not in seen:
            seen.add(key)
            deduped.append(cause)
    return tuple(deduped)
