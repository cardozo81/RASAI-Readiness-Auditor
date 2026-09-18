"""Shared CAT page assembly preserving the stable section order."""
from rasai.catalog_report_analysis import *  # noqa: F401,F403


def _catalog_results_html(database: Path, data: _ReportData, catalog_id: str) -> str:
    metrics=_catalog_metrics(database,data,catalog_id)
    base=_table(("Indicador","Valor","Tipo"),metrics,empty="Nenhum índice ou métrica principal foi materializado neste contexto.")
    if catalog_id=="CAT-01":
        return base+"<div class='subsection'><h3>Arquivos e descoberta</h3>"+_discovery_html(database,data)+"</div><div class='subsection'><h3>Padrões e compatibilidade web</h3>"+_standards_summary(database,data)+"</div><div class='subsection'><h3>Erros e alertas do navegador</h3><p class='section-lead'>Erros de console, JavaScript e falhas de requisição pertencem a este catálogo. A captura do navegador é identificada em Governança.</p>"+_runtime_diagnostics_html(database,data)+"</div>"
    if catalog_id=="CAT-02":
        return base+"<div class='subsection'><h3>Verificações automatizadas</h3>"+_lighthouse_accessibility_html(database,data)+"</div>"
    if catalog_id=="CAT-03":
        return base+_semantic_html(database,data)
    if catalog_id=="CAT-04":
        obs=_web_observation(database,data.audit_id)
        notes=[]
        for key,label in (("lcp_assessment","LCP"),("inp_assessment","INP"),("cls_assessment","CLS"),("cwv_assessment","Core Web Vitals")):
            if obs.get(key):notes.append((label,_assessment_label(obs.get(key))))
        return base+("<div class='subsection'><h3>Avaliações persistidas</h3>"+_table(("Métrica","Avaliação"),notes)+"</div>" if notes else "")
    if catalog_id=="CAT-05":
        return base+"<div class='subsection'><h3>Observações de busca</h3>"+_search_intelligence_html(database,data)+"</div>"
    if catalog_id=="CAT-06":
        return base+"<div class='subsection'><h3>Amostras</h3>"+_apdex_samples_html(database,data,experience=False)+"</div>"
    if catalog_id=="CAT-07":
        return base+"<div class='subsection'><h3>Amostras</h3><p class='section-lead'>A tabela usa o fuso horário de apresentação do RASAi, mostra 10 registros por página quando necessário e permite ordenar pelas colunas.</p>"+_apdex_samples_html(database,data,experience=True)+"</div>"
    if catalog_id=="CAT-08":
        return _improvement_html(database,data)
    if catalog_id=="CAT-09":
        return _remediation_html(database,data)
    return base


def _catalog_analysis_html(database: Path, data: _ReportData, catalog_id: str) -> str:
    policy,enabled=_ai_policy(data,catalog_id)
    indicator=_integration_indicator(database,data,catalog_id)
    if catalog_id=="CAT-08":
        return "<div class='notice good'><strong>Função desta página:</strong> correlacionar evidências já coletadas, explicar problemas e priorizar melhorias. Quando a IA foi utilizada, o resultado permanece orientativo e vinculado às evidências; ela não altera a pontuação determinística.</div>"+indicator
    if catalog_id=="CAT-09":
        return "<div class='notice'><strong>Função desta página:</strong> transformar achados persistidos em ações de correção. Exemplos de código/texto são sugestões e exigem revisão humana e nova auditoria após a implementação.</div>"+indicator
    if policy=="Não utiliza IA":
        text="Este catálogo apresenta observações, medições e validações do seu próprio domínio. Recomendações aprofundadas ficam em CAT-08 e implementações em CAT-09."
    elif enabled:
        text=f"{policy} estava habilitada para esta capacidade. A página mantém o resultado do domínio e apenas indica o uso do recurso; detalhes de requisição, dados envolvidos, tokens, custo e comunicação ficam em IA e integrações."
    else:
        text=f"{policy}, porém não habilitada para esta capacidade nesta execução."
    return f"<div class='notice'><strong>Fronteira de responsabilidade:</strong> {escape(text)}</div>{indicator}"


def _execution_context_notice(database: Path, data: _ReportData, catalog_id: str) -> str:
    run=_explicit_run(database,data,catalog_id)
    if not run:return ""
    if catalog_id=="CAT-06" and _norm(run.get("status"))=="PARTIAL":
        reason=_norm(run.get("reason"))
        if reason=="SMALL_GROUP_BELOW_NORMAL_MINIMUM":
            config=_safe_json(run.get("configuration"),{})
            normal_min=config.get("normal_group_minimum") if isinstance(config,Mapping) else None
            valid=int(run.get("valid_samples") or 0)
            target=int(run.get("target_valid_samples") or 0)
            minimum=f"{normal_min} amostras" if normal_min else "o grupo mínimo normal da metodologia"
            return f"<div class='notice warn'><strong>Por que o resultado é Parcial se a etapa foi concluída?</strong> A coleta técnica terminou sem falha e atingiu {valid} amostra(s) válida(s) para uma meta operacional de {target}. Porém, esse volume está abaixo de {escape(minimum)}; por contrato, o Apdex é calculado, mas permanece <strong>Parcial</strong> por cobertura estatística reduzida. Isso não representa falha de execução.</div>"
        return "<div class='notice warn'><strong>Resultado funcional parcial:</strong> a etapa técnica foi executada, mas a metodologia registrou cobertura incompleta ou amostra inválida. Consulte as amostras e o motivo persistido.</div>"
    return ""


