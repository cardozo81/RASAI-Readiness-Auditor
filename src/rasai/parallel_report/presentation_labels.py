"""Typed public labels only: never translate evidence or untyped free text."""
import json
import re
from rasai.time_contract import (presentation_timezone_for_audit,
                                 format_presentation_timestamp,
                                 format_presentation_date_only)
from rasai.public_language import component_label, scope_label, supplemental_public_label, safe_visible_fallback
from rasai.catalog_report_public_labels import public_label as canonical_public_label

FIELD_LABELS = {'status':'Estado','severity':'Criticidade','priority':'Prioridade','provider':'Provedor','model':'Modelo','source':'Origem','reference':'Referência','references':'Referências','scope':'Escopo','device':'Dispositivo','native_usage_quantity':'Requisições','input_tokens':'Tokens de entrada','output_tokens':'Tokens de saída','duration_ms':'Duração (ms)','created_at':'Criada em','started_at':'Iniciada em','completed_at':'Concluída em','captured_at':'Capturada em','collected_at':'Coletada em','executed_at':'Executada em','updated_at':'Atualizada em','finished_at':'Finalizada em','capture_utc':'Capturada em','capture_timestamp':'Capturada em','classification':'Tipo de resultado','eligible_for_content_comparison':'Comparação de conteúdo elegível','selected_for_content_comparison':'Selecionado para comparação'}
STATUS_LABELS = {'SUCCESS':'Concluído','COMPLETE':'Concluído','COMPLETED':'Concluído','PASS':'Aprovado','PARTIAL':'Parcial','WARNING':'Atenção','FAILED':'Falhou','ERROR':'Falhou','FAIL':'Reprovado','BLOCKED':'Bloqueado','NOT_OBSERVED':'Não observado','COLLECTION_FAILED':'Falha na coleta','INCONCLUSIVE':'Inconclusivo','NOT_REQUESTED':'Não solicitado','NOT_APPLICABLE':'Não aplicável','SKIPPED':'Não executado','UNKNOWN':'Não determinado','CONSOLIDATED':'Consolidado','NOT_CONSOLIDATED':'Não consolidado','COMPLETE_WITH_LIMITATIONS':'Concluído com limitações','GOOD':'Bom','NEEDS_IMPROVEMENT':'Precisa melhorar','TOLERATING':'Tolerável','OBSERVED':'Observado','COHERENT':'Coerente','NOT_DETERMINABLE':'Não determinável','AVAILABLE':'Disponível','NOT_CONFIGURED':'Não configurado','DISABLED':'Desabilitado','NO_DATA':'Sem dados','ABSENT':'Ausente'}
STATUS_LABELS.update({
    'UNAVAILABLE':'Indisponível', 'NOT_AVAILABLE':'Não disponível',
    'REQUESTED_NOT_EXECUTED':'Solicitado, não executado',
    'FAILED_RETRYABLE':'Falha recuperável', 'FAILED_PERMANENT':'Falha permanente',
    'PENDING':'Pendente', 'FINAL':'Final', 'RUNNING':'Em execução', 'IN_PROGRESS':'Em andamento',
    'ACCEPTED':'Aceita', 'REJECTED':'Rejeitada', 'UNVERIFIED':'Não verificado',
    'VALIDACAO_NECESSARIA':'Validação necessária',
    'INSUFICIENTE':'Insuficiente', 'SUFICIENTE':'Suficiente',
})
STATUS_LABELS.update({'MISSING_PROPOSED':'Ausente — proposta disponível','MEASURED':'Medido','READY':'Pronto','RESPONSE':'Resposta','LIMITED_AVAILABILITY':'Disponibilidade limitada','NEWLY_AVAILABLE':'Disponível recentemente','WIDELY_AVAILABLE':'Amplamente disponível'})
SEVERITY_LABELS = {'CRITICAL':'Crítica','HIGH':'Alta','MEDIUM':'Média','LOW':'Baixa','INFO':'Informativa','INFORMATIONAL':'Informativa'}
PRIORITY_LABELS = {k:v for k,v in SEVERITY_LABELS.items() if k not in {'INFO','INFORMATIONAL'}}
PRIORITY_LABELS.update({
    'P0':'Prioridade 0 (crítica)', 'P1':'Prioridade 1 (alta)',
    'P2':'Prioridade 2 (média)', 'P3':'Prioridade 3 (baixa)',
})
DEVICE_LABELS = {'MOBILE':'Móvel','DESKTOP':'Desktop','POPULATION':'Agregado de experiência','MIXED_DEVICE_POPULATION':'Agregado dos dispositivos configurados'}
ORIGIN_LABELS = {'PRODUCT_PROPOSAL':'Proposta de produto','PERSISTED_CONTRACT':'Critério de medição registrado','PUBLIC_STANDARD':'Padrão público','DETERMINISTIC':'Regra determinística','CONTENT_AI':'IA de conteúdo','DEEP_ANALYSIS':'Análise aprofundada','JSONLD':'JSON-LD','SECURITY_REMEDIATION':'Remediação de segurança','EXTERNAL':'Externo','AUTO':'Automático','MIXED':'Misto'}
VALUE_LABELS = {**STATUS_LABELS, **SEVERITY_LABELS, **DEVICE_LABELS, **ORIGIN_LABELS}
TIMESTAMPS = {'created_at','started_at','completed_at','captured_at','collected_at','executed_at','projected_at','updated_at','fetch_time','lighthouse_fetch_time','finished_at','observed_at','calculated_at','capture_utc','capture_timestamp','capture_time','capture_time_utc','timestamp_utc','provider_created_at','reused_at','persisted_at','requested_at','measurement_at',
              'collection_window_start','collection_window_end','last_updated'}
