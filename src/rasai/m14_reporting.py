"""M14 page-oriented reporting projection over persisted audit state."""

from __future__ import annotations

from datetime import datetime
from html import escape
import json
from pathlib import Path
import sqlite3
from typing import Any

from rasai.actionability import Actionability, classify_actionability, label_for
from rasai.domain import new_id, utc_now
from rasai.persistence import AuditWorkspace
from rasai.remediation import recipe_for
from rasai.reporting import ReportBuilder, ReportRecord
from rasai.rule_references import references_for


TEMPLATE_VERSION = "REPORT-GEO-003"

_RESULT_LABELS = {
    "PASS": "APROVADO",
    "FAIL": "PROBLEMA",
    "WARNING": "ALERTA",
    "UNKNOWN": "NÃO DETERMINADO",
    "NOT_APPLICABLE": "NÃO APLICÁVEL",
    "ERROR": "ERRO DE ANÁLISE",
}
_ACTION_CLASS = {
    Actionability.REQUIRED_FIX: "required",
    Actionability.REVIEW_RECOMMENDED: "review",
    Actionability.OPTIONAL_IMPROVEMENT: "optional",
    Actionability.NO_ACTION: "none",
    Actionability.INSUFFICIENT_EVIDENCE: "insufficient",
}
_CATEGORY_WHY = {
    "TECHNICAL_ACCESSIBILITY": "A capacidade de recuperar a página é pré-condição para que sistemas externos possam observar e processar seu conteúdo.",
    "DISCOVERY": "Descoberta rastreável reduz ambiguidade sobre quais URLs pertencem ao universo auditável; não é promessa de indexação ou ranking.",
    "ROBOTS": "Políticas de crawler podem permitir ou impedir aquisição técnica por agentes específicos e devem refletir a intenção aprovada da organização.",
    "INDEXABILITY": "Sinais de indexação e canonicalização inconsistentes podem tornar incerta a versão que sistemas externos devem processar.",
    "CANONICAL": "Canonicalização consistente ajuda a reduzir ambiguidade entre URLs equivalentes sem permitir que o auditor invente a URL preferencial.",
    "CONTENT_EXTRACTABILITY": "Conteúdo que não pode ser extraído de forma estável reduz a evidência disponível para análise e resposta.",
    "JAVASCRIPT_RENDERING": "Diferenças entre RAW e DOM renderizado podem alterar o conteúdo efetivamente observável após JavaScript.",
    "SEMANTIC_STRUCTURE": "Estrutura explícita reduz inferência necessária para identificar tópico, seções e relações do conteúdo.",
    "ENTITY_CLARITY": "Entidades claramente identificadas reduzem ambiguidade sem exigir que o auditor crie fatos ou relações ausentes.",
    "STRUCTURED_DATA": "Dados estruturados só são úteis quando interpretáveis e coerentes com o conteúdo realmente observado.",
    "ANSWERABILITY": "Respostas explícitas e contextualizadas aumentam a recuperabilidade do conteúdo sem criar fatos novos.",
    "CITATION_READINESS": "Afirmações factuais claras e contextualizadas tornam a evidência mais verificável e citável.",
    "EVIDENCE_TRUST": "Atribuição, responsabilidade e sinais de atualização consistentes aumentam a rastreabilidade da evidência.",
    "INTENT_COVERAGE": "Cobertura de intenções deve ser sustentada pelo conteúdo existente; lacunas não autorizam o auditor a inventar respostas.",
}

