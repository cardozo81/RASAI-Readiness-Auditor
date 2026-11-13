"""Editorial page compositions over the immutable model; no SQL or runtime helpers."""
from .components import text, chip, origin, kv, ruler, table, stack
from .read_model import thaw
from .templates import LABELS

# Each page owns explicit editorial sections rather than a sequence of SQL tables.
SECTIONS = {
 'extracao': [('Captura e metadados', ['page_snapshots'], [('requested_url','URL solicitada'),('final_url','URL final'),('device','Dispositivo'),('captured_at','Capturado em'),('title','Título'),('canonical','Canonical')]), ('Entidades e sinais identificados',['entity_observations'], [('name','Entidade'),('entity_type','Tipo'),('confidence','Confiança declarada')])],
 'descoberta': [('Arquivos de descoberta e padrões',['m24_diagnostics'], [('title','Observação'),('scope_url','URL'),('severity','Severidade'),('observed_value','Observado'),('remediation','Orientação')]), ('Padrões e métricas técnicas',['standards_metric_observations'], [('label','Métrica'),('value','Valor'),('unit','Unidade'),('scope','Escopo'),('state','Estado')]), ('Serviços de validação',['standards_service_runs'], [('service_id','Serviço'),('state','Estado'),('targets_attempted','Alvos tentados'),('targets_succeeded','Alvos concluídos')])],
 'conteudo': [('Contexto da análise',['content_analysis_contexts','property_semantic_contexts'], [('page_purpose','Propósito'),('intended_audience','Público'),('business_sector','Setor'),('source_mode','Origem')]), ('Coerência por página',['semantic_coherence_assessments'], [('page_url','Página'),('criterion_id','Critério'),('result','Resultado'),('reasoning_summary','Fundamentação'),('confidence','Confiança declarada')]), ('Achados semânticos e acessibilidade',['findings','improvement_intelligence_findings'], [('title','Achado'),('severity','Severidade'),('observed_value','Atual'),('expected_condition','Esperado'),('source','Origem')]), ('Dados estruturados',['jsonld_remediation_suggestions'], [('status','Estado'),('existing_types','Tipos observados'),('proposed_json','Sugestão não aprovada')])],
 'performance': [('Laboratório e campo',['web_performance_observations'], [('url','URL'),('device','Dispositivo'),('performance_score','Lighthouse /100'),('lcp_lab_ms','LCP laboratório ms'),('field_scope','Escopo de campo'),('lcp_p75_ms','LCP campo p75 ms'),('inp_p75_ms','INP campo p75 ms'),('cwv_assessment','CWV')]), ('Apdex de navegação',['synthetic_apdex_summaries'], [('url','URL'),('device','Dispositivo'),('profile_id','Perfil'),('apdex_score','Apdex'),('valid_samples','Amostras válidas'),('invalid_samples','Inválidas')]), ('Apdex de experiência',['synthetic_ux_apdex_summaries'], [('url','URL'),('device','Dispositivo'),('profile_id','Perfil'),('apdex_score','Apdex'),('valid_samples','Amostras válidas'),('target_samples','Alvo de amostras')]), ('JavaScript e rede observados',['synthetic_ux_apdex_error_details'], [('error_type','Tipo'),('source_url','Recurso'),('http_status','HTTP'),('message','Observação')])],
 'search-geo': [('Busca observada — SERP',['serp_observations'], [('query','Consulta'),('engine','Mecanismo'),('language','Idioma'),('country','Mercado'),('device','Dispositivo'),('collected_at','Instante'),('result_count','Resultados'),('observation_status','Estado')]), ('Concorrência observada',['serp_competitive_results'], [('url','URL'),('position','Posição'),('classification','Classificação'),('reason','Motivo')]), ('Pesquisa externa — Perplexity',['perplexity_search_runs'], [('query_json','Consulta'),('status','Estado'),('native_usage_quantity','Requests'),('started_at','Instante')]), ('GEO e evidências contextuais',['geo_observation_runs','serp_competitive_ai_analyses'], [('contract_version','Contrato'),('summary','Síntese'),('projection_json','Projeção persistida'),('state','Estado')])],
 'seguranca': [('Cobertura da análise passiva',['passive_security_runs'], [('status','Estado'),('pages_analyzed','Páginas'),('resources_count','Recursos'),('findings_count','Achados'),('limitations_json','Limitações')]), ('Achados e remediação',['passive_security_findings'], [('title','Achado'),('severity','Severidade'),('url_scope','Escopo'),('description','Observado'),('remediation','Remediação'),('validation','Como validar')])],
 'plano': [('Ações por prioridade',['directed_analysis_actions'], [('priority','Prioridade'),('title','Ação'),('effort','Esforço'),('source_kind','Origem'),('implementation_guidance_json','Como implementar'),('validation_steps_json','Como validar')]), ('Correções técnicas propostas',['improvement_intelligence_recommendations'], [('title','Correção'),('selector','Elemento'),('original_html','Atual persistido'),('suggested_html','Sugerido — não aprovado'),('verification','Como validar')]), ('Textos sugeridos por IA',['content_remediation_suggestions'], [('target_location','Alvo'),('objective','Objetivo'),('proposed_text','Sugerido — não aprovado'),('review_note','Revisão humana')])],
 'ia-custos': [('Custo por chamada',['ai_provider_attempts','content_remediation_attempts'], [('provider','Provider'),('model','Modelo'),('status','Estado'),('input_tokens','Tokens entrada'),('output_tokens','Tokens saída'),('estimated_cost','Estimado'),('observed_cost','Observado'),('cost_currency','Moeda'),('duration_ms','Duração ms')]), ('Entradas e saídas completas',['ai_exchange_log'], [('purpose','Finalidade'),('provider','Provider'),('model','Modelo'),('outcome','Estado'),('request_payload','Entrada sanitizada'),('response_payload','Saída sanitizada')]), ('Proveniência e execução',['ai_tasks'], [('purpose','Finalidade'),('status','Estado'),('prompt_version','Versão do prompt'),('semantic_contract_version','Contrato')])],
}