# Civil dates from CrUX windows and external source metadata are NOT instants.
# Only explicitly typed fields receive pt-BR date formatting, without shifting days.
CIVIL_DATES = {'first_start','first_end','last_start','last_end',
               'period_start','period_end','source_date','last_updated'}
ENUM_FIELDS = {'status','state','result','severity','priority','priority_class','coverage','confidence','device','source_kind','source_mode','origin_kind','effort','completion_status','consolidation_status','observation_status','outcome','analysis_state','field_scope','cwv_assessment'}
FIELD_LABELS.update({'projected_at':'Projetada em','fetch_time':'Coletada em','lighthouse_fetch_time':'Coletada pelo Lighthouse em','observed_at':'Observada em','calculated_at':'Calculada em','type':'Tipo','selector':'Seletor','line':'Linha','column':'Coluna','coverage':'Cobertura','canonical':'URL canônica','sha256':'SHA-256'})
# Explicit labels for the already selected analytical fields. Raw keys, IDs and
# free-text evidence remain unchanged in technical payloads and annexes.
FIELD_LABELS.update({
    'category':'Categoria de origem', 'state':'Estado', 'result':'Resultado',
    'title':'Título', 'label':'Métrica / observação', 'description':'Descrição',
    'component':'Etapa', 'required':'Obrigatório', 'attempt_count':'Tentativas',
    'attempt_number':'Número da tentativa', 'last_attempt_at':'Última tentativa em',
    'last_success_at':'Último sucesso em', 'last_error_code':'Motivo registrado',
    'retryable':'Permite nova tentativa', 'result_ref':'Referência do resultado',
    'kind':'Tipo', 'heartbeat_at':'Último sinal da sessão em',
    'schema_version':'Versão do esquema', 'configuration_kind':'Tipo de configuração',
    'configuration_hash':'Hash da configuração', 'changed_fields_json':'Campos alterados',
    'exposure_level':'Exposição estimada', 'device_contexts':'Contextos de dispositivo',
    'min_pages':'Mínimo de páginas previsto', 'max_pages':'Máximo de páginas previsto',
    'min_ai_attempts':'Mínimo de tentativas de IA previsto', 'max_ai_attempts':'Máximo de tentativas de IA previsto',
    'min_web_calls':'Mínimo de chamadas web previsto', 'max_web_calls':'Máximo de chamadas web previsto',
    'reasons':'Motivos registrados', 'input_mode':'Modo de entrada',
    'supplied_count':'Entradas fornecidas', 'normalized_unique_count':'URLs únicas normalizadas',
    'input_url':'URL fornecida', 'normalized_url':'URL normalizada', 'position':'Posição',
    'architecture_classification':'Classificação da arquitetura', 'artifact_reference':'Arquivo de evidência',
    'artifact_sha256':'SHA-256 da evidência', 'depth':'Profundidade', 'discovery_sources':'Fontes de descoberta',
    'evidence_type':'Tipo de evidência', 'http_status':'Status HTTP', 'rendering_mode':'Modo de renderização',
    'preview_browser':'Navegador observado', 'preview_viewport':'Área visível',
    'preview_runtime_count':'Ocorrências do navegador', 'preview_visual_ref':'Referência da captura visual',
    'tag_name':'Elemento HTML', 'text_excerpt':'Trecho observado',
    'ai_enabled':'IA habilitada', 'ai_state':'Estado da IA', 'browser_support':'Suporte dos navegadores',
    'configured':'Configurado', 'effective_enabled':'Habilitado efetivamente',
    'errors':'Erros registrados', 'warnings':'Avisos registrados', 'grade':'Conceito',
    'diagnostics_count':'Diagnósticos', 'llms_state':'Estado de llms.txt',
    'methodology':'Método declarado', 'relation_degree':'Grau de relação',
    'requested':'Solicitado', 'scoring_impact':'Impacto registrado na pontuação',
    'service_id':'Serviço', 'signals':'Sinais observados', 'target':'Alvo',
    'targets_attempted':'Alvos tentados', 'targets_succeeded':'Alvos concluídos',
    'tests_failed':'Verificações reprovadas', 'tests_passed':'Verificações aprovadas',
    'unit':'Unidade', 'value':'Valor', 'evidence_ids':'IDs das evidências',
    'expected_condition':'Condição esperada', 'rule_id':'Regra', 'rule_version':'Versão da regra',
    'attempted_samples':'Amostras tentadas', 'benchmark_index':'Índice do ambiente de execução',
    'calibration_source':'Fonte da calibração', 'categories':'Categorias', 'cls':'CLS',
    'coefficient_of_variation':'Coeficiente de variação', 'concurrency':'Concorrência de execução',
    'consumed_by_navigation':'Utilizada na navegação', 'context_attempts':'Contextos tentados',
    'cpu_method':'Método de CPU', 'network_method':'Método de rede', 'crux_successes':'Sucessos CrUX',
    'delay_seconds':'Intervalo entre tentativas (s)', 'eligible_acquisitions':'Capturas elegíveis',
    'error_forced_frustrated':'Frustração por erro', 'error_forced_frustrated_count':'Amostras frustradas por erro',
    'error_scope':'Escopo dos erros', 'field_source':'Fonte de campo', 'form_factor':'Tipo de dispositivo',
    'first_half_mean_ms':'Média da primeira metade (ms)', 'second_half_mean_ms':'Média da segunda metade (ms)',
    'frustrated_count':'Amostras frustradas', 'tolerating_count':'Amostras toleráveis',
    'satisfied_count':'Amostras satisfeitas', 'frustrated_threshold_seconds':'Limite de frustração (s)',
    'frustration_seconds':'Limite de frustração (s)', 'satisfied_threshold_seconds':'Limite de satisfação (s)',
    'threshold_seconds':'Limite de satisfação (s)', 'http_error_count':'Erros HTTP',
    'invalid_samples':'Amostras inválidas', 'valid_samples':'Amostras válidas',
    'javascript_error_count':'Erros JavaScript', 'javascript_error_samples':'Amostras com erros JavaScript',
    'kpm':'Métrica principal de experiência', 'kpm_value_ms':'Valor da métrica de experiência (ms)',
    'lcp_ms':'LCP (ms)', 'lighthouse_total_ms':'Duração do Lighthouse (ms)',
    'load_duration_ms':'Duração do carregamento (ms)', 'navigation_duration_ms':'Duração da navegação (ms)',
    'user_action_duration_ms':'Duração da ação do usuário (ms)',
    'max_attempts_per_context':'Máximo de tentativas por contexto', 'max_attempts_per_page':'Máximo de tentativas por página',
    'min_ms':'Mínimo (ms)', 'max_ms':'Máximo (ms)', 'mean_ms':'Média (ms)', 'median_ms':'Mediana (ms)',
    'stddev_ms':'Desvio padrão (ms)', 'p75_ms':'Percentil 75 (ms)', 'p90_ms':'Percentil 90 (ms)',
    'p95_ms':'Percentil 95 (ms)', 'p99_ms':'Percentil 99 (ms)', 'mode':'Modo',
    'network_settled':'Rede estabilizada', 'network_unsettled_samples':'Amostras com rede não estabilizada',
    'page_limit':'Limite de páginas', 'pages_considered':'Páginas consideradas',
    'pagespeed_successes':'Sucessos PageSpeed', 'profile_id':'Perfil',
    'request_error_samples':'Amostras com erros de requisição', 'request_failed_count':'Requisições com falha',
    'reused_by_navigation':'Reutilizada na navegação', 'run_index':'Número da execução',
    'service':'Serviço', 'settle_seconds':'Espera por estabilização (s)', 'source_status':'Estado da fonte',
    'successful_contexts':'Contextos concluídos', 'target_samples_per_page':'Meta de amostras por página',
    'target_valid_samples':'Meta de amostras válidas', 'task_id':'ID da tarefa',
    'timeout_incompatible':'Tempo limite incompatível', 'trend_percent':'Variação entre metades (%)',
    'xhr_fetch_count':'Requisições XHR/fetch', 'collection_window_start':'Início da janela de coleta',
    'collection_window_end':'Fim da janela de coleta', 'country':'País / mercado', 'region':'Região',
    'domain':'Domínio', 'domain_status':'Presença do alvo', 'engine':'Mecanismo', 'language':'Idioma',
    'dropped_results':'Resultados descartados', 'normalization_incomplete_for_requested_depth':'Normalização incompleta no recorte',
    'observation_status':'Estado da observação', 'observed_position_ceiling':'Maior posição observada',
    'observed_position_count':'Posições observadas', 'query':'Consulta', 'raw_organic_result_count':'Resultados orgânicos na fonte',
    'requested_depth':'Profundidade consultada', 'requested_depth_complete':'Profundidade consultada completa',
    'result_count':'Resultados', 'result_type':'Tipo de resultado', 'serp_features':'Recursos da SERP',
    'snippet':'Trecho observado', 'source_audit_id':'Auditoria de origem', 'source_observation_id':'Observação de origem',
    'temporal_mode':'Modo temporal', 'url':'URL', 'attempts':'Tentativas', 'successes':'Sucessos',
    'evidence_ids_json':'IDs das evidências', 'integration_id':'Integração', 'party':'Relação com o site',
    'protocol':'Protocolo', 'resource_kind':'Tipo de recurso', 'resource_url':'URL do recurso',
    'actual_cost':'Custo parcial registrado', 'actual_pages':'Páginas executadas', 'currency':'Moeda',
    'expected_cost':'Previsão de custo', 'forecast_pages':'Páginas previstas',
    'likely_low':'Faixa provável — mínimo', 'likely_high':'Faixa provável — máximo',
    'potential':'Cenário potencial (P90)', 'relation':'Relação com a previsão',
    'notes':'Ressalvas registradas', 'confidence':'Confiança declarada na fonte',
    'unpriced_ai_attempts':'Tentativas de IA sem preço',
})
TYPED_LABELS = {
    'audit_mode': {'FULL':'Completo','QUICK':'Rápido'},
    'domain': {'ACCESSIBILITY':'Acessibilidade','CONTENT':'Conteúdo','SECURITY':'Segurança'},
    'source': {'AI':'IA'},
    'dimension': {'ACCESSIBILITY':'Acessibilidade','BEST_PRACTICES':'Boas práticas','CONTENT':'Conteúdo','EXPERIENCE':'Experiência','GEO_SEARCH_AI':'GEO, busca e IA','PERFORMANCE':'Desempenho','SECURITY':'Segurança','SEMANTICS':'Semântica','SEO':'SEO','STRUCTURED_DATA':'Dados estruturados','VULNERABILITIES':'Vulnerabilidades','YMYL':'YMYL'},
    'expected_gain': {'HIGH':'Alto','MEDIUM':'Médio','LOW':'Baixo'},
}
# Presentation-only interpretation of persisted enum domains.
# Never replace arbitrary prose, IDs, URLs, selectors, code or source data.
DIMENSION_LABELS = {
    'OVERALL_READINESS':'Índice de Prontidão Search & IA (SARI)',
    'DISCOVERY_ACCESS':'Acesso e descoberta', 'INDEXABILITY':'Indexabilidade',
    'CONTENT_EXTRACTABILITY':'Extração de conteúdo',
    'SEMANTIC_STRUCTURE':'Estrutura semântica', 'ENTITY_CLARITY':'Clareza de entidades',
    'STRUCTURED_DATA':'Dados estruturados', 'ANSWERABILITY':'Capacidade de resposta',
    'CITATION_READINESS':'Preparação para citação',
    'EVIDENCE_TRUST':'Confiança na evidência', 'INTENT_COVERAGE':'Cobertura de intenção',
    'CONTENT_VALUE':'Valor do conteúdo', 'SEO':'SEO', 'GEO_SEARCH_AI':'GEO, busca e IA',
    'ACCESSIBILITY':'Acessibilidade', 'PERFORMANCE':'Desempenho',
    'SECURITY':'Segurança', 'EXPERIENCE':'Experiência',
}
ENTITY_TYPE_LABELS = {
    'ORGANIZATION':'Organização', 'PERSON':'Pessoa', 'PRODUCT':'Produto',
    'SERVICE':'Serviço', 'PLACE':'Local', 'BRAND':'Marca',
    'TOPIC':'Assunto', 'OTHER':'Outro tipo de entidade',
}
SCOPE_LABELS = {
    'URL_SET':'Conjunto de URLs', 'DEVICE_SNAPSHOT':'Captura por dispositivo',
    'SEARCH_QUERY':'Consulta de pesquisa', 'URL':'URL individual',
    'ORIGIN':'Origem do site', 'SITE':'Site', 'PAGE':'Página',
    'AUDIT':'Auditoria', 'GLOBAL':'Visão geral',
    'FIELD':'Medição real de usuários', 'LAB':'Medição em laboratório',
    'URL_LEVEL':'URL específica', 'ORIGIN_LEVEL':'Origem do site',
}
METHOD_LABELS = {
    'DETERMINISTIC_PERSISTED_EVIDENCE':'Análise determinística de evidências registradas',
    'DETERMINISTIC':'Análise baseada em regras, sem IA',
    'PERSISTED_EVIDENCE':'Evidências já registradas',
}
CONFIDENCE_SCOPE_LABELS = {
    'LIMITED':'Limitada às evidências disponíveis',
    'LOCAL':'Limitada ao ambiente observado',
    'INSUFFICIENT':'Evidência insuficiente para conclusão ampla',
    'GLOBAL':'Abrangência global declarada',
}
PROVENANCE_LABELS = {
    'LOCAL_DNS_RESOLVER':'Resolvedor DNS local',
    'LOCAL_TLS_SOCKET':'Conexão TLS observada localmente',
    'LOCAL_TCP_SOCKET':'Conexão TCP observada localmente',
    'LOCAL_OPERATOR_PROCESS':'Sonda executada localmente com autorização',
    'NO_DNS_CAPTURE':'DNS não medido separadamente na captura',
    'NO_TCP_TIMING_CAPTURE':'Tempo de conexão TCP não medido separadamente',
    'NO_TLS_TIMING_CAPTURE':'Tempo de negociação TLS não medido separadamente',
    'NO_ACTIVE_PROBE':'Sonda complementar não realizada',
    'NO_ENRICHMENT':'Geolocalização ou ASN não enriquecidos',
    'LOCAL_MAXMIND_MMDB':'Base geográfica local',
    'LOCAL_MMDB_CITY':'Base geográfica local',
    'AUD_CAPTURE':'Captura registrada na auditoria',
}
FIELD_ENUM_LABELS = {
    'category': {'DISCOVERY_ACCESS':'Acesso e descoberta do conteúdo'},
    'dimension': DIMENSION_LABELS,
    'provenance': PROVENANCE_LABELS,
    'measurement_origin': PROVENANCE_LABELS,
    'entity_type': ENTITY_TYPE_LABELS,
    'scope': SCOPE_LABELS,
    'field_scope': SCOPE_LABELS,
    'url_scope': SCOPE_LABELS,
    'analysis_method': METHOD_LABELS,
    'confidence_scope': CONFIDENCE_SCOPE_LABELS,
    'method': METHOD_LABELS,
    'source_kind': ORIGIN_LABELS,
    'origin_kind': ORIGIN_LABELS,
    'source': {'AI':'IA', 'GSC':'Google Search Console',
               'SERP':'Resultados de busca', 'EXTERNAL':'Fonte externa'},
    'source_mode': {'AUTO':'Automático', 'MIXED':'Misto',
                    'PERSISTED':'Dados já registrados', 'MANUAL':'Manual'},
    'decision': {'ACCEPTED':'Aceita', 'REJECTED':'Rejeitada', 'PENDING':'Pendente'},
    'required': {'1':'Sim', '0':'Não', 'TRUE':'Sim', 'FALSE':'Não'},
}
FIELD_ENUM_LABELS['source'].update({'DETERMINISTIC-RULES-ENGINE':'Motor de regras determinísticas',
                                  'LOCAL-AUDIT-HISTORY':'Histórico local de auditorias'})
