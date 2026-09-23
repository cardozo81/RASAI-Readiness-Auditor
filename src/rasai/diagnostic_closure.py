"""Current diagnostic-closure projection derived from durable fulfillment state.

This module never mutates audit evidence.  It separates package/data integrity from
diagnostic completeness and intentionally derives the visible warning from the current
effective work-item state, while historical attempts remain in provenance tables.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sqlite3
from typing import Any, Mapping



_RESOLVED = frozenset({"SUCCESS", "DISABLED", "NOT_APPLICABLE"})
_SOURCE_PARTIAL_STATES = frozenset(
    {
        "PENDING",
        "RUNNING",
        "WAITING_FOR_DATA",
        "FAILED_RETRYABLE",
        "NOT_CONFIGURED",
        "REQUESTED_NOT_EXECUTED",
    }
)
_AI_COMPONENTS = frozenset(
    {
        "SEMANTIC_AI",
        "TECHNICAL_AI",
        "CONTENT_REMEDIATION_AI",
        "IMPROVEMENT_INTELLIGENCE",
        "COMPETITIVE_INTELLIGENCE",
    }
)
_COMPONENTS: dict[str, tuple[str, str, str]] = {
    "SEMANTIC_AI": ("CAT-03", "Análise semântica por IA", "IA"),
    "WEB_PERFORMANCE": ("CAT-04", "Web Performance / PageSpeed", "API/integração"),
    "SEARCH_INTELLIGENCE": ("CAT-05", "Search Intelligence / SERP", "API/integração"),
    "GOOGLE_SEARCH_CONSOLE": ("CAT-05", "Google Search Console", "API/integração"),
    "SYNTHETIC_APDEX": ("CAT-06", "Apdex de navegação", "Coleta"),
    "EXPERIENCE_APDEX": ("CAT-07", "Apdex de experiência", "Coleta"),
    "IMPROVEMENT_INTELLIGENCE": ("CAT-08", "Análise profunda por IA", "IA"),
    "CONTENT_REMEDIATION_AI": ("CAT-09", "Enriquecimento de remediação por IA", "IA"),
    "TECHNICAL_AI": ("CAT-09", "Análise técnica por IA", "IA"),
    "PASSIVE_SECURITY": ("CAT-10", "Segurança passiva", "Integração/análise"),
    "HTTP_ACQUISITION": ("CAT-01", "Aquisição HTTP", "Coleta"),
    "RENDER_CAPTURE": ("CAT-01", "Captura renderizada", "Coleta"),
    "CONTENT_EXTRACTION": ("CAT-03", "Extração de conteúdo", "Coleta"),
}


@dataclass(frozen=True, slots=True)
class DiagnosticPending:
    component: str
    scope_key: str
    catalog_id: str
    integration: str
    kind: str
    state: str
    reason: str
    required_to_close: bool = True


def _component_meta(component: str) -> tuple[str, str, str]:
    key = str(component or "").strip().upper()
    if key in _COMPONENTS:
        return _COMPONENTS[key]
    label = key.replace("_", " ").title() or "Etapa técnica"
    return ("-", label, "Etapa")


def _field(item: Any, name: str, default: Any = "") -> Any:
    if isinstance(item, Mapping):
        return item.get(name, default)
    try:
        keys = item.keys()
    except (AttributeError, TypeError):
        return getattr(item, name, default)
    if name in keys:
        try:
            return item[name]
        except (IndexError, KeyError, TypeError):
            return default
    return getattr(item, name, default)


def _reason(item: Any) -> str:
    message = str(_field(item, "last_error_message", "") or "").strip()
    code = str(_field(item, "last_error_code", "") or "").strip()
    if message and code and message != code:
        return f"{message} ({code})"
    return message or code or "requisito necessário ainda não concluído"


def _state(item: Any) -> str:
    component = str(_field(item, "component", "") or "").upper()
    status = str(_field(item, "status", "") or "").upper()
    error_class = str(_field(item, "last_error_class", "") or "").upper()
    code = str(_field(item, "last_error_code", "") or "").upper()
    ai = component in _AI_COMPONENTS
    if status == "WAITING_FOR_DATA" or error_class == "PREREQUISITE":
        return "Não executada - pré-requisitos incompletos" if ai else "Aguardando pré-requisito"
    if ai and (
        error_class == "CONFIGURATION"
        or "NOT_CONFIGURED" in code
        or "PROVIDER_NONE" in code
        or "AI_DISABLED" in code
    ):
        return "Não executada - IA não configurada/disponível"
    if ai and status in {"FAILED_RETRYABLE", "FAILED_PERMANENT", "BLOCKED"}:
        return "Solicitada - provider/execução não concluiu"
    labels = {
        "PENDING": "Pendente",
        "RUNNING": "Em processamento",
        "FAILED_RETRYABLE": "Falha temporária - reprocessável",
        "FAILED_PERMANENT": "Falha definitiva",
        "BLOCKED": "Bloqueada",
        "NOT_CONFIGURED": "Não configurada",
        "REQUESTED_NOT_EXECUTED": "Solicitada - não executada",
    }
    return labels.get(status, status.replace("_", " ").title() or "Pendente")


def current_pending(workspace: Any, audit_id: str) -> tuple[DiagnosticPending, ...]:
    """Read current required gaps without mutating the source audit database."""
    path = Path(getattr(workspace, "database", workspace))
    if not path.is_file():
        return ()
    try:
        connection = sqlite3.connect(
            f"file:{path.resolve().as_posix()}?mode=ro",
            uri=True,
            timeout=2.0,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only = ON")
        try:
            exists = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='audit_fulfillment_work_items'"
            ).fetchone()
            if not exists:
                return ()
            persisted = connection.execute(
                """SELECT component,scope_key,status,last_error_class,last_error_code,
                          last_error_message
                   FROM audit_fulfillment_work_items
                   WHERE audit_id=? AND required=1
                     AND status NOT IN ('SUCCESS','DISABLED','NOT_APPLICABLE')
                   ORDER BY component,scope_key""",
                (audit_id,),
            ).fetchall()
        finally:
            connection.close()
    except (OSError, sqlite3.Error, ValueError):
        return ()

    rows: list[DiagnosticPending] = []
    for item in persisted:
        component = str(item["component"] or "").upper()
        catalog_id, integration, kind = _component_meta(component)
        rows.append(
            DiagnosticPending(
                component=component,
                scope_key=str(item["scope_key"] or "AUDIT"),
                catalog_id=catalog_id,
                integration=integration,
                kind=kind,
                state=_state(item),
                reason=_reason(item),
            )
        )
    rows.sort(key=lambda row: (row.catalog_id, row.component, row.scope_key))
    return tuple(rows)


def diagnostic_complete(workspace: Any, audit_id: str) -> bool:
    return not current_pending(workspace, audit_id)


def source_usable_for_consolidation(database: str | Path, audit_id: str) -> bool:
    """Accept an intact partial AUD as a non-conclusive source, never a corrupt one.

    This function is strictly read-only. It must not call fulfillment helpers that
    defensively create/upgrade schema on the source AUD.
    """
    path = Path(database)
    if not path.is_file():
        return False
    try:
        connection = sqlite3.connect(
            f"file:{path.resolve().as_posix()}?mode=ro",
            uri=True,
            timeout=2.0,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only = ON")
        try:
            quick = connection.execute("PRAGMA quick_check").fetchone()
            if not quick or str(quick[0]).casefold() != "ok":
                return False

            audit = connection.execute(
                "SELECT status FROM audits WHERE audit_id=?",
                (audit_id,),
            ).fetchone()
            if audit is None or str(audit["status"] or "").upper() != "COMPLETED":
                return False

            contract_exists = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='audit_fulfillment_contracts'"
            ).fetchone()
            work_exists = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='audit_fulfillment_work_items'"
            ).fetchone()

            # AUDs created before the fulfillment extension remain governed by the
            # immutable consolidation reader/index integrity checks. Do not create the
            # extension here merely to decide source usability.
            if not contract_exists:
                return True

            contract = connection.execute(
                """SELECT processing_status,consolidation_eligible
                   FROM audit_fulfillment_contracts WHERE audit_id=?""",
                (audit_id,),
            ).fetchone()
            if contract is None:
                return False
            if str(contract["processing_status"] or "").upper() == "FAILED_FATAL":
                return False
            if bool(contract["consolidation_eligible"]):
                return True
            if not work_exists:
                return False

            pending = connection.execute(
                """SELECT status,retryable FROM audit_fulfillment_work_items
                   WHERE audit_id=? AND required=1
                     AND status NOT IN ('SUCCESS','DISABLED','NOT_APPLICABLE')""",
                (audit_id,),
            ).fetchall()
        finally:
            connection.close()
    except (OSError, sqlite3.Error, ValueError):
        return False

    if not pending:
        return False
    return all(
        str(row["status"] or "").upper() in _SOURCE_PARTIAL_STATES
        and bool(row["retryable"])
        for row in pending
    )


__all__ = [
    "DiagnosticPending",
    "current_pending",
    "diagnostic_complete",
    "source_usable_for_consolidation",
]
