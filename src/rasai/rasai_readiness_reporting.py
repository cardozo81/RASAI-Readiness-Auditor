"""Canonical SARI-001 reporting and executive indicator dashboard.

This module is projection-only. It never recalculates persisted scores,
Lighthouse/Core Web Vitals values, accessibility results or Apdex. SARI-001 is
the public Search & AI Readiness Index and SCORE-GEO-004 is its sole runtime
scoring contract.
"""
from __future__ import annotations

from collections import Counter
from html import escape
import json
from pathlib import Path
import re
import sqlite3
from typing import Any

from rasai import report_navigation
from rasai.branding import CANONICAL_READINESS_REPORT, PUBLIC_INDEX_VERSION
from rasai.content_context_persistence import load_content_analysis_context
from rasai.persistence import AuditWorkspace
from rasai.rule_references import references_for


RASAI_FILE = CANONICAL_READINESS_REPORT
PUBLIC_METHOD_VERSION = PUBLIC_INDEX_VERSION
COMPATIBLE_ENGINE_VERSION = "SCORE-GEO-004"
_DASHBOARD_START = "<!-- rasai-executive-dashboard:start -->"
_DASHBOARD_END = "<!-- rasai-executive-dashboard:end -->"

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
_SECTION_BY_KICKER = ("Leitura obrigatória", "Dimensões", "Escopo do produto")


def enrich_rasai_reporting(*, audit_id: str, workspace: AuditWorkspace) -> Path:
    """Materialize the canonical SARI page and normalize final report roles."""
    report_dir = workspace.root / "report"
    report_dir.mkdir(parents=True, exist_ok=True)
    _register_navigation()
    data = _load(audit_id, workspace)

    readiness = report_dir / RASAI_FILE
    readiness.write_text(
        _rasai_page(data, workspace, report_dir), encoding="utf-8", newline="\n"
    )

    index_path = report_dir / "index.html"
    if index_path.is_file():
        index_path.write_text(
            _rewrite_index(index_path.read_text(encoding="utf-8"), data, report_dir),
            encoding="utf-8",
            newline="\n",
        )

    for filename in ("mobile.html", "desktop.html"):
        path = report_dir / filename
        if path.is_file():
            path.write_text(
                _rewrite_device_page(path.read_text(encoding="utf-8"), filename),
                encoding="utf-8",
                newline="\n",
            )

    report_navigation.normalize_report_navigation(report_dir)
    _post_normalize_language(report_dir)
    return readiness


