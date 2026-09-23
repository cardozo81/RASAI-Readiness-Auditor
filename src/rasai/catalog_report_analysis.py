"""Per-catalog external-use indicators, samples, analysis and remediation."""
from rasai.catalog_report_evidence import *  # noqa: F401,F403


def _integration_indicator(database: Path, data: _ReportData, catalog_id: str) -> str:
    con=sqlite3.connect(database); con.row_factory=sqlite3.Row
    try:
        labels=[]
        if catalog_id in {"CAT-02","CAT-04"}:
            for r in _audit_rows(con,"web_performance_attempts",data.audit_id):
                if catalog_id=="CAT-02" and _norm(r.get("service"))!="PAGESPEED_INSIGHTS":
                    continue
                labels.append((_friendly_service(r.get("service")),_status_label(r.get("status"))))
        if catalog_id=="CAT-01":
            visible_services={"w3c-validator","w3c-css-validator","mdn-observatory","web-platform-baseline"}
            for r in _audit_rows(con,"standards_service_runs",data.audit_id):
                if r.get("requested") and str(r.get("service_id") or "") in visible_services:
                    labels.append((_friendly_service(r.get("service_id")),_status_label(r.get("state"))))
            for a in _ai_attempts(database,data.audit_id):
                if str(a.get("contract") or "").upper()=="M24-TECHNICAL-REMEDIATION-V2":
                    labels.append(("IA aplicada à remediação técnica da descoberta",_status_label(a.get("status"))))
        if catalog_id in {"CAT-03","CAT-08","CAT-09","CAT-10"}:
            for a in _ai_attempts(database,data.audit_id):
                if a.get("catalog_id")==catalog_id:
                    labels.append((a.get("purpose"),_status_label(a.get("status"))))
        if catalog_id=="CAT-10":
            for r in _audit_rows(con,"passive_security_integrations",data.audit_id):
                integration=str(r.get("integration_id") or "")
                labels.append((_friendly_service(integration),_status_label(r.get("state"))))
    finally:con.close()
    if not labels:return ""
    unique=[]
    for item in labels:
        if item not in unique:unique.append(item)
    pills="".join(f"<span class='ref'>{escape(str(name))} · {_display_value(state)}</span>" for name,state in unique)
    return f"<div class='notice'><strong>Recursos externos utilizados neste contexto:</strong><div class='pill-list'>{pills}</div><p class='muted'>Consumo, tentativas, custos, dados envolvidos e comunicação detalhada ficam centralizados em <a href='ai-integrations.html'>IA e integrações</a>.</p></div>"


def _technical_work_status(value: Any) -> str:
    raw=_norm(value)
    if raw in _STATUS_SUCCESS:return "Etapa concluída"
    if raw=="PARTIAL":return "Etapa parcial"
    if raw=="REQUESTED_NOT_EXECUTED":return "Solicitado, não executado"
    if raw=="NOT_CONFIGURED":return "Não configurada - reprocessamento necessário"
    if raw=="WAITING_FOR_DATA":return "Aguardando pré-requisitos"
    if raw in _STATUS_PENDING:return "Etapa pendente"
    return _status_label(value)


