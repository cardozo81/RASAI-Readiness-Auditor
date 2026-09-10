"""Project external Web Performance evidence into the static report site."""

from __future__ import annotations

from html import escape
import json
from pathlib import Path
import sqlite3
from typing import Any

from rasai.m22_quality_domains import enrich_m22_domain_reports
from rasai.persistence import AuditWorkspace
from rasai.report_navigation import normalize_report_navigation, render_report_navigation
from rasai.score_geo_004 import SCORING_VERSION

PERFORMANCE_FILE = "web-performance.html"

_LIGHTHOUSE_CATEGORY_LABELS = {
    "performance": "Performance",
    "accessibility": "Accessibility",
    "best-practices": "Best Practices",
    "seo": "SEO técnico",
    "agentic-browsing": "Agentic Browsing",
}

_OFFICIAL_REFERENCES = (
    (
        "PageSpeed Insights API v5",
        "https://developers.google.com/speed/docs/insights/v5/reference/pagespeedapi/runpagespeed",
        "API oficial usada como transporte para o lighthouseResult e, enquanto disponível, field data CrUX na resposta.",
    ),
    (
        "PageSpeed Insights - Get Started",
        "https://developers.google.com/speed/docs/insights/v5/get-started",
        "Documenta uso com/sem chave e a migração recomendada de field data para CrUX API.",
    ),
    (
        "Lighthouse overview",
        "https://developer.chrome.com/docs/lighthouse/overview/",
        "Define Lighthouse como ferramenta automatizada de auditoria de qualidade Web.",
    ),
    (
        "Lighthouse Performance Scoring",
        "https://developer.chrome.com/docs/lighthouse/performance/performance-scoring",
        "Explica score 0-100, pesos e curvas da categoria Performance.",
    ),
    (
        "Lighthouse Accessibility scoring",
        "https://developer.chrome.com/docs/lighthouse/accessibility/scoring",
        "Explica a pontuação automatizada da categoria Accessibility e seus limites.",
    ),
    (
        "Lighthouse Best Practices",
        "https://developer.chrome.com/docs/lighthouse/best-practices/",
        "Catálogo/metodologia da categoria automatizada Best Practices.",
    ),
    (
        "Lighthouse SEO",
        "https://developer.chrome.com/docs/lighthouse/seo/",
        "Auditorias automatizadas de fundamentos técnicos de SEO; não representa uma avaliação integral de SEO ou ranking.",
    ),
    (
        "Lighthouse Agentic Browsing",
        "https://github.com/GoogleChrome/lighthouse/blob/main/core/config/agentic-browsing-config.js",
        "Categoria experimental do Lighthouse voltada a práticas que afetam a interação e compreensão por agentes de IA.",
    ),
    (
        "Chrome UX Report API",
        "https://developer.chrome.com/docs/crux/api/",
        "API oficial de experiência real agregada, com LCP, INP e CLS por URL/origin e form factor.",
    ),
    (
        "Como usar a CrUX API",
        "https://developer.chrome.com/docs/crux/guides/crux-api",
        "Documenta percentil 75, form factors e avaliação de Core Web Vitals.",
    ),
    (
        "Core Web Vitals",
        "https://web.dev/articles/vitals",
        "Define LCP, INP e CLS e os thresholds de experiência considerada boa.",
    ),
)


def enrich_m21_report_site(*, audit_id: str, workspace: AuditWorkspace) -> Path:
    report_dir = workspace.root / "report"
    report_dir.mkdir(parents=True, exist_ok=True)
    data = _load(audit_id, workspace)
    path = report_dir / PERFORMANCE_FILE
    path.write_text(_performance_page(data, report_dir), encoding="utf-8", newline="\n")
    for html_path in report_dir.glob("*.html"):
        if html_path.name == PERFORMANCE_FILE:
            continue
        html = html_path.read_text(encoding="utf-8")
        if html_path.name == "index.html" and "web-performance-summary" not in html:
            html = html.replace("</header>", "</header>" + _index_summary(data), 1)
        if html_path.name == "references.html" and "web-performance-methodology" not in html:
            html = html.replace("</main>", _references_section() + "</main>", 1)
        html_path.write_text(html, encoding="utf-8", newline="\n")

    # Accessibility consumes only already-persisted Web Performance artifacts.
    # It creates an independent page and adds evidence-bound diagnostics without
    # changing readiness scoring or making another network call.
    enrich_m22_domain_reports(audit_id=audit_id, workspace=workspace)
    normalize_report_navigation(report_dir)
    return path


