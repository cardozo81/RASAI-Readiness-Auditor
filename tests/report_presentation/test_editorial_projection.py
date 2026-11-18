"""Issue #722: high-value analytical projections, source rows only."""
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
