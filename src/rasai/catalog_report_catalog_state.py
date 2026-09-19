"""Catalog ownership, status and effective configuration."""
from rasai.catalog_report_presentation import *  # noqa: F401,F403
from rasai.configuration_value_labels import (
    configuration_csv_report,
    configuration_value_report,
)
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
        "CAT-10":{"PASSIVE_SECURITY"},
    }[catalog_id]
    if catalog_id=="CAT-10" and bool(data.catalog_items.get("CAT-10",{}).get("ai_execution_enabled",False)):
        # CAT-10 owns the deterministic passive-security run and, when explicitly
        # requested, also depends on the canonical Improvement Intelligence SECURITY
        # advisory. This keeps requested-but-not-executed AI visible to status/assurance.
        ownership.add("IMPROVEMENT_INTELLIGENCE")
    out=[]
    for row in data.work_items:
        comp=_norm(row.get("component"))
        if comp in ownership or any(comp.startswith(x+"_") for x in ownership):
            out.append(row)
    return out


def _catalog_source_specs(catalog_id: str) -> tuple[tuple[str,str],...]:
    """Relevant persisted sources that must remain visible in the catalog provenance."""
    return {
        "CAT-01":(
            ("standards_metric_observations","Métricas de padrões web"),
            ("standards_service_runs","Serviços de padrões web"),
            ("m24_runs","Execução dos diagnósticos técnicos"),
            ("m24_diagnostics","Diagnósticos de descoberta"),
            ("page_snapshots","Capturas de navegador"),
        ),
        "CAT-02":(
            ("web_performance_attempts","Tentativas Lighthouse/PageSpeed"),
            ("web_performance_observations","Medições automatizadas de acessibilidade"),
            ("element_observations","Elementos observados"),
            ("finding_element_observations","Vínculos entre achados e elementos"),
        ),
        "CAT-03":(
            ("entity_observations","Entidades identificadas"),
            ("semantic_assessments","Avaliações semânticas"),
            ("semantic_coherence_assessments","Coerência semântica por página"),
            ("semantic_property_signals","Sinais semânticos da propriedade"),
            ("property_semantic_summaries","Resumo de coerência da propriedade"),
            ("content_analysis_contexts","Contextos de conteúdo"),
            ("property_semantic_contexts","Contexto semântico da propriedade"),
            ("content_context_interpretations","Interpretações contextuais de IA"),
            ("semantic_corpus_manifests","Manifesto do corpus semântico"),
        ),
        "CAT-04":(
            ("web_performance_runs","Execuções de desempenho web"),
            ("web_performance_attempts","Tentativas de coleta externa"),
            ("web_performance_observations","Medições de desempenho"),
            ("lighthouse_execution_profiles","Perfil efetivo do Lighthouse"),
        ),
        "CAT-05":(
            ("serp_observations","Observações de resultados de busca"),
            ("serp_evidence_provenance","Provenance das observações SERP"),
            ("serp_competitive_analyses","Comparações competitivas determinísticas"),
            ("serp_competitive_results","Classificações competitivas"),
            ("serp_competitive_pages","Páginas públicas comparadas"),
            ("serp_competitive_ai_analyses","Análises competitivas por IA"),
            ("gsc_search_performance","Dados do Google Search Console"),
            ("generative_visibility_query_runs","Consultas de visibilidade em IA"),
            ("generative_visibility_page_citations","Citações observadas em IA"),
        ),
        "CAT-06":(
            ("synthetic_apdex_runs","Execuções do Apdex de navegação"),
            ("synthetic_apdex_samples","Amostras do Apdex de navegação"),
            ("synthetic_apdex_summaries","Resumo do Apdex de navegação"),
            ("synthetic_apdex_acquisition_runs","Execuções de aquisição sintética"),
            ("synthetic_apdex_acquisitions","Aquisições sintéticas disponíveis"),
        ),
        "CAT-07":(
            ("synthetic_ux_apdex_runs","Execuções do Apdex de experiência"),
            ("synthetic_ux_apdex_samples","Amostras do Apdex de experiência"),
            ("synthetic_ux_apdex_summaries","Resumo do Apdex de experiência"),
            ("synthetic_ux_apdex_error_details","Erros detalhados observados na experiência"),
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
            ("root_cause_precision","Precisão e provenance das causas"),
            ("content_remediation_suggestions","Sugestões de conteúdo"),
            ("jsonld_remediation_suggestions","Sugestões de dados estruturados"),
            ("request_remediation_ai","Remediações de falhas de requisição"),
            ("request_remediation_evidence","Evidências de remediação de requisições"),
            ("recommendation_governance","Decisões de governança das recomendações"),
            ("remediation_groups","Agrupamentos de remediação"),
            ("improvement_intelligence_recommendations","Remediações da análise profunda"),
        ),
        "CAT-10":(
            ("passive_security_runs","Execução da segurança passiva"),
            ("passive_security_resources","Inventário de scripts, recursos, forms e iframes"),
            ("passive_security_components","Componentes e versões identificáveis"),
            ("passive_security_integrations","Estado de OSV, CISA KEV e fontes reutilizadas"),
            ("passive_security_advisories","Advisories e CVEs correlacionados"),
            ("passive_security_findings","Findings determinísticos/externos"),
            ("passive_security_remediations","Plano de remediação de segurança"),
            ("web_performance_observations","Lighthouse Best Practices reutilizado"),
            ("standards_service_runs","MDN HTTP Observatory reutilizado"),
            ("page_snapshots","Runtime e snapshots reutilizados"),
        ),
    }[catalog_id]