def _work_execution_html(data: _ReportData, catalog_id: str) -> str:
    work=_catalog_work(data,catalog_id)
    rows=[];modals=[]
    for i,row in enumerate(work,1):
        mid=f"work-{catalog_id.lower()}-{i}"
        status=_technical_work_status(row.get("status"))
        status_display=_state_text(row.get("status"),status)
        rows.append((_friendly_component(row.get("component")),status_display,_attempt_count_label(row.get("attempt_count")),_modal_button(mid,"Ver execução")))
        detail_items=(
            ("Conclusão da etapa",status_display),
            ("Tentativas registradas na etapa",_attempt_count_label(row.get("attempt_count"))),
        )
        if catalog_id!="CAT-10":
            detail_items+=(
                ("Escopo técnico",row.get("scope_key") or "-"),
                ("Referência do resultado",row.get("effective_result_ref") or "-"),
                ("Identificador",row.get("work_item_id") or "-"),
            )
        modals.append(_modal(
            mid,
            _friendly_component(row.get("component")),
            f"Etapa técnica relacionada a {catalog_id}",
            _kv(detail_items),
        ))
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
        classification=_state_text(s.get("classification"),_classification_label(s.get("classification")))
        measurement=_state_text(s.get("status"),_status_label(s.get("status")))
        rows.append((s.get("run_index",i),captured,_device_label(s.get("device")),classification,_fmt_number(duration,"ms"),measurement,_modal_button(mid,"Ver amostra")))
        if experience:
            fields=(
                ("Amostra",s.get("sample_id")),("Data/hora da medição",captured),("URL",s.get("url")),("URL final",s.get("final_url")),
                ("Classificação",classification),("Duração da ação",_fmt_number(s.get("user_action_duration_ms"),"ms")),
                ("Navegação",_fmt_number(s.get("navigation_duration_ms"),"ms")),("LCP",_fmt_number(s.get("lcp_ms"),"ms")),("CLS",s.get("cls")),
                ("Requisições XHR/fetch",s.get("xhr_fetch_count")),("Recursos dinâmicos",s.get("dynamic_resource_count")),
                ("Erros JavaScript",s.get("javascript_error_count")),("Erros de console",s.get("console_error_count")),
                ("Requisições com falha",s.get("request_failed_count")),("Falhas em recursos próprios",s.get("first_party_request_failed_count")),
                ("Respostas HTTP com erro",s.get("http_error_count")),("Rede estabilizada","Sim" if s.get("network_settled") else "Não"),
                ("Frustração forçada por erro","Sim" if s.get("error_forced_frustrated") else "Não"),("Erro",s.get("error_message") or s.get("error_code") or "-"),
            )
            note="<div class='notice'>Esta amostra persiste contagens de falhas por requisição. Quando a lista individual de URLs não faz parte do contrato da amostra, o relatório não inventa esse detalhe.</div>"
        else:
            fields=(("Amostra",s.get("sample_id")),("Data/hora da medição",captured),("URL",s.get("url")),("URL final",s.get("final_url")),("Classificação",classification),("Duração",_fmt_number(s.get("duration_ms"),"ms")),("HTTP",s.get("http_status")),("Perfil técnico",s.get("profile_id")),("Política de cache",_session_label(s.get("cache_policy"))),("Erro",s.get("error_message") or s.get("error_code") or "-"))
            diagnostics=_safe_json(s.get("browser_diagnostics"),{})
            note="<h3>Diagnóstico de navegador</h3><div class='pre'>"+escape(json.dumps(diagnostics,ensure_ascii=False,indent=2))+"</div>" if diagnostics else ""
        modals.append(_modal(mid,f"Amostra {s.get('run_index',i)}",f"{'Apdex de experiência' if experience else 'Apdex de navegação'} · {s.get('url') or '-'}",_kv(fields)+note))
    return _table(("Amostra","Data/hora","Dispositivo","Classificação","Duração","Medição","Detalhe"),rows,empty="Nenhuma amostra foi persistida para este Apdex.",sortable=bool(rows),page_size=10 if experience and len(rows)>10 else None)+"".join(modals)



def _ux_profile_execution_html(database: Path, data: _ReportData) -> str:
    """Aggregate persisted CAT-07 attempts by URL, device and technical profile."""
    con=sqlite3.connect(database); con.row_factory=sqlite3.Row
    try:
        samples=_audit_rows(con,"synthetic_ux_apdex_samples",data.audit_id)
        summaries=_audit_rows(con,"synthetic_ux_apdex_summaries",data.audit_id)
    finally:
        con.close()
    if not samples:
        return "<div class='notice'>Nenhuma tentativa de Apdex de experiência foi persistida nesta auditoria.</div>"

    summary_by_key={}
    for item in summaries:
        device=_norm(item.get("device"))
        if device=="POPULATION":
            continue
        key=(str(item.get("url") or ""),device,str(item.get("profile_id") or ""))
        summary_by_key[key]=item

    grouped={}
    for item in samples:
        key=(
            str(item.get("url") or ""),
            _norm(item.get("device")),
            str(item.get("profile_id") or ""),
        )
        grouped.setdefault(key,[]).append(item)

    def distribution(values, labeler=lambda value:value):
        counts={}
        for raw in values:
            key=str(raw if raw not in (None,"") else "sem resposta")
            counts[key]=counts.get(key,0)+1
        return "; ".join(f"{labeler(key)} ×{counts[key]}" for key in sorted(counts)) or "-"

    rows=[]
    total_http_responses=0
    for key in sorted(grouped):
        url,device,profile_id=key
        items=grouped[key]
        summary=summary_by_key.get(key)
        attempts=len(items)
        valid=sum(item.get("classification") not in (None,"") for item in items)
        invalid=attempts-valid
        target=int((summary or {}).get("target_samples") or valid)
        responses=sum(item.get("http_status") is not None for item in items)
        total_http_responses += responses
        http_states=distribution([
            int(item.get("http_status")) if item.get("http_status") is not None else None
            for item in items
        ])
        navigation_states=distribution(
            [item.get("status") for item in items],
            lambda value:_status_label(value) if value!="sem resposta" else "Sem estado",
        )
        classifications=distribution(
            [item.get("classification") for item in items],
            lambda value:_classification_label(value) if value!="sem resposta" else "Inválida",
        )
        xhr=sum(int(item.get("xhr_fetch_count") or 0) for item in items)
        failed=sum(int(item.get("request_failed_count") or 0) for item in items)
        http_errors=sum(int(item.get("http_error_count") or 0) for item in items)
        rows.append((
            url or "-",
            _device_label(device),
            _Html(f"<code>{escape(profile_id or '-')}</code>"),
            target,
            attempts,
            f"{responses}/{attempts}",
            http_states,
            navigation_states,
            f"{valid}/{invalid}",
            classifications,
            xhr,
            failed,
            http_errors,
        ))

    lead=(
        "<p class='section-lead'><strong>Uma tentativa</strong> corresponde a uma user action sintética "
        "com uma navegação principal. Contadores de XHR/fetch e erros são telemetria dentro da tentativa; "
        "não representam novas amostras nem o total exato de requests quando a lista completa não foi persistida.</p>"
    )
    summary=(
        "<div class='metric-grid'>"
        +_metric("Perfis executados",len(grouped))
        +_metric("Tentativas persistidas",len(samples))
        +_metric("Retornos HTTP principais",f"{total_http_responses}/{len(samples)}")
        +"</div>"
    )
    return lead+summary+_table(
        (
            "URL","Dispositivo","Perfil técnico","Alvo válido","Tentativas",
            "Retorno HTTP principal","HTTP principal","Estado da navegação",
            "Válidas / inválidas","Classificação","XHR/fetch",
            "Requisições com falha","HTTP >=400",
        ),
        rows,
        empty="Nenhuma tentativa de Apdex de experiência foi persistida nesta auditoria.",
        sortable=bool(rows),
        page_size=10 if len(rows)>10 else None,
    )

