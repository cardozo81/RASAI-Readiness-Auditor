"""Technical, accessibility and semantic evidence projections."""
from rasai.catalog_report_metrics import *  # noqa: F401,F403
from rasai.catalog_report_public_labels import public_text


def _artifact_path(root: Path, reference: Any) -> Path|None:
    if not reference:return None
    ref=str(reference).replace("\\","/")
    try:
        candidate=(root/ref).resolve()
        candidate.relative_to(root.resolve())
    except (ValueError,OSError):
        return None
    return candidate if candidate.is_file() else None


def _read_json_artifact(root: Path, reference: Any, *, max_bytes: int=30_000_000) -> Any:
    path=_artifact_path(root,reference)
    if path is None:return None
    try:
        if path.stat().st_size>max_bytes:return None
        return json.loads(path.read_text(encoding="utf-8",errors="replace"))
    except (OSError,ValueError,json.JSONDecodeError):
        return None


def _capture_snapshots(database: Path, audit_id: str) -> list[dict[str,Any]]:
    con=sqlite3.connect(database); con.row_factory=sqlite3.Row
    try:
        if not (_table_exists(con,"page_snapshots") and _table_exists(con,"pages")):return []
        rows=_rows(con,"""SELECT ps.*, p.normalized_url AS page_url FROM page_snapshots ps
            JOIN pages p ON p.page_id=ps.page_id WHERE p.audit_id=? ORDER BY p.rowid,ps.device""",(audit_id,))
        return _dict_rows(rows)
    finally:con.close()


def _runtime_items(snapshot: Mapping[str,Any]) -> list[dict[str,Any]]:
    meta=_safe_json(snapshot.get("browser_metadata"),{})
    runtime=meta.get("runtime_diagnostics") if isinstance(meta,Mapping) else {}
    items=runtime.get("items",[]) if isinstance(runtime,Mapping) else []
    return [dict(v) for v in items if isinstance(v,Mapping)]


def _runtime_type_label(value: Any) -> str:
    return {
        "CONSOLE_ERROR":"Erro do console","CONSOLE_WARNING":"Alerta do console","PAGE_ERROR":"Erro JavaScript da página",
        "REQUEST_FAILED":"Requisição com falha","HTTP_ERROR":"Resposta HTTP com erro",
    }.get(_norm(value),str(value or "Diagnóstico").replace("_"," ").title())


def _runtime_diagnostics_html(database: Path, data: _ReportData) -> str:
    rows=[]; modals=[]; idx=0
    for snap in _capture_snapshots(database,data.audit_id):
        for item in _runtime_items(snap):
            idx+=1; mid=f"runtime-{idx}"
            label=_runtime_type_label(item.get("type"))
            url=item.get("url") or "-"; message=item.get("message") or "-"
            rows.append((label,message,url,_modal_button(mid,"Ver ocorrência")))
            modals.append(_modal(mid,label,f"{_device_label(snap.get('device'))} · {snap.get('final_url') or snap.get('requested_url') or snap.get('page_url') or '-'}",
                _kv((("Mensagem",message),("Recurso / URL",url),("Identificador da captura",snap.get("snapshot_id")),("Dispositivo",_device_label(snap.get("device")))))))
    return _table(("Tipo","Mensagem","Recurso","Detalhe"),rows,empty="Nenhum erro de console, JavaScript ou requisição foi persistido nas capturas disponíveis.",sortable=bool(rows))+"".join(modals)


def _discovery_title(row: Mapping[str,Any], observed: Any) -> str:
    code=_norm(row.get("code"))
    explicit={
        "M24-ROBOTS-ABSENT":"robots.txt não encontrado",
        "M24-SITEMAP-ABSENT":"Sitemap não encontrado no caminho convencional",
        "M24-LLMS-ABSENT":"llms.txt não encontrado",
        "M24-LLMS-DISCOVERY-SUMMARY":"Resumo da descoberta de llms.txt",
        "M24-DISCOVERY-INDEXNOW":"Uso de IndexNow não determinável nesta auditoria",
    }
    if code in explicit:return explicit[code]
    title=str(row.get("title") or "Recurso de descoberta")
    replacements={
        "ABSENT":"não encontrado","UNAVAILABLE":"sem dados disponíveis",
        "NOT_DETERMINABLE":"não determinável","NOT_REQUESTED":"não solicitado",
    }
    for raw,human in replacements.items():title=title.replace(raw,human)
    return public_text(title)