def _metric_proposal(key, thresholds):
    by_id = {item.get('metric_id'): item for item in thresholds}
    if key == 'value':
        return by_id.get('SARI_PRESENTATION_PROPOSAL')
    if key in {'performance_score', 'accessibility_score', 'best_practices_score', 'seo_score'}:
        return by_id.get('LIGHTHOUSE_CATEGORY_PERSISTED_CONTRACT')
    if key == 'apdex_score':
        return by_id.get('APDEX_RESULT_PERSISTED_CONTRACT')
    return None


def editorial(page, records, costs, thresholds):
    def rows(names):
        return [{**thaw(r.data), '_ref': r.href} for r in records if r.table in names]
    html = ''
    if page == 'index':
        audits = rows(['audits'])
        html += '<h2>Contexto da auditoria</h2>'
        for data in audits:
            html += kv([(label, data.get(key)) for key,label in [('audit_id','Auditoria'),('status','Estado'),('completion_status','Conclusão'),('created_at','Criada em')]])
        html += '<h2>Índices em uma leitura</h2>'
    if page in {'index','indices','performance'}:
        if page != 'index':
            html += '<h2>Indicadores independentes e escopos</h2>'
        html += '<div>' if page == 'indices' else '<div class="grid">'
        for data in sorted(rows(['scores','web_performance_observations','synthetic_apdex_summaries','synthetic_ux_apdex_summaries']), key=lambda r: r.get('dimension') != 'OVERALL_READINESS'):
            for key in ('value','performance_score','accessibility_score','best_practices_score','seo_score','apdex_score'):
                if page == 'index' and key == 'value' and data.get('dimension') != 'OVERALL_READINESS':
                    continue
                if key not in data:
                    continue
                if page == 'performance' and key == 'value':
                    continue
                proposal = _metric_proposal(key, thresholds)
                scope = ' · '.join(str(data[k]) for k in ('device','url','profile_id','consolidation_status','confidence') if data.get(k) is not None)
                html += ruler(LABELS.get(data.get('dimension',key),data.get('dimension',key)), data[key], 1 if key == 'apdex_score' else 100, proposal, scope, data['_ref'])
                if page == 'indices' and key == 'value':
                    contributions = [r for r in rows(['score_contributions']) if r.get('score_id') == data.get('score_id')]
                    html += table('Composição da dimensão', contributions, [('rule_id','Regra'),('result','Resultado'),('weight','Peso'),('result_factor','Fator'),('effective_contribution','Contribuição'),('_ref','Fonte')])
        html += '</div>'
    if page == 'index':
        html += '<h2>Riscos e ações prioritárias</h2>' + table('Ações com prioridade alta persistida',[r for r in rows(['directed_analysis_actions']) if r.get('priority') in {'HIGH','CRITICAL','P1','P0'}], [('priority','Prioridade'),('title','Ação'),('effort','Esforço'),('_ref','Fonte')])
        html += '<h2>Estado da execução</h2>' + table('Cobertura operacional', rows(['audit_fulfillment_work_items']), [('component','Componente'),('status','Estado'),('required','Obrigatório'),('_ref','Fonte')])
    if page in {'index','ia-custos'}:
        html += '<h2>Consumo e proveniência</h2>' + chip(costs['coverage']) + kv([('Tentativas identificadas',costs['attempt_count'])])
        for currency, amounts in costs['totals'].items():
            html += kv([(f'{currency} · {kind}',value) for kind,value in amounts.items()])
            source_labels = {
                'ai_provider_attempts': 'IA / integração',
                'content_remediation_attempts': 'Remediação de conteúdo',
            }
            source_counts = {}
            parts = []
            for entry in costs['entries']:
                if entry['currency'] != currency or entry['amount'] is None:
                    continue
                source = entry.get('source') or 'origem não identificada'
                source_counts[source] = source_counts.get(source, 0) + 1
                label = f"{source_labels.get(source, source)} #{source_counts[source]}"
                parts.append((label, entry['amount'], entry.get('attempt_id')))
            html += stack(
                parts,
                title='Composição do custo conciliado por tentativa',
                unit=currency,
                note='Cada segmento usa o valor conciliado da tentativa: observado quando disponível; estimado como fallback. As cores são apenas categóricas e não indicam qualidade, severidade ou conformidade.',
            )
        html += '<p class="callout">Custo técnico estimado não equivale a cobrança observada. Tokens de Search não são inferidos.</p>'
    for title, names, columns in SECTIONS.get(page, []):
        html += '<h2>' + text(title) + '</h2>'
        if any('suggest' in name or name.startswith('ai_') for name in names):
            html += origin('IA sugeriu' if 'propost' in title.lower() or 'sugerid' in title.lower() else 'Externo')
        html += table(title, rows(names), columns + [('_ref','Fonte')])
    return html
