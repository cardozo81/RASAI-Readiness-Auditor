"""Final read-only UX layer for generated audit and consolidated HTML reports.

This module only projects persisted/report-owned information. It never recalculates
scores, runs collectors, calls providers, changes audit evidence, or mutates audit.db.
"""
from __future__ import annotations

from dataclasses import dataclass
from html import escape
import re
import sqlite3
from typing import Any, Mapping, Sequence

from rasai.report_contract import ReportSurface, surface_by_filename

_STYLE_ID = "rasai-reader-experience-v1"
_SCRIPT_ID = "rasai-reader-experience-script-v1"
_HELP_MARKER = "data-rasai-page-help='true'"
_STATUS_MARKER = "data-rasai-analysis-status='true'"

_COMPONENTS_BY_FILE: dict[str, tuple[str, ...]] = {
    "index.html": (),
    "readiness.html": ("CORE_AUDIT", "SEMANTIC_AI"),
    "scoring.html": ("CORE_AUDIT",),
    "context.html": ("CORE_AUDIT",),
    "crawling-discovery.html": ("CORE_AUDIT", "TECHNICAL_AI"),
    "mobile.html": ("CORE_AUDIT", "SEMANTIC_AI"),
    "desktop.html": ("CORE_AUDIT", "SEMANTIC_AI"),
    "accessibility.html": ("WEB_PERFORMANCE",),
    "web-performance.html": ("WEB_PERFORMANCE",),
    "standards.html": ("CORE_AUDIT",),
    "apdex.html": ("SYNTHETIC_APDEX",),
    "apdex-experience.html": ("EXPERIENCE_APDEX",),
    "search-intelligence.html": ("SEARCH_INTELLIGENCE",),
    "observability.html": ("GOOGLE_SEARCH_CONSOLE",),
    "ai-usage.html": (
        "SEMANTIC_AI",
        "TECHNICAL_AI",
        "CONTENT_REMEDIATION_AI",
        "IMPROVEMENT_INTELLIGENCE",
    ),
    "improvement-intelligence.html": ("IMPROVEMENT_INTELLIGENCE",),
    "content-suggestions.html": ("CONTENT_REMEDIATION_AI",),
    "remediation.html": ("CORE_AUDIT",),
    "quality.html": ("CORE_AUDIT",),
    "references.html": ("CORE_AUDIT",),
}

_COMPONENT_LABELS = {
    "CORE_AUDIT": "Coleta e análise principal",
    "SEMANTIC_AI": "Análise semântica por IA",
    "TECHNICAL_AI": "Análise técnica por IA",
    "CONTENT_REMEDIATION_AI": "Sugestões de conteúdo por IA",
    "IMPROVEMENT_INTELLIGENCE": "Análise profunda por IA",
    "WEB_PERFORMANCE": "Web Performance / PageSpeed / Lighthouse",
    "SYNTHETIC_APDEX": "Synthetic Navigation Apdex",
    "EXPERIENCE_APDEX": "Synthetic User Experience Apdex",
    "SEARCH_INTELLIGENCE": "Search Intelligence",
    "GOOGLE_SEARCH_CONSOLE": "Google Search Console",
}

_CONFIG_GUIDANCE = {
    "SEMANTIC_AI": "Habilite a análise semântica e configure ao menos um provedor de IA elegível.",
    "TECHNICAL_AI": "Habilite a análise técnica por IA e configure um provedor de IA elegível.",
    "CONTENT_REMEDIATION_AI": "Habilite as sugestões de conteúdo por IA e configure um provedor elegível.",
    "IMPROVEMENT_INTELLIGENCE": "Habilite a análise profunda e configure provedor, modelo e esforço compatíveis com esta finalidade.",
    "WEB_PERFORMANCE": "Habilite Web Performance e configure as credenciais necessárias às fontes externas que desejar usar, como PageSpeed/CrUX.",
    "SYNTHETIC_APDEX": "Habilite Synthetic Navigation Apdex e informe os parâmetros mínimos da medição, incluindo threshold e amostragem.",
    "EXPERIENCE_APDEX": "Habilite Synthetic User Experience Apdex e seus parâmetros de população; a execução depende da medição sintética base aplicável.",
    "SEARCH_INTELLIGENCE": "Habilite Search Intelligence, configure um provedor de busca compatível e informe as consultas necessárias.",
    "GOOGLE_SEARCH_CONSOLE": "Configure a integração com Search Console e a propriedade/site correspondente quando essa observação for desejada.",
}

_STATUS_LABELS = {
    "SUCCESS": "Concluído",
    "DISABLED": "Não solicitado",
    "NOT_APPLICABLE": "Não aplicável",
    "NOT_CONFIGURED": "Configuração necessária",
    "WAITING_FOR_DATA": "Aguardando dados",
    "REQUESTED_NOT_EXECUTED": "Solicitado, não executado",
    "PENDING": "Pendente",
    "RUNNING": "Em processamento",
    "FAILED_RETRYABLE": "Falhou; pode ser reprocessado",
    "FAILED_PERMANENT": "Falhou",
    "BLOCKED": "Bloqueado",
}

