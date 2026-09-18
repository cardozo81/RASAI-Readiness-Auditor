"""Capture context, overview, SARI and execution governance pages."""
from rasai.catalog_report_page import *  # noqa: F401,F403


def _capture_context_body(database: Path, data: _ReportData) -> str:
    snaps=_capture_snapshots(database,data.audit_id)
    rows=[];modals=[]
    for i,s in enumerate(snaps,1):
        meta=_safe_json(s.get("browser_metadata"),{})
        profile=meta.get("profile") if isinstance(meta,Mapping) and isinstance(meta.get("profile"),Mapping) else {}
        browser=meta.get("browser_identity") if isinstance(meta,Mapping) and isinstance(meta.get("browser_identity"),Mapping) else {}
        viewport=profile.get("viewport") if isinstance(profile,Mapping) and isinstance(profile.get("viewport"),Mapping) else {}
        runtime=_runtime_items(s)
        mid=f"capture-{i}"
        rows.append((_device_label(s.get("device")),s.get("requested_url") or s.get("page_url") or "-",s.get("final_url") or "-",s.get("http_status") or "-",len(runtime),_modal_button(mid,"Ver captura")))
        visual_ref=meta.get("visual_artifact_ref") if isinstance(meta,Mapping) else None
        visual_path=_artifact_path(database.parent,visual_ref)
        artifact_rows=[
            ("Resposta HTTP",s.get("raw_artifact_ref") or "-"),("HTML renderizado",s.get("rendered_artifact_ref") or "-"),
            ("Conteúdo principal",s.get("main_content_ref") or "-"),("Dados estruturados",s.get("structured_data_ref") or "-"),
            ("Captura visual",visual_ref or "-"),
        ]
        body=_kv((("Identificador da página",s.get("page_id")),("Identificador da captura",s.get("snapshot_id")),("URL solicitada",s.get("requested_url") or s.get("page_url")),("URL final",s.get("final_url")),("Capturado em",s.get("captured_at")),("HTTP",s.get("http_status")),("Tipo de conteúdo",s.get("content_type")),("Renderização",s.get("rendering_mode")),("Arquitetura",s.get("architecture_classification")),("Dispositivo",_device_label(s.get("device"))),("Perfil",browser.get("descriptor") or profile.get("device") or "-"),("Área visível (viewport)",f"{viewport.get('width','-')} × {viewport.get('height','-')}"),("Escala de pixels (DPR)",profile.get("device_scale_factor") or "-"),("Navegador",f"{browser.get('channel','Chrome')} {browser.get('browser_version') or meta.get('browser_version','-')}"),("Idioma",browser.get("locale") or profile.get("locale") or "-"),("Diagnósticos da execução do navegador",len(runtime))))
        body+="<h3>Arquivos e evidências</h3>"+_table(("Arquivo / evidência","Referência"),artifact_rows)
        if visual_path is not None and visual_ref:
            href="../"+str(visual_ref).replace("\\","/")
            body+="<h3>Captura visual</h3><p class='muted'>Imagem persistida no momento da captura; não é reconstruída pelo relatório.</p>"
            body+=f"<a class='capture-link' href='{escape(href)}' target='_blank' rel='noopener'><img class='capture-preview' src='{escape(href)}' alt='Captura visual da página auditada em {_device_label(s.get('device'))}'></a>"
        elif visual_ref:
            body+="<div class='notice warn'>A referência da captura visual foi persistida, mas o arquivo não está disponível junto aos artefatos desta cópia da auditoria.</div>"
        modals.append(_modal(mid,"Captura da página",f"{_device_label(s.get('device'))} · {s.get('final_url') or s.get('requested_url') or '-'}",body))
    body=_audit_hero(data,"Captura e contexto","Como a página foi capturada: URL, dispositivo, navegador, renderização e artefatos. Diagnósticos funcionais permanecem no catálogo responsável.")
    body+=_outline((("capture","Capturas"),("boundaries","Responsabilidades"),("technical","Detalhes técnicos")))
    body+=_section("capture","Capturas da auditoria",_table(("Dispositivo","URL solicitada","URL final","HTTP","Diagnósticos","Detalhe"),rows,empty="Nenhuma captura de navegador persistida.",sortable=bool(rows))+"".join(modals))
    body+=_section("boundaries","Responsabilidades","<div class='grid'><div class='card'><h3>Captura e contexto</h3><p>Identifica a captura, navegador, dispositivo, área visível, URL e arquivos de evidência.</p></div><div class='card'><h3>CAT-01</h3><p>Exibe erros/alertas do navegador e problemas técnicos observados.</p><p><a href='cat-01.html'>Abrir CAT-01</a></p></div><div class='card'><h3>CAT-06 / CAT-07</h3><p>Exibem suas próprias amostras sintéticas; não duplicam a captura base.</p></div></div>")
    body+=_section("technical","Detalhes técnicos","<details><summary>Como interpretar os identificadores</summary><div class='detail-body'><p>O identificador da página localiza o alvo auditado; o identificador da captura localiza uma execução específica por dispositivo/contexto. Os CATs referenciam esses identificadores sem criar cópias dos artefatos.</p></div></details>")
    return body