def _catalog_body(database: Path, data: _ReportData, catalog_id: str) -> str:
    catalog=CATALOG_BY_ID[catalog_id]
    status,tone,detail=_catalog_status(database,data,catalog_id)
    sources=_catalog_sources(database,data,catalog_id)
    work=_catalog_work(data,catalog_id)
    metrics=_catalog_metrics(database,data,catalog_id)
    outline=_outline((("summary","Resumo"),("scope","Escopo"),("config","Configuração"),("execution","Execução"),("results","Resultados"),("evidence","Evidências"),("analysis","Análise"),("remediation","Remediações"),("technical","Detalhes técnicos")))
    summary=_section("summary","Resumo",f"<div class='catalog-state'><div><p>{escape(catalog.purpose)}</p><p class='muted'>{escape(catalog.expected_result)}</p></div>{_badge(status,tone)}</div><div class='metric-grid'>{_metric('Capacidades',len(catalog.capability_ids))}{_metric('Fontes com dados',len(sources))}{_metric('Etapas próprias',len(work))}{_metric('Indicadores principais',len(metrics))}</div>")
    if _plan_available(data):
        capability_state="Incluída" if catalog_id in data.selected else "Não solicitada"
    else:
        capability_state="Indeterminada - snapshot do plano ausente/inválido"
    capabilities=[(_capability_label(c),capability_state) for c in catalog.capability_ids]
    scope=_section("scope","Escopo solicitado",_table(("Capacidade","Situação"),capabilities)+f"<div class='notice'>{escape(detail)}</div>")
    config=_section("config","Configuração efetiva",_table(("Configuração","Valor","Origem"),_configuration_rows(data,catalog_id))+"<p class='muted'>Os valores vêm do plano congelado desta AUD, não da configuração atual da máquina. Quando esse snapshot não existe, o relatório declara o estado como indeterminado em vez de inferir “não solicitado”.</p>")
    execution=_section("execution","Execução",_work_execution_html(data,catalog_id)+_execution_context_notice(database,data,catalog_id)+f"<p><strong>Estado funcional do catálogo:</strong> {_badge(status,tone)} {escape(detail)}</p>")
    results=_section("results","Resultados",_catalog_results_html(database,data,catalog_id))
    source_cards="".join(f"<div class='source-item'><strong>{escape(label)}</strong><small>{count} registro(s) persistido(s)</small></div>" for _table_name,label,count in sources)
    evidence=_section("evidence","Evidências",("<div class='source-list'>"+source_cards+"</div>" if source_cards else "<div class='notice'>Nenhuma fonte própria deste catálogo foi encontrada.</div>")+"<p class='muted'>Esta seção identifica a proveniência funcional. Nomes físicos de tabelas ficam restritos a Detalhes técnicos.</p>")
    analysis=_section("analysis","Análise e interpretação",_catalog_analysis_html(database,data,catalog_id))
    if catalog_id=="CAT-09":
        rem_body="<p>As correções detalhadas deste catálogo aparecem em <strong>Resultados</strong>. Cada item procura informar problema, risco de manter, benefício esperado, local de aplicação, implementação sugerida e forma de validação quando esses dados foram persistidos.</p>"
    elif catalog_id=="CAT-08":
        rem_body="<p>A análise profunda prioriza melhorias. Implementação técnica, exemplos de HTML/texto e critérios de validação são consolidados em <a href='cat-09.html'>CAT-09 · Remediações</a>.</p>"
    else:
        rem_body=f"<p>Este catálogo é proprietário do diagnóstico do seu domínio. Correções são centralizadas em <a href='cat-09.html'>CAT-09 · Remediações</a>; quando uma análise profunda usa esta evidência, o vínculo aparece em <a href='cat-08.html'>CAT-08 · Análise profunda e melhorias</a>.</p>"
    remediation=_section("remediation","Remediações",rem_body)
    tech_rows=[(label,table,count) for table,label,count in sources]
    item=data.catalog_items.get(catalog_id,{})
    technical=_section("technical","Detalhes técnicos",f"<details><summary>Mostrar proveniência técnica</summary><div class='detail-body'>{_table(('Fonte funcional','Fonte interna','Registros'),tech_rows,empty='Nenhuma fonte interna específica identificada.')}<p><strong>Identificadores técnicos de capacidade:</strong> <code>{escape(', '.join(catalog.capability_ids))}</code></p><p><strong>Aptidão registrada no plano:</strong> {escape(str(item.get('status') or '-'))}</p></div></details>")
    return _audit_hero(data,f"{catalog.id} · {catalog.label}",catalog.expected_result)+outline+summary+scope+config+execution+results+evidence+analysis+remediation+technical


__all__ = [name for name in globals() if not name.startswith("__")]
