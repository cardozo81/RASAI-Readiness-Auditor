"""M17 remediation precision and report-consistency projections."""

from __future__ import annotations

from html import escape
import json
import re
import sqlite3
from typing import Any

from rasai.actionability import Actionability, classify_actionability, label_for
from rasai.m15_reporting import M15RemediationReportBuilder, M15ReportBuilder, _short_path
from rasai.m16_reporting import M16RemediationReportBuilder, M16ReportBuilder
from rasai.m16_root_cause import AffectedElement, RootCauseAnalysis
from rasai.m17_precision import M17PrecisionPersistence, RootCausePrecision
from rasai.persistence import AuditWorkspace
from rasai.remediation import recipe_for


_M17_CSS = r"""
.m17-precision{border-left-color:#1d4ed8}.m17-precision-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:9px;margin:10px 0}.m17-precision-grid>div{background:#fff;border:1px solid #e5e7eb;border-radius:9px;padding:10px;min-width:0}.m17-precision-grid small{display:block;color:#667085;font-size:.72rem}.m17-precision-grid strong{display:block;margin-top:3px;overflow-wrap:anywhere}.m17-target{background:#eff6ff;border:1px solid #bfdbfe;border-radius:9px;padding:12px;margin:10px 0}.m17-target code{font-size:.82rem}.m17-link{border-top:1px solid #dbe3ef;margin-top:12px;padding-top:11px}.m17-link a{font-weight:800;color:#1d4ed8}.m17-integrity{margin-top:16px}.m17-integrity.ok{border-left:4px solid #16803c}.m17-integrity.warn{border-left:4px solid #d92d20}.m17-action-note{font-size:.86rem;color:#667085}.m17-occurrence{margin:12px 0;padding:12px;border:1px solid #d0d5dd;border-radius:10px;background:#fff}.m17-occurrence summary{cursor:pointer;font-weight:800}.m17-trace-table td,.m17-trace-table th{font-size:.82rem}.m17-trace-table code{overflow-wrap:anywhere}@media(max-width:900px){.m17-precision-grid{grid-template-columns:1fr}}
"""

_AI_USED_SENTENCE = (
    "Análises semânticas utilizaram o provider externo configurado. O relatório reutiliza somente resultados normalizados e persistidos; "
    "credenciais não são incluídas e nenhuma chamada livre adicional é feita para redigir remediações."
)


class M17ReportBuilder(M16ReportBuilder):
    """Replace generic M16 remediation copy with precise M17 occurrence diagnosis."""

    def __init__(self) -> None:
        super().__init__()
        self._m17_precision: dict[str, RootCausePrecision] = {}

    def build(self, *, audit_id: str, workspace: AuditWorkspace) -> str:
        with M17PrecisionPersistence(workspace) as store:
            self._m17_precision = {item.finding_id: item for item in store.list_for_audit(audit_id)}
        html = super().build(audit_id=audit_id, workspace=workspace)
        html = html.replace("</style>", f"{_M17_CSS}</style>", 1)

        findings, semantic, integrity = _load_report_state(audit_id, workspace)
        html = html.replace("Problemas identificados", "Findings identificados")
        html = html.replace("Principais ações necessárias", "Ações e revisões prioritárias")
        html = html.replace("Plano de correção priorizado", "Plano priorizado de ações e revisões")
        html = html.replace(_AI_USED_SENTENCE, _ai_disclaimer(semantic))
        html = _inject_actionability_metrics(html, findings)
        html = _replace_section(
            html,
            "Plano priorizado de ações e revisões",
            _prioritized_action_plan(audit_id, workspace),
        )
        html = _replace_section(
            html,
            "Correções técnicas detalhadas",
            _compact_detailed_corrections(audit_id, workspace),
        )
        html = _inject_integrity(html, integrity)
        return html

    def _finding_detail(
        self,
        *,
        finding: sqlite3.Row,
        page: sqlite3.Row,
        evidence_by_id: dict[str, sqlite3.Row],
        observations: list[sqlite3.Row],
        priority: str,
    ) -> str:
        # Bypass M16's generic block. M17 keeps evidence/location in report.html
        # and centralizes the full recipe in remediation.html.
        html = M15ReportBuilder._finding_detail(
            self,
            finding=finding,
            page=page,
            evidence_by_id=evidence_by_id,
            observations=observations,
            priority=priority,
        )
        analysis = self._m16_analyses.get(str(finding["finding_id"]))
        precision = self._m17_precision.get(str(finding["finding_id"]))
        if analysis is None or precision is None:
            return html
        prefix = html.split("<h4>Problema</h4>", 1)[0]
        block = _precision_block(analysis, precision, page_label=str(page["normalized_url"]), full=False)
        return (
            prefix
            + block
            + "<p class='m17-link'><a href='remediation.html'>Abrir detalhamento completo desta remediação em remediation.html →</a></p>"
            + "</article>"
        )