def _security_finding_type_label(value: Any) -> str:
    return {
        "OBSERVATION":"Observação",
        "CONFIGURATION_WEAKNESS":"Fragilidade de configuração",
        "EXPOSURE":"Exposição",
        "POTENTIAL_VULNERABILITY":"Vulnerabilidade potencial",
        "KNOWN_VULNERABILITY":"Vulnerabilidade conhecida",
        "THREAT_REPUTATION":"Inteligência de ameaças / reputação",
        "RUNTIME_FAILURE":"Falha em tempo de execução",
        "INFORMATION_DISCLOSURE":"Exposição de informação",
    }.get(_norm(value),public_label(value) or str(value or "-").replace("_"," ").title())


def _security_category_label(value: Any) -> str:
    return {
        "TRANSPORT":"Transporte",
        "HTTP_SECURITY":"Segurança HTTP",
        "BROWSER_SECURITY":"Segurança do navegador",
        "CORS":"CORS",
        "COOKIES":"Cookies",
        "PRIVACY_BROWSER":"Privacidade / navegador",
        "CROSS_ORIGIN":"Políticas entre origens",
        "INFORMATION_DISCLOSURE":"Exposição de informação",
        "MIXED_CONTENT":"Conteúdo misto",
        "RESOURCE_INTEGRITY":"Integridade de recursos",
        "FORMS":"Formulários",
        "IFRAMES":"Iframes",
        "RUNTIME":"Tempo de execução",
        "VULNERABILITY_INTELLIGENCE":"Inteligência de vulnerabilidades / CVE",
    }.get(_norm(value),public_label(value) or str(value or "-").replace("_"," ").title())


def _security_party_label(value: Any) -> str:
    return {
        "FIRST_PARTY":"Próprio domínio",
        "THIRD_PARTY":"Domínio externo",
        "INLINE":"Em linha",
        "UNKNOWN":"Não determinado",
    }.get(_norm(value),public_label(value) or str(value or "-").replace("_"," ").title())


def _security_source_label(value: Any) -> str:
    raw=str(value or "").strip()
    if not raw:
        return "-"
    return {
        "RASAI PASSIVE SECURITY ANALYZER": "Análise determinística de segurança passiva",
        "OSV + CISA KEV": "OSV + CISA KEV",
        "OSV": "OSV",
    }.get(raw.upper(),raw)


def _security_resource_kind_label(value: Any) -> str:
    return {
        "SCRIPT":"Script",
        "STYLESHEET":"Folha de estilos",
        "RESOURCE":"Recurso",
        "FORM":"Formulário",
        "IFRAME":"Iframe",
        "IMG":"Imagem",
        "SOURCE":"Fonte",
        "VIDEO":"Vídeo",
        "AUDIO":"Áudio",
        "TRACK":"Track",
    }.get(_norm(value),public_label(value) or str(value or "-").replace("_"," ").title())


def _security_severity_tone(value: Any) -> str:
    raw=_norm(value)
    if raw in {"CRITICAL","HIGH"}:
        return "bad"
    if raw=="MEDIUM":
        return "warn"
    return "neutral"


_SECURITY_LIMITATION_LABELS = {
    "NO_PERSISTED_PAGE_CONTEXT": "Não há contexto de página persistido suficiente para completar todas as verificações.",
    "OSV_REDUCED_COVERAGE": "A cobertura do OSV ficou reduzida por indisponibilidade ou resposta parcial da fonte externa.",
    "CISA_KEV_REDUCED_COVERAGE": "A cobertura da lista CISA KEV ficou reduzida por indisponibilidade da fonte externa.",
}

