"""Read-only report projection for the evidence-bound Directed Analysis."""
from __future__ import annotations

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
    return _DIMENSION_LABELS_DIRECTED.get(raw, str(value or "-").replace("_"," ").title())


def _gain_label(value: Any) -> str:
    return {"HIGH":"Alto","MEDIUM":"Médio","LOW":"Baixo"}.get(_norm(value),_level_label(value))


def _directed_reason_label(value: Any) -> str:
    raw=str(value or "").strip()
    if not raw:
        return "-"
    mapped=_DIRECTED_REASON_LABELS.get(_norm(raw))
    if mapped:
        return mapped
    if raw.startswith("DIRECTED_ANALYSIS_ERROR:"):
        return "A síntese estratégica encontrou um erro técnico e foi concluída com limitações."
    if re.fullmatch(r"[A-Z0-9_:-]+",raw):
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


def _action_modal(action: Mapping[str,Any], by_id: Mapping[str,Mapping[str,Any]]) -> str:
    action_id=str(action.get("action_id") or "")
    modal_id="directed-"+re.sub(r"[^a-z0-9_-]+","-",action_id.casefold()).strip("-")
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
    body=_kv((
        ("Por que agir",action.get("reason") or "-"),
        ("Objetivo principal",action.get("primary_objective") or "Não consolidado pela IA"),
        ("Prioridade",_level_label(action.get("priority")) if action.get("priority") else "Não consolidada"),
        ("Esforço",_level_label(action.get("effort")) if action.get("effort") else "Não consolidado"),
        ("Confiança",_confidence_label(action.get("confidence")) if action.get("confidence") else "Não consolidada"),
        ("Justificativa da confiança",action.get("confidence_rationale") or "Não consolidada pela IA"),
        ("Estado da análise","Analisada pela IA" if _norm(action.get("analysis_state"))=="AI_ANALYZED" else "Base técnica persistida; síntese estratégica não materializada"),
    ))
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
