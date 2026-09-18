"""Catalog ownership, status and effective configuration."""
from rasai.catalog_report_presentation import *  # noqa: F401,F403
import json


def _plan_available(data: _ReportData) -> bool:
    return bool(
        data.configuration
        and data.config_hash
        and data.computed_hash
        and data.config_hash == data.computed_hash
    )


def _friendly_component(value: Any) -> str:
    key=_norm(value)
    return _COMPONENT_LABELS.get(key, str(value or "-").replace("_"," ").title())


def _friendly_service(value: Any) -> str:
    key=str(value or "")
    return _SERVICE_LABELS.get(key,_SERVICE_LABELS.get(key.casefold(),key.replace("_"," ").title() or "-"))


def _ai_policy(data: _ReportData, catalog_id: str) -> tuple[str,bool]:
    item=data.catalog_items.get(catalog_id,{})
    mode=str(item.get("ai_mode") or CATALOG_BY_ID[catalog_id].ai_mode or "NONE").upper()
    enabled=bool(item.get("ai_execution_enabled",False))
    label={"NONE":"Não utiliza IA","OPTIONAL":"IA opcional","REQUIRED":"IA obrigatória"}.get(mode,mode)
    return label,enabled


def _catalog_work(data: _ReportData, catalog_id: str) -> list[dict[str,Any]]:
    ownership={
        "CAT-01":set(),
        "CAT-02":set(),
        "CAT-03":{"SEMANTIC_AI"},
        "CAT-04":{"WEB_PERFORMANCE"},
        "CAT-05":{"SEARCH_INTELLIGENCE","GSC","AI_VISIBILITY","OBSERVABILITY"},
        "CAT-06":{"SYNTHETIC_APDEX"},
        "CAT-07":{"EXPERIENCE_APDEX","SYNTHETIC_UX_APDEX"},
        "CAT-08":{"IMPROVEMENT_INTELLIGENCE"},
        "CAT-09":{"CONTENT_REMEDIATION_AI","TECHNICAL_AI"},
    }[catalog_id]
    out=[]
    for row in data.work_items:
        comp=_norm(row.get("component"))
        if comp in ownership or any(comp.startswith(x+"_") for x in ownership):
            out.append(row)
    return out


def _catalog_source_specs(catalog_id: str) -> tuple[tuple[str,str],...]:
    return {
        "CAT-01":(
            ("standards_metric_observations","Métricas de padrões web"),
            ("standards_service_runs","Serviços de padrões web"),
            ("m24_diagnostics","Diagnósticos de descoberta"),
            ("page_snapshots","Capturas de navegador"),
        ),
        "CAT-02":(("web_performance_observations","Medições automatizadas de acessibilidade"),),
        "CAT-03":(
            ("entity_observations","Entidades identificadas"),
            ("semantic_assessments","Avaliações semânticas"),
            ("content_analysis_contexts","Contextos de conteúdo"),
        ),
        "CAT-04":(
            ("web_performance_runs","Execuções de desempenho web"),
            ("web_performance_attempts","Tentativas de coleta externa"),
            ("web_performance_observations","Medições de desempenho"),
        ),
        "CAT-05":(
            ("serp_observations","Observações de resultados de busca"),
            ("gsc_search_performance","Dados do Google Search Console"),
            ("generative_visibility_query_runs","Consultas de visibilidade em IA"),
            ("generative_visibility_page_citations","Citações observadas em IA"),
        ),
        "CAT-06":(
            ("synthetic_apdex_runs","Execuções do Apdex de navegação"),
            ("synthetic_apdex_samples","Amostras do Apdex de navegação"),
            ("synthetic_apdex_summaries","Resumo do Apdex de navegação"),
            ("synthetic_apdex_acquisitions","Aquisições sintéticas disponíveis"),
        ),
        "CAT-07":(
            ("synthetic_ux_apdex_runs","Execuções do Apdex de experiência"),
            ("synthetic_ux_apdex_samples","Amostras do Apdex de experiência"),
            ("synthetic_ux_apdex_summaries","Resumo do Apdex de experiência"),
            ("synthetic_apdex_acquisitions","Aquisições sintéticas disponíveis"),
        ),
        "CAT-08":(
            ("improvement_intelligence_runs","Execução da análise profunda"),
            ("improvement_intelligence_findings","Problemas correlacionados"),
            ("improvement_intelligence_recommendations","Melhorias recomendadas"),
        ),
        "CAT-09":(
            ("recommendations","Recomendações determinísticas"),
            ("root_cause_analyses","Análises de causa raiz"),
            ("content_remediation_suggestions","Sugestões de conteúdo"),
            ("jsonld_remediation_suggestions","Sugestões de dados estruturados"),
            ("improvement_intelligence_recommendations","Remediações da análise profunda"),
        ),
    }[catalog_id]