def _load(audit_id: str, workspace: AuditWorkspace) -> dict[str, Any]:
    connection = sqlite3.connect(workspace.database)
    connection.row_factory = sqlite3.Row
    try:
        run = _one(connection, "SELECT * FROM web_performance_runs WHERE audit_id=?", (audit_id,))
        raw_observations = _many(
            connection,
            """SELECT o.*,p.normalized_url
               FROM web_performance_observations o
               JOIN pages p ON p.page_id=o.page_id
               WHERE o.audit_id=?
               ORDER BY p.normalized_url,o.device,o.observation_id""",
            (audit_id,),
        )
        attempts = _many(
            connection,
            "SELECT * FROM web_performance_attempts WHERE audit_id=? ORDER BY created_at,service,attempt_id",
            (audit_id,),
        )
    finally:
        connection.close()

    observations: list[dict[str, Any]] = []
    for row in raw_observations:
        item = dict(row)
        item["lighthouse_category_diagnostics"] = _load_lighthouse_category_diagnostics(
            workspace,
            str(item.get("pagespeed_artifact_reference") or "") or None,
        )
        observations.append(item)
    return {"run": run, "observations": observations, "attempts": attempts}


def _one(connection: sqlite3.Connection, sql: str, params: tuple[Any, ...]) -> sqlite3.Row | None:
    try:
        return connection.execute(sql, params).fetchone()
    except sqlite3.OperationalError as exc:
        if "no such table" in str(exc).lower():
            return None
        raise


def _many(connection: sqlite3.Connection, sql: str, params: tuple[Any, ...]) -> list[sqlite3.Row]:
    try:
        return list(connection.execute(sql, params).fetchall())
    except sqlite3.OperationalError as exc:
        if "no such table" in str(exc).lower():
            return []
        raise