def _discovery_html(database: Path, data: _ReportData) -> str:
    con=sqlite3.connect(database); con.row_factory=sqlite3.Row
    try:items=_audit_rows(con,"m24_diagnostics",data.audit_id)
    finally:con.close()
    relevant=[r for r in items if _norm(r.get("category")) in {"ROBOTS","SITEMAP","AI_ACCESS","FILES_DISCOVERY","DISCOVERY"}]
    rows=[]; modals=[]
    for i,row in enumerate(relevant,1):
        mid=f"discovery-{i}"
        observed=_safe_json(row.get("observed_value"),{})
        state=observed.get("state") if isinstance(observed,Mapping) else None
        situation=_status_label(state or row.get("severity"))
        category={"ROBOTS":"robots.txt","SITEMAP":"Sitemap / feed","AI_ACCESS":"Arquivo para agentes de IA","DISCOVERY":"Mecanismo de descoberta"}.get(_norm(row.get("category")),str(row.get("category") or "Recurso").replace("_"," ").title())
        title=_discovery_title(row,observed)
        rows.append((category,title,row.get("scope_url") or "-",_modal_button(mid,"Ver leitura")))
        human_observed = observed.get("reason") or observed.get("error") or observed.get("detail") if isinstance(observed,Mapping) else observed
        modal_body=_kv((("Situação",situation),("Observação",human_observed or title),("Impacto na pontuação",_score_impact_label(row.get("scoring_impact"))),("Referência",row.get("diagnostic_id") or "-")))
        if row.get("remediation"):
            modal_body+="<h3>Orientação registrada</h3><p>"+escape(str(row.get("remediation")))+"</p><p class='muted'>A orientação técnica consolidada e, quando disponível, enriquecida por IA fica em <a href='cat-09.html'>CAT-09 · Remediações</a>.</p>"
        if isinstance(observed,(dict,list)):
            modal_body+="<details><summary>Ver dados técnicos observados</summary><div class='detail-body'><div class='pre'>"+escape(json.dumps(observed,ensure_ascii=False,indent=2))+"</div></div></details>"
        modals.append(_modal(mid,title,row.get("scope_url") or "Recurso de descoberta",modal_body))
    return _table(("Recurso","Resultado observado","Endereço","Detalhe"),rows,empty="Nenhum diagnóstico de robots, sitemap ou arquivo de descoberta foi persistido.",sortable=bool(rows))+"".join(modals)


def _standards_summary(database: Path, data: _ReportData) -> str:
    con=sqlite3.connect(database); con.row_factory=sqlite3.Row
    try:
        metrics=_audit_rows(con,"standards_metric_observations",data.audit_id)
        services=_audit_rows(con,"standards_service_runs",data.audit_id)
    finally:con.close()
    wanted={"web_platform_widely_available_count":"Recursos amplamente disponíveis","web_platform_newly_available_count":"Recursos recentemente disponíveis","web_platform_limited_availability_count":"Recursos com disponibilidade limitada","w3c_css_conformance":"Conformidade CSS W3C"}
    rows=[]
    for r in metrics:
        key=str(r.get("metric_key") or "")
        if key in wanted:
            value=r.get("value_num") if r.get("value_num") is not None else r.get("status")
            rows.append((wanted[key],value,_status_label(r.get("status"))))
    for r in services:
        if str(r.get("service_id")) in {"w3c-validator","mdn-observatory","w3c-css-validator","web-platform-baseline"}:
            rows.append((_friendly_service(r.get("service_id")),f"{r.get('targets_succeeded',0)}/{r.get('targets_attempted',0)} alvo(s)",_status_label(r.get("state"))))
    return _table(("Verificação","Resultado","Estado"),rows,empty="Nenhuma métrica de padrões web foi persistida.",sortable=bool(rows))


def _lighthouse_accessibility_html(database: Path, data: _ReportData) -> str:
    obs=_web_observation(database,data.audit_id)
    artifact=obs.get("pagespeed_artifact_reference")
    payload=_read_json_artifact(database.parent,artifact)
    if not isinstance(payload,Mapping):
        return "<div class='notice'>A pontuação de acessibilidade pode estar persistida, mas o artefato detalhado do Lighthouse não está disponível para esta projeção.</div>"
    lh=payload.get("lighthouseResult") if isinstance(payload.get("lighthouseResult"),Mapping) else {}
    categories=lh.get("categories") if isinstance(lh,Mapping) and isinstance(lh.get("categories"),Mapping) else {}
    acc=categories.get("accessibility") if isinstance(categories,Mapping) and isinstance(categories.get("accessibility"),Mapping) else {}
    refs=acc.get("auditRefs",[]) if isinstance(acc,Mapping) else []
    ids={str(r.get("id")) for r in refs if isinstance(r,Mapping)}
    audits=lh.get("audits") if isinstance(lh,Mapping) and isinstance(lh.get("audits"),Mapping) else {}
    rows=[];modals=[];idx=0
    for aid in ids:
        a=audits.get(aid)
        if not isinstance(a,Mapping):continue
        score=a.get("score")
        if score is None or score==1:continue
        idx+=1;mid=f"a11y-{idx}"
        source_title=a.get("title") or aid
        title=_LIGHTHOUSE_A11Y_LABELS.get(aid,source_title)
        details=a.get("details") if isinstance(a.get("details"),Mapping) else {}
        items=details.get("items",[]) if isinstance(details,Mapping) else []
        sample=items[0] if items and isinstance(items[0],Mapping) else {}
        node=sample.get("node") if isinstance(sample.get("node"),Mapping) else {}
        selector=node.get("selector") or "-"
        snippet=node.get("snippet") or ""
        rows.append((title,"Requer atenção",selector,_modal_button(mid,"Ver evidência")))
        body=_kv((("Verificação",title),("Descrição da fonte",a.get("description") or source_title or "-"),("Elemento",selector),("Trecho",snippet or "-"),("Identificador técnico",aid)))
        body+="<p class='muted'>Quando houver recomendação correspondente, a implementação é centralizada em <a href='cat-09.html'>CAT-09 · Remediações</a>.</p>"
        modals.append(_modal(mid,title,"Evidência automatizada do Lighthouse",body))
    return _table(("Verificação","Resultado","Elemento","Detalhe"),rows,empty="Nenhuma violação automatizada do Lighthouse foi encontrada no artefato persistido.",sortable=bool(rows),page_size=10 if len(rows)>10 else None)+"".join(modals)