def _catalog_source_count(connection: sqlite3.Connection, table: str, audit_id: str) -> int:
    direct=_audit_count(connection,table,audit_id)
    if direct:
        return direct
    if not _table_exists(connection,table):
        return 0
    if table=="finding_element_observations" and _table_exists(connection,"element_observations"):
        rows=_rows(
            connection,
            """SELECT COUNT(*) FROM finding_element_observations feo
               JOIN element_observations eo
                 ON eo.element_observation_id=feo.element_observation_id
               WHERE eo.audit_id=?""",
            (audit_id,),
        )
        return int(rows[0][0]) if rows else 0
    if table=="page_snapshots" and _table_exists(connection,"pages"):
        rows=_rows(
            connection,
            """SELECT COUNT(*) FROM page_snapshots ps
               JOIN pages p ON p.page_id=ps.page_id
               WHERE p.audit_id=?""",
            (audit_id,),
        )
        return int(rows[0][0]) if rows else 0
    if table in {"serp_competitive_results","serp_competitive_pages"} and _table_exists(connection,"serp_competitive_analyses"):
        rows=_rows(
            connection,
            f"""SELECT COUNT(*) FROM {table} child
                JOIN serp_competitive_analyses parent
                  ON parent.observation_id=child.observation_id
                WHERE parent.audit_id=?""",
            (audit_id,),
        )
        return int(rows[0][0]) if rows else 0
    return 0


def _catalog_sources(database: Path, data: _ReportData, catalog_id: str) -> list[tuple[str,str,int]]:
    con=sqlite3.connect(database); con.row_factory=sqlite3.Row
    try:
        out=[]
        for table,label in _catalog_source_specs(catalog_id):
            count=_catalog_source_count(con,table,data.audit_id)
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
        "CAT-10":"passive_security_runs",
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
    sources=_catalog_sources(database,data,catalog_id)

    # CAT-10 has a canonical consolidated run. Preparatory inventory/integration rows
    # are useful evidence, but they cannot by themselves mean that the catalog finished.
    if catalog_id=="CAT-10" and not run:
        states={_norm(r.get("status")) for r in work}
        if states & _STATUS_FAILURE:
            return (
                ("PARCIAL" if sources or states & _STATUS_SUCCESS else "FALHA"),
                ("warn" if sources or states & _STATUS_SUCCESS else "bad"),
                "Há evidência preparatória do CAT-10, mas a execução consolidada não foi persistida e existe etapa dependente com falha."
                if sources
                else "A execução consolidada do CAT-10 não foi persistida e existe etapa dependente com falha.",
            )
        if states & _STATUS_PENDING:
            return "PARCIAL","warn","O CAT-10 possui etapa dependente parcial/pendente, mas não possui execução consolidada persistida."
        if sources:
            return "PARCIAL","warn","O CAT-10 possui evidências preparatórias persistidas, mas não possui execução consolidada em passive_security_runs."
        return "SEM RESULTADO","warn","O CAT-10 foi solicitado, mas não há execução consolidada nem evidência preparatória reconhecida."

    if work:
        states={_norm(r.get("status")) for r in work}
        if states & _STATUS_FAILURE:
            return ("PARCIAL" if states & _STATUS_SUCCESS else "FALHA"),("warn" if states & _STATUS_SUCCESS else "bad"),"Há etapa(s) do catálogo com falha persistida."
        if states & _STATUS_PENDING:
            return "PARCIAL","warn","Há etapa(s) do catálogo ainda parcial(is) ou pendente(s)."
        if states & _STATUS_SUCCESS:
            return "CONCLUÍDO","good","As etapas próprias deste catálogo foram concluídas."
    if sources:
        return "CONCLUÍDO","good","O catálogo possui evidências/resultados persistidos. Nem todo domínio funcional possui uma etapa de execução própria."
    return "SEM RESULTADO","warn","O catálogo foi solicitado, mas não há resultado reconhecido para esta projeção."