def _performance_page(data: dict[str, Any], report_dir: Path) -> str:
    run, observations, attempts = data["run"], data["observations"], data["attempts"]
    enabled = bool(run["enabled"]) if run is not None else False
    status = str(run["status"]) if run is not None else "UNAVAILABLE"
    field_source = str(run["field_source"]) if run is not None else "-"
    page_limit = int(run["page_limit"]) if run is not None else 0
    pages = int(run["pages_considered"]) if run is not None else 0
    contexts = int(run["context_attempts"]) if run is not None else 0
    successes = int(run["successful_contexts"]) if run is not None else 0
    categories = ", ".join(_json_list(run["categories"])) if run is not None else "-"
    limit_label = "todas as páginas auditadas" if page_limit == 0 else str(page_limit)

    cards = [_observation_card(row) for row in observations]

    attempt_rows = []
    for row in attempts:
        attempt_rows.append(
            "<tr>"
            f"<td class='mono'>{escape(str(row['url']))}</td>"
            f"<td>{escape(str(row['device']))}</td>"
            f"<td>{escape(str(row['service']))}</td>"
            f"<td>{escape(str(row['status']))}</td>"
            f"<td>{escape(str(row['http_status'] if row['http_status'] is not None else '-'))}</td>"
            f"<td>{escape(str(row['duration_ms']))} ms</td>"
            f"<td>{escape(str(row['error_code'] or '-'))}</td>"
            "</tr>"
        )

    if not enabled:
        notice = (
            f"<div class='notice'><strong>Coleta externa desabilitada.</strong> "
            f"Esse é o comportamento padrão para evitar tráfego/quota externa não solicitado. "
            f"{SCORING_VERSION} continua disponível normalmente.</div>"
        )
    elif status in {"PARTIAL", "UNAVAILABLE"}:
        notice = (
            f"<div class='notice warn'><strong>Coleta externa incompleta.</strong> "
            f"Falha, quota, ausência de amostra CrUX ou indisponibilidade do serviço não é defeito "
            f"do website e não reduz {SCORING_VERSION}.</div>"
        )
    else:
        notice = (
            "<div class='notice'><strong>Evidência externa coletada.</strong> "
            "Lighthouse/CrUX permanecem métricas independentes dos índices proprietários do RASAi.</div>"
        )

    nav = _nav(report_dir)
    ownership = _ownership_section(categories)
    return f"""<!doctype html><html lang='pt-BR'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>Web Performance - RASAi - Search & AI Readiness Auditor</title><link rel='stylesheet' href='css/site.css'></head><body>{nav}<main class='app-main'>
<header class='hero'><div class='eyebrow'>Web Performance · evidência externa Lighthouse + CrUX</div><h1>Qualidade Web, Lighthouse e Core Web Vitals</h1><p class='lead'>O RASAi coleta, persiste e contextualiza evidências externas sem assumir autoria sobre os scores do Lighthouse. Performance, Accessibility, Best Practices e SEO técnico são categorias consolidadas do Google Chrome Lighthouse; Agentic Browsing é uma categoria experimental do Lighthouse. Core Web Vitals de campo pertencem ao CrUX. Nenhum desses scores é convertido automaticamente em SARI-001 ou {SCORING_VERSION}; cada metodologia permanece independente.</p><div class='metric-grid'>{_metric('Coleta externa', 'Habilitada' if enabled else 'Desabilitada')}{_metric('Status', status)}{_metric('Páginas consideradas', pages)}{_metric('Contextos', f'{successes}/{contexts}')}{_metric('Limite configurado', limit_label)}{_metric('Field source', field_source)}</div></header>
{notice}
{ownership}
<section class='panel'><div class='kicker'>Resultados</div><h2>Por página e dispositivo</h2>{''.join(cards) if cards else '<p class="intro">Nenhuma observação externa persistida.</p>'}</section>
<section class='panel'><div class='kicker'>Operação externa</div><h2>Tentativas de coleta</h2><p class='intro'>Esta telemetria é de serviços de medição, não de IA. Chaves de API nunca são persistidas nem exibidas.</p><div class='table-wrap'><table><thead><tr><th>URL</th><th>Device</th><th>Serviço</th><th>Status</th><th>HTTP</th><th>Duração</th><th>Erro</th></tr></thead><tbody>{''.join(attempt_rows) if attempt_rows else '<tr><td colspan="7">Nenhuma chamada externa.</td></tr>'}</tbody></table></div></section>
<section class='panel'><div class='kicker'>Governança de consumo</div><h2>Custos, quota e IA</h2><p class='intro'>Web Performance e Acessibilidade não criam chamadas a LLM. O consumo desta camada é PageSpeed/CrUX e ocorre apenas quando habilitado.</p><p class='intro'>PageSpeed pode ser chamado sem chave em baixo volume, mas uma chave é recomendada para automação frequente. CrUX API direta exige chave. O limite de páginas e o timeout são configuráveis para controlar quota e duração.</p></section>
<footer class='footer'>Web Performance é evidência complementar. SARI-001 e {SCORING_VERSION} permanecem metodologicamente independentes.</footer></main></body></html>
"""


