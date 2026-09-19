"""Operational state contract for optional integrations and collections.

This module persists integration-attempt state used by console/observability workflows.
It does not render AUD HTML and does not alter scoring, provider selection, collection
policy or persisted website evidence.
"""
from __future__ import annotations

from contextlib import redirect_stdout
from datetime import datetime, timezone
import io
import json
from pathlib import Path
from rasai.observability.store import observability_database_path
import sqlite3
import sys
from typing import Any, Mapping
import uuid

from rasai.secret_safety import redact_text


_CANONICAL_STATES = {
    "DISABLED": "Desabilitado / não solicitado",
    "NOT_CONFIGURED": "Não configurado",
    "SUCCESS": "Executado com sucesso",
    "PARTIAL": "Executado parcialmente",
    "NO_DATA": "Executado sem dado utilizável",
    "ERROR": "Falhou / indisponível",
    "UNKNOWN": "Estado não determinado",
}

_OBSERVABILITY_SOURCES = {
    "import": "RASAI_OBSERVABILITY_IMPORT",
    "bing-import": "BING_WEBMASTER_TOOLS",
    "google-ai-import": "GOOGLE_GENERATIVE_AI_PERFORMANCE",
    "google-ai-control": "GOOGLE_GENERATIVE_AI_CONTROL",
    "gsc-sites": "GOOGLE_SEARCH_CONSOLE",
    "gsc-sitemaps": "GOOGLE_SEARCH_CONSOLE",
    "gsc-search": "GOOGLE_SEARCH_CONSOLE",
    "gsc-appearance": "GOOGLE_SEARCH_CONSOLE",
    "gsc-inspect": "GOOGLE_SEARCH_CONSOLE",
    "crux-history": "CRUX_HISTORY_API",
}


def public_integration_state(state: str) -> str:
    normalized = str(state or "UNKNOWN").strip().upper()
    return _CANONICAL_STATES.get(normalized, normalized.replace("_", " ").title())


def _table_exists(connection: sqlite3.Connection, table: str) -> bool:
    return connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (table,),
    ).fetchone() is not None


def _ensure_observability_attempt_table(workspace: Path) -> Path | None:
    workspace = Path(workspace)
    if not (workspace / "audit.db").is_file():
        return None
    database = observability_database_path(workspace)
    connection = sqlite3.connect(database)
    try:
        with connection:
            connection.execute(
                """CREATE TABLE IF NOT EXISTS integration_attempts (
                    attempt_id TEXT PRIMARY KEY,
                    operation TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    reason TEXT,
                    metadata TEXT NOT NULL,
                    attempted_at TEXT NOT NULL
                )"""
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_obs_integration_attempts_time "
                "ON integration_attempts(attempted_at,operation)"
            )
    finally:
        connection.close()
    return database


def record_observability_attempt(
    workspace: str | Path,
    *,
    operation: str,
    source_type: str,
    status: str,
    reason: str | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> str | None:
    """Persist an observability attempt in the sidecar without mutating audit.db."""
    database = _ensure_observability_attempt_table(Path(workspace))
    if database is None:
        return None
    attempt_id = f"INT-{uuid.uuid4().hex.upper()}"
    safe_reason = redact_text(str(reason))[:1000] if reason else None
    safe_metadata = {
        str(key): redact_text(str(value)) if isinstance(value, str) else value
        for key, value in dict(metadata or {}).items()
    }
    connection = sqlite3.connect(database)
    try:
        with connection:
            connection.execute(
                "INSERT INTO integration_attempts("
                "attempt_id,operation,source_type,status,reason,metadata,attempted_at"
                ") VALUES (?,?,?,?,?,?,?)",
                (
                    attempt_id,
                    str(operation),
                    str(source_type),
                    str(status).upper(),
                    safe_reason,
                    json.dumps(
                        safe_metadata,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
    finally:
        connection.close()
    return attempt_id


class _Tee(io.TextIOBase):
    def __init__(self, target: Any) -> None:
        self.target = target
        self.capture = io.StringIO()

    def write(self, text: str) -> int:
        self.capture.write(text)
        return self.target.write(text)

    def flush(self) -> None:
        self.target.flush()


def _observability_failure_reason(output: str) -> tuple[str, str]:
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    error = next(
        (
            line.split("RASAi observe error:", 1)[1].strip()
            for line in reversed(lines)
            if "RASAi observe error:" in line
        ),
        "",
    )
    if "not configured; set environment variable" in error.casefold():
        return "NOT_CONFIGURED", error
    return "ERROR", error or "A operação terminou com erro antes de materializar o dataset esperado."


def _install_observability_cli_attempt_ledger() -> None:
    from rasai.observability import cli

    if getattr(cli, "_rasai_integration_attempt_ledger", False):
        return
    original = cli.main

    def main(argv: list[str] | None = None) -> int:
        effective = list(argv) if argv is not None else list(sys.argv[1:])
        try:
            args = cli.build_parser().parse_args(effective)
        except SystemExit:
            return original(effective)
        operation = str(getattr(args, "observe_command", "") or "")
        source = _OBSERVABILITY_SOURCES.get(operation)
        if source is None:
            return original(effective)
        workspace = cli._workspace(args.audits_root, args.audit)
        tee = _Tee(sys.stdout)
        with redirect_stdout(tee):
            code = int(original(effective) or 0)
        output = tee.capture.getvalue()
        if code == 0:
            status, reason = (
                "SUCCESS",
                "Operação concluída e estado/dataset persistido pelo fluxo de observabilidade.",
            )
        else:
            status, reason = _observability_failure_reason(output)
        record_observability_attempt(
            workspace,
            operation=operation,
            source_type=source,
            status=status,
            reason=reason,
            metadata={"exit_code": code},
        )
        return code

    cli.main = main
    cli._rasai_integration_attempt_ledger = True


def install() -> None:
    """Install operational integration-attempt persistence idempotently."""
    _install_observability_cli_attempt_ledger()
