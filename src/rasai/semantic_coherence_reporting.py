"""Compact, audit-traceable CAT-03 projection for semantic coherence and assessments."""
from __future__ import annotations

from collections import Counter
from html import escape
import json
import sqlite3
from typing import Any

from rasai.score_geo_004 import DIMENSION_WEIGHTS, RULE_SCORING_CONTRACT
from rasai.semantic_coherence import PAGE_COHERENCE_CRITERIA, PROPERTY_COHERENCE_CRITERIA
from rasai.catalog_report_public_labels import public_label

_INSTALLED = False

_RESULT_LABELS = {
    "COHERENT": "Coerente", "PARTIAL": "Parcial", "INCOHERENT": "Incoerente",
    "NOT_DETERMINABLE": "Não determinável", "NOT_APPLICABLE": "Não aplicável",
    "PASS": "Aprovado", "FAIL": "Não aprovado", "WARNING": "Atenção", "UNKNOWN": "Não determinável",
}
_PROPERTY_LABELS = {
    "business_sector": "Setor / ramo", "business_description": "Descrição do negócio",
    "primary_offering": "Oferta principal", "target_audience_profile": "Público-alvo detalhado",
    "primary_goal": "Objetivo principal", "positioning": "Posicionamento",
}
_DIMENSION_ORIGINAL_EN = {
    "DISCOVERY_ACCESS": "Discovery & Crawler Access",
    "INDEXABILITY": "Indexability",
    "CONTENT_EXTRACTABILITY": "Rendering & Extractability",
    "SEMANTIC_STRUCTURE": "Semantic Structure",
    "ENTITY_CLARITY": "Entity Clarity",
    "STRUCTURED_DATA": "Structured Data",
    "ANSWERABILITY": "Answerability",
    "CITATION_READINESS": "Citation Readiness",
    "EVIDENCE_TRUST": "Evidence & Trust",
    "INTENT_COVERAGE": "Intent Coverage",
    "CONTENT_VALUE": "Content Value",
    "NON_SCORING": "Non-scoring",
}
_DIMENSION_LABELS = {
    "DISCOVERY_ACCESS": "Acesso e descoberta",
    "INDEXABILITY": "Capacidade de indexação",
    "CONTENT_EXTRACTABILITY": "Extração de conteúdo",
    "SEMANTIC_STRUCTURE": "Estrutura semântica",
    "ENTITY_CLARITY": "Clareza de entidades",
    "STRUCTURED_DATA": "Dados estruturados",
    "ANSWERABILITY": "Capacidade de resposta",
    "CITATION_READINESS": "Preparação para citação",
    "EVIDENCE_TRUST": "Evidências e confiabilidade",
    "INTENT_COVERAGE": "Cobertura de intenções",
    "CONTENT_VALUE": "Valor do conteúdo",
    "NON_SCORING": "Não participa da pontuação",
}

_PROPERTY_COHERENCE_LABELS = {
    "SC-X01": "Identidade da organização permanece coerente entre as páginas auditadas",
    "SC-X02": "Oferta principal permanece alinhada entre as páginas e o contexto declarado",
    "SC-X03": "Público-alvo permanece alinhado entre as páginas e o contexto declarado",
    "SC-X04": "Posicionamento permanece alinhado entre as páginas e o contexto declarado",
    "SC-X05": "Objetivo principal e chamadas para ação permanecem alinhados entre as páginas",
    "SC-X06": "Propósitos das páginas permanecem alinhados ao contexto da propriedade sem contradição material",
}

_PAGE_COHERENCE_LABELS = {
    "SC-P01": "Título e conteúdo principal visível expressam o mesmo assunto principal",
    "SC-P02": "Headings e conteúdo principal visível expressam uma hierarquia semântica coerente",
    "SC-P03": "Propósito declarado ou interpretado é coerente com o conteúdo visível e a intenção do usuário",
    "SC-P04": "Público declarado ou interpretado é coerente com linguagem, profundidade e terminologia",
    "SC-P05": "Oferta principal declarada está representada de forma coerente quando aplicável",
    "SC-P06": "Posicionamento declarado está representado de forma coerente quando aplicável",
    "SC-P07": "Entidades observadas são coerentes com o conteúdo visível",
    "SC-P08": "Dados estruturados são coerentes com o conteúdo visível",
    "SC-P09": "Entidades dos dados estruturados são coerentes com as entidades observadas no conteúdo",
    "SC-P10": "Chamadas para ação são coerentes com o propósito da página e o objetivo declarado quando aplicável",
    "SC-P11": "Claims materiais apresentam suporte ou qualificação observável suficiente para o contexto",
    "SC-P12": "Sinais de autoria ou responsabilidade são coerentes com o risco editorial e os requisitos de confiança",
    "SC-P13": "Sinais de publicação e atualização são coerentes com a sensibilidade temporal da página",
}


