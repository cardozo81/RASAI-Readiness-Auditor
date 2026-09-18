"""Per-catalog external-use indicators, samples, analysis and remediation."""
from rasai.catalog_report_evidence import *  # noqa: F401,F403


def _integration_indicator(database: Path, data: _ReportData, catalog_id: str) -> str:
    con=sqlite3.connect(database); con.row_factory=sqlite3.Row
    try:
        labels=[]
        if catalog_id in {"CAT-02","CAT-04"}:
            for r in _audit_rows(con,"web_performance_attempts",data.audit_id):
                labels.append((_friendly_service(r.get("service")),_status_label(r.get("status"))))
        if catalog_id=="CAT-01":
            visible_services={"w3c-validator","w3c-css-validator","mdn-observatory","web-platform-baseline"}
            for r in _audit_rows(con,"standards_service_runs",data.audit_id):
                if r.get("requested") and str(r.get("service_id") or "") in visible_services:
                    labels.append((_friendly_service(r.get("service_id")),_status_label(r.get("state"))))
            for a in _ai_attempts(database,data.audit_id):
                if str(a.get("contract") or "").upper()=="M24-TECHNICAL-REMEDIATION-V2":
                    labels.append(("IA aplicada à remediação técnica da descoberta",_status_label(a.get("status"))))
        if catalog_id in {"CAT-03","CAT-08","CAT-09"}:
            for a in _ai_attempts(database,data.audit_id):
                if a.get("catalog_id")==catalog_id:
                    labels.append((a.get("purpose"),_status_label(a.get("status"))))
    finally:con.close()
    if not labels:return ""
    unique=[]
    for item in labels:
        if item not in unique:unique.append(item)
    pills="".join(f"<span class='ref'>{escape(str(name))} · {escape(str(state))}</span>" for name,state in unique)
    return f"<div class='notice'><strong>Recursos externos utilizados neste contexto:</strong><div class='pill-list'>{pills}</div><p class='muted'>Consumo, tentativas, custos, dados envolvidos e comunicação detalhada ficam centralizados em <a href='ai-integrations.html'>IA e integrações</a>.</p></div>"


def _technical_work_status(value: Any) -> str:
    raw=_norm(value)
    if raw in _STATUS_SUCCESS:return "Etapa concluída"
    if raw=="PARTIAL":return "Etapa parcial"
    if raw in _STATUS_PENDING:return "Etapa pendente"
    return _status_label(value)


def _work_execution_html(data: _ReportData, catalog_id: str) -> str:
    work=_catalog_work(data,catalog_id)
    rows=[];modals=[]
    for i,row in enumerate(work,1):
        mid=f"work-{catalog_id.lower()}-{i}"
        status=_technical_work_status(row.get("status"))
        rows.append((_friendly_component(row.get("component")),status,_attempt_count_label(row.get("attempt_count")),_modal_button(mid,"Ver execução")))
        modals.append(_modal(mid,_friendly_component(row.get("component")),f"Etapa técnica relacionada a {catalog_id}",
            _kv((("Conclusão da etapa",status),("Tentativas registradas na etapa",_attempt_count_label(row.get("attempt_count"))),("Escopo técnico",row.get("scope_key") or "-"),("Referência do resultado",row.get("effective_result_ref") or "-"),("Identificador",row.get("work_item_id") or "-")))))
    return _table(("Etapa","Conclusão técnica","Tentativas","Detalhe"),rows,empty="Este domínio não possui uma etapa de execução funcional própria; o estado é derivado de seu resultado persistido.")+"".join(modals)