def _ownership_section(categories: str) -> str:
    return f"""<section class='panel' id='web-quality-ownership'><div class='kicker'>Proveniência e propriedade metodológica</div><h2>Quem é responsável por cada indicador</h2><p class='intro'>A presença destes indicadores dentro de <strong>Web Performance</strong> é uma decisão de organização do relatório RASAi. A metodologia dos scores Lighthouse continua pertencendo ao Google Chrome Lighthouse; o RASAi atua como coletor, validador de integridade, persistência, rastreabilidade e camada de interpretação.</p><div class='table-wrap'><table><thead><tr><th>Indicador</th><th>Proprietário/metodologia</th><th>Fonte técnica</th><th>Escopo</th><th>Relação com RASAi</th></tr></thead><tbody>
<tr><td><strong>Performance</strong></td><td>Google Chrome Lighthouse</td><td><code>lighthouseResult.categories.performance.score</code></td><td>Score de laboratório 0-100; FCP, Speed Index, LCP lab, TBT e CLS lab são detalhes associados à categoria Performance.</td><td>RASAi não recalcula o score e não o converte em SARI-001/{SCORING_VERSION}.</td></tr>
<tr><td><strong>Accessibility</strong></td><td>Google Chrome Lighthouse</td><td><code>lighthouseResult.categories.accessibility.score</code></td><td>Auditorias automatizadas de acessibilidade. Não equivale a conformidade WCAG completa.</td><td>O score é espelhado aqui para completar o conjunto Lighthouse e detalhado em <a href='accessibility.html'>Acessibilidade</a>.</td></tr>
<tr><td><strong>Best Practices</strong></td><td>Google Chrome Lighthouse</td><td><code>lighthouseResult.categories.best-practices.score</code></td><td>Checks automatizados de qualidade técnica, segurança e práticas modernas suportadas pelo Lighthouse.</td><td>Indicador complementar; não recebe peso automático no SARI-001/{SCORING_VERSION}.</td></tr>
<tr><td><strong>SEO técnico</strong></td><td>Google Chrome Lighthouse</td><td><code>lighthouseResult.categories.seo.score</code></td><td>Fundamentos técnicos automatizáveis de SEO/indexabilidade. Não mede ranking, tráfego, autoridade, conteúdo integral, SERP ou probabilidade de citação por IA.</td><td>Indicador complementar. Search Intelligence/SERP e Search & AI Readiness permanecem domínios separados.</td></tr>
<tr><td><strong>Agentic Browsing</strong></td><td>Google Chrome Lighthouse · experimental</td><td><code>lighthouseResult.categories.agentic-browsing.score</code></td><td>Checks experimentais voltados à capacidade de agentes automatizados compreenderem e operarem a página. A composição pode evoluir com versões do Lighthouse.</td><td>Indicador complementar e experimental; não é tratado como score proprietário nem entra automaticamente no SARI-001/{SCORING_VERSION}.</td></tr>
<tr><td><strong>Core Web Vitals</strong></td><td>Google Chrome UX Report (CrUX)</td><td>LCP, INP e CLS no percentil 75</td><td>Experiência agregada de usuários reais quando há amostra suficiente.</td><td>RASAi preserva a fonte/escopo e não transforma ausência de amostra em falha.</td></tr>
<tr><td><strong>Diagnósticos exibidos</strong></td><td>Lighthouse + projeção RASAi</td><td><code>auditRefs</code> e <code>audits</code> do artifact PageSpeed</td><td>O RASAi seleciona e apresenta checks reprovados/diagnósticos sem alterar o resultado-fonte.</td><td>Camada explicativa e de rastreabilidade, não um novo score.</td></tr>
</tbody></table></div><div class='notice'><strong>Regra de leitura:</strong> um score Lighthouse alto significa bom resultado apenas no conjunto de auditorias automatizadas daquela categoria e daquela execução. Agentic Browsing deve ser lido como experimental e version-dependent. Nenhum deles deve ser renomeado como score proprietário do RASAi.</div><p class='intro'>Categorias solicitadas nesta execução: <code>{escape(categories)}</code>.</p></section>"""


def _observation_card(row: dict[str, Any]) -> str:
    category_scores = (
        _metric("Performance · Lighthouse", _score(row.get("performance_score")))
        + _metric("Accessibility · Lighthouse", _score(row.get("accessibility_score")))
        + _metric("Best Practices · Lighthouse", _score(row.get("best_practices_score")))
        + _metric("SEO técnico · Lighthouse", _score(row.get("seo_score")))
        + _metric("Agentic Browsing · Lighthouse experimental", _score(row.get("agentic_browsing_score")))
    )
    diagnostics = row.get("lighthouse_category_diagnostics")
    return f"""<article class='page-card'><div class='finding-head'><div><span class='badge'>{escape(str(row.get('device') or '-'))}</span> <span class='badge info'>{escape(str(row.get('status') or '-'))}</span></div><span class='badge'>{escape(str(row.get('field_source') or 'SEM FIELD DATA'))}</span></div>
<h3 class='page-url'>{escape(str(row.get('normalized_url') or row.get('url') or '-'))}</h3>
<h4>Lighthouse · scores por categoria</h4><div class='metric-grid'>{category_scores}</div>
<p class='intro'>Os valores acima vêm diretamente das categorias presentes no <code>lighthouseResult</code> e são persistidos em escala 0-100. O RASAi multiplica o valor 0..1 retornado pela API por 100 apenas para apresentação; não repondera, não combina e não recalcula a metodologia Lighthouse. <strong>SEO técnico</strong> não representa “SEO total”; <strong>Agentic Browsing</strong> é experimental.</p>
{_category_checks(diagnostics)}
<h4>Performance · métricas de laboratório associadas ao Lighthouse</h4><div class='metric-grid'>{_metric('FCP lab', _ms(row.get('fcp_lab_ms')))}{_metric('Speed Index', _ms(row.get('speed_index_lab_ms')))}{_metric('LCP lab', _ms(row.get('lcp_lab_ms')))}{_metric('TBT lab', _ms(row.get('tbt_lab_ms')))}{_metric('CLS lab', _number(row.get('cls_lab'), 3))}</div>
<p class='intro'>FCP, Speed Index, LCP lab, TBT e CLS lab pertencem ao diagnóstico de <strong>Performance Lighthouse</strong>. Eles não são detalhes de Accessibility, Best Practices, SEO ou Agentic Browsing.</p>
<h4>Core Web Vitals · dados reais CrUX</h4><div class='metric-grid'>{_metric('CWV', str(row.get('cwv_assessment') or '-'))}{_metric('LCP p75', _ms(row.get('lcp_p75_ms')))}{_metric('INP p75', _ms(row.get('inp_p75_ms')))}{_metric('CLS p75', _number(row.get('cls_p75'), 3))}{_metric('Escopo', str(row.get('field_scope') or '-'))}{_metric('Fonte', str(row.get('field_source') or '-'))}</div>
{_cwv_explanation(row)}{_technical_details(row)}</article>"""