_M14_CSS = r"""
        html,body,.page,section,.hero,article,.metric,.detail-grid>div,.recipe-grid>div{min-width:0}
        .page,section,.hero,article,div,span,strong,p,li,td,th,dt,dd,a{overflow-wrap:anywhere}
        pre,code{max-width:100%;white-space:pre-wrap;overflow-wrap:anywhere;word-break:break-word}
        pre{overflow-x:auto}
        h1{font-size:clamp(1.75rem,4vw,2.25rem)}h2{font-size:clamp(1.2rem,3vw,1.45rem)}
        .m14-executive{border-top:6px solid var(--info)}
        .m14-nav{display:flex;flex-wrap:wrap;gap:8px;margin:14px 0}.m14-nav a{background:#eef4ff;border:1px solid #d9e5ff;border-radius:999px;padding:6px 10px;text-decoration:none;color:#1f56a8;font-weight:700;font-size:.82rem}
        .url-inventory{margin:0;padding-left:1.4rem}.url-inventory li{margin:7px 0}.url-inventory a{font-family:ui-monospace,SFMono-Regular,Menlo,monospace}
        .actionability{font-weight:900;letter-spacing:.02em}.action-required{color:#b42318}.action-review{color:#9c6e00}.action-optional{color:#175cd3}.action-none{color:#16803c}.action-insufficient{color:#667085}
        .status-legend{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:10px}.status-legend>div{border:1px solid var(--border);border-radius:10px;padding:11px;background:#fafbfd}.status-legend strong{display:block;margin-bottom:3px}
        .page-audit{scroll-margin-top:16px;border-top:6px solid #344054}.page-url{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:clamp(1rem,2.4vw,1.3rem);word-break:break-word}
        .snapshot-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px;margin:16px 0}.snapshot-card{border:1px solid var(--border);border-radius:12px;padding:14px;min-width:0}.snapshot-card dl{grid-template-columns:130px minmax(0,1fr)}
        .visual-frame{position:relative;display:block;max-width:100%;margin-top:10px;border:1px solid var(--border);border-radius:10px;overflow:hidden;background:#f6f8fb}.visual-frame img{display:block;width:100%;height:auto;max-width:100%}.visual-box{position:absolute;border:3px solid #d92d20;background:rgba(217,45,32,.08);pointer-events:none}
        .m14-finding{border:1px solid var(--border);border-left:6px solid #98a2b3;border-radius:12px;padding:17px;margin:12px 0;min-width:0}.m14-finding.action-required{border-left-color:#d92d20}.m14-finding.action-review{border-left-color:#dc9900}.m14-finding.action-optional{border-left-color:#2e64d6}.m14-finding.action-insufficient{border-left-color:#667085}.m14-finding h4{margin-top:14px}
        .m14-detail{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:9px}.m14-detail>div{background:#f8fafc;border-radius:8px;padding:9px;min-width:0}.m14-detail small{display:block;color:#667085}.m14-detail strong{display:block}
        .technical-ref{border:1px solid #e5eaf1;border-radius:9px;padding:10px;margin:8px 0;background:#fbfcfe}.technical-ref a{font-weight:800}
        .sitemap-card,.robots-card{border:1px solid var(--border);border-radius:12px;padding:15px;margin:10px 0}.resource-url{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;word-break:break-word}
        .score-state-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.score-state-card{border:1px solid var(--border);border-radius:12px;padding:14px}.score-state-card strong{display:block;font-size:1.2rem}
        @media(max-width:760px){.snapshot-grid,.score-state-grid{grid-template-columns:1fr}.snapshot-card dl{grid-template-columns:1fr}.m14-nav{display:grid;grid-template-columns:1fr}.m14-nav a{text-align:left}}
"""


