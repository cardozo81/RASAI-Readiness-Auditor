"""Read-only report projection for the evidence-bound Directed Analysis."""
from __future__ import annotations

from hashlib import sha256
import json
import sqlite3
from typing import Any, Mapping, Sequence

from rasai.catalog_report_presentation import *  # noqa: F401,F403


_SECTION_LABELS_DIRECTED = {
    "summary": "Resumo",
    "scope": "Escopo",
    "config": "Configuração",
    "execution": "Execução",
    "results": "Resultados",
    "evidence": "Evidências",
    "analysis": "Análise",
    "remediation": "Remediação",
    "technical": "Detalhes técnicos",
}

_DIRECTED_REASON_LABELS = {
    "AI_NOT_REQUESTED_FOR_AUDIT": "Síntese estratégica por IA não solicitada para esta auditoria.",
    "AI_PROVIDER_NOT_RESOLVED": "Não foi possível resolver um provedor de IA elegível para a síntese estratégica.",
    "NO_ACTIONABLE_PERSISTED_RECOMMENDATIONS": "Nenhuma recomendação acionável persistida foi encontrada para compor a síntese.",
}


_DIMENSION_LABELS_DIRECTED = {
    "APDEX_NAVIGATION": "Apdex de navegação",
    "APDEX_EXPERIENCE": "Apdex de experiência",
    "PERFORMANCE": "Desempenho",
    "ACCESSIBILITY": "Acessibilidade",
    "SEO": "SEO",
    "GEO_SEARCH_AI": "GEO / Busca e IA",
    "BEST_PRACTICES": "Boas práticas",
    "CONTENT": "Conteúdo",
    "SEMANTICS": "Semântica",
    "STRUCTURED_DATA": "Dados estruturados",
    "YMYL": "YMYL",
    "SECURITY": "Segurança",
    "VULNERABILITIES": "Vulnerabilidades",
    "HTML_CSS": "HTML / CSS",
    "CRAWLABILITY": "Rastreabilidade por crawlers",
    "INDEXABILITY": "Indexabilidade",
    "EXPERIENCE": "Experiência",
    "COMPETITIVE_INTELLIGENCE": "Inteligência competitiva",
    "TECHNICAL_QUALITY": "Qualidade técnica",
}


def _json(value: Any, default: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    if value in (None, ""):
        return default
    try:
        return json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return default


def _rows(connection: sqlite3.Connection, table: str, audit_id: str) -> list[dict[str, Any]]:
    try:
        cols={str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})").fetchall()}
        if "audit_id" not in cols:
            return []
        return [dict(row) for row in connection.execute(
            f"SELECT * FROM {table} WHERE audit_id=? ORDER BY rowid", (audit_id,)
        ).fetchall()]
    except sqlite3.Error:
        return []


def _one(connection: sqlite3.Connection, table: str, audit_id: str) -> dict[str, Any]:
    values=_rows(connection,table,audit_id)
    return values[-1] if values else {}


def _dimension_label(value: Any) -> str:
    raw=_norm(value)
    return _DIMENSION_LABELS_DIRECTED.get(raw, public_label(value) or str(value or "-").replace("_"," ").title())


def _gain_label(value: Any) -> str:
    return {"HIGH":"Alto","MEDIUM":"Médio","LOW":"Baixo"}.get(_norm(value),_level_label(value))


def _directed_reason_label(value: Any) -> str:
    raw=str(value or "").strip()
    if not raw:
        return "-"
    mapped=_DIRECTED_REASON_LABELS.get(_norm(raw))
    if mapped:
        return mapped
    if "DIRECTED_ANALYSIS_OUTPUT_INVALID" in raw:
        return (
            "A síntese estratégica por IA recebeu uma resposta incompatível com o contrato esperado. "
            "As ações técnicas persistidas permanecem disponíveis."
        )
    if raw.startswith("AI_PROVIDER_UNAVAILABLE:"):
        return (
            "A síntese estratégica por IA não pôde ser concluída pelo provedor configurado. "
            "As ações técnicas persistidas permanecem disponíveis."
        )
    if raw.startswith("DIRECTED_ANALYSIS_ERROR:"):
        return "A síntese estratégica encontrou um erro técnico e foi concluída com limitações."
    if re.fullmatch(r"[A-Z0-9_:=.-]+",raw):
        return "Limitação técnica registrada para a síntese estratégica."
    return raw