def _dimension_label(value: Any) -> Any:
    token = str(value or "NON_SCORING").upper()
    return _DIMENSION_LABELS.get(token, public_label(token) or token.replace("_", " ").title())


_CONTENT_LABELS = {
    "page_purpose": "Propósito da página", "intended_audience": "Público pretendido",
    "content_origin": "Origem do conteúdo", "risk_profile": "Perfil de risco",
    "ymyl_category": "Categoria YMYL", "experience_requirement": "Requisito de experiência",
    "freshness_sensitivity": "Sensibilidade à atualização",
}


def _table_exists(connection: sqlite3.Connection, name: str) -> bool:
    return connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1", (name,)).fetchone() is not None


def _rows(database: Any, audit_id: str, table: str) -> list[dict[str, Any]]:
    connection = sqlite3.connect(database); connection.row_factory = sqlite3.Row
    try:
        if not _table_exists(connection, table): return []
        columns={str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})")}
        if "audit_id" not in columns:return []
        return [dict(row) for row in connection.execute(f"SELECT * FROM {table} WHERE audit_id=?", (audit_id,)).fetchall()]
    finally: connection.close()


def _confidence(value: Any) -> str:
    try: return f"{float(value) * 100:.0f}%"
    except (TypeError, ValueError): return "-"


def _status(value: Any) -> str:
    token = str(value or "NOT_DETERMINABLE").upper()
    return _RESULT_LABELS.get(token, public_label(value) or token.replace("_", " ").title())


def _json_list(value: Any) -> list[Any]:
    if isinstance(value,list):return value
    try:
        parsed=json.loads(str(value or "[]"))
        return parsed if isinstance(parsed,list) else []
    except (TypeError,ValueError,json.JSONDecodeError):return []


def _context_html(evidence: Any, database: Any, audit_id: str) -> str:
    property_rows = _rows(database, audit_id, "property_semantic_contexts")
    content_rows = _rows(database, audit_id, "content_analysis_contexts")
    manifest_rows = _rows(database, audit_id, "semantic_corpus_manifests")
    blocks: list[str] = []
    property_values=[]
    if property_rows:
        row=property_rows[0]
        for key,label in _PROPERTY_LABELS.items():
            raw=str(row.get(key) or "auto"); property_values.append((label,raw,"Automático" if raw.casefold()=="auto" else "Declarado"))
    else: property_values=[(label,"auto","Automático") for label in _PROPERTY_LABELS.values()]
    blocks.append("<div class='subsection'><h3>Contexto da propriedade</h3>"+evidence._table(("Campo","Valor usado","Origem"),property_values)+"<p class='muted'>Contexto declarado é entrada da auditoria, não evidência observada e não altera a pontuação por si só.</p></div>")
    content_values=[]
    if content_rows:
        row=content_rows[0]
        for key,label in _CONTENT_LABELS.items():
            raw=str(row.get(key) or "auto"); content_values.append((label,raw,"Automático" if raw.casefold()=="auto" else "Declarado"))
    if content_values:
        blocks.append("<div class='subsection'><h3>Contexto editorial, risco e confiança</h3>"+evidence._table(("Campo","Valor usado","Origem"),content_values)+"</div>")
    if manifest_rows:
        manifest=manifest_rows[0]
        try:
            page_count=len(json.loads(str(manifest.get("page_ids_json") or "[]"))); snapshot_count=len(json.loads(str(manifest.get("snapshot_ids_json") or "[]")))
        except (TypeError,ValueError,json.JSONDecodeError):page_count=snapshot_count=0
        blocks.append("<div class='notice'><strong>Gate semântico:</strong> "+f"{escape(str(manifest.get('status') or '-'))}. O contexto foi congelado antes da primeira chamada de IA; corpus com {page_count} página(s) e {snapshot_count} captura(s). A agregação entre páginas usa apenas resultados já persistidos e não gera uma chamada adicional.</div>")
    return "".join(blocks)