def _apdex_samples_html(database: Path, data: _ReportData, *, experience: bool) -> str:
    table="synthetic_ux_apdex_samples" if experience else "synthetic_apdex_samples"
    con=sqlite3.connect(database); con.row_factory=sqlite3.Row
    try:samples=_audit_rows(con,table,data.audit_id)
    finally:con.close()
    samples=sorted(samples,key=lambda item:(str(item.get("captured_at") or ""),int(item.get("run_index") or 0)))
    rows=[];modals=[]
    for i,s in enumerate(samples,1):
        mid=("ux" if experience else "nav")+f"-sample-{i}"
        duration=s.get("kpm_value_ms") if experience else s.get("duration_ms")
        captured=s.get("captured_at") or "-"
        rows.append((s.get("run_index",i),captured,_device_label(s.get("device")),_classification_label(s.get("classification")),_fmt_number(duration,"ms"),_status_label(s.get("status")),_modal_button(mid,"Ver amostra")))
        if experience:
            fields=(
                ("Amostra",s.get("sample_id")),("Data/hora da medição",captured),("URL",s.get("url")),("URL final",s.get("final_url")),
                ("Classificação",_classification_label(s.get("classification"))),("Duração da ação",_fmt_number(s.get("user_action_duration_ms"),"ms")),
                ("Navegação",_fmt_number(s.get("navigation_duration_ms"),"ms")),("LCP",_fmt_number(s.get("lcp_ms"),"ms")),("CLS",s.get("cls")),
                ("Requisições XHR/fetch",s.get("xhr_fetch_count")),("Recursos dinâmicos",s.get("dynamic_resource_count")),
                ("Erros JavaScript",s.get("javascript_error_count")),("Erros de console",s.get("console_error_count")),
                ("Requisições com falha",s.get("request_failed_count")),("Falhas em recursos próprios",s.get("first_party_request_failed_count")),
                ("Respostas HTTP com erro",s.get("http_error_count")),("Rede estabilizada","Sim" if s.get("network_settled") else "Não"),
                ("Frustração forçada por erro","Sim" if s.get("error_forced_frustrated") else "Não"),("Erro",s.get("error_message") or s.get("error_code") or "-"),
            )
            note="<div class='notice'>Esta amostra persiste contagens de falhas por requisição. Quando a lista individual de URLs não faz parte do contrato da amostra, o relatório não inventa esse detalhe.</div>"
        else:
            fields=(("Amostra",s.get("sample_id")),("Data/hora da medição",captured),("URL",s.get("url")),("URL final",s.get("final_url")),("Classificação",_classification_label(s.get("classification"))),("Duração",_fmt_number(s.get("duration_ms"),"ms")),("HTTP",s.get("http_status")),("Perfil técnico",s.get("profile_id")),("Política de cache",_session_label(s.get("cache_policy"))),("Erro",s.get("error_message") or s.get("error_code") or "-"))
            diagnostics=_safe_json(s.get("browser_diagnostics"),{})
            note="<h3>Diagnóstico de navegador</h3><div class='pre'>"+escape(json.dumps(diagnostics,ensure_ascii=False,indent=2))+"</div>" if diagnostics else ""
        modals.append(_modal(mid,f"Amostra {s.get('run_index',i)}",f"{'Apdex de experiência' if experience else 'Apdex de navegação'} · {s.get('url') or '-'}",_kv(fields)+note))
    return _table(("Amostra","Data/hora","Dispositivo","Classificação","Duração","Medição","Detalhe"),rows,empty="Nenhuma amostra foi persistida para este Apdex.",sortable=bool(rows),page_size=10 if experience and len(rows)>10 else None)+"".join(modals)