_GOOD = {"SUCCESS"}
_NEUTRAL = {"DISABLED", "NOT_APPLICABLE"}
_CONFIG = {"NOT_CONFIGURED"}
_WAITING = {"WAITING_FOR_DATA", "REQUESTED_NOT_EXECUTED", "PENDING", "RUNNING"}
_FAILURE = {"FAILED_RETRYABLE", "FAILED_PERMANENT", "BLOCKED"}


@dataclass(frozen=True, slots=True)
class PageState:
    label: str
    tone: str
    summary: str


def _table_exists(connection: sqlite3.Connection, table: str) -> bool:
    try:
        return connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1", (table,)
        ).fetchone() is not None
    except sqlite3.Error:
        return False


def _rows(connection: sqlite3.Connection, sql: str, params: tuple[Any, ...]) -> list[sqlite3.Row]:
    try:
        return list(connection.execute(sql, params).fetchall())
    except sqlite3.Error:
        return []


def _one(connection: sqlite3.Connection, sql: str, params: tuple[Any, ...]) -> sqlite3.Row | None:
    try:
        return connection.execute(sql, params).fetchone()
    except sqlite3.Error:
        return None


def build_report_experience_context(connection: sqlite3.Connection, audit_id: str) -> dict[str, Any]:
    """Read only persisted execution metadata needed by the final HTML projection."""
    contract: dict[str, Any] | None = None
    if _table_exists(connection, "audit_fulfillment_contracts"):
        row = _one(
            connection,
            "SELECT processing_status,score_status,report_status,consolidation_eligible,"
            "required_items,successful_items,pending_items,blocked_items,expired_items,reprocess_count "
            "FROM audit_fulfillment_contracts WHERE audit_id=?",
            (audit_id,),
        )
        if row is not None:
            contract = {key: row[key] for key in row.keys()}

    work_items: list[dict[str, Any]] = []
    if _table_exists(connection, "audit_fulfillment_work_items"):
        for row in _rows(
            connection,
            "SELECT component,scope_key,required,status,attempt_count,retryable,last_error_class,last_error_code "
            "FROM audit_fulfillment_work_items WHERE audit_id=? ORDER BY component,scope_key",
            (audit_id,),
        ):
            work_items.append({key: row[key] for key in row.keys()})

    url_count = 0
    devices: tuple[str, ...] = ()
    if _table_exists(connection, "pages"):
        row = _one(connection, "SELECT COUNT(DISTINCT normalized_url) AS total FROM pages WHERE audit_id=?", (audit_id,))
        if row is not None:
            try:
                url_count = int(row["total"] or 0)
            except (TypeError, ValueError):
                url_count = 0
    if _table_exists(connection, "page_snapshots") and _table_exists(connection, "pages"):
        found = _rows(
            connection,
            "SELECT DISTINCT UPPER(COALESCE(ps.device,'')) AS device FROM page_snapshots ps "
            "JOIN pages p ON p.page_id=ps.page_id WHERE p.audit_id=? ORDER BY device",
            (audit_id,),
        )
        devices = tuple(str(row["device"]) for row in found if str(row["device"] or "").strip())

    return {
        "audit_id": audit_id,
        "contract": contract,
        "work_items": tuple(work_items),
        "url_count": url_count,
        "devices": devices,
    }


def _items_for(filename: str, context: Mapping[str, Any]) -> tuple[Mapping[str, Any], ...]:
    components = set(_COMPONENTS_BY_FILE.get(filename, ()))
    if not components:
        return ()
    return tuple(
        item for item in context.get("work_items", ())
        if isinstance(item, Mapping) and str(item.get("component") or "") in components
    )


