"""Explicit thematic field projections, without row limits or completeness claims."""
from collections import defaultdict

from .capture_projection import public_data, object_value
from .components import table, text
from .read_model import PAGES, destination, thaw
from .presentation_labels import public_value

# These are observable fields, not every storage/configuration column. Their
# exact scope and all remaining fields are published in the receipt below.
FIELDS = {
 'page_snapshots': 'title canonical device captured_at http_status rendering_mode architecture_classification preview_browser preview_viewport preview_runtime_count preview_visual_ref',
 'audit_fulfillment_attempts': 'component attempt_number status started_at finished_at result_ref',
 'audit_execution_sessions': 'kind source state started_at heartbeat_at finished_at',
 'audit_fulfillment_work_items': 'component required status attempt_count retryable last_error_code last_attempt_at last_success_at',
 'console_execution_projections': 'projected_at exposure_level min_pages max_pages device_contexts min_ai_attempts max_ai_attempts min_web_calls max_web_calls reasons',
 'pages': 'normalized_url depth discovery_sources',
 'element_observations': 'tag_name selector text_excerpt device captured_at',
 'evidence': 'evidence_type source observed_value artifact_reference captured_at',
 'standards_metric_observations': 'label value unit scope target device state source methodology relation_degree classification description grade errors warnings tests_passed tests_failed signals browser_support',
 'standards_service_runs': 'service_id requested configured effective_enabled state targets_attempted targets_succeeded',
 'm24_runs': 'status llms_state ai_enabled ai_state diagnostics_count scoring_impact',
 'm24_ai_results': 'state reason',
 'rule_executions': 'rule_id rule_version result observed_value expected_condition device executed_at evidence_ids',
 'serp_results': 'position title snippet domain url result_type serp_features',
 'serp_evidence_provenance': 'temporal_mode captured_at source_audit_id source_observation_id',
 'synthetic_apdex_runs': 'status threshold_seconds frustration_seconds target_valid_samples max_attempts_per_context attempted_samples valid_samples invalid_samples delay_seconds concurrency reason',
 'synthetic_apdex_samples': 'device run_index profile_id status classification duration_ms http_status cpu_method network_method captured_at',
 'synthetic_apdex_acquisitions': 'device profile_id source source_status load_duration_ms http_status cpu_method network_method consumed_by_navigation captured_at',
 'synthetic_apdex_acquisition_runs': 'mode eligible_acquisitions reused_by_navigation timeout_incompatible updated_at',
 'synthetic_apdex_summaries': 'device profile_id valid_samples invalid_samples satisfied_count tolerating_count frustrated_count min_ms max_ms mean_ms median_ms stddev_ms coefficient_of_variation p75_ms p90_ms p95_ms p99_ms first_half_mean_ms second_half_mean_ms trend_percent',
 'synthetic_ux_apdex_runs': 'status task_id target_samples_per_page max_attempts_per_page attempted_samples valid_samples invalid_samples kpm satisfied_threshold_seconds frustrated_threshold_seconds error_scope settle_seconds calibration_source',
 'synthetic_ux_apdex_samples': 'device run_index profile_id status classification kpm kpm_value_ms user_action_duration_ms navigation_duration_ms lcp_ms cls http_status xhr_fetch_count javascript_error_count request_failed_count http_error_count network_settled error_forced_frustrated',
 'synthetic_ux_apdex_summaries': 'device profile_id valid_samples invalid_samples satisfied_count tolerating_count frustrated_count error_forced_frustrated_count mean_ms median_ms p75_ms p90_ms p95_ms p99_ms javascript_error_samples request_error_samples network_unsettled_samples',
 'web_performance_attempts': 'service status http_status duration_ms created_at artifact_reference artifact_sha256',
 'lighthouse_execution_profiles': 'device form_factor benchmark_index lighthouse_total_ms captured_at',
 'passive_security_resources': 'resource_kind party domain protocol resource_url evidence_ids_json',
 'passive_security_integrations': 'integration_id requested state attempts successes observed_at',
 'console_cost_forecast_outcomes': 'currency expected_cost actual_cost status relation likely_low likely_high potential forecast_pages actual_pages confidence unpriced_ai_attempts source notes',
}
TITLES = {
 'rule_executions':'Critérios e resultados de cada regra executada',
 'serp_results':'Títulos e trechos dos resultados orgânicos observados',
 'standards_metric_observations':'Métricas e funcionalidades por ferramenta',
 'synthetic_apdex_samples':'Medições individuais de navegação',
 'synthetic_ux_apdex_samples':'Medições individuais de experiência',
 'synthetic_apdex_summaries':'Dispersão das medições de navegação',
 'synthetic_ux_apdex_summaries':'Dispersão das medições de experiência',
 'passive_security_resources':'Inventário observacional por recurso e origem',
 'console_cost_forecast_outcomes':'Intervalos e cobertura da previsão financeira',
 'evidence':'Sinais persistidos por tipo de evidência',
}