FIELD_ENUM_LABELS['method'].update({'PASSIVE_READ_ONLY':'Leitura da captura passiva já registrada',
                                   'EXPLICIT_DNS_TCP_TLS_PROBE':'Sonda autorizada de DNS, TCP e TLS',
                                   'WINDOWS_TRACERT':'Rastreamento ICMP registrado pelo tracert'})
FIELD_ENUM_LABELS['last_error_code'] = {
    'PLANNED_WORK_NOT_EXECUTED':'Execução encerrada antes de uma tentativa efetiva',
    'AI_NOT_CONFIGURED':'Nenhum provedor de IA apto configurado',
}
PROVENANCE_LABELS.update({
    'CDP_MAIN_DOCUMENT_RESPONSE':'Resposta principal observada pelo navegador (CDP)',
    'PLAYWRIGHT_MAIN_NAVIGATION_RESPONSE_SERVER_ADDR':'Endereço remoto observado pelo navegador (Playwright)',
    'RAW_HTTP_CAPTURE':'Resposta HTTP persistida',
    'AUD_PERSISTED_CAPTURE':'Captura persistida da auditoria',
})
STATUS_LABELS.update({'OPEN':'Em aberto', 'NOT_COMPARABLE':'Não comparável', 'NÃO COMPARÁVEL':'Não comparável'})
VALUE_LABELS.update(STATUS_LABELS)
FIELD_ENUM_LABELS['confidence'] = {'BOA':'Boa'}
FIELD_ENUM_LABELS['device'] = {'BOTH':'Ambos os dispositivos'}
FIELD_ENUM_LABELS.update({
    'party': {'FIRST_PARTY':'Primeira parte', 'THIRD_PARTY':'Terceira parte', 'INLINE':'Incluído na página'},
    'integration_id': {'TLS_EXTERNAL':'TLS externo', 'THREAT_REPUTATION':'Reputação de ameaças',
                       'MDN_OBSERVATORY':'MDN Observatory', 'CISA_KEV':'CISA KEV'},
    'evidence_type': {'DOM_ELEMENT':'Elemento DOM', 'HTML_ELEMENT':'Elemento HTML',
                      'HTTP_HEADER':'Cabeçalho HTTP', 'HTTP_RESPONSE':'Resposta HTTP',
                      'MAIN_CONTENT':'Conteúdo principal', 'META_TAG':'Metadado HTML',
                      'ROBOTS_RULE':'Regra de robots.txt', 'SITEMAP_ENTRY':'Entrada de sitemap',
                      'VISUAL_SNAPSHOT':'Captura visual'},
    'rendering_mode': {'PLAYWRIGHT_CHROMIUM':'Navegador Chromium via Playwright'},
    'calibration_source': {'MANUAL_CALIBRATION':'Calibração manual registrada'},
    'kpm': {'USER_ACTION_DURATION':'Duração da ação do usuário'},
    'temporal_mode': {'LIVE_RECOLLECTION':'Nova coleta registrada nesta execução'},
    'comparison_status': {'CUSTOMER_CONTENT_NOT_COMPARABLE':'Conteúdo do alvo não comparável'},
})
FIELD_ENUM_LABELS['source'].update({'PAGESPEED_INSIGHTS':'PageSpeed Insights',
                                   'SYNTHETIC_LOAD_ACTION':'Carregamento e ação sintéticos'})
