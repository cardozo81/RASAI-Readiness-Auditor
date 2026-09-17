"""Compact CAT-03 projection for declared context and semantic coherence."""
from __future__ import annotations

from collections import Counter
from html import escape
import json
import sqlite3
from typing import Any, Mapping

from rasai.semantic_coherence import PAGE_COHERENCE_CRITERIA, PROPERTY_COHERENCE_CRITERIA

_INSTALLED = False

_RESULT_LABELS = {
    "COHERENT": "Coerente",
    "PARTIAL": "Parcial",
    "INCOHERENT": "Incoerente",
    "NOT_DETERMINABLE": "Não determinável",
    "NOT_APPLICABLE": "Não aplicável",
}
_PROPERTY_LABELS = {
    "business_sector": "Setor / ramo",
    "business_description": "Descrição do negócio",
    "primary_offering": "Oferta principal",
    "target_audience_profile": "Público-alvo detalhado",
    "primary_goal": "Objetivo principal",
    "positioning": "Posicionamento",
}
_CONTENT_LABELS = {
    "page_purpose": "Propósito da página",
    "intended_audience": "Público pretendido",
    "content_origin": "Origem do conteúdo",
    "risk_profile": "Perfil de risco",
    "ymyl_category": "Categoria YMYL",
    "experience_requirement": "Requisito de experiência",
    "freshness_sensitivity": "Sensibilidade à atualização",
}


def _table_exists(connection: sqlite3.Connection, name: str) -> bool:
    return connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1", (name,)
    ).fetchone() is not None


def _rows(database: Any, audit_id: str, table: str) -> list[dict[str, Any]]:
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    try:
        if not _table_exists(connection, table):
            return []
        return [dict(row) for row in connection.execute(f"SELECT * FROM {table} WHERE audit_id=?", (audit_id,)).fetchall()]
    finally:
        connection.close()


def _confidence(value: Any) -> str:
    try:
        return f"{float(value) * 100:.0f}%"
    except (TypeError, ValueError):
        return "—"


def _status(value: Any) -> str:
    token = str(value or "NOT_DETERMINABLE").upper()
    return _RESULT_LABELS.get(token, token.replace("_", " ").title())


def _context_html(evidence: Any, database: Any, audit_id: str) -> str:
    property_rows = _rows(database, audit_id, "property_semantic_contexts")
    content_rows = _rows(database, audit_id, "content_analysis_contexts")
    manifest_rows = _rows(database, audit_id, "semantic_corpus_manifests")
    blocks: list[str] = []

    property_values: list[tuple[Any, ...]] = []
    if property_rows:
        row = property_rows[0]
        for key, label in _PROPERTY_LABELS.items():
            raw = str(row.get(key) or "auto")
            property_values.append((label, raw, "Automático" if raw.casefold() == "auto" else "Declarado"))
    else:
        property_values = [(label, "auto", "Automático") for label in _PROPERTY_LABELS.values()]
    blocks.append(
        "<div class='subsection'><h3>Contexto da propriedade</h3>"
        + evidence._table(("Campo", "Valor usado", "Origem"), property_values)
        + "<p class='muted'>Contexto declarado é entrada da auditoria, não evidência observada e não altera a pontuação por si só.</p></div>"
    )

    content_values: list[tuple[Any, ...]] = []
    if content_rows:
        row = content_rows[0]
        for key, label in _CONTENT_LABELS.items():
            raw = str(row.get(key) or "auto")
            content_values.append((label, raw, "Automático" if raw.casefold() == "auto" else "Declarado"))
    if content_values:
        blocks.append(
            "<div class='subsection'><h3>Contexto editorial, risco e confiança</h3>"
            + evidence._table(("Campo", "Valor usado", "Origem"), content_values)
            + "</div>"
        )

    if manifest_rows:
        manifest = manifest_rows[0]
        try:
            page_count = len(json.loads(str(manifest.get("page_ids_json") or "[]")))
            snapshot_count = len(json.loads(str(manifest.get("snapshot_ids_json") or "[]")))
        except (TypeError, ValueError, json.JSONDecodeError):
            page_count = snapshot_count = 0
        blocks.append(
            "<div class='notice'><strong>Gate semântico:</strong> "
            f"{escape(str(manifest.get('status') or '—'))}. O contexto foi congelado antes da primeira chamada de IA; "
            f"corpus com {page_count} página(s) e {snapshot_count} captura(s). "
            "A agregação entre páginas usa apenas resultados já persistidos e não gera uma chamada adicional.</div>"
        )
    return "".join(blocks)


