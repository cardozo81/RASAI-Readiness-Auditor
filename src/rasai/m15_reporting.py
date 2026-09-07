"""M15 report UX and error-centric remediation projection.

The page-oriented REPORT-GEO-003 remains the primary human report. M15 adds a
second, derived view (REMEDIATION-GEO-001) and improves navigation/typography
without changing persisted findings or SCORE-GEO-001.
"""

from __future__ import annotations

from collections import defaultdict
from html import escape
import json
from pathlib import Path
import sqlite3
from typing import Any
from urllib.parse import urlsplit

from rasai.actionability import Actionability, classify_actionability, label_for
from rasai.m14_reporting import M14ReportBuilder
from rasai.persistence import AuditWorkspace
from rasai.remediation import recipe_for
from rasai.rule_references import references_for


REMEDIATION_TEMPLATE_VERSION = "REMEDIATION-GEO-001"

_DIMENSION_GUIDE: tuple[tuple[str, str, str, str, tuple[str, ...]], ...] = (
    (
        "TECHNICAL_ACCESSIBILITY", "Acessibilidade Técnica",
        "Mede se páginas e recursos necessários podem ser recuperados e interpretados tecnicamente.",
        "Manter respostas HTTP previsíveis, redirects válidos, políticas de crawler intencionais e recursos de descoberta acessíveis.",
        ("BR-GEO-005", "BR-GEO-017", "BR-GEO-018"),
    ),
    (
        "INDEXABILITY", "Capacidade de Indexação",
        "Avalia sinais que ajudam a determinar se a URL pode participar do universo indexável e qual versão é preferencial.",
        "Revisar diretivas de indexação, canonicalização e conflitos entre sinais técnicos.",
        ("BR-GEO-013", "BR-GEO-015"),
    ),
    (
        "CONTENT_EXTRACTABILITY", "Extração de Conteúdo",
        "Avalia se o conteúdo principal permanece recuperável e utilizável após aquisição e rendering.",
        "Preservar conteúdo principal no DOM, reduzir dependência frágil de JavaScript e evitar duplicação ou estrutura que obscureça o conteúdo.",
        ("BR-GEO-025",),
    ),
    (
        "SEMANTIC_STRUCTURE", "Estrutura Semântica",
        "Avalia título, hierarquia e organização semântica que tornam o tópico e as seções explícitos.",
        "Usar títulos representativos, headings coerentes e estrutura de seções que reflita a organização real do conteúdo.",
        ("BR-GEO-028", "BR-GEO-029", "BR-GEO-030"),
    ),
    (
        "ENTITY_CLARITY", "Clareza de Entidades",
        "Avalia quão claramente pessoas, organizações, produtos ou conceitos principais são identificados no conteúdo.",
        "Nomear entidades de forma explícita, adicionar contexto suficiente e reduzir referências ambíguas.",
        ("BR-GEO-031", "BR-GEO-032", "BR-GEO-033"),
    ),
    (
        "STRUCTURED_DATA", "Dados Estruturados",
        "Avalia sintaxe e coerência dos dados estruturados com o conteúdo efetivamente observado.",
        "Manter JSON-LD válido e coerente com o conteúdo visível; não declarar fatos que a página não sustenta.",
        ("BR-GEO-034", "BR-GEO-035", "BR-GEO-036", "BR-GEO-037"),
    ),
    (
        "ANSWERABILITY", "Capacidade de Resposta",
        "Avalia se a intenção principal e suas respostas relevantes aparecem de forma explícita e contextualizada.",
        "Responder diretamente às intenções cobertas pela página, com contexto suficiente para evitar inferência desnecessária.",
        ("BR-GEO-038", "BR-GEO-039", "BR-GEO-040"),
    ),
    (
        "CITATION_READINESS", "Preparação para Citação",
        "Avalia clareza e contexto de afirmações factuais que podem precisar ser verificadas ou citadas.",
        "Tornar afirmações factuais específicas, contextualizadas e distinguíveis de inferências ou linguagem promocional.",
        ("BR-GEO-041", "BR-GEO-042", "BR-GEO-043", "BR-GEO-044"),
    ),
    (
        "EVIDENCE_TRUST", "Evidências e Confiabilidade",
        "Avalia sinais de atribuição, responsabilidade e atualização que ajudam a rastrear a origem da informação.",
        "Explicitar autoria/responsabilidade quando aplicável e manter sinais de atualização coerentes com o conteúdo.",
        ("BR-GEO-045", "BR-GEO-046", "BR-GEO-047"),
    ),
    (
        "INTENT_COVERAGE", "Cobertura de Intenções",
        "Avalia quanto das intenções relevantes observadas pode ser sustentado pelo conteúdo existente.",
        "Cobrir intenções prioritárias com conteúdo real e evitar criar respostas artificiais apenas para preencher lacunas de auditoria.",
        ("BR-GEO-048", "BR-GEO-049"),
    ),
)