def _category_checks(diagnostics: Any) -> str:
    if not isinstance(diagnostics, dict):
        return "<div class='notice'><strong>Detalhes de checks Lighthouse:</strong> artifact bruto indisponível para projeção. Os scores persistidos permanecem sujeitos ao gate de integridade externo.</div>"
    blocks = []
    for category_id in ("best-practices", "seo", "agentic-browsing"):
        detail = diagnostics.get(category_id)
        if not isinstance(detail, dict):
            continue
        label = _LIGHTHOUSE_CATEGORY_LABELS[category_id]
        summary = (
            f"{int(detail.get('passed', 0))} aprovados · "
            f"{int(detail.get('failed', 0))} reprovados · "
            f"{int(detail.get('manual', 0))} manuais · "
            f"{int(detail.get('not_applicable', 0))} não aplicáveis · "
            f"{int(detail.get('other', 0))} outros"
        )
        failures = detail.get("failures")
        rows = []
        if isinstance(failures, list):
            for item in failures:
                if not isinstance(item, dict):
                    continue
                score = item.get("score")
                score_label = "-" if score is None else f"{float(score) * 100:.0f}/100"
                rows.append(
                    "<tr>"
                    f"<td><code>{escape(str(item.get('id') or '-'))}</code></td>"
                    f"<td>{escape(score_label)}</td>"
                    f"<td>{escape(str(item.get('weight') if item.get('weight') is not None else '-'))}</td>"
                    f"<td><strong>{escape(str(item.get('title') or '-'))}</strong>"
                    f"<br><span class='muted'>{escape(str(item.get('display_value') or ''))}</span></td>"
                    f"<td>{escape(str(item.get('description') or item.get('explanation') or '-'))}</td>"
                    "</tr>"
                )
        failure_table = (
            "<div class='table-wrap'><table><thead><tr><th>Audit ID</th><th>Score</th><th>Peso</th><th>Check</th><th>Detalhe Lighthouse</th></tr></thead><tbody>"
            + ("".join(rows) if rows else "<tr><td colspan='5'>Nenhum check reprovado com detalhe estruturado neste artifact.</td></tr>")
            + "</tbody></table></div>"
        )
        experimental = " Categoria experimental; sua composição pode mudar entre versões do Lighthouse." if category_id == "agentic-browsing" else ""
        blocks.append(
            f"<details><summary>{escape(label)} · checks Lighthouse ({escape(summary)})</summary>"
            f"<div class='detail-body'><p class='intro'>Resumo calculado pelo RASAi a partir dos <code>auditRefs</code> da categoria. "
            f"O score da categoria continua sendo o valor fornecido pelo Lighthouse.{escape(experimental)}</p>{failure_table}</div></details>"
        )
    return "".join(blocks) if blocks else "<p class='intro'>O artifact não trouxe <code>auditRefs</code> detalhados para Best Practices, SEO ou Agentic Browsing.</p>"


