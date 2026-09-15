"""Final presentation contract for audit history and reprocess navigation.

Presentation/navigation only. This module reads persisted audit metadata to show the
physical end of local processing independently from the logical fulfillment state, adds
compact domain/URL context to history, and restores the canonical reprocess presentation
after later UI overlays. It never mutates audit evidence or execution rules.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
import sqlite3
from types import ModuleType
from typing import Any
from urllib.parse import urlsplit


def _table_columns(connection: sqlite3.Connection, table: str) -> set[str]:
    try:
        return {str(row[1]) for row in connection.execute(f'PRAGMA table_info("{table}")').fetchall()}
    except sqlite3.Error:
        return set()


def _read_only(audit_root: Path) -> sqlite3.Connection | None:
    database = audit_root / "audit.db"
    if not database.is_file():
        return None
    try:
        connection = sqlite3.connect(
            f"file:{database.resolve().as_posix()}?mode=ro",
            uri=True,
            timeout=0.5,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only = ON")
        return connection
    except sqlite3.Error:
        return None


def _timestamp_key(value: str) -> tuple[int, datetime | str]:
    raw = str(value or "").strip()
    if not raw:
        return (0, "")
    try:
        from rasai.time_contract import parse_timestamp

        return (1, parse_timestamp(raw))
    except (ImportError, OSError, ValueError):
        return (0, raw)


def process_finished_at(audit_root: Path, audit_id: str) -> str | None:
    """Return the latest persisted physical completion for this AUD lifecycle.

    The timestamp is intentionally independent from fulfillment ``COMPLETE``. An initial
    execution that ends with a partial AUD still has a physical finish time. A later
    completed RPR is part of the same AUD lifecycle and becomes the most recent local
    process completion shown in history.
    """
    connection = _read_only(audit_root)
    if connection is None:
        return None
    candidates: list[str] = []
    try:
        projection_cols = _table_columns(connection, "console_execution_projections")
        if {"audit_id", "finished_at"} <= projection_cols:
            row = connection.execute(
                "SELECT finished_at FROM console_execution_projections WHERE audit_id=? LIMIT 1",
                (audit_id,),
            ).fetchone()
            if row and str(row[0] or "").strip():
                candidates.append(str(row[0]).strip())

        reprocess_cols = _table_columns(connection, "audit_reprocess_runs")
        if {"audit_id", "completed_at"} <= reprocess_cols:
            rows = connection.execute(
                "SELECT completed_at FROM audit_reprocess_runs "
                "WHERE audit_id=? AND completed_at IS NOT NULL",
                (audit_id,),
            ).fetchall()
            candidates.extend(str(row[0]).strip() for row in rows if str(row[0] or "").strip())

        audit_cols = _table_columns(connection, "audits")
        if {"audit_id", "completed_at"} <= audit_cols:
            row = connection.execute(
                "SELECT completed_at FROM audits WHERE audit_id=? LIMIT 1",
                (audit_id,),
            ).fetchone()
            if row and str(row[0] or "").strip():
                candidates.append(str(row[0]).strip())
    except sqlite3.Error:
        return None
    finally:
        connection.close()

    if not candidates:
        return None
    return max(candidates, key=_timestamp_key)


def _host(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return "-"
    parsed = urlsplit(raw if "://" in raw else f"//{raw}")
    return parsed.hostname or raw.rstrip("/")


def domain_context(audit_root: Path, audit_id: str) -> str:
    """Return ``primary-domain`` or ``primary-domain (N URLs)`` for history."""
    connection = _read_only(audit_root)
    if connection is None:
        return "-"
    primary = ""
    url_count = 0
    try:
        target_cols = _table_columns(connection, "audit_targets")
        if {"audit_id", "normalized_origin"} <= target_cols:
            row = connection.execute(
                "SELECT normalized_origin FROM audit_targets "
                "WHERE audit_id=? ORDER BY rowid LIMIT 1",
                (audit_id,),
            ).fetchone()
            if row:
                primary = str(row[0] or "").strip()

        page_cols = _table_columns(connection, "pages")
        if {"audit_id", "normalized_url"} <= page_cols:
            row = connection.execute(
                "SELECT COUNT(DISTINCT normalized_url) FROM pages "
                "WHERE audit_id=? AND normalized_url IS NOT NULL AND normalized_url<>''",
                (audit_id,),
            ).fetchone()
            url_count = int(row[0] or 0) if row else 0
            if not primary:
                row = connection.execute(
                    "SELECT normalized_url FROM pages WHERE audit_id=? "
                    "AND normalized_url IS NOT NULL AND normalized_url<>'' ORDER BY rowid LIMIT 1",
                    (audit_id,),
                ).fetchone()
                if row:
                    primary = str(row[0] or "").strip()

        if url_count <= 0 and {"audit_id", "input_url"} <= target_cols:
            row = connection.execute(
                "SELECT COUNT(DISTINCT input_url) FROM audit_targets "
                "WHERE audit_id=? AND input_url IS NOT NULL AND input_url<>''",
                (audit_id,),
            ).fetchone()
            url_count = int(row[0] or 0) if row else 0
    except sqlite3.Error:
        return "-"
    finally:
        connection.close()

    domain = _host(primary)
    if domain == "-":
        return domain
    return f"{domain} ({url_count} URLs)" if url_count > 1 else domain


def _history_row(index: int, audit_root: Path, audit_width: int) -> None:
    from rasai import console_usability_refinements as usability

    audit_id = audit_root.name
    summary = usability._safe_summary(audit_root, audit_id)
    status = usability._friendly_status(summary.get("processing_status") or "STATUS NÃO PROJETADO")
    completed = usability._local_timestamp(process_finished_at(audit_root, audit_id))
    reprocess = usability._reprocess_label(summary)
    domain = domain_context(audit_root, audit_id)
    print(
        f"{index:>2}. {audit_id:<{audit_width}}  {completed:<16}  "
        f"{status:<29}  {reprocess:<16}  {domain}"
    )


def _choose_audit_factory(console_module: ModuleType):
    def choose_audit(state: Any) -> str | None:
        from rasai import audit_management_console as management
        from rasai import console_navigation as navigation

        while True:
            audits = navigation._audit_directories(state.audits_root)
            print("\nAUDITORIAS / HISTÓRICO")
            print(f"Raiz: {state.audits_root}")
            if audits:
                recent = audits[:20]
                audit_width = max(36, min(44, max(len(item.name) for item in recent)))
                print("\nRecentes:")
                print(
                    f"{'Nº':>3} {'AUDITORIA':<{audit_width}}  {'CONCLUSÃO LOCAL':<16}  "
                    f"{'SITUAÇÃO':<29}  {'REPROCESSAMENTO':<16}  DOMÍNIO"
                )
                print(
                    f"{'---':>3} {'-' * audit_width}  {'-' * 16}  "
                    f"{'-' * 29}  {'-' * 16}  {'-' * 24}"
                )
                for index, audit_root in enumerate(recent, 1):
                    _history_row(index, audit_root, audit_width)
            else:
                print("\nNenhum AUD com audit.db encontrado nesta raiz.")

            print("\nI. Informar Audit ID")
            print("G. Gerenciar / excluir auditorias")
            print("V. Voltar")
            raw = input("Escolha: ").strip().upper()
            if raw == "V":
                return None
            if raw == "G":
                management._management_menu(console_module, state)
                console_module.render_header(state)
                continue
            if raw == "I":
                audit_id = input("Audit ID (AUD-*) ou V para cancelar: ").strip().upper()
                if audit_id == "V":
                    state.error = ""
                    continue
                candidate = Path(state.audits_root) / audit_id
                if audit_id.startswith("AUD-") and (candidate / "audit.db").is_file():
                    state.error = ""
                    return audit_id
                state.error = f"AUD não encontrado em {state.audits_root}: {audit_id or '<vazio>'}"
                continue
            try:
                selected = int(raw) - 1
            except ValueError:
                state.error = "opção de auditoria inválida"
                continue
            if 0 <= selected < min(len(audits), 20):
                state.error = ""
                return audits[selected].name
            state.error = "opção de auditoria inválida"

    return choose_audit


def install(console_module: ModuleType) -> None:
    """Install after the final usability/operator overlays."""
    if getattr(console_module, "_rasai_history_presentation_installed", False):
        return
    from rasai import console_navigation as navigation
    from rasai import console_reprocess_parity as parity
    from rasai import console_usability_refinements as usability

    # A later usability overlay historically rebound the older reprocess function. Keep
    # the canonical parity implementation as the final presentation owner.
    navigation._reprocess_selected = parity.reprocess_selected
    usability._reprocess_selected = parity.reprocess_selected

    # The final history owner includes process completion and domain context while
    # preserving the same selection, management and cancellation behavior.
    usability._history_row = _history_row
    navigation._choose_audit = _choose_audit_factory(console_module)

    console_module._rasai_history_presentation_installed = True