def _state_from_items(items: Sequence[Mapping[str, Any]], *, optional: bool) -> PageState:
    if not items:
        if optional:
            return PageState(
                "Estado não determinado",
                "neutral",
                "A página está disponível, mas não há estado operacional persistido suficiente para classificar esta capacidade com segurança.",
            )
        return PageState(
            "Dados da auditoria disponíveis",
            "info",
            "Esta página apresenta dados persistidos da auditoria; consulte abaixo a cobertura e as limitações específicas.",
        )

    statuses = {str(item.get("status") or "UNKNOWN").upper() for item in items}
    successful = sum(1 for item in items if str(item.get("status") or "").upper() in _GOOD)
    if statuses & _CONFIG:
        return PageState(
            "Configuração necessária",
            "warn",
            "Uma capacidade solicitada não pôde executar porque faltou configuração necessária.",
        )
    if statuses & _FAILURE:
        if successful:
            return PageState(
                "Concluída com limitações",
                "warn",
                "Parte do resultado foi produzida, mas uma ou mais dependências falharam ou ficaram bloqueadas.",
            )
        return PageState(
            "Não concluída",
            "bad",
            "A capacidade foi solicitada, porém a execução necessária não produziu resultado utilizável.",
        )
    if statuses & _WAITING:
        if successful:
            return PageState(
                "Concluída com limitações",
                "warn",
                "Há resultado utilizável, mas parte do universo ainda depende de dados ou execução complementar.",
            )
        return PageState(
            "Dados insuficientes",
            "warn",
            "A análise depende de dados ou execução que ainda não produziram evidência utilizável.",
        )
    if statuses <= _NEUTRAL:
        if statuses == {"NOT_APPLICABLE"}:
            return PageState("Não aplicável", "neutral", "Esta capacidade não se aplica ao universo observado nesta auditoria.")
        return PageState("Dados não solicitados", "neutral", "A capacidade correspondente não foi habilitada para esta auditoria.")
    if statuses <= (_GOOD | _NEUTRAL) and successful:
        return PageState("Concluída", "good", "Os requisitos persistidos aplicáveis a esta análise foram atendidos.")
    return PageState(
        "Estado não determinado",
        "neutral",
        "Há dados persistidos, mas o estado disponível não permite classificar a execução com segurança.",
    )


def _index_state(context: Mapping[str, Any]) -> PageState:
    contract = context.get("contract")
    if not isinstance(contract, Mapping):
        return PageState(
            "Estado não determinado",
            "neutral",
            "A auditoria foi materializada, mas o contrato de conclusão não está disponível para classificar o estado final.",
        )
    status = str(contract.get("processing_status") or "UNKNOWN").upper()
    success = int(contract.get("successful_items") or 0)
    required = int(contract.get("required_items") or 0)
    if status == "COMPLETE" and bool(contract.get("consolidation_eligible")):
        return PageState(
            "Auditoria concluída",
            "good",
            f"{success}/{required} requisito(s) aplicáveis atendidos. O resultado persistido está final para esta execução.",
        )
    if status in {"PARTIAL_RETRYABLE", "PROCESSING"}:
        return PageState(
            "Auditoria preliminar",
            "warn",
            f"{success}/{required} requisito(s) aplicáveis atendidos. Existem pendências que podem reduzir cobertura ou impedir conclusão final.",
        )
    if status in {"PARTIAL_BLOCKED", "FAILED_FATAL", "EXPIRED_FOR_COMPLETION"}:
        return PageState(
            "Auditoria incompleta",
            "bad",
            f"{success}/{required} requisito(s) aplicáveis atendidos. Há bloqueio, falha ou validade temporal incompatível com a conclusão final.",
        )
    return PageState(
        "Estado não determinado",
        "neutral",
        "O contrato de execução não permite classificar esta auditoria como final neste momento.",
    )


def _page_state(filename: str, surface: ReportSurface, context: Mapping[str, Any]) -> PageState:
    if filename == "index.html":
        return _index_state(context)
    return _state_from_items(_items_for(filename, context), optional=surface.optional)


def _scope_text(context: Mapping[str, Any]) -> str:
    urls = int(context.get("url_count") or 0)
    devices = tuple(str(item) for item in context.get("devices", ()) if str(item).strip())
    pieces: list[str] = []
    if urls:
        pieces.append(f"{urls} URL" if urls == 1 else f"{urls} URLs")
    if devices:
        pretty = ["Mobile" if item == "MOBILE" else "Desktop" if item == "DESKTOP" else item.title() for item in devices]
        pieces.append(" + ".join(pretty))
    return " · ".join(pieces) or "Escopo persistido na auditoria"


def _ai_state(html: str, filename: str, items: Sequence[Mapping[str, Any]]) -> tuple[str, str]:
    ai_items = [item for item in items if "AI" in str(item.get("component") or "") or str(item.get("component") or "") == "IMPROVEMENT_INTELLIGENCE"]
    statuses = {str(item.get("status") or "UNKNOWN").upper() for item in ai_items}
    if "Gerado por IA" in html or "Conteúdo gerado por IA" in html:
        return "IA utilizada", "good"
    if "data-ai-cost-attribution='true'" in html and "Sem consumo IA direto" not in html:
        return "IA utilizada", "good"
    if statuses & (_FAILURE | _CONFIG | _WAITING):
        return "IA solicitada, não concluída", "warn"
    if ai_items and statuses <= _NEUTRAL:
        return "IA não utilizada", "neutral"
    if filename == "ai-usage.html":
        return "Telemetria de IA", "info"
    return "IA não utilizada diretamente", "neutral"


def _chip(text: str, tone: str = "neutral") -> str:
    return f"<span class='rasai-state-chip state-{escape(tone, quote=True)}'>{escape(text)}</span>"


