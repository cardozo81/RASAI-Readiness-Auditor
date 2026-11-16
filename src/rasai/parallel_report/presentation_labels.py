"""Typed public labels only: never translate evidence or untyped free text."""
import json
import re
from rasai.time_contract import presentation_timezone_for_audit, format_presentation_timestamp
from rasai.public_language import component_label, scope_label, supplemental_public_label, safe_visible_fallback
from rasai.catalog_report_public_labels import public_label as canonical_public_label

FIELD_LABELS = {'status':'Estado','severity':'Criticidade','priority':'Prioridade','provider':'Provedor','model':'Modelo','source':'Origem','reference':'Referência','references':'Referências','scope':'Escopo','device':'Dispositivo','native_usage_quantity':'Requisições','input_tokens':'Tokens de entrada','output_tokens':'Tokens de saída','duration_ms':'Duração (ms)','created_at':'Criada em','started_at':'Iniciada em','completed_at':'Concluída em','captured_at':'Capturada em','collected_at':'Coletada em','executed_at':'Executada em','updated_at':'Atualizada em','finished_at':'Finalizada em','capture_utc':'Capturada em','capture_timestamp':'Capturada em','classification':'Tipo de resultado','eligible_for_content_comparison':'Comparação de conteúdo elegível','selected_for_content_comparison':'Selecionado para comparação'}
STATUS_LABELS = {'SUCCESS':'Concluído','COMPLETE':'Concluído','COMPLETED':'Concluído','PASS':'Aprovado','PARTIAL':'Parcial','WARNING':'Atenção','FAILED':'Falhou','ERROR':'Falhou','FAIL':'Reprovado','BLOCKED':'Bloqueado','NOT_OBSERVED':'Não observado','COLLECTION_FAILED':'Falha na coleta','INCONCLUSIVE':'Inconclusivo','NOT_REQUESTED':'Não solicitado','NOT_APPLICABLE':'Não aplicável','SKIPPED':'Não executado','UNKNOWN':'Não determinado','CONSOLIDATED':'Consolidado','NOT_CONSOLIDATED':'Não consolidado','COMPLETE_WITH_LIMITATIONS':'Concluído com limitações','GOOD':'Bom','NEEDS_IMPROVEMENT':'Precisa melhorar','TOLERATING':'Tolerável','OBSERVED':'Observado','COHERENT':'Coerente','NOT_DETERMINABLE':'Não determinável','AVAILABLE':'Disponível','NOT_CONFIGURED':'Não configurado','DISABLED':'Desabilitado','NO_DATA':'Sem dados','ABSENT':'Ausente'}
STATUS_LABELS.update({
    'UNAVAILABLE':'Indisponível', 'NOT_AVAILABLE':'Não disponível',
    'REQUESTED_NOT_EXECUTED':'Solicitado, não executado',
    'FAILED_RETRYABLE':'Falha recuperável', 'FAILED_PERMANENT':'Falha permanente',
    'PENDING':'Pendente', 'RUNNING':'Em execução', 'IN_PROGRESS':'Em andamento',
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
ORIGIN_LABELS = {'PRODUCT_PROPOSAL':'Proposta de produto','PERSISTED_CONTRACT':'Contrato persistido','PUBLIC_STANDARD':'Padrão público','DETERMINISTIC':'Regra determinística','CONTENT_AI':'IA de conteúdo','DEEP_ANALYSIS':'Análise aprofundada','JSONLD':'JSON-LD','SECURITY_REMEDIATION':'Remediação de segurança','EXTERNAL':'Externo','AUTO':'Automático','MIXED':'Misto'}
VALUE_LABELS = {**STATUS_LABELS, **SEVERITY_LABELS, **DEVICE_LABELS, **ORIGIN_LABELS}
TIMESTAMPS = {'created_at','started_at','completed_at','captured_at','collected_at','executed_at','projected_at','updated_at','fetch_time','lighthouse_fetch_time','finished_at','observed_at','calculated_at','capture_utc','capture_timestamp','capture_time','capture_time_utc','timestamp_utc','provider_created_at','reused_at','persisted_at','requested_at','measurement_at'}
ENUM_FIELDS = {'status','state','result','severity','priority','priority_class','coverage','confidence','device','source_kind','source_mode','origin_kind','effort','completion_status','consolidation_status','observation_status','outcome','analysis_state','field_scope','cwv_assessment'}
FIELD_LABELS.update({'projected_at':'Projetada em','fetch_time':'Coletada em','lighthouse_fetch_time':'Coletada pelo Lighthouse em','observed_at':'Observada em','calculated_at':'Calculada em','type':'Tipo','selector':'Seletor','line':'Linha','column':'Coluna','coverage':'Cobertura','canonical':'URL canônica','sha256':'SHA-256'})
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
SEMANTIC_ENUM_FIELDS = ENUM_FIELDS | {
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
    if field in {'eligible_for_content_comparison', 'selected_for_content_comparison'}:
        if type(value) in (bool, int) and value in (0, 1, False, True):
            return 'Sim' if value else 'Não'
        return 'Não determinado'
    if field == 'classification' and isinstance(value, str):
        return COMPETITIVE_CLASSES.get(value.upper(), value)
    if field == 'reason' and isinstance(value, str):
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
                      if key in TIMESTAMPS
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