def _register_navigation() -> None:
    items: list[tuple[str, str]] = []
    seen = False
    for label, filename in report_navigation.NAV_ITEMS:
        if filename == RASAI_FILE:
            if not seen:
                items.append(("Search & AI Readiness", RASAI_FILE))
                seen = True
            continue
        if filename == "mobile.html":
            label = "Relatório Mobile"
        elif filename == "desktop.html":
            label = "Relatório Desktop"
        items.append((label, filename))
    if not seen:
        insertion = next(
            (i + 1 for i, item in enumerate(items) if item[1] == "index.html"), 1
        )
        items.insert(insertion, ("Search & AI Readiness", RASAI_FILE))
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
               WHERE s.audit_id=?
               ORDER BY c.device,c.dimension,c.rule_id,c.contribution_id""",
            (audit_id,),
        )
        web_run = _one(
            connection, "SELECT * FROM web_performance_runs WHERE audit_id=?", (audit_id,)
        )
        web = _many(
            connection,
            """SELECT o.*,p.normalized_url FROM web_performance_observations o
               JOIN pages p ON p.page_id=o.page_id
               WHERE o.audit_id=?
               ORDER BY p.normalized_url,o.device,o.observation_id""",
            (audit_id,),
        )
        apdex_run = _one(
            connection, "SELECT * FROM synthetic_apdex_runs WHERE audit_id=?", (audit_id,)
        )
        apdex = _many(
            connection,
            "SELECT * FROM synthetic_apdex_summaries WHERE audit_id=? ORDER BY url,device,summary_id",
            (audit_id,),
        )
        ai_session = _one(
            connection, "SELECT * FROM ai_audit_sessions WHERE audit_id=?", (audit_id,)
        )
        ai_attempts = _many(
            connection,
            "SELECT * FROM ai_provider_attempts WHERE audit_id=? ORDER BY started_at,attempt_index,attempt_id",
            (audit_id,),
        )
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


def _rasai_page(data: dict[str, Any], workspace: AuditWorkspace, report_dir: Path) -> str:
    audit = data["audit"]
    project = str(audit["project_name"]) if audit is not None and "project_name" in audit.keys() else "-"
    scores = data["scores"]
    engines = sorted({str(row["scoring_version"]) for row in scores if row["scoring_version"]})
    engine_label = ", ".join(engines) or COMPATIBLE_ENGINE_VERSION
    overall_cards = "".join(
        _overall_card(scores, device)
        for device in ("MOBILE", "DESKTOP")
        if _has_device(scores, device)
    )
    dimension_tables = "".join(
        _dimension_table(scores, device)
        for device in ("MOBILE", "DESKTOP")
        if _has_device(scores, device)
    )
    groundability = "".join(
        _groundability_block(scores, device)
        for device in ("MOBILE", "DESKTOP")
        if _has_device(scores, device)
    )
    nav = report_navigation.render_report_navigation(report_dir, RASAI_FILE)
    audit_id = str(audit["audit_id"]) if audit is not None and "audit_id" in audit.keys() else ""
    return f"""<!doctype html>
