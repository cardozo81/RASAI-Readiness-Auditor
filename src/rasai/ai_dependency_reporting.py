"""Report projection for AI-DEPENDENCY-001 readiness snapshots."""
from __future__ import annotations

from html import escape
import json
import sqlite3
from typing import Any

_INSTALLED = False

_PURPOSE_LABELS = {
    "TECHNICAL_AI": "IA técnica",
    "DEEP_ANALYSIS": "CAT-08 · análise profunda",
    "SEMANTIC_AI": "CAT-03 · análise semântica",
}


def _load(value: Any, default: Any) -> Any:
    if value in (None, ""):
        return default
    if isinstance(value, (dict, list, tuple)):
        return value
    try:
        return json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return default


def _rows(database: Any, audit_id: str) -> list[dict[str, Any]]:
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    try:
        exists = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='ai_dependency_snapshots'"
        ).fetchone()
        if not exists:
            return []
        return [
            dict(row)
            for row in connection.execute(
                "SELECT * FROM ai_dependency_snapshots WHERE audit_id=? ORDER BY created_at,dependency_snapshot_id",
                (audit_id,),
            ).fetchall()
        ]
    finally:
        connection.close()


def dependency_html(database: Any, data: Any) -> str:
    from rasai import catalog_report_integrations as i

    rows = _rows(database, data.audit_id)
    if not rows:
        return i._section(
            "ai-dependencies",
            "Dependências antes da IA",
            "<div class='notice'>Nenhum snapshot de dependência de IA foi persistido nesta execução.</div>",
        )

    table_rows = []
    modals = []
    for index, row in enumerate(rows, 1):
        modal_id = f"ai-dependency-{index}"
        expected = _load(row.get("expected_json"), [])
        present = _load(row.get("present_json"), {})
        missing = _load(row.get("missing_json"), [])
        evidence = _load(row.get("evidence_ids_json"), [])
        ready = bool(row.get("ready"))
        purpose = str(row.get("purpose") or "—")
        table_rows.append((
            _PURPOSE_LABELS.get(purpose, purpose),
            "Pronto" if ready else "Bloqueado",
            len(expected) if isinstance(expected, list) else "—",
            len(missing) if isinstance(missing, list) else "—",
            row.get("created_at") or "—",
            i._modal_button(modal_id, "Ver dependências"),
        ))
        body = i._kv((
            ("Finalidade", _PURPOSE_LABELS.get(purpose, purpose)),
            ("Estado antes da chamada", "Pronto" if ready else "Bloqueado"),
            ("Escopo", row.get("scope_key") or "AUDIT"),
            ("Dependências esperadas", ", ".join(str(v) for v in expected) if isinstance(expected, list) else str(expected)),
            ("Dependências ausentes/não prontas", ", ".join(str(v) for v in missing) if isinstance(missing, list) and missing else "Nenhuma"),
            ("Evidências relacionadas", ", ".join(str(v) for v in evidence) if isinstance(evidence, list) and evidence else "—"),
            ("Fingerprint do contexto", row.get("context_fingerprint") or "—"),
            ("Contrato", row.get("contract_version") or "—"),
            ("Registrado em", row.get("created_at") or "—"),
        ))
        if isinstance(present, dict):
            body += "<h3>Estado efetivo das dependências</h3><div class='pre'>" + escape(
                json.dumps(present, ensure_ascii=False, indent=2, sort_keys=True)
            ) + "</div>"
        if not ready:
            body += (
                "<div class='notice warn'><strong>Provider não elegível neste ponto:</strong> o gate registrou contexto "
                "incompleto; essa decisão deve ocorrer antes da criação de tentativa/custo.</div>"
            )
        modals.append(i._modal(modal_id, _PURPOSE_LABELS.get(purpose, purpose), "Prontidão do contexto antes do provider", body))

    content = i._table(
        ("Finalidade", "Prontidão", "Esperadas", "Pendentes", "Registrado em", "Detalhe"),
        table_rows,
        sortable=bool(table_rows),
        page_size=10 if len(table_rows) > 10 else None,
    ) + "".join(modals)
    content += (
        "<p class='muted'>O snapshot comprova o contexto disponível imediatamente antes do limite de execução da IA. "
        "Ele é metadado de governança e não altera evidências ou score.</p>"
    )
    return i._section("ai-dependencies", "Dependências antes da IA", content)


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    from rasai import catalog_report_site as site

    current = site._ai_integrations_body
    if getattr(current, "_rasai_ai_dependency_reporting", False):
        _INSTALLED = True
        return

    def ai_integrations_body(database: Any, data: Any) -> str:
        return current(database, data) + dependency_html(database, data)

    ai_integrations_body._rasai_ai_dependency_reporting = True
    ai_integrations_body._rasai_original = current
    site._ai_integrations_body = ai_integrations_body
    _INSTALLED = True


__all__ = ["dependency_html", "install"]
