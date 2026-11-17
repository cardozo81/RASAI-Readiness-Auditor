"""Editorial page compositions over the immutable model; no SQL or runtime helpers."""
from .components import text, chip, origin, kv, ruler, table, stack
from .read_model import thaw, SEARCH_PAGE
from .templates import LABELS
from .presentation_labels import public_value, timezone_for_records, timezone_provenance, metric_label
from functools import partial
from collections import Counter
from decimal import Decimal, InvalidOperation
from datetime import datetime, timezone

# Each page owns explicit editorial sections rather than a sequence of SQL tables.
SECTIONS = {
 'extracao': [('Captura e metadados', ['page_snapshots'], [('requested_url','URL solicitada'),('final_url','URL final'),('device','Dispositivo'),('captured_at','Capturado em'),('title','Título'),('canonical','Canonical')]), ('Entidades e sinais identificados',['entity_observations'], [('name','Entidade'),('entity_type','Tipo'),('confidence','Confiança declarada')])],
 'descoberta': [('Arquivos de descoberta e padrões',['m24_diagnostics'], [('title','Observação'),('scope_url','URL'),('severity','Severidade'),('observed_value','Observado'),('remediation','Orientação')]), ('Padrões e métricas técnicas',['standards_metric_observations'], [('label','Métrica'),('value','Valor'),('unit','Unidade'),('scope','Escopo'),('state','Estado')]), ('Serviços de validação',['standards_service_runs'], [('service_id','Serviço'),('state','Estado'),('targets_attempted','Alvos tentados'),('targets_succeeded','Alvos concluídos')])],
 'conteudo': [('Contexto da análise',['content_analysis_contexts','property_semantic_contexts'], [('page_purpose','Propósito'),('intended_audience','Público'),('business_sector','Setor'),('source_mode','Origem')]), ('Coerência por página',['semantic_coherence_assessments'], [('page_url','Página'),('criterion_id','Critério'),('result','Resultado'),('reasoning_summary','Fundamentação'),('confidence','Confiança declarada')]), ('Achados técnicos por classificação de origem',['findings','improvement_intelligence_findings'], [('category','Categoria persistida'),('title','Achado'),('severity','Severidade'),('observed_value','Atual'),('expected_condition','Esperado'),('source','Origem')]), ('Dados estruturados',['jsonld_remediation_suggestions'], [('status','Estado'),('existing_types','Tipos observados'),('proposed_json','Sugestão não aprovada')])],
 'performance': [('Laboratório e campo',['web_performance_observations'], [('url','URL'),('device','Dispositivo'),('performance_score','Lighthouse /100'),('lcp_lab_ms','LCP laboratório ms'),('field_scope','Escopo de campo'),('lcp_p75_ms','LCP campo p75 ms'),('inp_p75_ms','INP campo p75 ms'),('cls_p75','CLS de campo p75'),('cwv_assessment','CWV')]), ('Apdex de navegação',['synthetic_apdex_summaries'], [('url','URL'),('device','Dispositivo'),('profile_id','Perfil'),('apdex_score','Apdex'),('valid_samples','Amostras válidas'),('invalid_samples','Inválidas')]), ('Apdex de experiência',['synthetic_ux_apdex_summaries'], [('url','URL'),('device','Dispositivo'),('profile_id','Perfil'),('apdex_score','Apdex'),('valid_samples','Amostras válidas'),('target_samples','Alvo de amostras')]), ('Detalhes de erros do Apdex de experiência',['synthetic_ux_apdex_error_details'], [('error_type','Tipo'),('source_url','Recurso'),('http_status','HTTP'),('message','Observação')])],
 SEARCH_PAGE: [('Busca observada — SERP',['serp_observations'], [('query','Consulta'),('engine','Mecanismo'),('language','Idioma'),('country','Mercado'),('device','Dispositivo'),('collected_at','Instante'),('result_count','Resultados'),('requested_depth','Profundidade consultada'),('customer_position','Posição do alvo'),('domain_status','Alvo no recorte'),('observation_status','Estado')]), ('Concorrência observada na busca',['serp_competitive_results'], [('position','Posição'),('domain','Domínio'),('url','URL'),('classification','Tipo de resultado'),('reason','Motivo da classificação'),('eligible_for_content_comparison','Comparação de conteúdo elegível'),('selected_for_content_comparison','Selecionado para comparação')]), ('Pesquisa externa — Perplexity',['perplexity_search_runs'], [('query_json','Consulta'),('status','Estado'),('native_usage_quantity','Requests'),('started_at','Instante')]), ('GEO e evidências contextuais',['geo_observation_runs','serp_competitive_ai_analyses'], [('contract_version','Contrato'),('summary','Síntese'),('projection_json','Projeção persistida'),('state','Estado')])],
 'seguranca': [('Cobertura da análise passiva',['passive_security_runs'], [('status','Estado'),('pages_analyzed','Páginas'),('resources_count','Recursos'),('findings_count','Achados'),('limitations_json','Limitações')]), ('Achados e remediação',['passive_security_findings'], [('title','Achado'),('severity','Severidade'),('url_scope','Escopo'),('description','Observado'),('remediation','Remediação'),('validation','Como validar')])],
 'plano': [('Ações por prioridade',['directed_analysis_actions'], [('priority','Prioridade'),('title','Ação'),('effort','Esforço'),('source_kind','Origem'),('implementation_guidance_json','Como implementar'),('validation_steps_json','Como validar')]), ('Correções técnicas propostas',['improvement_intelligence_recommendations'], [('title','Correção'),('selector','Elemento'),('original_html','Atual persistido'),('suggested_html','Sugerido — não aprovado'),('verification','Como validar')]), ('Textos sugeridos por IA',['content_remediation_suggestions'], [('target_location','Alvo'),('objective','Objetivo'),('proposed_text','Sugerido — não aprovado'),('review_note','Revisão humana')])],
 'ia-custos': [('Custo por chamada',['ai_provider_attempts','content_remediation_attempts'], [('provider','Provedor'),('model','Modelo'),('status','Estado'),('input_tokens','Tokens entrada'),('output_tokens','Tokens saída'),('estimated_cost','Estimado'),('cost_currency','Moeda da estimativa'),('observed_cost','Observado'),('observed_cost_currency','Moeda observada'),('started_at','Início da tentativa'),('finished_at','Fim da tentativa'),('duration_ms','Duração ms')]), ('Entradas e saídas completas',['ai_exchange_log'], [('purpose','Finalidade'),('provider','Provedor'),('model','Modelo'),('outcome','Estado'),('request_payload','Entrada sanitizada'),('response_payload','Saída sanitizada')]), ('Proveniência e execução',['ai_tasks'], [('purpose','Finalidade'),('status','Estado'),('prompt_version','Versão do prompt'),('semantic_contract_version','Versão da especificação técnica')])],
}