def _directed_status(value: Any) -> str:
    raw=_norm(value)
    return {
        "NO_ACTIONS":"Sem ações aplicáveis",
        "DISABLED":"Dados técnicos disponíveis; síntese estratégica por IA não solicitada",
        "COMPLETE":"Concluída",
        "COMPLETE_WITH_LIMITATIONS":"Concluída com limitações",
    }.get(raw,_status_label(value))


def _passive_security_finding_id(
    audit_id: str,
    page_id: Any,
    code: str,
    title: str,
) -> str:
    """Reproduce the persisted passive-security stable key for legacy target lookup."""
    raw="\\x1f".join(str(part or "") for part in (audit_id,page_id,code,title))
    return "SEC-"+sha256(raw.encode("utf-8")).hexdigest()[:24]


def _action_target_contexts(
    connection: sqlite3.Connection,
    audit_id: str,
    actions: Sequence[Mapping[str,Any]],
) -> dict[str,dict[str,str]]:
    """Resolve human-safe action targets only from already-persisted evidence."""
    security_actions=[
        action for action in actions
        if _norm(action.get("source_kind"))=="SECURITY_REMEDIATION"
        and str(action.get("source_id") or "").strip()
    ]
    if not security_actions:
        return {}
    try:
        remediations={
            str(row["remediation_id"]):dict(row)
            for row in connection.execute(
                "SELECT remediation_id,finding_id FROM passive_security_remediations WHERE audit_id=?",
                (audit_id,),
            ).fetchall()
        }
        findings={
            str(row["finding_id"]):dict(row)
            for row in connection.execute(
                """SELECT finding_id,page_id,url_scope,category,title,description
                   FROM passive_security_findings WHERE audit_id=?""",
                (audit_id,),
            ).fetchall()
        }
        resources=[
            dict(row)
            for row in connection.execute(
                """SELECT resource_id,page_id,page_url,resource_url,resource_kind,party
                   FROM passive_security_resources WHERE audit_id=?""",
                (audit_id,),
            ).fetchall()
        ]
    except sqlite3.Error:
        return {}

    resource_for_finding: dict[str,dict[str,Any]]={}
    for finding_id,finding in findings.items():
        title=str(finding.get("title") or "")
        if "SRI" not in title.upper():
            continue
        page_id=str(finding.get("page_id") or "")
        for resource in resources:
            if str(resource.get("page_id") or "")!=page_id:
                continue
            resource_id=str(resource.get("resource_id") or "")
            if not resource_id:
                continue
            expected=_passive_security_finding_id(
                audit_id,
                page_id,
                f"SRI_{resource_id}",
                title,
            )
            if expected==finding_id:
                resource_for_finding[finding_id]=resource
                break

    contexts: dict[str,dict[str,str]]={}
    for action in security_actions:
        action_id=str(action.get("action_id") or "")
        remediation=remediations.get(str(action.get("source_id") or ""))
        if not remediation:
            continue
        finding=findings.get(str(remediation.get("finding_id") or ""))
        if not finding:
            continue
        description=str(finding.get("description") or "")
        category=_norm(finding.get("category"))
        url_scope=str(finding.get("url_scope") or "").strip()
        cookie_match=re.search(r"\\bSet-Cookie\\s*#(\\d+)",description,re.IGNORECASE)
        if category=="COOKIES" and cookie_match:
            occurrence=f"Set-Cookie #{cookie_match.group(1)}"
            label=occurrence+(f" · {url_scope}" if url_scope else "")
            contexts[action_id]={
                "label":label,
                "note":(
                    "Esta ação se aplica a esta ocorrência de Set-Cookie. "
                    "O nome e o valor do cookie permanecem ocultos; o mesmo Set-Cookie pode aparecer em mais de uma ação quando diferentes atributos precisam de correção."
                ),
            }
            continue
        resource=resource_for_finding.get(str(finding.get("finding_id") or ""))
        if resource:
            resource_url=str(resource.get("resource_url") or "").strip()
            kind={"SCRIPT":"Script","STYLESHEET":"Stylesheet"}.get(
                _norm(resource.get("resource_kind")),
                "Recurso",
            )
            label=(f"{kind} externo · {resource_url}" if resource_url else f"{kind} externo persistido")
            contexts[action_id]={
                "label":label,
                "note":(
                    "Esta ação se aplica ao recurso externo persistido acima. "
                    "Recursos com o mesmo tipo de achado continuam sendo ocorrências independentes."
                ),
            }
    return contexts


