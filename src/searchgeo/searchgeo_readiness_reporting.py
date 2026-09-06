"""Dedicated SearchGEO readiness reporting and cross-domain executive dashboard.

This module is deliberately projection-only. It never recalculates persisted
scores, Lighthouse/CrUX values or Apdex. ``SGRI-001`` is the public methodology
identifier for the current SearchGEO Readiness Index presentation; the persisted
calculation engine remains ``SCORE-GEO-002`` until the arithmetic itself changes.

The executive dashboard shows only final/summary outcomes and links to the
single analytical home of each indicator. Detailed SearchGEO dimensions live in
``searchgeo.html``; Lighthouse/CrUX, Accessibility and Apdex remain in their
respective pages.
"""
from __future__ import annotations

from collections import Counter
from html import escape
import json
from pathlib import Path
import re
import sqlite3
from typing import Any

from searchgeo import report_navigation
from searchgeo.content_context_persistence import load_content_analysis_context
from searchgeo.persistence import AuditWorkspace
from searchgeo.rule_references import references_for


SEARCHGEO_FILE = "searchgeo.html"
PUBLIC_METHOD_VERSION = "SGRI-001"
COMPATIBLE_ENGINE_VERSION = "SCORE-GEO-002"
_DASHBOARD_START = "<!-- searchgeo-executive-dashboard:start -->"
_DASHBOARD_END = "<!-- searchgeo-executive-dashboard:end -->"

_DIMENSION_LABELS = {
    "TECHNICAL_ACCESSIBILITY": "Acessibilidade técnica",
    "INDEXABILITY": "Capacidade de indexação",
    "CONTENT_EXTRACTABILITY": "Extração de conteúdo",
    "SEMANTIC_STRUCTURE": "Estrutura semântica",
    "ENTITY_CLARITY": "Clareza de entidades",
    "STRUCTURED_DATA": "Dados estruturados",
    "ANSWERABILITY": "Capacidade de resposta",
    "CITATION_READINESS": "Preparação para citação",
    "EVIDENCE_TRUST": "Evidências e confiabilidade",
    "INTENT_COVERAGE": "Cobertura de intenções",
}
_STATUS_LABELS = {
    "CONSOLIDATED": "Consolidado",
    "PARTIAL": "Parcial",
    "NOT_CONSOLIDATED": "Não consolidado",
    "NOT_APPLICABLE": "Não aplicável",
    "HIGH": "Alta",
    "MEDIUM": "Média",
    "LOW": "Baixa",
    "UNAVAILABLE": "Indisponível",
}

_SECTION_BY_KICKER = (
    "Leitura obrigatória",
    "Dimensões",
    "Escopo do produto",
)


def enrich_searchgeo_reporting(*, audit_id: str, workspace: AuditWorkspace) -> Path:
    """Create/update SearchGEO page and normalize dashboard/device report roles.

    Idempotent by design. It can run after M20, M21/M22, M23 and final report
    enrichments without changing source measurements.
    """
    report_dir = workspace.root / "report"
    report_dir.mkdir(parents=True, exist_ok=True)
    _register_navigation()
    data = _load(audit_id, workspace)

    searchgeo_path = report_dir / SEARCHGEO_FILE
    searchgeo_path.write_text(
        _searchgeo_page(data, workspace, report_dir),
        encoding="utf-8",
        newline="\n",
    )

    index_path = report_dir / "index.html"
    if index_path.is_file():
        html = index_path.read_text(encoding="utf-8")
        index_path.write_text(
            _rewrite_index(html, data, report_dir),
            encoding="utf-8",
            newline="\n",
        )

    for filename in ("mobile.html", "desktop.html"):
        path = report_dir / filename
        if not path.is_file():
            continue
        html = path.read_text(encoding="utf-8")
        path.write_text(
            _rewrite_device_page(html, filename),
            encoding="utf-8",
            newline="\n",
        )

    references_path = report_dir / "references.html"
    if references_path.is_file():
        html = references_path.read_text(encoding="utf-8")
        html = html.replace(
            "<div class=\"kicker\">SCORE-GEO-002</div><h2>Regras de cálculo</h2>",
            f"<div class=\"kicker\">{PUBLIC_METHOD_VERSION}</div><h2>Regras do SearchGEO Readiness Index</h2>",
        )
        html = html.replace(
            "<div class='kicker'>SCORE-GEO-002</div><h2>Regras de cálculo</h2>",
            f"<div class='kicker'>{PUBLIC_METHOD_VERSION}</div><h2>Regras do SearchGEO Readiness Index</h2>",
        )
        references_path.write_text(html, encoding="utf-8", newline="\n")

    report_navigation.normalize_report_navigation(report_dir)
    _post_normalize_language(report_dir)
    return searchgeo_path