def _overview_body(database: Path, data: _ReportData) -> str:
    rows=[]
    for catalog in CATALOGS:
        status,tone,detail=_catalog_status(database,data,catalog.id)
        page=CATALOG_PAGE_BY_ID[catalog.id]
        rows.append((_Html(f"<a href='{escape(page.filename)}'><strong>{escape(catalog.id)} · {escape(catalog.label)}</strong></a>"),_Html(_badge(status,tone)),detail))
    indexes=[]
    for r in data.scores:
        dim=str(r.get("dimension") or "")
        label=_DIMENSION_LABELS.get(dim,dim.replace("_"," ").title())
        ctx="SARI" if dim=="OVERALL_READINESS" else _DIMENSION_CONTEXT.get(dim,"")
        link="sari.html" if dim=="OVERALL_READINESS" else CATALOG_PAGE_BY_ID[ctx].filename if ctx in CATALOG_PAGE_BY_ID else "metrics.html"
        indexes.append((_Html(f"<a href='{link}'>{escape(label)}</a>"),_score_value(r),_device_label(r.get("device")),"Índice",_confidence_label(r.get("confidence"))))
    for cid in ("CAT-04","CAT-06","CAT-07"):
        for name,value,kind in _catalog_metrics(database,data,cid):
            indexes.append((_Html(f"<a href='{CATALOG_PAGE_BY_ID[cid].filename}'>{escape(str(name))}</a>"),value,CATALOG_BY_ID[cid].label,kind,"-"))
    integrity="Íntegro" if data.config_hash and data.computed_hash==data.config_hash else "Plano não encontrado" if not data.config_hash else "Integridade divergente"
    body=_audit_hero(data,"Visão geral por catálogos","Resumo do plano congelado e dos resultados persistidos, mantendo coleta, análise e remediação em responsabilidades distintas.")
    body+=_outline((("catalogs","Catálogos"),("indices","Índices"),("integrity","Integridade")))
    body+=_section("catalogs","Catálogos da auditoria",_table(("Catálogo","Estado","Interpretação"),rows,sortable=True))
    body+=_section("indices","Índices e métricas evidentes",_table(("Indicador","Valor","Contexto","Tipo","Confiança"),indexes,empty="Nenhum índice ou métrica reconhecido foi persistido.",sortable=bool(indexes))+"<p class='muted'>O inventário metodológico completo está em <a href='metrics.html'>Índices e métricas</a>.</p>")
    body+=_section("integrity","Integridade e proveniência",f"<div class='metric-grid'>{_metric('Plano da execução',integrity)}{_metric('Fonte de verdade','Dados persistidos da auditoria')}{_metric('Contrato do relatório',CATALOG_REPORT_CONTRACT_VERSION)}</div><div class='notice'>O relatório organiza dados já persistidos. Ele não executa nova captura, integração, IA ou cálculo de pontuação.</div>")
    return body