def _action_target_label(
    action: Mapping[str,Any],
    target_by_id: Mapping[str,Mapping[str,str]],
) -> str:
    context=target_by_id.get(str(action.get("action_id") or ""),{})
    return str(context.get("label") or "-")


def _group_actions_by_title(actions: Sequence[Mapping[str,Any]]) -> list[list[Mapping[str,Any]]]:
    groups: dict[str,list[Mapping[str,Any]]]={}
    order: list[str]=[]
    for action in actions:
        key=str(action.get("title") or "-")
        if key not in groups:
            groups[key]=[]
            order.append(key)
        groups[key].append(action)
    return [groups[key] for key in order]


def _target_summary(
    actions: Sequence[Mapping[str,Any]],
    target_by_id: Mapping[str,Mapping[str,str]],
    *,
    limit: int=3,
) -> str:
    labels=[]
    for action in actions:
        label=_action_target_label(action,target_by_id)
        if label!="-" and label not in labels:
            labels.append(label)
    count=len(actions)
    if count==1:
        return labels[0] if labels else "1 ocorrência técnica"
    if not labels:
        return f"{count} ocorrências técnicas distintas"
    shown=labels[:max(1,limit)]
    suffix=(f"; +{len(labels)-len(shown)} — ver Ações estratégicas" if len(labels)>len(shown) else "")
    return f"{count} ocorrências: "+"; ".join(shown)+suffix


def _common_field_label(
    actions: Sequence[Mapping[str,Any]],
    field: str,
    labeler: Any,
    empty: str,
) -> str:
    values=[action.get(field) for action in actions if action.get(field)]
    normalized={_norm(value) for value in values}
    if not values:
        return empty
    if len(normalized)==1:
        return str(labeler(values[0]))
    return "Variável entre as ocorrências"


def _merged_dimension_labels(actions: Sequence[Mapping[str,Any]]) -> str:
    gain_rank={"LOW":1,"MEDIUM":2,"HIGH":3}
    best: dict[str,str]={}
    for action in actions:
        dimensions=_json(action.get("affected_dimensions_json"),[])
        for item in dimensions if isinstance(dimensions,list) else []:
            if not isinstance(item,Mapping):
                continue
            dimension=str(item.get("dimension") or "")
            gain=_norm(item.get("expected_gain"))
            if not dimension:
                continue
            previous=best.get(dimension)
            if previous is None or gain_rank.get(gain,0)>gain_rank.get(previous,0):
                best[dimension]=gain
    return ", ".join(
        f"{_dimension_label(dimension)} ({_gain_label(gain)})"
        for dimension,gain in sorted(best.items(),key=lambda item:_dimension_label(item[0]))
    ) or "-"


