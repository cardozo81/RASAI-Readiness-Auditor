"""Final user-facing reconciliation for audit report semantics.

This pass is presentation-only: it reads persisted audit evidence and adjusts
the final HTML projection. It never performs network calls and never changes
RuleExecutions, scores, weights, or immutable audit evidence.
"""
from __future__ import annotations

from html import escape
import json
from pathlib import Path
import re
import sqlite3
from typing import Any

from rasai.persistence import AuditWorkspace
from rasai.score_geo_004 import DIMENSION_WEIGHTS, OVERALL_AGGREGATION_VERSION, SCORING_VERSION

_DIMENSION_LABELS = {
    "DISCOVERY_ACCESS": "Acesso e descoberta",
    "INDEXABILITY": "Capacidade de indexação",
    "CONTENT_EXTRACTABILITY": "Extração de conteúdo",
    "SEMANTIC_STRUCTURE": "Estrutura semântica",
    "ENTITY_CLARITY": "Clareza de entidades",
    "STRUCTURED_DATA": "Dados estruturados",
    "ANSWERABILITY": "Capacidade de resposta",
    "CITATION_READINESS": "Preparação para citação",
    "EVIDENCE_TRUST": "Evidências e confiabilidade",
    "INTENT_COVERAGE": "Cobertura de intenções",
    "CONTENT_VALUE": "Valor do conteúdo",
}
_LIGHTHOUSE_LABELS = (
    "Performance · Lighthouse",
    "Accessibility · Lighthouse",
    "Best Practices · Lighthouse",
    "SEO técnico · Lighthouse",
)
_SCORE_STYLE = """
<style id='rasai-lighthouse-score-bands'>
.metric.lighthouse-score-good{background:var(--soft-green,#edf6f0);border-left:4px solid var(--green,#5f9674)}
.metric.lighthouse-score-warn{background:var(--soft-amber,#fff6df);border-left:4px solid var(--amber,#c78b2a)}
.metric.lighthouse-score-bad{background:var(--soft-red,#fff0ef);border-left:4px solid var(--red,#c5574f)}
.metric.lighthouse-score-unavailable{opacity:.82}
</style>
"""


def reconcile_validated_report_details(*, audit_id: str, workspace: AuditWorkspace) -> None:
    report_dir = workspace.root / "report"
    if not report_dir.is_dir():
        return
    connection = sqlite3.connect(workspace.database)
    connection.row_factory = sqlite3.Row
    try:
        _rewrite_navigation(report_dir)
        _rewrite_web_performance(report_dir / "web-performance.html", connection, audit_id)
        _rewrite_readiness(report_dir / "readiness.html", connection, audit_id)
        _rewrite_ai_usage(report_dir / "ai-usage.html", connection, audit_id)
    finally:
        connection.close()