_M15_CSS = r"""
:root{--m15-sidebar:258px;--m15-ink:#101828;--m15-muted:#667085;--m15-line:#e4e7ec;--m15-surface:#fff;--m15-soft:#f8fafc}
body{color:var(--m15-ink)}
.m15-sidebar{position:fixed;inset:0 auto 0 0;width:var(--m15-sidebar);box-sizing:border-box;background:#0f172a;color:#e2e8f0;padding:22px 16px;overflow-y:auto;z-index:50;border-right:1px solid #1e293b}
.m15-sidebar .brand{font-size:.72rem;letter-spacing:.12em;text-transform:uppercase;font-weight:800;color:#94a3b8;margin-bottom:8px}
.m15-sidebar h2{font-size:1rem;margin:0 0 16px;color:#fff}.m15-sidebar nav{display:grid;gap:5px}.m15-sidebar a{display:block;color:#cbd5e1;text-decoration:none;padding:8px 10px;border-radius:8px;font-size:.82rem;line-height:1.25;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.m15-sidebar a:hover,.m15-sidebar a:focus{background:#1e293b;color:#fff;outline:none}.m15-sidebar .secondary{margin-top:18px;padding-top:14px;border-top:1px solid #334155;color:#93c5fd;font-weight:700}
.page.m15-main{margin-left:var(--m15-sidebar);max-width:1280px;padding:28px 34px 56px}.m14-nav{display:none}
.hero h1{font-size:clamp(1.85rem,2.7vw,2.55rem);line-height:1.08}.hero .lead,.section-intro{max-width:78ch}.metric strong{font-size:clamp(.92rem,1.3vw,1.08rem);line-height:1.25}
.score-row{grid-template-columns:minmax(220px,1.6fr) minmax(118px,.65fr) minmax(118px,.65fr) minmax(145px,.8fr)!important;align-items:center;gap:10px}.score-row>div{min-width:0}.score-row strong,.score-row .score-value{overflow-wrap:normal!important;word-break:normal!important;hyphens:none}.score-row .score-value{font-size:clamp(1.05rem,1.8vw,1.35rem)!important;line-height:1.15}.score-row>div:nth-child(n+2) strong{font-size:.93rem;line-height:1.2}
.m15-crosslink{display:flex;gap:12px;align-items:center;justify-content:space-between;border:1px solid #bfdbfe;background:#eff6ff;border-radius:12px;padding:14px 16px;margin:18px 0}.m15-crosslink a{font-weight:800;color:#1d4ed8}
.m15-guide-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.m15-guide-card{border:1px solid var(--m15-line);border-radius:12px;padding:16px;background:var(--m15-surface)}.m15-guide-card h3{font-size:1rem;margin:0 0 8px}.m15-guide-card .dimension-code{font:700 .72rem ui-monospace,SFMono-Regular,Menlo,monospace;color:var(--m15-muted)}.m15-guide-card p{margin:7px 0;font-size:.9rem;line-height:1.5}.m15-guide-card .refs{margin-top:9px;font-size:.82rem}.m15-guide-card .refs a{display:inline-block;margin:3px 8px 3px 0}
.m15-interpretation dl{grid-template-columns:minmax(170px,220px) minmax(0,1fr)}.m15-interpretation dd{line-height:1.5}
@media(max-width:1050px){.score-row{grid-template-columns:minmax(190px,1.4fr) minmax(100px,.6fr) minmax(105px,.6fr) minmax(120px,.7fr)!important}.m15-guide-grid{grid-template-columns:1fr}}
@media(max-width:820px){.m15-sidebar{position:sticky;top:0;width:auto;height:auto;inset:auto;padding:10px 12px;overflow-x:auto}.m15-sidebar .brand,.m15-sidebar h2{display:none}.m15-sidebar nav{display:flex;gap:6px;min-width:max-content}.m15-sidebar a{max-width:180px;background:#1e293b}.m15-sidebar .secondary{margin:0;padding:8px 10px;border:0}.page.m15-main{margin-left:0;padding:18px 14px 44px}.score-row{grid-template-columns:1fr!important;gap:4px}.score-row>div{padding-left:0!important}.m15-crosslink{align-items:flex-start;flex-direction:column}.m15-interpretation dl{grid-template-columns:1fr}}
@media print{.m15-sidebar{display:none!important}.page.m15-main{margin-left:0;max-width:none;padding:0}.m15-crosslink{display:none}}
"""