STATUS_LABELS.update({'DEFAULT_OFF':'Desabilitado por padrão',
                      'TRANSIENT_SHELL':'Interface transitória observada na captura'})
VALUE_LABELS.update(STATUS_LABELS)
SEMANTIC_ENUM_FIELDS = ENUM_FIELDS | {
    'category',
    'last_error_code',
    'party', 'integration_id', 'evidence_type', 'rendering_mode',
    'calibration_source', 'kpm', 'temporal_mode', 'comparison_status',
    'entity_type', 'component', 'dimension', 'scope', 'scope_key', 'audit_mode',
    'url_scope', 'analysis_method', 'confidence_scope', 'method',
    'decision', 'required', 'domain', 'source', 'source_kind',
    'source_mode', 'origin_kind', 'measurement_origin', 'purpose',
    'error_scope', 'domain_status', 'service_state', 'event_state',
    'rule_result', 'provider_state', 'hop_state', 'provenance',
}
# Readable interpretation of persisted deterministic SERP classifier enums.
# These maps affect only presentation, never free-text evidence or SQLite.
COMPETITIVE_CLASSES = {
    'CUSTOMER': 'Resultado do domínio auditado',
    'ORGANIC_CANDIDATE': 'Resultado orgânico externo (candidato, não concorrente comprovado)',
    'PUBLIC_AUTHORITY': 'Site de autoridade pública',
    'KNOWLEDGE_REFERENCE': 'Fonte de referência e conhecimento',
    'SOCIAL_PLATFORM': 'Rede social',
    'VIDEO_PLATFORM': 'Plataforma de vídeo',
    'MARKETPLACE': 'Marketplace (candidato à comparação de conteúdo)',
    'NON_ORGANIC': 'Resultado não orgânico',
}
COMPETITIVE_REASONS = {
    'matches configured customer domain': 'Pertence ao domínio configurado para a auditoria.',
    'public-authority domain heuristic': 'Domínio identificado por regra como fonte de autoridade pública.',
    'knowledge/reference platform heuristic': 'Domínio identificado por regra como fonte de referência.',
    'social platform heuristic': 'Domínio identificado por regra como rede social.',
    'video platform heuristic': 'Domínio identificado por regra como plataforma de vídeos.',
    'marketplace heuristic; retained as a Search competitor candidate':
        'Marketplace observado; mantido como candidato para comparação de conteúdo, sem presumir concorrência comercial.',
    'external organic result; business equivalence is not inferred':
        'Resultado orgânico externo; não foi comprovada equivalência entre os negócios.',
}

