"""SCORE-GEO-002 reporting refinements for dimension applicability."""

from __future__ import annotations

from html import escape
import json
import re
import sqlite3

from rasai.persistence import AuditWorkspace


_DIMENSION_LABELS = {
    "TECHNICAL_ACCESSIBILITY": "Acessibilidade Técnica",
    "INDEXABILITY": "Capacidade de Indexação",
    "CONTENT_EXTRACTABILITY": "Extração de Conteúdo",
    "SEMANTIC_STRUCTURE": "Estrutura Semântica",
    "ENTITY_CLARITY": "Clareza de Entidades",
    "STRUCTURED_DATA": "Dados Estruturados",
    "ANSWERABILITY": "Capacidade de Resposta",
    "CITATION_READINESS": "Preparação para Citação",
    "EVIDENCE_TRUST": "Evidências e Confiabilidade",
    "INTENT_COVERAGE": "Cobertura de Intenções",
}
_DEVICE_LABELS = {"DESKTOP": "Desktop", "MOBILE": "Mobile"}


def refine_score_applicability_html(
    html: str,
    *,
    audit_id: str,
    workspace: AuditWorkspace,
) -> str:
    """Make NOT_APPLICABLE dimensions explicit in the human report.

    The underlying score state is persisted by SCORE-GEO-002. This projection
    prevents `value=NULL` for a legitimately non-applicable dimension from being
    presented as "informação insuficiente" and makes the Overall denominator
    visible to the reader.
    """

    rows = _load_scores(audit_id, workspace)
    if not rows:
        return html

    by_device: dict[str, list[sqlite3.Row]] = {"DESKTOP": [], "MOBILE": []}
    for row in rows:
        by_device.setdefault(str(row["device"]), []).append(row)

    refined = html
    for device in ("DESKTOP", "MOBILE"):
        device_rows = by_device.get(device, [])
        not_applicable = [
            row for row in device_rows
            if row["dimension"] != "OVERALL_READINESS"
            and row["consolidation_status"] == "NOT_APPLICABLE"
        ]
        for row in not_applicable:
            refined = _replace_dimension_card(
                refined,
                device=device,
                dimension=str(row["dimension"]),
            )
        refined = _annotate_overall_card(
            refined,
            device=device,
            dimension_rows=[row for row in device_rows if row["dimension"] != "OVERALL_READINESS"],
            not_applicable=not_applicable,
        )
    return refined


def _load_scores(audit_id: str, workspace: AuditWorkspace) -> list[sqlite3.Row]:
    connection = sqlite3.connect(workspace.database)
    connection.row_factory = sqlite3.Row
    try:
        try:
            return list(
                connection.execute(
                    "SELECT * FROM scores WHERE audit_id=? ORDER BY device,dimension",
                    (audit_id,),
                ).fetchall()
            )
        except sqlite3.OperationalError as exc:
            if "no such table" in str(exc).lower():
                return []
            raise
    finally:
        connection.close()


def _replace_dimension_card(html: str, *, device: str, dimension: str) -> str:
    device_label = _DEVICE_LABELS[device]
    dimension_label = _DIMENSION_LABELS.get(dimension, dimension.replace("_", " ").title())
    heading = f"<h2>Score GEO - {device_label}</h2>"
    start = html.find(heading)
    if start < 0:
        return html
    end = html.find("</section>", start)
    if end < 0:
        return html
    section = html[start : end + len("</section>")]

    card_pattern = re.compile(
        r"<article class=\"score-row state-[^\"]+\">(?:(?!</article>).)*?"
        + re.escape(f"<strong>{dimension_label}</strong>")
        + r"(?:(?!</article>).)*?</article>",
        re.DOTALL,
    )
    replacement = f"""
        <article class="score-row state-info">
          <div class="score-main"><strong>{escape(dimension_label)}</strong><span class="badge state-info">NÃO APLICÁVEL</span></div>
          <div class="score-number">-</div>
          <div><small>Classificação</small><strong>Fora do universo aplicável</strong></div>
          <div><small>Cobertura</small><strong>NÃO APLICÁVEL</strong></div>
          <div><small>Confiabilidade</small><strong>NÃO APLICÁVEL</strong></div>
          <div><small>Consolidação</small><strong>NÃO APLICÁVEL</strong></div>
        </article>
    """
    updated, count = card_pattern.subn(replacement, section, count=1)
    if count == 0:
        return html
    return html[:start] + updated + html[end + len("</section>") :]


def _annotate_overall_card(
    html: str,
    *,
    device: str,
    dimension_rows: list[sqlite3.Row],
    not_applicable: list[sqlite3.Row],
) -> str:
    if not dimension_rows or not not_applicable:
        return html

    label = _DEVICE_LABELS[device]
    applicable_count = len(dimension_rows) - len(not_applicable)
    total_count = len(dimension_rows)
    excluded_labels = ", ".join(
        _DIMENSION_LABELS.get(str(row["dimension"]), str(row["dimension"]))
        for row in not_applicable
    )
    note = (
        f"<p class='method-note'><strong>Dimensões aplicáveis:</strong> {applicable_count} de {total_count}. "
        f"<strong>Fora do universo aplicável:</strong> {escape(excluded_labels)}. "
        "A exclusão não atribui nota zero nem nota máxima.</p>"
    )

    pattern = re.compile(
        r"(<article class=\"overall-card state-[^\"]+\">(?:(?!</article>).)*?"
        + re.escape(f'<div class="card-label">{label}</div>')
        + r"(?:(?!</article>).)*?)(</article>)",
        re.DOTALL,
    )
    return pattern.sub(r"\1" + note + r"\2", html, count=1)


def overall_applicability_summary(limitations_json: str | None) -> tuple[str, ...]:
    """Public helper for tests/other projections; never guesses excluded dimensions."""

    if not limitations_json:
        return ()
    try:
        values = json.loads(limitations_json)
    except (TypeError, ValueError, json.JSONDecodeError):
        return ()
    if not isinstance(values, list):
        return ()
    prefix = "DIMENSION_NOT_APPLICABLE:"
    return tuple(
        str(value).split(":", 1)[1]
        for value in values
        if isinstance(value, str) and value.startswith(prefix)
    )