_SECURITY_DETAIL_KEY_LABELS = {
    "reason": "Motivo",
    "queryable_components": "Componentes com versão consultável",
    "source_blocked": "Fonte bloqueada pela política",
    "cves_checked": "CVEs verificados",
    "matched": "Correspondências encontradas",
    "reused_from": "Fonte reutilizada",
    "redirect_chain": "Cadeia de redirecionamentos",
    "script_sources": "Origens permitidas para scripts",
    "cookie": "Atributos do cookie",
    "runtime_type": "Tipo de ocorrência em execução",
    "count": "Quantidade",
    "sample_count": "Quantidade de amostras",
    "samples": "Amostras",
    "secure": "Atributo Secure",
    "httponly": "Atributo HttpOnly",
    "samesite": "Política SameSite",
    "sensitive_name_hint": "Nome sugere dado sensível",
    "advisory_id": "Identificador do aviso de segurança",
    "aliases": "Identificadores relacionados",
    "severity": "Severidade informada pela fonte",
    "references": "Referências da fonte",
    "kev_state": "Correspondência com CISA KEV",
    "kev": "Detalhes CISA KEV",
    "library": "Biblioteca",
    "version": "Versão",
    "ecosystem": "Ecossistema",
    "identification_method": "Método de identificação",
    "domain": "Domínio",
    "path": "Caminho",
    "name_hash": "Identificador protegido do cookie",
    "url": "URL",
    "type": "Tipo",
    "score": "Pontuação",
    "cveID": "CVE",
    "vendorProject": "Fornecedor / projeto",
    "product": "Produto",
    "dateAdded": "Data de inclusão",
    "shortDescription": "Descrição",
    "requiredAction": "Ação requerida",
    "dueDate": "Prazo",
    "knownRansomwareCampaignUse": "Uso conhecido em ransomware",
    "notes": "Observações",
    "cwes": "CWEs",
}

_SECURITY_DETAIL_ALLOWED_KEYS = frozenset(_SECURITY_DETAIL_KEY_LABELS)

_SECURITY_DETAIL_VALUE_LABELS = {
    "NO_VERSIONED_COMPONENT_IDENTIFIED": "Nenhum componente com versão identificável foi encontrado.",
    "NO_CVE_FROM_OSV": "Nenhum CVE foi retornado pelo OSV para os componentes consultados.",
    "OPTIONAL_DEEP_TLS_NOT_ENABLED_IN_INITIAL_SCOPE": "Análise TLS externa aprofundada não habilitada neste escopo.",
    "URL_REPUTATION_REQUIRES_EXPLICIT_PRIVACY_AND_PROVIDER_POLICY": "Consulta de reputação de URL não habilitada; exige política explícita de privacidade e de provedor.",
    "MATCHED": "Correspondência encontrada",
    "NOT_MATCHED": "Sem correspondência",
    "NOT_CHECKED": "Não verificado",
    "REQUESTFAILED": "Requisição com falha",
    "CONSOLE.ERROR": "Erro de console",
    "PAGEERROR": "Erro de página",
    "HTTP_ERROR": "Resposta HTTP com erro",
    "FILENAME": "Nome do arquivo",
}


def _security_limitation_label(value: Any) -> str:
    raw=_norm(value)
    return _SECURITY_LIMITATION_LABELS.get(
        raw,
        _status_label(value) if raw in {
            "NO_DATA","NOT_REQUESTED","UNAVAILABLE","PARTIAL","FAILED_RETRYABLE",
            "FAILED_TERMINAL","NOT_CONFIGURED","WAITING_FOR_DATA"
        } else public_label(value) or str(value or "-").replace("_"," ").title(),
    )


def _security_identification_method_label(value: Any) -> str:
    raw=_norm(value)
    return {
        "FILENAME":"Nome do arquivo",
        "URL":"URL do recurso",
        "HEADER":"Cabeçalho HTTP",
        "MANIFEST":"Manifesto",
        "SBOM":"SBOM",
    }.get(raw,public_label(value) or str(value or "-").replace("_"," ").title())


def _security_detail_key_label(value: Any) -> str:
    raw=str(value or "").strip()
    return _SECURITY_DETAIL_KEY_LABELS.get(
        raw.casefold(),
        raw.replace("_"," ").strip().capitalize() or "Detalhe",
    )


def _security_detail_scalar(value: Any) -> str:
    if isinstance(value,bool):
        return "Sim" if value else "Não"
    if value is None:
        return "-"
    raw=_norm(value)
    if raw in _SECURITY_DETAIL_VALUE_LABELS:
        return _SECURITY_DETAIL_VALUE_LABELS[raw]
    if raw in {"TRUE","FALSE"}:
        return "Sim" if raw=="TRUE" else "Não"
    if raw in {"FIRST_PARTY","THIRD_PARTY","INLINE","UNKNOWN"}:
        return _security_party_label(value)
    if raw in {
        "SUCCESS","COMPLETE","COMPLETED","PARTIAL","FAILED_RETRYABLE","FAILED_TERMINAL",
        "NOT_REQUESTED","UNAVAILABLE","NO_DATA","NOT_CONFIGURED","WAITING_FOR_DATA",
    }:
        return _status_label(value)
    if raw in {"CRITICAL","HIGH","MEDIUM","LOW","INFO"}:
        return _level_label(value)
    return str(value)