def _render_status_header(*, filename: str, surface: ReportSurface, context: Mapping[str, Any], html: str) -> str:
    state = _page_state(filename, surface, context)
    items = _items_for(filename, context)
    ai_label, ai_tone = _ai_state(html, filename, items)
    title = "Estado da auditoria" if filename == "index.html" else "Estado desta análise"
    return (
        f"<section class='rasai-analysis-status state-{escape(state.tone, quote=True)}' {_STATUS_MARKER}>"
        "<div class='rasai-analysis-status-main'>"
        f"<div><div class='rasai-status-kicker'>{escape(title)}</div><h2>{escape(state.label)}</h2>"
        f"<p>{escape(state.summary)}</p></div>"
        f"<span class='rasai-status-badge state-{escape(state.tone, quote=True)}'>{escape(state.label)}</span>"
        "</div>"
        "<div class='rasai-status-meta'>"
        + _chip(_scope_text(context), "info")
        + _chip(ai_label, ai_tone)
        + _chip("Dados persistidos · sem recálculo no HTML", "neutral")
        + "</div>"
        "</section>"
    )


def _human_status(item: Mapping[str, Any]) -> str:
    raw = str(item.get("status") or "UNKNOWN").upper()
    return _STATUS_LABELS.get(raw, raw.replace("_", " ").title())


def _component_tone(item: Mapping[str, Any]) -> str:
    status = str(item.get("status") or "UNKNOWN").upper()
    if status in _GOOD:
        return "good"
    if status in _FAILURE:
        return "bad"
    if status in (_CONFIG | _WAITING):
        return "warn"
    return "neutral"


def _render_work_items(items: Sequence[Mapping[str, Any]]) -> str:
    if not items:
        return "<p class='rasai-help-muted'>Nenhum estado operacional específico foi persistido para esta página.</p>"
    rows: list[str] = []
    for item in items:
        component = str(item.get("component") or "UNKNOWN")
        scope = str(item.get("scope_key") or "AUDIT")
        code = str(item.get("last_error_code") or "").strip()
        technical = f"<br><small>Referência técnica: <code>{escape(component)}</code> · escopo <code>{escape(scope)}</code>"
        if code:
            technical += f" · código <code>{escape(code)}</code>"
        technical += "</small>"
        rows.append(
            "<tr>"
            f"<td>{escape(_COMPONENT_LABELS.get(component, component.replace('_', ' ').title()))}{technical}</td>"
            f"<td>{_chip(_human_status(item), _component_tone(item))}</td>"
            f"<td>{int(item.get('attempt_count') or 0)}</td>"
            "</tr>"
        )
    return (
        "<div class='table-wrap rasai-help-table'><table><thead><tr><th>Dependência / etapa</th><th>Estado</th><th>Tentativas</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table></div>"
    )


def _render_list(values: Sequence[str], empty: str) -> str:
    material = [str(value).strip() for value in values if str(value).strip()]
    if not material:
        return f"<p class='rasai-help-muted'>{escape(empty)}</p>"
    return "<ul>" + "".join(f"<li>{escape(value)}</li>" for value in material) + "</ul>"


def _render_guidance(items: Sequence[Mapping[str, Any]], surface: ReportSurface) -> str:
    actions: list[str] = []
    for item in items:
        status = str(item.get("status") or "UNKNOWN").upper()
        component = str(item.get("component") or "")
        if status in (_CONFIG | _WAITING | _FAILURE):
            guidance = _CONFIG_GUIDANCE.get(component)
            if guidance and guidance not in actions:
                actions.append(guidance)
    if actions:
        return _render_list(tuple(actions), "Nenhuma ação de configuração identificada.")
    if surface.optional_dependencies:
        return (
            "<p class='rasai-help-muted'>Nenhuma correção de configuração foi identificada como obrigatória nesta projeção. "
            "Dependências complementares só precisam ser habilitadas quando o usuário desejar os dados adicionais correspondentes.</p>"
        )
    return "<p class='rasai-help-muted'>Não há configuração adicional indicada por esta página.</p>"


