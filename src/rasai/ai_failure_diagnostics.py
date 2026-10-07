"""Human-readable diagnostics for persisted AI provider attempts.

This module only reads structured telemetry already stored in audit.db. It does not
perform provider calls and intentionally avoids raw payloads, headers and secrets.
"""
from __future__ import annotations

from pathlib import Path
import sqlite3
from typing import Any, Mapping

from rasai.catalog_report_public_labels import public_label


_ERROR_LABELS = {
    "TIMEOUT_ERROR": "Tempo limite excedido",
    "NETWORK_ERROR": "Falha de rede",
    "SERVER_ERROR": "Erro temporário do servidor",
    "RATE_LIMIT_ERROR": "Limite de requisições do provider",
    "AUTHENTICATION_ERROR": "Falha de autenticação",
    "AUTHORIZATION_ERROR": "Falha de autorização",
    "QUOTA_ERROR": "Quota ou crédito indisponível",
    "CONTRACT_ERROR": "Resposta incompatível com o contrato",
    "CONTENT_POLICY_ERROR": "Resposta bloqueada por política do provider",
    "CLIENT_ERROR": "Erro de requisição ao provider",
    "UNKNOWN_ERROR": "Erro técnico não classificado",
}
_SUCCESS = {"SUCCESS", "COMPLETE", "COMPLETED"}
_TRANSIENT = {
    "TIMEOUT_ERROR",
    "NETWORK_ERROR",
    "SERVER_ERROR",
    "RATE_LIMIT_ERROR",
}
_CONFIGURATION = {
    "AUTHENTICATION_ERROR",
    "AUTHORIZATION_ERROR",
    "QUOTA_ERROR",
}


def format_ai_attempt_diagnostic(attempt: Mapping[str, Any]) -> str:
    """Return a bounded human-readable diagnosis from structured attempt fields."""
    status = str(attempt.get("status") or "").upper()
    if status in _SUCCESS:
        return "-"

    error_class = str(attempt.get("error_class") or "").upper().strip()
    error_code = str(attempt.get("error_code") or "").strip()
    error_type = str(attempt.get("error_type") or "").strip()
    error_detail = str(attempt.get("error_detail") or "").strip()
    http_status = attempt.get("http_status")

    parts: list[str] = []
    if error_class == "UNKNOWN_PROVIDER_ERROR" and error_detail:
        # A classe técnica continua UNKNOWN para retry/quarentena, mas a apresentação
        # não deve apagar uma causa concreta já sanitizada e persistida.
        parts.append("Falha do provedor sem classificação específica")
    elif error_class:
        parts.append(
            _ERROR_LABELS.get(error_class)
            or public_label(error_class)
            or error_class.replace("_", " ").title()
        )
    elif error_type:
        parts.append(public_label(error_type) or error_type.replace("_", " ").title())

    if http_status not in (None, ""):
        try:
            parts.append(f"HTTP {int(http_status)}")
        except (TypeError, ValueError):
            parts.append(f"HTTP {http_status}")

    if error_code:
        parts.append(public_label(error_code) or error_code.replace("_", " ").title())
    elif error_type and not parts:
        parts.append(public_label(error_type) or error_type.replace("_", " ").title())

    if error_detail and error_class == "UNKNOWN_PROVIDER_ERROR":
        parts.append(error_detail)

    return " - ".join(dict.fromkeys(parts)) or "Erro técnico sem detalhe persistido"


def _table_exists(connection: sqlite3.Connection, table: str) -> bool:
    return connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone() is not None


def _columns(connection: sqlite3.Connection, table: str) -> set[str]:
    return {
        str(row[1])
        for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
    }


def latest_semantic_failure_attempts(
    database: str | Path,
    *,
    audit_id: str,
    snapshot_id: str,
) -> tuple[dict[str, Any], ...]:
    """Load the latest causal SEMANTIC_M7 attempt chain for one snapshot."""
    connection = sqlite3.connect(Path(database))
    connection.row_factory = sqlite3.Row
    try:
        if not _table_exists(connection, "ai_provider_attempts"):
            return ()
        columns = _columns(connection, "ai_provider_attempts")
        if not {"audit_id", "snapshot_id", "status"}.issubset(columns):
            return ()

        filters = ["audit_id=?", "snapshot_id=?"]
        params: list[Any] = [audit_id, snapshot_id]
        if "operation" in columns and "semantic_contract_version" in columns:
            filters.append(
                "(operation='SEMANTIC_M7' OR "
                "(operation IS NULL AND semantic_contract_version LIKE 'M18-SEMANTIC-%'))"
            )
        elif "operation" in columns:
            filters.append("operation='SEMANTIC_M7'")
        elif "semantic_contract_version" in columns:
            filters.append("semantic_contract_version LIKE 'M18-SEMANTIC-%'")

        rows = connection.execute(
            "SELECT rowid,* FROM ai_provider_attempts WHERE "
            + " AND ".join(filters)
            + " ORDER BY started_at,rowid",
            tuple(params),
        ).fetchall()
        if not rows:
            return ()

        latest = rows[-1]
        if "ai_task_id" in columns and str(latest["ai_task_id"] or "").strip():
            task_id = str(latest["ai_task_id"])
            rows = [row for row in rows if str(row["ai_task_id"] or "") == task_id]
        elif "ai_round_id" in columns and str(latest["ai_round_id"] or "").strip():
            round_id = str(latest["ai_round_id"])
            rows = [row for row in rows if str(row["ai_round_id"] or "") == round_id]
        else:
            rows = rows[-8:]

        return tuple(
            dict(row)
            for row in rows
            if str(row["status"] or "").upper() not in _SUCCESS
        )
    finally:
        connection.close()


def format_ai_attempt_line(attempt: Mapping[str, Any]) -> str:
    """Format one persisted provider failure without exposing payloads or headers."""
    provider = str(attempt.get("provider") or "IA").upper().strip() or "IA"
    diagnostic = format_ai_attempt_diagnostic(attempt)
    request_id = str(attempt.get("request_id") or "").strip()
    if request_id:
        diagnostic = f"{diagnostic} - ID da requisição: {request_id}"
    return f"{provider}: {diagnostic}"


def semantic_retry_action(attempts: tuple[Mapping[str, Any], ...]) -> str | None:
    """Suggest an operator action only from persisted structured failure classes."""
    classes = {
        str(item.get("error_class") or "").upper().strip()
        for item in attempts
        if str(item.get("status") or "").upper() not in _SUCCESS
    }
    classes.discard("")
    if not classes:
        return None
    if classes & _CONFIGURATION:
        return (
            "revisar credencial, permissão ou quota indicada pelo provider "
            "antes de nova tentativa"
        )
    if classes.issubset(_TRANSIENT):
        return (
            "nova tentativa é possível; verifique disponibilidade dos providers/rede "
            "e reprocese o requisito"
        )
    return None


__all__ = [
    "format_ai_attempt_diagnostic",
    "format_ai_attempt_line",
    "latest_semantic_failure_attempts",
    "semantic_retry_action",
]