TECHNICAL_ONLY_FIELDS = frozenset({
    'projection_json', 'query_json', 'proposed_json', 'request_payload',
    'response_payload', 'limitations_json', 'implementation_guidance_json',
    'validation_steps_json', 'original_html', 'suggested_html',
    'raw_payload', 'configuration_json',
})
MACHINE_TOKEN = re.compile(r'^[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)*$')


def typed_public_label(value, field):
    """Interpret a known enum domain in pt-BR, without changing canonical data."""
    if value is None:
        return 'N/D'
    if field == 'required' and type(value) is bool:
        return 'Sim' if value else 'Não'
    if field == 'required' and type(value) is int and value in (0, 1):
        return 'Sim' if value == 1 else 'Não'
    if not isinstance(value, str):
        return value
    token = value.upper()
    if field == 'component':
        return {'SEARCH': 'Pesquisa em mecanismos de busca'}.get(token) or component_label(value)
    if field == 'scope_key':
        return scope_label(value)
    mapped = FIELD_ENUM_LABELS.get(field, {}).get(token)
    if mapped is not None:
        return mapped
    if field == 'required':
        return 'Não determinado'
    generic = (SEVERITY_LABELS if field == 'severity'
               else PRIORITY_LABELS if field in {'priority', 'priority_class'}
               else VALUE_LABELS)
    known = generic.get(token) or supplemental_public_label(value)
    if known is None and MACHINE_TOKEN.fullmatch(value):
        known = canonical_public_label(value)
    if known is not None:
        return known
    return safe_visible_fallback(value) if MACHINE_TOKEN.fullmatch(value) else value