def _render_help(*, filename: str, surface: ReportSurface, context: Mapping[str, Any], html: str) -> str:
    items = _items_for(filename, context)
    state = _page_state(filename, surface, context)
    ai_label, ai_tone = _ai_state(html, filename, items)
    dialog_id = "rasai-page-help"
    trigger = (
        "<section class='rasai-page-transparency' data-rasai-page-help-trigger='true'>"
        "<div><strong>Transparência deste relatório</strong><p>Dados utilizados, dependências, limitações e configuração necessária.</p></div>"
        f"<button type='button' class='rasai-help-open' data-dialog-id='{dialog_id}'>Entenda esta página</button>"
        "</section>"
    )
    dialog = (
        f"<dialog id='{dialog_id}' class='rasai-help-dialog' {_HELP_MARKER}>"
        "<div class='rasai-help-dialog-head'><div><div class='rasai-status-kicker'>Transparência</div>"
        f"<h2>Entenda: {escape(surface.label)}</h2></div><button type='button' class='rasai-help-close' aria-label='Fechar'>×</button></div>"
        f"<div class='rasai-help-summary state-{escape(state.tone, quote=True)}'><strong>{escape(state.label)}</strong><p>{escape(state.summary)}</p></div>"
        "<section><h3>O que esta página entrega</h3>"
        + _render_list(surface.outputs, "A página não declara outputs adicionais.")
        + "</section>"
        "<section><h3>Dados que podem alimentar esta página</h3>"
        + _render_list(surface.inputs, "Nenhum input específico declarado.")
        + "</section>"
        "<section><h3>Estado das dependências nesta auditoria</h3>"
        + _render_work_items(items)
        + "</section>"
        "<div class='rasai-help-grid'>"
        "<section><h3>Dependências necessárias</h3>"
        + _render_list(surface.required_dependencies, "Nenhuma dependência adicional além das evidências persistidas.")
        + "</section>"
        "<section><h3>Dependências complementares</h3>"
        + _render_list(surface.optional_dependencies, "Nenhuma dependência complementar declarada.")
        + "</section></div>"
        "<section><h3>Como obter uma análise mais completa</h3>"
        + _render_guidance(items, surface)
        + "</section>"
        "<section><h3>Uso de IA</h3>"
        f"<p>{_chip(ai_label, ai_tone)}</p><p>{escape(surface.ai_usage)}</p>"
        + ("<p><a href='ai-usage.html'>Abrir rastreabilidade de IA e custos</a></p>" if filename != "ai-usage.html" else "")
        + "</section>"
        "<details class='rasai-help-technical'><summary>Rastreabilidade técnica</summary>"
        f"<p><strong>Arquivo:</strong> <code>{escape(filename)}</code></p>"
        f"<p><strong>Fonte de verdade:</strong> {escape(surface.source_of_truth)}</p>"
        f"<p><strong>Impacto na pontuação:</strong> {escape(surface.score_impact)}</p>"
        "<p>Identificadores técnicos aparecem aqui apenas para suporte e auditoria; a leitura principal usa linguagem orientada ao analista.</p>"
        "</details>"
        "</dialog>"
    )
    return trigger + dialog


def _dashboard_path() -> str:
    return (
        "<section class='rasai-dashboard-path' data-rasai-dashboard-path='true'>"
        "<a href='readiness.html'><small>Resultado técnico</small><strong>Entender a avaliação</strong><span>Score, cobertura, confiança e fatores que explicam o resultado.</span></a>"
        "<a href='remediation.html'><small>Ação</small><strong>Ver o que corrigir</strong><span>Prioridades, páginas afetadas, correção e critério de aceite.</span></a>"
        "<a href='quality.html'><small>Evolução</small><strong>Verificar o que mudou</strong><span>Qualidade, comparação e verificação quando houver base compatível.</span></a>"
        "</section>"
    )


def _inject_after_header_or_main(html: str, block: str) -> str:
    if "</header>" in html:
        return html.replace("</header>", "</header>" + block, 1)
    match = re.search(r"<main\b[^>]*>", html, flags=re.IGNORECASE)
    if match:
        return html[: match.end()] + block + html[match.end() :]
    return block + html


def _inject_before_footer(html: str, block: str) -> str:
    match = re.search(r"<footer\b", html, flags=re.IGNORECASE)
    if match:
        return html[: match.start()] + block + html[match.start() :]
    if "</main>" in html:
        return html.replace("</main>", block + "</main>", 1)
    return html + block


def _mark_dashboard(html: str) -> str:
    return re.sub(
        r"<main\b([^>]*?)class=(['\"])([^'\"]*)\2([^>]*)>",
        lambda match: (
            "<main" + match.group(1) + "class=" + match.group(2)
            + (match.group(3) + " rasai-dashboard-page" if "rasai-dashboard-page" not in match.group(3) else match.group(3))
            + match.group(2) + match.group(4) + ">"
        ),
        html,
        count=1,
        flags=re.IGNORECASE,
    )