def _register_navigation() -> None:
    items: list[tuple[str, str]] = []
    searchgeo_seen = False
    for label, filename in report_navigation.NAV_ITEMS:
        if filename == SEARCHGEO_FILE:
            if not searchgeo_seen:
                items.append(("SearchGEO Readiness", SEARCHGEO_FILE))
                searchgeo_seen = True
            continue
        if filename == "mobile.html":
            label = "Evidências Mobile"
        elif filename == "desktop.html":
            label = "Evidências Desktop"
        items.append((label, filename))
    if not searchgeo_seen:
        insertion = next(
            (index + 1 for index, value in enumerate(items) if value[1] == "index.html"),
            1,
        )
        items.insert(insertion, ("SearchGEO Readiness", SEARCHGEO_FILE))
    report_navigation.NAV_ITEMS = tuple(items)


def _load(audit_id: str, workspace: AuditWorkspace) -> dict[str, Any]:
    connection = sqlite3.connect(workspace.database)
    connection.row_factory = sqlite3.Row
    try:
        audit = _one(connection, "SELECT * FROM audits WHERE audit_id=?", (audit_id,))
        scores = _many(
            connection,
            "SELECT * FROM scores WHERE audit_id=? ORDER BY device,dimension",
            (audit_id,),
        )
        contributions = _many(
            connection,
            """SELECT c.* FROM score_contributions c
               JOIN scores s ON s.score_id=c.score_id
               WHERE s.audit_id=? ORDER BY c.device,c.dimension,c.rule_id,c.contribution_id""",
            (audit_id,),
        )
        web_run = _one(connection, "SELECT * FROM web_performance_runs WHERE audit_id=?", (audit_id,))
        web = _many(
            connection,
            """SELECT o.*,p.normalized_url FROM web_performance_observations o
               JOIN pages p ON p.page_id=o.page_id
               WHERE o.audit_id=? ORDER BY p.normalized_url,o.device,o.observation_id""",
            (audit_id,),
        )
        apdex_run = _one(connection, "SELECT * FROM synthetic_apdex_runs WHERE audit_id=?", (audit_id,))
        apdex = _many(
            connection,
            "SELECT * FROM synthetic_apdex_summaries WHERE audit_id=? ORDER BY url,device,summary_id",
            (audit_id,),
        )
        ai_session = _one(connection, "SELECT * FROM ai_audit_sessions WHERE audit_id=?", (audit_id,))
        ai_attempts = _many(connection, "SELECT * FROM ai_provider_attempts WHERE audit_id=? ORDER BY started_at,attempt_index,attempt_id", (audit_id,))
        return {
            "audit": audit,
            "scores": scores,
            "contributions": contributions,
            "web_run": web_run,
            "web": web,
            "apdex_run": apdex_run,
            "apdex": apdex,
            "ai_session": ai_session,
            "ai_attempts": ai_attempts,
        }
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