def _improvement_html(database: Path, data: _ReportData) -> str:
    con=sqlite3.connect(database); con.row_factory=sqlite3.Row
    try:
        run=_last(con,"improvement_intelligence_runs",data.audit_id)
        findings=_audit_rows(con,"improvement_intelligence_findings",data.audit_id)
        recs=_audit_rows(con,"improvement_intelligence_recommendations",data.audit_id)
    finally:con.close()
    if not run:
        attempts=[a for a in _ai_attempts(database,data.audit_id) if str(a.get("contract") or "").upper()=="IMPROVEMENT-INTELLIGENCE-001"]
        if attempts:
            trace=[(a.get("provider") or "-",a.get("model") or "-",_status_label(a.get("status")),a.get("attempt_index") or "-") for a in attempts]
            return "<div class='notice bad'><strong>Resultado funcional ausente:</strong> existem tentativas de IA registradas para a análise profunda, mas o resultado consolidado não foi persistido. Isso é uma inconsistência de execução/persistência, não significa que a análise não tenha sido tentada. Consulte <a href='ai-integrations.html'>IA e integrações</a> para o diagnóstico.</div>"+_table(("Provedor","Modelo","Resultado da tentativa","Tentativa"),trace)
        return "<div class='notice warn'><strong>Análise profunda sem resultado:</strong> o catálogo foi solicitado, mas não há resultado funcional nem tentativa de IA reconhecida nesta auditoria. Consulte Evidências da execução para localizar a etapa que não foi produzida.</div>"
    rec_by_finding={str(r.get("finding_id")):r for r in recs}
    rows=[];modals=[]
    for i,f in enumerate(findings,1):
        rec=rec_by_finding.get(str(f.get("finding_id")))
        mid=f"improvement-{i}"
        source_cat=_DOMAIN_CATALOG.get(_norm(f.get("domain")))
        reference=_Html(f"<a class='ref' href='{CATALOG_PAGE_BY_ID[source_cat].filename}'>Origem: {source_cat}</a>") if source_cat in CATALOG_PAGE_BY_ID else "-"
        rows.append((f.get("title") or "Problema identificado",_level_label(f.get("severity")),_level_label(rec.get("priority") if rec else "-"),reference,_modal_button(mid,"Ver análise")))
        body=_kv((("Problema",f.get("observation") or f.get("title") or "-"),("Domínio",_domain_label(f.get("domain"))),("Severidade",_level_label(f.get("severity"))),("Fonte",f.get("source") or "-"),("Catálogo de origem",source_cat or "-")))
        if rec:
            body+="<h3>Melhoria recomendada</h3><p>"+escape(str(rec.get("recommendation") or rec.get("title") or "-"))+"</p>"
            body+="<p><a href='cat-09.html'>Ver remediação e detalhes de implementação no CAT-09</a></p>"
        modals.append(_modal(mid,f.get("title") or "Análise",f"Análise profunda · {source_cat or 'evidência transversal'}",body))
    intro=f"<div class='metric-grid'>{_metric('Problemas correlacionados',len(findings))}{_metric('Melhorias recomendadas',len(recs))}{_metric('Estado',_status_label(run.get('status')))}{_metric('Idioma da análise',run.get('analysis_language') or run.get('language') or '-')}</div>"
    summary=run.get("ai_summary") or run.get("summary")
    if summary:
        intro+=f"<div class='notice'><strong>Síntese da análise:</strong> {escape(str(summary))}</div>"
    return intro+_table(("Problema","Severidade","Prioridade","Referência","Detalhe"),rows,empty="A análise foi concluída sem materializar problemas correlacionados.",sortable=bool(rows),page_size=10 if len(rows)>10 else None)+"".join(modals)


def _rationale_parts(value: Any) -> dict[str,str]:
    text=str(value or "").strip()
    if not text:return {}
    labels={
        "degradação/risco atual":"risk","degradacao/risco atual":"risk",
        "benefício esperado se aplicado":"benefit","beneficio esperado se aplicado":"benefit",
        "justificativa técnica":"technical","justificativa tecnica":"technical",
    }
    parts={};current="technical";buffer=[]
    def flush():
        if buffer:
            parts[current]=" ".join(v.strip() for v in buffer if v.strip()).strip()
            buffer.clear()
    for line in text.splitlines():
        stripped=line.strip(); lower=stripped.casefold()
        matched=False
        for label,key in labels.items():
            prefix=label.casefold()+":"
            if lower.startswith(prefix):
                flush();current=key;buffer.append(stripped[len(prefix):].strip());matched=True;break
        if not matched:buffer.append(stripped)
    flush()
    return parts


def _m24_ai_guidance(database: Path, audit_id: str) -> tuple[list[dict[str,Any]],str]:
    con=sqlite3.connect(database);con.row_factory=sqlite3.Row
    try:run=_last(con,"m24_ai_results",audit_id)
    finally:con.close()
    if not run:return [],""
    payload=_read_json_artifact(database.parent,run.get("artifact_reference"))
    explanation=payload.get("explanation") if isinstance(payload,Mapping) and isinstance(payload.get("explanation"),Mapping) else {}
    actions=explanation.get("actions",[]) if isinstance(explanation,Mapping) else []
    policy=str(explanation.get("policy_note_pt") or "") if isinstance(explanation,Mapping) else ""
    return [dict(v) for v in actions if isinstance(v,Mapping)],policy


def _impact_summary(value: Any) -> str:
    impacts=_safe_json(value,{})
    if not isinstance(impacts,Mapping):return "-"
    labels={"accessibility":"Acessibilidade","ai_access":"Acesso por IA","best_practices":"Boas práticas","performance":"Performance","security":"Segurança","seo":"SEO"}
    active=[f"{labels.get(str(k),str(k).replace('_',' ').title())}: {v}" for k,v in impacts.items() if isinstance(v,(int,float)) and v>0]
    return " · ".join(active) or "Sem impacto adicional quantificado"