def _security_detail_html(value: Any) -> str:
    if isinstance(value,Mapping):
        rows=[]
        for key,item in value.items():
            if str(key) not in _SECURITY_DETAIL_ALLOWED_KEYS:
                continue
            rendered=_security_detail_html(item)
            if not rendered:
                continue
            rows.append(
                "<dt>"+escape(_security_detail_key_label(key))+"</dt>"
                "<dd>"+rendered+"</dd>"
            )
        return "<dl class='kv'>"+"".join(rows)+"</dl>" if rows else ""
    if isinstance(value,(list,tuple)):
        if not value:
            return "<span class='muted'>Nenhum valor informado.</span>"
        rendered=[_security_detail_html(item) for item in value]
        rendered=[item for item in rendered if item]
        return "<ul>"+"".join("<li>"+item+"</li>" for item in rendered)+"</ul>" if rendered else ""
    return str(_display_value(_security_detail_scalar(value)))


def _passive_security_html(database: Path, data: _ReportData) -> str:
    con=sqlite3.connect(database); con.row_factory=sqlite3.Row
    try:
        run=_last(con,"passive_security_runs",data.audit_id)
        findings=_audit_rows(con,"passive_security_findings",data.audit_id)
        resources=_audit_rows(con,"passive_security_resources",data.audit_id)
        components=_audit_rows(con,"passive_security_components",data.audit_id)
        integrations=_audit_rows(con,"passive_security_integrations",data.audit_id)
        standards=_audit_rows(con,"standards_metric_observations",data.audit_id)
        web=_last(con,"web_performance_observations",data.audit_id)
        improvement_run=_last(con,"improvement_intelligence_runs",data.audit_id)
        ai_recommendations=[
            row for row in _audit_rows(con,"improvement_intelligence_recommendations",data.audit_id)
            if _norm(row.get("domain"))=="SECURITY"
        ]
    finally:
        con.close()

    catalog_items=getattr(data,"catalog_items",{}) or {}
    cat10_item=catalog_items.get("CAT-10",{}) if isinstance(catalog_items,Mapping) else {}
    ai_requested=bool(cat10_item.get("ai_execution_enabled",False)) if isinstance(cat10_item,Mapping) else False

    if not run:
        message=(
            "<div class='notice warn'><strong>Segurança passiva sem resultado:</strong> "
            "o CAT-10 não possui execução consolidada persistida nesta AUD. O relatório não infere "
            "ausência de risco a partir da ausência de dados.</div>"
        )
        if ai_requested:
            message+=(
                "<div class='notice warn'><strong>IA consultiva solicitada, mas não executada de forma utilizável:</strong> "
                "sem a execução consolidada do CAT-10 não há base final para materializar a análise de Segurança passiva por IA. "
                "Consulte Execução e IA e integrações; este estado não deve ser apresentado como análise concluída.</div>"
            )
        return message

    coverage=_safe_json(run.get("coverage_json"),{})
    limitations=_safe_json(run.get("limitations_json"),[])
    ai_rec_by_finding={
        str(row.get("finding_id")): row
        for row in ai_recommendations
        if str(row.get("finding_id") or "").strip()
    }
    ai_matches=sum(1 for item in findings if str(item.get("finding_id") or "") in ai_rec_by_finding)
    coverage_labels={
        "transport":"HTTPS e redirecionamentos",
        "headers":"Cabeçalhos de segurança",
        "csp":"Política de Segurança de Conteúdo (CSP)",
        "cookies":"Cookies",
        "cors_cross_origin":"CORS e políticas entre origens",
        "scripts_resources":"Scripts e recursos",
        "third_party":"Recursos de terceiros",
        "mixed_content":"Conteúdo misto",
        "forms_iframes":"Formulários e iframes",
        "runtime":"Erros em tempo de execução",
        "component_inventory":"Inventário de componentes",
        "osv_intelligence":"OSV / avisos de segurança",
        "cisa_kev":"CISA KEV",
        "vulnerability_intelligence":"Inteligência de vulnerabilidades",
        "active_scanning":"Varredura ativa",
    }
    coverage_rows=[]
    if isinstance(coverage,Mapping):
        for key,value in coverage.items():
            if bool(value):
                coverage_state=_state_text("PASS","Coberto")
            elif str(key)=="active_scanning":
                coverage_state=_state_text("NOT_APPLICABLE","Não executado por política")
            else:
                coverage_state=_state_text("WARNING","Não coberto")
            coverage_rows.append((
                coverage_labels.get(str(key),public_label(key) or str(key).replace("_"," ").title()),
                coverage_state,
            ))

    severities={key:0 for key in ("CRITICAL","HIGH","MEDIUM","LOW","INFO")}
    types={}
    for item in findings:
        sev=_norm(item.get("severity"))
        if sev in severities:
            severities[sev]+=1
        typ=_norm(item.get("finding_type"))
        types[typ]=types.get(typ,0)+1

    summary=(
        "<div class='notice'><strong>Escopo de segurança:</strong> análise estritamente passiva. "
        "O CAT-10 não executa teste de invasão (pentest), exploração, fuzzing, força bruta, contorno de autenticação, submissão de formulários "
        "ou cargas ofensivas. Ele reutiliza HTTP, HTML/DOM, navegador, telemetria de execução e integrações externas governadas.</div>"
        "<div class='metric-grid'>"
        +_metric("Estado",_status_label(run.get("status")))
        +_metric("Páginas analisadas",run.get("pages_analyzed",0))
        +_metric("Recursos inventariados",len(resources))
        +_metric("Componentes identificados",len(components))
        +_metric_result("Achados",len(findings),"neutral")
        +_metric_result("Críticos",severities["CRITICAL"],"bad" if severities["CRITICAL"] else "neutral")
        +_metric_result("Altos",severities["HIGH"],"bad" if severities["HIGH"] else "neutral")
        +_metric_result("Médios",severities["MEDIUM"],"warn" if severities["MEDIUM"] else "neutral")
        +_metric("Achados com análise por IA",(f"{ai_matches}/{len(findings)}" if ai_requested else "Não solicitada"))
        +"</div>"
    )
    best_practices=web.get("best_practices_score") if web else None
    if best_practices is not None:
        try:
            bp=float(best_practices)
            bp_label=f"{bp*100:.0f} / 100" if 0 <= bp <= 1 else f"{bp:.0f} / 100"
        except (TypeError,ValueError):
            bp_label=str(best_practices)
        summary+="<div class='notice'><strong>Lighthouse · Boas práticas reutilizado:</strong> "+escape(bp_label)+". Este sinal já coletado é complementar; o CAT-10 não repete Lighthouse nem converte sua nota diretamente em achado.</div>"

    limitation_html=""
    if isinstance(limitations,list) and limitations:
        limitation_html=(
            "<div class='notice warn'><strong>Cobertura reduzida:</strong> "
            +escape(" · ".join(_security_limitation_label(v) for v in limitations))
            +". Falha/indisponibilidade de fonte externa reduz a cobertura do CAT-10; não é convertida automaticamente em vulnerabilidade do alvo.</div>"
        )

    ai_notice=""
    if ai_requested:
        if not improvement_run:
            ai_notice=(
                "<div class='notice warn'><strong>IA consultiva solicitada, mas sem resultado persistido:</strong> "
                "o CAT-10 foi configurado para enriquecimento por IA, porém não existe execução consolidada da "
                "Análise Profunda nesta AUD. Os achados determinísticos permanecem válidos; a ausência de IA "
                "deve ser tratada como lacuna de execução, não como análise concluída.</div>"
            )
        else:
            ai_domains=_safe_json(improvement_run.get("domains_json"),[])
            security_in_run=isinstance(ai_domains,list) and any(_norm(value)=="SECURITY" for value in ai_domains)
            if not security_in_run:
                ai_notice=(
                    "<div class='notice warn'><strong>IA executada sem a dimensão Segurança passiva:</strong> "
                    "há resultado da Análise Profunda, mas ele não declara Segurança passiva entre as dimensões "
                    "persistidos. O CAT-10 não atribui recomendações de outro domínio aos achados de segurança.</div>"
                )
            else:
                ai_notice=(
                    "<div class='notice'><strong>IA consultiva do CAT-10:</strong> "
                    +escape(str(ai_matches))+" de "+escape(str(len(findings)))
                    +" achado(s) possuem recomendação vinculada às evidências materializada pela Análise Profunda. "
                    "A IA é consultiva, não participa da pontuação e não substitui validação humana nem a evidência determinística.</div>"
                )

    finding_rows=[]; modals=[]
    for index,item in enumerate(findings,1):
        finding_token=re.sub(r"[^a-z0-9_-]+","-",str(item.get("finding_id") or index).casefold()).strip("-") or str(index)
        mid=f"security-finding-{finding_token}"
        recommendation=ai_rec_by_finding.get(str(item.get("finding_id") or ""))
        ai_state=("Analisado pela IA" if recommendation else "Sem recomendação específica" if ai_requested else "Não solicitada")
        finding_type=_security_finding_type_label(item.get("finding_type"))
        category=_security_category_label(item.get("category"))
        party=_security_party_label(item.get("party_context"))
        cves=_safe_json(item.get("cve_json"),[])
        evidence_ids=_safe_json(item.get("evidence_ids_json"),[])
        details=_safe_json(item.get("details_json"),{})
        severity_display=_result_value(_level_label(item.get("severity")),_security_severity_tone(item.get("severity")))
        finding_rows.append((
            severity_display,
            finding_type,
            category,
            item.get("title") or "Achado",
            party,
            _confidence_label(item.get("confidence")),
            ai_state,
            _modal_button(mid,"Ver achado"),
        ))
        body=_kv((
            ("Problema observado",item.get("description") or "-"),
            ("Classificação",finding_type),
            ("Severidade",severity_display),
            ("Confiança",_confidence_label(item.get("confidence"))),
            ("Origem",_security_source_label(item.get("source"))),
            ("Contexto",party),
            ("Impacto",item.get("impact") or "-"),
            ("Contenção imediata",item.get("containment") or "-"),
            ("Correção definitiva",item.get("remediation") or "-"),
            ("Como validar",item.get("validation") or "-"),
            ("CWE",item.get("cwe") or "-"),
            ("CVE(s)",", ".join(str(v) for v in cves) if isinstance(cves,list) and cves else "-"),
        ))
        if recommendation:
            body+=(
                "<h3>Análise e sugestão consultiva da IA</h3>"
                +_kv((
                    ("Recomendação",recommendation.get("recommendation") or recommendation.get("title") or "-"),
                    ("Justificativa / análise",recommendation.get("rationale") or "-"),
                    ("Confiança da IA",_confidence_label(recommendation.get("confidence"))),
                    ("Esforço estimado",_level_label(recommendation.get("effort"))),
                    ("Prioridade",_priority_text(recommendation.get("priority"))),
                    ("Como validar",recommendation.get("verification") or "-"),
                ))
            )
            if recommendation.get("suggested_text"):
                body+="<h4>Texto/exemplo sugerido</h4><div class='pre'>"+escape(str(recommendation.get("suggested_text")))+"</div>"
            if recommendation.get("suggested_html"):
                body+="<h4>Exemplo técnico sugerido</h4><div class='pre'>"+escape(str(recommendation.get("suggested_html")))+"</div>"
            body+="<div class='notice'>Orientação gerada por IA a partir das evidências persistidas deste achado. É consultiva, não participa da pontuação, não confirma explorabilidade e exige revisão humana.</div>"
        elif ai_requested:
            body+="<div class='notice warn'><strong>IA consultiva sem recomendação específica para este achado.</strong> A configuração solicitava IA; consulte o estado da Análise Profunda e a cobertura N/M no resumo do CAT-10.</div>"
        if isinstance(evidence_ids,list) and evidence_ids:
            body+="<h3>Rastreabilidade</h3><p>"+escape(str(len(evidence_ids)))+" referência(s) de evidência persistida(s) e vinculada(s) a este achado.</p>"
        if isinstance(details,Mapping) and details:
            rendered_details=_security_detail_html(details)
            if rendered_details:
                body+="<details><summary>Detalhes técnicos persistidos</summary><div class='detail-body'>"+rendered_details+"</div></details>"
        modals.append(_modal(mid,item.get("title") or "Achado de segurança",f"{category} · {_security_source_label(item.get('source'))}",body))

    integration_rows=[]; integration_modals=[]
    for index,item in enumerate(integrations,1):
        mid=f"security-integration-{index}"
        details=_safe_json(item.get("details_json"),{})
        integration_rows.append((
            _friendly_service(item.get("integration_id")),
            "Sim" if bool(item.get("requested")) else "Não",
            _state_text(item.get("state"),_status_label(item.get("state"))),
            item.get("attempts",0),
            item.get("successes",0),
            _modal_button(mid,"Ver integração"),
        ))
        body=_kv((
            ("Integração",_friendly_service(item.get("integration_id"))),
            ("Solicitada","Sim" if bool(item.get("requested")) else "Não"),
            ("Estado",_state_text(item.get("state"),_status_label(item.get("state")))),
            ("Tentativas",item.get("attempts",0)),
            ("Sucessos",item.get("successes",0)),
            ("Erro técnico",item.get("error_message") or item.get("error_type") or "-"),
        ))
        if isinstance(details,Mapping) and details:
            rendered_details=_security_detail_html(details)
            if rendered_details:
                body+="<h3>Detalhes persistidos</h3>"+rendered_details
        body+="<div class='notice'>Os estados apresentados descrevem a cobertura da integração — por exemplo, sem dados, não solicitado ou indisponível — e não significam, por si sós, problema de segurança no site.</div>"
        integration_modals.append(_modal(mid,_friendly_service(item.get("integration_id")),"Integração externa/reutilizada do CAT-10",body))

    resource_groups={}
    for item in resources:
        key=(str(item.get("resource_kind") or "UNKNOWN"),str(item.get("party") or "UNKNOWN"))
        resource_groups[key]=resource_groups.get(key,0)+1
    resource_rows=[
        (_security_resource_kind_label(kind),_security_party_label(party),count)
        for (kind,party),count in sorted(resource_groups.items())
    ]

    component_rows=[]
    for item in components[:100]:
        component_rows.append((
            item.get("library") or "-",
            item.get("version") or "Versão não determinada",
            item.get("ecosystem") or "-",
            _security_identification_method_label(item.get("identification_method")),
            _confidence_label(item.get("confidence")),
        ))

    mdn_rows=[]
    for item in standards:
        if str(item.get("metric_id") or "")!="mdn_http_observatory":
            continue
        details=_safe_json(item.get("details_json"),{})
        grade=details.get("grade") if isinstance(details,Mapping) else None
        tests_passed=details.get("tests_passed") if isinstance(details,Mapping) else None
        tests_failed=details.get("tests_failed") if isinstance(details,Mapping) else None
        mdn_rows.append((
            item.get("target") or "-",
            _status_label(item.get("state")),
            grade or "-",
            item.get("value") if item.get("value") is not None else "-",
            tests_passed if tests_passed is not None else "-",
            tests_failed if tests_failed is not None else "-",
        ))

    type_rows=[
        (_security_finding_type_label(key),value)
        for key,value in sorted(types.items())
    ]

    return (
        summary
        +limitation_html
        +ai_notice
        +"<div class='subsection'><h3>O que foi analisado</h3>"
        +_table(("Cobertura","Estado"),coverage_rows,empty="Cobertura não persistida.")
        +"</div>"
        +"<div class='subsection'><h3>Achados</h3>"
        +_table(("Severidade","Classificação","Categoria","Problema","Contexto","Confiança","IA consultiva","Detalhe"),finding_rows,empty="Nenhum achado de segurança foi materializado para o escopo analisado.",sortable=bool(finding_rows),page_size=10 if len(finding_rows)>10 else None)
        +"".join(modals)+"</div>"
        +"<div class='subsection'><h3>Distribuição por classificação</h3>"
        +_table(("Classificação","Achados"),type_rows,empty="Nenhuma classificação materializada.")
        +"</div>"
        +"<div class='subsection'><h3>Scripts, recursos e origem</h3>"
        +_table(("Tipo de recurso","Origem","Quantidade"),resource_rows,empty="Nenhum recurso HTML foi inventariado.")
        +"</div>"
        +"<div class='subsection'><h3>Componentes/versionamento identificáveis</h3>"
        +"<p class='section-lead'>Versão detectada pelo nome do arquivo é evidência heurística moderada: pode habilitar correlação OSV, mas o achado permanece potencial até confirmação por inventário, build ou SBOM.</p>"
        +_table(("Componente","Versão","Ecossistema","Método","Confiança"),component_rows,empty="Nenhum componente com identificação útil foi detectado.",sortable=bool(component_rows))
        +"</div>"
        +"<div class='subsection'><h3>MDN HTTP Observatory reutilizado</h3>"
        +"<p class='section-lead'>Resultado proveniente da coleta canônica de padrões web; o CAT-10 não dispara uma segunda consulta ao Observatory.</p>"
        +_table(("Origem","Estado","Classificação","Pontuação","Testes aprovados","Testes falhos"),mdn_rows,empty="Nenhuma medição do MDN HTTP Observatory foi persistida nesta AUD.",sortable=bool(mdn_rows))
        +"</div>"
        +"<div class='subsection'><h3>Integrações de segurança</h3>"
        +_table(("Integração","Solicitada","Estado","Tentativas","Sucessos","Detalhe"),integration_rows,empty="Nenhuma integração própria do CAT-10 foi persistida.",sortable=bool(integration_rows))
        +"".join(integration_modals)+"</div>"
    )


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
        severity_display=_severity_text(f.get("severity"))
        priority_display=_priority_text(rec.get("priority")) if rec else "-"
        rows.append((f.get("title") or "Problema identificado",severity_display,priority_display,reference,_modal_button(mid,"Ver análise")))
        body=_kv((("Problema",f.get("observation") or f.get("title") or "-"),("Domínio",_domain_label(f.get("domain"))),("Severidade",severity_display),("Fonte",f.get("source") or "-"),("Catálogo de origem",source_cat or "-")))
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
    active=[f"{labels.get(str(k),public_label(k) or str(k).replace('_',' ').title())}: {v}" for k,v in impacts.items() if isinstance(v,(int,float)) and v>0]
    return " · ".join(active) or "Sem impacto adicional quantificado"


