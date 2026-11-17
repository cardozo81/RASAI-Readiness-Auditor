"""Focused regressions for read-only Search/GEO and context-aware sanitization."""
import json
import sqlite3

from rasai.observability.store import observability_database_path
from rasai.parallel_report.sanitization import sanitize
from rasai.parallel_report.search_geo_synthesis import render_search_geo_synthesis


def test_css_class_identifiers_survive_without_leaking_secret_shapes():
    raw = {
        'selector': 'div.sk-uigroup-header.sk-accessibility-button',
        'html': '<div class="sk-accessibility-button sk-uigroup-header"></div>',
        'finding': 'O DOM contém div.sk-uigroup-header após o carregamento.',
        'literal': 'sk-' + 'Z' * 35,
        'authorization': 'Bearer ' + 'z' * 24,
        'nested': json.dumps({'token': 'sk-proj-' + 'Q' * 28}),
        'html_with_key': '<div data-api-key="sk-proj-' + 'X' * 28 + '"></div>',
        'secret_as_class': '<div class="sk-proj-' + 'Y' * 28 + '"></div>',
        'cookie_value': 'privado',
        'password': 'privado',
    }
    result = sanitize(raw)
    assert result['selector'] == raw['selector']
    assert result['html'] == raw['html']
    assert 'div.sk-uigroup-header' in result['finding']
    assert result['literal'] == '[REDACTED]'
    assert result['authorization'] == result['cookie_value'] == result['password'] == '[REDACTED]'
    assert result['nested']['token'] == '[REDACTED]'
    for item in ('html_with_key', 'secret_as_class'):
        assert 'sk-proj-' not in result[item]
    assert sanitize({'selector': '.sk-navigation-98765432109876'})['selector'] == '.sk-navigation-98765432109876'
    assert 'sk-proj-' not in sanitize({'selector': '.sk-proj-' + 'R' * 30})['selector']


def _external_source_fixture(root):
    db = observability_database_path(root)
    db.parent.mkdir(parents=True)
    with sqlite3.connect(db) as connection:
        connection.execute(
            'CREATE TABLE datasets (dataset_id TEXT, source_type TEXT, metadata TEXT, artifact_path TEXT)')
        connection.execute(
            'CREATE TABLE web_archive_observations (record_id TEXT, dataset_id TEXT)')
        connection.execute(
            'INSERT INTO datasets VALUES (?, ?, ?, ?)',
            ('cc-1', 'COMMON_CRAWL_CDX_HISTORY', '{"errors": 2}', 'artifacts/cc.json'))
    return db


def test_search_geo_integrations_use_persisted_failure_and_disabled_configuration(tmp_path):
    source = _external_source_fixture(tmp_path)
    before = source.read_bytes()
    tables = {
        'audit_execution_configurations': [{
            'configuration_json': json.dumps({
                'RASAI_COMMON_CRAWL_ENABLED': True,
                'RASAI_GSC_ENABLED': False,
                'RASAI_CLARITY_ENABLED': False,
            }),
        }],
    }
    html = render_search_geo_synthesis(tmp_path, tables)
    assert 'Common Crawl' in html
    assert 'Executada com erro registrado' in html
    assert 'Google Search Console' in html and 'Microsoft Clarity' in html
    assert html.count('Desabilitada') >= 2
    assert 'serp_results' in html
    assert 'report-catalog/' not in html
    assert before == source.read_bytes()  # sqlite read-only: no WAL writes


def test_competitive_summary_keeps_provenance_and_mismatched_universes_separate(tmp_path):
    data = {
        'serp_results': [{'position': i} for i in range(5)],
        'serp_competitive_results': [
            {'selected_for_content_comparison': True, 'position': i} for i in range(3)
        ],
        'serp_competitive_analyses': [{
            'observation_id': 'SERP-1', 'candidate_count': 3,
            'observed_competitor_pages': 2, 'gap_count': 3,
            'comparison_status': 'PARTIAL',
            'evidence_ref': 'artifacts/competitive.json',
            'evidence_sha256': 'a' * 64,
        }],
        'geo_observation_runs': [{
            'perplexity_run_id': 'P-1',
            'projection_json': json.dumps({
                'source_count': 10,
                'descriptive_overlap': {'serp_denominator': 5, 'common_urls': 3},
            }),
        }],
        'serp_competitive_ai_analyses': [{
            'observation_id': 'SERP-1',
            'state': 'SUCCESS', 'provider': 'synthetic',
            'model': 'synthetic', 'summary': 'Proposta consultiva não aprovada.',
            'opportunity_count': 1,
            'opportunities_json': json.dumps([{
                'title': 'Avaliar cobertura da consulta',
                'priority': 'MEDIUM',
                'recommendation': 'Conferir a intenção antes da revisão.',
                'evidence_ids': ['CE-CUSTOMER', 'CE-COMP-001'],
            }]),
            'evidence_ref': 'artifacts/competitive-ai.json',
            'evidence_sha256': 'b' * 64,
        }],
    }
    html = render_search_geo_synthesis(tmp_path, data)
    assert 'Resultados SERP normalizados' in html
    assert 'P-1' in html
    assert 'artifacts/competitive.json' in html
    assert 'Proposta consultiva não aprovada.' in html
    assert 'não constitui ação aprovada' in html
    assert 'citação generativa' in html
    assert 'Avaliar cobertura da consulta' in html
    assert 'CE-CUSTOMER, CE-COMP-001' in html
    assert 'report-catalog/' not in html


def test_absent_observability_does_not_infer_execution_failure_or_zero(tmp_path):
    html = render_search_geo_synthesis(tmp_path, {})
    assert 'inventário externo indisponível' in html
    assert 'Falha registrada' not in html
    assert 'N/D' in html
    assert 'Não há dependência do relatório de catálogo' in html



def test_financial_critical_label_is_typed_only_in_financial_projection():
    from rasai.parallel_report.analytical_views import build_analytical_views
    from rasai.parallel_report.read_model import build
    tables = {'console_cost_forecast_outcomes': [{
        'currency': 'USD', 'status': 'CRÍTICO',
        'expected_cost': 0.0411926, 'actual_cost': 0.68212442,
    }]}
    schema = {'console_cost_forecast_outcomes': {
        'columns': list(tables['console_cost_forecast_outcomes'][0]),
        'primary_key': [],
    }}
    records = build(tables, schema)
    html, receipt = build_analytical_views(tables, records, schema, 'UTC')
    assert 'Crítico' in html['ia-custos']
    assert receipt['ia-custos.html']['console_cost_forecast_outcomes']['records_available'] == 1
    assert records[0].data['status'] == 'CRÍTICO'  # immutable original record