def _auto_interpretation_html(evidence: Any, database: Any, audit_id: str) -> str:
    rows=sorted(_rows(database,audit_id,"content_context_interpretations"),key=lambda r:(str(r.get("page_url") or ""),int(r.get("sequence_no") or 0),str(r.get("field_name") or "")))
    if not rows:
        return "<div class='subsection'><h3>Interpretações AUTO aplicadas</h3><div class='notice'>Nenhuma interpretação AUTO estruturada foi persistida nesta execução. Campos configurados explicitamente continuam sendo a fonte de contexto; ausência desta tabela não é convertida em inferência.</div></div>"
    table_rows=[];modals=[]
    for index,row in enumerate(rows,1):
        field=str(row.get("field_name") or ""); modal_id=f"auto-context-{index}"
        table_rows.append((row.get("page_url") or row.get("snapshot_id") or "-",_CONTENT_LABELS.get(field,field.replace("_"," ").title()),"AUTO",_status(row.get("status")),row.get("interpreted_value") or "Não determinável",_confidence(row.get("confidence")),evidence._modal_button(modal_id,"Ver interpretação")))
        ids=_json_list(row.get("evidence_ids_json"))
        body=evidence._kv((("Configuração canônica","AUTO"),("Interpretação aplicada",row.get("interpreted_value") or "Não determinável"),("Status",_status(row.get("status"))),("Origem","Inferência de IA desta execução"),("Confiança",_confidence(row.get("confidence"))),("Justificativa",row.get("rationale") or "-"),("Evidências",", ".join(str(v) for v in ids) or "-"),("Provedor",row.get("provider") or "-"),("Modelo",row.get("model") or "-"),("Sequência da chamada",row.get("sequence_no") or "-"),("Contrato",row.get("contract_version") or "-"),("Impacto direto na pontuação","Não"),("Persistida como",row.get("interpretation_type") or "AI_INFERENCE")))
        body+="<p class='muted'>A inferência é reconstruível para esta AUD, mas não sobrescreve a configuração AUTO e não se torna fato canônico da propriedade.</p>"
        modals.append(evidence._modal(modal_id,_CONTENT_LABELS.get(field,field),str(row.get("page_url") or row.get("snapshot_id") or "Contexto"),body))
    return "<div class='subsection'><h3>Interpretações AUTO aplicadas</h3>"+evidence._table(("Página","Campo","Configuração","Status","Interpretação","Confiança","Detalhe"),table_rows,sortable=True,page_size=10 if len(table_rows)>10 else None)+"".join(modals)+"</div>"