def _jsonld_title(row: Mapping[str, Any]) -> str:
    existing = row.get("existing_types")
    try:
        parsed = json.loads(existing) if isinstance(existing, str) else existing
    except (TypeError, ValueError, json.JSONDecodeError):
        parsed = []
    return (
        "Aprimorar dados estruturados existentes"
        if isinstance(parsed, list) and parsed
        else "Considerar implementar dados estruturados aplicáveis"
    )


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
        rows.append((title,_priority_text(r.get("priority_class")),"Determinística",_modal_button(mid,"Ver correção")))
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
        priority_display=_priority_text(r.get("priority"))
        severity_display=_severity_text(r.get("severity"))
        rows.append((title,priority_display,f"CAT-08 → {source_cat or 'evidência transversal'}",_modal_button(mid,"Ver implementação")))
        rationale=_rationale_parts(r.get("rationale"))
        problem=finding.get("observation") or finding.get("title") or "-"
        body=_kv((("Problema observado",problem),("Domínio",_domain_label(r.get("domain"))),("Severidade",severity_display),("Prioridade",priority_display),("Onde aplicar",r.get("selector") or "Não se aplica / não identificado"),("Como corrigir",r.get("recommendation") or "-"),("Risco de manter como está",rationale.get("risk") or r.get("rationale") or "-"),("Benefício esperado da correção",rationale.get("benefit") or "-"),("Justificativa técnica",rationale.get("technical") or "-"),("Impactos relacionados",_impact_summary(r.get("impacts_json"))),("Esforço",_level_label(r.get("effort"))),("Confiança",_confidence_label(r.get("confidence"))),("Problema de origem",r.get("finding_id") or "-")))
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
