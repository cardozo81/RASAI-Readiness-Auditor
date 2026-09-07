"""M16 reporting projections for persisted RootCauseAnalysis records."""

from __future__ import annotations

from html import escape
import json
import sqlite3
from typing import Any

from rasai.m15_reporting import M15RemediationReportBuilder, M15ReportBuilder, _short_path
from rasai.m16_root_cause import AffectedElement, M16Persistence, RootCauseAnalysis
from rasai.persistence import AuditWorkspace


_M16_CSS = r"""
.m16-root{margin:16px 0;padding:16px;border:1px solid #c7d7fe;border-left:6px solid #3157a4;border-radius:12px;background:#f8fbff}
.m16-root h4{margin-top:0}.m16-root-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:9px;margin:10px 0}.m16-root-grid>div{background:#fff;border:1px solid #e5eaf2;border-radius:9px;padding:10px;min-width:0}.m16-root-grid small{display:block;color:#667085;font-size:.72rem}.m16-root-grid strong{display:block;margin-top:3px;overflow-wrap:anywhere}.m16-element-table{width:100%;border-collapse:collapse;margin:10px 0;font-size:.82rem}.m16-element-table th,.m16-element-table td{padding:8px;text-align:left;vertical-align:top;border-bottom:1px solid #e4e7ec}.m16-element-table th{background:#f2f4f7;color:#475467}.m16-code{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;overflow-wrap:anywhere}.m16-root pre{max-height:300px;overflow:auto;background:#101828;color:#f2f4f7;padding:10px;border-radius:8px}.m16-change{background:#fff;border:1px solid #d0d5dd;border-radius:9px;padding:12px;line-height:1.5}.m16-decision{background:#fff6ed;border:1px solid #fedf89;border-radius:9px;padding:10px;margin-top:9px}.m16-occurrence{margin:12px 0;padding:12px;border:1px solid #d0d5dd;border-radius:10px;background:#fff}.m16-occurrence summary{cursor:pointer;font-weight:800}.m16-selector-unknown{font-weight:800;color:#667085}@media(max-width:900px){.m16-root-grid{grid-template-columns:1fr}.m16-element-table{display:block;overflow-x:auto}}
"""


class M16ReportBuilder(M15ReportBuilder):
    """Extend page-oriented REPORT-GEO-003 with root-cause diagnostics."""

    def __init__(self) -> None:
        self._m16_analyses: dict[str, RootCauseAnalysis] = {}

    def build(self, *, audit_id: str, workspace: AuditWorkspace) -> str:
        with M16Persistence(workspace) as store:
            self._m16_analyses = {item.finding_id: item for item in store.list_for_audit(audit_id)}
        html = super().build(audit_id=audit_id, workspace=workspace)
        return html.replace("</style>", f"{_M16_CSS}</style>", 1)

    def _finding_detail(
        self,
        *,
        finding: sqlite3.Row,
        page: sqlite3.Row,
        evidence_by_id: dict[str, sqlite3.Row],
        observations: list[sqlite3.Row],
        priority: str,
    ) -> str:
        html = super()._finding_detail(
            finding=finding,
            page=page,
            evidence_by_id=evidence_by_id,
            observations=observations,
            priority=priority,
        )
        analysis = self._m16_analyses.get(str(finding["finding_id"]))
        if analysis is None:
            return html
        block = _analysis_block(analysis, page_label=str(page["normalized_url"]))
        return html.replace("<h4>Problema</h4>", block + "<h4>Problema</h4>", 1)


class M16RemediationReportBuilder(M15RemediationReportBuilder):
    """Add per-occurrence root cause to the grouped remediation projection."""

    def __init__(self) -> None:
        self._m16_analyses: dict[str, RootCauseAnalysis] = {}

    def build(self, *, audit_id: str, workspace: AuditWorkspace) -> str:
        with M16Persistence(workspace) as store:
            self._m16_analyses = {item.finding_id: item for item in store.list_for_audit(audit_id)}
        html = super().build(audit_id=audit_id, workspace=workspace)
        return html.replace("</style>", f"{_M16_CSS}</style>", 1)

    def _group_card(
        self,
        *,
        key: tuple[str, str, str],
        rows: list[sqlite3.Row],
        page_by_id: dict[str, sqlite3.Row],
        page_anchor: dict[str, int],
        obs_by_finding: dict[str, list[sqlite3.Row]],
        priorities: dict[str, str],
    ) -> str:
        html = super()._group_card(
            key=key,
            rows=rows,
            page_by_id=page_by_id,
            page_anchor=page_anchor,
            obs_by_finding=obs_by_finding,
            priorities=priorities,
        )
        occurrences: list[str] = []
        for row in rows:
            analysis = self._m16_analyses.get(str(row["finding_id"]))
            if analysis is None:
                continue
            page = page_by_id.get(row["page_id"]) if row["page_id"] else None
            page_label = _short_path(str(page["normalized_url"])) if page is not None else "DOMÍNIO / RECURSO GLOBAL"
            occurrences.append(
                "<details class='m16-occurrence'>"
                f"<summary>{escape(page_label)} · {escape(str(row['device'] or 'GLOBAL'))} · causa raiz</summary>"
                f"{_analysis_block(analysis, page_label=page_label, nested=True)}"
                "</details>"
            )
        if not occurrences:
            return html
        insert = (
            "<div class='m16-group-details'><h4>Diagnóstico técnico por ocorrência</h4>"
            + "".join(occurrences)
            + "</div>"
        )
        return html.replace("</article>", insert + "</article>", 1)


