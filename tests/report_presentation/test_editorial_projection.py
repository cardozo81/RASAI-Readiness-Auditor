"""Issue #722: high-value analytical projections, source rows only."""
import json
from rasai.parallel_report.read_model import build, SEARCH_PAGE
from rasai.parallel_report.analytical_views import build_analytical_views


def test_selected_semantic_and_provider_usage_sources_become_analytical_not_billing():
    tables = {
        'ai_provider_native_usage': [{
            'attempt_id': 'AI-1', 'provider': 'test', 'native_usage_quantity': 0,
            'native_usage_unit': 'search', 'observed_cost': None,
            'estimated_cost': 0.02, 'cost_currency': 'USD',
        }],
        'semantic_assessments': [{
            'assessment_type': 'NAMED_CONTEXT', 'result': 'UNKNOWN',
            'confidence': None, 'reasoning_summary': 'Sem evidência de comprovação',
        }],
        'perplexity_search_sources': [{
            'position': 1, 'title': 'Fonte persistida', 'url': 'https://example.org/',
        }],
        'passive_security_remediations': [{
            'finding_id': 'F-1', 'correction': 'Analisar configuração',
            'advisory_only': 1,
        }],
        'score_contributions': [{
            'score_id': 'S-1', 'rule_id': 'R-1', 'weight': 0.25,
            'result': 'PASS', 'effective_contribution': 0.17,
        }],
    }
    schema = {
        name: {'columns': sorted({field for row in rows for field in row}),
               'primary_key': [], 'foreign_keys': []}
        for name, rows in tables.items()
    }
    records = build(tables, schema)
    html, receipt = build_analytical_views(tables, records, schema, 'UTC')
    ia = receipt['ia-custos.html']['ai_provider_native_usage']
    assert 'native_usage_quantity' in ia['direct_fields']
    assert 'estimated_cost' in ia['direct_fields']
    assert 'observed_cost' not in ia['direct_fields']
    assert '0,02' in html['ia-custos']
    assert 'faturamento' in html['ia-custos']
    assert 'Sem evidência de comprovação' in html['conteudo']
    assert 'Fonte persistida' in html[SEARCH_PAGE]
    assert 'não aprovadas' in html['seguranca']
    assert '0,17' in html['indices']
    assert receipt['indices.html']['score_contributions']['executive_interpretation_certified'] is False


def test_competitor_page_and_root_cause_precision_are_source_backed_projections():
    """#722: visible fields are persisted; target selectors are not observations."""
    tables = {
        'serp_competitive_pages': [
            {'observation_id':'OBS-1', 'role':'CUSTOMER', 'domain':'example.test',
             'fetch_status':'OBSERVED', 'http_status':200, 'title':'Página cliente',
             'word_count':120},
            {'observation_id':'OBS-1', 'role':'COMPETITOR_CANDIDATE',
             'domain':'other.example', 'fetch_status':'ERROR',
             'http_status':None, 'title':None, 'word_count':None},
        ],
        'root_cause_precision': [
            {'finding_id':'F-1','rule_id':'BR-TEST', 'reason_code':'CANONICAL_ABSENT',
             'precise_cause_summary':'Canonical não observado',
             'observed_element_status':'ABSENT','observed_selector':None,
             'target_selector':'head > link[rel="canonical"]',
             'target_element':'link','target_location':'head',
             'materialized_at':'2026-11-18T10:00:00+00:00'},
        ],
    }
    schema = {
        name: {'columns':list(rows[0]), 'primary_key':[], 'foreign_keys':[]}
        for name,rows in tables.items()
    }
    records=build(tables,schema)
    html,receipt=build_analytical_views(tables,records,schema,'UTC')
    search=receipt[f'{SEARCH_PAGE}.html']['serp_competitive_pages']
    plan=receipt['plano.html']['root_cause_precision']
    assert search['analytical_records']==2
    assert {'role','fetch_status','http_status','word_count'} <= set(search['direct_fields'])
    assert 'Página cliente' in html[SEARCH_PAGE]
    assert 'other.example' in html[SEARCH_PAGE]
    # #728: these fields are human-facing execution states, not raw evidence.
    assert '<td title="Observado">Observado</td>' in html[SEARCH_PAGE]
    assert '<td title="Falhou">Falhou</td>' in html[SEARCH_PAGE]
    assert plan['analytical_records']==1
    assert 'reason_code' in plan['direct_fields']
    assert 'observed_element_status' in plan['direct_fields']
    assert 'target_selector' in plan['direct_fields']
    assert 'observed_selector' not in plan['direct_fields']
    assert 'CANONICAL_ABSENT' in html['plano']
    assert '<td title="Ausente">Ausente</td>' in html['plano']
    assert 'head &gt; link' in html['plano']
    # Original facts/identifiers are not rewritten when a cell is humanized.
    assert tables['serp_competitive_pages'][0]['fetch_status'] == 'OBSERVED'
    assert tables['root_cause_precision'][0]['observed_element_status'] == 'ABSENT'
    assert plan['executive_interpretation_certified'] is False