def _ymyl_alignment_html(evidence: Any, database: Any, audit_id: str) -> str:
    from rasai.editorial_risk_context import build_editorial_risk_context

    context = build_editorial_risk_context(database, audit_id)
    ymyl = context.get("ymyl", {})
    if not isinstance(ymyl, dict) or not bool(ymyl.get("active")):
        return ""

    interpretation = context.get("auto_interpretations", {}).get("ymyl_category", {})
    category_origin = "Configuração declarada"
    if str(ymyl.get("configured_category") or "auto").casefold() == "auto":
        category_origin = (
            "Inferência de IA desta execução"
            if isinstance(interpretation, dict)
            and str(interpretation.get("status") or "").upper() == "INTERPRETED"
            else "AUTO não determinável"
        )

    rows = [
        (
            "Perfil de risco configurado",
            ymyl.get("configured_risk_profile") or "auto",
            "Configuração canônica",
        ),
        (
            "Categoria YMYL configurada",
            ymyl.get("configured_category") or "auto",
            "Configuração canônica",
        ),
        (
            "Categoria YMYL efetiva",
            ymyl.get("effective_category") or "auto",
            category_origin,
        ),
        (
            "Relação com a parametrização do usuário",
            (ymyl.get("configuration_relation") or {}).get("label") or "Não determinável",
            "Configuração canônica × interpretação AUTO",
        ),
        (
            "Conclusão conteúdo × contexto YMYL",
            ymyl.get("alignment_label") or "Não determinável",
            "SC-P11, SC-P12 e SC-P13",
        ),
        (
            "Mudança no conteúdo",
            ymyl.get("content_change_label") or "Não determinável",
            "Derivada dos critérios YMYL persistidos",
        ),
    ]

    details: list[tuple[Any, ...]] = []
    for item in ymyl.get("coherence", []) or []:
        details.append(
            (
                item.get("page_url") or item.get("snapshot_id") or "-",
                _status(item.get("result")),
                _confidence(item.get("confidence")),
                item.get("reasoning_summary")
                or item.get("observed_context")
                or "-",
                ", ".join(str(v) for v in item.get("evidence_ids", []) or []) or "-",
            )
        )
    detail_html = (
        "<details><summary>Ver leitura YMYL por página</summary><div class='detail-body'>"
        + evidence._table(
            ("Página", "Resultado", "Confiança", "Leitura da IA", "Evidências"),
            details,
            sortable=bool(details),
            page_size=10 if len(details) > 10 else None,
        )
        + "</div></details>"
        if details
        else "<div class='notice'>SC-P11, SC-P12 e SC-P13 não produziram conclusão suficiente para esta execução; o relatório não infere aderência por conta própria.</div>"
    )
    return (
        "<div class='subsection'><h3>Contexto YMYL × conteúdo observado</h3>"
        + evidence._table(("Leitura", "Resultado", "Origem"), rows)
        + detail_html
        + "<p class='muted'>A configuração humana permanece canônica. Interpretações AUTO são inferência de IA "
        "auditável e não sobrescrevem a configuração. A conclusão acima não declara conformidade legal ou regulatória; "
        "quando houver lacunas evidence-bound, o mesmo contexto é encaminhado ao CAT-08 e suas recomendações aparecem "
        "no CAT-09.</p></div>"
    )


def _semantic_assessment_rows(database: Any, audit_id: str) -> list[dict[str,Any]]:
    connection=sqlite3.connect(database);connection.row_factory=sqlite3.Row
    try:
        required=("semantic_assessments","page_snapshots","pages")
        if any(not _table_exists(connection,name) for name in required):return []
        has_executions=_table_exists(connection,"rule_executions")
        if has_executions:
            sql="""SELECT sa.*,ps.page_id,p.normalized_url AS page_url,
                    re.rule_execution_id,re.executed_at,re.evidence_ids AS execution_evidence_ids
                FROM semantic_assessments sa
                JOIN page_snapshots ps ON ps.snapshot_id=sa.snapshot_id
                JOIN pages p ON p.page_id=ps.page_id
                LEFT JOIN rule_executions re ON re.rowid=(
                    SELECT re2.rowid FROM rule_executions re2
                    WHERE re2.audit_id=? AND re2.snapshot_id=sa.snapshot_id AND re2.rule_id=sa.assessment_type
                    ORDER BY re2.executed_at DESC,re2.rowid DESC LIMIT 1)
                WHERE p.audit_id=? ORDER BY p.normalized_url,sa.assessment_type,sa.assessment_id"""
            return [dict(row) for row in connection.execute(sql,(audit_id,audit_id))]
        sql="""SELECT sa.*,ps.page_id,p.normalized_url AS page_url,NULL AS rule_execution_id,NULL AS executed_at,NULL AS execution_evidence_ids
               FROM semantic_assessments sa JOIN page_snapshots ps ON ps.snapshot_id=sa.snapshot_id
               JOIN pages p ON p.page_id=ps.page_id WHERE p.audit_id=?
               ORDER BY p.normalized_url,sa.assessment_type,sa.assessment_id"""
        return [dict(row) for row in connection.execute(sql,(audit_id,))]
    finally:connection.close()