def _searchgeo_page(data: dict[str, Any], workspace: AuditWorkspace, report_dir: Path) -> str:
    audit = data["audit"]
    project = str(audit["project_name"]) if audit is not None and "project_name" in audit.keys() else "—"
    scores = data["scores"]
    engines = sorted({str(row["scoring_version"]) for row in scores if row["scoring_version"]})
    engine_label = ", ".join(engines) or COMPATIBLE_ENGINE_VERSION
    overall_cards = "".join(_overall_card(scores, device) for device in ("MOBILE", "DESKTOP") if _has_device(scores, device))
    dimension_tables = "".join(_dimension_table(scores, device) for device in ("MOBILE", "DESKTOP") if _has_device(scores, device))
    groundability = "".join(_groundability_block(scores, device) for device in ("MOBILE", "DESKTOP") if _has_device(scores, device))
    provenance = _provenance_block(data["contributions"])
    content_context = _content_context_block(workspace, str(audit["audit_id"]) if audit is not None else "")
    limitations_block = _audit_limitations_block(audit)
    ai_operational_block = _ai_operational_diagnostic(data)
    nav = report_navigation.render_report_navigation(report_dir, SEARCHGEO_FILE)
    return f"""<!doctype html>
<html lang='pt-BR'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>SearchGEO Readiness — SearchGEO Readiness Auditor</title><link rel='stylesheet' href='css/site.css'></head><body>{nav}<main class='app-main'>
<header class='hero'><div class='eyebrow'>SearchGEO · metodologia proprietária evidence-based</div><h1>SearchGEO Readiness Index</h1><p class='lead'>O {PUBLIC_METHOD_VERSION} consolida a prontidão observada para descoberta, interpretação, recuperação e uso como evidência em Search e AI Search. Não representa probabilidade de ranking, citação ou resposta por qualquer mecanismo externo.</p><div class='score-grid'>{overall_cards or "<div class='notice warn'>Readiness geral não consolidado.</div>"}</div><div class='metric-grid'>{_metric('Metodologia pública',PUBLIC_METHOD_VERSION)}{_metric('Motor persistido',engine_label)}{_metric('Projeto',project)}{_metric('Natureza','Heurística SearchGEO')}</div></header>
<section class='notice'><strong>Compatibilidade metodológica:</strong> {PUBLIC_METHOD_VERSION} é a identidade pública desta apresentação. O cálculo persistido continua usando <code>{escape(engine_label)}</code>; esta mudança de relatório não recalcula auditorias, não altera pesos e não quebra comparabilidade histórica.</section>
{limitations_block}
{ai_operational_block}
<section class='panel'><div class='kicker'>Indicadores proprietários</div><h2>Dimensões do readiness</h2><p class='intro'>Esta é a página canônica dos indicadores SearchGEO. Score, Coverage, Confidence e Consolidation não são repetidos nas páginas Mobile/Desktop; essas páginas passam a conter evidências e findings do respectivo dispositivo.</p>{dimension_tables or "<p class='intro'>Nenhuma dimensão de score persistida.</p>"}</section>
<section class='panel'><div class='kicker'>Groundability</div><h2>Sinais de capacidade de fundamentação</h2><p class='intro'>SGRI-001 não cria um novo subscore de Groundability. Para evitar uma heurística adicional não calibrada, o relatório expõe separadamente os sinais já persistidos de Answerability, Citation Readiness e Evidence & Trust.</p>{groundability or "<p class='intro'>Sinais não disponíveis.</p>"}</section>
{content_context}
{provenance}
<section class='panel'><div class='kicker'>Fórmula e limites</div><h2>Como interpretar o índice</h2><div class='grid'><article class='ref-card'><h3>Dimension Score</h3><p><code>Σ(weight × result_factor) / Σ(weight evaluated) × 100</code></p><p>PASS=1; WARNING=0,5 por padrão; FAIL=0. UNKNOWN/ERROR/NOT_APPLICABLE não são convertidos silenciosamente em FAIL.</p></article><article class='ref-card'><h3>Overall Readiness</h3><p>Média simples das dimensões aplicáveis suficientemente consolidadas. Dimensão legitimamente NOT_APPLICABLE não recebe zero.</p></article><article class='ref-card'><h3>Coverage</h3><p>Proporção do peso aplicável efetivamente avaliado. Mede completude da análise, não qualidade do site.</p></article><article class='ref-card'><h3>Confidence</h3><p>Qualifica a força da conclusão com thresholds internos versionados. Não é score de conteúdo nem probabilidade estatística.</p></article></div><div class='notice warn'><strong>Limite de validade:</strong> pesos, fatores WARNING, thresholds de Confidence/Consolidation e faixas visuais são decisões metodológicas do SearchGEO. Fontes externas sustentam os fenômenos observados, mas não homologam o índice composto.</div><p><a href='references.html#indicator-provenance'>Abrir proveniência, fontes primárias e regras de cálculo →</a></p></section>
<section class='panel'><div class='kicker'>Observed AI Visibility</div><h2>Separação entre readiness e resultado observado</h2><p class='intro'>Esta auditoria não transforma readiness em suposta probabilidade de citação. Métricas observadas de AI visibility só devem ser publicadas quando houver coleta externa específica, repetível e identificada por engine/query/período. Na ausência dessa evidência, nenhum número é fabricado.</p></section>
<footer class='footer'>SGRI-001 é uma metodologia proprietária, versionada e auditável do SearchGEO. Métricas externas permanecem em páginas próprias e mantêm sua metodologia original.</footer></main></body></html>\n"""