<html lang='pt-BR'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>Search & AI Readiness - RASAi - Search & AI Readiness Auditor</title><link rel='stylesheet' href='css/site.css'></head><body>{nav}<main class='app-main'>
<header class='hero'><div class='eyebrow'>RASAi - metodologia proprietária evidence-based</div><h1>Search & AI Readiness Index</h1><p class='lead'>O {PUBLIC_METHOD_VERSION} consolida sinais de prontidão para descoberta, interpretação, recuperação e uso como evidência em Search e AI Search. Não representa probabilidade de ranking, resposta ou citação futura.</p><div class='score-grid'>{overall_cards or "<div class='notice warn'>Readiness geral não disponível com a evidência persistida.</div>"}</div><div class='metric-grid'>{_metric('Metodologia pública', PUBLIC_METHOD_VERSION)}{_metric('Método de scoring', engine_label)}{_metric('Projeto', project)}{_metric('Natureza', 'Heurística RASAi reproduzível')}</div></header>
<section class='notice'><strong>Contrato metodológico:</strong> novas auditorias usam <code>{escape(COMPATIBLE_ENGINE_VERSION)}</code>. O Overall é determinístico e não depende de model artifact ou calibração externa. Lighthouse, Core Web Vitals, Accessibility e Apdex permanecem indicadores independentes e não entram no SARI-001.</section>
{_audit_limitations_block(audit)}
{_ai_operational_diagnostic(data)}
<section class='panel'><div class='kicker'>Indicadores proprietários</div><h2>Dimensões do readiness</h2><p class='intro'>Score, Coverage, Confidence e Consolidation ficam centralizados nesta página. As páginas Mobile/Desktop preservam evidências e findings do respectivo dispositivo.</p>{dimension_tables or "<p class='intro'>Nenhuma dimensão de score persistida.</p>"}</section>
<section class='panel'><div class='kicker'>Groundability</div><h2>Sinais de capacidade de fundamentação</h2><p class='intro'>SARI-001 não cria um subscore adicional de Groundability. Answerability, Citation Readiness e Evidence & Trust permanecem sinais distintos e rastreáveis.</p>{groundability or "<p class='intro'>Sinais não disponíveis.</p>"}</section>
{_content_context_block(workspace, audit_id)}
{_provenance_block(data["contributions"])}
<section class='panel'><div class='kicker'>Fórmula e limites</div><h2>Como interpretar o índice</h2><div class='grid'><article class='ref-card'><h3>Dimension Score</h3><p><code>sum(weight x result_factor) / sum(weight evaluated) x 100</code></p><p>PASS=1; WARNING=0,5 por padrão; FAIL=0. UNKNOWN/ERROR/NOT_APPLICABLE não são convertidos silenciosamente em FAIL.</p></article><article class='ref-card'><h3>Overall Readiness</h3><p>Média de igual peso das dimensões aplicáveis com medição suficiente. Dimensão legitimamente NOT_APPLICABLE sai do denominador e não recebe zero.</p></article><article class='ref-card'><h3>Coverage</h3><p>Mede completude da análise aplicável. O Overall usa a média da Coverage das dimensões aplicáveis.</p></article><article class='ref-card'><h3>Confidence</h3><p>O Overall usa a menor Confidence entre as dimensões aplicáveis. Para consolidar, exige Coverage média de pelo menos 80% e Confidence mínima MEDIUM.</p></article></div><div class='notice warn'><strong>Limite de validade:</strong> pesos, fatores WARNING e thresholds de Coverage/Confidence/Consolidation são decisões metodológicas versionadas do RASAi. O índice não é homologado por mecanismo de busca ou provedor de IA.</div><p><a href='score-geo-004.html'>Abrir contrato completo do SCORE-GEO-004</a></p><p><a href='references.html#indicator-provenance'>Abrir proveniência, fontes primárias e regras de cálculo</a></p></section>
<section class='panel'><div class='kicker'>Observed AI Visibility</div><h2>Separação entre readiness e resultado observado</h2><p class='intro'>Readiness não é convertido em suposta probabilidade de citação. Resultados observados de AI visibility permanecem datasets independentes quando coletados com engine, query e período identificados.</p></section>
<footer class='footer'>SARI-001 e SCORE-GEO-004 são contratos proprietários, versionados e auditáveis do RASAi. Não garantem ranking, tráfego, conversão ou citação futura.</footer></main></body></html>\n"""


def _overall_card(scores: list[sqlite3.Row], device: str) -> str:
    row = next(
        (
            item for item in scores
            if str(item["device"]).upper() == device
            and str(item["dimension"]) == "OVERALL_READINESS"
        ),
        None,
    )
    label = "Mobile" if device == "MOBILE" else "Desktop"
    if row is None:
        return f"<article class='score-card warn'><div class='label'>{label} - {PUBLIC_METHOD_VERSION}</div><div class='score-number'>Indisponível</div><p class='intro'>Overall não persistido.</p></article>"
    coverage = f"{float(row['coverage']) * 100:.0f}%"
    confidence = _STATUS_LABELS.get(str(row["confidence"]), str(row["confidence"]))
    consolidation = str(row["consolidation_status"])
    if row["value"] is None:
        return f"<article class='score-card warn'><div class='label'>{label} - {PUBLIC_METHOD_VERSION}</div><div class='score-number'>Não consolidado</div><p class='intro'>Coverage {escape(coverage)} - Confidence {escape(confidence)}. Consulte as dimensões bloqueantes.</p></article>"
    value = float(row["value"])
    css = "good" if consolidation == "CONSOLIDATED" and value >= 75 else "warn" if value >= 40 else "bad"
    status = _STATUS_LABELS.get(consolidation, consolidation)
    return f"<article class='score-card {css}'><div class='label'>{label} - {PUBLIC_METHOD_VERSION}</div><div class='score-number'>{value:.1f}<span>/100</span></div><div class='score-meta'><div><small>Coverage</small><strong>{coverage}</strong></div><div><small>Confidence</small><strong>{escape(confidence)}</strong></div><div><small>Consolidação</small><strong>{escape(status)}</strong></div></div></article>"


def _dimension_table(scores: list[sqlite3.Row], device: str) -> str:
    rows = [
        row for row in scores
        if str(row["device"]).upper() == device
        and str(row["dimension"]) != "OVERALL_READINESS"
    ]
    if not rows:
        return ""
    body: list[str] = []
    for row in rows:
        value = "-" if row["value"] is None else f"{float(row['value']):.1f}"
        body.append(
            "<tr>"
            f"<td>{escape(_DIMENSION_LABELS.get(str(row['dimension']), str(row['dimension'])))}</td>"
            f"<td>{value}</td><td>{float(row['coverage']) * 100:.0f}%</td>"
            f"<td>{escape(_STATUS_LABELS.get(str(row['confidence']), str(row['confidence'])))}</td>"
            f"<td>{escape(_STATUS_LABELS.get(str(row['consolidation_status']), str(row['consolidation_status'])))}</td>"
            "</tr>"
        )
    label = "Mobile" if device == "MOBILE" else "Desktop"
    return f"<h3>{label}</h3><div class='table-wrap'><table><thead><tr><th>Dimensão</th><th>Score</th><th>Coverage</th><th>Confidence</th><th>Consolidação</th></tr></thead><tbody>{''.join(body)}</tbody></table></div>"


def _groundability_block(scores: list[sqlite3.Row], device: str) -> str:
    wanted = ("ANSWERABILITY", "CITATION_READINESS", "EVIDENCE_TRUST")
    rows = [
        row for dimension in wanted for row in scores
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


def _audit_limitations_block(audit: sqlite3.Row | None) -> str:
    if audit is None or "limitations" not in audit.keys():
        return ""
    try:
        values = json.loads(str(audit["limitations"] or "[]"))
    except (json.JSONDecodeError, TypeError, ValueError):
        values = []
    items = [str(item).strip() for item in values if str(item).strip()] if isinstance(values, list) else []
    if not items:
        return ""
    rows = "".join(f"<li>{escape(item)}</li>" for item in items)
    return f"<section class='notice warn' data-audit-limitations='true'><strong>Limitações da auditoria:</strong><ul>{rows}</ul><p>Essas condições podem reduzir Coverage ou Consolidation; não são convertidas automaticamente em falha do website.</p></section>"


def _ai_operational_diagnostic(data: dict[str, Any]) -> str:
    attempts = [
        row for row in data.get("ai_attempts", [])
        if not str(_row_get(row, "semantic_contract_version", "") or "").startswith("M20-")
    ]
    failures = [row for row in attempts if str(_row_get(row, "status", "")) != "SUCCESS"]
    if not failures:
        return ""
    successes = [row for row in attempts if str(_row_get(row, "status", "")) == "SUCCESS"]
    session = data.get("ai_session")
    initial = str(_row_get(session, "initial_provider", "-") if session is not None else _row_get(failures[0], "provider", "-"))
    effective = str(_row_get(session, "effective_provider", "-") if session is not None else (_row_get(successes[-1], "provider", "-") if successes else "-"))
    details = "".join(
        "<li>" + escape(
            f"{_row_get(row, 'provider', '-')}/{_row_get(row, 'model', '-')}: "
            f"{_row_get(row, 'error_class', _row_get(row, 'status', '-'))}; "
            f"code={_row_get(row, 'error_code', '-')}"
        ) + "</li>"
        for row in failures[:8]
    )
    if successes:
        headline = "Fallback de IA utilizado após falha operacional"
        impact = f"O provider inicial era {initial}; a execução obteve resultado válido com {effective}. Falha de provider não é atribuída ao website."
        css = "notice"
    else:
        headline = "Análise semântica externa incompleta"
        impact = "Regras dependentes da análise externa podem permanecer UNKNOWN e reduzir Coverage/Confidence. Isso é limitação da integração, não evidência de defeito no website."
        css = "notice warn"
    return f"<section class='{css}' data-ai-operational-diagnostic='true'><strong>{escape(headline)}</strong><p>{escape(impact)}</p><ul>{details}</ul></section>"


def _content_context_block(workspace: AuditWorkspace, audit_id: str) -> str:
    if not audit_id:
        return ""
    loaded = load_content_analysis_context(workspace=workspace, audit_id=audit_id)
    if loaded is None:
        return "<section class='panel'><div class='kicker'>Content Risk Profile</div><h2>Contexto editorial</h2><p class='intro'>Nenhum contexto editorial persistido para esta auditoria.</p></section>"
    context, metadata = loaded
    source_mode = str(metadata.get("source_mode") or "-")
    return f"<section class='panel'><div class='kicker'>Content Risk Profile</div><h2>Contexto editorial aplicado</h2><p class='intro'>YMYL e E-E-A-T orientam rigor e interpretação; não são scores oficiais.</p><div class='metric-grid'>{_metric('Risk profile', context.risk_profile.value)}{_metric('YMYL', context.ymyl_category.value)}{_metric('Page purpose', context.page_purpose.value)}{_metric('Audience', context.intended_audience.value)}{_metric('Experience requirement', context.experience_requirement.value)}{_metric('Freshness sensitivity', context.freshness_sensitivity.value)}{_metric('Content origin', context.content_origin.value)}{_metric('Resolução', source_mode)}</div><p><a href='content-suggestions.html'>Abrir análise e sugestões de conteúdo</a></p></section>"


def _provenance_block(contributions: list[sqlite3.Row]) -> str:
    rule_ids = sorted({str(row["rule_id"]) for row in contributions if row["rule_id"]})
    counts: Counter[str] = Counter()
    for rule_id in rule_ids:
        bases = {str(ref.basis) for ref in references_for(rule_id)} or {"INTERNAL"}
        for basis in bases:
            counts[basis] += 1
    body = (
        "<p class='intro'>Nenhuma contribuição de score persistida.</p>"
        if not counts
        else "<div class='metric-grid'>" + "".join(
            _metric(f"Regras com base {basis}", count)
            for basis, count in sorted(counts.items())
        ) + "</div>"
    )
    return f"<section class='panel'><div class='kicker'>Proveniência do índice</div><h2>Base das regras contribuintes</h2><p class='intro'>A classificação das BR-GEO descreve a base documental das regras; não adiciona um peso oculto ao score.</p>{body}<p><a href='references.html#indicator-provenance'>Ver classificação, autoridade e fonte por indicador</a></p></section>"


def _rewrite_index(html: str, data: dict[str, Any], report_dir: Path) -> str:
    html = re.sub(
        r"<div class=\"score-grid\">.*?<div class=\"metric-grid\">",
        '<div class="metric-grid">', html, count=1, flags=re.DOTALL,
    )
    html = re.sub(
        r"<div class='score-grid'>.*?<div class='metric-grid'>",
        "<div class='metric-grid'>", html, count=1, flags=re.DOTALL,
    )
    for kicker in _SECTION_BY_KICKER:
        html = re.sub(
            rf"<section class=(['\"])panel\1>\s*<div class=(['\"])kicker\2>{re.escape(kicker)}</div>.*?</section>",
            "", html, count=1, flags=re.DOTALL,
        )
    html = re.sub(r"<section id=['\"]m21-performance-summary['\"].*?</section>", "", html, flags=re.DOTALL)
    html = re.sub(r"<section id=['\"]m22-accessibility-summary['\"].*?</section>", "", html, flags=re.DOTALL)
    html = re.sub(r"<!-- rasai-m23-index-start -->.*?<!-- rasai-m23-index-end -->", "", html, flags=re.DOTALL)
    html = re.sub(r"<!-- rasai-external-metrics-integrity:start -->.*?<!-- rasai-external-metrics-integrity:end -->", "", html, flags=re.DOTALL)
    html = re.sub(rf"{re.escape(_DASHBOARD_START)}.*?{re.escape(_DASHBOARD_END)}", "", html, flags=re.DOTALL)
    html = html.replace(
        "Dashboard executivo de readiness. O índice é um modelo interno e reprodutível do RASAi; não é uma nota oficial do Google, OpenAI ou de outro mantenedor.",
        "Dashboard executivo dos resultados finais disponíveis. Cada indicador mantém sua metodologia e sua página analítica própria; o painel não cruza métricas distintas em um score comum.",
    )
    dashboard = _dashboard(data, report_dir)
    return html.replace("</header>", "</header>" + dashboard, 1) if "</header>" in html else html.replace("</main>", dashboard + "</main>", 1)


def _rewrite_device_page(html: str, filename: str) -> str:
    html = re.sub(r"<div class=\"score-grid\">.*?</header>", "</header>", html, count=1, flags=re.DOTALL)
    html = re.sub(r"<div class='score-grid'>.*?</header>", "</header>", html, count=1, flags=re.DOTALL)
    html = re.sub(
        r"<section class=(['\"])panel\1>\s*<div class=(['\"])kicker\2>Scorecard</div>.*?</section>",
        "", html, count=1, flags=re.DOTALL,
    )
    label = "Mobile" if filename == "mobile.html" else "Desktop"
    marker = "data-rasai-device-role='evidence-only'"
    if marker not in html:
        notice = f"<section class='notice' {marker}><strong>Papel desta página:</strong> evidências e findings {label}. Score, Coverage, Confidence e dimensões RASAi estão centralizados em <a href='{RASAI_FILE}'>Search & AI Readiness</a>.</section>"
        html = html.replace("</header>", "</header>" + notice, 1)
    html = html.replace("Relatório por dispositivo", "Evidências por dispositivo")
    return html


def _dashboard(data: dict[str, Any], report_dir: Path) -> str:
    cards: list[str] = []
    scores = data["scores"]
    for device in ("MOBILE", "DESKTOP"):
        row = next(
            (
                item for item in scores
                if str(item["device"]).upper() == device
                and str(item["dimension"]) == "OVERALL_READINESS"
            ), None,
        )
        if row is None:
            continue
        label = "Mobile" if device == "MOBILE" else "Desktop"
        coverage = f"{float(row['coverage']) * 100:.0f}%"
        confidence = _STATUS_LABELS.get(str(row["confidence"]), str(row["confidence"]))
        if row["value"] is None:
            value = "NÃO CONSOLIDADO"
            detail = f"Coverage {coverage} - Confidence {confidence}"
        else:
            value = f"{float(row['value']):.1f}/100"
            status = _STATUS_LABELS.get(str(row["consolidation_status"]), str(row["consolidation_status"]))
            detail = f"Coverage {coverage} - Confidence {confidence} - {status}"
        cards.append(_indicator_card(f"Search & AI Readiness - {label}", value, detail, RASAI_FILE, "RASAi - SARI-001"))

    web = data["web"]
    cwv_values = [str(row["cwv_assessment"]) for row in web if str(row["cwv_assessment"]) in {"PASS", "FAIL"}]
    if cwv_values:
        cwv_value = f"{sum(value == 'PASS' for value in cwv_values)}/{len(cwv_values)} aprovados"
        cwv_detail = "Contextos com LCP, INP e CLS p75 suficientes"
    else:
        cwv_value, cwv_detail = "NÃO DISPONÍVEL", _external_status(data["web_run"])
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
        apdex_value, apdex_detail = _device_ranges(apdex_rows, "apdex_score", scale=1.0, suffix="", digits=3)
    elif apdex_run is not None and not bool(apdex_run["enabled"]):
        apdex_value, apdex_detail = "DESABILITADO", "Medição opcional não executada"
    else:
        apdex_value, apdex_detail = "NÃO DISPONÍVEL", "Sem grupo Apdex final materializado"
    apdex_link = "apdex.html" if (report_dir / "apdex.html").is_file() else "web-performance.html"
    cards.append(_indicator_card("Synthetic Navigation Apdex", apdex_value, apdex_detail, apdex_link, "Apdex Technical Specification"))

    return (
        _DASHBOARD_START
        + "<section id='executive-indicator-dashboard' class='panel'><div class='kicker'>Dashboard executivo</div><h2>Resultados finais por indicador</h2><p class='intro'>O painel resume resultados sem misturar metodologias. Nenhum Lighthouse, Core Web Vitals, Accessibility ou Apdex é convertido no SARI-001; cada card aponta para a página que contém evidência, escopo e fonte.</p>"
        + f"<div class='grid'>{''.join(cards)}</div></section>"
        + _DASHBOARD_END
    )


def _indicator_card(title: str, value: str, detail: str, href: str, source: str) -> str:
    return f"<article class='ref-card'><div class='kicker'>{escape(source)}</div><h3>{escape(title)}</h3><div class='score-number'>{escape(value)}</div><p class='intro'>{escape(detail)}</p><p><a href='{escape(href, quote=True)}'>Analisar detalhes</a></p></article>"


def _device_ranges(rows: list[sqlite3.Row], column: str, *, scale: float, suffix: str, digits: int = 0) -> tuple[str, str]:
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
        rendered = f"{minimum:.{digits}f}{suffix}" if abs(minimum - maximum) < 10 ** (-(digits + 2)) else f"{minimum:.{digits}f}-{maximum:.{digits}f}{suffix}"
        parts.append(f"{label} {rendered}")
    return (" - ".join(parts), f"{total} contexto(s) com resultado válido; faixa, não média inventada") if parts else ("NÃO DISPONÍVEL", "Nenhum contexto válido")


def _external_status(run: sqlite3.Row | None) -> str:
    if run is None:
        return "Coleta externa não materializada"
    return "Coleta desabilitada" if not bool(run["enabled"]) else f"Status da coleta: {run['status']}"


def _truthy(row: sqlite3.Row, column: str) -> bool:
    try:
        return bool(row[column])
    except (IndexError, KeyError):
        return False


def _has_device(scores: list[sqlite3.Row], device: str) -> bool:
    return any(str(row["device"]).upper() == device for row in scores)


def _metric(label: str, value: Any) -> str:
    return f"<div class='metric'><small>{escape(str(label))}</small><strong>{escape(str(value))}</strong></div>"


def _row_get(row: sqlite3.Row | None, key: str, default: Any = None) -> Any:
    if row is None:
        return default
    try:
        return row[key] if key in row.keys() and row[key] not in (None, "") else default
    except (IndexError, KeyError, AttributeError):
        return default


def _post_normalize_language(report_dir: Path) -> None:
    replacements = {
        "index.html": (
            ("<strong>Natureza dos indicadores:</strong> Heurística RASAi + evidência rastreável. Score, Coverage, Confidence e Consolidation são índices internos versionados; observações e BR-GEO podem ter bases externas individuais.", "<strong>Natureza dos indicadores:</strong> painel multimetodológico. O SARI-001 é proprietário; Core Web Vitals, Lighthouse e Apdex preservam metodologia externa e permanecem independentes."),
        ),
        "mobile.html": (
            ("Os scores deste dispositivo são internos. A base OFFICIAL/STANDARD/HEURISTIC de cada BR-GEO e seus links constam em Referências e metodologia.", "Esta página contém evidências e findings do dispositivo. Os indicadores agregados RASAi ficam exclusivamente em Search & AI Readiness; a base de cada BR-GEO permanece rastreável em Referências e metodologia."),
        ),
        "desktop.html": (
            ("Os scores deste dispositivo são internos. A base OFFICIAL/STANDARD/HEURISTIC de cada BR-GEO e seus links constam em Referências e metodologia.", "Esta página contém evidências e findings do dispositivo. Os indicadores agregados RASAi ficam exclusivamente em Search & AI Readiness; a base de cada BR-GEO permanece rastreável em Referências e metodologia."),
        ),
    }
    for filename, pairs in replacements.items():
        path = report_dir / filename
        if not path.is_file():
            continue
        html = path.read_text(encoding="utf-8")
        for old, new in pairs:
            html = html.replace(old, new)
        path.write_text(html.replace("—", "-").replace("–", "-"), encoding="utf-8", newline="\n")