def _friendly_deterministic_title(row: Mapping[str,Any], root: Mapping[str,Any]) -> str:
    title=str(row.get("title") or "Correção")
    text=(title+" "+str(row.get("description") or "")+" "+str(root.get("cause_summary") or "")).casefold()
    if "robots.txt" in text and "aus" in text:return "Avaliar necessidade e política de robots.txt"
    if "sitemap" in text and "aus" in text:return "Avaliar publicação e localização do sitemap"
    return title


def _remediation_html(database: Path, data: _ReportData) -> str:
    con=sqlite3.connect(database); con.row_factory=sqlite3.Row
    try:
        roots=_audit_rows(con,"root_cause_analyses",data.audit_id)
        deterministic=_audit_rows(con,"recommendations",data.audit_id)
        content=_audit_rows(con,"content_remediation_suggestions",data.audit_id)
        jsonld=_audit_rows(con,"jsonld_remediation_suggestions",data.audit_id)
        deep=_audit_rows(con,"improvement_intelligence_recommendations",data.audit_id)
        deep_findings=_audit_rows(con,"improvement_intelligence_findings",data.audit_id)
    finally:con.close()
    ai_discovery,policy_note=_m24_ai_guidance(database,data.audit_id)
    rows=[];modals=[];idx=0
    root_by_find={str(r.get("finding_id")):r for r in roots}
    finding_by_id={str(r.get("finding_id")):r for r in deep_findings}

    # When technical AI produced a human-safe recommendation for discovery resources,
    # it is the primary CAT-09 representation. Deterministic fallback rows for the same
    # robots/sitemap corroboration are suppressed to avoid duplicate/conflicting advice.
    ai_codes={str(a.get("diagnostic_code") or "") for a in ai_discovery}
    suppressed_rules=set()
    if "M24-ROBOTS-ABSENT" in ai_codes:suppressed_rules.update({"BR-GEO-017","BR-GEO-056"})
    if "M24-SITEMAP-ABSENT" in ai_codes:suppressed_rules.update({"BR-GEO-003","BR-GEO-055"})

    for action in ai_discovery:
        idx+=1;mid=f"rem-discovery-{idx}"
        code=str(action.get("diagnostic_code") or "")
        objective=action.get("objective_pt") or "Orientação técnica de descoberta"
        rows.append((objective,"Informativa","CAT-01 → CAT-09 · IA técnica",_modal_button(mid,"Ver orientação")))
        body=_kv((("Objetivo",objective),("Como proceder",action.get("recommended_change_pt") or "-"),("Validação humana necessária","Sim" if action.get("human_validation_required") else "Não"),("Evidências",", ".join(str(v) for v in action.get("evidence_ids",[]) if str(v)) or "-")))
        body+="<div class='notice'><strong>Importante:</strong> ausência de robots.txt ou sitemap no caminho convencional não é convertida automaticamente em erro. A recomendação respeita o contexto e exige decisão operacional quando aplicável.</div>"
        modals.append(_modal(mid,str(objective),f"Orientação assistida por IA · evidência de descoberta {code or 'persistida'}",body))

    for r in deterministic:
        root=root_by_find.get(str(r.get("finding_id")),{})
        if str(root.get("rule_id") or "") in suppressed_rules:continue
        idx+=1;mid=f"rem-det-{idx}"
        title=_friendly_deterministic_title(r,root)
        rows.append((title,_level_label(r.get("priority_class")),"Determinística",_modal_button(mid,"Ver correção")))
        body=_kv((("Problema / objetivo",r.get("description") or root.get("cause_summary") or "-"),("Impacto",_level_label(r.get("impact"))),("Esforço",_level_label(r.get("effort"))),("Confiança",_confidence_label(r.get("confidence"))),("Problema de origem",r.get("finding_id") or "-")))
        if root:
            body+="<h3>Implementação sugerida</h3>"+_kv((("Mudança exata",root.get("exact_change") or "-"),("Exemplo após correção",root.get("example_after") or "-"),("Decisão humana necessária",root.get("human_decision_required") or "Não indicada"),("Critério de aceite",root.get("acceptance_criteria") or "-"),("Como revalidar",root.get("revalidation_steps") or "-")))
        modals.append(_modal(mid,title,"Remediação determinística derivada de problema persistido",body))

    for r in content:
        idx+=1;mid=f"rem-content-{idx}"
        rows.append((r.get("objective") or "Melhoria de conteúdo","-","IA · conteúdo",_modal_button(mid,"Ver sugestão")))
        body=_kv((("Objetivo",r.get("objective")),("Onde aplicar",r.get("target_location")),("Texto proposto",r.get("proposed_text")),("Confiança",_confidence_label(r.get("confidence"))),("Problema de origem",r.get("finding_id"))))
        modals.append(_modal(mid,r.get("objective") or "Sugestão de conteúdo","Conteúdo assistido por IA",body))

    for r in jsonld:
        idx+=1;mid=f"rem-jsonld-{idx}"
        rows.append(("Aprimorar dados estruturados","-","Dados estruturados",_modal_button(mid,"Ver JSON-LD")))
        proposed=_safe_json(r.get("proposed_json"),r.get("proposed_json"))
        body=_kv((("Situação",_status_label(r.get("status"))),("Tipos existentes",", ".join(_safe_json(r.get("existing_types"),[])) or "Nenhum"),("Melhorias",r.get("improvements") or "-")))
        body+="<h3>JSON-LD sugerido</h3><div class='pre'>"+escape(json.dumps(proposed,ensure_ascii=False,indent=2) if isinstance(proposed,(dict,list)) else str(proposed or "-"))+"</div>"
        modals.append(_modal(mid,"Dados estruturados","Sugestão persistida; exige revisão humana",body))

    for r in deep:
        idx+=1;mid=f"rem-deep-{idx}"
        title=r.get("title") or "Melhoria da análise profunda"
        source_cat=_DOMAIN_CATALOG.get(_norm(r.get("domain")))
        finding=finding_by_id.get(str(r.get("finding_id")),{})
        rows.append((title,_level_label(r.get("priority")),f"CAT-08 → {source_cat or 'evidência transversal'}",_modal_button(mid,"Ver implementação")))
        rationale=_rationale_parts(r.get("rationale"))
        problem=finding.get("observation") or finding.get("title") or "-"
        body=_kv((("Problema observado",problem),("Domínio",_domain_label(r.get("domain"))),("Severidade",_level_label(r.get("severity"))),("Prioridade",_level_label(r.get("priority"))),("Onde aplicar",r.get("selector") or "Não se aplica / não identificado"),("Como corrigir",r.get("recommendation") or "-"),("Risco de manter como está",rationale.get("risk") or r.get("rationale") or "-"),("Benefício esperado da correção",rationale.get("benefit") or "-"),("Justificativa técnica",rationale.get("technical") or "-"),("Impactos relacionados",_impact_summary(r.get("impacts_json"))),("Esforço",_level_label(r.get("effort"))),("Confiança",_confidence_label(r.get("confidence"))),("Problema de origem",r.get("finding_id") or "-")))
        if r.get("original_html"):
            body+="<h3>Trecho observado</h3><div class='pre'>"+escape(str(r.get("original_html")))+"</div>"
        if r.get("suggested_html"):
            body+="<h3>Exemplo após correção</h3><div class='pre'>"+escape(str(r.get("suggested_html")))+"</div>"
        if r.get("suggested_text"):
            body+="<h3>Texto sugerido</h3><div class='pre'>"+escape(str(r.get("suggested_text")))+"</div>"
        if r.get("verification"):
            body+="<h3>Como validar</h3><p>"+escape(str(r.get("verification")))+"</p>"
        evidence=_safe_json(r.get("evidence_ids_json"),[])
        if isinstance(evidence,list) and evidence:
            body+="<details><summary>Ver referências de evidência</summary><div class='detail-body'><p>"+escape(" · ".join(str(v) for v in evidence))+"</p></div></details>"
        modals.append(_modal(mid,title,f"Remediação da análise CAT-08 · origem {source_cat or 'transversal'}",body))

    lead=""
    if policy_note:
        lead="<div class='notice'><strong>Política para arquivos de descoberta:</strong> "+escape(policy_note)+"</div>"
    if rows:
        lead+=f"<div class='metric-grid'>{_metric('Correções e melhorias apresentadas',len(rows))}{_metric('Remediações da análise profunda',len(deep))}{_metric('Orientações técnicas de descoberta',len(ai_discovery))}</div>"
    return lead+_table(("Correção / melhoria","Prioridade","Origem","Detalhe"),rows,empty="Nenhuma remediação persistida para esta auditoria.",sortable=bool(rows),page_size=10 if len(rows)>10 else None)+"".join(modals)


__all__ = [name for name in globals() if not name.startswith("__")]