def _catalog_sources(database: Path, data: _ReportData, catalog_id: str) -> list[tuple[str,str,int]]:
    con=sqlite3.connect(database); con.row_factory=sqlite3.Row
    try:
        out=[]
        for table,label in _catalog_source_specs(catalog_id):
            count=_audit_count(con,table,data.audit_id)
            if count:
                out.append((table,label,count))
        if catalog_id=="CAT-03" and _table_exists(con,"rule_executions"):
            placeholders=",".join("?" for _ in _STRUCTURED_RULE_LABELS)
            rows=_rows(con,f"SELECT COUNT(*) FROM rule_executions WHERE audit_id=? AND rule_id IN ({placeholders})",(data.audit_id,*_STRUCTURED_RULE_LABELS.keys()))
            count=int(rows[0][0]) if rows else 0
            if count:
                out.append(("rule_executions (BR-GEO-034..037)","Validações de dados estruturados",count))
        return out
    finally:
        con.close()


def _explicit_run(database: Path, data: _ReportData, catalog_id: str) -> dict[str,Any]:
    table={
        "CAT-04":"web_performance_runs","CAT-06":"synthetic_apdex_runs","CAT-07":"synthetic_ux_apdex_runs",
        "CAT-08":"improvement_intelligence_runs","CAT-09":"content_remediation_runs",
    }.get(catalog_id)
    if not table:
        return {}
    con=sqlite3.connect(database); con.row_factory=sqlite3.Row
    try:
        return _last(con,table,data.audit_id)
    finally:
        con.close()


def _catalog_status(database: Path, data: _ReportData, catalog_id: str) -> tuple[str,str,str]:
    if not _plan_available(data):
        return "INDETERMINADO","warn","O snapshot do plano/configuração desta auditoria está ausente ou inválido; não é possível concluir se este catálogo foi ou não solicitado."
    if catalog_id not in data.selected:
        return "NÃO SOLICITADO","neutral","Este catálogo não fazia parte do plano congelado desta auditoria."
    if catalog_id=="CAT-05":
        con=sqlite3.connect(database); con.row_factory=sqlite3.Row
        try:
            row=con.execute("SELECT * FROM standards_service_runs WHERE audit_id=? AND service_id='common-crawl' ORDER BY rowid DESC LIMIT 1",(data.audit_id,)).fetchone() if _table_exists(con,"standards_service_runs") else None
        finally:
            con.close()
        if row is not None and bool(row["requested"]) and bool(row["effective_enabled"]):
            state=_norm(row["state"])
            attempted=int(row["targets_attempted"] or 0)
            details={}
            try:
                parsed=json.loads(str(row["details_json"] or "{}"))
                if isinstance(parsed,dict): details=parsed
            except (TypeError,ValueError,json.JSONDecodeError):
                pass
            reason=str(details.get("reason") or "")
            if state in {"ERROR","FAILED_RETRYABLE","FAILED_PERMANENT","BLOCKED"} or (attempted==0 and reason in {"PRE_SCORING_COLLECTION_STATE_NOT_FOUND","COMMON_CRAWL_PRESEAL_DATASET_MISSING"}):
                return "PARCIAL","warn","Search Intelligence possui evidência persistida, mas Common Crawl foi solicitado e não concluiu validamente a coleta planejada nesta AUD."
    run=_explicit_run(database,data,catalog_id)
    if run:
        raw=_norm(run.get("status"))
        if raw in {"COMPLETE_WITH_LIMITATIONS","COMPLETED_WITH_LIMITATIONS"} or "LIMITATION" in raw:
            return "PARCIAL","warn","A execução terminou com limitações e não deve ser apresentada como conclusão integral do catálogo."
        if raw in _STATUS_SUCCESS:
            return "CONCLUÍDO","good","A execução específica deste catálogo foi concluída e possui resultado persistido."
        if raw in _STATUS_FAILURE:
            return "FALHA","bad","A execução específica deste catálogo registrou falha. Consulte Execução e IA e integrações quando aplicável."
        if raw in _STATUS_PENDING:
            return "PARCIAL","warn","A execução específica deste catálogo foi persistida como parcial ou pendente."
    work=_catalog_work(data,catalog_id)
    if work:
        states={_norm(r.get("status")) for r in work}
        if states & _STATUS_FAILURE:
            return ("PARCIAL" if states & _STATUS_SUCCESS else "FALHA"),("warn" if states & _STATUS_SUCCESS else "bad"),"Há etapa(s) do catálogo com falha persistida."
        if states & _STATUS_PENDING:
            return "PARCIAL","warn","Há etapa(s) do catálogo ainda parcial(is) ou pendente(s)."
        if states & _STATUS_SUCCESS:
            return "CONCLUÍDO","good","As etapas próprias deste catálogo foram concluídas."
    sources=_catalog_sources(database,data,catalog_id)
    if sources:
        return "CONCLUÍDO","good","O catálogo possui evidências/resultados persistidos. Nem todo domínio funcional possui uma etapa de execução própria."
    return "SEM RESULTADO","warn","O catálogo foi solicitado, mas não há resultado reconhecido para esta projeção."