def _ai_operational_diagnostic(data: dict[str, Any]) -> str:
    attempts = [
        row for row in data.get("ai_attempts", [])
        if not str(row["semantic_contract_version"] or "").startswith("M20-")
    ]
    failures = [row for row in attempts if str(row["status"]) != "SUCCESS"]
    if not failures:
        return ""
    successes = [row for row in attempts if str(row["status"]) == "SUCCESS"]
    fallback_rows = [row for row in attempts if "fallback_from_provider" in row.keys() and row["fallback_from_provider"]]
    session = data.get("ai_session")
    initial = str(session["initial_provider"] or "—") if session is not None else str(failures[0]["provider"])
    effective = str(session["effective_provider"] or "—") if session is not None else (str(successes[-1]["provider"]) if successes else "—")
    detail_rows: list[str] = []
    for row in failures[:8]:
        error_class = str(row["error_class"] or row["status"])
        error_type = str(row["error_type"] or "—")
        error_code = str(row["error_code"] or "—")
        decision = str(row["decision"] if "decision" in row.keys() and row["decision"] else "STOP")
        detail_rows.append(
            "<li>" + escape(f"{row['provider']}/{row['model'] or '—'}: {error_class}; type={error_type}; code={error_code}; decisão={decision}") + "</li>"
        )
    if fallback_rows and successes:
        headline = "Fallback de IA utilizado por falha de integração"
        impact = (
            f"O provider que deveria atender primeiro era {initial}. Após erro operacional, "
            f"o SearchGEO utilizou {effective} como fallback e obteve resultado válido. "
            "O fallback é identificado na telemetria e não é atribuído ao website."
        )
        css = "notice"
    else:
        headline = "Análise semântica externa com erro operacional"
        impact = (
            f"O provider esperado era {initial}, mas não houve resultado semântico válido em todos os contextos. "
            "Regras dependentes da análise externa podem permanecer UNKNOWN e reduzir Coverage/Consolidation. "
            "Isto é limitação da integração de IA, não evidência de defeito no website."
        )
        css = "notice warn"
    return (
        f"<section class='{css}' data-ai-operational-diagnostic='true'>"
        f"<strong>{escape(headline)}</strong><p>{escape(impact)}</p>"
        f"<ul>{''.join(detail_rows)}</ul>"
        "<p>Consulte o bloco “Uso de IA — execução, erros, retry e fallback” para tokens, custo e sequência completa de tentativas.</p>"
        "</section>"
    )


def _audit_limitations_block(audit: sqlite3.Row | None) -> str:
    if audit is None or "limitations" not in audit.keys():
        return ""
    raw = audit["limitations"]
    try:
        values = json.loads(str(raw or "[]"))
    except (json.JSONDecodeError, TypeError, ValueError):
        values = []
    if not isinstance(values, list):
        values = []
    items = [str(item).strip() for item in values if str(item).strip()]
    if not items:
        return ""
    rows = "".join(f"<li>{escape(item)}</li>" for item in items)
    return (
        "<section class='notice warn' data-audit-limitations='true'>"
        "<strong>Por que esta auditoria possui limitações:</strong>"
        f"<ul>{rows}</ul>"
        "<p>Essas condições reduzem Coverage/Consolidation; não são convertidas automaticamente em falha do website.</p>"
        "</section>"
    )


def _overall_card(scores: list[sqlite3.Row], device: str) -> str:
    row = next(
        (
            item for item in scores
            if str(item["device"]).upper() == device and str(item["dimension"]) == "OVERALL_READINESS"
        ),
        None,
    )
    label = "Mobile" if device == "MOBILE" else "Desktop"
    if row is None or row["value"] is None or str(row["consolidation_status"]) == "NOT_CONSOLIDATED":
        coverage = f"{float(row['coverage']) * 100:.0f}%" if row is not None else "—"
        confidence = _STATUS_LABELS.get(str(row["confidence"]), str(row["confidence"])) if row is not None else "Indisponível"
        return f"<article class='score-card warn'><div class='label'>{escape(label)} · {PUBLIC_METHOD_VERSION}</div><div class='score-number'>Não consolidado</div><p class='intro'>Coverage {escape(coverage)} · Confidence {escape(confidence)}.</p></article>"
    value = float(row["value"])
    css = "good" if value >= 75 else "warn" if value >= 40 else "bad"
    confidence = str(row["confidence"])
    return f"<article class='score-card {css}'><div class='label'>{escape(label)} · {PUBLIC_METHOD_VERSION}</div><div class='score-number'>{value:.1f}<span>/100</span></div><div class='score-meta'><div><small>Coverage</small><strong>{float(row['coverage'])*100:.0f}%</strong></div><div><small>Confidence</small><strong>{escape(_STATUS_LABELS.get(confidence,confidence))}</strong></div><div><small>Consolidação</small><strong>{escape(_STATUS_LABELS.get(str(row['consolidation_status']),str(row['consolidation_status'])))}</strong></div></div></article>"