def build_analytical_views(tables, records, schema, timezone_name):
    by_table = defaultdict(list)
    for r in records:
        by_table[r.table].append(r)
    rendered = defaultdict(str)
    receipt = {page+'.html': {} for page,_ in PAGES}
    for name, originals in tables.items():
        page = destination(name)
        if page is None:
            continue
        fields = FIELDS.get(name, '').split()
        entries, structured = [], set()
        for record in by_table[name]:
            row = public_data(thaw(record.data))
            if name == 'page_snapshots':
                from .catalog_context import _capture_preview
                row = _capture_preview(row)
            detail = object_value(row.get('details_json'))
            if name == 'standards_metric_observations':
                row = {**row, **{k:detail[k] for k in fields if k in detail}}
                compatibility = detail.get('per_compat_key')
                if isinstance(compatibility,dict):
                    row['browser_support'] = '; '.join(str(key)+': '+', '.join(str(k)+' '+str(v) for k,v in item.get('support',{}).items()) for key,item in compatibility.items() if isinstance(item,dict) and isinstance(item.get('support'),dict)) or None
                    row['signals'] = '; '.join(str(s.get('kind'))+': '+str(s.get('evidence')) for item in compatibility.values() if isinstance(item,dict) for s in item.get('signals',[]) if isinstance(s,dict)) or None
            entry = {k:row.get(k) for k in fields}
            if name == 'standards_metric_observations' and entry.get('classification'):
                entry['classification'] = public_value(entry['classification'], 'status')
            for k,v in list(entry.items()):
                if isinstance(v, dict) or (isinstance(v, list) and any(isinstance(x,(dict,list)) for x in v)):
                    # Do not relabel arbitrary JSON as interpreted evidence.
                    structured.add(k)
                    names = list(v) if isinstance(v,dict) else ['itens estruturados']
                    entry[k] = 'Estrutura persistida; campos: ' + ', '.join(names) + '. Consulte a evidência vinculada.'
            entry['_ref'] = record.href
            entries.append(entry)
        def known(v):
            return v is not None and v != 'N/D' and v != ''
        available = [k for k in fields if any(known(e.get(k)) for e in entries)]
        direct = [k for k in available if k not in structured]
        technical = [k for k in schema[name]['columns'] if k not in direct]
        receipt[page+'.html'][name] = dict(
            records_available=len(originals), analytical_records=len(entries) if available else 0,
            preview_records=0, direct_fields=direct, structured_fields_in_detail=sorted(structured),
            fields_not_in_this_projection=technical,
            field_cells={k:sum(known(e.get(k)) for e in entries) for k in direct},
            field_origins={k:(k if k in schema[name]['columns'] else
                'browser_metadata (projeção _capture_preview)' if k.startswith('preview_') else
                'details_json.per_compat_key' if k in {'signals','browser_support'} else 'details_json.'+k) for k in direct},
            adequate_representation_certified=False, executive_interpretation_certified=False,
            limitation='EXPLICIT_FIELD_SCOPE_ONLY_NOT_FAMILY_COMPLETENESS')
        if not available:
            continue
        title = TITLES.get(name, 'Observações por contexto · '+name.replace('_',' '))
        # Existing table/filter/sort/modal components; no new visual system.
        rendered[page] += '<section data-analytical-family="'+text(name)+'"><h2>'+text(title)+'</h2>'
        rendered[page] += '<p class="rf">Todos os '+text(len(entries))+' registros desta fonte, nos campos indicados. Dados persistidos, sem nova classificação ou conclusão. Campos estruturados não interpretados permanecem no vínculo de evidência.</p>'
        rendered[page] += table(title, entries, [(k,k.replace('_',' ')) for k in available]+[('_ref','Evidência')],
                                timezone_name=timezone_name, full_text=True)
        rendered[page] += '</section>'
    return rendered, receipt