def _metric_proposal(key, thresholds):
    by_id = {item.get('metric_id'): item for item in thresholds}
    if key == 'value':
        return by_id.get('SARI_PRESENTATION_PROPOSAL')
    if key in {'performance_score', 'accessibility_score', 'best_practices_score', 'seo_score', 'agentic_browsing_score'}:
        return by_id.get('LIGHTHOUSE_CATEGORY_PERSISTED_CONTRACT')
    if key == 'apdex_score':
        return by_id.get('APDEX_RESULT_PERSISTED_CONTRACT')
    return None


def _money(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        amount = Decimal(str(value))
        return amount if amount.is_finite() and amount >= 0 else None
    except (InvalidOperation, TypeError, ValueError):
        return None


def _timestamp(value):
    if not value:
        return None
    try:
        result = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return result if result.tzinfo else result.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def editorial(page, records, costs, thresholds, governance=None):
    timezone_name, timezone_reason = timezone_for_records(records)
    local_table = partial(table, timezone_name=timezone_name)
    def rows(names):
        return [{**thaw(r.data), '_ref': r.href, '_source_table': r.table} for r in records if r.table in names]
    from .governance import Governance
    if governance is None:
        governance = Governance(rows(['recommendation_governance']))
    html = ''
    if page == 'index':
        audits = rows(['audits'])
        html += '<h2>Contexto da auditoria</h2>'
        for data in audits:
            targets = rows(['audit_targets'])
            domains = list(dict.fromkeys(r.get('normalized_origin') or r.get('input_url') for r in targets if r.get('normalized_origin') or r.get('input_url')))
            devices = sorted({str(public_value(r.get('device'),'device')) for r in rows(['page_snapshots']) if r.get('device')})
            pairs = [('Auditoria',data.get('audit_id')),('Domínio auditado',' · '.join(domains) or None),('Dispositivo',' · '.join(devices) or None)]
            pairs += [(label,public_value(data.get(key),key,timezone_name)) for key,label in [('status','Estado'),('completion_status','Conclusão'),('created_at','Criada em'),('started_at','Início da auditoria'),('completed_at','Fechamento da auditoria-base'),('project_name','Projeto'),('primary_language','Idioma'),('market','Mercado'),('audit_mode','Modo'),('auditor_version','Versão do auditor'),('ruleset_version','Versão das regras')]]
            pairs += [('Fuso de apresentação',timezone_name),('Origem do fuso',timezone_provenance(timezone_reason))]
            html += kv(pairs)
        html += '<h2>Índices em uma leitura</h2>'
    if page in {'index','indices','performance'}:
        if page != 'index':
            html += '<h2>Indicadores independentes e escopos</h2>'
        html += '<div>' if page == 'indices' else '<div class="grid">'
        for data in sorted(rows(['scores','web_performance_observations','synthetic_apdex_summaries','synthetic_ux_apdex_summaries']), key=lambda r: r.get('dimension') != 'OVERALL_READINESS'):
            for key in ('value','performance_score','accessibility_score','best_practices_score','seo_score','agentic_browsing_score','apdex_score'):
                if page == 'index' and key == 'value' and data.get('dimension') != 'OVERALL_READINESS':
                    continue
                if key not in data:
                    continue
                if page == 'performance' and key == 'value':
                    continue
                proposal = _metric_proposal(key, thresholds)
                scope = ' · '.join(str(public_value(data[k],k,timezone_name)) for k in ('device','url','profile_id','consolidation_status','confidence') if data.get(k) is not None)
                if key == 'value':
                    coverage = data.get('coverage')
                    percent = f'{coverage * 100:.1f}%'.replace('.', ',') if isinstance(coverage, (int, float)) else 'N/D'
                    scope += ' · Cobertura ' + percent
                elif key == 'apdex_score':
                    run = next(iter(rows([data['_source_table'].replace('_summaries', '_runs')])), {})
                    target = data.get('target_samples', run.get('target_valid_samples'))
                    scope += ' · Amostras válidas / meta: ' + ' / '.join(str(v) if v is not None else 'N/D' for v in (data.get('valid_samples'), target))
                    thresholds_pair = (run.get('satisfied_threshold_seconds', run.get('threshold_seconds')), run.get('frustrated_threshold_seconds', run.get('frustration_seconds')))
                    if all(value is not None for value in thresholds_pair):
                        scope += ' · T/F (s): ' + ' / '.join(str(v) for v in thresholds_pair)
                    if data.get('small_group'):
                        scope += ' · Grupo pequeno; generalização limitada'
                html += ruler(metric_label(data,key,LABELS), data[key], 1 if key == 'apdex_score' else 100, proposal, scope, data['_ref'])
                if page == 'indices' and key == 'value':
                    contributions = [r for r in rows(['score_contributions']) if r.get('score_id') == data.get('score_id')]
                    if contributions:
                        html += local_table('Composição da dimensão', contributions, [('rule_id','Regra'),('result','Resultado'),('weight','Peso'),('result_factor','Fator'),('effective_contribution','Contribuição')])
                    else:
                        html += '<p class="rf">Decomposição de regras desta dimensão não disponível na fonte. O índice acima permanece medido quando possui valor persistido; nenhuma contribuição é inferida.</p>'
        html += '</div>'
        if page == 'performance' and rows(['synthetic_population_apdex_summaries']):
            populations = rows(['synthetic_population_apdex_summaries'])
            mobile = rows(['synthetic_ux_apdex_summaries'])
            html += '<h2>Dados de suporte da população</h2>'
            for item in populations:
                matched = any(
                    row.get('device') == 'MOBILE' and
                    row.get('apdex_score') == item.get('apdex_score') and
                    row.get('valid_samples') == item.get('valid_samples')
                    for row in mobile
                )
                mix = item.get('device_mix') or item.get('device_mix_json')
                if isinstance(mix, str):
                    try:
                        import json
                        mix = json.loads(mix)
                    except (TypeError, ValueError):
                        mix = None
                mobile_only = (isinstance(mix, dict) and len(mix) == 1 and
                               mix.get('MOBILE') == 100.0)
                if matched and mobile_only:
                    html += '<p>População (mix 100% móvel): mesma medição que Móvel. '
                    html += '<a class="tech-link" href="' + text(item['_ref']) + '">Detalhe da população</a></p>'
                else:
                    html += '<p>Registro populacional persistido; equivalência com a medição móvel não demonstrada.</p>'
                    html += local_table('População: dados de suporte', [item], [
                        ('device', 'Dispositivo'), ('apdex_score', 'Apdex'),
                        ('valid_samples', 'Amostras válidas'), ('device_mix', 'Mix de dispositivos')])
    if page == 'index':
        exceptions = [r for r in rows(['scores']) if r.get('confidence') == 'LOW' or r.get('consolidation_status') == 'NOT_APPLICABLE']
        if exceptions:
            html += local_table('Dimensões com baixa confiança ou sem aplicação', exceptions,
                                [('dimension','Dimensão'),('coverage','Cobertura (fração)'),('confidence','Confiança'),('consolidation_status','Estado')])
        html += '<h2>Ações aprovadas com prioridade persistida</h2>' + local_table('Ações com prioridade alta persistida',[r for r in rows(['directed_analysis_actions']) if r.get('priority') in {'HIGH','CRITICAL','P1','P0'} and governance.disposition('directed_analysis_actions', r) == 'Aceita pela governança'], [('priority','Prioridade'),('title','Ação'),('effort','Esforço')])
        html += '<h2>Estado da execução</h2>' + local_table('Cobertura operacional', rows(['audit_fulfillment_work_items']), [('component','Componente'),('status','Estado'),('required','Obrigatório')])
    if page in {'index','ia-custos'}:
        html += '<h2>Consumo e proveniência</h2>' + chip(costs['coverage']) + kv([('Tentativas identificadas',costs['attempt_count'])])
        attempt_rows = rows(['ai_provider_attempts', 'content_remediation_attempts'])
        priced = [row for row in attempt_rows if _money(row.get('estimated_cost')) is not None]
        by_currency = {}
        for row in priced:
            currency = row.get('cost_currency') or 'moeda não registrada'
            by_currency[currency] = by_currency.get(currency, Decimal(0)) + _money(row['estimated_cost'])
        observed = [row for row in attempt_rows if _money(row.get('observed_cost')) is not None]
        html += kv([
            ('Custo estimado persistido',
             ' · '.join(str(currency) + ' ' + format(total, 'f') for currency, total
                        in sorted(by_currency.items())) + ' em ' + str(len(priced)) +
             ' tentativas com preço' if priced else 'N/D — sem estimativas monetárias persistidas'),
            ('Custo observado pelo provedor',
             str(len(observed)) + ' tentativa(s) com valor observado' if observed else 'N/D — nenhum custo observado pelo provedor'),
        ])
        forecasts = rows(['console_cost_forecast_outcomes'])
        for forecast in forecasts:
            evaluated = forecast.get('evaluated_at')
            instant = _timestamp(evaluated)
            newer = [row for row in attempt_rows
                     if instant and _timestamp(row.get('started_at')) and
                     _timestamp(row.get('started_at')) > instant]
            amount = forecast.get('actual_cost')
            html += kv([(
                'Instantâneo do console em ' + str(evaluated or 'data não registrada'),
                (str(forecast.get('currency') or 'moeda não informada') + ' ' +
                 (format(_money(amount), 'f') if _money(amount) is not None else 'N/D') +
                 ' — anterior a ' + str(len(newer)) + ' tentativa(s)'
                 if instant else 'data de avaliação não verificável; sem equivalência com custo final')
            )])
        if page == 'ia-custos' and priced:
            html += '<h2>Tentativas com custo estimado persistido</h2>'
            html += local_table('Preço por tentativa — sem cobrança inferida', priced, [
                ('provider', 'Provedor'), ('model', 'Modelo'),
                ('pricing_rule_id', 'Regra de preço'), ('pricing_version', 'Versão do preço'),
                ('estimated_cost', 'Custo estimado'), ('cost_currency', 'Moeda'),
                ('started_at', 'Início')
            ])
        for currency, amounts in costs['totals'].items():
            html += kv([(f'{currency} · {kind}',public_value(value,'amount')) for kind,value in amounts.items() if kind != 'conciliado'])
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
                title='Composição do custo estimado ou observado por tentativa',
                unit=currency,
                note='Cada segmento usa um custo persistido da tentativa: observado quando disponível; estimado como alternativa. Não representa cobrança final. As cores são categóricas e não indicam conformidade.',
            )
        html += '<p class="callout">Custo técnico estimado não equivale a cobrança observada. Tokens de Search não são inferidos.</p>'
        if page == 'ia-custos':
            if not costs['attempt_count']:
                not_executed = any(r.get('component') in {'TECHNICAL_AI','CONTENT_REMEDIATION_AI'}
                                   and r.get('status') == 'REQUESTED_NOT_EXECUTED'
                                   for r in rows(['audit_fulfillment_work_items']))
                html += ('<p class="callout w">' + ('IA não executada nos requisitos registrados. ' if not_executed else '')
                         + '0 tentativas registradas. A ausência de tentativas não é uma medição de tokens ou de cobrança.</p>')
                html += kv([('Tokens de entrada', 'N/D — não medidos'),
                            ('Tokens de saída', 'N/D — não medidos'),
                            ('Provedores de IA executados', 'Nenhum registrado'),
                            ('Custo observado nas tentativas de IA', 'N/D — sem telemetria de tentativas')])
            if any(r.get('processing_status') == 'PARTIAL_RETRYABLE'
                   for r in rows(['audit_fulfillment_contracts'])):
                html += '<p><strong>Custo total da auditoria:</strong> N/D — execução parcial; não demonstrado como custo final.</p>'
            research = rows(['perplexity_search_runs'])
            serp = rows(['serp_observations'])
            html += '<h2>Pesquisa externa e consumo de IA</h2>'
            html += '<p>Resultados de busca e tentativas de IA são fontes distintas; não se somam contagens de resultados como chamadas ou tokens.</p>'
            if not research:
                html += '<p>Pesquisa Perplexity: nenhuma execução registrada; custo e tokens N/D.</p>'
            else:
                html += local_table('Pesquisa Perplexity registrada', research,
                    [('provider','Provedor'),('model','Modelo'),('status','Estado'),
                     ('started_at','Início'),('estimated_cost','Custo estimado'),
                     ('observed_cost','Custo observado'),('cost_currency','Moeda')])
            if serp:
                html += local_table('Busca SERP observada — não constitui tentativa de IA', serp,
                    [('engine','Mecanismo'),('provider','Provedor'),('collected_at','Coletada em'),
                     ('observation_status','Estado'),('query','Consulta')])
                html += '<p class="rf">Esta observação de busca não fornece, por si só, cobrança monetária ou consumo de IA.</p>'
    if page == 'plano':
        from .action_plan import render_plan
        html += render_plan(rows, timezone_name, governance)
    for title, names, columns in ([] if page == 'plano' else SECTIONS.get(page, [])):
        if page == 'ia-custos' and not rows(names):
            continue  # absence is explained above; populated telemetry retains its full tables
        html += '<h2>' + text(title) + '</h2>'
        if names == ['serp_competitive_results']:
            html += ('<p class="rf">Classificação determinística dos resultados observados '
                     'em busca, não comprovação de concorrência comercial. Posição vale '
                     'somente para consulta, mercado, dispositivo e instante medidos. '
                     'Seleção para comparar conteúdos não confirma equivalência entre '
                     'empresas nem causa de posicionamento.</p>')
        if 'jsonld_remediation_suggestions' in names:
            html += origin('Proposta determinística do RASAi · baseada na captura')
        elif any('suggest' in name or name.startswith('ai_') for name in names):
            html += origin('IA sugeriu' if 'propost' in title.lower() or 'sugerid' in title.lower() else 'Externo')
        items = rows(names)
        if not items and names == ['synthetic_ux_apdex_error_details']:
            html += '<p>Nenhum detalhe de erro do Apdex de experiência disponível. Consulte as medições independentes de rede e scripts.</p>'
        else:
            html += local_table(title, items, columns)
    return html
