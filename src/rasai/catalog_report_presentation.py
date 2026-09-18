"""Human-facing labels and shared visual helpers."""
from rasai.catalog_report_model import *  # noqa: F401,F403
from rasai.time_contract import localize_html_timestamps
from rasai.catalog_report_public_labels import public_label

_EMPTY = "-"
_RICH_TOKEN_RE = re.compile(
    r"(\[[^\]\n]+\]\(https?://[^)\s]+\)|`[^`\n]+`|https?://[^\s<>()]+)",
    re.I,
)

def _translated_text(pt_br: Any, original: Any) -> _Html:
    translated = str(pt_br or _EMPTY).replace("—", "-")
    source = str(original or "").strip()
    if not source or translated.casefold() == source.casefold():
        return _Html(escape(translated))
    return _Html(
        escape(translated)
        + " <span class='translation-mark' title='"
        + escape(source, quote=True)
        + "' aria-label='Rótulo amigável; valor interno: "
        + escape(source, quote=True)
        + "'>🌐</span>"
    )

def _internal_value_label(value: Any) -> _Html | None:
    raw = str(value or "").strip()
    label = public_label(raw)
    return _translated_text(label, raw) if label else None

def _rich_text(value: Any) -> _Html:
    if isinstance(value, _Html):
        return value
    text = str(value or "").strip()
    if not text or text == "—":
        return _Html(_EMPTY)
    internal = _internal_value_label(text)
    if internal is not None:
        return internal
    out: list[str] = []
    cursor = 0
    for match in _RICH_TOKEN_RE.finditer(text):
        out.append(escape(text[cursor:match.start()]))
        token = match.group(0)
        markdown = re.fullmatch(r"\[([^\]\n]+)\]\((https?://[^)\s]+)\)", token, re.I)
        if markdown:
            label, href = markdown.group(1), markdown.group(2)
            out.append(
                "<a class='external-link' href='" + escape(href, quote=True)
                + "' target='_blank' rel='noopener noreferrer'>"
                + escape(label) + " ↗</a>"
            )
        elif token.startswith("`") and token.endswith("`"):
            out.append("<code>" + escape(token[1:-1]) + "</code>")
        else:
            href = token
            trailing = ""
            while href and href[-1] in ".,;:":
                trailing = href[-1] + trailing
                href = href[:-1]
            out.append(
                "<a class='external-link' href='" + escape(href, quote=True)
                + "' target='_blank' rel='noopener noreferrer'>"
                + escape(href) + " ↗</a>" + escape(trailing)
            )
        cursor = match.end()
    out.append(escape(text[cursor:]))
    return _Html("".join(out).replace("\n", "<br>"))

def _display_value(value: Any) -> _Html:
    return value if isinstance(value, _Html) else _rich_text(value)

def _temporal_mode_label(value: Any) -> _Html:
    return _internal_value_label(value) or _rich_text(value)



def _status_label(value: Any) -> str:
    raw=_norm(value)
    mapping={
        "SUCCESS":"Concluído","COMPLETE":"Concluído","COMPLETED":"Concluído","FINAL":"Concluído",
        "READY":"Disponível","AVAILABLE":"Disponível","MEASURED":"Medido","GENERATED":"Gerado","CONSOLIDATED":"Consolidado",
        "PASS":"Aprovado","FAIL":"Não aprovado","WARNING":"Atenção","INFO":"Informativo",
        "PARTIAL":"Parcial","FAILED_RETRYABLE":"Falha reprocessável","FAILED_PERMANENT":"Falha permanente",
        "FAILED_FATAL":"Falha fatal","FAILURE":"Falha","ERROR":"Erro","TECHNICAL_ERROR":"Erro técnico",
        "CONTRACT_ERROR":"Erro de resposta contratual","BLOCKED":"Bloqueado","DISABLED":"Desabilitado",
        "NOT_REQUESTED":"Não solicitado","REQUESTED_NOT_EXECUTED":"Solicitado, não executado","NOT_CONFIGURED":"Não configurado",
        "NOT_APPLICABLE":"Não aplicável","SKIPPED":"Ignorado","ABSENT":"Não encontrado","UNAVAILABLE":"Sem dados disponíveis",
        "NO_DATA":"Sem dados","INCOMPLETE":"Incompleto","PRELIMINARY":"Preliminar","VALID":"Válido","EXPIRED":"Expirado",
        "RUNNING":"Em execução","PENDING":"Pendente","PROCESSING":"Em processamento","WAITING_FOR_DATA":"Aguardando dados",
        "NOT_DETERMINABLE":"Não determinável com os dados desta auditoria","UNKNOWN":"Não determinado",
        "COMPLETE_WITH_LIMITATIONS":"Concluído com limitações","COMPLETED_WITH_LIMITATIONS":"Concluído com limitações",
        "APPLICATION_ERROR":"Erro da aplicação","INVALID_SAMPLE":"Amostra inválida","BROWSER_UNAVAILABLE":"Navegador indisponível",
        "TIMEOUT":"Tempo limite excedido","NAVIGATION_ERROR":"Erro de navegação",
    }
    mapped=public_label(value)
    return mapping.get(raw, mapped or str(value or _EMPTY).replace("_"," ").title())