def _semantic_assessments_html(evidence: Any,database: Any,audit_id: str) -> str:
    rows=_semantic_assessment_rows(database,audit_id)
    if not rows:return "<div class='subsection'><h3>Avaliações semânticas</h3><div class='notice'>Nenhum assessment semântico persistido para esta AUD.</div></div>"
    table_rows=[];modals=[]
    for index,row in enumerate(rows,1):
        rule=str(row.get("assessment_type") or "");contract=RULE_SCORING_CONTRACT.get(rule);modal_id=f"semantic-assessment-{index}"
        dimension=contract.dimension if contract else "NON_SCORING";group=contract.scoring_group if contract else "-"
        origin="Baseline determinístico" if str(row.get("provider") or "").upper()=="DETERMINISTIC_BASELINE" else "IA" if str(row.get("provider") or "").upper() not in {"","NONE"} else "Determinístico/sem IA"
        table_rows.append((row.get("page_url") or "-",rule,_dimension_label(dimension),_status(row.get("result")),_confidence(row.get("confidence")),origin,evidence._modal_button(modal_id,"Ver proveniência")))
        source_ids=_json_list(row.get("evidence_ids"));execution_ids=_json_list(row.get("execution_evidence_ids"));all_ids=list(dict.fromkeys([*source_ids,*execution_ids]))
        dim_weight=DIMENSION_WEIGHTS.get(dimension);group_weight=contract.group_weight if contract else None
        body=evidence._kv((("Regra",rule),("Dimensão",_dimension_label(dimension)),("Código da dimensão",dimension),("Grupo de pontuação",group),("Resultado",_status(row.get("result"))),("Confiança",_confidence(row.get("confidence"))),("Origem da avaliação",origin),("Provedor",row.get("provider") or "-"),("Modelo",row.get("model") or "-"),("Justificativa resumida",row.get("reasoning_summary") or "-"),("Evidências fonte",", ".join(str(v) for v in source_ids) or "-"),("Evidências da execução",", ".join(str(v) for v in all_ids) or "-"),("ID da avaliação",row.get("assessment_id") or "-"),("ID da execução da regra",row.get("rule_execution_id") or "-"),("Prompt",f"{row.get('prompt_id') or '-'} / v{row.get('prompt_version') or '-'}"),("Configuração",row.get("configuration_version") or "-"),("Executado em",row.get("executed_at") or "-"),("Peso da dimensão",f"{dim_weight*100:.2f}%" if dim_weight is not None else "Não aplicável"),("Peso do grupo dentro da dimensão",f"{group_weight*100:.2f}%" if group_weight is not None else "Não aplicável"),("Impacto na pontuação","Conforme SCORE-GEO-004" if contract else "Não participa")))
        body+="<p class='muted'>O peso final por regra/escopo é calculado pelo contrato hierárquico, considerando aplicabilidade e normalização; o modelo de IA não escolhe nem altera os pesos. Veja <a href='sari.html'>SARI</a> e <a href='methodology.html'>Metodologia</a>.</p>"
        modals.append(evidence._modal(modal_id,f"{rule} · avaliação",str(row.get("page_url") or "Página"),body))
    return "<div class='subsection'><h3>Avaliações semânticas</h3>"+evidence._table(("Página","Regra","Dimensão","Resultado","Confiança","Origem","Detalhe"),table_rows,sortable=True,page_size=10 if len(table_rows)>10 else None)+"".join(modals)+"</div>"


def _property_summary_html(evidence: Any, database: Any, audit_id: str) -> str:
    summaries=sorted(_rows(database,audit_id,"property_semantic_summaries"),key=lambda row:str(row.get("criterion_id")))
    if not summaries:return "<div class='subsection'><h3>Coerência da propriedade</h3><div class='notice'>A análise de coerência da propriedade não produziu dados nesta execução. A coleta determinística e as demais evidências do CAT-03 permanecem válidas.</div></div>"
    table_rows=[];modals=[]
    for index,row in enumerate(summaries,1):
        criterion=str(row.get("criterion_id") or "");modal_id=f"property-coherence-{index}"
        table_rows.append((_PROPERTY_COHERENCE_LABELS.get(criterion,PROPERTY_COHERENCE_CRITERIA.get(criterion,criterion)),_status(row.get("result")),_confidence(row.get("confidence")),int(row.get("observation_count") or 0),evidence._modal_button(modal_id,"Ver análise")))
        ids=_json_list(row.get("evidence_ids_json"))
        body=evidence._kv((("Critério",criterion),("Resultado",_status(row.get("result"))),("Confiança agregada",_confidence(row.get("confidence"))),("Páginas/observações consideradas",row.get("observation_count") or 0),("Leitura",row.get("summary") or "-"),("Evidências relacionadas",", ".join(str(item) for item in ids) or "-")))
        modals.append(evidence._modal(modal_id,_PROPERTY_COHERENCE_LABELS.get(criterion,PROPERTY_COHERENCE_CRITERIA.get(criterion,criterion)),"Agregação determinística entre páginas",body))
    divergent=sum(1 for row in summaries if str(row.get("result")) in {"PARTIAL","INCOHERENT"})
    note=f"<p class='muted'>{divergent} dimensão(ões) com divergência ou coerência parcial. A implementação de correções fica centralizada em <a href='cat-09.html'>CAT-09 · Remediações</a>.</p>" if divergent else ""
    return "<div class='subsection'><h3>Coerência da propriedade</h3>"+evidence._table(("Dimensão","Resultado","Confiança","Base","Detalhe"),table_rows,sortable=True)+note+"".join(modals)+"</div>"