def _dimension_table(scores: list[sqlite3.Row], device: str) -> str:
    rows = [
        row for row in scores
        if str(row["device"]).upper() == device and str(row["dimension"]) != "OVERALL_READINESS"
    ]
    if not rows:
        return ""
    body: list[str] = []
    for row in rows:
        value = "—" if row["value"] is None else f"{float(row['value']):.1f}"
        body.append(
            "<tr>"
            f"<td>{escape(_DIMENSION_LABELS.get(str(row['dimension']),str(row['dimension'])))}</td>"
            f"<td>{value}</td><td>{float(row['coverage'])*100:.0f}%</td>"
            f"<td>{escape(_STATUS_LABELS.get(str(row['confidence']),str(row['confidence'])))}</td>"
            f"<td>{escape(_STATUS_LABELS.get(str(row['consolidation_status']),str(row['consolidation_status'])))}</td>"
            "</tr>"
        )
    label = "Mobile" if device == "MOBILE" else "Desktop"
    return f"<h3>{label}</h3><div class='table-wrap'><table><thead><tr><th>Dimensão</th><th>Score</th><th>Coverage</th><th>Confidence</th><th>Consolidação</th></tr></thead><tbody>{''.join(body)}</tbody></table></div>"


def _groundability_block(scores: list[sqlite3.Row], device: str) -> str:
    wanted = ("ANSWERABILITY", "CITATION_READINESS", "EVIDENCE_TRUST")
    rows = [
        row for dimension in wanted
        for row in scores
        if str(row["device"]).upper() == device and str(row["dimension"]) == dimension
    ]
    if not rows:
        return ""
    label = "Mobile" if device == "MOBILE" else "Desktop"
    metrics = "".join(
        _metric(
            _DIMENSION_LABELS.get(str(row["dimension"]), str(row["dimension"])),
            "NÃO CONSOLIDADO" if row["value"] is None else f"{float(row['value']):.1f}/100",
        )
        for row in rows
    )
    return f"<h3>{label}</h3><div class='metric-grid'>{metrics}</div>"


def _content_context_block(workspace: AuditWorkspace, audit_id: str) -> str:
    if not audit_id:
        return ""
    loaded = load_content_analysis_context(workspace=workspace, audit_id=audit_id)
    if loaded is None:
        return "<section class='panel'><div class='kicker'>Content Risk Profile</div><h2>Contexto editorial</h2><p class='intro'>Nenhum contexto editorial persistido para esta auditoria.</p></section>"
    context, metadata = loaded
    source_mode = str(metadata.get("source_mode") or "—")
    return f"""<section class='panel'><div class='kicker'>Content Risk Profile</div><h2>Contexto editorial aplicado</h2><p class='intro'>YMYL e E-E-A-T são usados como contexto de rigor e interpretação; não recebem um “score oficial”. O objetivo é reduzir análise semântica generalista e tornar recomendações mais aderentes ao risco do conteúdo.</p><div class='metric-grid'>{_metric('Risk profile',context.risk_profile.value)}{_metric('YMYL',context.ymyl_category.value)}{_metric('Page purpose',context.page_purpose.value)}{_metric('Audience',context.intended_audience.value)}{_metric('Experience requirement',context.experience_requirement.value)}{_metric('Freshness sensitivity',context.freshness_sensitivity.value)}{_metric('Content origin',context.content_origin.value)}{_metric('Resolução',source_mode)}</div><p><a href='content-suggestions.html'>Abrir análise e sugestões de conteúdo →</a></p></section>"""