def _load_lighthouse_category_diagnostics(
    workspace: AuditWorkspace,
    artifact_reference: str | None,
) -> dict[str, Any] | None:
    payload = _read_json_artifact(workspace, artifact_reference)
    if payload is None:
        return None
    result = payload.get("lighthouseResult")
    if not isinstance(result, dict):
        return None
    categories = result.get("categories")
    audits = result.get("audits")
    if not isinstance(categories, dict) or not isinstance(audits, dict):
        return None

    output: dict[str, Any] = {}
    for category_id in _LIGHTHOUSE_CATEGORY_LABELS:
        category = categories.get(category_id)
        if not isinstance(category, dict):
            continue
        refs = category.get("auditRefs")
        refs = refs if isinstance(refs, list) else []
        passed = failed = manual = not_applicable = other = 0
        failures: list[dict[str, Any]] = []
        for ref in refs:
            if not isinstance(ref, dict):
                continue
            audit_id = str(ref.get("id") or "").strip()
            audit = audits.get(audit_id)
            if not audit_id or not isinstance(audit, dict):
                other += 1
                continue
            mode = str(audit.get("scoreDisplayMode") or "").casefold()
            score = _float(audit.get("score"))
            if mode == "manual":
                manual += 1
                continue
            if mode in {"notapplicable", "not-applicable"}:
                not_applicable += 1
                continue
            if score is not None and score >= 1.0:
                passed += 1
                continue
            if score is not None and score < 1.0:
                failed += 1
                if len(failures) < 50:
                    failures.append(
                        {
                            "id": audit_id,
                            "score": score,
                            "weight": _float(ref.get("weight")),
                            "title": str(audit.get("title") or audit_id),
                            "description": _plain(audit.get("description")),
                            "display_value": _plain(audit.get("displayValue")),
                            "explanation": _plain(audit.get("explanation")),
                        }
                    )
                continue
            other += 1
        output[category_id] = {
            "passed": passed,
            "failed": failed,
            "manual": manual,
            "not_applicable": not_applicable,
            "other": other,
            "failures": failures,
        }
    return output


def _read_json_artifact(workspace: AuditWorkspace, reference: str | None) -> dict[str, Any] | None:
    if not reference:
        return None
    root = workspace.root.resolve()
    path = (workspace.root / reference).resolve()
    try:
        path.relative_to(root)
    except ValueError:
        return None
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _index_summary(data: dict[str, Any]) -> str:
    run = data["run"]
    if run is None:
        return ""
    enabled, status = bool(run["enabled"]), str(run["status"])
    observations = data["observations"]
    cwv_pass = sum(1 for row in observations if str(row.get("cwv_assessment")) == "PASS")
    cwv_valid = sum(1 for row in observations if str(row.get("cwv_assessment")) in {"PASS", "FAIL"})
    performance = _average_score(observations, "performance_score")
    accessibility = _average_score(observations, "accessibility_score")
    best_practices = _average_score(observations, "best_practices_score")
    seo = _average_score(observations, "seo_score")
    agentic = _average_score(observations, "agentic_browsing_score")
    return f"""<section id='web-performance-summary' class='panel'><div class='kicker'>Qualidade Web · evidência externa</div><h2>Web Performance e Lighthouse</h2><p class='intro'>Os scores Lighthouse são evidências externas: Performance, Accessibility, Best Practices, SEO técnico e Agentic Browsing experimental. O RASAi coleta e contextualiza esses valores sem convertê-los em {SCORING_VERSION}. Core Web Vitals permanecem field data CrUX.</p><div class='metric-grid'>{_metric('Coleta', 'Habilitada' if enabled else 'Desabilitada')}{_metric('Status', status)}{_metric('CWV aprovados', f'{cwv_pass}/{cwv_valid}' if cwv_valid else 'NÃO DISPONÍVEL')}{_metric('Performance Lighthouse · média', _score(performance))}{_metric('Accessibility Lighthouse · média', _score(accessibility))}{_metric('Best Practices Lighthouse · média', _score(best_practices))}{_metric('SEO técnico Lighthouse · média', _score(seo))}{_metric('Agentic Browsing Lighthouse · média experimental', _score(agentic))}</div><p><a href='{PERFORMANCE_FILE}'>Abrir Web Performance →</a></p></section>"""