def _assessment_label(value: Any) -> str:
    raw=_norm(value)
    return {
        "PASS":"Aprovado",
        "FAIL":"Não aprovado",
        "GOOD":"Bom",
        "NEEDS_IMPROVEMENT":"Precisa melhorar",
        "POOR":"Ruim",
        "NOT_APPLICABLE":"Não aplicável",
        "UNAVAILABLE":"Sem dados disponíveis",
        "INCOMPLETE":"Incompleto",
    }.get(raw,_status_label(value))


def _device_label(value: Any) -> str:
    raw=_norm(value)
    return {"MOBILE":"Dispositivo móvel","DESKTOP":"Desktop","TABLET":"Tablet"}.get(raw,str(value or _EMPTY).replace("_"," ").title())


def _classification_label(value: Any) -> str:
    raw=_norm(value)
    return {"SATISFIED":"Satisfatória","TOLERATING":"Tolerável","FRUSTRATED":"Frustrada"}.get(raw,str(value or _EMPTY).replace("_"," ").title())


def _level_label(value: Any) -> str:
    raw=_norm(value)
    return {
        "CRITICAL":"Crítica","VERY_HIGH":"Muito alta","HIGH":"Alta","MEDIUM":"Média","LOW":"Baixa","VERY_LOW":"Muito baixa",
        "INFO":"Informativa","WARNING":"Atenção","P1":"Prioridade 1","P2":"Prioridade 2","P3":"Prioridade 3","P4":"Prioridade 4",
    }.get(raw,str(value or "—").replace("_"," ").title())


def _confidence_label(value: Any) -> str:
    raw=_norm(value)
    if raw in {"HIGH","MEDIUM","LOW","VERY_HIGH","VERY_LOW"}:
        return _level_label(value)
    if raw in {"UNAVAILABLE","NOT_AVAILABLE"}:
        return "Sem dados para estimar"
    if raw in {"NOT_APPLICABLE","N/A"}:
        return "Não aplicável"
    if raw in {"UNKNOWN","NOT_DETERMINABLE"}:
        return "Não determinada"
    try:
        number=float(value)
        return f"{number*100:.0f}%" if 0<=number<=1 else f"{number:g}"
    except (TypeError,ValueError):
        return str(value or "—").replace("_"," ")


def _session_label(value: Any) -> str:
    raw=_norm(value)
    return {"COLD":"Sessão nova, sem reaproveitamento","WARM":"Sessão reutilizada","COLD_CONTEXT":"Contexto novo, sem reaproveitamento de cache","WARM_CONTEXT":"Contexto com reaproveitamento"}.get(raw,str(value or "—").replace("_"," ").title())


def _error_scope_label(value: Any) -> str:
    raw=_norm(value)
    return {
        "ALL":"Todos os erros observados",
        "FIRST_PARTY":"Somente falhas atribuídas a recursos do próprio domínio; erros de console/JavaScript sem origem confiável permanecem diagnósticos",
        "OWNER":"Somente falhas atribuídas a recursos do próprio domínio",
        "NAVIGATION":"Somente erro da ação/navegação principal",
    }.get(raw,str(value or "—").replace("_"," ").title())


def _score_impact_label(value: Any) -> str:
    raw=_norm(value)
    return {"NONE":"Sem impacto direto na pontuação","BOUNDED_AI_RESOURCE_ASSESSMENT":"Avaliação limitada e vinculada a evidências","NON_SCORING":"Não participa da pontuação"}.get(raw,str(value or "—").replace("_"," ").title())