class M17RemediationReportBuilder(M16RemediationReportBuilder):
    """Keep recipe once per problem and precise diagnosis once per occurrence."""

    def __init__(self) -> None:
        super().__init__()
        self._m17_precision: dict[str, RootCausePrecision] = {}

    def build(self, *, audit_id: str, workspace: AuditWorkspace) -> str:
        with M17PrecisionPersistence(workspace) as store:
            self._m17_precision = {item.finding_id: item for item in store.list_for_audit(audit_id)}
        html = super().build(audit_id=audit_id, workspace=workspace)
        html = html.replace("</style>", f"{_M17_CSS}</style>", 1)
        html = html.replace("Problemas agrupados", "Achados e remediações agrupados")
        html = html.replace("Problemas globais", "Achados globais")
        html = html.replace("Problemas por página", "Achados por página")
        return html

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
        # Bypass M16's occurrence block so M17 does not duplicate root-cause text.
        html = M15RemediationReportBuilder._group_card(
            self,
            key=key,
            rows=rows,
            page_by_id=page_by_id,
            page_anchor=page_anchor,
            obs_by_finding=obs_by_finding,
            priorities=priorities,
        )
        occurrences: list[str] = []
        for row in rows:
            finding_id = str(row["finding_id"])
            analysis = self._m16_analyses.get(finding_id)
            precision = self._m17_precision.get(finding_id)
            if analysis is None or precision is None:
                continue
            page = page_by_id.get(row["page_id"]) if row["page_id"] else None
            page_label = _short_path(str(page["normalized_url"])) if page is not None else "DOMÍNIO / RECURSO GLOBAL"
            occurrences.append(
                "<details class='m17-occurrence'>"
                f"<summary>{escape(page_label)} · {escape(str(row['device'] or 'GLOBAL'))} · diagnóstico técnico</summary>"
                f"{_precision_block(analysis, precision, page_label=page_label, full=True)}"
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


def _precision_block(
    analysis: RootCauseAnalysis,
    precision: RootCausePrecision,
    *,
    page_label: str,
    full: bool,
) -> str:
    observed_selector = precision.observed_selector or (
        "NÃO APLICÁVEL" if precision.observed_element_status in {"ABSENT", "NOT_APPLICABLE"} else "NÃO DETERMINADO"
    )
    target_selector = precision.target_selector or "NÃO APLICÁVEL"
    target_element = precision.target_element or "NÃO APLICÁVEL"
    target_location = precision.target_location or "NÃO APLICÁVEL"
    reason = precision.reason_code or "NÃO DETERMINADO"
    elements = _elements_table(analysis.affected_elements, precision.observed_element_status)
    observed = _json_pre(analysis.observed_value)
    recipe = recipe_for(analysis.rule_id)
    details = ""
    if full:
        acceptance = "".join(f"<li>{escape(item)}</li>" for item in analysis.acceptance_criteria)
        validation = "".join(f"<li>{escape(item)}</li>" for item in analysis.revalidation_steps)
        example = (
            f"<details><summary>Exemplo pós-correção</summary><pre><code>{escape(analysis.example_after)}</code></pre></details>"
            if analysis.example_after else ""
        )
        human = (
            f"<div class='m16-decision'><strong>Decisão humana necessária</strong><br>{escape(analysis.human_decision_required)}</div>"
            if analysis.human_decision_required else ""
        )
        details = (
            f"{example}{human}<h5>Critério de aceite</h5><ul>{acceptance}</ul>"
            f"<h5>Revalidação</h5><ol>{validation}</ol>"
        )
    return f"""
    <section class="m16-root m17-precision">
      <h4>Diagnóstico de causa raiz</h4>
      <div class="m17-precision-grid">
        <div><small>Causa</small><strong>{escape(analysis.cause_type)}</strong></div>
        <div><small>Motivo técnico</small><strong>{escape(reason)}</strong></div>
        <div><small>Escopo afetado</small><strong>{escape(analysis.affected_scope)}</strong></div>
        <div><small>Elemento observado</small><strong>{escape(precision.observed_element_status)}</strong></div>
        <div><small>Selector observado</small><strong>{escape(observed_selector)}</strong></div>
        <div><small>Precisão diagnóstica</small><strong>{escape(analysis.diagnostic_confidence)}</strong></div>
        <div><small>Local</small><strong>{escape(page_label)}</strong></div>
        <div><small>Regra</small><strong>{escape(analysis.rule_id)}</strong></div>
      </div>
      <p><strong>Causa raiz:</strong> {escape(precision.precise_cause_summary)}</p>
      <p class="m17-action-note"><strong>Recipe técnica:</strong> {escape(recipe.title)}</p>
      <h5>Elemento(s) efetivamente observado(s)</h5>{elements}
      <div class="m17-target"><strong>Alvo técnico da correção - não confundir com elemento observado</strong><br>
        Elemento/estrutura: <code>{escape(target_element)}</code><br>
        Selector técnico alvo: <code>{escape(target_selector)}</code><br>
        Local esperado: <code>{escape(target_location)}</code>
      </div>
      <h5>Observado versus esperado</h5>
      <div class="m17-precision-grid">
        <div><small>Observado</small>{observed}</div>
        <div><small>Condição esperada</small><strong>{escape(analysis.expected_condition or 'NÃO DETERMINADO')}</strong></div>
        <div><small>Evidências-base</small><strong>{escape(', '.join(analysis.evidence_basis) or 'NÃO DETERMINADO')}</strong></div>
      </div>
      <h5>Mudança recomendada</h5><div class="m16-change">{escape(analysis.exact_change)}</div>
      {details}
    </section>
    """


def _elements_table(elements: tuple[AffectedElement, ...], status: str) -> str:
    if not elements:
        if status == "ABSENT":
            return (
                "<div class='notice notice-unknown'><strong>Elemento observado: AUSENTE.</strong><br>"
                "Não existe selector observado porque o nó esperado não foi encontrado. O selector técnico alvo é mostrado separadamente como orientação de implementação.</div>"
            )
        if status == "NOT_APPLICABLE":
            return "<div class='notice notice-unknown'>Esta causa pertence a recurso/documento e não possui nó DOM aplicável.</div>"
        return "<div class='notice notice-unknown'>Nenhum nó DOM pôde ser atribuído com segurança a esta ocorrência.</div>"
    rows: list[str] = []
    for element in elements:
        name = element.tag_name or "NÃO DETERMINADO"
        if element.element_id:
            name += f"#{element.element_id}"
        if element.classes:
            name += "." + ".".join(element.classes[:4])
        observed_html = (
            f"<details><summary>HTML observado</summary><pre><code>{escape(element.outer_html)}</code></pre></details>"
            if element.outer_html else "Trecho HTML não persistido"
        )
        rows.append(
            "<tr>"
            f"<td>{escape(element.relation)}</td>"
            f"<td class='m16-code'>{escape(element.selector or 'NÃO DETERMINADO')}</td>"
            f"<td class='m16-code'>{escape(name)}</td>"
            f"<td>{observed_html}</td>"
            "</tr>"
        )
    return (
        "<table class='m16-element-table'><thead><tr><th>Relação</th><th>Selector observado</th><th>Elemento</th><th>Evidência HTML</th></tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table>"
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


def _load_report_state(
    audit_id: str,
    workspace: AuditWorkspace,
) -> tuple[list[sqlite3.Row], list[sqlite3.Row], dict[str, list[sqlite3.Row]]]:
    connection = sqlite3.connect(workspace.database)
    connection.row_factory = sqlite3.Row
    try:
        findings = list(connection.execute(
            """
            SELECT f.*, re.result AS rule_result, re.observed_value AS execution_observed_value
            FROM findings f JOIN rule_executions re ON re.rule_execution_id=f.rule_execution_id
            WHERE f.audit_id=? ORDER BY f.finding_id
            """,
            (audit_id,),
        ).fetchall())
        semantic = _query_optional(
            connection,
            """
            SELECT sa.provider, sa.model, sa.result
            FROM semantic_assessments sa
            JOIN page_snapshots ps ON ps.snapshot_id=sa.snapshot_id
            JOIN pages p ON p.page_id=ps.page_id
            WHERE p.audit_id=?
            """,
            (audit_id,),
        )
        actionable = list(connection.execute(
            """
            SELECT re.* FROM rule_executions re
            WHERE re.audit_id=? AND re.result IN ('FAIL','WARNING')
            ORDER BY re.rule_id,re.rule_execution_id
            """,
            (audit_id,),
        ).fetchall())
        mapped = {
            str(row["rule_execution_id"])
            for row in connection.execute(
                "SELECT rule_execution_id FROM findings WHERE audit_id=?",
                (audit_id,),
            ).fetchall()
        }
        orphan = [row for row in actionable if str(row["rule_execution_id"]) not in mapped]
        unexpected = [row for row in findings if str(row["rule_result"]) not in {"FAIL", "WARNING"}]
        return findings, semantic, {"orphan": orphan, "unexpected": unexpected}
    finally:
        connection.close()


def _ai_disclaimer(rows: list[Any]) -> str:
    providers = {str(row["provider"]).upper() for row in rows if row["provider"]}
    external = sorted(
        item for item in providers
        if item not in {"", "NONE", "FALLBACK", "UNAVAILABLE", "DETERMINISTIC", "DETERMINISTIC_BASELINE"}
    )
    unavailable = "UNAVAILABLE" in providers
    if external and unavailable:
        return (
            f"Provider(s) externo(s) {', '.join(external)} produziram resultados válidos em parte da auditoria, mas também houve chamadas ou respostas rejeitadas/indisponíveis. "
            "Somente respostas normalizadas e persistidas são consideradas análises externas concluídas."
        )
    if external:
        return (
            f"Análises semânticas externas foram concluídas e persistidas com provider(s) {', '.join(external)}. "
            "O relatório não realiza chamada livre adicional para redigir remediações."
        )
    if unavailable:
        return (
            "O provider externo foi configurado e houve tentativa de uso, mas nenhuma análise semântica externa válida foi concluída nesta auditoria. "
            "A resposta foi indisponível ou rejeitada pelo contrato evidence-bound; o baseline determinístico permanece o fallback quando aplicável."
        )
    return (
        "Nenhuma análise semântica externa concluída foi persistida nesta auditoria. "
        "Ausência de IA pode reduzir cobertura sem penalizar automaticamente o website."
    )

def _inject_actionability_metrics(html: str, findings: list[sqlite3.Row]) -> str:
    counts = {action: 0 for action in Actionability}
    for row in findings:
        action = classify_actionability(
            row["rule_result"],
            rule_id=str(row["rule_id"]),
            observed_value=_json_object(row["execution_observed_value"]),
        )
        counts[action] += 1
    extra = (
        f"<div class='metric'><small>Ações necessárias</small><strong>{counts[Actionability.REQUIRED_FIX]}</strong></div>"
        f"<div class='metric'><small>Revisões recomendadas</small><strong>{counts[Actionability.REVIEW_RECOMMENDED]}</strong></div>"
        f"<div class='metric'><small>Melhorias opcionais</small><strong>{counts[Actionability.OPTIONAL_IMPROVEMENT]}</strong></div>"
    )
    pattern = re.compile(r"(<div class='metric'><small>Findings identificados</small><strong>\d+</strong></div>)")
    return pattern.sub(r"\1" + extra, html, count=1)


def _prioritized_action_plan(audit_id: str, workspace: AuditWorkspace) -> str:
    connection = sqlite3.connect(workspace.database)
    connection.row_factory = sqlite3.Row
    try:
        group_rows = _query_optional(
            connection,
            "SELECT * FROM remediation_groups WHERE audit_id=?",
            (audit_id,),
        )
        groups = {str(row["group_id"]): row for row in group_rows}
        recommendations = _query_optional(
            connection,
            "SELECT * FROM recommendations WHERE audit_id=? ORDER BY priority_score DESC,recommendation_id",
            (audit_id,),
        )
        finding_rows = list(connection.execute(
            """
            SELECT f.*, re.result AS rule_result, re.observed_value AS execution_observed_value
            FROM findings f JOIN rule_executions re ON re.rule_execution_id=f.rule_execution_id
            WHERE f.audit_id=?
            """,
            (audit_id,),
        ).fetchall())
        finding_by_id = {str(row["finding_id"]): row for row in finding_rows}
    finally:
        connection.close()
    if not recommendations:
        return "<section><h2>Plano priorizado de ações e revisões</h2><p class='muted'>Nenhuma recomendação persistida disponível.</p></section>"
    cards: list[str] = []
    for recommendation in recommendations:
        group = groups.get(str(recommendation["remediation_group_id"]))
        if group is None:
            continue
        affected = [str(item) for item in _json_list(group["affected_findings"])]
        finding = next((finding_by_id.get(item) for item in affected if finding_by_id.get(item)), None)
        if finding is None:
            continue
        action = classify_actionability(
            finding["rule_result"],
            rule_id=str(finding["rule_id"]),
            observed_value=_json_object(finding["execution_observed_value"]),
        )
        priority = str(recommendation["priority_class"])
        title = _action_title(action, str(finding["title"]))
        note = _priority_action_note(action, priority)
        cards.append(
            f"""
            <article class="recommendation state-{_priority_state(priority)}">
              <div class="finding-head">
                <span class="badge priority-{escape(priority.lower())}">{escape(label_for(action))} · {escape(priority)}</span>
                <span class="rule">{escape(str(group['rule_id']))} · {float(recommendation['priority_score']):.2f}</span>
              </div>
              <h3>{escape(title)}</h3>
              <p><strong>Achado:</strong> {escape(str(finding['title']))}</p>
              <p>{escape(str(recommendation['description']))}</p>
              <p class="m17-action-note">{escape(note)}</p>
              <div class="pill-row"><span>Dispositivo: {escape(str(recommendation['device']))}</span><span>Impacto: {escape(str(recommendation['impact']))}</span><span>Esforço: {escape(str(recommendation['effort']))}</span><span>Confiabilidade: {escape(str(recommendation['confidence']))}</span></div>
              <p class="muted">Escopo: {len(affected)} finding(s), {len(_json_list(group['affected_pages']))} página(s).</p>
            </article>
            """
        )
    return "<section><h2>Plano priorizado de ações e revisões</h2>" + "".join(cards) + "</section>"


def _action_title(action: Actionability, finding_title: str) -> str:
    if action is Actionability.REQUIRED_FIX:
        return f"Corrigir: {finding_title}"
    if action is Actionability.REVIEW_RECOMMENDED:
        return f"Revisar: {finding_title}"
    if action is Actionability.OPTIONAL_IMPROVEMENT:
        return f"Melhoria opcional: {finding_title}"
    if action is Actionability.INSUFFICIENT_EVIDENCE:
        return f"Investigar evidência: {finding_title}"
    return finding_title


def _priority_action_note(action: Actionability, priority: str) -> str:
    if action is Actionability.REVIEW_RECOMMENDED:
        return f"{priority} ordena a revisão recomendada; não converte o achado em falha comprovada nem em ação obrigatória."
    if action is Actionability.INSUFFICIENT_EVIDENCE:
        return f"{priority} ordena a investigação; não autoriza alteração do site sem evidência adicional."
    return f"{priority} ordena este item dentro de sua classe de actionability; prioridade não altera o RuleResult."


def _compact_detailed_corrections(audit_id: str, workspace: AuditWorkspace) -> str:
    connection = sqlite3.connect(workspace.database)
    connection.row_factory = sqlite3.Row
    try:
        rows = list(connection.execute(
            """
            SELECT f.*, re.result AS rule_result, re.observed_value AS execution_observed_value
            FROM findings f JOIN rule_executions re ON re.rule_execution_id=f.rule_execution_id
            WHERE f.audit_id=? ORDER BY f.rule_id,f.finding_id
            """,
            (audit_id,),
        ).fetchall())
    finally:
        connection.close()

    trace_rows: list[str] = []
    for row in rows:
        action = classify_actionability(
            row["rule_result"],
            rule_id=str(row["rule_id"]),
            observed_value=_json_object(row["execution_observed_value"]),
        )
        evidence_ids = [str(item) for item in _json_list(row["evidence_ids"])]
        recipe = recipe_for(str(row["rule_id"]))
        trace_rows.append(
            "<tr>"
            f"<td><code>{escape(str(row['rule_id']))}</code></td>"
            f"<td>{escape(label_for(action))}</td>"
            f"<td>{escape(recipe.title)}</td>"
            f"<td><code>{escape(', '.join(evidence_ids) or 'NÃO DETERMINADO')}</code></td>"
            "</tr>"
        )
    table = (
        "<div class='table-wrap'><table class='m17-trace-table'><thead><tr>"
        "<th>Regra</th><th>Actionability</th><th>Recipe técnica</th><th>Evidências</th>"
        "</tr></thead><tbody>" + "".join(trace_rows) + "</tbody></table></div>"
        if trace_rows else "<p class='muted'>Nenhum finding persistido para remediação.</p>"
    )
    return f"""
    <section>
      <h2>Correções técnicas detalhadas</h2>
      <p class="section-intro">Para reduzir duplicação, o diagnóstico técnico por ocorrência aparece uma vez em cada finding da seção Página por página. Esta tabela preserva a rastreabilidade mínima entre regra, actionability, recipe e evidências. Exemplo, aceite, revalidação e todas as ocorrências ficam consolidados em <code>remediation.html</code>.</p>
      {table}
      <p class="m17-link"><a href="remediation.html">Abrir achados e remediações agrupados →</a></p>
    </section>
    """


def _inject_integrity(html: str, integrity: dict[str, list[sqlite3.Row]]) -> str:
    orphan = integrity.get("orphan", [])
    unexpected = integrity.get("unexpected", [])
    if not orphan and not unexpected:
        block = (
            "<div class='notice notice-info m17-integrity ok'><strong>Integridade RuleExecution → Finding: OK</strong><br>"
            "Todas as execuções FAIL/WARNING possuem finding correspondente e todos os findings apontam para resultado acionável.</div>"
        )
    else:
        rows: list[str] = []
        for row in orphan:
            rows.append(
                f"<tr><td>EXECUÇÃO SEM FINDING</td><td>{escape(str(row['rule_id']))}</td><td>{escape(str(row['result']))}</td><td>{escape(str(row['device'] or 'GLOBAL'))}</td><td class='mono'>{escape(str(row['rule_execution_id']))}</td></tr>"
            )
        for row in unexpected:
            rows.append(
                f"<tr><td>FINDING COM RESULTADO INESPERADO</td><td>{escape(str(row['rule_id']))}</td><td>{escape(str(row['rule_result']))}</td><td>{escape(str(row['device'] or 'GLOBAL'))}</td><td class='mono'>{escape(str(row['rule_execution_id']))}</td></tr>"
            )
        block = (
            "<div class='notice notice-warning m17-integrity warn'><strong>Integridade RuleExecution → Finding: ATENÇÃO</strong><br>"
            "A tabela abaixo expõe divergências de projeção. Elas não são convertidas automaticamente em novos findings porque isso alteraria semântica de regras sem revisão da origem."
            "<div class='table-wrap'><table><thead><tr><th>Tipo</th><th>Regra</th><th>Resultado</th><th>Device</th><th>ID</th></tr></thead><tbody>"
            + "".join(rows)
            + "</tbody></table></div></div>"
        )
    pattern = re.compile(r"(<section>\s*<h2>Detalhes técnicos</h2>.*?)(</section>)", re.DOTALL)
    return pattern.sub(lambda match: match.group(1) + block + match.group(2), html, count=1)


def _replace_section(html: str, heading: str, replacement: str) -> str:
    pattern = re.compile(rf"<section>\s*<h2>{re.escape(heading)}</h2>.*?</section>", re.DOTALL)
    return pattern.sub(replacement, html, count=1)


def _query_optional(connection: sqlite3.Connection, sql: str, params: tuple[Any, ...]) -> list[sqlite3.Row]:
    try:
        return list(connection.execute(sql, params).fetchall())
    except sqlite3.OperationalError as exc:
        if "no such table" in str(exc).lower():
            return []
        raise


def _priority_state(priority: str) -> str:
    return {"P0": "critical", "P1": "problem", "P2": "warning"}.get(priority, "unknown")


def _json_list(value: Any) -> list[Any]:
    if value in (None, ""):
        return []
    if isinstance(value, list):
        return value
    try:
        parsed = json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
    return parsed if isinstance(parsed, list) else []


def _json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if value in (None, ""):
        return {}
    try:
        parsed = json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}