def _configuration_rows(data: _ReportData, catalog_id: str) -> list[Sequence[Any]]:
    item=data.catalog_items.get(catalog_id,{})
    policy,ai_enabled=_ai_policy(data,catalog_id)
    plan_available=_plan_available(data)
    cat05_competitive_ai=False
    if catalog_id=="CAT-05":
        search_cfg=data.configuration.get("search_intelligence")
        if isinstance(search_cfg,Mapping):
            raw=search_cfg.get("ai_competitive")
            cat05_competitive_ai=raw is True or str(raw).strip().casefold() in {"1","true","yes","on","sim"}
        if not cat05_competitive_ai:
            for work in getattr(data,"work_items",()):
                if _norm(work.get("component"))!="SEARCH_INTELLIGENCE":
                    continue
                raw_cfg=work.get("configuration")
                try:
                    parsed=json.loads(raw_cfg) if isinstance(raw_cfg,str) else raw_cfg
                except (TypeError,ValueError,json.JSONDecodeError):
                    parsed={}
                if isinstance(parsed,Mapping):
                    raw=parsed.get("ai_competitive")
                    cat05_competitive_ai=raw is True or str(raw).strip().casefold() in {"1","true","yes","on","sim"}
                if cat05_competitive_ai:
                    break
    ai_usage=("Habilitado para inteligência competitiva" if cat05_competitive_ai else (("Habilitado" if ai_enabled else "Não habilitado") if policy!="Não utiliza IA" else "Não se aplica"))
    ai_policy=("IA competitiva opcional e evidence-bound" if cat05_competitive_ai else policy)
    rows=[
        ("Incluído nesta auditoria",("Sim" if catalog_id in data.selected else "Não") if plan_available else "Indeterminado - snapshot ausente/inválido","Plano congelado" if plan_available else "Snapshot da execução"),
        ("URL / alvo","; ".join(data.targets) if data.targets else "-","Plano congelado" if plan_available else "Evidência persistida"),
        ("Uso de IA nesta capacidade",ai_usage,"Plano congelado / Search Intelligence" if cat05_competitive_ai else ("Plano congelado" if plan_available else "Não determinável")),
        ("Política de IA",ai_policy,"Search Intelligence" if cat05_competitive_ai else "Catálogo"),
    ]
    settings=data.configuration.get("settings") if isinstance(data.configuration.get("settings"),Mapping) else {}
    if catalog_id=="CAT-03":
        environment=settings.get("environment") if isinstance(settings,Mapping) else {}
        if isinstance(environment,Mapping):
            content_fields=(
                ("Perfil de risco","RASAI_CONTENT_RISK_PROFILE"),
                ("Categoria YMYL","RASAI_YMYL_CATEGORY"),
                ("Propósito da página","RASAI_PAGE_PURPOSE"),
                ("Público pretendido","RASAI_INTENDED_AUDIENCE"),
                ("Requisito de experiência","RASAI_EXPERIENCE_REQUIREMENT"),
                ("Sensibilidade à atualização","RASAI_FRESHNESS_SENSITIVITY"),
                ("Origem do conteúdo","RASAI_CONTENT_ORIGIN"),
            )
            for label,name in content_fields:
                raw=environment.get(name)
                if raw in (None,""):
                    continue
                value=configuration_value_report(name, raw)
                rows.append((label,value,"Plano congelado / configuração efetiva"))
    elif catalog_id=="CAT-04":
        cfg=settings.get("web_performance") if isinstance(settings,Mapping) else {}
        if isinstance(cfg,Mapping):
            rows.extend([
                ("Desempenho web","Habilitado" if str(cfg.get("enabled","")).lower()=="true" else "Desabilitado","Configuração da execução"),
                (
                    "Fonte de dados de campo",
                    configuration_value_report(
                        "RASAI_WEB_PERFORMANCE_FIELD_SOURCE",
                        cfg.get("field_source") or "auto",
                    ),
                    "Configuração da execução",
                ),
                (
                    "Categorias Lighthouse",
                    configuration_csv_report(
                        "RASAI_LIGHTHOUSE_CATEGORIES",
                        cfg.get("lighthouse_categories") or "",
                    ),
                    "Configuração da execução",
                ),
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
    elif catalog_id=="CAT-10":
        environment=settings.get("environment") if isinstance(settings,Mapping) else {}
        if isinstance(environment,Mapping):
            fields=(
                ("Segurança passiva","RASAI_PASSIVE_SECURITY"),
                ("Headers / CSP / CORS","RASAI_SECURITY_HEADERS"),
                ("Cookies","RASAI_SECURITY_COOKIES"),
                ("Scripts / recursos","RASAI_SECURITY_RESOURCES"),
                ("Third-party","RASAI_SECURITY_THIRD_PARTY"),
                ("Correlação runtime","RASAI_SECURITY_RUNTIME_CORRELATION"),
                ("OSV","RASAI_SECURITY_OSV"),
                ("CISA KEV","RASAI_SECURITY_CISA_KEV"),
                ("Timeout externo (s)","RASAI_SECURITY_EXTERNAL_TIMEOUT_SECONDS"),
            )
            for label,name in fields:
                raw=environment.get(name)
                if raw not in (None,""):
                    rows.append((label,public_label(raw) or str(raw),"Plano congelado / configuração efetiva"))
        rows.append(("MDN HTTP Observatory","Reutilizado da configuração canônica de padrões; não há configuração paralela no CAT-10","Arquitetura do catálogo"))
    if item.get("detail"):
        rows.append(("Condição registrada no plano",_plan_detail_label(item.get("detail")),"Plano congelado"))
    return rows


__all__ = [name for name in globals() if not name.startswith("__")]
