"""Typed public labels only: never translate evidence or untyped free text."""
import json
import re
from rasai.time_contract import presentation_timezone_for_audit, format_presentation_timestamp

FIELD_LABELS = {'status':'Estado','severity':'Criticidade','priority':'Prioridade','provider':'Provedor','model':'Modelo','source':'Origem','reference':'Referência','references':'Referências','scope':'Escopo','device':'Dispositivo','native_usage_quantity':'Requisições','input_tokens':'Tokens de entrada','output_tokens':'Tokens de saída','duration_ms':'Duração (ms)','created_at':'Criada em','started_at':'Iniciada em','completed_at':'Concluída em','captured_at':'Capturada em','collected_at':'Coletada em','executed_at':'Executada em','updated_at':'Atualizada em','finished_at':'Finalizada em'}
STATUS_LABELS = {'SUCCESS':'Concluído','COMPLETE':'Concluído','COMPLETED':'Concluído','PASS':'Aprovado','PARTIAL':'Parcial','WARNING':'Atenção','FAILED':'Falhou','ERROR':'Falhou','FAIL':'Reprovado','BLOCKED':'Bloqueado','NOT_REQUESTED':'Não solicitado','NOT_APPLICABLE':'Não aplicável','SKIPPED':'Não executado','UNKNOWN':'Não determinado','CONSOLIDATED':'Consolidado','NOT_CONSOLIDATED':'Não consolidado','COMPLETE_WITH_LIMITATIONS':'Concluído com limitações','GOOD':'Bom','NEEDS_IMPROVEMENT':'Precisa melhorar','TOLERATING':'Tolerável','OBSERVED':'Observado','COHERENT':'Coerente','NOT_DETERMINABLE':'Não determinável','AVAILABLE':'Disponível','NOT_CONFIGURED':'Não configurado','DISABLED':'Desabilitado','NO_DATA':'Sem dados','ABSENT':'Ausente'}
STATUS_LABELS.update({'MISSING_PROPOSED':'Ausente — proposta disponível','MEASURED':'Medido','READY':'Pronto','RESPONSE':'Resposta','LIMITED_AVAILABILITY':'Disponibilidade limitada','NEWLY_AVAILABLE':'Disponível recentemente','WIDELY_AVAILABLE':'Amplamente disponível'})
SEVERITY_LABELS = {'CRITICAL':'Crítica','HIGH':'Alta','MEDIUM':'Média','LOW':'Baixa','INFO':'Informativa','INFORMATIONAL':'Informativa'}
PRIORITY_LABELS = {k:v for k,v in SEVERITY_LABELS.items() if k not in {'INFO','INFORMATIONAL'}}
DEVICE_LABELS = {'MOBILE':'Móvel','DESKTOP':'Desktop','POPULATION':'Agregado de experiência','MIXED_DEVICE_POPULATION':'Agregado dos dispositivos configurados'}
ORIGIN_LABELS = {'PRODUCT_PROPOSAL':'Proposta de produto','PERSISTED_CONTRACT':'Contrato persistido','PUBLIC_STANDARD':'Padrão público','DETERMINISTIC':'Regra determinística','CONTENT_AI':'IA de conteúdo','DEEP_ANALYSIS':'Análise aprofundada','JSONLD':'JSON-LD','SECURITY_REMEDIATION':'Remediação de segurança','EXTERNAL':'Externo','AUTO':'Automático','MIXED':'Misto'}
VALUE_LABELS = {**STATUS_LABELS, **SEVERITY_LABELS, **DEVICE_LABELS, **ORIGIN_LABELS}
TIMESTAMPS = {'created_at','started_at','completed_at','captured_at','collected_at','executed_at','projected_at','updated_at','fetch_time','lighthouse_fetch_time','finished_at','observed_at','calculated_at'}
ENUM_FIELDS = {'status','state','result','severity','priority','priority_class','coverage','confidence','device','source_kind','source_mode','origin_kind','effort','completion_status','consolidation_status','observation_status','outcome','analysis_state','field_scope','cwv_assessment'}
FIELD_LABELS.update({'projected_at':'Projetada em','fetch_time':'Coletada em','lighthouse_fetch_time':'Coletada pelo Lighthouse em','observed_at':'Observada em','calculated_at':'Calculada em','type':'Tipo','selector':'Seletor','line':'Linha','column':'Coluna','coverage':'Cobertura','canonical':'URL canônica','sha256':'SHA-256'})
TYPED_LABELS = {
    'audit_mode': {'FULL':'Completo','QUICK':'Rápido'},
    'domain': {'ACCESSIBILITY':'Acessibilidade','CONTENT':'Conteúdo','SECURITY':'Segurança'},
    'source': {'AI':'IA'},
    'dimension': {'ACCESSIBILITY':'Acessibilidade','BEST_PRACTICES':'Boas práticas','CONTENT':'Conteúdo','EXPERIENCE':'Experiência','GEO_SEARCH_AI':'GEO, busca e IA','PERFORMANCE':'Desempenho','SECURITY':'Segurança','SEMANTICS':'Semântica','SEO':'SEO','STRUCTURED_DATA':'Dados estruturados','VULNERABILITIES':'Vulnerabilidades','YMYL':'YMYL'},
    'expected_gain': {'HIGH':'Alto','MEDIUM':'Médio','LOW':'Baixo'},
}


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
    if field in TIMESTAMPS and isinstance(value,str) and re.fullmatch(r'\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?',value):
        if timezone_name:
            try:
                return format_presentation_timestamp(value,timezone_name=timezone_name)
            except (ValueError,OverflowError):
                pass
    if type(value) is float:
        return str(value).replace('.',',')
    if field in TYPED_LABELS:
        return TYPED_LABELS[field].get(str(value),value)
    if field in ENUM_FIELDS:
        token=str(value).upper()
        labels=SEVERITY_LABELS if field=='severity' else (PRIORITY_LABELS if field in {'priority','priority_class'} else VALUE_LABELS)
        return labels.get(token,value)
    if field in {'estimated_cost','observed_cost','amount','percentage'} and isinstance(value,str) and re.fullmatch(r'-?\d+(?:\.\d+)?',value):
        return value.replace('.',',')
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
    if token in {'FAILED','ERROR','FAIL','BLOCKED'}:
        return 'bad'
    return 'info' if token in {'INFO','INFORMATIONAL','EXTERNAL'} else 'none'


def metric_label(row,key,labels):
    if key!='apdex_score':
        return labels.get(row.get('dimension',key),row.get('dimension',key))
    family=row.get('_source_table')
    if family=='synthetic_apdex_summaries':
        return 'Apdex sintético de navegação'
    if family=='synthetic_population_apdex_summaries':
        return 'Apdex sintético populacional'
    if family=='synthetic_ux_apdex_summaries':
        suffix=' — agregado dos dispositivos' if row.get('device')=='POPULATION' else ' — '+str(public_value(row.get('device'),'device'))
        return 'Apdex sintético de experiência'+suffix
    return 'Apdex — família não determinada'