def _links(values: Any, *, label_prefix: str) -> _Html:
    refs=_json(values,[])
    if not isinstance(refs,list) or not refs:
        return _Html("<span class='muted'>Sem referência aplicável.</span>")
    links=[]
    for index,ref in enumerate(refs,1):
        if not isinstance(ref,Mapping):
            continue
        href=str(ref.get("href") or "").strip()
        if not href:
            continue
        catalog=str(ref.get("catalog_id") or "CAT")
        section_raw=str(ref.get("section_id") or "")
        section=_SECTION_LABELS_DIRECTED.get(section_raw, "Seção")
        topic=str(ref.get("topic") or "").strip()
        title=" → ".join(v for v in (catalog,section,topic) if v)
        links.append(
            "<a class='ref' href='"+escape(href,quote=True)+"' title='"+escape(title,quote=True)+"'>"
            +escape(f"{label_prefix} {index}: {catalog} → {section}")
            +"</a>"
        )
    return _Html("<div class='pill-list'>"+"".join(links)+"</div>" if links else "<span class='muted'>Sem referência aplicável.</span>")


def _action_modal(
    action: Mapping[str,Any],
    by_id: Mapping[str,Mapping[str,Any]],
    target_by_id: Mapping[str,Mapping[str,str]],
) -> str:
    action_id=str(action.get("action_id") or "")
    title_token=re.sub(r"[^a-z0-9_-]+","-",str(action.get("title") or "acao").casefold()).strip("-") or "acao"
    modal_id="directed-"+title_token[:48]+"-"+sha256(action_id.encode("utf-8")).hexdigest()[:8]
    dimensions=_json(action.get("affected_dimensions_json"),[])
    dependencies=_json(action.get("dependencies_json"),[])
    guidance=_json(action.get("implementation_guidance_json"),[])
    validation=_json(action.get("validation_steps_json"),[])
    source_refs=_json(action.get("source_refs_json"),[])
    evidence_refs=_json(action.get("evidence_refs_json"),[])
    remediation_refs=_json(action.get("remediation_refs_json"),[])
    dim_rows=[
        (_dimension_label(item.get("dimension")),_gain_label(item.get("expected_gain")))
        for item in dimensions if isinstance(item,Mapping)
    ]
    dep_rows=[]
    for dep in dependencies if isinstance(dependencies,list) else []:
        dep_action=by_id.get(str(dep),{})
        dep_rows.append((dep_action.get("title") or "Ação relacionada",))
    target_context=target_by_id.get(action_id,{})
    pairs=[("Alvo / ocorrência",target_context.get("label") or "Consulte a origem técnica persistida.")]
    if target_context.get("note"):
        pairs.append(("Como interpretar esta ocorrência",target_context.get("note")))
    pairs.extend((
        ("Por que agir",action.get("reason") or "-"),
        ("Objetivo principal",action.get("primary_objective") or "Não consolidado pela IA"),
        ("Prioridade",_level_label(action.get("priority")) if action.get("priority") else "Não consolidada"),
        ("Esforço",_level_label(action.get("effort")) if action.get("effort") else "Não consolidado"),
        ("Confiança",_confidence_label(action.get("confidence")) if action.get("confidence") else "Não consolidada"),
        ("Justificativa da confiança",action.get("confidence_rationale") or "Não consolidada pela IA"),
        ("Estado da análise","Analisada pela IA" if _norm(action.get("analysis_state"))=="AI_ANALYZED" else "Base técnica persistida; síntese estratégica não materializada"),
    ))
    body=_kv(tuple(pairs))
    body+="<h3>Impacto multidimensional</h3>"+_table(("Dimensão","Ganho esperado"),dim_rows,empty="Nenhuma dimensão adicional foi materializada.")
    if dep_rows:
        body+="<h3>Dependências</h3>"+_table(("Ação relacionada",),dep_rows)
    body+="<h3>Como implementar</h3>"+(
        "<ol>"+"".join("<li>"+escape(str(v))+"</li>" for v in guidance)+"</ol>"
        if isinstance(guidance,list) and guidance else "<p class='muted'>Consulte a remediação técnica de origem.</p>"
    )
    body+="<h3>Como validar</h3>"+(
        "<ol>"+"".join("<li>"+escape(str(v))+"</li>" for v in validation)+"</ol>"
        if isinstance(validation,list) and validation else "<p class='muted'>Reexecute o CAT e a métrica de origem após a correção.</p>"
    )
    body+="<h3>Origem técnica</h3>"+str(_links(source_refs,label_prefix="Origem"))
    body+="<h3>Evidências</h3>"+str(_links(evidence_refs,label_prefix="Evidência"))
    body+="<h3>Correção técnica / remediação</h3>"+str(_links(remediation_refs,label_prefix="Remediação"))
    body+="<div class='notice'>Os links são construídos pelo RASAi a partir de referências persistidas e seções estáveis dos CATs. A IA não cria nomes de arquivo, anchors ou identificadores de evidência.</div>"
    return modal_id,_modal(modal_id,action.get("title") or "Ação estratégica","Análise Direcionada · ação estratégica",body)