def _configuration_rows(data: _ReportData, catalog_id: str) -> list[Sequence[Any]]:
    item=data.catalog_items.get(catalog_id,{})
    policy,ai_enabled=_ai_policy(data,catalog_id)
    plan_available=_plan_available(data)
    rows=[
        ("Incluído nesta auditoria",("Sim" if catalog_id in data.selected else "Não") if plan_available else "Indeterminado - snapshot ausente/inválido","Plano congelado" if plan_available else "Snapshot da execução"),
        ("URL / alvo","; ".join(data.targets) if data.targets else "-","Plano congelado" if plan_available else "Evidência persistida"),
        ("Uso de IA nesta capacidade",("Habilitado" if ai_enabled else "Não habilitado") if policy!="Não utiliza IA" else "Não se aplica","Plano congelado" if plan_available else "Não determinável"),
        ("Política de IA",policy,"Catálogo"),
    ]
    settings=data.configuration.get("settings") if isinstance(data.configuration.get("settings"),Mapping) else {}
    if catalog_id=="CAT-04":
        cfg=settings.get("web_performance") if isinstance(settings,Mapping) else {}
        if isinstance(cfg,Mapping):
            rows.extend([
                ("Desempenho web","Habilitado" if str(cfg.get("enabled","")).lower()=="true" else "Desabilitado","Configuração da execução"),
                ("Fonte de dados de campo",cfg.get("field_source") or "Automática","Configuração da execução"),
                ("Categorias Lighthouse",str(cfg.get("lighthouse_categories") or "-").replace(","," · "),"Configuração da execução"),
            ])
    elif catalog_id=="CAT-05":
        search=data.configuration.get("search_intelligence")
        if isinstance(search,Mapping):
            queries=search.get("queries",[])
            rows.extend([
                ("Inteligência de busca / SERP","Habilitado" if bool(search.get("enabled")) else "Desabilitado","Plano congelado"),
                ("Consultas de busca","; ".join(str(v) for v in queries if str(v).strip()) if isinstance(queries,list) else str(queries or "-"),"Plano congelado"),
                ("Profundidade da busca",f"Top {search.get('depth','-')}","Plano congelado"),
                ("Dispositivo",_device_label(search.get("device")),"Plano congelado"),
                ("Região",search.get("region") or "Não definida","Plano congelado"),
            ])
    elif catalog_id=="CAT-06":
        cfg=settings.get("synthetic_apdex") if isinstance(settings,Mapping) else {}
        if isinstance(cfg,Mapping):
            rows.extend([
                ("Limite para experiência satisfatória",f"{cfg.get('threshold_seconds','-')} s","Configuração da execução"),
                ("Amostras por contexto",cfg.get("samples_per_context","-"),"Configuração da execução"),
                ("Máximo de tentativas",cfg.get("max_attempts_per_context","-"),"Configuração da execução"),
            ])
    elif catalog_id=="CAT-07":
        cfg=settings.get("synthetic_apdex_experience") if isinstance(settings,Mapping) else {}
        if isinstance(cfg,Mapping):
            rows.extend([
                ("Amostras por página",cfg.get("samples_per_page","-"),"Configuração da execução"),
                ("Limite satisfatório",f"{cfg.get('satisfied_seconds','-')} s","Configuração da execução"),
                ("Limite frustrado",f"{cfg.get('frustrated_seconds','-')} s","Configuração da execução"),
                ("Erros afetam o Apdex","Sim" if str(cfg.get("errors_affect_apdex","")).lower()=="true" else "Não","Configuração da execução"),
                ("Escopo de erros",_error_scope_label(cfg.get("error_scope")),"Configuração da execução"),
                ("Sessão",_session_label(cfg.get("session_mode")),"Configuração da execução"),
            ])
    elif catalog_id=="CAT-08":
        cfg=settings.get("improvement_intelligence") if isinstance(settings,Mapping) else {}
        if isinstance(cfg,Mapping):
            rows.extend([
                ("Domínios analisados"," · ".join(_domain_label(v) for v in str(cfg.get("domains") or "").split(",") if v.strip()) or "-","Configuração da execução"),
                ("Máximo de recomendações",cfg.get("max_recommendations","-"),"Configuração da execução"),
            ])
    elif catalog_id=="CAT-09":
        ai=settings.get("ai") if isinstance(settings,Mapping) else {}
        if isinstance(ai,Mapping):
            rows.extend([
                ("Enriquecimento de conteúdo","Habilitado" if str(ai.get("content_remediation","")).lower()=="true" else "Desabilitado","Configuração da execução"),
                ("Remediação técnica","Habilitada" if str(ai.get("technical_remediation","")).lower()=="true" else "Desabilitada","Configuração da execução"),
            ])
    if item.get("detail"):
        rows.append(("Condição registrada no plano",_plan_detail_label(item.get("detail")),"Plano congelado"))
    return rows


__all__ = [name for name in globals() if not name.startswith("__")]