def _sari_body(data: _ReportData) -> str:
    overall=[r for r in data.scores if _norm(r.get("dimension"))=="OVERALL_READINESS"]
    cards="".join(_metric(f"SARI · {_device_label(r.get('device'))}",_score_value(r),f"Cobertura {r.get('coverage','-')} · Confiança {_confidence_label(r.get('confidence'))}") for r in overall)
    limitations=[]
    for r in overall:
        parsed=_safe_json(r.get("limitations"),[])
        for item in parsed if isinstance(parsed,list) else []:
            limitations.append((_device_label(r.get("device")),str(item).replace("_"," ")))
    versions=sorted({str(r.get("scoring_version")) for r in data.scores if r.get("scoring_version")})
    body=_audit_hero(data,"SARI · Search & AI Readiness Index","Índice persistido de prontidão, com cobertura, confiança, dimensões e limitações. O HTML não recalcula o SARI.")
    body+=_outline((("result","Resultado"),("composition","Composição"),("limitations","Limitações"),("method","Método")))
    body+=_section("result","Resultado geral",f"<div class='metric-grid'>{cards or _metric('SARI','Sem pontuação persistida')}</div><div class='notice'>O valor deve ser lido junto de cobertura, confiança e condições de validação persistidas.</div>")
    body+=_section("composition","Composição e dimensões",_score_table(data,include_overall=False))
    body+=_section("limitations","Limitações e gates persistidos",_table(("Contexto","Limitação / gate"),limitations,empty="Nenhuma limitação serializada foi encontrada."))
    body+=_section("method","Metodologia aplicada",f"<div class='metric-grid'>{_metric('Versão da metodologia',', '.join(versions) or '-')}{_metric('Fonte do valor','Pontuação persistida da auditoria')}{_metric('Recalcula no HTML?','Não')}</div><p>Pesos, fórmulas e condições de validação pertencem à metodologia persistida. Consulte <a href='methodology.html'>Metodologia e pontuação</a>.</p>")
    return body


def _execution_evidence_body(database: Path, data: _ReportData) -> str:
    rows=[]
    for c in CATALOGS:
        status,tone,detail=_catalog_status(database,data,c.id)
        rows.append((c.id,c.label,"Sim" if c.id in data.selected else "Não",_Html(_badge(status,tone)),detail))
    integrity="Íntegro" if data.config_hash and data.computed_hash==data.config_hash else "Plano não encontrado" if not data.config_hash else "Integridade divergente"
    work_rows=[];modals=[]
    for i,r in enumerate(data.work_items,1):
        mid=f"fulfillment-{i}"
        work_status=_technical_work_status(r.get("status"))
        work_rows.append((_friendly_component(r.get("component")),work_status,_attempt_count_label(r.get("attempt_count")),_modal_button(mid,"Ver etapa")))
        modals.append(_modal(mid,_friendly_component(r.get("component")),"Etapa técnica persistida da execução",_kv((("Conclusão da etapa",work_status),("Tentativas registradas na etapa",_attempt_count_label(r.get("attempt_count"))),("Obrigatória","Sim" if r.get("required") else "Não"),("Escopo técnico",r.get("scope_key") or "-"),("Resultado",r.get("effective_result_ref") or "-"),("Último erro",r.get("last_error_message") or r.get("last_error_code") or "-"),("Identificador",r.get("work_item_id") or "-")))))
    body=_audit_hero(data,"Evidências da execução","O que foi solicitado, o estado funcional de cada catálogo e as etapas técnicas persistidas.")
    body+=_outline((("matrix","Plano × execução"),("integrity","Plano congelado"),("technical","Etapas técnicas")))
    body+=_section("matrix","Plano × execução",_table(("Catálogo","Contexto","Selecionado","Estado funcional","Interpretação"),rows,sortable=True))
    body+=_section("integrity","Plano congelado",f"<div class='metric-grid'>{_metric('Integridade',integrity)}{_metric('Catálogos selecionados',len(data.selected))}{_metric('Etapas técnicas persistidas',len(data.work_items))}{_metric('Resultado lógico',_audit_state(data))}</div><p class='muted'>Ausência de plano é estado indeterminado; nunca é convertida em “não solicitado”.</p>")
    body+=_section("technical","Etapas técnicas",_table(("Etapa","Conclusão técnica","Tentativas","Detalhe"),work_rows,empty="Nenhuma etapa técnica persistida.",sortable=bool(work_rows))+"".join(modals)+"<p class='muted'>Conclusão técnica indica se a etapa executou. O estado funcional do catálogo pode permanecer parcial quando a própria metodologia considera a cobertura insuficiente, como em um grupo Apdex pequeno.</p>")
    return body


__all__ = [name for name in globals() if not name.startswith("__")]