def test_728_contextual_state_labels_do_not_rewrite_literal_evidence():
    from rasai.parallel_report.presentation_labels import public_value

    assert public_value('OBSERVED', 'fetch_status') == 'Observado'
    assert public_value('ERROR', 'fetch_status') == 'Falhou'
    assert public_value('ABSENT', 'observed_element_status') == 'Ausente'
    assert public_value('NOT_APPLICABLE', 'observed_element_status') == 'Não aplicável'
    assert public_value('OBSERVED', 'observed_value') == 'OBSERVED'
    assert public_value('ABSENT', 'observed_value') == 'ABSENT'
    assert public_value('CANONICAL_ABSENT', 'reason_code') == 'CANONICAL_ABSENT'


def test_internal_configuration_control_metadata_is_annex_only():
    """#728: internal control metadata is not decision-facing analytic content."""
    from rasai.parallel_report.annex_payloads import collect_payloads
    from rasai.parallel_report.render import record_html
    from rasai.parallel_report.read_model import thaw

    settings = {
        'config_id': 'CFG-PRIVATE',
        'schema_version': 'INTERNAL_SCHEMA_V6',
        'configuration_kind': 'INTERNAL_EXECUTION_POLICY',
        'configuration_hash': 'HASH_INTERNAL_ONLY_123',
        'changed_fields_json': '["SECRET_INTERNAL_POLICY_FLAG"]',
        'created_at': '2026-11-19T10:00:00+00:00',
    }
    source = {'audit_execution_configurations': [dict(settings)],
              'ai_provider_native_usage': [{
                  'attempt_id': 'AI-PUBLIC', 'provider': 'Provider A',
                  'estimated_cost': 0.02, 'cost_currency': 'USD',
              }]}
    schema = {
        name: {'columns': list(rows[0]), 'primary_key': ['config_id']
               if name == 'audit_execution_configurations' else ['attempt_id'],
               'foreign_keys': []}
        for name, rows in source.items()
    }
    original = {name: [dict(row) for row in rows] for name, rows in source.items()}
    records = build(source, schema)
    html, receipt = build_analytical_views(source, records, schema, 'UTC')
    technical = receipt['ia-custos.html']['audit_execution_configurations']

    assert technical['records_available'] == 1
    assert technical['analytical_records'] == 0
    assert technical['direct_fields'] == []
    assert set(settings).issubset(technical['fields_not_in_this_projection'])
    assert technical['executive_interpretation_certified'] is False
    assert 'data-analytical-family="audit_execution_configurations"' not in html['ia-custos']
    for raw in ('INTERNAL_SCHEMA_V6', 'INTERNAL_EXECUTION_POLICY',
                'HASH_INTERNAL_ONLY_123', 'SECRET_INTERNAL_POLICY_FLAG'):
        assert raw not in html['ia-custos']
    assert 'AI-PUBLIC' in html['ia-custos']
    config_record = next(record for record in records
                         if record.table == 'audit_execution_configurations')
    with collect_payloads() as annexes:
        detail = record_html(config_record, {config_record.href: ()})
    assert 'Origem dos dados e horários' in detail
    assert 'anexos/' in detail
    payload = next(iter(annexes.values())).decode('utf-8')
    assert settings['configuration_hash'] in payload
    assert json.loads(payload)['changed_fields_json'] == json.loads(settings['changed_fields_json'])
    assert thaw(config_record.data) == {**settings, 'changed_fields_json': json.loads(settings['changed_fields_json'])}
    assert source == original