def _provenance_block(contributions: list[sqlite3.Row]) -> str:
    rule_ids = sorted({str(row["rule_id"]) for row in contributions if row["rule_id"]})
    counts: Counter[str] = Counter()
    for rule_id in rule_ids:
        refs = references_for(rule_id)
        bases = {str(ref.basis) for ref in refs} or {"INTERNAL"}
        for basis in bases:
            counts[basis] += 1
    if not counts:
        body = "<p class='intro'>Nenhuma contribuição de score persistida.</p>"
    else:
        metrics = "".join(_metric(f"Regras com base {basis}", count) for basis, count in sorted(counts.items()))
        body = f"<div class='metric-grid'>{metrics}</div>"
    return f"""<section class='panel'><div class='kicker'>Proveniência do índice</div><h2>Base das regras contribuintes</h2><p class='intro'>A contagem abaixo descreve a classificação catalogada das BR-GEO que contribuíram para dimensões persistidas. Ela não é um peso adicional do score e uma regra pode possuir mais de uma referência.</p>{body}<p><a href='references.html#indicator-provenance'>Ver classificação, autoridade e fonte por indicador →</a></p></section>"""


def _rewrite_index(html: str, data: dict[str, Any], report_dir: Path) -> str:
    # Remove SearchGEO score cards from the legacy Overview header while keeping
    # audit metadata. The canonical SearchGEO score now lives in searchgeo.html.
    html = re.sub(
        r"<div class=\"score-grid\">.*?<div class=\"metric-grid\">",
        '<div class="metric-grid">',
        html,
        count=1,
        flags=re.DOTALL,
    )
    html = re.sub(
        r"<div class='score-grid'>.*?<div class='metric-grid'>",
        "<div class='metric-grid'>",
        html,
        count=1,
        flags=re.DOTALL,
    )
    for kicker in _SECTION_BY_KICKER:
        html = re.sub(
            rf"<section class=(['\"])panel\1>\s*<div class=(['\"])kicker\2>{re.escape(kicker)}</div>.*?</section>",
            "",
            html,
            count=1,
            flags=re.DOTALL,
        )

    # Remove legacy per-domain summaries/details from the index. Their final
    # outcomes are re-projected below in one compact dashboard; details stay in
    # their canonical pages.
    html = re.sub(r"<section id=['\"]m21-performance-summary['\"].*?</section>", "", html, flags=re.DOTALL)
    html = re.sub(r"<section id=['\"]m22-accessibility-summary['\"].*?</section>", "", html, flags=re.DOTALL)
    html = re.sub(
        r"<!-- searchgeo-m23-index-start -->.*?<!-- searchgeo-m23-index-end -->",
        "",
        html,
        flags=re.DOTALL,
    )
    html = re.sub(
        r"<!-- searchgeo-external-metrics-integrity:start -->.*?<!-- searchgeo-external-metrics-integrity:end -->",
        "",
        html,
        flags=re.DOTALL,
    )
    html = re.sub(
        rf"{re.escape(_DASHBOARD_START)}.*?{re.escape(_DASHBOARD_END)}",
        "",
        html,
        flags=re.DOTALL,
    )
    html = html.replace(
        "Dashboard executivo de readiness. O índice é um modelo interno e reprodutível do SearchGEO; não é uma nota oficial do Google, OpenAI ou de outro mantenedor.",
        "Dashboard executivo dos resultados finais disponíveis. Cada indicador mantém sua metodologia e sua página analítica própria; o painel não cruza métricas distintas em um score comum.",
    )
    dashboard = _dashboard(data, report_dir)
    if "</header>" in html:
        return html.replace("</header>", "</header>" + dashboard, 1)
    return html.replace("</main>", dashboard + "</main>", 1)


def _rewrite_device_page(html: str, filename: str) -> str:
    html = re.sub(
        r"<div class=\"score-grid\">.*?</header>",
        "</header>",
        html,
        count=1,
        flags=re.DOTALL,
    )
    html = re.sub(
        r"<div class='score-grid'>.*?</header>",
        "</header>",
        html,
        count=1,
        flags=re.DOTALL,
    )
    html = re.sub(
        r"<section class=(['\"])panel\1>\s*<div class=(['\"])kicker\2>Scorecard</div>.*?</section>",
        "",
        html,
        count=1,
        flags=re.DOTALL,
    )
    label = "Mobile" if filename == "mobile.html" else "Desktop"
    marker = "data-searchgeo-device-role='evidence-only'"
    if marker not in html:
        notice = (
            f"<section class='notice' {marker}><strong>Papel desta página:</strong> evidências e findings {label}. "
            f"Score, Coverage, Confidence e dimensões SearchGEO estão centralizados em <a href='{SEARCHGEO_FILE}'>SearchGEO Readiness</a>.</section>"
        )
        html = html.replace("</header>", "</header>" + notice, 1)
    html = html.replace("<div class=\"eyebrow\">Relatório por dispositivo</div>", "<div class=\"eyebrow\">Evidências por dispositivo</div>")
    html = html.replace("<div class='eyebrow'>Relatório por dispositivo</div>", "<div class='eyebrow'>Evidências por dispositivo</div>")
    return html


