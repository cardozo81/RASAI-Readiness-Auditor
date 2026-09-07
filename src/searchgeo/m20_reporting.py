"""Projection of Sugestões e remediação de conteúdo por IA data into the static report site."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from html import escape
import json
from pathlib import Path
import sqlite3
from typing import Any

from searchgeo.content_context import configured_content_analysis_context
from searchgeo.content_context_persistence import (
    load_content_analysis_context,
    persist_content_analysis_context,
)
from searchgeo.persistence import AuditWorkspace
from searchgeo.report_navigation import normalize_report_navigation, render_report_navigation

CONTENT_FILE = "content-suggestions.html"
_GOOGLE_HELPFUL_CONTENT = "https://developers.google.com/search/docs/fundamentals/creating-helpful-content"
_GOOGLE_RATER_GUIDELINES = "https://services.google.com/fh/files/misc/hsw-sqrg.pdf"
_GOOGLE_STRUCTURED_DATA = "https://developers.google.com/search/docs/appearance/structured-data/sd-policies"
_SCHEMA_ORG = "https://schema.org/docs/documents.html"

_CONTEXT_LABELS = {
    "risk_profile": "Perfil de risco",
    "ymyl_category": "Categoria YMYL",
    "page_purpose": "Propósito da página",
    "intended_audience": "Público pretendido",
    "experience_requirement": "Experiência em primeira mão",
    "freshness_sensitivity": "Sensibilidade temporal",
    "content_origin": "Origem do conteúdo",
}
_CONTEXT_HINTS = {
    "risk_profile": "YMYL eleva a exigência de confiança e suporte factual; STANDARD mantém a régua editorial comum; AUTO é inferência provisória da IA.",
    "ymyl_category": "Contextualiza o tipo de impacto potencial: saúde/segurança, estabilidade financeira, bem-estar social ou outra consequência relevante.",
    "page_purpose": "Ajuda a IA a avaliar completude e utilidade conforme a finalidade real da página, sem aplicar o mesmo padrão a todos os formatos.",
    "intended_audience": "Diferencia conteúdo para público geral, profissional ou misto; não autoriza inferir credenciais ou requisitos legais.",
    "experience_requirement": "Distingue situações em que experiência em primeira mão é necessária, útil ou não esperada; não substitui expertise quando ela é material.",
    "freshness_sensitivity": "Quando alta, aumenta a exigência sobre datas, qualificadores temporais e coerência de atualização; nunca autoriza fabricar uma data nova.",
    "content_origin": "Distingue conteúdo próprio, terceiro, UGC ou misto para avaliar autoria, responsabilidade e atribuição com maior precisão.",
}


def enrich_m20_report_site(*, audit_id: str, workspace: AuditWorkspace) -> Path:
    """Write the Sugestões e remediação de conteúdo por IA page and connect it to the already materialized report site."""
    report_dir = workspace.root / "report"
    report_dir.mkdir(parents=True, exist_ok=True)

    # Resolve once per audit process and persist before rendering. The report
    # must remain reproducible after environment variables change or disappear.
    context = configured_content_analysis_context()
    persist_content_analysis_context(
        workspace=workspace,
        audit_id=audit_id,
        context=context,
        created_at=datetime.now(timezone.utc).isoformat(),
    )

    data = _load(audit_id, workspace)
    content_path = report_dir / CONTENT_FILE
    content_path.write_text(_content_page(data, report_dir), encoding="utf-8", newline="\n")

    for html_path in report_dir.glob("*.html"):
        if html_path.name == CONTENT_FILE:
            continue
        html = html_path.read_text(encoding="utf-8")
        if html_path.name == "remediation.html" and "m20-content-link" not in html:
            html = html.replace(
                "</header>",
                "</header><section id='m20-content-link' class='notice'><strong>Conteúdo, contexto editorial e Structured Data:</strong> "
                f"<a href='{CONTENT_FILE}'>abrir análise e sugestões por página →</a></section>",
                1,
            )
        if html_path.name == "ai-usage.html" and "m20-ai-telemetry" not in html:
            html = html.replace("</main>", _ai_telemetry(data) + "</main>", 1)
        html_path.write_text(html, encoding="utf-8", newline="\n")

    normalize_report_navigation(report_dir)
    return content_path


def _load(audit_id: str, workspace: AuditWorkspace) -> dict[str, Any]:
    persisted_context = load_content_analysis_context(workspace=workspace, audit_id=audit_id)
    connection = sqlite3.connect(workspace.database)
    connection.row_factory = sqlite3.Row
    try:
        run = _one(connection, "SELECT * FROM content_remediation_runs WHERE audit_id=?", (audit_id,))
        suggestions = _many(connection, """
            SELECT s.*,p.normalized_url,f.rule_id,f.title AS finding_title
            FROM content_remediation_suggestions s
            JOIN pages p ON p.page_id=s.page_id
            JOIN findings f ON f.finding_id=s.finding_id
            WHERE s.audit_id=? ORDER BY p.normalized_url,s.device,f.rule_id,s.suggestion_id
        """, (audit_id,))
        jsonld = _many(connection, """
            SELECT j.*,p.normalized_url
            FROM jsonld_remediation_suggestions j
            JOIN pages p ON p.page_id=j.page_id
            WHERE j.audit_id=? ORDER BY p.normalized_url,j.device,j.suggestion_id
        """, (audit_id,))
        attempts = _many(connection, "SELECT * FROM content_remediation_attempts WHERE audit_id=? ORDER BY started_at,attempt_index,attempt_id", (audit_id,))
        return {
            "run": run,
            "suggestions": suggestions,
            "jsonld": jsonld,
            "attempts": attempts,
            "context": persisted_context,
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


def _content_page(data: dict[str, Any], report_dir: Path) -> str:
    run = data["run"]
    nav = _nav(report_dir)
    run_status = str(run["status"]) if run is not None else "UNAVAILABLE"
    enabled = bool(run["enabled"]) if run is not None else False
    eligible = int(run["eligible_findings"]) if run is not None else 0
    generated = int(run["generated_suggestions"]) if run is not None else 0
    attempted = int(run["attempted_contexts"]) if run is not None else 0
    telemetry = _telemetry_summary(data["attempts"])
    context_html = _context_panel(data["context"])

    by_page: dict[tuple[str, str], list[sqlite3.Row]] = defaultdict(list)
    for row in data["suggestions"]:
        by_page[(str(row["normalized_url"]), str(row["device"]))].append(row)
    suggestion_cards = []
    for (url, device), rows in by_page.items():
        items = []
        for row in rows:
            evidence = ", ".join(_json_list(row["evidence_ids"])) or "—"
            items.append(f"""<details><summary>{escape(str(row['rule_id']))} · {escape(str(row['finding_title']))}</summary><div class='detail-body'><p><strong>Objetivo:</strong> {escape(str(row['objective']))}</p><p><strong>Local sugerido:</strong> {escape(str(row['target_location']))}</p><h5>Texto proposto</h5><pre>{escape(str(row['proposed_text']))}</pre><div class='remediation-grid'><div><small>Provider / modelo</small><strong>{escape(str(row['provider']))} / {escape(str(row['model'] or '—'))}</strong></div><div><small title='Confiança desta sugestão específica; não é o Confidence global do SCORE-GEO-002.'>Confiança da sugestão ⓘ</small><strong>{float(row['confidence'])*100:.0f}%</strong></div><div><small>Evidências</small><strong class='mono'>{escape(evidence)}</strong></div></div><div class='notice warn'><strong>Revisão humana obrigatória:</strong> {escape(str(row['review_note']))}</div></div></details>""")
        suggestion_cards.append(f"<article class='page-card'><div class='kicker'>Sugestões de conteúdo · {escape(device)}</div><h3 class='page-url'>{escape(url)}</h3>{''.join(items)}</article>")

    jsonld_cards = []
    for row in data["jsonld"]:
        improvements = "".join(f"<li>{escape(str(item))}</li>" for item in _json_list(row["improvements"]))
        types = ", ".join(_json_list(row["existing_types"])) or "Nenhum tipo observado"
        proposed = ""
        if row["proposed_json"]:
            proposed_obj = _json_value(row["proposed_json"])
            proposed = f"<h5>JSON-LD baseline sugerido</h5><pre>{escape(json.dumps(proposed_obj, ensure_ascii=False, indent=2, sort_keys=True))}</pre>"
        jsonld_cards.append(f"""<article class='page-card'><div class='finding-head'><div><span class='badge'>{escape(str(row['device']))}</span> <span class='badge info'>{escape(str(row['status']))}</span></div><span class='badge'>{escape(types)}</span></div><h3 class='page-url'>{escape(str(row['normalized_url']))}</h3>{proposed}<h5>Revisão recomendada</h5><ul>{improvements}</ul></article>""")

    if not enabled:
        ai_notice = "<div class='notice'><strong>Sugestões textuais por IA estão desabilitadas.</strong> O contexto editorial continua documentado, mas não gera chamada externa. A revisão JSON-LD abaixo é determinística.</div>"
    elif run_status == "NOT_CONFIGURED":
        ai_notice = "<div class='notice warn'><strong>Remediação por IA foi habilitada, mas não havia provider saudável/configurado.</strong> Nenhuma sugestão textual externa foi publicada; a revisão JSON-LD determinística continua disponível.</div>"
    else:
        ai_notice = "<div class='notice warn'><strong>Conteúdo sugerido é advisory.</strong> Não altera score/findings e requer validação humana antes de publicação, especialmente quando o conteúdo é YMYL.</div>"

    shortcuts = """<div class='notice'><strong>Atalhos:</strong> <a href='#contexto-editorial'>contexto editorial</a> · <a href='#telemetria-ia'>telemetria IA</a> · <a href='#sugestoes-textuais'>sugestões textuais</a> · <a href='#structured-data'>Structured Data</a> · <a href='#referencias-metodo'>referências</a></div>"""

    return f"""<!doctype html><html lang='pt-BR'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>Conteúdo e JSON-LD — RASAI — Search & AI Readiness Auditor</title><link rel='stylesheet' href='css/site.css'></head><body>{nav}<main class='app-main'><header class='hero'><div class='eyebrow'>Sugestões e remediação de conteúdo por IA · análise contextual e remediação opcional</div><h1>Conteúdo e JSON-LD</h1><p class='lead'>Avaliação editorial orientada por evidências. Quando IA está ativa, o contexto YMYL/E-E-A-T, propósito, público, experiência, freshness e origem do conteúdo condicionam a análise sem criar um score paralelo nem promessa de ranking/citação.</p><div class='metric-grid'>{_metric('Remediação por IA','Habilitada' if enabled else 'Desabilitada')}{_metric('Status',run_status)}{_metric('Findings elegíveis',eligible)}{_metric('Contextos chamados',attempted)}{_metric('Sugestões publicadas',generated)}{_metric('Revisões JSON-LD',len(data['jsonld']))}</div></header>{shortcuts}{ai_notice}{context_html}<section id='telemetria-ia' class='panel'><div class='kicker'>Rastreabilidade</div><h2>Uso de IA desta etapa</h2><p class='intro'>Os valores abaixo vêm da telemetria persistida das chamadas Sugestões e remediação de conteúdo por IA. Custo é estimativa baseada na tabela de pricing conhecida pelo adapter; quando não há base confiável, o relatório mostra indisponível em vez de inventar valor.</p><div class='metric-grid'>{_metric('Providers',telemetry['providers'])}{_metric('Modelos',telemetry['models'])}{_metric('Reasoning',telemetry['reasoning'])}{_metric('Chamadas',telemetry['calls'])}{_metric('Tempo acumulado',telemetry['duration'])}{_metric('Tokens totais',telemetry['tokens'])}{_metric('Custo estimado',telemetry['cost'])}</div><p><a href='ai-usage.html#m20-ai-telemetry'>Abrir detalhamento completo de IA, tentativas, tokens, duração e erros →</a></p></section><section id='sugestoes-textuais' class='panel'><div class='kicker'>People-first</div><h2>Sugestões textuais por finding</h2><p class='intro'>Confidence LOW do score, sozinho, nunca dispara esta etapa. Só findings semânticos/contentuais persistidos entram no input. O contrato bloqueia evidence_ids externos ao finding e rejeita novos tokens numéricos que não existam no conteúdo/evidências fornecidos.</p>{''.join(suggestion_cards) if suggestion_cards else '<p class="intro">Nenhuma sugestão textual persistida.</p>'}</section><section id='structured-data' class='panel'><div class='kicker'>Structured Data</div><h2>JSON-LD por página/dispositivo</h2><p class='intro'>Quando não há JSON-LD, o auditor propõe um baseline <code>WebPage</code> usando somente dados já observados. Quando já existe markup, não o sobrescreve: apresenta revisão segura e rastreável. Para rich results, valide a documentação específica do tipo.</p>{''.join(jsonld_cards) if jsonld_cards else '<p class="intro">Nenhuma revisão JSON-LD persistida.</p>'}</section><section id='referencias-metodo' class='panel'><div class='kicker'>Base conceitual oficial</div><h2>Referências aplicadas</h2><p class='intro'>O RASAI usa E-E-A-T e YMYL como contexto conceitual de avaliação, não como fator individual de ranking nem como percentual proprietário. O Google declara que confiança é o elemento central de E-E-A-T, que nem todo conteúdo precisa demonstrar todos os componentes e que tópicos YMYL recebem uma exigência maior de sinais alinhados a E-E-A-T.</p><div class='ref-grid'><div class='ref-card'><strong>Google Search Central — Helpful, reliable, people-first content</strong><p>Base para E-E-A-T, YMYL, Who/How/Why, propósito, público, experiência e freshness.</p><a href='{_GOOGLE_HELPFUL_CONTENT}' target='_blank' rel='noopener'>Abrir fonte oficial ↗</a></div><div class='ref-card'><strong>Google — Search Quality Rater Guidelines</strong><p>Referência conceitual para propósito da página, Page Quality e necessidades do usuário; avaliações humanas não são fatores diretos de ranking.</p><a href='{_GOOGLE_RATER_GUIDELINES}' target='_blank' rel='noopener'>Abrir fonte oficial ↗</a></div><div class='ref-card'><strong>Google — Structured Data Guidelines</strong><p>Políticas para marcação coerente com o conteúdo visível.</p><a href='{_GOOGLE_STRUCTURED_DATA}' target='_blank' rel='noopener'>Abrir fonte oficial ↗</a></div><div class='ref-card'><strong>Schema.org</strong><p>Vocabulário utilizado na proposta estrutural.</p><a href='{_SCHEMA_ORG}' target='_blank' rel='noopener'>Abrir referência ↗</a></div></div></section><footer class='footer'>Sugestões e remediação de conteúdo por IA é projeção auxiliar. Contexto editorial e sugestões não alteram retrospectivamente RuleExecution, Finding, Score, Coverage ou Confidence.</footer></main></body></html>\n"""


def _context_panel(record: tuple[Any, dict[str, Any]] | None) -> str:
    if record is None:
        return "<section id='contexto-editorial' class='panel'><h2>Contexto editorial</h2><div class='notice warn'>Contexto não persistido nesta auditoria.</div></section>"
    context, metadata = record
    payload = context.provider_payload()
    source_mode = str(metadata.get("source_mode") or "UNKNOWN")
    source_label = {"AUTO": "Inferido pela IA quando necessário", "MANUAL": "Configurado explicitamente", "MIXED": "Misto: configuração + inferência"}.get(source_mode, source_mode)
    cards = []
    for field in _CONTEXT_LABELS:
        value = str(payload[field])
        origin = "AUTO" if field in set(metadata.get("auto_fields") or ()) else "CONFIGURADO"
        cards.append(
            "<div class='metric'>"
            f"<small title='{escape(_CONTEXT_HINTS[field], quote=True)}'>{escape(_CONTEXT_LABELS[field])} ⓘ</small>"
            f"<strong>{escape(value)}</strong><span class='badge {'unknown' if origin == 'AUTO' else 'info'}'>{origin}</span></div>"
        )
    warning = (
        "<div class='notice warn'><strong>Contexto parcialmente ou totalmente AUTO:</strong> classificações automáticas são hipóteses de trabalho baseadas apenas no conteúdo observável. Quando o domínio é conhecido como YMYL, prefira configuração explícita.</div>"
        if source_mode in {"AUTO", "MIXED"}
        else "<div class='notice good'><strong>Contexto explicitamente configurado:</strong> a IA recebeu os parâmetros como contexto da auditoria; ainda assim não pode inventar fatos, credenciais ou conformidade regulatória.</div>"
    )
    return f"""<section id='contexto-editorial' class='panel'><div class='kicker'>YMYL · E-E-A-T · propósito</div><h2>Contexto editorial aplicado à IA</h2><p class='intro'>Origem: <strong>{escape(source_label)}</strong>. Estes parâmetros tornam a avaliação menos generalista. Eles ajustam a régua de evidência e a interpretação das recomendações, mas não entram aritmeticamente no SCORE-GEO-002.</p><div class='metric-grid'>{''.join(cards)}</div>{warning}</section>"""


def _nav(report_dir: Path) -> str:
    return render_report_navigation(report_dir, CONTENT_FILE)


def _telemetry_summary(attempts: list[sqlite3.Row]) -> dict[str, Any]:
    providers = sorted({str(row["provider"]) for row in attempts if row["provider"]})
    models = sorted({str(row["model"]) for row in attempts if row["model"]})
    reasoning = sorted({str(row["reasoning_profile"]) for row in attempts if row["reasoning_profile"]})
    duration_ms = sum(int(row["duration_ms"] or 0) for row in attempts)
    total_tokens_values = [int(row["total_tokens"]) for row in attempts if row["total_tokens"] is not None]
    costs = [float(row["estimated_cost"]) for row in attempts if row["estimated_cost"] is not None]
    currencies = sorted({str(row["cost_currency"]) for row in attempts if row["cost_currency"]})
    if costs:
        currency = currencies[0] if len(currencies) == 1 else "/".join(currencies)
        cost = f"{sum(costs):.8f} {currency}".strip()
    else:
        cost = "Indisponível" if attempts else "0"
    return {
        "providers": ", ".join(providers) or "—",
        "models": ", ".join(models) or "—",
        "reasoning": ", ".join(reasoning) or "—",
        "calls": len(attempts),
        "duration": f"{duration_ms/1000:.2f} s",
        "tokens": sum(total_tokens_values) if total_tokens_values else ("—" if attempts else 0),
        "cost": cost,
    }


def _ai_telemetry(data: dict[str, Any]) -> str:
    attempts = data["attempts"]
    run = data["run"]
    telemetry = _telemetry_summary(attempts)
    rows = []
    for row in attempts:
        error = " · ".join(str(row[key]) for key in ("error_class", "http_status", "error_code") if row[key] not in (None, "")) or "—"
        cost = f"{float(row['estimated_cost']):.8f} {escape(str(row['cost_currency'] or ''))}" if row["estimated_cost"] is not None else "—"
        rows.append(f"<tr><td class='mono'>{escape(str(row['url']))}</td><td>{escape(str(row['device']))}</td><td>{escape(str(row['provider']))}</td><td>{escape(str(row['model'] or '—'))}</td><td>{escape(str(row['reasoning_profile'] or '—'))}</td><td>{escape(str(row['status']))}</td><td>{escape(str(row['input_tokens'] if row['input_tokens'] is not None else '—'))}</td><td>{escape(str(row['output_tokens'] if row['output_tokens'] is not None else '—'))}</td><td>{escape(str(row['reasoning_tokens'] if row['reasoning_tokens'] is not None else '—'))}</td><td>{escape(str(row['total_tokens'] if row['total_tokens'] is not None else '—'))}</td><td>{cost}</td><td>{escape(str(row['duration_ms']))} ms</td><td>{escape(error)}</td></tr>")
    status = str(run["status"]) if run is not None else "UNAVAILABLE"
    enabled = bool(run["enabled"]) if run is not None else False
    context_record = data.get("context")
    context_summary = "—"
    if context_record is not None:
        context, metadata = context_record
        context_summary = f"{metadata.get('source_mode','UNKNOWN')} · {context.compact_summary()}"
    return f"""<section id='m20-ai-telemetry' class='panel'><div class='kicker'>Sugestões e remediação de conteúdo por IA</div><h2>Remediação opcional de conteúdo por IA</h2><p class='intro'>Telemetria desta finalidade é separada da análise semântica Análise semântica por IA, roteamento e telemetria. O recurso é default OFF e não executa chamadas apenas porque Confidence está baixa.</p><div class='metric-grid'>{_metric('Habilitada','Sim' if enabled else 'Não')}{_metric('Status',status)}{_metric('Providers',telemetry['providers'])}{_metric('Modelos',telemetry['models'])}{_metric('Reasoning',telemetry['reasoning'])}{_metric('Chamadas',telemetry['calls'])}{_metric('Tempo acumulado',telemetry['duration'])}{_metric('Tokens totais',telemetry['tokens'])}{_metric('Custo estimado',telemetry['cost'])}</div><p class='intro'><strong>Contexto editorial persistido:</strong> {escape(context_summary)}</p><div class='table-wrap'><table><thead><tr><th>URL</th><th>Device</th><th>Provider</th><th>Modelo</th><th>Reasoning</th><th>Status</th><th>Input</th><th>Output</th><th>Reasoning tokens</th><th>Total</th><th>Custo est.</th><th>Duração</th><th>Erro</th></tr></thead><tbody>{''.join(rows) if rows else '<tr><td colspan="13">Nenhuma chamada Sugestões e remediação de conteúdo por IA.</td></tr>'}</tbody></table></div></section>"""


def _metric(label: str, value: Any) -> str:
    return f"<div class='metric'><small>{escape(str(label))}</small><strong>{escape(str(value))}</strong></div>"


def _json_value(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def _json_list(value: Any) -> list[Any]:
    parsed = _json_value(value)
    return parsed if isinstance(parsed, list) else []