_REMEDIATION_CSS = r"""
*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:#f4f6f8;color:#101828;font-family:Inter,ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif}.wrap{max-width:1240px;margin:auto;padding:30px 24px 60px}header,.group,.summary{background:#fff;border:1px solid #e4e7ec;border-radius:14px;box-shadow:0 1px 2px rgba(16,24,40,.04)}header{padding:24px;margin-bottom:16px;border-top:6px solid #344054}h1{font-size:clamp(1.8rem,3vw,2.45rem);margin:.25rem 0}h2{font-size:1.35rem;margin:30px 0 12px}h3{font-size:1.05rem;margin:0}.lead{max-width:80ch;color:#475467;line-height:1.55}.summary{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:1px;overflow:hidden;margin-bottom:18px}.summary div{padding:14px;background:#fff}.summary small{display:block;color:#667085}.summary strong{font-size:1.2rem}.group{padding:18px;margin:12px 0;border-left:6px solid #667085}.group.required{border-left-color:#d92d20}.group.review{border-left-color:#dc9900}.group.optional{border-left-color:#2e64d6}.group.insufficient{border-left-color:#667085}.head{display:flex;gap:10px;justify-content:space-between;align-items:flex-start;flex-wrap:wrap}.badges{display:flex;gap:6px;flex-wrap:wrap}.badge{font-size:.72rem;font-weight:800;border-radius:999px;padding:4px 8px;background:#eef2f6}.scope-global{background:#fee4e2;color:#912018}.scope-page{background:#e0f2fe;color:#075985}.action{font-weight:900}.paths{display:flex;gap:6px;flex-wrap:wrap;margin:10px 0}.paths a{font:700 .78rem ui-monospace,SFMono-Regular,Menlo,monospace;background:#f2f4f7;padding:5px 8px;border-radius:7px;color:#344054;text-decoration:none;max-width:330px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.occurrences{width:100%;border-collapse:collapse;margin:12px 0;font-size:.86rem}.occurrences th,.occurrences td{text-align:left;border-bottom:1px solid #eaecf0;padding:9px;vertical-align:top}.occurrences th{color:#475467;background:#f9fafb}.mono{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;overflow-wrap:anywhere}.recipe{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:10px;margin-top:12px}.recipe>div{background:#f8fafc;padding:12px;border-radius:9px}.refs a{display:block;margin:5px 0}.toplink{display:inline-block;margin-top:10px;font-weight:800;color:#1d4ed8}.empty{padding:18px;background:#fff;border-radius:12px;color:#667085}@media(max-width:700px){.wrap{padding:16px 10px 40px}.occurrences{display:block;overflow-x:auto}.head{display:block}}
"""


