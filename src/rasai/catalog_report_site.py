"""Catalog report methodology, inventory and materialization entrypoint."""
from rasai.catalog_report_integrations import *  # noqa: F401,F403


def _methodology_body(data: _ReportData) -> str:
    versions=sorted({str(r.get("scoring_version")) for r in data.scores if r.get("scoring_version")})
    body=_audit_hero(data,"Metodologia e pontuação","Como distinguir observação, índice, interpretação e recomendação sem confundir medição com opinião de IA.")
    body+=_section("principles","Princípios de leitura","<div class='grid'><div class='card'><h3>Observação</h3><p>Fato capturado ou medido: HTTP, DOM, LCP, erro, arquivo, SERP.</p></div><div class='card'><h3>Índice</h3><p>Resultado agregado calculado por contrato, como SARI ou Apdex.</p></div><div class='card'><h3>Análise</h3><p>Interpretação/correlação persistida, determinística ou assistida por IA.</p></div><div class='card'><h3>Remediação</h3><p>Ação sugerida para corrigir ou melhorar um problema observado.</p></div></div>")
    body+=_section("scoring","Metodologia de pontuação persistida",f"<div class='metric-grid'>{_metric('Versão',', '.join(versions) or '—')}{_metric('Recalcula a pontuação?','Não')}{_metric('Fonte','Dados persistidos da auditoria')}</div>{_score_table(data)}")
    body+=_section("ai","IA e determinismo","<p>IA pode interpretar, correlacionar, priorizar e sugerir. Ela não escolhe pesos nem reescreve uma medição determinística nesta projeção.</p>")
    return body


def _metrics_body(database: Path, data: _ReportData) -> str:
    rows=[]
    for r in data.scores:
        dim=str(r.get("dimension") or "");label=_DIMENSION_LABELS.get(dim,dim.replace("_"," ").title())
        ctx="SARI" if dim=="OVERALL_READINESS" else _DIMENSION_CONTEXT.get(dim,"Metodologia")
        link="sari.html" if dim=="OVERALL_READINESS" else CATALOG_PAGE_BY_ID[ctx].filename if ctx in CATALOG_PAGE_BY_ID else "methodology.html"
        rows.append((_Html(f"<a href='{link}'>{escape(label)}</a>"),"Índice",_score_value(r),str(r.get("device") or "—").title(),"Índice persistido",r.get("scoring_version","—")))
    for cid in ("CAT-04","CAT-06","CAT-07"):
        for name,value,kind in _catalog_metrics(database,data,cid):
            rows.append((_Html(f"<a href='{CATALOG_PAGE_BY_ID[cid].filename}'>{escape(str(name))}</a>"),kind,value,CATALOG_BY_ID[cid].label,"Medição persistida","—"))
    definitions=(
        ("SARI","Índice","Prontidão agregada com cobertura, confiança e condições de validação."),
        ("Lighthouse","Índice","Pontuações laboratoriais por categoria quando coletadas."),
        ("LCP / INP / CLS","Métrica","Métricas de experiência/performance; o contexto diferencia laboratório e campo."),
        ("Apdex","Índice","Satisfação calculada a partir das amostras e limites persistidos."),
        ("SERP","Métrica","Posição observada em uma coleta de resultados de busca; não equivale à posição média do GSC."),
    )
    body=_audit_hero(data,"Índices e métricas","Inventário transversal dos números persistidos, com rótulos funcionais e referência ao catálogo proprietário.")
    body+=_section("inventory","Inventário desta auditoria",_table(("Indicador","Tipo","Valor","Contexto","Origem","Contrato"),rows,empty="Nenhum índice/métrica reconhecido foi persistido."))
    body+=_section("dictionary","Dicionário",_table(("Termo","Tipo","Como interpretar"),definitions))
    return body


def materialize_catalog_report_site(*, audit_id: str, workspace: Any) -> Path:
    """Materialize the independent ``report-catalog/`` tree and return its index."""
    report_dir=Path(workspace.root)/CATALOG_REPORT_DIR
    css_dir=report_dir/"css";css_dir.mkdir(parents=True,exist_ok=True)
    database=Path(workspace.database)
    data=_load_data(audit_id,database)
    (css_dir/"site.css").write_text(_CSS.strip()+"\n",encoding="utf-8",newline="\n")
    bodies={
        "index.html":_overview_body(database,data),
        "sari.html":_sari_body(data),
        "capture-context.html":_capture_context_body(database,data),
        "execution-evidence.html":_execution_evidence_body(database,data),
        "ai-integrations.html":_ai_integrations_body(database,data),
        "methodology.html":_methodology_body(data),
        "metrics.html":_metrics_body(database,data),
    }
    for catalog in CATALOGS:
        bodies[CATALOG_PAGE_BY_ID[catalog.id].filename]=_catalog_body(database,data,catalog.id)
    for page in CATALOG_REPORT_PAGES:
        body=bodies.get(page.filename)
        if body is None:
            body=_audit_hero(data,page.label,"Superfície sem projeção específica disponível.")
        (report_dir/page.filename).write_text(_shell(page,audit_id,body),encoding="utf-8",newline="\n")
    manifest={
        "contract":CATALOG_REPORT_CONTRACT_VERSION,
        "audit_id":audit_id,
        "source_of_truth":"audit.db + artifacts + secret-free execution snapshot",
        "catalog_report_dir":CATALOG_REPORT_DIR,
        "pages":[{"id":p.id,"filename":p.filename,"label":p.label,"catalog_id":p.catalog_id} for p in CATALOG_REPORT_PAGES],
        "principles":{"read_only":True,"modal_scope":"contextual-atomic","human_labels":True,"cross_catalog_reference_not_duplication":True},
    }
    (report_dir/"manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+"\n",encoding="utf-8",newline="\n")
    return report_dir/"index.html"

__all__ = [name for name in globals() if not name.startswith("__")]