def enhance_report_experience(html: str, *, filename: str, context: Mapping[str, Any]) -> str:
    """Add presentation-only status, transparency and reading-path UX to one AUD page."""
    try:
        surface = surface_by_filename(filename)
    except KeyError:
        return html

    rendered = html
    if _STYLE_ID not in rendered:
        rendered = rendered.replace("</head>", _STYLE + "</head>", 1) if "</head>" in rendered else _STYLE + rendered
    if _SCRIPT_ID not in rendered:
        rendered = rendered.replace("</body>", _SCRIPT + "</body>", 1) if "</body>" in rendered else rendered + _SCRIPT

    if _STATUS_MARKER not in rendered:
        rendered = _inject_after_header_or_main(
            rendered,
            _render_status_header(filename=filename, surface=surface, context=context, html=rendered),
        )
    if filename == "index.html":
        rendered = _mark_dashboard(rendered)
        if "data-rasai-dashboard-path='true'" not in rendered:
            status_end = re.search(r"</section>", rendered[rendered.find(_STATUS_MARKER):]) if _STATUS_MARKER in rendered else None
            if status_end and _STATUS_MARKER in rendered:
                marker = rendered.find(_STATUS_MARKER)
                absolute = marker + status_end.end()
                rendered = rendered[:absolute] + _dashboard_path() + rendered[absolute:]
            else:
                rendered = _inject_after_header_or_main(rendered, _dashboard_path())
    if _HELP_MARKER not in rendered:
        rendered = _inject_before_footer(
            rendered,
            _render_help(filename=filename, surface=surface, context=context, html=rendered),
        )
    return rendered


def enhance_consolidated_experience(html: str, artifact: Mapping[str, Any] | None = None) -> str:
    """Apply the same visual semantics to the static historical/consolidated report."""
    if "data-rasai-consolidated-experience='true'" in html:
        return html
    ai = artifact.get("ai") if isinstance(artifact, Mapping) and isinstance(artifact.get("ai"), Mapping) else None
    ai_requested = bool(ai and ai.get("requested"))
    ai_status = str(ai.get("status") or "UNKNOWN").upper() if ai else "NOT_REQUESTED"
    changes = [item for item in (artifact.get("changes", ()) if isinstance(artifact, Mapping) else ()) if isinstance(item, Mapping)]
    if ai_requested and ai_status == "COMPLETE":
        ai_chip = _chip("IA especialista concluída", "good")
    elif ai_requested:
        ai_chip = _chip("IA especialista não concluída", "warn")
    else:
        ai_chip = _chip("IA especialista não solicitada", "neutral")
    improved = sum(1 for item in changes if str(item.get("status") or "").upper() in {"IMPROVED", "RESOLVED"})
    regressed = sum(1 for item in changes if str(item.get("status") or "").upper() in {"REGRESSED", "NEW"})
    header = (
        "<section class='rasai-analysis-status state-info' data-rasai-consolidated-experience='true'>"
        "<div class='rasai-analysis-status-main'><div><div class='rasai-status-kicker'>Estado do consolidado</div>"
        "<h2>Leitura histórica materializada</h2><p>Os valores exibidos reutilizam auditorias persistidas e comparáveis; o HTML não recalcula as fontes originais.</p></div>"
        "<span class='rasai-status-badge state-info'>Consolidado</span></div>"
        "<div class='rasai-status-meta'>"
        + ai_chip
        + _chip(f"{improved} melhora(s) / resolução(ões) observada(s)", "good" if improved else "neutral")
        + _chip(f"{regressed} regressão(ões) / novo(s) sinal(is)", "warn" if regressed else "neutral")
        + "</div></section>"
    )
    help_block = (
        "<section class='rasai-page-transparency' data-rasai-consolidated-help-trigger='true'><div><strong>Transparência deste consolidado</strong>"
        "<p>Fontes históricas, comparabilidade, uso de IA e limites de interpretação.</p></div>"
        "<button type='button' class='rasai-help-open' data-dialog-id='rasai-consolidated-help'>Entenda este relatório</button></section>"
        "<dialog id='rasai-consolidated-help' class='rasai-help-dialog' data-rasai-page-help='true'>"
        "<div class='rasai-help-dialog-head'><div><div class='rasai-status-kicker'>Transparência</div><h2>Entenda o relatório consolidado</h2></div>"
        "<button type='button' class='rasai-help-close' aria-label='Fechar'>×</button></div>"
        "<section><h3>O que ele utiliza</h3><ul><li>Auditorias concluídas e elegíveis no período/filtro.</li>"
        "<li>Scores e métricas já persistidos em cada auditoria.</li><li>Comparações e verificação de correções quando metodologicamente compatíveis.</li>"
        "<li>Análise especialista por IA somente quando explicitamente solicitada.</li></ul></section>"
        "<section><h3>Como interpretar evolução</h3><p>Melhora observada não prova causalidade. Correção verificada demonstra a transição persistida da regra; não comprova, por si só, impacto em ranking, tráfego, conversão ou visibilidade em IA.</p></section>"
        f"<section><h3>IA especialista</h3><p>{ai_chip}</p><p>Quando usada, a IA interpreta o pacote de mudanças já calculado e não altera os valores históricos.</p></section>"
        "<details class='rasai-help-technical'><summary>Rastreabilidade técnica</summary><p>Fontes: AUD-*/audit.db elegíveis, índice derivado de consolidação e artifacts do CONS. Séries incompatíveis não devem ser fundidas silenciosamente.</p></details>"
        "</dialog>"
    )
    rendered = html
    if _STYLE_ID not in rendered:
        rendered = rendered.replace("</head>", _STYLE + "</head>", 1) if "</head>" in rendered else _STYLE + rendered
    if _SCRIPT_ID not in rendered:
        rendered = rendered.replace("</body>", _SCRIPT + "</body>", 1) if "</body>" in rendered else rendered + _SCRIPT
    rendered = _inject_after_header_or_main(rendered, header)
    rendered = _inject_before_footer(rendered, help_block)
    return rendered