def _property_summary_html(evidence: Any, database: Any, audit_id: str) -> str:
    summaries = sorted(_rows(database, audit_id, "property_semantic_summaries"), key=lambda row: str(row.get("criterion_id")))
    if not summaries:
        return (
            "<div class='subsection'><h3>Coerência da propriedade</h3>"
            "<div class='notice'>A análise de coerência da propriedade não produziu dados nesta execução. "
            "A coleta determinística e as demais evidências do CAT-03 permanecem válidas.</div></div>"
        )
    table_rows = []
    modals = []
    for index, row in enumerate(summaries, 1):
        criterion = str(row.get("criterion_id") or "")
        modal_id = f"property-coherence-{index}"
        table_rows.append((
            PROPERTY_COHERENCE_CRITERIA.get(criterion, criterion),
            _status(row.get("result")),
            _confidence(row.get("confidence")),
            int(row.get("observation_count") or 0),
            evidence._modal_button(modal_id, "Ver análise"),
        ))
        try:
            evidence_ids = json.loads(str(row.get("evidence_ids_json") or "[]"))
        except (TypeError, ValueError, json.JSONDecodeError):
            evidence_ids = []
        body = evidence._kv((
            ("Critério", criterion),
            ("Resultado", _status(row.get("result"))),
            ("Confiança agregada", _confidence(row.get("confidence"))),
            ("Páginas/observações consideradas", row.get("observation_count") or 0),
            ("Leitura", row.get("summary") or "—"),
            ("Evidências relacionadas", ", ".join(str(item) for item in evidence_ids) or "—"),
        ))
        modals.append(evidence._modal(modal_id, PROPERTY_COHERENCE_CRITERIA.get(criterion, criterion), "Agregação cross-page determinística", body))
    divergent = sum(1 for row in summaries if str(row.get("result")) in {"PARTIAL", "INCOHERENT"})
    note = ""
    if divergent:
        note = f"<p class='muted'>{divergent} dimensão(ões) com divergência ou coerência parcial. A implementação de correções fica centralizada em <a href='cat-09.html'>CAT-09 · Remediações</a>.</p>"
    return (
        "<div class='subsection'><h3>Coerência da propriedade</h3>"
        + evidence._table(("Dimensão", "Resultado", "Confiança", "Base", "Detalhe"), table_rows, sortable=True)
        + note + "".join(modals) + "</div>"
    )


def _page_summary_html(evidence: Any, database: Any, audit_id: str) -> str:
    rows = _rows(database, audit_id, "semantic_coherence_assessments")
    if not rows:
        return (
            "<div class='subsection'><h3>Coerência semântica por página</h3>"
            "<div class='notice'>Nenhuma avaliação de coerência por IA foi persistida. "
            "Isso não invalida conteúdo/estrutura/JSON-LD coletados deterministicamente.</div></div>"
        )
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(str(row.get("criterion_id") or ""), []).append(row)
    table_rows = []
    modals = []
    for index, criterion in enumerate(PAGE_COHERENCE_CRITERIA, 1):
        items = grouped.get(criterion, [])
        counts = Counter(str(item.get("result") or "NOT_DETERMINABLE") for item in items)
        divergence = counts.get("PARTIAL", 0) + counts.get("INCOHERENT", 0)
        confidence = sum(float(item.get("confidence") or 0) for item in items) / len(items) if items else 0.0
        modal_id = f"page-coherence-{index}"
        state = "Incoerente" if counts.get("INCOHERENT") else "Parcial" if divergence else "Coerente" if items else "Não determinável"
        table_rows.append((
            PAGE_COHERENCE_CRITERIA[criterion], state, _confidence(confidence), divergence,
            evidence._modal_button(modal_id, "Ver páginas"),
        ))
        details = []
        for item in sorted(items, key=lambda value: (str(value.get("page_url")), str(value.get("snapshot_id")))):
            details.append((
                item.get("page_url") or "—",
                _status(item.get("result")),
                _confidence(item.get("confidence")),
                item.get("observed_context") or "—",
            ))
        body = evidence._table(("Página", "Resultado", "Confiança", "Observado"), details, sortable=bool(details), page_size=10 if len(details) > 10 else None)
        body += "<p class='muted'>O detalhe técnico da chamada, provider, tokens e custo permanece em <a href='ai-integrations.html'>IA e integrações</a>.</p>"
        modals.append(evidence._modal(modal_id, PAGE_COHERENCE_CRITERIA[criterion], criterion, body))
    return (
        "<div class='subsection'><h3>Coerência semântica por página</h3>"
        + evidence._table(("Dimensão", "Resultado", "Confiança", "Divergências", "Detalhe"), table_rows, sortable=True)
        + "".join(modals) + "</div>"
    )


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    from rasai import catalog_report_evidence as evidence
    from rasai import catalog_report_page as page

    original = evidence._semantic_html

    def semantic_html_with_coherence(database: Any, data: Any) -> str:
        return (
            _context_html(evidence, database, data.audit_id)
            + _property_summary_html(evidence, database, data.audit_id)
            + _page_summary_html(evidence, database, data.audit_id)
            + original(database, data)
        )

    evidence._semantic_html = semantic_html_with_coherence
    # catalog_report_page imports evidence helpers by value via wildcard composition.
    page._semantic_html = semantic_html_with_coherence
    _INSTALLED = True