def _dashboard(data: dict[str, Any], report_dir: Path) -> str:
    cards: list[str] = []
    scores = data["scores"]
    for device in ("MOBILE", "DESKTOP"):
        row = next(
            (
                item for item in scores
                if str(item["device"]).upper() == device and str(item["dimension"]) == "OVERALL_READINESS"
            ),
            None,
        )
        if row is None:
            continue
        label = "Mobile" if device == "MOBILE" else "Desktop"
        if row["value"] is None or str(row["consolidation_status"]) == "NOT_CONSOLIDATED":
            value = "NÃO CONSOLIDADO"
            detail = f"Coverage {float(row['coverage'])*100:.0f}% · Confidence {_STATUS_LABELS.get(str(row['confidence']),str(row['confidence']))}"
        else:
            value = f"{float(row['value']):.1f}/100"
            detail = f"Coverage {float(row['coverage'])*100:.0f}% · Confidence {_STATUS_LABELS.get(str(row['confidence']),str(row['confidence']))}"
        cards.append(_indicator_card(f"SearchGEO Readiness · {label}", value, detail, SEARCHGEO_FILE, "SearchGEO · SGRI-001"))

    web = data["web"]
    cwv_values = [str(row["cwv_assessment"]) for row in web if str(row["cwv_assessment"]) in {"PASS", "FAIL"}]
    cwv_pass = sum(value == "PASS" for value in cwv_values)
    if cwv_values:
        cwv_value = f"{cwv_pass}/{len(cwv_values)} aprovados"
        cwv_detail = "Contextos com LCP, INP e CLS p75 suficientes"
    else:
        cwv_value = "NÃO DISPONÍVEL"
        cwv_detail = _external_status(data["web_run"])
    cards.append(_indicator_card("Core Web Vitals", cwv_value, cwv_detail, "web-performance.html", "Chrome / web.dev"))

    perf = _device_ranges(web, "performance_score", scale=100.0, suffix="/100")
    cards.append(_indicator_card("Lighthouse Performance", perf[0], perf[1], "web-performance.html", "Chrome Lighthouse"))

    a11y = _device_ranges(web, "accessibility_score", scale=100.0, suffix="/100")
    cards.append(_indicator_card("Lighthouse Accessibility", a11y[0], a11y[1], "accessibility.html", "Chrome Lighthouse + WCAG 2.2"))

    apdex_run = data["apdex_run"]
    apdex_rows = [row for row in data["apdex"] if row["apdex_score"] is not None]
    final_rows = [row for row in apdex_rows if _truthy(row, "final_group")]
    apdex_rows = final_rows or apdex_rows
    if apdex_rows:
        apdex_summary = _device_ranges(apdex_rows, "apdex_score", scale=1.0, suffix="", digits=3)
        apdex_value, apdex_detail = apdex_summary
    elif apdex_run is not None and not bool(apdex_run["enabled"]):
        apdex_value, apdex_detail = "DESABILITADO", "Medição opcional não executada"
    else:
        apdex_value, apdex_detail = "NÃO DISPONÍVEL", "Sem grupo Apdex final materializado"
    apdex_link = "apdex.html" if (report_dir / "apdex.html").is_file() else "web-performance.html"
    cards.append(_indicator_card("Synthetic Navigation Apdex", apdex_value, apdex_detail, apdex_link, "Apdex Technical Specification"))

    return (
        _DASHBOARD_START
        + "<section id='executive-indicator-dashboard' class='panel'><div class='kicker'>Dashboard executivo</div>"
        "<h2>Resultados finais por indicador</h2>"
        "<p class='intro'>O painel resume resultados sem misturar metodologias. Nenhum Lighthouse, Core Web Vitals, Accessibility ou Apdex é convertido no SGRI-001; cada card aponta para a página que contém evidência, escopo e fonte oficial.</p>"
        f"<div class='grid'>{''.join(cards)}</div></section>"
        + _DASHBOARD_END
    )