_STYLE = r"""
<style id='rasai-reader-experience-v1'>
:root{--rasai-good:#3f7452;--rasai-good-bg:#edf7f0;--rasai-warn:#7b5728;--rasai-warn-bg:#fff7e8;--rasai-bad:#8f4447;--rasai-bad-bg:#fff0f0;--rasai-info:#3c5e9d;--rasai-info-bg:#eef3fb;--rasai-neutral:#5d6878;--rasai-neutral-bg:#f4f6f8}
.rasai-analysis-status{margin:14px 0 18px;padding:16px 18px;border:1px solid var(--line,rgba(80,96,120,.18));border-left:5px solid var(--rasai-neutral);border-radius:10px;background:var(--rasai-neutral-bg);box-shadow:0 8px 24px rgba(31,45,61,.05)}
.rasai-analysis-status.state-good{border-left-color:var(--rasai-good);background:var(--rasai-good-bg)}.rasai-analysis-status.state-warn{border-left-color:var(--rasai-warn);background:var(--rasai-warn-bg)}.rasai-analysis-status.state-bad{border-left-color:var(--rasai-bad);background:var(--rasai-bad-bg)}.rasai-analysis-status.state-info{border-left-color:var(--rasai-info);background:var(--rasai-info-bg)}
.rasai-analysis-status-main{display:flex;align-items:flex-start;justify-content:space-between;gap:18px}.rasai-analysis-status h2{margin:3px 0 6px;font-size:1.24rem}.rasai-analysis-status p{margin:0;line-height:1.5}.rasai-status-kicker{font-size:.72rem;font-weight:800;letter-spacing:.08em;text-transform:uppercase;color:var(--muted,#6f7b8d)}
.rasai-status-badge,.rasai-state-chip{display:inline-flex;align-items:center;border-radius:999px;font-size:.76rem;font-weight:750;line-height:1.25;padding:5px 9px;white-space:nowrap;border:1px solid transparent}.state-good.rasai-status-badge,.rasai-state-chip.state-good{color:var(--rasai-good);background:#fff;border-color:rgba(63,116,82,.3)}.state-warn.rasai-status-badge,.rasai-state-chip.state-warn{color:var(--rasai-warn);background:#fff;border-color:rgba(123,87,40,.3)}.state-bad.rasai-status-badge,.rasai-state-chip.state-bad{color:var(--rasai-bad);background:#fff;border-color:rgba(143,68,71,.3)}.state-info.rasai-status-badge,.rasai-state-chip.state-info{color:var(--rasai-info);background:#fff;border-color:rgba(60,94,157,.28)}.state-neutral.rasai-status-badge,.rasai-state-chip.state-neutral{color:var(--rasai-neutral);background:#fff;border-color:rgba(93,104,120,.24)}
.rasai-status-meta{display:flex;flex-wrap:wrap;gap:7px;margin-top:12px}.rasai-dashboard-path{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin:0 0 20px}.rasai-dashboard-path a{display:flex;flex-direction:column;gap:5px;padding:15px 16px;border:1px solid var(--line,rgba(80,96,120,.18));border-radius:10px;background:#fff;text-decoration:none;box-shadow:0 8px 22px rgba(31,45,61,.04)}.rasai-dashboard-path a:hover{border-color:rgba(60,94,157,.38);box-shadow:0 10px 26px rgba(31,45,61,.08)}.rasai-dashboard-path small{font-weight:800;text-transform:uppercase;letter-spacing:.06em;color:var(--rasai-info)}.rasai-dashboard-path strong{font-size:1.02rem;color:var(--ink,#273449)}.rasai-dashboard-path span{font-size:.86rem;line-height:1.45;color:var(--muted,#6f7b8d)}
.rasai-dashboard-page .indicator-card,.rasai-dashboard-page .score-card,.rasai-dashboard-page .metric{transition:transform .15s ease,box-shadow .15s ease}.rasai-dashboard-page .indicator-card:hover,.rasai-dashboard-page .score-card:hover{transform:translateY(-1px);box-shadow:0 10px 28px rgba(31,45,61,.08)}
.rasai-page-transparency{display:flex;justify-content:space-between;align-items:center;gap:16px;margin:26px 0 14px;padding:13px 15px;border-top:1px solid var(--line,rgba(80,96,120,.18));border-bottom:1px solid var(--line,rgba(80,96,120,.18));background:#fafbfc}.rasai-page-transparency p{margin:3px 0 0;font-size:.86rem;color:var(--muted,#6f7b8d)}.rasai-help-open,.rasai-help-close{border:1px solid rgba(60,94,157,.3);border-radius:7px;background:#fff;color:var(--rasai-info);font:inherit;font-weight:750;cursor:pointer;padding:8px 11px}.rasai-help-open:hover{background:var(--rasai-info-bg)}.rasai-help-close{font-size:1.25rem;line-height:1;padding:6px 9px;color:var(--rasai-neutral)}
.rasai-help-dialog{width:min(900px,calc(100vw - 32px));max-height:min(86vh,900px);border:0;border-radius:12px;padding:0;box-shadow:0 28px 80px rgba(20,32,50,.28);color:var(--ink,#273449)}.rasai-help-dialog::backdrop{background:rgba(20,30,45,.48)}.rasai-help-dialog>*{margin-left:20px;margin-right:20px}.rasai-help-dialog-head{position:sticky;top:0;z-index:2;display:flex;justify-content:space-between;align-items:flex-start;gap:14px;margin:0;padding:18px 20px 14px;background:#fff;border-bottom:1px solid var(--line,rgba(80,96,120,.18))}.rasai-help-dialog-head h2{margin:3px 0 0}.rasai-help-dialog>section,.rasai-help-dialog>details{margin-top:18px;margin-bottom:18px}.rasai-help-dialog h3{margin:0 0 8px;font-size:1rem}.rasai-help-dialog ul{margin:.4rem 0;padding-left:1.25rem}.rasai-help-dialog li{margin:.34rem 0;line-height:1.45}.rasai-help-summary{padding:12px 14px;border-radius:8px;border-left:4px solid var(--rasai-neutral);background:var(--rasai-neutral-bg)}.rasai-help-summary.state-good{border-left-color:var(--rasai-good);background:var(--rasai-good-bg)}.rasai-help-summary.state-warn{border-left-color:var(--rasai-warn);background:var(--rasai-warn-bg)}.rasai-help-summary.state-bad{border-left-color:var(--rasai-bad);background:var(--rasai-bad-bg)}.rasai-help-summary.state-info{border-left-color:var(--rasai-info);background:var(--rasai-info-bg)}.rasai-help-summary p{margin:.3rem 0 0}.rasai-help-grid{display:grid;grid-template-columns:1fr 1fr;gap:18px}.rasai-help-muted{color:var(--muted,#6f7b8d)}.rasai-help-table small{color:var(--muted,#6f7b8d)}.rasai-help-technical{padding:11px 13px;border:1px solid var(--line,rgba(80,96,120,.18));border-radius:8px;background:#fafbfc}.rasai-help-technical summary{cursor:pointer;font-weight:750}
.rasai-fulfillment-banner{margin:10px 0!important;border-radius:9px!important;box-shadow:none}.rasai-fulfillment-final{color:var(--rasai-good)!important;background:var(--rasai-good-bg)}.rasai-fulfillment-preliminary{color:var(--rasai-warn)!important;background:var(--rasai-warn-bg)}
@media(max-width:760px){.rasai-analysis-status-main,.rasai-page-transparency{display:block}.rasai-status-badge{margin-top:10px}.rasai-dashboard-path{grid-template-columns:1fr}.rasai-help-grid{grid-template-columns:1fr}.rasai-help-open{width:100%;margin-top:10px}.rasai-help-dialog{width:calc(100vw - 18px);max-height:92vh}.rasai-help-dialog>*{margin-left:14px;margin-right:14px}.rasai-help-dialog-head{margin:0;padding-left:14px;padding-right:14px}}
@media print{.rasai-page-transparency,.rasai-help-dialog{display:none!important}.rasai-analysis-status{box-shadow:none}.rasai-dashboard-path{grid-template-columns:repeat(3,1fr)}}
</style>
"""

_SCRIPT = r"""
<script id='rasai-reader-experience-script-v1'>
(function(){'use strict';
  const openDialog=button=>{const id=button.getAttribute('data-dialog-id'),dialog=id&&document.getElementById(id);if(!dialog)return;if(typeof dialog.showModal==='function')dialog.showModal();else dialog.setAttribute('open','');};
  document.addEventListener('click',event=>{const open=event.target.closest&&event.target.closest('.rasai-help-open');if(open){openDialog(open);return;}const close=event.target.closest&&event.target.closest('.rasai-help-close');if(close){const dialog=close.closest('dialog');if(dialog&&typeof dialog.close==='function')dialog.close();else if(dialog)dialog.removeAttribute('open');}});
  document.querySelectorAll('.rasai-help-dialog').forEach(dialog=>dialog.addEventListener('click',event=>{if(event.target===dialog&&typeof dialog.close==='function')dialog.close();}));
})();
</script>
"""