def timezone_for_records(records):
    from .read_model import thaw
    audit_ids = {thaw(r.data).get('audit_id') for r in records if r.table == 'audits'}
    configurations = [thaw(r.data).get('configuration_json') for r in records if r.table == 'audit_execution_configurations' and thaw(r.data).get('audit_id') in audit_ids]
    if len(configurations) != 1:
        return presentation_timezone_for_audit(None)
    configuration = configurations[0]
    if isinstance(configuration,str):
        try:
            configuration=json.loads(configuration)
        except ValueError:
            configuration=None
    return presentation_timezone_for_audit(configuration)


def timezone_provenance(reason):
    if reason.startswith('settings.'):
        return 'Persistido na configuração da AUD'
    if reason.startswith('INVALID'):
        return 'Fuso persistido inválido; utilizado padrão de apresentação do produto.'
    if 'CONFLICT' in reason:
        return 'Configuração divergente; preferida apresentação persistida.'
    return 'Fuso histórico não persistido; utilizado padrão de apresentação do produto.'


def public_value(value, field=None, timezone_name=None):
    if value is None:
        return 'N/D'
    if field in {'requested','configured','effective_enabled','ai_enabled','retryable',
                 'consumed_by_navigation','reused_by_navigation','network_settled',
                 'error_forced_frustrated','requested_depth_complete',
                 'normalization_incomplete_for_requested_depth'} and type(value) in (bool, int):
        return {0:'Não',1:'Sim'}.get(value, 'Não determinado')
    if field in {'eligible_for_content_comparison', 'selected_for_content_comparison'}:
        if type(value) in (bool, int) and value in (0, 1, False, True):
            return 'Sim' if value else 'Não'
        return 'Não determinado'
    if field == 'classification' and isinstance(value, str):
        return COMPETITIVE_CLASSES.get(value.upper(), value)
    if field == 'reason' and isinstance(value, str):
        if value == 'SMALL_GROUP_BELOW_NORMAL_MINIMUM':
            return 'Grupo pequeno, abaixo do mínimo normal de amostras'
        if value in COMPETITIVE_REASONS:
            return COMPETITIVE_REASONS[value]
        if value.startswith('SERP result_type='):
            return 'Resultado não orgânico segundo o provedor (tipo: ' + value.split('=', 1)[1] + ').'
    if field == 'lcp_lab_ms' and isinstance(value, (float, int)):
        return f'{value:,.0f}'.replace(',', ' ')
    if field == 'domain_status' and value == 'NOT_FOUND_WITHIN_DEPTH':
        return 'Não encontrado na profundidade consultada'
    if (field in TIMESTAMPS or (isinstance(field, str) and field.endswith(('_at', '_utc', '_timestamp')))) and isinstance(value,str) and re.fullmatch(r'\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?',value):
        if timezone_name:
            try:
                return format_presentation_timestamp(value,timezone_name=timezone_name)
            except (ValueError,OverflowError):
                pass
    if field in CIVIL_DATES and isinstance(value, str):
        civil = format_presentation_date_only(value)
        if civil is not None:
            return civil
    if type(value) is float:
        return str(value).replace('.',',')
    if field in TYPED_LABELS:
        known = TYPED_LABELS[field].get(str(value))
        if known is not None:
            return known
    if field in SEMANTIC_ENUM_FIELDS:
        return typed_public_label(value, field)
    if field in {'estimated_cost','observed_cost','amount','percentage'} and isinstance(value,str) and re.fullmatch(r'-?\d+(?:\.\d+)?',value):
        return value.replace('.',',')
    return value