def _indicator_card(title: str, value: str, detail: str, href: str, source: str) -> str:
    return f"""<article class='ref-card'><div class='kicker'>{escape(source)}</div><h3>{escape(title)}</h3><div class='score-number'>{escape(value)}</div><p class='intro'>{escape(detail)}</p><p><a href='{escape(href, quote=True)}'>Analisar detalhes →</a></p></article>"""


def _device_ranges(
    rows: list[sqlite3.Row],
    column: str,
    *,
    scale: float,
    suffix: str,
    digits: int = 0,
) -> tuple[str, str]:
    by_device: dict[str, list[float]] = {}
    for row in rows:
        try:
            raw = row[column]
        except (IndexError, KeyError):
            continue
        if raw is None:
            continue
        device = str(row["device"] or "GLOBAL").upper() if "device" in row.keys() else "GLOBAL"
        by_device.setdefault(device, []).append(float(raw) * scale)
    if not by_device:
        return "NÃO DISPONÍVEL", "Nenhum contexto válido"
    parts: list[str] = []
    total = 0
    for device in ("MOBILE", "DESKTOP", "GLOBAL"):
        values = by_device.get(device)
        if not values:
            continue
        total += len(values)
        label = {"MOBILE": "Mobile", "DESKTOP": "Desktop", "GLOBAL": "Global"}[device]
        minimum, maximum = min(values), max(values)
        if abs(minimum - maximum) < 10 ** (-(digits + 2)):
            rendered = f"{minimum:.{digits}f}{suffix}"
        else:
            rendered = f"{minimum:.{digits}f}–{maximum:.{digits}f}{suffix}"
        parts.append(f"{label} {rendered}")
    if not parts:
        return "NÃO DISPONÍVEL", "Nenhum contexto válido"
    return " · ".join(parts), f"{total} contexto(s) com resultado válido; faixa, não média inventada"


def _external_status(run: sqlite3.Row | None) -> str:
    if run is None:
        return "Coleta externa não materializada"
    enabled = bool(run["enabled"])
    status = str(run["status"])
    return "Coleta desabilitada" if not enabled else f"Status da coleta: {status}"


def _truthy(row: sqlite3.Row, column: str) -> bool:
    try:
        return bool(row[column])
    except (IndexError, KeyError):
        return False


def _has_device(scores: list[sqlite3.Row], device: str) -> bool:
    return any(str(row["device"]).upper() == device for row in scores)


def _metric(label: str, value: Any) -> str:
    return f"<div class='metric'><small>{escape(str(label))}</small><strong>{escape(str(value))}</strong></div>"


def _post_normalize_language(report_dir: Path) -> None:
    replacements = {
        "index.html": (
            (
                "<strong>Natureza dos indicadores:</strong> Heurística SearchGEO + evidência rastreável. Score, Coverage, Confidence e Consolidation são índices internos versionados; observações e BR-GEO podem ter bases externas individuais.",
                "<strong>Natureza dos indicadores:</strong> painel multimetodológico. O SGRI-001 é proprietário; Core Web Vitals, Lighthouse e Apdex preservam metodologia externa e permanecem independentes.",
            ),
        ),
        "mobile.html": (
            (
                "Os scores deste dispositivo são internos. A base OFFICIAL/STANDARD/HEURISTIC de cada BR-GEO e seus links constam em Referências e metodologia.",
                "Esta página contém evidências e findings do dispositivo. Os indicadores agregados SearchGEO ficam exclusivamente em SearchGEO Readiness; a base de cada BR-GEO permanece rastreável em Referências e metodologia.",
            ),
        ),
        "desktop.html": (
            (
                "Os scores deste dispositivo são internos. A base OFFICIAL/STANDARD/HEURISTIC de cada BR-GEO e seus links constam em Referências e metodologia.",
                "Esta página contém evidências e findings do dispositivo. Os indicadores agregados SearchGEO ficam exclusivamente em SearchGEO Readiness; a base de cada BR-GEO permanece rastreável em Referências e metodologia.",
            ),
        ),
    }
    for filename, pairs in replacements.items():
        path = report_dir / filename
        if not path.is_file():
            continue
        html = path.read_text(encoding="utf-8")
        for old, new in pairs:
            html = html.replace(old, new)
        path.write_text(html, encoding="utf-8", newline="\n")