class M15ReportBuilder(M14ReportBuilder):
    """Apply M15 navigation, typography and interpretability to REPORT-GEO-003."""

    def build(self, *, audit_id: str, workspace: AuditWorkspace) -> str:
        html = super().build(audit_id=audit_id, workspace=workspace)
        pages, scores = self._load_navigation_data(audit_id, workspace)
        sidebar = self._sidebar(pages)
        guide = self._score_dimension_guide(scores)
        interpretation = self._interpretation()
        crosslink = (
            "<section class='m15-crosslink' id='visao-por-problema'><div><strong>Visão transversal por problema</strong>"
            "<br><span>Veja quais achados são globais e quais se repetem apenas em páginas específicas.</span></div>"
            "<a href='remediation.html'>Abrir remediation.html →</a></section>"
        )
        html = html.replace("</style>", f"{_M15_CSS}</style>", 1)
        html = html.replace('<body><main class="page">', f'<body>{sidebar}<main class="page m15-main">', 1)
        html = html.replace('<header class="hero m14-executive"', crosslink + '<header class="hero m14-executive"', 1)
        html = html.replace("<footer>", guide + interpretation + "<footer>", 1)
        return html

    @staticmethod
    def _load_navigation_data(audit_id: str, workspace: AuditWorkspace) -> tuple[list[sqlite3.Row], list[sqlite3.Row]]:
        connection = sqlite3.connect(workspace.database)
        connection.row_factory = sqlite3.Row
        try:
            pages = list(connection.execute(
                "SELECT * FROM pages WHERE audit_id = ? ORDER BY depth, normalized_url", (audit_id,)
            ).fetchall())
            try:
                scores = list(connection.execute(
                    "SELECT * FROM scores WHERE audit_id = ? ORDER BY device, dimension", (audit_id,)
                ).fetchall())
            except sqlite3.OperationalError:
                scores = []
            return pages, scores
        finally:
            connection.close()

    @staticmethod
    def _sidebar(pages: list[sqlite3.Row]) -> str:
        links = []
        for index, page in enumerate(pages, start=1):
            path = _short_path(str(page["normalized_url"]))
            links.append(
                f"<a href='#pagina-{index}' title='{escape(path)}'>{escape(path)}</a>"
            )
        page_links = "".join(links) or "<span>Nenhuma página persistida</span>"
        return (
            "<aside class='m15-sidebar' aria-label='Páginas auditadas'>"
            "<div class='brand'>RASAi Auditor</div><h2>Páginas</h2><nav>"
            "<a href='#resumo-m14'>Resumo</a>"
            f"{page_links}"
            "<a class='secondary' href='#guia-score-geo'>Entender Score GEO</a>"
            "<a class='secondary' href='remediation.html'>Problemas agrupados ↗</a>"
            "</nav></aside>"
        )

    @staticmethod
    def _score_dimension_guide(scores: list[sqlite3.Row]) -> str:
        score_index = {(str(row["device"]), str(row["dimension"])): row for row in scores}
        cards = []
        for code, title, meaning, improve, rule_ids in _DIMENSION_GUIDE:
            states = []
            for device in ("DESKTOP", "MOBILE"):
                row = score_index.get((device, code))
                if row is None:
                    continue
                value = "NÃO DETERMINADO" if row["value"] is None else f"{float(row['value']):.1f}"
                coverage = f"{float(row['coverage']) * 100:.0f}%"
                states.append(f"{device.title()}: score {value}, coverage {coverage}, {row['consolidation_status']}")
            refs = _dimension_references(rule_ids)
            refs_html = "".join(
                f"<a href='{escape(url)}' target='_blank' rel='noopener'>{escape(label)}</a>"
                for label, url in refs
            ) or "<span>Referência técnica externa específica não identificada; consulte as regras do auditor.</span>"
            cards.append(
                "<article class='m15-guide-card'>"
                f"<div class='dimension-code'>{escape(code)}</div><h3>{escape(title)}</h3>"
                f"<p><strong>O que é:</strong> {escape(meaning)}</p>"
                f"<p><strong>Como melhorar:</strong> {escape(improve)}</p>"
                f"<p><strong>Nesta auditoria:</strong> {escape(' · '.join(states) or 'sem score persistido para esta dimensão')}</p>"
                f"<div class='refs'><strong>Referências:</strong><br>{refs_html}</div></article>"
            )
        return (
            "<section id='guia-score-geo'><div class='section-kicker'>REFERÊNCIA DE LEITURA</div>"
            "<h2>O que cada dimensão do Score GEO mede</h2>"
            "<p class='section-intro'>As dez dimensões abaixo são as dimensões oficiais de SCORE-GEO-001. "
            "As orientações indicam como melhorar a evidência avaliada; não representam promessa de ranking, citação ou tráfego.</p>"
            f"<div class='m15-guide-grid'>{''.join(cards)}</div></section>"
        )

    @staticmethod
    def _interpretation() -> str:
        return """
        <section id="como-interpretar-final" class="m15-interpretation">
          <div class="section-kicker">COMO INTERPRETAR</div><h2>Leitura correta dos resultados</h2>
          <p class="section-intro">Score, cobertura, confiabilidade, consolidação e actionability respondem perguntas diferentes. Leia os cinco em conjunto.</p>
          <dl>
            <dt>Score</dt><dd>Qualidade observada somente nas regras efetivamente avaliadas. Um <strong>0.0 calculado</strong> é diferente de ausência de cálculo.</dd>
            <dt>Coverage</dt><dd>Quanto do universo aplicável pôde ser avaliado. Coverage baixa reduz a força da conclusão; não equivale a qualidade baixa do site.</dd>
            <dt>Confiabilidade</dt><dd>Segurança da conclusão considerando cobertura, evidências e erros de execução. HIGH/MEDIUM/LOW/UNAVAILABLE não substitui o score.</dd>
            <dt>Consolidação</dt><dd>Indica se há base suficiente para tratar a dimensão como consolidada, parcial ou não consolidada.</dd>
            <dt>Actionability</dt><dd>Indica o que fazer: ação necessária, revisão recomendada, melhoria opcional, nenhuma ação ou ação não determinada. Não altera SCORE-GEO-001.</dd>
            <dt>Desktop × Mobile</dt><dd>São contextos independentes. Compare os dois antes de concluir que um problema é global ao website.</dd>
            <dt>Sem IA</dt><dd>A ausência de provider pode reduzir Coverage e Consolidação de análises semânticas; não atribui automaticamente nota zero ao website.</dd>
          </dl>
        </section>
        """


