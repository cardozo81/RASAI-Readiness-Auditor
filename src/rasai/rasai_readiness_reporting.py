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
        discovery_executions = _many(
            connection,
            "SELECT * FROM rule_executions WHERE audit_id=? AND rule_id IN ('BR-GEO-003','BR-GEO-017','BR-GEO-018','BR-GEO-055','BR-GEO-056') ORDER BY rule_id,rule_execution_id",
            (audit_id,),
        )
        m24_run = _one(
            connection,
            "SELECT * FROM m24_runs WHERE audit_id=? ORDER BY completed_at DESC LIMIT 1",
            (audit_id,),
        )
        rule_executions = _many(
            connection,
            "SELECT rule_execution_id,rule_id,page_id,device,result,observed_value,expected_condition,error,evidence_ids FROM rule_executions WHERE audit_id=? ORDER BY rule_id,rule_execution_id",
            (audit_id,),
        )
        target = _one(
            connection,
            "SELECT * FROM audit_targets WHERE audit_id=? ORDER BY target_id LIMIT 1",
            (audit_id,),
        )
        return {
            "audit": audit,
            "target": target,
            "scores": scores,
            "contributions": contributions,
            "rule_executions": rule_executions,
            "web_run": web_run,
            "web": web,
            "apdex_run": apdex_run,
            "apdex": apdex,
            "ai_session": ai_session,
            "ai_attempts": ai_attempts,
            "discovery_executions": discovery_executions,
            "m24_run": m24_run,
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
{_sari_governance_block(data)}
{_ai_operational_diagnostic(data)}
<section class='panel'><div class='kicker'>Indicadores proprietários</div><h2>Dimensões do readiness</h2><p class='intro'>Score, Coverage, Confidence e Consolidation ficam centralizados nesta página. As páginas Mobile/Desktop preservam evidências e findings do respectivo dispositivo.</p>{dimension_tables or "<p class='intro'>Nenhuma dimensão de score persistida.</p>"}</section>
<section class='panel'><div class='kicker'>Groundability</div><h2>Sinais de capacidade de fundamentação</h2><p class='intro'>SARI-001 não cria um subscore adicional de Groundability. Answerability, Citation Readiness e Evidence & Trust permanecem sinais distintos e rastreáveis.</p>{groundability or "<p class='intro'>Sinais não disponíveis.</p>"}</section>
{_discovery_scoring_block(data)}
{_structured_data_scoring_block(data)}
{_content_context_block(workspace, audit_id)}
{_provenance_block(data["contributions"])}
<section class='panel'><div class='kicker'>Fórmula e limites</div><h2>Como interpretar o índice</h2><div class='grid'><article class='ref-card'><h3>Dimension Score</h3><p><code>sum(weight x result_factor) / sum(weight evaluated) x 100</code></p><p>PASS=1; WARNING=0,5 por padrão; FAIL=0. UNKNOWN/ERROR/NOT_APPLICABLE não são convertidos silenciosamente em FAIL.</p></article><article class='ref-card'><h3>Overall Readiness</h3><p>Média de igual peso das dimensões aplicáveis com medição suficiente. Dimensão legitimamente NOT_APPLICABLE sai do denominador e não recebe zero.</p></article><article class='ref-card'><h3>Coverage</h3><p>Mede completude da análise aplicável. O Overall usa a média da Coverage das dimensões aplicáveis.</p></article><article class='ref-card'><h3>Confidence</h3><p>O Overall usa a menor Confidence entre as dimensões aplicáveis. Para consolidar, exige Coverage média de pelo menos 80% e Confidence mínima MEDIUM. A presença de IA não é requisito: uma execução NO_AI pode atingir MEDIUM/HIGH quando Coverage, evidências e integridade da execução forem suficientes.</p></article></div><div class='notice warn'><strong>Limite de validade:</strong> pesos, fatores WARNING e thresholds de Coverage/Confidence/Consolidation são decisões metodológicas versionadas do RASAi. O índice não é homologado por mecanismo de busca ou provedor de IA.</div><p><a href='score-geo-004.html'>Abrir contrato completo do SCORE-GEO-004</a></p><p><a href='references.html#indicator-provenance'>Abrir proveniência, fontes primárias e regras de cálculo</a></p></section>
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


def _governance_rule_description(rule_id: str) -> str:
    text = report_navigation._RULE_TOOLTIPS.get(rule_id, "")
    if " · " in text:
        return text.split(" · ", 1)[1]
    return text or "Critério versionado do RASAi."


def _governance_json(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    try:
        parsed = json.loads(str(value or "{}"))
    except (json.JSONDecodeError, TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _governance_execution(data: dict[str, Any], execution_id: str) -> sqlite3.Row | None:
    return next(
        (row for row in data.get("rule_executions", []) if str(row["rule_execution_id"]) == execution_id),
        None,
    )


def _governance_action(data: dict[str, Any], contribution: sqlite3.Row) -> str:
    execution = _governance_execution(data, str(contribution["rule_execution_id"]))
    if execution is not None:
        expected = str(execution["expected_condition"] or "").strip()
        if expected:
            return expected
    return _governance_rule_description(str(contribution["rule_id"]))


def _governance_observed_reason(data: dict[str, Any], contribution: sqlite3.Row) -> str:
    execution = _governance_execution(data, str(contribution["rule_execution_id"]))
    if execution is None:
        return ""
    observed = _governance_json(execution["observed_value"])
    for key in ("reason", "status", "state", "error"):
        value = observed.get(key)
        if value not in (None, "", [], {}):
            return f"{key}={value}"
    error = str(execution["error"] or "").strip()
    return error


def _sari_dashboard_explanation(data: dict[str, Any]) -> str:
    scores = data.get("scores", [])
    blocks: list[str] = []
    for device in ("MOBILE", "DESKTOP"):
        overall = next(
            (row for row in scores if str(row["device"]).upper() == device and str(row["dimension"]) == "OVERALL_READINESS"),
            None,
        )
        if overall is None or str(overall["consolidation_status"]) == "CONSOLIDATED":
            continue
        blockers = [
            row for row in scores
            if str(row["device"]).upper() == device
            and str(row["dimension"]) != "OVERALL_READINESS"
            and (str(row["confidence"]) in {"LOW", "UNAVAILABLE"} or str(row["consolidation_status"]) != "CONSOLIDATED")
        ]
        blocker_text = ", ".join(
            f"{_DIMENSION_LABELS.get(str(row['dimension']), str(row['dimension']))} ({float(row['coverage'])*100:.0f}% Coverage / {_STATUS_LABELS.get(str(row['confidence']), str(row['confidence']))})"
            for row in blockers
        ) or "uma ou mais dimensões não atingiram os gates de medição"
        label = "Mobile" if device == "MOBILE" else "Desktop"
        blocks.append(
            f"<div class='notice warn sari-governance-summary'><strong>Por que {label} está {escape(_STATUS_LABELS.get(str(overall['consolidation_status']), str(overall['consolidation_status'])))}:</strong> "
            f"o score {float(overall['value']):.1f}/100 descreve a qualidade dos grupos efetivamente avaliados; a Confidence qualifica a força da medição. "
            f"Neste AUD, o bloqueador é {escape(blocker_text)}. Para consolidar, é preciso tornar esses grupos conclusivos; não basta aumentar o score numérico. "
            "<a href='readiness.html#sari-governance'>Ver causa, regra e ação necessária</a>.</div>"
        )
    return "".join(blocks)


def _sari_parameterization_note(data: dict[str, Any]) -> str:
    audit = data.get("audit")
    target = data.get("target")
    if audit is None:
        return ""
    try:
        limits_raw = audit["limitations"] if "limitations" in audit.keys() else "[]"
        limits = json.loads(str(limits_raw or "[]"))
    except (json.JSONDecodeError, TypeError, ValueError):
        limits = []
    items = [str(item) for item in limits] if isinstance(limits, list) else []
    rendered_gap = next((item for item in items if item.startswith("RENDERED_DISCOVERY_GAP:")), None)
    if rendered_gap is None:
        return ""
    count = rendered_gap.split(":", 1)[1] if ":" in rendered_gap else "?"
    target_type = str(target["target_type"] or "-") if target is not None and "target_type" in target.keys() else "-"
    max_pages = int(audit["max_pages"] or 0) if "max_pages" in audit.keys() else 0
    specific = ""
    if target_type.upper() == "DOMAIN" and max_pages <= 1:
        specific = (
            f" Neste AUD o target é DOMAIN com max_pages={max_pages}; isso é uma matriz mínima para um domínio. "
            "Se o objetivo for medir o domínio, aumente max_pages de forma conservadora. Se o objetivo for somente uma URL, prefira target de URL única."
        )
    return (
        "<div class='notice' data-parameterization-guidance='true'><strong>Parametrização e escopo:</strong> "
        f"o rendering encontrou {escape(count)} destino(s) same-origin fora do universo efetivamente auditado. "
        "Isso é uma limitação de cobertura do escopo escolhido, não um erro do RASAi e não é convertido automaticamente em FAIL do website."
        + escape(specific)
        + " Alterar parâmetros amplia a matriz de medição; não deve ser usado apenas para buscar uma nota maior.</div>"
    )


def _sari_governance_block(data: dict[str, Any]) -> str:
    scores = data.get("scores", [])
    contributions = data.get("contributions", [])
    sections: list[str] = []
    for device in ("MOBILE", "DESKTOP"):
        overall = next(
            (row for row in scores if str(row["device"]).upper() == device and str(row["dimension"]) == "OVERALL_READINESS"),
            None,
        )
        if overall is None:
            continue
        label = "Mobile" if device == "MOBILE" else "Desktop"
        dimensions = [
            row for row in scores
            if str(row["device"]).upper() == device and str(row["dimension"]) != "OVERALL_READINESS"
        ]
        blockers = [
            row for row in dimensions
            if str(row["confidence"]) in {"LOW", "UNAVAILABLE"} or str(row["consolidation_status"]) != "CONSOLIDATED"
        ]
        blocker_cards: list[str] = []
        for dimension in blockers:
            dim_name = str(dimension["dimension"])
            unresolved = [
                row for row in contributions
                if str(row["device"]).upper() == device
                and str(row["dimension"]) == dim_name
                and (str(row["result"]) in {"UNKNOWN", "ERROR"} or row["result_factor"] is None)
            ]
            details: list[str] = []
            for contribution in unresolved:
                rule_id = str(contribution["rule_id"])
                reason = _governance_observed_reason(data, contribution)
                action = _governance_action(data, contribution)
                details.append(
                    f"<li><strong>{escape(rule_id)}</strong> - {escape(_governance_rule_description(rule_id))}. "
                    + (f"<span class='muted'>Evidência atual: {escape(reason)}.</span> " if reason else "")
                    + f"<strong>Para tornar a medição conclusiva:</strong> {escape(action)}.</li>"
                )
            why = (
                f"Coverage {float(dimension['coverage'])*100:.1f}% · Confidence {_STATUS_LABELS.get(str(dimension['confidence']), str(dimension['confidence']))} · "
                f"Consolidação {_STATUS_LABELS.get(str(dimension['consolidation_status']), str(dimension['consolidation_status']))}"
            )
            blocker_cards.append(
                f"<article class='ref-card'><h4>{escape(_DIMENSION_LABELS.get(dim_name, dim_name))}</h4><p>{escape(why)}</p>"
                + (f"<ul>{''.join(details)}</ul>" if details else "<p>A dimensão não atingiu o gate; consulte suas RuleExecutions/evidências para a causa persistida.</p>")
                + "</article>"
            )

        deductions = [
            row for row in contributions
            if str(row["device"]).upper() == device
            and row["result_factor"] is not None
            and float(row["result_factor"]) < 1.0
        ]
        deduction_rows: list[str] = []
        for contribution in deductions[:16]:
            rule_id = str(contribution["rule_id"])
            dim_name = str(contribution["dimension"])
            deduction_rows.append(
                "<tr>"
                f"<td>{escape(_DIMENSION_LABELS.get(dim_name, dim_name))}</td>"
                f"<td><strong>{escape(rule_id)}</strong><br><small>{escape(_governance_rule_description(rule_id))}</small></td>"
                f"<td>{escape(str(contribution['result']))}</td>"
                f"<td>{float(contribution['weight']):g}</td>"
                f"<td>{float(contribution['result_factor']):.2f}</td>"
                f"<td>{escape(_governance_action(data, contribution))}</td>"
                "</tr>"
            )
        deductions_html = (
            "<h4>O que reduz o score e pode ser melhorado</h4><p class='intro'>Estes itens foram avaliados conclusivamente; portanto afetam a nota, mas não são necessariamente a causa de Confidence baixa. Corrigi-los melhora a qualidade medida. Não altere parâmetros apenas para mascarar esses resultados.</p>"
            "<div class='table-wrap'><table><thead><tr><th>Dimensão</th><th>Regra / critério</th><th>Resultado</th><th>Peso</th><th>Fator</th><th>Condição esperada</th></tr></thead>"
            f"<tbody>{''.join(deduction_rows)}</tbody></table></div>"
            if deduction_rows else "<p class='intro'>Nenhuma dedução conclusiva materializada neste dispositivo.</p>"
        )
        status = str(overall["consolidation_status"])
        confidence = str(overall["confidence"])
        summary_class = "good" if status == "CONSOLIDATED" else "warn"
        summary = (
            f"<div class='notice {summary_class}'><strong>Leitura de governança - {label}:</strong> "
            f"Overall {('-' if overall['value'] is None else format(float(overall['value']), '.1f') + '/100')} · Coverage {float(overall['coverage'])*100:.1f}% · "
            f"Confidence {_STATUS_LABELS.get(confidence, confidence)} · Consolidação {_STATUS_LABELS.get(status, status)}. "
        )
        if status != "CONSOLIDATED":
            summary += (
                "O gate de consolidação exige Coverage Overall de pelo menos 80% e Confidence mínima MEDIUM. "
                "O Overall herda a menor Confidence entre as dimensões aplicáveis; por isso uma nota relativamente alta pode permanecer parcial sem contradição."
            )
        else:
            summary += "Os gates mínimos de Coverage e Confidence foram atendidos para esta medição."
        summary += "</div>"
        blocker_html = (
            "<h4>Por que Confidence/Consolidação não chegaram ao ideal</h4>"
            + ("<div class='grid'>" + "".join(blocker_cards) + "</div>" if blocker_cards else "<p>Nenhuma dimensão bloqueante.</p>")
        )
        sections.append(f"<section class='sari-governance-device'>{summary}{blocker_html}{deductions_html}</section>")

    if not sections:
        return ""
    return (
        "<section id='sari-governance' class='panel'><div class='kicker'>Governança da medição</div>"
        "<h2>Por que o SARI chegou a este resultado e como melhorar</h2>"
        "<p class='intro'>O RASAi separa três perguntas: <strong>qualidade medida</strong> (Score), <strong>quanto do universo aplicável foi realmente avaliado</strong> (Coverage) e <strong>força da medição</strong> (Confidence). Consolidation aplica gates sobre Coverage/Confidence. Essa separação evita transformar ausência de evidência em falsa qualidade ou falsa falha.</p>"
        + "".join(sections)
        + _sari_parameterization_note(data)
        + "</section>"
    )


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


def _json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str) or not value.strip():
        return {}
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _state_pt(value: Any) -> str:
    raw = str(value or "UNAVAILABLE").upper()
    return {
        "OBTAINED": "OBTIDO",
        "ABSENT": "AUSENTE",
        "INVALID": "INVÁLIDO",
        "HTTP_ERROR": "ERRO HTTP",
        "NETWORK_ERROR": "ERRO DE REDE",
        "UNAVAILABLE": "INDISPONÍVEL",
        "NOT_REQUESTED": "NÃO SOLICITADO",
        "SKIPPED_SOURCE_BLOCKER": "NÃO CONSULTADO - BLOQUEIO DE FONTE",
    }.get(raw, raw)


def _rule_results(executions: list[sqlite3.Row], rule_id: str) -> str:
    values = sorted({str(_row_get(row, "result", "NÃO EXECUTADO")) for row in executions if str(_row_get(row, "rule_id", "")) == rule_id})
    return ", ".join(values) if values else "NÃO EXECUTADO"


def _group_trace(contributions: list[sqlite3.Row], group: str) -> str:
    rows = [row for row in contributions if str(_row_get(row, "scoring_group", "") or "") == group]
    if not rows:
        return "<p class='intro'>Nenhuma contribuição representativa persistida para este grupo.</p>"
    items: list[str] = []
    for row in sorted(rows, key=lambda item: (str(_row_get(item, "device", "")), str(_row_get(item, "rule_id", "")))):
        factor_raw = _row_get(row, "result_factor")
        effective_raw = _row_get(row, "effective_contribution")
        weight = float(_row_get(row, "weight", 0.0) or 0.0)
        factor = "-" if factor_raw is None else f"{float(factor_raw):.2f}"
        effective = "-" if effective_raw is None else f"{float(effective_raw):.3f}"
        items.append(
            "<li>"
            f"<strong>{escape(str(_row_get(row, 'device', '-')).title())}</strong>: "
            f"representante <code>{escape(str(_row_get(row, 'rule_id', '-')))}</code> = {escape(str(_row_get(row, 'result', '-')))}; "
            f"peso {weight:g} × fator {factor} = contribuição {effective}."
            "</li>"
        )
    return "<ul class='compact-list'>" + "".join(items) + "</ul>"


def _sitemap_state(executions: list[sqlite3.Row]) -> str:
    states: list[str] = []
    for row in executions:
        if str(_row_get(row, "rule_id", "")) != "BR-GEO-003":
            continue
        observed = _json_object(_row_get(row, "observed_value", ""))
        for item in observed.get("sitemaps", []):
            if isinstance(item, dict) and item.get("state"):
                states.append(_state_pt(item.get("state")))
    return ", ".join(dict.fromkeys(states)) if states else "NÃO OBSERVADO"


def _robots_state(executions: list[sqlite3.Row]) -> str:
    for row in executions:
        if str(_row_get(row, "rule_id", "")) == "BR-GEO-017":
            observed = _json_object(_row_get(row, "observed_value", ""))
            return _state_pt(observed.get("state"))
    return "NÃO OBSERVADO"


def _crawler_state(executions: list[sqlite3.Row], robots_state: str) -> str:
    rows = [row for row in executions if str(_row_get(row, "rule_id", "")) == "BR-GEO-018"]
    if not rows:
        return "NÃO OBSERVADO"
    unresolved = 0
    blocked = 0
    for row in rows:
        observed = _json_object(_row_get(row, "observed_value", ""))
        unresolved += len(observed.get("unresolved", []) if isinstance(observed.get("unresolved"), list) else [])
        blocked += len(observed.get("blocked_search_crawlers", []) if isinstance(observed.get("blocked_search_crawlers"), list) else [])
    if unresolved:
        return f"NÃO RESOLVIDO ({unresolved} combinação(ões))"
    if blocked:
        return f"BLOQUEIO SEARCH DETECTADO ({blocked})"
    if robots_state == "AUSENTE":
        return "RESOLVIDO POR DEFAULT ALLOW (robots.txt ausente)"
    return "RESOLVIDO - SEM BLOQUEIO SEARCH"


def _discovery_scoring_block(data: dict[str, Any]) -> str:
    executions = data.get("discovery_executions", [])
    contributions = data.get("contributions", [])
    sitemap_state = _sitemap_state(executions)
    robots_state = _robots_state(executions)
    crawler_state = _crawler_state(executions, robots_state)
    llms_state = _state_pt(_row_get(data.get("m24_run"), "llms_state", "UNAVAILABLE"))
    sitemap_result = _rule_results(executions, "BR-GEO-003")
    robots_result = _rule_results(executions, "BR-GEO-017")
    crawler_result = _rule_results(executions, "BR-GEO-018")
    ai_sitemap = _rule_results(executions, "BR-GEO-055")
    ai_robots = _rule_results(executions, "BR-GEO-056")
    return (
        "<section class='panel' id='discovery-scoring-inputs'><div class='kicker'>SARI - inputs técnicos de descoberta</div>"
        "<h2>O que foi realmente encontrado e como entrou no SARI</h2>"
        "<p class='intro'>O estado observado é mostrado separadamente do resultado da regra. <strong>AUSENTE não significa encontrado</strong>: sitemap e robots ausentes recebem WARNING com fatores reduzidos. Acesso de crawler pode ser resolvido como default allow quando robots.txt não existe; BR-GEO-017/018/056 compartilham o grupo ROBOTS, portanto o resultado mais restritivo representa o grupo sem bônus duplicado.</p>"
        "<div class='grid'>"
        "<article class='ref-card'><h3>Sitemap</h3>"
        f"<p><strong>Estado observado:</strong> {escape(sitemap_state)}</p>"
        f"<p><strong>Regra base:</strong> <code>BR-GEO-003</code> = {escape(sitemap_result)}</p>"
        f"<p><strong>IA técnica bounded:</strong> <code>BR-GEO-055</code> = {escape(ai_sitemap)}</p>"
        "<p><strong>Grupo:</strong> <code>SITEMAP</code> · peso máximo versionado 0,25.</p>"
        + _group_trace(contributions, "SITEMAP")
        + "</article>"
        "<article class='ref-card'><h3>robots.txt e acesso de crawlers</h3>"
        f"<p><strong>robots.txt observado:</strong> {escape(robots_state)}</p>"
        f"<p><strong>BR-GEO-017:</strong> {escape(robots_result)}</p>"
        f"<p><strong>Acesso efetivo:</strong> {escape(crawler_state)} · <code>BR-GEO-018</code> = {escape(crawler_result)}</p>"
        f"<p><strong>IA técnica bounded:</strong> <code>BR-GEO-056</code> = {escape(ai_robots)}</p>"
        "<p><strong>Grupo:</strong> <code>ROBOTS</code> · peso máximo versionado 0,60.</p>"
        + _group_trace(contributions, "ROBOTS")
        + "</article></div>"
        "<div class='notice'><strong>llms.txt:</strong> estado observado nesta camada: "
        + escape(llms_state)
        + ". O arquivo é tratado como proposta comunitária experimental e pode enriquecer o diagnóstico de descoberta, mas <strong>peso SARI = 0</strong>. Presença, ausência ou erro de llms.txt não aumenta nem reduz o SCORE-GEO-004.</div>"
        "<p><a href='crawling-discovery.html'>Abrir diagnóstico aprofundado de rastreamento e descoberta →</a></p></section>"
    )


def _structured_data_state(executions: list[sqlite3.Row]) -> tuple[str, int, int, tuple[str, ...]]:
    rows = [row for row in executions if str(_row_get(row, "rule_id", "")) == "BR-GEO-034"]
    if not rows:
        return "NÃO OBSERVADO", 0, 0, ()
    present = 0
    blocks = 0
    invalid = 0
    types: list[str] = []
    for row in rows:
        observed = _json_object(_row_get(row, "observed_value", ""))
        if bool(observed.get("present")):
            present += 1
        blocks += int(observed.get("blocks") or 0)
        invalid += int(observed.get("invalid_blocks") or 0)
        for item in observed.get("types", []) if isinstance(observed.get("types"), list) else []:
            if isinstance(item, str):
                types.append(item)
    if invalid:
        state = "PRESENTE COM BLOCO(S) INVÁLIDO(S)"
    elif present:
        state = "PRESENTE E SINTATICAMENTE INTERPRETÁVEL"
    else:
        state = "AUSENTE NO HTML ANALISADO"
    return state, blocks, invalid, tuple(dict.fromkeys(types))


def _structured_score_summary(scores: list[sqlite3.Row]) -> str:
    rows = [row for row in scores if str(_row_get(row, "dimension", "")) == "STRUCTURED_DATA"]
    if not rows:
        return "Não persistido"
    parts: list[str] = []
    for row in rows:
        device = str(_row_get(row, "device", "-")).title()
        value = _row_get(row, "value")
        rendered = "N/A" if value is None else f"{float(value):.1f}/100"
        parts.append(f"{device}: {rendered}")
    return " · ".join(parts)


def _structured_data_scoring_block(data: dict[str, Any]) -> str:
    executions = data.get("rule_executions", [])
    contributions = data.get("contributions", [])
    state, blocks, invalid, types = _structured_data_state(executions)
    type_text = ", ".join(types) if types else "nenhum @type observado"
    rule_results = {rule_id: _rule_results(executions, rule_id) for rule_id in ("BR-GEO-034", "BR-GEO-035", "BR-GEO-036", "BR-GEO-037")}
    absence_note = (
        "Na ausência de JSON-LD, BR-GEO-034 permanece aplicável como WARNING com fator 0,80; BR-GEO-035..037 ficam NOT_APPLICABLE. Assim a ausência é uma lacuna leve e rastreável, não zero e não N/A para toda a dimensão."
        if state == "AUSENTE NO HTML ANALISADO"
        else "Quando JSON-LD existe, sintaxe/tipos e consistência com conteúdo/entidades são avaliados pelos grupos versionados do Structured Data."
    )
    return (
        "<section class='panel' id='structured-data-scoring-inputs'><div class='kicker'>SARI - dados estruturados</div>"
        "<h2>JSON-LD no cálculo do SCORE-GEO-004</h2>"
        "<p class='intro'>O RASAi procura blocos <code>script[type=&quot;application/ld+json&quot;]</code> no HTML preservado. A tabela de dimensões mostra o score agregado; este bloco expõe a origem da contribuição para que seja possível verificar se JSON-LD entrou ou não na aritmética.</p>"
        f"<div class='metric-grid'>{_metric('Estado JSON-LD', state)}{_metric('Blocos observados', blocks)}{_metric('Blocos inválidos', invalid)}{_metric('Tipos', type_text)}{_metric('Structured Data', _structured_score_summary(data.get('scores', [])))}</div>"
        "<div class='grid'>"
        "<article class='ref-card'><h3>Presença, sintaxe e tipos</h3>"
        f"<p><code>BR-GEO-034</code> = {escape(rule_results['BR-GEO-034'])} · <code>BR-GEO-035</code> = {escape(rule_results['BR-GEO-035'])}</p>"
        "<p><strong>Grupo:</strong> <code>STRUCTURED_DATA_SYNTAX</code>.</p>"
        + _group_trace(contributions, "STRUCTURED_DATA_SYNTAX")
        + "</article>"
        "<article class='ref-card'><h3>Consistência semântica</h3>"
        f"<p><code>BR-GEO-036</code> = {escape(rule_results['BR-GEO-036'])} · <code>BR-GEO-037</code> = {escape(rule_results['BR-GEO-037'])}</p>"
        "<p><strong>Grupo:</strong> <code>STRUCTURED_DATA_CONSISTENCY</code>. Quando aplicável, a análise pode usar evidência semântica/IA evidence-bound; o modelo não escolhe pesos.</p>"
        + _group_trace(contributions, "STRUCTURED_DATA_CONSISTENCY")
        + "</article></div>"
        f"<div class='notice'>{escape(absence_note)}</div>"
        "<p><a href='structured-data.html'>Abrir evidências detalhadas de conteúdo e JSON-LD →</a></p></section>"
    )


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
    html = re.sub(r"<section id=['\"]web-performance-summary['\"].*?</section>", "", html, flags=re.DOTALL)
    html = re.sub(r"<section id=['\"]accessibility-summary['\"].*?</section>", "", html, flags=re.DOTALL)
    html = re.sub(r"<!-- rasai-apdex-index-start -->.*?<!-- rasai-apdex-index-end -->", "", html, flags=re.DOTALL)
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
    sari_cards: list[str] = []
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
        condition, condition_label = _sari_condition(row)
        sari_cards.append(_indicator_card(
            f"Search & AI Readiness - {label}", value, detail, RASAI_FILE,
            "RASAi - SARI-001", condition, condition_label, primary=True,
        ))

    web = data["web"]
    cwv_values = [str(row["cwv_assessment"]) for row in web if str(row["cwv_assessment"]) in {"PASS", "FAIL"}]
    if cwv_values:
        passed = sum(value == "PASS" for value in cwv_values)
        total = len(cwv_values)
        cwv_value = f"{passed}/{total} aprovados"
        cwv_detail = "Aprovação exige LCP, INP e CLS p75 dentro dos limites Core Web Vitals no contexto."
        cwv_condition, cwv_label = _cwv_condition(passed, total)
    else:
        cwv_value, cwv_detail = "NÃO DISPONÍVEL", _external_status(data["web_run"])
        cwv_condition, cwv_label = "neutral", "Sem dados suficientes"
    cards.append(_indicator_card(
        "Core Web Vitals", cwv_value, cwv_detail, "web-performance.html", "Chrome / web.dev",
        cwv_condition, cwv_label,
    ))

    perf = _device_ranges(web, "performance_score", scale=1.0, suffix="/100")
    perf_condition, perf_label = _lighthouse_condition(web, "performance_score")
    cards.append(_indicator_card(
        "Lighthouse Performance", perf[0], perf[1], "web-performance.html", "Chrome Lighthouse",
        perf_condition, perf_label,
    ))
    a11y = _device_ranges(web, "accessibility_score", scale=1.0, suffix="/100")
    a11y_condition, a11y_label = _lighthouse_condition(web, "accessibility_score")
    cards.append(_indicator_card(
        "Lighthouse Accessibility", a11y[0], a11y[1], "accessibility.html", "Chrome Lighthouse + WCAG 2.2",
        a11y_condition, a11y_label,
    ))

    apdex_run = data["apdex_run"]
    all_apdex_rows = [row for row in data["apdex"] if row["apdex_score"] is not None]
    final_rows = [row for row in all_apdex_rows if _truthy(row, "final_group")]
    apdex_rows = final_rows or all_apdex_rows
    small_group_only = bool(apdex_rows) and not bool(final_rows)
    if apdex_rows:
        apdex_value, apdex_detail = _device_ranges(apdex_rows, "apdex_score", scale=1.0, suffix="", digits=3)
        if small_group_only:
            apdex_detail += "; grupo pequeno (<100 válidas/contexto), leitura diagnóstica"
        apdex_condition, apdex_label = _apdex_condition(apdex_rows, small_group_only=small_group_only)
    elif apdex_run is not None and not bool(apdex_run["enabled"]):
        apdex_value, apdex_detail = "DESABILITADO", "Medição opcional não executada"
        apdex_condition, apdex_label = "neutral", "Não executado"
    else:
        apdex_value, apdex_detail = "NÃO DISPONÍVEL", "Sem grupo Apdex materializado"
        apdex_condition, apdex_label = "neutral", "Sem dados suficientes"
    apdex_link = "apdex.html" if (report_dir / "apdex.html").is_file() else "web-performance.html"
    cards.append(_indicator_card(
        "Synthetic Navigation Apdex", apdex_value, apdex_detail, apdex_link,
        "Apdex Technical Specification", apdex_condition, apdex_label,
    ))

    return (
        _DASHBOARD_START
        + "<section id='executive-indicator-dashboard' class='panel'><div class='kicker'>Dashboard executivo</div><h2>Resultados finais por indicador</h2><p class='intro'>O painel resume resultados sem misturar metodologias. A condição visual é calculada separadamente para cada indicador; no Lighthouse, a subdivisão de valores Poor abaixo de 25 como crítico é somente severidade visual do RASAi e não uma quarta faixa oficial do Lighthouse. Nenhum Lighthouse, Core Web Vitals, Accessibility ou Apdex é convertido no SARI-001.</p>"
        + "<div class='indicator-tier-label'>Índice proprietário de readiness</div>"
        + f"<div class='indicator-primary-grid'>{''.join(sari_cards) if sari_cards else "<div class='notice warn'>SARI-001 não disponível.</div>"}</div>"
        + _sari_dashboard_explanation(data)
        + "<div class='indicator-tier-label indicator-tier-supporting'>Indicadores complementares - independentes do SARI-001</div>"
        + f"<div class='grid indicator-grid indicator-supporting-grid'>{''.join(cards)}</div></section>"
        + _DASHBOARD_END
    )


def _indicator_card(
    title: str,
    value: str,
    detail: str,
    href: str,
    source: str,
    condition: str = "neutral",
    condition_label: str = "Informativo",
    primary: bool = False,
) -> str:
    value_markup = _indicator_value_markup(value)
    return (
        f"<article class='ref-card indicator-card {'indicator-primary' if primary else 'indicator-supporting'} condition-{escape(condition, quote=True)}'>"
        f"<div class='kicker'>{escape(source)}</div><h3>{escape(title)}</h3>"
        f"{value_markup}<span class='indicator-condition'>{escape(condition_label)}</span>"
        f"<p class='intro'>{escape(detail)}</p><p><a href='{escape(href, quote=True)}'>Analisar detalhes</a></p></article>"
    )


def _indicator_value_markup(value: str) -> str:
    parts = [item.strip() for item in value.split(" - ") if item.strip()]
    rendered: list[str] = []
    for part in parts:
        match = re.fullmatch(r"(Mobile|Desktop|Global)\s+(.+)", part)
        if match is None:
            rendered = []
            break
        rendered.append(
            "<span class='indicator-device'>"
            f"<small>{escape(match.group(1))}</small><strong>{escape(match.group(2))}</strong></span>"
        )
    if rendered:
        return "<div class='indicator-values'>" + "".join(rendered) + "</div>"
    return f"<div class='score-number indicator-score'>{escape(value)}</div>"


def _sari_condition(row: sqlite3.Row) -> tuple[str, str]:
    value = float(row["value"]) if row["value"] is not None else None
    consolidation = str(row["consolidation_status"] or "")
    confidence = str(row["confidence"] or "")
    if value is None or consolidation == "NOT_CONSOLIDATED" or confidence == "UNAVAILABLE":
        return "critical", "Crítico - não consolidado"
    if value < 40:
        return "critical", "Crítico"
    if value < 75:
        return "below", "Abaixo do esperado"
    if consolidation != "CONSOLIDATED" or confidence == "LOW":
        return "near", "Quase no esperado - medição parcial"
    return "expected", "Dentro do esperado"


def _cwv_condition(passed: int, total: int) -> tuple[str, str]:
    if total <= 0:
        return "neutral", "Sem dados suficientes"
    if passed == total:
        return "expected", "Dentro do esperado"
    if passed == 0:
        return "critical", "Crítico - nenhum contexto aprovado"
    ratio = passed / total
    return ("near", "Quase no esperado") if ratio >= 0.75 else ("below", "Abaixo do esperado")


def _numeric_values(rows: list[sqlite3.Row], column: str) -> list[float]:
    output: list[float] = []
    for row in rows:
        try:
            value = row[column]
        except (IndexError, KeyError):
            continue
        if value is not None:
            output.append(float(value))
    return output


def _lighthouse_condition(rows: list[sqlite3.Row], column: str) -> tuple[str, str]:
    values = _numeric_values(rows, column)
    if not values:
        return "neutral", "Sem dados suficientes"
    worst = min(values)
    if worst >= 90:
        return "expected", "Dentro do esperado - Good"
    if worst >= 50:
        return "near", "Quase no esperado - Needs Improvement"
    if worst >= 25:
        return "below", "Abaixo do esperado - Poor"
    return "critical", "Crítico - Poor (severidade visual RASAi)"


def _apdex_condition(rows: list[sqlite3.Row], *, small_group_only: bool) -> tuple[str, str]:
    values = _numeric_values(rows, "apdex_score")
    if not values:
        return "neutral", "Sem dados suficientes"
    worst = min(values)
    if worst >= 0.85:
        condition = ("expected", "Dentro do esperado - Good/Excellent")
    elif worst >= 0.70:
        condition = ("near", "Quase no esperado - Fair")
    elif worst >= 0.50:
        condition = ("below", "Abaixo do esperado - Poor")
    else:
        condition = ("critical", "Crítico - Unacceptable")
    if small_group_only and condition[0] == "expected":
        return "near", "Quase no esperado - grupo pequeno"
    return condition


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
