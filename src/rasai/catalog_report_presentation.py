"""Human-facing labels and shared visual helpers."""
from rasai.catalog_report_model import *  # noqa: F401,F403
from rasai.time_contract import localize_html_timestamps


def _status_label(value: Any) -> str:
    raw=_norm(value)
    mapping={
        "SUCCESS":"Concluído","COMPLETE":"Concluído","COMPLETED":"Concluído","FINAL":"Concluído",
        "READY":"Disponível","AVAILABLE":"Disponível","PARTIAL":"Parcial","FAILED_RETRYABLE":"Falha reprocessável",
        "FAILED_PERMANENT":"Falha permanente","FAILED_FATAL":"Falha","ERROR":"Erro","CONTRACT_ERROR":"Erro de resposta contratual",
        "BLOCKED":"Bloqueado","DISABLED":"Desabilitado","NOT_REQUESTED":"Não solicitado","NOT_APPLICABLE":"Não aplicável",
        "ABSENT":"Não encontrado","UNAVAILABLE":"Sem dados disponíveis","RUNNING":"Em execução","PENDING":"Pendente",
        "NOT_DETERMINABLE":"Não determinável com os dados desta auditoria","UNKNOWN":"Não determinado",
        "COMPLETE_WITH_LIMITATIONS":"Concluído com limitações",
    }
    return mapping.get(raw, str(value or "—").replace("_"," ").title())


def _device_label(value: Any) -> str:
    raw=_norm(value)
    return {"MOBILE":"Dispositivo móvel","DESKTOP":"Desktop","TABLET":"Tablet"}.get(raw,str(value or "—").replace("_"," ").title())


def _classification_label(value: Any) -> str:
    raw=_norm(value)
    return {"SATISFIED":"Satisfatória","TOLERATING":"Tolerável","FRUSTRATED":"Frustrada"}.get(raw,str(value or "—").replace("_"," ").title())


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
    return {"ALL":"Todos os erros observados","FIRST_PARTY":"Somente recursos do próprio domínio","OWNER":"Somente recursos do próprio domínio"}.get(raw,str(value or "—").replace("_"," ").title())


def _score_impact_label(value: Any) -> str:
    raw=_norm(value)
    return {"NONE":"Sem impacto direto na pontuação","BOUNDED_AI_RESOURCE_ASSESSMENT":"Avaliação limitada e vinculada a evidências","NON_SCORING":"Não participa da pontuação"}.get(raw,str(value or "—").replace("_"," ").title())


def _domain_label(value: Any) -> str:
    raw=_norm(value)
    return {
        "ACCESSIBILITY":"Acessibilidade","PERFORMANCE":"Performance","SEMANTICS_STRUCTURE":"Estrutura semântica",
        "CONTENT":"Conteúdo","SEARCH_RANKING":"Busca e posicionamento","FILES_DISCOVERY":"Arquivos de descoberta",
        "TECHNICAL_HTML":"HTML e estrutura técnica","BEST_PRACTICES":"Boas práticas","SECURITY":"Segurança passiva",
        "AI_ACCESS":"Acesso por agentes de IA",
    }.get(raw,str(value or "—").replace("_"," ").title())


def _capability_label(value: Any) -> str:
    raw=str(value or "")
    return {
        "domain-discovery":"Descoberta e acesso técnico","standards":"Padrões e compatibilidade web",
        "accessibility":"Acessibilidade","content-suggestions":"Conteúdo, semântica e dados estruturados",
        "web-performance":"Web Performance","search-intelligence":"Inteligência de busca / SERP",
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
    note_html=f"<small>{escape(note)}</small>" if note else ""
    return f"<div class='metric'><small>{escape(label)}</small><strong>{escape(_plain(value) or '—')}</strong>{note_html}</div>"


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
    head="".join(f"<th>{escape(str(h))}</th>" for h in headers)
    body="".join("<tr>"+"".join(f"<td>{cell if isinstance(cell,_Html) else escape(_plain(cell))}</td>" for cell in row)+"</tr>" for row in rows)
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
        pairs.append(f"<dt>{escape(label)}</dt><dd>{value if isinstance(value,_Html) else escape(_plain(value) or '—')}</dd>")
    return "<dl class='kv'>"+"".join(pairs)+"</dl>"


def _modal(modal_id: str, title: str, context: str, body: str) -> str:
    return f"""<dialog id='{escape(modal_id)}' class='rasai-modal'><div class='modal-head'><div><h2>{escape(title)}</h2><p>{escape(context)}</p></div><button class='modal-close' type='button' data-modal-close aria-label='Fechar'>Fechar</button></div><div class='modal-body'>{body}</div></dialog>"""


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
        rows.append((_DIMENSION_LABELS.get(dim,dim.replace("_"," ").title()),_device_label(row.get("device")),_score_value(row),row.get("coverage","—"),_confidence_label(row.get("confidence")),_status_label(row.get("consolidation_status")),row.get("scoring_version","—")))
    return _table(("Indicador","Contexto","Valor","Cobertura","Confiança","Consolidação","Método"),rows)


__all__ = [name for name in globals() if not name.startswith("__")]