class M15RemediationReportBuilder:
    """Create a second report grouped by issue instead of by audited page."""

    def build(self, *, audit_id: str, workspace: AuditWorkspace) -> str:
        data = self._load(audit_id, workspace)
        audit = data["audit"]
        pages = data["pages"]
        findings = data["findings"]
        observations = data["observations"]
        priorities = self._priority_map(data["groups"], data["recommendations"])
        page_by_id = {row["page_id"]: row for row in pages}
        page_anchor = {row["page_id"]: index for index, row in enumerate(pages, start=1)}
        obs_by_finding: dict[str, list[sqlite3.Row]] = defaultdict(list)
        for row in observations:
            obs_by_finding[str(row["finding_id"])].append(row)

        grouped: dict[tuple[str, str, str], list[sqlite3.Row]] = defaultdict(list)
        for finding in findings:
            action = classify_actionability(
                finding["rule_result"], rule_id=finding["rule_id"],
                observed_value=_json_object(finding["execution_observed_value"]),
            )
            scope = "GLOBAL" if finding["page_id"] is None else "PAGE"
            grouped[(scope, str(finding["rule_id"]), action.value)].append(finding)

        global_groups = []
        page_groups = []
        for key in sorted(grouped, key=lambda item: (item[0] != "GLOBAL", item[1], item[2])):
            rendered = self._group_card(
                key=key, rows=grouped[key], page_by_id=page_by_id, page_anchor=page_anchor,
                obs_by_finding=obs_by_finding, priorities=priorities,
            )
            (global_groups if key[0] == "GLOBAL" else page_groups).append(rendered)

        title = f"Problemas agrupados - {audit['project_name']}"
        unique_pages = {row["page_id"] for row in findings if row["page_id"]}
        body = f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
        <title>{escape(title)}</title><style>{_REMEDIATION_CSS}</style></head><body><main class="wrap">
        <header id="topo"><div class="badge">{REMEDIATION_TEMPLATE_VERSION}</div><h1>{escape(title)}</h1>
        <p class="lead">Esta visão reorganiza os mesmos findings persistidos por regra/problema. Use-a para distinguir condições globais, recorrentes em várias páginas e pontuais. Nenhum score ou finding é recalculado aqui.</p>
        <a class="toplink" href="report.html">← Voltar para report.html</a></header>
        <section class="summary"><div><small>Audit ID</small><strong>{escape(str(audit['audit_id']))}</strong></div>
        <div><small>Findings</small><strong>{len(findings)}</strong></div><div><small>Páginas com findings</small><strong>{len(unique_pages)}</strong></div>
        <div><small>Grupos globais</small><strong>{len(global_groups)}</strong></div><div><small>Grupos por página</small><strong>{len(page_groups)}</strong></div></section>
        <h2>Problemas globais</h2>{''.join(global_groups) if global_groups else '<div class="empty">Nenhum finding global persistido.</div>'}
        <h2>Problemas por página</h2>{''.join(page_groups) if page_groups else '<div class="empty">Nenhum finding de página persistido.</div>'}
        </main></body></html>"""
        return body

    @staticmethod
    def _load(audit_id: str, workspace: AuditWorkspace) -> dict[str, Any]:
        connection = sqlite3.connect(workspace.database)
        connection.row_factory = sqlite3.Row
        try:
            audit = connection.execute("SELECT * FROM audits WHERE audit_id = ?", (audit_id,)).fetchone()
            if audit is None:
                raise ValueError(f"audit not found: {audit_id}")
            pages = list(connection.execute("SELECT * FROM pages WHERE audit_id = ? ORDER BY depth, normalized_url", (audit_id,)).fetchall())
            findings = list(connection.execute(
                """SELECT f.*, re.result AS rule_result, re.observed_value AS execution_observed_value
                   FROM findings f JOIN rule_executions re ON re.rule_execution_id=f.rule_execution_id
                   WHERE f.audit_id=? ORDER BY f.rule_id,f.page_id,f.device,f.finding_id""", (audit_id,)
            ).fetchall())
            observations = _query_optional(connection,
                """SELECT feo.finding_id,eo.* FROM finding_element_observations feo
                   JOIN element_observations eo ON eo.element_observation_id=feo.element_observation_id
                   WHERE eo.audit_id=? ORDER BY feo.finding_id,eo.element_observation_id""", (audit_id,))
            groups = _query_optional(connection, "SELECT * FROM remediation_groups WHERE audit_id=?", (audit_id,))
            recommendations = _query_optional(connection, "SELECT * FROM recommendations WHERE audit_id=?", (audit_id,))
            return {"audit": audit, "pages": pages, "findings": findings, "observations": observations, "groups": groups, "recommendations": recommendations}
        finally:
            connection.close()

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

    def _group_card(
        self, *, key: tuple[str, str, str], rows: list[sqlite3.Row],
        page_by_id: dict[str, sqlite3.Row], page_anchor: dict[str, int],
        obs_by_finding: dict[str, list[sqlite3.Row]], priorities: dict[str, str],
    ) -> str:
        scope, rule_id, action_value = key
        action = Actionability(action_value)
        css_action = {
            Actionability.REQUIRED_FIX: "required", Actionability.REVIEW_RECOMMENDED: "review",
            Actionability.OPTIONAL_IMPROVEMENT: "optional", Actionability.INSUFFICIENT_EVIDENCE: "insufficient",
            Actionability.NO_ACTION: "none",
        }[action]
        unique_page_ids = list(dict.fromkeys(str(row["page_id"]) for row in rows if row["page_id"]))
        paths = []
        for page_id in unique_page_ids:
            page = page_by_id.get(page_id)
            if page is None:
                continue
            path = _short_path(str(page["normalized_url"]))
            paths.append(f"<a href='report.html#pagina-{page_anchor.get(page_id, 1)}' title='{escape(path)}'>{escape(path)}</a>")
        occurrences = []
        for row in rows:
            page = page_by_id.get(row["page_id"]) if row["page_id"] else None
            path = _short_path(str(page["normalized_url"])) if page is not None else "DOMÍNIO / RECURSO GLOBAL"
            linked = obs_by_finding.get(str(row["finding_id"]), [])
            observation = linked[0] if len(linked) == 1 else None
            selector = str(observation["selector"]) if observation is not None and observation["selector"] else "NÃO DETERMINADO"
            occurrences.append(
                f"<tr><td class='mono'>{escape(path)}</td><td>{escape(str(row['device'] or 'GLOBAL'))}</td>"
                f"<td>{escape(str(row['rule_result']))}</td><td>{escape(priorities.get(str(row['finding_id']), 'NÃO PRIORIZADO'))}</td>"
                f"<td class='mono'>{escape(selector)}</td></tr>"
            )
        recipe = recipe_for(rule_id)
        references = []
        for ref in references_for(rule_id):
            if ref.url:
                references.append(f"<a href='{escape(ref.url)}' target='_blank' rel='noopener'>{escape((ref.authority or '') + ' - ' + (ref.title or ''))}</a>")
            else:
                references.append(f"<span>Base {escape(ref.basis)} · referência interna {escape(rule_id)}</span>")
        scope_label = "GLOBAL" if scope == "GLOBAL" else f"PÁGINAS · {len(unique_page_ids)} afetada(s)"
        return f"""
        <article class="group {css_action}">
          <div class="head"><div><div class="badges"><span class="badge {'scope-global' if scope == 'GLOBAL' else 'scope-page'}">{escape(scope_label)}</span><span class="badge">{escape(rule_id)}</span></div>
          <h3>{escape(str(rows[0]['title']))}</h3></div><div class="action">{escape(label_for(action))}</div></div>
          <div class="paths">{''.join(paths)}</div>
          <table class="occurrences"><thead><tr><th>Local</th><th>Device</th><th>Resultado</th><th>Prioridade</th><th>Selector</th></tr></thead><tbody>{''.join(occurrences)}</tbody></table>
          <div class="recipe"><div><strong>O que alterar</strong><p>{escape(recipe.action)} - {escape(recipe.description)}</p></div>
          <div><strong>Critério de aceite</strong><p>{escape(' · '.join(recipe.acceptance) or 'Consultar regra e evidências persistidas.')}</p></div>
          <div class="refs"><strong>Referências técnicas</strong>{''.join(references)}</div></div>
        </article>"""


def write_remediation_report(*, workspace: AuditWorkspace, html: str) -> Path:
    path = workspace.root / "remediation.html"
    path.write_text(html, encoding="utf-8")
    return path


def _short_path(url: str) -> str:
    parsed = urlsplit(url)
    path = parsed.path or "/"
    if parsed.query:
        path += "?" + parsed.query
    return path


def _dimension_references(rule_ids: tuple[str, ...]) -> tuple[tuple[str, str], ...]:
    result: list[tuple[str, str]] = []
    seen: set[str] = set()
    for rule_id in rule_ids:
        for ref in references_for(rule_id):
            if not ref.url or ref.url in seen:
                continue
            seen.add(ref.url)
            label = f"{ref.authority or 'Fonte técnica'} - {ref.title or rule_id}"
            result.append((label, ref.url))
    return tuple(result)


def _query_optional(connection: sqlite3.Connection, sql: str, params: tuple[Any, ...]) -> list[sqlite3.Row]:
    try:
        return list(connection.execute(sql, params).fetchall())
    except sqlite3.OperationalError as exc:
        if "no such table" in str(exc).lower():
            return []
        raise


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