def _page_summary_html(evidence: Any, database: Any, audit_id: str) -> str:
    rows=_rows(database,audit_id,"semantic_coherence_assessments")
    if not rows:return "<div class='subsection'><h3>Coerência semântica por página</h3><div class='notice'>Nenhuma avaliação de coerência por IA foi persistida. Isso não invalida conteúdo/estrutura/JSON-LD coletados deterministicamente.</div></div>"
    grouped={}
    for row in rows:grouped.setdefault(str(row.get("criterion_id") or ""),[]).append(row)
    table_rows=[];modals=[]
    for index,criterion in enumerate(PAGE_COHERENCE_CRITERIA,1):
        items=grouped.get(criterion,[]);counts=Counter(str(item.get("result") or "NOT_DETERMINABLE") for item in items);divergence=counts.get("PARTIAL",0)+counts.get("INCOHERENT",0);confidence=sum(float(item.get("confidence") or 0) for item in items)/len(items) if items else 0.0;modal_id=f"page-coherence-{index}"
        state="Incoerente" if counts.get("INCOHERENT") else "Parcial" if divergence else "Coerente" if items else "Não determinável"
        table_rows.append((_PAGE_COHERENCE_LABELS.get(criterion,PAGE_COHERENCE_CRITERIA[criterion]),state,_confidence(confidence),divergence,evidence._modal_button(modal_id,"Ver páginas")))
        details=[(item.get("page_url") or "-",_status(item.get("result")),_confidence(item.get("confidence")),item.get("observed_context") or "-") for item in sorted(items,key=lambda value:(str(value.get("page_url")),str(value.get("snapshot_id"))))]
        body=evidence._table(("Página","Resultado","Confiança","Observado"),details,sortable=bool(details),page_size=10 if len(details)>10 else None)+"<p class='muted'>O detalhe técnico da chamada, provider, tokens e custo permanece em <a href='ai-integrations.html'>IA e integrações</a>.</p>"
        modals.append(evidence._modal(modal_id,_PAGE_COHERENCE_LABELS.get(criterion,PAGE_COHERENCE_CRITERIA[criterion]),criterion,body))
    return "<div class='subsection'><h3>Coerência semântica por página</h3>"+evidence._table(("Dimensão","Resultado","Confiança","Divergências","Detalhe"),table_rows,sortable=True)+"".join(modals)+"</div>"


def install() -> None:
    global _INSTALLED
    if _INSTALLED:return
    from rasai import catalog_report_evidence as evidence
    from rasai import catalog_report_page as page
    original=evidence._semantic_html
    def semantic_html_with_coherence(database: Any,data: Any) -> str:
        return _context_html(evidence,database,data.audit_id)+_auto_interpretation_html(evidence,database,data.audit_id)+_ymyl_alignment_html(evidence,database,data.audit_id)+_property_summary_html(evidence,database,data.audit_id)+_page_summary_html(evidence,database,data.audit_id)+_semantic_assessments_html(evidence,database,data.audit_id)+original(database,data)
    evidence._semantic_html=semantic_html_with_coherence
    page._semantic_html=semantic_html_with_coherence
    _INSTALLED=True