def _domain_label(value: Any) -> str:
    raw=_norm(value)
    return {
        "ACCESSIBILITY":"Acessibilidade","PERFORMANCE":"Desempenho","SEMANTICS_STRUCTURE":"Estrutura semântica",
        "CONTENT":"Conteúdo","SEARCH_RANKING":"Busca e posicionamento","FILES_DISCOVERY":"Arquivos de descoberta",
        "TECHNICAL_HTML":"HTML e estrutura técnica","BEST_PRACTICES":"Boas práticas","SECURITY":"Segurança passiva",
        "AI_ACCESS":"Acesso por agentes de IA",
    }.get(raw,str(value or "—").replace("_"," ").title())


def _capability_label(value: Any) -> str:
    raw=str(value or "")
    return {
        "domain-discovery":"Descoberta e acesso técnico","standards":"Padrões e compatibilidade web",
        "accessibility":"Acessibilidade","content-suggestions":"Conteúdo, semântica e dados estruturados",
        "web-performance":"Desempenho web","search-intelligence":"Inteligência de busca / SERP",
        "google-search-console":"Google Search Console","ai-visibility":"Visibilidade em respostas de IA",
        "observability":"Observabilidade externa","apdex-navigation":"Apdex de navegação",
        "apdex-experience":"Apdex de experiência","deep-analysis":"Análise profunda e melhorias",
        "remediation":"Remediações",
    }.get(raw,raw.replace("-"," ").replace("_"," ").title() or "—")


def _plan_detail_label(value: Any) -> str:
    text=str(value or "").strip()
    match=re.fullmatch(r"mix=mobile=(\d+(?:\.\d+)?)",text,re.I)
    if match:
        return f"Distribuição de dispositivos: {match.group(1)}% mobile"
    return text.replace("_"," ") if text else "—"


def _attempt_count_label(value: Any) -> str:
    try:
        number=int(value)
    except (TypeError,ValueError):
        return str(value or "—")
    return "Não contabilizada neste item" if number==0 else str(number)


def _tone_for_status(value: Any) -> str:
    raw=_norm(value)
    if raw in _STATUS_FAILURE or any(t in raw for t in ("FAIL","ERROR","BLOCK")):
        return "bad"
    if raw in _STATUS_PENDING or any(t in raw for t in ("PARTIAL","LIMIT","PENDING")):
        return "warn"
    if raw in _STATUS_SUCCESS or any(t in raw for t in ("SUCCESS","COMPLETE","CONCLU")):
        return "good"
    return "neutral"


def _badge(text: str, tone: str|None=None) -> str:
    return f"<span class='badge {escape(tone or _tone_for_status(text))}'>{escape(text)}</span>"


def _metric(label: str, value: Any, note: str="") -> str:
    note_html=f"<small>{escape(note.replace('—','-'))}</small>" if note else ""
    return f"<div class='metric'><small>{escape(label.replace('—','-'))}</small><strong>{_display_value(value)}</strong>{note_html}</div>"


def _table(
    headers: Sequence[str],
    rows: Sequence[Sequence[Any]],
    *,
    empty: str="Sem dados disponíveis para este contexto.",
    sortable: bool=False,
    page_size: int|None=None,
) -> str:
    if not rows:
        return f"<div class='notice'>{escape(empty)}</div>"
    head="".join(f"<th>{escape(str(h).replace('—','-'))}</th>" for h in headers)
    body="".join("<tr>"+"".join(f"<td>{_display_value(cell)}</td>" for cell in row)+"</tr>" for row in rows)
    interactive=bool(sortable or page_size)
    attrs=""
    if interactive:
        attrs=" data-interactive-table='true'"
        attrs+=f" data-sortable='{'true' if sortable else 'false'}'"
        if page_size:
            attrs+=f" data-page-size='{max(1,int(page_size))}'"
    table=f"<div class='table-wrap'><table{attrs}><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>"
    if page_size:
        table+="<div class='table-controls'><button type='button' data-table-prev>Página anterior</button><span class='table-page-info'></span><button type='button' data-table-next>Próxima página</button></div>"
    return table


def _kv(items: Sequence[tuple[str,Any]]) -> str:
    pairs=[]
    for label,value in items:
        pairs.append(f"<dt>{escape(label.replace('—','-'))}</dt><dd>{_display_value(value)}</dd>")
    return "<dl class='kv'>"+"".join(pairs)+"</dl>"


def _modal(modal_id: str, title: str, context: str, body: str) -> str:
    return f"""<dialog id='{escape(modal_id)}' class='rasai-modal'><div class='modal-head'><div><h2>{escape(title.replace('—','-'))}</h2><p>{escape(context.replace('—','-'))}</p></div><button class='modal-close' type='button' data-modal-close aria-label='Fechar'>Fechar</button></div><div class='modal-body'>{body}</div></dialog>"""