def _structured_data_html(database: Path, data: _ReportData) -> str:
    con=sqlite3.connect(database); con.row_factory=sqlite3.Row
    try:
        if not _table_exists(con,"rule_executions"):
            rules=[]
        else:
            placeholders=",".join("?" for _ in _STRUCTURED_RULE_LABELS)
            rules=_dict_rows(_rows(con,f"SELECT * FROM rule_executions WHERE audit_id=? AND rule_id IN ({placeholders}) ORDER BY rule_id",(data.audit_id,*_STRUCTURED_RULE_LABELS.keys())))
    finally:con.close()
    rows=[];modals=[]
    for i,r in enumerate(rules,1):
        rid=str(r.get("rule_id") or "")
        mid=f"structured-{i}"
        observed=_safe_json(r.get("observed_value"),r.get("observed_value"))
        summary="-"
        if isinstance(observed,Mapping):
            if "present" in observed:
                summary="Encontrado" if observed.get("present") else "Não encontrado"
                if isinstance(observed.get("types"),list) and observed.get("types"):
                    summary += " · " + ", ".join(str(v) for v in observed.get("types"))
            elif "structured_data_present" in observed:
                summary="Dados estruturados presentes" if observed.get("structured_data_present") else "Sem dados estruturados"
        elif observed not in (None,""):
            summary=str(observed)
        rows.append((_STRUCTURED_RULE_LABELS.get(rid,rid),_status_label(r.get("result")),summary,_modal_button(mid,"Ver validação")))
        body=_kv((("Validação",_STRUCTURED_RULE_LABELS.get(rid,rid)),("Resultado",_status_label(r.get("result"))),("Condição esperada",r.get("expected_condition") or "-"),("Identificador",rid)))
        if observed not in (None,""):
            body+="<details><summary>Ver dado técnico observado</summary><div class='detail-body'><div class='pre'>"+escape(json.dumps(observed,ensure_ascii=False,indent=2) if isinstance(observed,(dict,list)) else str(observed))+"</div></div></details>"
        modals.append(_modal(mid,_STRUCTURED_RULE_LABELS.get(rid,rid),"Validação determinística de dados estruturados",body))
    return _table(("Validação","Resultado","Leitura","Detalhe"),rows,empty="Nenhuma validação de JSON-LD/dados estruturados foi persistida.",sortable=bool(rows))+"".join(modals)


def _semantic_html(database: Path, data: _ReportData) -> str:
    con=sqlite3.connect(database); con.row_factory=sqlite3.Row
    try:
        entities=_audit_rows(con,"entity_observations",data.audit_id)
        assessments=_audit_rows(con,"semantic_assessments",data.audit_id)
    finally:con.close()
    blocks=[]
    if entities:
        entity_labels={"ORGANIZATION":"Organização","PERSON":"Pessoa","PRODUCT":"Produto","SERVICE":"Serviço","PLACE":"Local","EVENT":"Evento","TOPIC":"Tópico"}
        rows=[(r.get("name"),entity_labels.get(_norm(r.get("entity_type")),str(r.get("entity_type") or "-").replace("_"," ").title()),_confidence_label(r.get("confidence"))) for r in entities]
        blocks.append("<div class='subsection'><h3>Entidades identificadas</h3>"+_table(("Entidade","Tipo","Confiança"),rows,sortable=True,page_size=10 if len(rows)>10 else None)+"</div>")
    blocks.append("<div class='subsection'><h3>Dados estruturados / JSON-LD</h3>"+_structured_data_html(database,data)+"</div>")
    if assessments:
        providers=sorted({f"{r.get('provider')}/{r.get('model')}" for r in assessments if r.get("provider")})
        blocks.append(f"<div class='notice'><strong>Análise semântica assistida por IA:</strong> {len(assessments)} avaliação(ões) persistida(s). Provedor/modelo: {escape(', '.join(providers) or '-')}. <a href='ai-integrations.html'>Ver requisições, dados envolvidos e consumo em IA e integrações</a>.</div>")
    return "".join(blocks)


__all__ = [name for name in globals() if not name.startswith("__")]