class M14ReportBuilder:
    """Augment the stable M13 report with M14 persisted visual/page evidence."""

    def build(self, *, audit_id: str, workspace: AuditWorkspace) -> str:
        base_html = ReportBuilder().build(audit_id=audit_id, workspace=workspace)
        connection = sqlite3.connect(workspace.database)
        connection.row_factory = sqlite3.Row
        try:
            audit = connection.execute("SELECT * FROM audits WHERE audit_id = ?", (audit_id,)).fetchone()
            if audit is None:
                raise ValueError(f"audit not found: {audit_id}")
            target = connection.execute(
                "SELECT * FROM audit_targets WHERE audit_id = ? ORDER BY rowid LIMIT 1", (audit_id,)
            ).fetchone()
            pages = list(connection.execute(
                "SELECT * FROM pages WHERE audit_id = ? ORDER BY depth, normalized_url", (audit_id,)
            ).fetchall())
            snapshots = list(connection.execute(
                """
                SELECT ps.*, p.normalized_url
                FROM page_snapshots ps JOIN pages p ON p.page_id = ps.page_id
                WHERE p.audit_id = ? ORDER BY p.normalized_url, ps.device
                """,
                (audit_id,),
            ).fetchall())
            findings = list(connection.execute(
                """
                SELECT f.*, re.result AS rule_result, re.snapshot_id AS execution_snapshot_id,
                       re.observed_value AS execution_observed_value
                FROM findings f
                JOIN rule_executions re ON re.rule_execution_id = f.rule_execution_id
                WHERE f.audit_id = ?
                ORDER BY f.page_id, f.rule_id, f.finding_id
                """,
                (audit_id,),
            ).fetchall())
            evidence = list(connection.execute(
                "SELECT * FROM evidence WHERE audit_id = ? ORDER BY evidence_id", (audit_id,)
            ).fetchall())
            scores = self._query_optional(
                connection, "SELECT * FROM scores WHERE audit_id = ? ORDER BY device, dimension", (audit_id,)
            )
            inputs = self._query_optional(
                connection, "SELECT * FROM audit_input_urls WHERE audit_id = ? ORDER BY position", (audit_id,)
            )
            observations = self._query_optional(
                connection,
                """
                SELECT feo.finding_id, eo.*
                FROM finding_element_observations feo
                JOIN element_observations eo ON eo.element_observation_id = feo.element_observation_id
                WHERE eo.audit_id = ? ORDER BY feo.finding_id, eo.element_observation_id
                """,
                (audit_id,),
            )
            groups = self._query_optional(
                connection, "SELECT * FROM remediation_groups WHERE audit_id = ?", (audit_id,)
            )
            recommendations = self._query_optional(
                connection, "SELECT * FROM recommendations WHERE audit_id = ?", (audit_id,)
            )
            semantic = self._query_optional(
                connection,
                """
                SELECT DISTINCT sa.provider, sa.model
                FROM semantic_assessments sa
                JOIN page_snapshots ps ON ps.snapshot_id = sa.snapshot_id
                JOIN pages p ON p.page_id = ps.page_id
                WHERE p.audit_id = ? ORDER BY sa.provider, sa.model
                """,
                (audit_id,),
            )
        finally:
            connection.close()

        evidence_by_id = {row["evidence_id"]: row for row in evidence}
        observations_by_finding: dict[str, list[sqlite3.Row]] = {}
        for row in observations:
            observations_by_finding.setdefault(row["finding_id"], []).append(row)
        priority_by_finding = self._priority_map(groups, recommendations)
        page_by_id = {row["page_id"]: row for row in pages}
        snapshots_by_page: dict[str, dict[str, sqlite3.Row]] = {}
        for snapshot in snapshots:
            snapshots_by_page.setdefault(snapshot["page_id"], {})[snapshot["device"]] = snapshot
        findings_by_page: dict[str, list[sqlite3.Row]] = {}
        global_findings: list[sqlite3.Row] = []
        for finding in findings:
            if finding["page_id"]:
                findings_by_page.setdefault(finding["page_id"], []).append(finding)
            else:
                global_findings.append(finding)

        domain = target["normalized_origin"] if target is not None else self._infer_domain(pages)
        target_type = target["target_type"] if target is not None else "NÃO DETERMINADO"
        supplied_count = len(inputs) if inputs else (1 if target is not None else len(pages))
        input_urls = [row["normalized_url"] for row in inputs] if inputs else [row["normalized_url"] for row in pages]

        m14_body = "".join((
            self._executive(
                audit=audit,
                domain=domain,
                target_type=target_type,
                supplied_count=supplied_count,
                audited_count=len(pages),
                semantic=semantic,
            ),
            self._score_states(scores),
            self._url_inventory(input_urls, pages),
            self._status_legend(),
            self._domain_resources(
                domain=domain,
                input_urls=input_urls,
                evidence=evidence,
                global_findings=global_findings,
            ),
            self._top_actions(
                findings=findings,
                page_by_id=page_by_id,
                priority_by_finding=priority_by_finding,
            ),
            self._optional_improvements(findings=findings, evidence=evidence),
            self._page_by_page(
                workspace=workspace,
                pages=pages,
                snapshots_by_page=snapshots_by_page,
                findings_by_page=findings_by_page,
                evidence_by_id=evidence_by_id,
                observations_by_finding=observations_by_finding,
                priority_by_finding=priority_by_finding,
            ),
        ))

        html = base_html.replace("</style>", f"{_M14_CSS}</style>", 1)
        html = html.replace('<main class="page">', f'<main class="page">{m14_body}', 1)
        html = html.replace("REPORT-GEO-002", TEMPLATE_VERSION)
        return html

    @staticmethod
    def _query_optional(connection: sqlite3.Connection, sql: str, params: tuple[Any, ...]) -> list[sqlite3.Row]:
        try:
            return list(connection.execute(sql, params).fetchall())
        except sqlite3.OperationalError as exc:
            if "no such table" in str(exc).lower():
                return []
            raise

    @staticmethod
    def _priority_map(groups: list[sqlite3.Row], recommendations: list[sqlite3.Row]) -> dict[str, str]:
        rec_by_group = {row["remediation_group_id"]: row for row in recommendations if row["remediation_group_id"]}
        result: dict[str, str] = {}
        for group in groups:
            recommendation = rec_by_group.get(group["group_id"])
            priority = recommendation["priority_class"] if recommendation is not None else group["priority_class"]
            for finding_id in _json_list(group["affected_findings"]):
                result[str(finding_id)] = str(priority)
        return result

    @staticmethod
    def _infer_domain(pages: list[sqlite3.Row]) -> str:
        if not pages:
            return "NÃO DETERMINADO"
        url = str(pages[0]["normalized_url"])
        parts = url.split("/", 3)
        return "/".join(parts[:3]) if len(parts) >= 3 else url

    def _executive(
        self,
        *,
        audit: sqlite3.Row,
        domain: str,
        target_type: str,
        supplied_count: int,
        audited_count: int,
        semantic: list[sqlite3.Row],
    ) -> str:
        providers = sorted({str(row["provider"]) for row in semantic if row["provider"]})
        models = sorted({str(row["model"]) for row in semantic if row["model"]})
        ai_used = any(provider.casefold() not in {"none", "fallback", ""} for provider in providers)
        limitations = _json_list(audit["limitations"])
        limitation_text = " · ".join(str(value) for value in limitations[:4]) or "Nenhuma limitação adicional registrada."
        return f"""
        <header class="hero m14-executive" id="resumo-m14">
          <div class="eyebrow">M14 · Multi-URL · Visual/DOM Evidence · Actionability</div>
          <h1>Resumo executivo da auditoria</h1>
          <div class="meta-grid">
            {_metric("Projeto", audit['project_name'])}
            {_metric("audit_id", audit['audit_id'])}
            {_metric("Domínio", domain)}
            {_metric("Modo de entrada", target_type)}
            {_metric("URLs fornecidas", supplied_count)}
            {_metric("URLs efetivamente auditadas", audited_count)}
            {_metric("Data/hora de início", audit['started_at'] or audit['created_at'])}
            {_metric("Uso de IA", "SIM" if ai_used else "NÃO")}
            {_metric("Provider", ", ".join(providers) or "NÃO INFORMADO")}
            {_metric("Modelo", ", ".join(models) or "NÃO APLICÁVEL")}
          </div>
          <div class="notice notice-info"><strong>Limitações principais</strong><br>{escape(limitation_text)}</div>
          <nav class="m14-nav" aria-label="Navegação M14">
            <a href="#inventario-urls">Páginas auditadas</a><a href="#recursos-dominio">Recursos do domínio</a>
            <a href="#acoes-m14">Ações</a><a href="#melhorias-opcionais">Melhorias opcionais</a><a href="#paginas-m14">Página por página</a>
          </nav>
        </header>
        """

    @staticmethod
    def _score_states(scores: list[sqlite3.Row]) -> str:
        cards: list[str] = []
        for device in ("DESKTOP", "MOBILE"):
            row = next((item for item in scores if item["device"] == device and item["dimension"] == "OVERALL_READINESS"), None)
            if row is None or row["value"] is None:
                score = "NÃO DETERMINADO"
                state = "NÃO CALCULADO"
                coverage = "NÃO DISPONÍVEL" if row is None else f"{float(row['coverage']) * 100:.0f}%"
            else:
                score = f"{float(row['value']):.1f}"
                state = "CALCULADO"
                coverage = f"{float(row['coverage']) * 100:.0f}%"
            cards.append(
                f"<article class='score-state-card'><small>{escape(device.title())}</small>"
                f"<strong>Score: {escape(score)}</strong><span>Estado: {escape(state)}</span><br>"
                f"<span>Coverage: {escape(coverage)}</span></article>"
            )
        return (
            "<section><div class='section-kicker'>Zero versus ausência de cálculo</div><h2>Estado do Score GEO</h2>"
            "<p class='section-intro'>Um valor 0.0 abaixo significa score efetivamente calculado como zero. "
            "Quando faltam dados, o relatório mostra NÃO DETERMINADO / NÃO CALCULADO. Coverage permanece uma métrica separada.</p>"
            f"<div class='score-state-grid'>{''.join(cards)}</div></section>"
        )

    @staticmethod
    def _url_inventory(input_urls: list[str], pages: list[sqlite3.Row]) -> str:
        audited = {row["normalized_url"] for row in pages}
        ordered = list(dict.fromkeys(input_urls or [row["normalized_url"] for row in pages]))
        items: list[str] = []
        page_anchor = {row["normalized_url"]: f"pagina-{index}" for index, row in enumerate(pages, start=1)}
        for url in ordered:
            anchor = page_anchor.get(url)
            status = "AUDITADA" if url in audited else "NÃO AUDITADA"
            link = f"<a href='#{escape(anchor)}'>{escape(url)}</a>" if anchor else escape(url)
            items.append(f"<li>{link} <span class='badge'>{escape(status)}</span></li>")
        return f"""
        <section id="inventario-urls">
          <h2>PÁGINAS AUDITADAS</h2>
          <p class="section-intro">Inventário explícito usado para localizar cada página dentro deste mesmo audit_id.</p>
          <ol class="url-inventory">{''.join(items)}</ol>
        </section>
        """

    @staticmethod
    def _status_legend() -> str:
        rows = (
            ("PROBLEMA", "deve ser corrigido quando a regra/actionability comprova REQUIRED_FIX"),
            ("ALERTA", "revisar; pode ou não exigir alteração"),
            ("MELHORIA OPCIONAL", "boa prática recomendada, não bloqueante"),
            ("NÃO DETERMINADO", "o auditor não possui evidência suficiente"),
            ("NÃO APLICÁVEL", "nenhuma ação necessária"),
            ("APROVADO", "nenhuma ação necessária"),
        )
        cards = "".join(f"<div><strong>{escape(title)}</strong>{escape(text)}</div>" for title, text in rows)
        return f"<section><h2>Legenda de status e ação</h2><div class='status-legend'>{cards}</div></section>"

    def _domain_resources(
        self,
        *,
        domain: str,
        input_urls: list[str],
        evidence: list[sqlite3.Row],
        global_findings: list[sqlite3.Row],
    ) -> str:
        robots = next((row for row in evidence if row["evidence_type"] == "ROBOTS_RULE" and row["page_id"] is None), None)
        sitemap_rows = [row for row in evidence if row["evidence_type"] == "SITEMAP_ENTRY" and row["page_id"] is None and "state" in _json_object(row["observed_value"])]
        robots_html = self._robots_resource(domain=domain, row=robots, findings=global_findings)
        sitemaps_html = self._sitemap_resources(input_urls=input_urls, rows=sitemap_rows)
        return f"<section id='recursos-dominio'><h2>Recursos do domínio</h2>{robots_html}{sitemaps_html}</section>"

    @staticmethod
    def _robots_resource(*, domain: str, row: sqlite3.Row | None, findings: list[sqlite3.Row]) -> str:
        if row is None:
            return "<div class='robots-card'><h3>ROBOTS.TXT</h3><div class='notice notice-unknown'>Evidência de robots.txt NÃO DETERMINADA.</div></div>"
        value = _json_object(row["observed_value"])
        state = str(value.get("state") or "NÃO DETERMINADO")
        http = value.get("http") if isinstance(value.get("http"), dict) else {}
        crawler_access = value.get("crawler_access") if isinstance(value.get("crawler_access"), dict) else {}
        crawlers = ("Googlebot", "Googlebot Smartphone", "Bingbot", "OAI-SearchBot", "GPTBot")
        crawler_rows: list[str] = []
        for crawler in crawlers:
            states: list[bool | None] = []
            for page_policy in crawler_access.values():
                if isinstance(page_policy, dict):
                    states.append(page_policy.get(crawler))
            if states and any(item is False for item in states):
                policy = "BLOQUEADO EM PELO MENOS UMA URL"
            elif states and all(item is True for item in states):
                policy = "PERMITIDO NAS URLs AUDITADAS"
            else:
                policy = "NÃO DETERMINADO"
            crawler_rows.append(f"<tr><td>{escape(crawler)}</td><td>{escape(policy)}</td></tr>")
        declared = value.get("declared_sitemaps") if isinstance(value.get("declared_sitemaps"), list) else []
        related = [finding for finding in findings if finding["rule_id"] in {"BR-GEO-017", "BR-GEO-018"}]
        action_text = " · ".join(
            label_for(classify_actionability(finding["rule_result"], rule_id=finding["rule_id"], observed_value=_json_object(finding["execution_observed_value"])))
            for finding in related
        ) or "Nenhum finding global de robots persistido"
        return f"""
        <div class="robots-card">
          <h3>ROBOTS.TXT</h3>
          <div class="m14-detail">
            <div><small>URL consultada</small><strong class="resource-url">{escape(str(row['source']))}</strong></div>
            <div><small>Estado</small><strong>{escape(state)}</strong></div>
            <div><small>HTTP</small><strong>{escape(str(http.get('status') if http else 'NÃO DETERMINADO'))}</strong></div>
            <div><small>Interpretável</small><strong>{'SIM' if state == 'OBTAINED' else 'NÃO'}</strong></div>
            <div><small>Sitemap declarado</small><strong>{escape(', '.join(str(item) for item in declared) or 'NENHUM')}</strong></div>
            <div><small>Actionability</small><strong>{escape(action_text)}</strong></div>
          </div>
          <div class="table-wrap"><table><thead><tr><th>Crawler</th><th>Política observada</th></tr></thead><tbody>{''.join(crawler_rows)}</tbody></table></div>
          <p class="muted">Ausência válida de robots.txt não é tratada automaticamente como defeito. OAI-SearchBot e GPTBot permanecem avaliados separadamente.</p>
        </div>
        """

    @staticmethod
    def _sitemap_resources(*, input_urls: list[str], rows: list[sqlite3.Row]) -> str:
        obtained = [row for row in rows if _json_object(row["observed_value"]).get("state") == "OBTAINED"]
        heading = "Sitemap: LOCALIZADO" if obtained else "Sitemap: NÃO LOCALIZADO"
        cards: list[str] = []
        for row in rows:
            value = _json_object(row["observed_value"])
            state = str(value.get("state") or "NÃO DETERMINADO")
            http = value.get("http") if isinstance(value.get("http"), dict) else {}
            page_urls = value.get("page_urls") if isinstance(value.get("page_urls"), list) else []
            present = [url for url in input_urls if url in page_urls]
            absent = [url for url in input_urls if url not in page_urls]
            cards.append(f"""
            <article class="sitemap-card">
              <div class="m14-detail">
                <div><small>Origem da descoberta</small><strong>{escape(str(value.get('discovery_origin') or 'NÃO DETERMINADO'))}</strong></div>
                <div><small>URL</small><strong class="resource-url">{escape(str(row['source']))}</strong></div>
                <div><small>Estado</small><strong>{escape(state)}</strong></div>
                <div><small>HTTP</small><strong>{escape(str(http.get('status') if http else 'NÃO DETERMINADO'))}</strong></div>
                <div><small>Interpretável</small><strong>{'SIM' if state == 'OBTAINED' else 'NÃO'}</strong></div>
                <div><small>Quantidade de URLs</small><strong>{escape(str(value.get('url_count') if value.get('url_count') is not None else 'NÃO DETERMINADO'))}</strong></div>
                <div><small>URLs auditadas presentes</small><strong>{len(present)}</strong></div>
                <div><small>URLs auditadas ausentes</small><strong>{len(absent)}</strong></div>
              </div>
              <p><strong>Erro de parsing:</strong> {escape(str(value.get('error') or '-'))}</p>
              <p class="muted">Redirects e limitações permanecem rastreáveis no bloco HTTP persistido deste recurso.</p>
            </article>
            """)
        if not cards:
            cards.append("<div class='notice notice-unknown'>Nenhuma aquisição de sitemap foi persistida.</div>")
        action = (
            "<div class='notice notice-info'><strong>MELHORIA OPCIONAL</strong><br>O sitemap não foi localizado. "
            "A baseline BR-GEO-003 não transforma essa ausência, por si só, em FAIL ou penalidade de score.</div>"
            if not obtained else ""
        )
        return f"<h3 id='sitemaps'>{escape(heading)}</h3>{action}{''.join(cards)}"

    def _top_actions(
        self,
        *,
        findings: list[sqlite3.Row],
        page_by_id: dict[str, sqlite3.Row],
        priority_by_finding: dict[str, str],
    ) -> str:
        actionable: list[tuple[Actionability, sqlite3.Row]] = []
        for finding in findings:
            action = classify_actionability(
                finding["rule_result"],
                rule_id=finding["rule_id"],
                observed_value=_json_object(finding["execution_observed_value"]),
            )
            if action in {Actionability.REQUIRED_FIX, Actionability.REVIEW_RECOMMENDED, Actionability.INSUFFICIENT_EVIDENCE}:
                actionable.append((action, finding))
        if not actionable:
            content = "<p class='muted'>Nenhuma ação necessária/revisão evidence-backed foi identificada.</p>"
        else:
            cards = []
            for action, finding in actionable[:12]:
                page = page_by_id.get(finding["page_id"]) if finding["page_id"] else None
                url = page["normalized_url"] if page is not None else "Escopo global do domínio"
                cards.append(
                    f"<article class='m14-finding action-{_ACTION_CLASS[action]}'><div class='finding-head'>"
                    f"<strong class='actionability'>{escape(label_for(action))}</strong>"
                    f"<span class='rule'>{escape(str(finding['rule_id']))} · {escape(priority_by_finding.get(finding['finding_id'], 'NÃO PRIORIZADO'))}</span></div>"
                    f"<h3>{escape(str(finding['title']))}</h3><p class='resource-url'>{escape(str(url))}</p></article>"
                )
            content = "".join(cards)
        return f"<section id='acoes-m14'><h2>Principais ações necessárias</h2>{content}</section>"

    @staticmethod
    def _optional_improvements(*, findings: list[sqlite3.Row], evidence: list[sqlite3.Row]) -> str:
        cards: list[str] = []
        for finding in findings:
            action = classify_actionability(
                finding["rule_result"],
                rule_id=finding["rule_id"],
                observed_value=_json_object(finding["execution_observed_value"]),
            )
            if action is Actionability.OPTIONAL_IMPROVEMENT:
                cards.append(f"<article class='m14-finding action-optional'><strong>MELHORIA OPCIONAL</strong><h3>{escape(str(finding['title']))}</h3><p>Regra {escape(str(finding['rule_id']))}; não bloqueante.</p></article>")
        sitemap_states = [
            _json_object(row["observed_value"]).get("state")
            for row in evidence
            if row["evidence_type"] == "SITEMAP_ENTRY" and row["page_id"] is None and "state" in _json_object(row["observed_value"])
        ]
        if sitemap_states and not any(state == "OBTAINED" for state in sitemap_states):
            cards.append(
                "<article class='m14-finding action-optional'><strong>MELHORIA OPCIONAL</strong>"
                "<h3>Disponibilizar sitemap interpretável, se útil à estratégia do site</h3>"
                "<p>A ausência foi observada, mas não constitui FAIL automático nem reduz score apenas por não se aplicar.</p></article>"
            )
        if not cards:
            cards.append("<p class='muted'>Nenhuma melhoria opcional evidence-backed foi identificada nesta execução.</p>")
        return f"<section id='melhorias-opcionais'><h2>Melhorias recomendadas - não bloqueantes</h2>{''.join(cards)}</section>"

    def _page_by_page(
        self,
        *,
        workspace: AuditWorkspace,
        pages: list[sqlite3.Row],
        snapshots_by_page: dict[str, dict[str, sqlite3.Row]],
        findings_by_page: dict[str, list[sqlite3.Row]],
        evidence_by_id: dict[str, sqlite3.Row],
        observations_by_finding: dict[str, list[sqlite3.Row]],
        priority_by_finding: dict[str, str],
    ) -> str:
        page_sections: list[str] = []
        for index, page in enumerate(pages, start=1):
            snapshots = snapshots_by_page.get(page["page_id"], {})
            finding_rows = findings_by_page.get(page["page_id"], [])
            snapshot_cards = "".join(
                self._snapshot_card(workspace=workspace, device=device, snapshot=snapshots.get(device), finding_rows=finding_rows, observations_by_finding=observations_by_finding)
                for device in ("DESKTOP", "MOBILE")
            )
            detailed = "".join(
                self._finding_detail(
                    finding=finding,
                    page=page,
                    evidence_by_id=evidence_by_id,
                    observations=observations_by_finding.get(finding["finding_id"], []),
                    priority=priority_by_finding.get(finding["finding_id"], "NÃO PRIORIZADO"),
                )
                for finding in finding_rows
            ) or "<div class='notice notice-info'>Nenhum finding acionável persistido para esta página.</div>"
            requested = [snap["requested_url"] for snap in snapshots.values() if snap is not None]
            finals = [snap["final_url"] for snap in snapshots.values() if snap is not None and snap["final_url"]]
            statuses = [str(snap["http_status"]) for snap in snapshots.values() if snap is not None and snap["http_status"] is not None]
            page_sections.append(f"""
            <section class="page-audit" id="pagina-{index}">
              <div class="section-kicker">PÁGINA ANALISADA</div>
              <h2 class="page-url">{escape(str(page['normalized_url']))}</h2>
              <div class="m14-detail">
                <div><small>Requested URL</small><strong>{escape(' · '.join(dict.fromkeys(requested)) or str(page['normalized_url']))}</strong></div>
                <div><small>Final URL</small><strong>{escape(' · '.join(dict.fromkeys(finals)) or 'NÃO DETERMINADO')}</strong></div>
                <div><small>HTTP status</small><strong>{escape(' · '.join(dict.fromkeys(statuses)) or 'NÃO DETERMINADO')}</strong></div>
                <div><small>Findings da página</small><strong>{len(finding_rows)}</strong></div>
              </div>
              <div class="snapshot-grid">{snapshot_cards}</div>
              <h3>Findings e remediações da página</h3>{detailed}
            </section>
            """)
        return f"<div id='paginas-m14'><section><h2>Página por página</h2><p class='section-intro'>Desktop e Mobile permanecem snapshots independentes. Screenshots são evidência complementar ao RAW e ao DOM renderizado.</p></section>{''.join(page_sections)}</div>"

    def _snapshot_card(
        self,
        *,
        workspace: AuditWorkspace,
        device: str,
        snapshot: sqlite3.Row | None,
        finding_rows: list[sqlite3.Row],
        observations_by_finding: dict[str, list[sqlite3.Row]],
    ) -> str:
        if snapshot is None:
            return f"<article class='snapshot-card'><h3>{escape(device.title())}</h3><div class='notice notice-unknown'>Snapshot NÃO DETERMINADO.</div></article>"
        metadata = _json_object(snapshot["browser_metadata"])
        artifact = metadata.get("visual_artifact_ref") if isinstance(metadata.get("visual_artifact_ref"), str) else None
        image = self._portable_image(workspace, artifact)
        overlay = ""
        viewport = metadata.get("profile", {}).get("viewport", {}) if isinstance(metadata.get("profile"), dict) else {}
        width = _float_or_none(viewport.get("width")) if isinstance(viewport, dict) else None
        height = _float_or_none(viewport.get("height")) if isinstance(viewport, dict) else None
        if image and width and height:
            candidates: list[sqlite3.Row] = []
            for finding in finding_rows:
                if finding["execution_snapshot_id"] == snapshot["snapshot_id"]:
                    candidates.extend(observations_by_finding.get(finding["finding_id"], []))
            visual = next((row for row in candidates if row["bounding_box"]), None)
            if visual is not None:
                box = _json_object(visual["bounding_box"])
                try:
                    left = max(0.0, min(100.0, float(box["x"]) / width * 100.0))
                    top = max(0.0, min(100.0, float(box["y"]) / height * 100.0))
                    box_width = max(0.0, min(100.0 - left, float(box["width"]) / width * 100.0))
                    box_height = max(0.0, min(100.0 - top, float(box["height"]) / height * 100.0))
                    overlay = f"<span class='visual-box' style='left:{left:.3f}%;top:{top:.3f}%;width:{box_width:.3f}%;height:{box_height:.3f}%'></span>"
                except (KeyError, TypeError, ValueError, ZeroDivisionError):
                    overlay = ""
        screenshot_html = (
            f"<a class='visual-frame' href='{escape(image)}' target='_blank' rel='noopener'><img loading='lazy' src='{escape(image)}' alt='Screenshot {escape(device.title())}'>{overlay}</a>"
            if image else "<div class='notice notice-unknown'>Screenshot: NÃO DISPONÍVEL para este snapshot.</div>"
        )
        return f"""
        <article class="snapshot-card">
          <h3>{escape(device.title())}</h3>
          <dl>
            <dt>Estado</dt><dd>{'CAPTURADO' if snapshot['rendered_artifact_ref'] else 'NÃO DETERMINADO'}</dd>
            <dt>Requested URL</dt><dd>{escape(str(snapshot['requested_url']))}</dd>
            <dt>Final URL</dt><dd>{escape(str(snapshot['final_url'] or 'NÃO DETERMINADO'))}</dd>
            <dt>HTTP</dt><dd>{escape(str(snapshot['http_status'] if snapshot['http_status'] is not None else 'NÃO DETERMINADO'))}</dd>
            <dt>Viewport</dt><dd>{escape(f"{int(width)} × {int(height)}" if width and height else 'NÃO DETERMINADO')}</dd>
            <dt>Timestamp</dt><dd>{escape(str(snapshot['captured_at']))}</dd>
          </dl>
          {screenshot_html}
        </article>
        """

    def _finding_detail(
        self,
        *,
        finding: sqlite3.Row,
        page: sqlite3.Row,
        evidence_by_id: dict[str, sqlite3.Row],
        observations: list[sqlite3.Row],
        priority: str,
    ) -> str:
        action = classify_actionability(
            finding["rule_result"],
            rule_id=finding["rule_id"],
            observed_value=_json_object(finding["execution_observed_value"]),
        )
        recipe = recipe_for(finding["rule_id"])
        observation = observations[0] if len(observations) == 1 else None
        selector = observation["selector"] if observation is not None and observation["selector"] else "NÃO DETERMINADO"
        if observation is None:
            selector_reason = "finding associado ao documento/conjunto de conteúdo ou nenhum único nó DOM pôde ser atribuído com segurança."
            element = "NÃO DETERMINADO"
        else:
            classes = _json_list(observation["classes"])
            element = observation["tag_name"]
            if observation["element_id"]:
                element += f"#{observation['element_id']}"
            if classes:
                element += "." + ".".join(str(item) for item in classes[:4])
            selector_reason = "seletor reproduzível observado no DOM renderizado."
        observed_html = observation["outer_html"] if observation is not None and observation["outer_html"] else self._html_from_evidence(finding, evidence_by_id)
        observed_html_block = (
            f"<pre><code>{escape(str(observed_html))}</code></pre>"
            if observed_html else "<div class='notice notice-unknown'>Trecho HTML original não persistido para esta evidência.</div>"
        )
        references = "".join(self._reference(ref) for ref in references_for(finding["rule_id"]))
        acceptance = "".join(f"<li>{escape(item)}</li>" for item in recipe.acceptance)
        validation = "".join(f"<li>{escape(item)}</li>" for item in recipe.validation)
        example = f"<pre><code>{escape(recipe.example)}</code></pre>" if recipe.example else "<p class='muted'>Nenhum exemplo genérico é fornecido quando isso poderia fabricar conteúdo específico.</p>"
        evidence_ids = [str(item) for item in _json_list(finding["evidence_ids"])]
        why = _CATEGORY_WHY.get(str(finding["category"]), "O impacto é limitado ao escopo da regra e às evidências persistidas; o auditor não infere ranking ou citação futura.")
        return f"""
        <article class="m14-finding action-{_ACTION_CLASS[action]}">
          <div class="finding-head"><strong class="actionability">{escape(label_for(action))}</strong><span class="rule">{escape(str(finding['rule_id']))}</span></div>
          <h3>{escape(str(finding['title']))}</h3>
          <div class="m14-detail">
            <div><small>URL</small><strong>{escape(str(page['normalized_url']))}</strong></div>
            <div><small>Device</small><strong>{escape(str(finding['device']))}</strong></div>
            <div><small>Categoria GEO</small><strong>{escape(str(finding['category']))}</strong></div>
            <div><small>Resultado</small><strong>{escape(_RESULT_LABELS.get(finding['rule_result'], finding['rule_result']))}</strong></div>
            <div><small>Actionability</small><strong>{escape(label_for(action))}</strong></div>
            <div><small>Prioridade</small><strong>{escape(priority)}</strong></div>
            <div><small>Selector</small><strong>{escape(str(selector))}</strong></div>
            <div><small>Elemento</small><strong>{escape(str(element))}</strong></div>
          </div>
          <p class="muted"><strong>Precisão do selector:</strong> {escape(selector_reason)}</p>
          <h4>HTML efetivamente observado</h4>{observed_html_block}
          <h4>Problema</h4><p>{escape(str(finding['title']))}. Condição esperada: {escape(str(finding['expected_condition'] or 'não especificada'))}.</p>
          <h4>Por que importa para GEO</h4><p>{escape(why)}</p>
          <h4>O que alterar</h4><p><strong>{escape(recipe.action)}</strong> - {escape(recipe.description)}</p>
          <h4>Estrutura recomendada - exemplo</h4>{example}
          <h4>Critério de aceite</h4><ul>{acceptance}</ul>
          <h4>Como revalidar</h4><ol>{validation}</ol>
          <h4>Fonte técnica</h4>{references}
          <p class="muted"><strong>Evidências:</strong> {escape(', '.join(evidence_ids) or 'NÃO DETERMINADO')}</p>
        </article>
        """

    @staticmethod
    def _html_from_evidence(finding: sqlite3.Row, evidence_by_id: dict[str, sqlite3.Row]) -> str | None:
        for evidence_id in _json_list(finding["evidence_ids"]):
            row = evidence_by_id.get(str(evidence_id))
            if row is None:
                continue
            value = _json_object(row["observed_value"])
            for key in ("outer_html", "html", "snippet", "source_html"):
                candidate = value.get(key)
                if isinstance(candidate, str) and candidate.strip():
                    return candidate.strip()
        return None

    @staticmethod
    def _reference(reference: Any) -> str:
        if reference.url:
            return f"""
            <div class="technical-ref"><strong>Base: {escape(reference.basis)}</strong><br>
            <a href="{escape(reference.url)}" target="_blank" rel="noopener">{escape(reference.authority or '')} - {escape(reference.title or '')}</a><br>
            <span>{escape(reference.reference_scope)} · verificado em {escape(reference.verified_on or 'N/D')}</span></div>
            """
        normative = "não aplicável / não identificada"
        return f"""
        <div class="technical-ref"><strong>Base: {escape(reference.basis)}</strong><br>
        <span>Fonte externa normativa: {normative}</span><br><span>Referência interna: {escape(reference.rule_id)}</span></div>
        """

    @staticmethod
    def _portable_image(workspace: AuditWorkspace, reference: str | None) -> str | None:
        if not reference:
            return None
        path = Path(reference)
        if path.is_absolute() or ".." in path.parts:
            return None
        if not (workspace.root / path).is_file():
            return None
        return path.as_posix()


def new_m14_report_record(*, audit_id: str, auditor_version: str, file_path: str) -> ReportRecord:
    return ReportRecord(
        report_id=new_id("RPT"),
        audit_id=audit_id,
        format="HTML",
        status="GENERATED",
        generated_at=utc_now(),
        template_version=TEMPLATE_VERSION,
        auditor_version=auditor_version,
        file_path=file_path,
    )


def _metric(label: str, value: Any) -> str:
    return f"<div class='metric'><small>{escape(str(label))}</small><strong>{escape(str(value))}</strong></div>"


def _json_list(value: Any) -> list[Any]:
    if value in (None, ""):
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
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


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