def _read(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8") if path.is_file() else None
    except (OSError, UnicodeError):
        return None


def _write(path: Path, html: str) -> None:
    path.write_text(html, encoding="utf-8", newline="\n")


def _rewrite_navigation(report_dir: Path) -> None:
    for path in report_dir.glob("*.html"):
        html = _read(path)
        if html is None:
            continue
        updated = html.replace(">Apdex de navegação<", ">Apdex sintético de navegação<")
        if updated != html:
            _write(path, updated)


def _run_categories(connection: sqlite3.Connection, audit_id: str) -> set[str]:
    try:
        row = connection.execute(
            "SELECT categories FROM web_performance_runs WHERE audit_id=?",
            (audit_id,),
        ).fetchone()
    except sqlite3.OperationalError:
        return set()
    if row is None or not row["categories"]:
        return set()
    try:
        value = json.loads(str(row["categories"]))
    except (TypeError, ValueError, json.JSONDecodeError):
        return set()
    return {str(item).casefold() for item in value} if isinstance(value, list) else set()


def _lighthouse_class(score: float) -> str:
    if score >= 90:
        return "lighthouse-score-good"
    if score >= 50:
        return "lighthouse-score-warn"
    return "lighthouse-score-bad"


def _color_lighthouse_metrics(html: str) -> str:
    label_pattern = "|".join(re.escape(item) for item in _LIGHTHOUSE_LABELS)
    pattern = re.compile(
        rf"<div class='metric'><small>({label_pattern})</small><strong>([0-9]+(?:\.[0-9]+)?)/100</strong></div>"
    )

    def replace(match: re.Match[str]) -> str:
        score = float(match.group(2))
        return (
            f"<div class='metric {_lighthouse_class(score)}'>"
            f"<small>{match.group(1)}</small><strong>{match.group(2)}/100</strong></div>"
        )

    return pattern.sub(replace, html)


def _rewrite_web_performance(path: Path, connection: sqlite3.Connection, audit_id: str) -> None:
    html = _read(path)
    if html is None:
        return
    if "rasai-lighthouse-score-bands" not in html:
        html = html.replace("</head>", _SCORE_STYLE + "</head>", 1)
    html = _color_lighthouse_metrics(html)

    categories = _run_categories(connection, audit_id)
    agentic_requested = "agentic-browsing" in categories
    agentic_value = "Não retornado pelo provider" if agentic_requested else "Não disponível via PageSpeed API"
    html = re.sub(
        r"<div class='metric'><small>Agentic Browsing · Lighthouse experimental</small><strong>.*?</strong></div>",
        (
            "<div class='metric lighthouse-score-unavailable'>"
            "<small>Agentic Browsing · Lighthouse experimental</small>"
            f"<strong>{escape(agentic_value)}</strong></div>"
        ),
        html,
        count=1,
        flags=re.DOTALL,
    )
    html = html.replace(
        "Performance, Accessibility, Best Practices e SEO técnico são categorias consolidadas do Google Chrome Lighthouse; Agentic Browsing é uma categoria experimental do Lighthouse.",
        "Performance, Accessibility, Best Practices e SEO técnico são categorias Lighthouse transportadas pela API pública PageSpeed Insights. Agentic Browsing é experimental no Lighthouse/DevTools e não é uma categoria solicitável pela API pública PageSpeed v5 usada nesta coleta.",
    )
    html = html.replace(
        "Agentic Browsing deve ser lido como experimental e version-dependent.",
        "Agentic Browsing deve ser lido como experimental e requer uma execução Lighthouse direta separada da API pública PageSpeed.",
    )
    html = html.replace(
        "<td><code>lighthouseResult.categories.agentic-browsing.score</code></td>",
        "<td>Não transportado pela API pública PageSpeed v5</td>",
    )
    html = html.replace(
        "Indicador complementar e experimental; não é tratado como score proprietário nem entra automaticamente no SARI-001/",
        "Indicador complementar e experimental; para coleta futura requer adapter Lighthouse direto. Não é tratado como score proprietário nem entra automaticamente no SARI-001/",
    )
    _write(path, html)


def _latest_scores(connection: sqlite3.Connection, audit_id: str) -> dict[str, dict[str, sqlite3.Row]]:
    try:
        rows = connection.execute(
            """SELECT * FROM scores
               WHERE audit_id=? AND scoring_version=? AND dimension<> 'OVERALL_READINESS'
               ORDER BY calculated_at""",
            (audit_id, SCORING_VERSION),
        ).fetchall()
    except sqlite3.OperationalError:
        return {}
    latest: dict[str, dict[str, sqlite3.Row]] = {}
    for row in rows:
        latest.setdefault(str(row["device"]), {})[str(row["dimension"])] = row
    return latest


def _effective_sari_results(connection: sqlite3.Connection, audit_id: str) -> str:
    latest = _latest_scores(connection, audit_id)
    if not latest:
        return ""
    blocks: list[str] = []
    for device, by_dimension in sorted(latest.items()):
        denominator = sum(
            DIMENSION_WEIGHTS.get(dimension, 0.0)
            for dimension, row in by_dimension.items()
            if row["value"] is not None
            and str(row["consolidation_status"] or "") != "NOT_APPLICABLE"
        )
        rows: list[str] = []
        overall_from_rows = 0.0
        for dimension, base_weight in DIMENSION_WEIGHTS.items():
            row = by_dimension.get(dimension)
            value = None if row is None else row["value"]
            applicable = (
                row is not None
                and value is not None
                and str(row["consolidation_status"] or "") != "NOT_APPLICABLE"
            )
            effective_weight = base_weight / denominator if applicable and denominator > 0 else 0.0
            contribution = float(value) * effective_weight if applicable else None
            if contribution is not None:
                overall_from_rows += contribution
            score_text = "-" if value is None else f"{float(value):.1f}"
            effective_text = f"{effective_weight * 100:.2f}%" if applicable else "Excluído"
            contribution_text = "-" if contribution is None else f"{contribution:.2f} pts"
            status = "Não aplicável" if not applicable else str(row["consolidation_status"] or "-")
            rows.append(
                "<tr>"
                f"<td>{escape(_DIMENSION_LABELS.get(dimension, dimension))}</td>"
                f"<td>{base_weight * 100:.0f}%</td>"
                f"<td><strong>{escape(effective_text)}</strong></td>"
                f"<td>{escape(score_text)}</td>"
                f"<td>{escape(contribution_text)}</td>"
                f"<td>{escape(status)}</td>"
                "</tr>"
            )
        blocks.append(
            f"<h3>Resultado efetivo desta auditoria · {escape(device.title())}</h3>"
            "<p class='intro'>A tabela acima do contrato é a matriz fixa. A tabela abaixo mostra como essa matriz foi aplicada ao resultado efetivamente medido. Dimensões legitimamente não aplicáveis saem do denominador e os pesos restantes são normalizados.</p>"
            "<div class='table-wrap'><table><thead><tr>"
            "<th>Dimensão</th><th>Peso da matriz</th><th>Peso efetivo</th><th>Score</th><th>Contribuição ao Overall</th><th>Estado</th>"
            "</tr></thead><tbody>"
            + "".join(rows)
            + "</tbody></table></div>"
            f"<p class='intro'><strong>Overall reproduzido pela ponderação efetiva:</strong> {overall_from_rows:.2f}/100.</p>"
        )
    return "<div class='sari-effective-results'>" + "".join(blocks) + "</div>"


def _auto_context_notice(connection: sqlite3.Connection, audit_id: str) -> str:
    try:
        row = connection.execute(
            """SELECT risk_profile,ymyl_category,page_purpose,intended_audience,
                      experience_requirement,freshness_sensitivity,content_origin
               FROM content_analysis_contexts WHERE audit_id=? LIMIT 1""",
            (audit_id,),
        ).fetchone()
    except sqlite3.OperationalError:
        return ""
    if row is None:
        return ""
    automatic = [
        label
        for key, label in (
            ("risk_profile", "Risk profile"),
            ("ymyl_category", "YMYL"),
            ("page_purpose", "Page purpose"),
            ("intended_audience", "Audience"),
            ("experience_requirement", "Experience requirement / E-E-A-T"),
            ("freshness_sensitivity", "Freshness sensitivity"),
            ("content_origin", "Content origin"),
        )
        if str(row[key] or "").casefold() == "auto"
    ]
    if not automatic:
        return ""
    return (
        "<div class='notice auto-editorial-context' data-auto-editorial-context='true'>"
        "<strong>Campos em modo automático:</strong> "
        + escape(", ".join(automatic))
        + ". Nesta versão, <code>audit.db</code> preserva que a configuração foi <code>auto</code>, "
        "mas não persiste uma classificação editorial resolvida pela IA para esses atributos. "
        "Por isso o relatório não inventa uma interpretação YMYL/E-E-A-T. Para exibir “o que a IA entendeu”, "
        "o contrato de IA deve persistir separadamente configuração, classificação resolvida, confiança e evidências."
        "</div>"
    )


def _rewrite_readiness(path: Path, connection: sqlite3.Connection, audit_id: str) -> None:
    html = _read(path)
    if html is None:
        return
    html = html.replace(
        "<h2>HIERARCHICAL_WEIGHTED_READINESS_V1</h2>",
        "<h2>Agregação hierárquica ponderada</h2>"
        f"<p class='intro'>Contrato técnico: <code>{escape(OVERALL_AGGREGATION_VERSION)}</code>.</p>",
    )
    html = html.replace(
        "<strong>Grupo:</strong> <code>STRUCTURED_DATA_SYNTAX</code>",
        "<strong>Grupo:</strong> <strong>Sintaxe de dados estruturados</strong> <code>STRUCTURED_DATA_SYNTAX</code>",
    )
    html = html.replace(
        "<strong>Grupo:</strong> <code>STRUCTURED_DATA_CONSISTENCY</code>",
        "<strong>Grupo:</strong> <strong>Consistência de dados estruturados</strong> <code>STRUCTURED_DATA_CONSISTENCY</code>",
    )

    corrected = (
        "<strong>Dados estruturados no SCORE-GEO-004:</strong> a ausência explícita de JSON-LD é preservada como observação, "
        "mas BR-GEO-034 é reinterpretada como <strong>Não aplicável para scoring</strong> porque Structured Data não é requisito universal. "
        "Quando toda a dimensão fica Não aplicável, seus 5% saem do denominador e os pesos das dimensões aplicáveis são normalizados. "
        "JSON-LD presente, inválido ou inconsistente continua sendo avaliado quando aplicável."
    )
    html = re.sub(
        r"<div class='notice structured-data-absence-note'>.*?</div>",
        f"<div class='notice structured-data-absence-note'>{corrected}</div>",
        html,
        count=1,
        flags=re.DOTALL,
    )
    structured = re.search(
        r"<section\b[^>]*id='structured-data-scoring-inputs'[^>]*>.*?</section>",
        html,
        flags=re.DOTALL,
    )
    if structured is not None:
        section = structured.group(0)
        section = re.sub(
            r"<div class='notice'>Na ausência de JSON-LD,.*?</div>",
            f"<div class='notice'>{corrected}</div>",
            section,
            count=1,
            flags=re.DOTALL,
        )
        html = html[: structured.start()] + section + html[structured.end() :]

    result = _effective_sari_results(connection, audit_id)
    if result and "sari-effective-results" not in html:
        marker = "<div class='notice'><strong>Precedência de evidência:</strong>"
        if marker in html:
            html = html.replace(marker, result + marker, 1)
        else:
            html = html.replace("</main>", result + "</main>", 1)

    notice = _auto_context_notice(connection, audit_id)
    if notice and "data-auto-editorial-context='true'" not in html:
        anchor = "<p><a href='content-suggestions.html'>"
        if anchor in html:
            html = html.replace(anchor, notice + anchor, 1)
        else:
            html = html.replace("</main>", notice + "</main>", 1)
    _write(path, html)


def _rows(connection: sqlite3.Connection, sql: str, audit_id: str) -> list[sqlite3.Row]:
    try:
        return list(connection.execute(sql, (audit_id,)).fetchall())
    except sqlite3.OperationalError:
        return []


def _ai_totals(connection: sqlite3.Connection, audit_id: str) -> dict[str, Any]:
    primary = _rows(
        connection,
        "SELECT status,total_tokens,estimated_cost,cost_currency,semantic_contract_version FROM ai_provider_attempts WHERE audit_id=?",
        audit_id,
    )
    content = _rows(
        connection,
        "SELECT status,total_tokens,estimated_cost,cost_currency,contract_version FROM content_remediation_attempts WHERE audit_id=?",
        audit_id,
    )
    all_rows = [*primary, *content]
    costs: dict[str, float] = {}
    tokens = 0
    accepted = contract_rejected = technical = 0
    semantic_cost = technical_cost = content_cost = 0.0
    for row in primary:
        status = str(row["status"] or "").upper()
        version = str(row["semantic_contract_version"] or "")
        cost = float(row["estimated_cost"] or 0.0)
        if version.startswith("M18-"):
            semantic_cost += cost
        elif version.startswith("M24-"):
            technical_cost += cost
        if status == "SUCCESS":
            accepted += 1
        elif status == "CONTRACT_ERROR":
            contract_rejected += 1
        else:
            technical += 1
        if row["total_tokens"] is not None:
            tokens += int(row["total_tokens"])
        if row["estimated_cost"] is not None:
            currency = str(row["cost_currency"] or "USD")
            costs[currency] = costs.get(currency, 0.0) + cost
    for row in content:
        status = str(row["status"] or "").upper()
        cost = float(row["estimated_cost"] or 0.0)
        content_cost += cost
        if status == "SUCCESS":
            accepted += 1
        elif status == "CONTRACT_ERROR":
            contract_rejected += 1
        else:
            technical += 1
        if row["total_tokens"] is not None:
            tokens += int(row["total_tokens"])
        if row["estimated_cost"] is not None:
            currency = str(row["cost_currency"] or "USD")
            costs[currency] = costs.get(currency, 0.0) + cost
    return {
        "attempts": len(all_rows),
        "accepted": accepted,
        "contract_rejected": contract_rejected,
        "technical": technical,
        "tokens": tokens,
        "costs": costs,
        "semantic_cost": semantic_cost,
        "technical_cost": technical_cost,
        "content_cost": content_cost,
    }


def _replace_metric(html: str, label: str, value: str, *, new_label: str | None = None) -> str:
    pattern = re.compile(
        rf"(<div class='metric'><small>){re.escape(label)}(</small><strong>).*?(</strong></div>)",
        flags=re.DOTALL,
    )
    shown_label = escape(new_label or label)
    shown_value = escape(value)
    return pattern.sub(
        lambda m: m.group(1) + shown_label + m.group(2) + shown_value + m.group(3),
        html,
        count=1,
    )


def _format_costs(costs: dict[str, float]) -> str:
    if not costs:
        return "Não mensurável"
    return " + ".join(f"{value:.8f} {currency}" for currency, value in sorted(costs.items()))


def _rewrite_ai_usage(path: Path, connection: sqlite3.Connection, audit_id: str) -> None:
    html = _read(path)
    if html is None:
        return
    totals = _ai_totals(connection, audit_id)
    html = _replace_metric(html, "Chamadas", str(totals["attempts"]), new_label="Tentativas externas de IA")
    html = _replace_metric(html, "Sucessos", str(totals["accepted"]), new_label="Respostas aceitas")
    html = _replace_metric(html, "Custo estimado total", _format_costs(totals["costs"]), new_label="Custo estimado de IA")
    html = html.replace("<small>Provider efetivo</small>", "<small>Provider efetivo · análise semântica</small>", 1)
    html = html.replace("<small>Status da sessão</small>", "<small>Status da análise semântica</small>", 1)

    extra = (
        "<div class='metric'><small>Respostas rejeitadas pelo contrato RASAi</small>"
        f"<strong>{totals['contract_rejected']}</strong></div>"
        "<div class='metric'><small>Erros técnicos de request/provider</small>"
        f"<strong>{totals['technical']}</strong></div>"
        "<div class='metric'><small>Tokens medidos</small>"
        f"<strong>{totals['tokens']}</strong></div>"
    )
    if "Tokens medidos" not in html:
        marker = re.search(
            r"<div class='metric'><small>Respostas aceitas</small><strong>.*?</strong></div>",
            html,
            flags=re.DOTALL,
        )
        if marker:
            html = html[: marker.end()] + extra + html[marker.end() :]

    total_cost_text = _format_costs(totals["costs"])
    breakdown = (
        f"Análise semântica {totals['semantic_cost']:.8f} USD + "
        f"IA técnica de crawling/discovery {totals['technical_cost']:.8f} USD + "
        f"Remediação de conteúdo {totals['content_cost']:.8f} USD"
    )
    banner = (
        "<section class='notice cost-total' data-api-cost-total='true'>"
        f"<strong>Custo estimado do consumo de IA nesta execução: {escape(total_cost_text)}</strong>"
        f"<span class='cost-breakdown'>{escape(breakdown)}. "
        "Estimativa baseada na telemetria persistida; não substitui billing/invoice. "
        "Tentativas sem usage retornado pelo provider permanecem sem custo inferido.</span></section>"
    )
    html = re.sub(
        r"<section class='notice cost-total' data-api-cost-total='true'>.*?</section>",
        banner,
        html,
        count=1,
        flags=re.DOTALL,
    )

    for row in _rows(
        connection,
        "SELECT estimated_cost,cost_currency FROM ai_provider_attempts WHERE audit_id=? AND estimated_cost IS NOT NULL",
        audit_id,
    ):
        value = f"{float(row['estimated_cost']):.8f}"
        currency = str(row["cost_currency"] or "USD")
        html = html.replace(f"<td>{value}</td>", f"<td>{value} {escape(currency)}</td>", 1)

    if "Reasoning tokens são subconjunto" not in html:
        note = (
            "<div class='notice'><strong>Leitura de tokens e custo:</strong> "
            "Input, cache, output e total são contagens de tokens reportadas pelo provider. "
            "Reasoning tokens são subconjunto de output quando o provider os reporta; não devem ser somados novamente ao total. "
            "Todo custo financeiro é exibido com a moeda persistida.</div>"
        )
        html = html.replace("<section id='public-report-contract'", note + "<section id='public-report-contract'", 1)

    try:
        m24 = connection.execute(
            "SELECT state,reason FROM m24_ai_results WHERE audit_id=?",
            (audit_id,),
        ).fetchone()
    except sqlite3.OperationalError:
        m24 = None
    if m24 is not None and "CONTRACT_ERROR" in str(m24["reason"] or ""):
        phrase = "IA técnica de crawling/discovery (opcional)"
        index = html.find(phrase)
        if index >= 0:
            start = html.rfind("<section", 0, index)
            end = html.find("</section>", index)
            if start >= 0 and end >= 0:
                end += len("</section>")
                section = html[start:end]
                section = re.sub(
                    r"(<small>Estado</small><strong>).*?(</strong>)",
                    r"\1Resposta recebida, rejeitada pelo contrato RASAi\2",
                    section,
                    count=1,
                    flags=re.DOTALL,
                )
                if "contract-rejection-explanation" not in section:
                    section = section.replace(
                        "</section>",
                        "<div class='notice contract-rejection-explanation'><strong>Classificação correta:</strong> "
                        "o provider respondeu e houve consumo mensurável; a resposta foi rejeitada pelas regras de contrato/evidências do RASAi. "
                        "Por isso a tentativa conta em tokens/custo, mas não deve ser descrita como indisponibilidade do provider.</div></section>",
                        1,
                    )
                html = html[:start] + section + html[end:]

    html = html.replace("RASAI_AI_TECHNICAL_REMEDIATION", "remediação técnica por IA")
    html = html.replace("RASAI_AI_CONTENT_REMEDIATION", "remediação de conteúdo por IA")
    _write(path, html)