def directed_analysis_body(database: Any, data: Any) -> str:
    connection=sqlite3.connect(database); connection.row_factory=sqlite3.Row
    try:
        run=_one(connection,"directed_analysis_runs",data.audit_id)
        actions=_rows(connection,"directed_analysis_actions",data.audit_id)
        target_by_id=_action_target_contexts(connection,data.audit_id,actions)
    finally:
        connection.close()

    body=_audit_hero(
        data,
        "Análise Direcionada",
        "Camada estratégica auditável: correlaciona os resultados já persistidos nos CATs, sem executar novas coletas e sem transformar inferência de IA em fato técnico.",
    )
    body+=_outline((
        ("summary","Resumo estratégico"),
        ("transversal","Maior ganho transversal"),
        ("roadmap","Plano de ação"),
        ("objectives","Visões por objetivo"),
        ("actions","Ações"),
        ("traceability","Rastreabilidade"),
        ("limitations","Limitações"),
    ))

    if not run:
        body+=_section(
            "summary","Resumo estratégico",
            "<div class='notice warn'><strong>Análise Direcionada não materializada.</strong> "
            "Os dados técnicos continuam disponíveis nos CATs. Esta página não executa IA nem coleta durante a renderização.</div>",
        )
        return body

    status=_directed_status(run.get("status"))
    summary=_json(run.get("strategic_summary_json"),{})
    roadmap=_json(run.get("roadmap_json"),[])
    limitations=_json(run.get("limitations_json"),[])
    by_id={str(action.get("action_id")):action for action in actions}

    summary_html=(
        "<div class='metric-grid'>"
        +_metric("Estado",status)
        +_metric("Ações técnicas",len(actions))
        +_metric("Ações analisadas pela IA",run.get("ai_actions_count") or 0)
        +_metric("Provedor",run.get("provider") or "Não utilizado")
        +_metric("Modelo",run.get("model") or "Não utilizado")
        +"</div>"
    )
    if _norm(run.get("status"))=="DISABLED":
        summary_html+="<div class='notice'>A síntese estratégica por IA não foi solicitada para esta auditoria. Ações e referências técnicas persistidas permanecem disponíveis, mas o relatório não inventa priorização, esforço, confiança ou dependências estratégicas.</div>"
    elif _norm(run.get("status"))=="COMPLETE_WITH_LIMITATIONS":
        summary_html+="<div class='notice warn'>A camada estratégica foi materializada com limitações. Os fatos técnicos e referências persistidas permanecem válidos; campos não sustentados não são preenchidos por inferência.</div>"
    elif _norm(run.get("status"))=="NO_ACTIONS":
        summary_html+="<div class='notice'>Nenhuma recomendação acionável governada foi encontrada nos dados persistidos desta auditoria. Isso não equivale a declarar que a URL não possui problemas.</div>"

    categories=(
        ("Pontos fortes","strengths"),
        ("Fragilidades principais","fragilities"),
        ("Riscos","risks"),
        ("Oportunidades","opportunities"),
        ("Evidência insuficiente","insufficient_evidence"),
    )
    cards=[]
    if isinstance(summary,Mapping):
        for title,key in categories:
            items=summary.get(key)
            if isinstance(items,list) and items:
                cards.append("<div class='card'><h3>"+escape(title)+"</h3><ul>"+"".join("<li>"+escape(str(v))+"</li>" for v in items)+"</ul></div>")
        if summary.get("plan_overview"):
            summary_html+="<div class='notice'><strong>Visão geral do plano:</strong> "+escape(str(summary.get("plan_overview")))+"</div>"
    if cards:
        summary_html+="<div class='grid'>"+"".join(cards)+"</div>"
    body+=_section("summary","Resumo estratégico",summary_html)

    def transversal_score(action: Mapping[str,Any]) -> tuple[int,int,int,str]:
        dims=_json(action.get("affected_dimensions_json"),[])
        dim_count=len(dims) if isinstance(dims,list) else 0
        gain=sum({"HIGH":3,"MEDIUM":2,"LOW":1}.get(_norm(v.get("expected_gain")),0) for v in dims if isinstance(v,Mapping))
        effort={"LOW":3,"MEDIUM":2,"HIGH":1}.get(_norm(action.get("effort")),0)
        priority={"CRITICAL":4,"HIGH":3,"MEDIUM":2,"LOW":1}.get(_norm(action.get("priority")),0)
        return (dim_count,gain+effort,priority,str(action.get("action_id") or ""))

    top=sorted(actions,key=transversal_score,reverse=True)[:8]
    trans_rows=[]
    for action in top:
        dims=_json(action.get("affected_dimensions_json"),[])
        labels=", ".join(
            f"{_dimension_label(v.get('dimension'))} ({_gain_label(v.get('expected_gain'))})"
            for v in dims if isinstance(v,Mapping)
        )
        trans_rows.append((
            action.get("title") or "-",
            _level_label(action.get("effort")) if action.get("effort") else "Não consolidado",
            _confidence_label(action.get("confidence")) if action.get("confidence") else "Não consolidada",
            _level_label(action.get("priority")) if action.get("priority") else "Não consolidada",
            labels or "-",
        ))
    body+=_section(
        "transversal","O que corrigir para obter maior ganho transversal",
        _table(("Ação","Esforço","Confiança","Prioridade","Dimensões / ganho"),trans_rows,empty="Não há ações suficientes para uma visão transversal."),
    )

    roadmap_html=""
    if isinstance(roadmap,list) and roadmap:
        for phase in roadmap:
            if not isinstance(phase,Mapping):
                continue
            ids=[str(v) for v in phase.get("action_ids",[]) if str(v) in by_id]
            rows=[(by_id[action_id].get("title") or "-",) for action_id in ids]
            roadmap_html+="<div class='card'><h3>"+escape(str(phase.get("phase") or "Fase"))+"</h3><p>"+escape(str(phase.get("objective") or ""))+"</p>"+_table(("Ação",),rows,empty="Nenhuma ação vinculada.")+"</div>"
    if not roadmap_html:
        roadmap_html="<div class='notice'>Ordem estratégica não materializada. O relatório não fabrica uma sequência quando a IA estratégica não produziu uma resposta válida.</div>"
    body+=_section("roadmap","Plano geral de ação","<div class='grid'>"+roadmap_html+"</div>" if roadmap_html.startswith("<div class='card'>") else roadmap_html)

    dimensions={}
    for action in actions:
        for item in _json(action.get("affected_dimensions_json"),[]):
            if not isinstance(item,Mapping):
                continue
            key=str(item.get("dimension") or "")
            if key:
                dimensions.setdefault(key,[]).append((action,item))
    objective_blocks=[]
    for key,items in sorted(dimensions.items(),key=lambda kv:_dimension_label(kv[0])):
        rows=[]
        for action,impact in items:
            rows.append((
                action.get("title") or "-",
                _gain_label(impact.get("expected_gain")),
                _level_label(action.get("priority")) if action.get("priority") else "Não consolidada",
                _level_label(action.get("effort")) if action.get("effort") else "Não consolidado",
                _confidence_label(action.get("confidence")) if action.get("confidence") else "Não consolidada",
            ))
        objective_blocks.append("<details><summary>"+escape(_dimension_label(key))+"</summary><div class='detail-body'>"+_table(("Ação","Ganho","Prioridade","Esforço","Confiança"),rows)+"</div></details>")
    body+=_section("objectives","Visões por objetivo","".join(objective_blocks) or "<div class='notice'>Nenhuma dimensão estratégica foi materializada.</div>")

    action_rows=[];modals=[]
    for action in actions:
        modal_id,modal=_action_modal(action,by_id)
        dimensions_list=_json(action.get("affected_dimensions_json"),[])
        action_rows.append((
            action.get("title") or "-",
            _level_label(action.get("priority")) if action.get("priority") else "Não consolidada",
            _level_label(action.get("effort")) if action.get("effort") else "Não consolidado",
            _confidence_label(action.get("confidence")) if action.get("confidence") else "Não consolidada",
            len(dimensions_list) if isinstance(dimensions_list,list) else 0,
            _modal_button(modal_id,"Ver estratégia"),
        ))
        modals.append(modal)
    body+=_section(
        "actions","Ações estratégicas",
        _table(("Ação","Prioridade","Esforço","Confiança","Dimensões","Detalhe"),action_rows,empty="Nenhuma ação foi materializada.",sortable=bool(action_rows),page_size=10 if len(action_rows)>10 else None)+"".join(modals),
    )

    trace_rows=[]
    for action in actions:
        trace_rows.append((
            action.get("title") or "-",
            _links(action.get("source_refs_json"),label_prefix="Origem"),
            _links(action.get("evidence_refs_json"),label_prefix="Evidência"),
            _links(action.get("remediation_refs_json"),label_prefix="Correção"),
        ))
    body+=_section(
        "traceability","Rastreabilidade CAT → seção → assunto",
        "<p class='section-lead'>Cada ação usa somente referências criadas e validadas pelo sistema. Alterações de título/idioma não são usadas para compor o destino do link.</p>"
        +_table(("Ação","Origem","Evidência","Correção técnica"),trace_rows,empty="Nenhuma cadeia de rastreabilidade materializada."),
    )

    limitation_rows=[]
    if isinstance(limitations,list):
        for item in limitations:
            if isinstance(item,Mapping):
                raw_scope=str(item.get("catalog_id") or item.get("scope") or "Auditoria")
                scope="Análise direcionada" if _norm(raw_scope)=="DIRECTED_ANALYSIS" else raw_scope
                raw_reason=str(item.get("reason") or "")
                reason=_directed_reason_label(raw_reason)
                limitation_rows.append((
                    scope,
                    _status_label(item.get("status")) if item.get("status") else reason or "Limitação",
                    item.get("detail") or reason or "-",
                ))
            else:
                limitation_rows.append(("Auditoria","Limitação",str(item)))
    body+=_section(
        "limitations","Limitações e evidência insuficiente",
        _table(("Escopo","Estado","Detalhe"),limitation_rows,empty="Nenhuma limitação adicional foi persistida para a Análise Direcionada.")
        +"<div class='notice'><strong>Regra de interpretação:</strong> ausência de evidência nunca é convertida em conclusão negativa. Quando os dados não sustentam uma conclusão, o estado permanece explicitamente insuficiente/indeterminado.</div>",
    )
    return body


__all__=["directed_analysis_body"]