def _references_section() -> str:
    rows = "".join(
        f"<tr><td>{escape(name)}</td><td>OFICIAL/PRIMÁRIA</td><td>{escape(description)}</td><td><a href='{escape(url)}' target='_blank' rel='noopener'>abrir fonte</a></td></tr>"
        for name, url, description in _OFFICIAL_REFERENCES
    )
    return f"""<section id='web-performance-methodology' class='panel'><div class='kicker'>Qualidade Web externa · fontes primárias</div><h2>Lighthouse, Core Web Vitals e limites de interpretação</h2><p class='intro'>Performance, Accessibility, Best Practices e SEO técnico são categorias Lighthouse consolidadas nesta integração; Agentic Browsing é uma categoria experimental do próprio Lighthouse. Todas permanecem métricas externas distintas e não homologam SARI-001 nem o Overall Readiness do RASAi.</p><div class='table-wrap'><table><thead><tr><th>Fonte</th><th>Base</th><th>Uso</th><th>Referência</th></tr></thead><tbody>{rows}</tbody></table></div><div class='notice'><strong>Regra de interpretação:</strong> field data CrUX é experiência agregada de usuários reais; Lighthouse é auditoria automatizada/laboratório. Nenhuma categoria é convertida silenciosamente em peso, fator ou threshold do {SCORING_VERSION}.</div></section>"""


def _nav(report_dir: Path) -> str:
    return render_report_navigation(report_dir, PERFORMANCE_FILE)


def _cwv_explanation(row: dict[str, Any]) -> str:
    status = str(row.get("cwv_assessment") or "UNAVAILABLE")
    if status == "PASS":
        return "<div class='notice'><strong>CWV: aprovado.</strong> As três métricas disponíveis atendem aos thresholds de boa experiência no p75.</div>"
    if status == "FAIL":
        return "<div class='notice warn'><strong>CWV: não aprovado.</strong> Ao menos uma das três métricas disponíveis excede o threshold de boa experiência no p75.</div>"
    if status == "INCOMPLETE":
        return "<div class='notice'><strong>CWV: avaliação incompleta.</strong> Não classificar ausência de amostra de uma métrica como falha do site.</div>"
    return "<div class='notice'><strong>CWV: não disponível.</strong> CrUX pode não possuir amostra suficiente para esta URL/form factor.</div>"


def _technical_details(row: dict[str, Any]) -> str:
    return f"""<details><summary>Rastreabilidade técnica</summary><div class='detail-body'><p><strong>Lighthouse version:</strong> {escape(str(row.get('lighthouse_version') or '-'))} · <strong>fetch time:</strong> {escape(str(row.get('lighthouse_fetch_time') or '-'))}</p><p><strong>Origem dos scores:</strong> <code>lighthouseResult.categories.performance.score</code> · <code>accessibility.score</code> · <code>best-practices.score</code> · <code>seo.score</code> · <code>agentic-browsing.score</code>. Persistência RASAi: <code>performance_score</code>, <code>accessibility_score</code>, <code>best_practices_score</code>, <code>seo_score</code>, <code>agentic_browsing_score</code>.</p><p><strong>PageSpeed artifact:</strong> <code>{escape(str(row.get('pagespeed_artifact_reference') or '-'))}</code></p><p><strong>CrUX artifact:</strong> <code>{escape(str(row.get('crux_artifact_reference') or '-'))}</code></p><p><strong>Erros/limitações:</strong> {escape(str(row.get('error_summary') or '-'))}</p><p><strong>Separação metodológica:</strong> Lighthouse/CrUX não dependem de LLM e não alteram SARI-001/{SCORING_VERSION}. Search Intelligence/SERP também não é inferido destes scores.</p></div></details>"""


def _average_score(observations: list[dict[str, Any]], key: str) -> float | None:
    values = [float(row[key]) for row in observations if row.get(key) is not None]
    return sum(values) / len(values) if values else None


def _plain(value: Any) -> str:
    return " ".join(str(value or "").split())


def _float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _metric(label: str, value: Any) -> str:
    return f"<div class='metric'><small>{escape(str(label))}</small><strong>{escape(str(value))}</strong></div>"


def _score(value: Any) -> str:
    return "-" if value is None else f"{float(value):.0f}/100"


def _ms(value: Any) -> str:
    return "-" if value is None else f"{float(value):.0f} ms"


def _number(value: Any, digits: int) -> str:
    return "-" if value is None else f"{float(value):.{digits}f}"


def _json_list(value: Any) -> list[str]:
    if value is None:
        return []
    try:
        parsed = json.loads(value) if isinstance(value, str) else value
    except json.JSONDecodeError:
        return []
    return [str(item) for item in parsed] if isinstance(parsed, list) else []
