"""Project Web Performance externo web performance evidence into the static report site."""

from __future__ import annotations

from html import escape
import json
from pathlib import Path
import sqlite3
from typing import Any

from searchgeo.m22_quality_domains import enrich_m22_domain_reports
from searchgeo.persistence import AuditWorkspace
from searchgeo.report_navigation import normalize_report_navigation, render_report_navigation

PERFORMANCE_FILE = "web-performance.html"

_OFFICIAL_REFERENCES = (
    ("PageSpeed Insights API v5", "https://developers.google.com/speed/docs/insights/v5/reference/pagespeedapi/runpagespeed", "API oficial para Lighthouse e, enquanto disponível, dados de campo CrUX na resposta."),
    ("PageSpeed Insights — Get Started", "https://developers.google.com/speed/docs/insights/v5/get-started", "Documenta uso com/sem chave e a migração recomendada de field data para CrUX API."),
    ("Chrome UX Report API", "https://developer.chrome.com/docs/crux/api/", "API oficial de experiência real agregada, com LCP, INP e CLS por URL/origin e form factor."),
    ("Como usar a CrUX API", "https://developer.chrome.com/docs/crux/guides/crux-api", "Documenta percentil 75, form factors e avaliação de Core Web Vitals."),
    ("Lighthouse Performance Scoring", "https://developer.chrome.com/docs/lighthouse/performance/performance-scoring", "Explica score 0–100, pesos e curvas log-normais baseadas em HTTP Archive."),
    ("Core Web Vitals", "https://web.dev/articles/vitals", "Define LCP, INP e CLS e os thresholds de experiência considerada boa."),
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
        if html_path.name == "index.html" and "m21-performance-summary" not in html:
            html = html.replace("</header>", "</header>" + _index_summary(data), 1)
        if html_path.name == "references.html" and "m21-performance-methodology" not in html:
            html = html.replace("</main>", _references_section() + "</main>", 1)
        html_path.write_text(html, encoding="utf-8", newline="\n")

    # Acessibilidade automatizada e diagnósticos Web consumes only the already-persisted Web Performance externo artifacts. It creates an
    # independent Accessibility page and adds evidence-bound performance
    # diagnostics without changing GEO scoring or making another network call.
    enrich_m22_domain_reports(audit_id=audit_id, workspace=workspace)
    normalize_report_navigation(report_dir)
    return path


def _load(audit_id: str, workspace: AuditWorkspace) -> dict[str, Any]:
    connection = sqlite3.connect(workspace.database)
    connection.row_factory = sqlite3.Row
    try:
        run = _one(connection, "SELECT * FROM web_performance_runs WHERE audit_id=?", (audit_id,))
        observations = _many(connection, """SELECT o.*,p.normalized_url FROM web_performance_observations o JOIN pages p ON p.page_id=o.page_id WHERE o.audit_id=? ORDER BY p.normalized_url,o.device,o.observation_id""", (audit_id,))
        attempts = _many(connection, "SELECT * FROM web_performance_attempts WHERE audit_id=? ORDER BY created_at,service,attempt_id", (audit_id,))
        return {"run": run, "observations": observations, "attempts": attempts}
    finally:
        connection.close()


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
    field_source = str(run["field_source"]) if run is not None else "—"
    page_limit = int(run["page_limit"]) if run is not None else 0
    pages = int(run["pages_considered"]) if run is not None else 0
    contexts = int(run["context_attempts"]) if run is not None else 0
    successes = int(run["successful_contexts"]) if run is not None else 0
    categories = ", ".join(_json_list(run["categories"])) if run is not None else "—"
    limit_label = "todas as páginas auditadas" if page_limit == 0 else str(page_limit)

    cards = []
    for row in observations:
        cards.append(f"""<article class='page-card'><div class='finding-head'><div><span class='badge'>{escape(str(row['device']))}</span> <span class='badge info'>{escape(str(row['status']))}</span></div><span class='badge'>{escape(str(row['field_source'] or 'SEM FIELD DATA'))}</span></div><h3 class='page-url'>{escape(str(row['normalized_url']))}</h3><h4>Lighthouse · laboratório de performance</h4><div class='metric-grid'>{_metric('Performance', _score(row['performance_score']))}{_metric('FCP lab', _ms(row['fcp_lab_ms']))}{_metric('Speed Index', _ms(row['speed_index_lab_ms']))}{_metric('LCP lab', _ms(row['lcp_lab_ms']))}{_metric('TBT lab', _ms(row['tbt_lab_ms']))}{_metric('CLS lab', _number(row['cls_lab'], 3))}</div><p class='intro'>Lighthouse é medição de laboratório. O score de Performance é externo ao SearchGEO e não é convertido em SCORE-GEO-002. O score de Accessibility coletado no mesmo payload é projetado exclusivamente em <a href='accessibility.html'>Acessibilidade</a>.</p><h4>Core Web Vitals · dados reais CrUX</h4><div class='metric-grid'>{_metric('CWV', str(row['cwv_assessment']))}{_metric('LCP p75', _ms(row['lcp_p75_ms']))}{_metric('INP p75', _ms(row['inp_p75_ms']))}{_metric('CLS p75', _number(row['cls_p75'], 3))}{_metric('Escopo', str(row['field_scope'] or '—'))}{_metric('Fonte', str(row['field_source'] or '—'))}</div>{_cwv_explanation(row)}{_technical_details(row)}</article>""")

    attempt_rows = []
    for row in attempts:
        attempt_rows.append("<tr>" + f"<td class='mono'>{escape(str(row['url']))}</td><td>{escape(str(row['device']))}</td><td>{escape(str(row['service']))}</td><td>{escape(str(row['status']))}</td><td>{escape(str(row['http_status'] if row['http_status'] is not None else '—'))}</td><td>{escape(str(row['duration_ms']))} ms</td><td>{escape(str(row['error_code'] or '—'))}</td></tr>")

    if not enabled:
        notice = "<div class='notice'><strong>Coleta externa desabilitada.</strong> Esse é o comportamento padrão para evitar tráfego/quota externa não solicitado. SCORE-GEO-002 continua disponível normalmente.</div>"
    elif status in {"PARTIAL", "UNAVAILABLE"}:
        notice = "<div class='notice warn'><strong>Coleta externa incompleta.</strong> Falha, quota, ausência de amostra CrUX ou indisponibilidade do serviço não é defeito do website e não reduz SCORE-GEO-002.</div>"
    else:
        notice = "<div class='notice'><strong>Evidência externa coletada.</strong> Lighthouse/CrUX permanecem métricas independentes do índice heurístico SearchGEO.</div>"

    nav = _nav(report_dir)
    return f"""<!doctype html><html lang='pt-BR'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>Web Performance — SearchGEO Readiness Auditor</title><link rel='stylesheet' href='css/site.css'></head><body>{nav}<main class='app-main'><header class='hero'><div class='eyebrow'>Web Performance externo + Acessibilidade automatizada e diagnósticos Web · domínio Web Performance</div><h1>Core Web Vitals, Lighthouse e diagnóstico técnico</h1><p class='lead'>Camada externa e não destrutiva. Mede laboratório via Lighthouse e experiência real via CrUX quando disponível. Performance permanece separada de GEO e de Acessibilidade.</p><div class='metric-grid'>{_metric('Coleta externa', 'Habilitada' if enabled else 'Desabilitada')}{_metric('Status', status)}{_metric('Páginas consideradas', pages)}{_metric('Contextos', f'{successes}/{contexts}')}{_metric('Limite configurado', limit_label)}{_metric('Field source', field_source)}</div></header>{notice}<section class='panel'><div class='kicker'>Separação metodológica</div><h2>O que estes números significam</h2><p class='intro'><strong>Core Web Vitals</strong> são métricas de experiência real agregada: LCP, INP e CLS no percentil 75. <strong>Lighthouse</strong> é teste de laboratório e seu score 0–100 usa metodologia própria do Chrome. Nenhum destes valores representa probabilidade de citação em IA e nenhum é incorporado automaticamente ao Overall Readiness do SCORE-GEO-002.</p><div class='notice'><strong>Thresholds oficiais de “boa” experiência:</strong> LCP ≤ 2,5 s · INP ≤ 200 ms · CLS ≤ 0,1. A avaliação conjunta fica incompleta quando uma das três métricas não possui dados suficientes.</div><p class='intro'>Categorias solicitadas ao Lighthouse: <code>{escape(categories)}</code>. Uma única chamada pode transportar evidências de mais de um domínio para reduzir consumo externo, mas Acessibilidade automatizada e diagnósticos Web as projeta em páginas e interpretações separadas.</p></section><section class='panel'><div class='kicker'>Resultados</div><h2>Por página e dispositivo</h2>{''.join(cards) if cards else '<p class="intro">Nenhuma observação externa persistida.</p>'}</section><section class='panel'><div class='kicker'>Operação externa</div><h2>Tentativas de coleta</h2><p class='intro'>Esta telemetria é de serviços de medição, não de IA. Chaves de API nunca são persistidas nem exibidas.</p><div class='table-wrap'><table><thead><tr><th>URL</th><th>Device</th><th>Serviço</th><th>Status</th><th>HTTP</th><th>Duração</th><th>Erro</th></tr></thead><tbody>{''.join(attempt_rows) if attempt_rows else '<tr><td colspan="7">Nenhuma chamada externa.</td></tr>'}</tbody></table></div></section><section class='panel'><div class='kicker'>Governança de consumo</div><h2>Custos, quota e IA</h2><p class='intro'>Web Performance externo/Acessibilidade automatizada e diagnósticos Web não criam chamadas a LLM. OpenAI, DeepSeek e MiMo continuam restritos às finalidades já configuradas em Análise semântica por IA, roteamento e telemetria/Sugestões e remediação de conteúdo por IA. O consumo desta camada é somente PageSpeed/CrUX e ocorre apenas quando explicitamente habilitado.</p><p class='intro'>PageSpeed pode ser chamado sem chave em baixo volume, mas uma chave é recomendada para automação frequente. CrUX API direta exige chave. O limite de páginas e o timeout são configuráveis para controlar quota e duração.</p></section><footer class='footer'>Web Performance é evidência complementar. SCORE-GEO-002 permanece índice heurístico independente e reprodutível.</footer></main></body></html>\n"""


def _index_summary(data: dict[str, Any]) -> str:
    run = data["run"]
    if run is None:
        return ""
    enabled, status = bool(run["enabled"]), str(run["status"])
    observations = data["observations"]
    cwv_pass = sum(1 for row in observations if str(row["cwv_assessment"]) == "PASS")
    cwv_valid = sum(1 for row in observations if str(row["cwv_assessment"]) in {"PASS", "FAIL"})
    lighthouse = [float(row["performance_score"]) for row in observations if row["performance_score"] is not None]
    avg = sum(lighthouse) / len(lighthouse) if lighthouse else None
    return f"""<section id='m21-performance-summary' class='panel'><div class='kicker'>Domínio independente</div><h2>Web Performance</h2><p class='intro'>Core Web Vitals e Lighthouse são apresentados separadamente do SCORE-GEO-002 e da página de Acessibilidade. Falha de coleta externa não é finding GEO do website.</p><div class='metric-grid'>{_metric('Coleta', 'Habilitada' if enabled else 'Desabilitada')}{_metric('Status', status)}{_metric('CWV aprovados', f'{cwv_pass}/{cwv_valid}' if cwv_valid else 'NÃO DISPONÍVEL')}{_metric('Lighthouse médio', f'{avg:.0f}/100' if avg is not None else 'NÃO DISPONÍVEL')}</div><p><a href='{PERFORMANCE_FILE}'>Abrir Web Performance →</a></p></section>"""


def _references_section() -> str:
    rows = "".join(f"<tr><td>{escape(name)}</td><td>OFICIAL</td><td>{escape(description)}</td><td><a href='{escape(url)}' target='_blank' rel='noopener'>abrir fonte</a></td></tr>" for name, url, description in _OFFICIAL_REFERENCES)
    return f"""<section id='m21-performance-methodology' class='panel'><div class='kicker'>Web Performance externo · fontes externas</div><h2>Core Web Vitals e Lighthouse Performance</h2><p class='intro'>Estas fontes sustentam somente os fenômenos que documentam. Elas não homologam o Overall Readiness do SearchGEO.</p><div class='table-wrap'><table><thead><tr><th>Fonte</th><th>Base</th><th>Uso</th><th>Referência</th></tr></thead><tbody>{rows}</tbody></table></div><div class='notice'><strong>Regra de interpretação:</strong> field data CrUX é experiência agregada de usuários reais; Lighthouse é laboratório. Nenhuma métrica é convertida silenciosamente em peso, fator ou threshold do SCORE-GEO-002.</div></section>"""


def _nav(report_dir: Path) -> str:
    return render_report_navigation(report_dir, PERFORMANCE_FILE)


def _cwv_explanation(row: sqlite3.Row) -> str:
    status = str(row["cwv_assessment"])
    if status == "PASS": return "<div class='notice'><strong>CWV: aprovado.</strong> As três métricas disponíveis atendem aos thresholds de boa experiência no p75.</div>"
    if status == "FAIL": return "<div class='notice warn'><strong>CWV: não aprovado.</strong> Ao menos uma das três métricas disponíveis excede o threshold de boa experiência no p75.</div>"
    if status == "INCOMPLETE": return "<div class='notice'><strong>CWV: avaliação incompleta.</strong> Não classificar ausência de amostra de uma métrica como falha do site.</div>"
    return "<div class='notice'><strong>CWV: não disponível.</strong> CrUX pode não possuir amostra suficiente para esta URL/form factor.</div>"


def _technical_details(row: sqlite3.Row) -> str:
    return f"""<details><summary>Rastreabilidade técnica</summary><div class='detail-body'><p><strong>Lighthouse version:</strong> {escape(str(row['lighthouse_version'] or '—'))} · <strong>fetch time:</strong> {escape(str(row['lighthouse_fetch_time'] or '—'))}</p><p><strong>PageSpeed artifact:</strong> <code>{escape(str(row['pagespeed_artifact_reference'] or '—'))}</code></p><p><strong>CrUX artifact:</strong> <code>{escape(str(row['crux_artifact_reference'] or '—'))}</code></p><p><strong>Erros/limitações:</strong> {escape(str(row['error_summary'] or '—'))}</p></div></details>"""


def _metric(label: str, value: Any) -> str: return f"<div class='metric'><small>{escape(str(label))}</small><strong>{escape(str(value))}</strong></div>"
def _score(value: Any) -> str: return "—" if value is None else f"{float(value):.0f}/100"
def _ms(value: Any) -> str: return "—" if value is None else f"{float(value):.0f} ms"
def _number(value: Any, digits: int) -> str: return "—" if value is None else f"{float(value):.{digits}f}"
def _json_list(value: Any) -> list[str]:
    if value is None: return []
    try: parsed = json.loads(value) if isinstance(value, str) else value
    except json.JSONDecodeError: return []
    return [str(item) for item in parsed] if isinstance(parsed, list) else []