def presentation_timestamps(value, timezone_name):
    """Localize only typed timestamp keys in visible HTML data projections.

    Never change source DB, annex JSON, unrelated prose, dates or epoch numbers.
    """
    if isinstance(value, dict):
        return {key: presentation_timestamps(item, timezone_name)
                if isinstance(item, (dict, list, tuple))
                else (public_value(item, key, timezone_name)
                      if key in TIMESTAMPS or key in CIVIL_DATES
                      or (isinstance(key, str) and key.endswith(('_at', '_utc', '_timestamp')))
                      else item)
                for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [presentation_timestamps(item, timezone_name) for item in value]
    return value


def chip_tone(value, field):
    token=str(value or '').upper()
    if field in {'severity','priority','priority_class'}:
        return {'CRITICAL':'bad critical','HIGH':'bad','MEDIUM':'warn','LOW':'none','INFO':'info','INFORMATIONAL':'info'}.get(token,'none')
    if token in {'SUCCESS','COMPLETE','COMPLETED','PASS','CONSOLIDATED','GOOD','MEDIDO'}:
        return 'ok'
    if token in {'PARTIAL','WARNING','NEEDS_IMPROVEMENT','TOLERATING','COMPLETE_WITH_LIMITATIONS','PARCIAL'}:
        return 'warn'
    if token == 'CRITICAL':
        return 'bad critical'
    if token in {'FAILED','ERROR','FAIL','BLOCKED','COLLECTION_FAILED'}:
        return 'bad'
    return 'info' if token in {'INFO','INFORMATIONAL','EXTERNAL'} else 'none'


def metric_label(row,key,labels):
    if key=='agentic_browsing_score':
        return 'Lighthouse · Navegação por agentes'
    if key!='apdex_score':
        return labels.get(row.get('dimension',key), public_value(row.get('dimension',key), 'dimension'))
    family=row.get('_source_table')
    if family=='synthetic_apdex_summaries':
        return 'Apdex sintético de navegação'
    if family=='synthetic_population_apdex_summaries':
        return 'Apdex sintético populacional'
    if family=='synthetic_ux_apdex_summaries':
        suffix=' — agregado dos dispositivos' if row.get('device')=='POPULATION' else ' — '+str(public_value(row.get('device'),'device'))
        return 'Apdex sintético de experiência'+suffix
    return 'Apdex — família não determinada'