def _modal_button(modal_id: str, label: str="Ver detalhes") -> _Html:
    return _Html(f"<button type='button' class='action' data-modal-open='{escape(modal_id)}'>{escape(label)}</button>")


def _section(section_id: str, title: str, body: str, kicker: str="") -> str:
    k=f"<div class='kicker'>{escape(kicker)}</div>" if kicker else ""
    return f"<section id='{escape(section_id)}' class='panel'>{k}<h2>{escape(title)}</h2>{body}</section>"


def _outline(items: Sequence[tuple[str,str]]) -> str:
    return "<nav class='outline' aria-label='Atalhos desta página'>"+"".join(f"<a href='#{escape(a)}'>{escape(l)}</a>" for a,l in items)+"</nav>"


def _navigation(current: str) -> str:
    out=[]; group=None
    for page in CATALOG_REPORT_PAGES:
        if page.group != group:
            out.append(f"<div class='nav-group'>{escape(page.group)}</div>"); group=page.group
        active=" active" if page.filename==current else ""
        aria=" aria-current='page'" if active else ""
        out.append(f"<a class='{active.strip()}' href='{escape(page.filename)}'{aria}>{escape(page.label)}</a>")
    return "".join(out)


def _shell(page: CatalogReportPage, audit_id: str, body: str) -> str:
    html=f"""<!doctype html><html lang='pt-BR'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>{escape(page.label)} · RASAi</title><link rel='stylesheet' href='css/site.css'></head><body data-report-contract='{CATALOG_REPORT_CONTRACT_VERSION}' data-page='{escape(page.id)}'><aside class='app-nav' data-shared-report-menu='{CATALOG_REPORT_CONTRACT_VERSION}'><div class='brand'><small>RASAi · relatório por catálogos</small><strong>{escape(audit_id)}</strong></div><nav aria-label='Relatórios'>{_navigation(page.filename)}</nav></aside><main class='app-main'>{body}<footer class='footer'>Projeção somente para leitura de dados persistidos · {CATALOG_REPORT_CONTRACT_VERSION} · nenhuma coleta, integração, IA ou cálculo de pontuação é executado pelo HTML.</footer></main><script>{_JS}</script></body></html>"""
    return localize_html_timestamps(html)


def _audit_state(data: _ReportData) -> str:
    if data.fulfillment:
        return _status_label(data.fulfillment.get("processing_status"))
    return _status_label(data.audit.get("completion_status") or data.audit.get("status"))


def _audit_hero(data: _ReportData, title: str, subtitle: str) -> str:
    target=data.targets[0] if data.targets else "—"
    project=str(data.audit.get("project_name") or "—")
    return f"<header class='hero'><div class='eyebrow'>Auditoria {escape(data.audit_id)}</div><h1>{escape(title)}</h1><p>{escape(subtitle)}</p><div class='metric-grid'>{_metric('URL auditada',target)}{_metric('Projeto',project)}{_metric('Resultado da execução',_audit_state(data))}{_metric('Catálogos selecionados',len(data.selected))}</div></header>"


def _score_value(row: Mapping[str,Any]) -> str:
    try:
        return f"{float(row.get('value')):.1f}"
    except (TypeError,ValueError):
        return _plain(row.get("value")) or "—"


def _score_table(data: _ReportData, *, include_overall: bool=True, context: str|None=None) -> str:
    rows=[]
    for row in sorted(data.scores,key=lambda x:(str(x.get("device","")),str(x.get("dimension","")))):
        dim=str(row.get("dimension") or "")
        if not include_overall and dim=="OVERALL_READINESS":
            continue
        if context and _DIMENSION_CONTEXT.get(dim)!=context:
            continue
        consolidation=_norm(row.get("consolidation_status"))
        structured_absent=(dim=="STRUCTURED_DATA" and consolidation=="NOT_APPLICABLE" and row.get("value") is None)
        value="Não aplicável" if structured_absent else _score_value(row)
        confidence="Não aplicável - nenhum dado estruturado foi observado" if structured_absent else _confidence_label(row.get("confidence"))
        rows.append((_DIMENSION_LABELS.get(dim,dim.replace("_"," ").title()),_device_label(row.get("device")),value,row.get("coverage","—"),confidence,_status_label(row.get("consolidation_status")),row.get("scoring_version","—")))
    return _table(("Indicador","Contexto","Valor","Cobertura","Confiança","Consolidação","Método"),rows)


__all__ = [name for name in globals() if not name.startswith("__")]