def _analysis_block(
    analysis: RootCauseAnalysis,
    *,
    page_label: str,
    nested: bool = False,
) -> str:
    selector_label = {
        "NOT_APPLICABLE": "NÃO APLICÁVEL",
        "NOT_DETERMINED": "NÃO DETERMINADO",
        "MULTI_ELEMENT_SET": "CONJUNTO DE ELEMENTOS",
        "CONTEXT_REGION": "REGIÃO CONTEXTUAL",
        "EXACT": "ELEMENTO EXATO",
    }.get(analysis.selector_status, analysis.selector_status)
    elements = _elements_table(analysis.affected_elements, selector_label)
    observed = _json_pre(analysis.observed_value)
    acceptance = "".join(f"<li>{escape(item)}</li>" for item in analysis.acceptance_criteria)
    validation = "".join(f"<li>{escape(item)}</li>" for item in analysis.revalidation_steps)
    decision = (
        f"<div class='m16-decision'><strong>Decisão humana necessária</strong><br>{escape(analysis.human_decision_required)}</div>"
        if analysis.human_decision_required else ""
    )
    example = (
        f"<details><summary>Exemplo pós-correção</summary><pre><code>{escape(analysis.example_after)}</code></pre></details>"
        if analysis.example_after else ""
    )
    wrapper = "div" if nested else "section"
    return f"""
    <{wrapper} class="m16-root">
      <h4>Diagnóstico de causa raiz</h4>
      <div class="m16-root-grid">
        <div><small>Causa</small><strong>{escape(analysis.cause_type)}</strong></div>
        <div><small>Escopo afetado</small><strong>{escape(analysis.affected_scope)}</strong></div>
        <div><small>Precisão diagnóstica</small><strong>{escape(analysis.diagnostic_confidence)}</strong></div>
        <div><small>Local</small><strong>{escape(page_label)}</strong></div>
        <div><small>Selector</small><strong>{escape(selector_label)}</strong></div>
        <div><small>Regra</small><strong>{escape(analysis.rule_id)}</strong></div>
      </div>
      <p><strong>Causa raiz:</strong> {escape(analysis.cause_summary)}</p>
      <h5>Elemento(s) relacionado(s)</h5>{elements}
      <h5>Observado versus esperado</h5>
      <div class="m16-root-grid">
        <div><small>Observado</small>{observed}</div>
        <div><small>Condição esperada</small><strong>{escape(analysis.expected_condition or 'NÃO DETERMINADO')}</strong></div>
        <div><small>Evidências-base</small><strong>{escape(', '.join(analysis.evidence_basis) or 'NÃO DETERMINADO')}</strong></div>
      </div>
      <h5>Mudança exata recomendada</h5><div class="m16-change">{escape(analysis.exact_change)}</div>
      {example}{decision}
      <h5>Critério de aceite</h5><ul>{acceptance}</ul>
      <h5>Revalidação</h5><ol>{validation}</ol>
    </{wrapper}>
    """


def _elements_table(elements: tuple[AffectedElement, ...], selector_label: str) -> str:
    if not elements:
        return (
            "<div class='notice notice-unknown'>"
            f"Selector: <span class='m16-selector-unknown'>{escape(selector_label)}</span>. "
            "Nenhum nó DOM foi atribuído como elemento exato para esta causa; o diagnóstico permanece no escopo documental/recurso/conteúdo indicado."
            "</div>"
        )
    rows = []
    for element in elements:
        element_name = element.tag_name or "NÃO DETERMINADO"
        if element.element_id:
            element_name += f"#{element.element_id}"
        if element.classes:
            element_name += "." + ".".join(element.classes[:4])
        html = (
            f"<details><summary>HTML observado</summary><pre><code>{escape(element.outer_html)}</code></pre></details>"
            if element.outer_html else "Trecho HTML não persistido"
        )
        rows.append(
            "<tr>"
            f"<td>{escape(element.relation)}</td>"
            f"<td class='m16-code'>{escape(element.selector or 'NÃO DETERMINADO')}</td>"
            f"<td class='m16-code'>{escape(element_name)}</td>"
            f"<td>{html}</td>"
            "</tr>"
        )
    return (
        "<table class='m16-element-table'><thead><tr>"
        "<th>Relação</th><th>Selector</th><th>Elemento</th><th>Evidência HTML</th>"
        "</tr></thead><tbody>" + "".join(rows) + "</tbody></table>"
    )


def _json_pre(value: Any) -> str:
    if value is None:
        return "<strong>NÃO DETERMINADO</strong>"
    try:
        text = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)
    except (TypeError, ValueError):
        text = str(value)
    if len(text) > 6000:
        text = text[:6000] + "\n… [truncado no relatório]"
    return f"<pre><code>{escape(text)}</code></pre>"
