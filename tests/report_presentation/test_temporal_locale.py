"""Report-presentation-only timestamp localization and civil-date contract.

All conversions apply only to typed, visible fields; source and annex bytes stay UTC.
"""
import json

from rasai.parallel_report import __version__, executive_evidence
from rasai.parallel_report.analytical_views import build_analytical_views
from rasai.parallel_report.components import table
from rasai.parallel_report.execution_context import build_execution_context
from rasai.parallel_report.page_views import editorial
from rasai.parallel_report.presentation_labels import public_value, timezone_for_records
from rasai.parallel_report.read_model import build, SEARCH_PAGE
from rasai.parallel_report.thresholds import load

ZONE = 'America/Sao_Paulo'


def _records(tables):
    schema = {name: {
        'columns': list(rows[0]) if rows else [],
        'primary_key': [], 'foreign_keys': [],
    } for name, rows in tables.items()}
    return build(tables, schema), schema


def test_only_typed_instants_and_civil_dates_are_localized():
    assert __version__ == '0.4.24'
    raw = '2026-11-17T15:41:12+00:00'
    local = '17/11/2026 12:41:12 (America/Sao_Paulo)'
    for field in ('collection_window_start', 'collection_window_end', 'started_at'):
        assert public_value(raw, field, ZONE) == local
    for field, date, expected in (
        ('first_start', '2026-01-18', '18/01/2026'),
        ('first_end', '2026-02-14', '14/02/2026'),
        ('last_start', '2026-10-18', '18/10/2026'),
        ('last_end', '2026-11-14', '14/11/2026'),
        ('period_start', '2026-01-18', '18/01/2026'),
        ('period_end', '2026-02-14', '14/02/2026'),
        ('source_date', '2022-07-04', '04/07/2022'),
        ('last_updated', '2026-11-05', '05/11/2026'),
    ):
        assert public_value(date, field, ZONE) == expected
    assert public_value('2026-02-30', 'source_date', ZONE) == '2026-02-30'
    assert public_value('2026-11-17', 'created_at', ZONE) == '2026-11-17'
    assert public_value(raw, 'title', ZONE) == raw
    assert public_value('Foi coletado em ' + raw, 'notes', ZONE).endswith(raw)


def test_collection_window_source_dates_and_unchanged_persisted_metadata():
    raw = '2026-11-17T15:41:12+00:00'
    row = {'query': 'consulta', 'collected_at': raw,
           'quality_metadata': json.dumps({
               'collection_window_start': raw,
               'collection_window_end': raw,
           })}
    tables = {'serp_observations': [row],
              'perplexity_search_sources': [{
                  'position': 1, 'source_date': '2022-07-04',
                  'last_updated': '2026-11-05',
              }]}
    records, schema = _records(tables)
    rendered, receipt = build_analytical_views(tables, records, schema, ZONE)
    search = rendered[SEARCH_PAGE]
    local = '17/11/2026 12:41:12 (America/Sao_Paulo)'
    assert search.count(local) >= 3
    assert '04/07/2022' in search and '05/11/2026' in search
    assert raw not in search
    assert tables['serp_observations'][0]['collected_at'] == raw
    assert receipt[SEARCH_PAGE + '.html']['serp_observations']['records_available'] == 1


def test_reprocess_history_uses_audit_zone_not_windows_timezone(monkeypatch):
    monkeypatch.setenv('RASAI_PRESENTATION_TIMEZONE', 'Asia/Tokyo')
    rows = {
        'audit_fulfillment_contracts': [{
            'processing_status': 'COMPLETE', 'score_status': 'FINAL',
            'report_status': 'FINAL', 'required_items': 4,
            'successful_items': 4, 'consolidation_eligible': True,
        }],
        'audit_reprocess_runs': [{
            'reprocess_id': 'RPR-1', 'status': 'COMPLETED',
            'started_at': '2026-11-17T16:38:20.145313+00:00',
            'completed_at': '2026-11-17T17:24:03.701642+00:00',
            'attempted_items': 4, 'successful_items': 4, 'remaining_items': 0,
        }],
    }
    rendered, _ = build_execution_context(rows, {'pages': {}}, ZONE)
    html = rendered['index:execution']
    assert '17/11/2026 13:38:20 (America/Sao_Paulo)' in html
    assert '17/11/2026 14:24:03 (America/Sao_Paulo)' in html
    assert '2026-11-17T16:38:20.145313+00:00' not in html
    assert rows['audit_reprocess_runs'][0]['started_at'].endswith('+00:00')


def test_financial_narrative_uses_frozen_timezone_with_provenance_unchanged(monkeypatch):
    raw = '2026-11-17T16:09:25.783348+00:00'
    rows = {
        'console_cost_forecast_outcomes': [{
            'evaluated_at': raw, 'currency': 'USD', 'actual_cost': 0.005,
            'notes': 'Nota original persistida.', 'source': 'local-audit-history',
        }],
        'audit_fulfillment_contracts': [{
            'completed_at': '2026-11-17T17:32:04.264825+00:00',
        }],
    }
    records, schema = _records(rows)
    html, _ = build_analytical_views(rows, records, schema, ZONE)
    financial = html['ia-custos']
    assert 'Registrado em 17/11/2026 13:09:25 (America/Sao_Paulo)' in financial
    assert 'concluído em 17/11/2026 14:32:04 (America/Sao_Paulo)' in financial
    assert raw not in financial
    assert 'Nota original persistida.' in financial
    assert rows['console_cost_forecast_outcomes'][0]['notes'] == 'Nota original persistida.'

    monkeypatch.setenv('RASAI_PRESENTATION_TIMEZONE', 'Asia/Tokyo')
    tables = {**rows,
              'audits': [{'audit_id': 'AUD-TEMP', 'primary_language': 'pt-BR'}],
              'audit_execution_configurations': [{
                  'audit_id': 'AUD-TEMP',
                  'configuration_json': json.dumps({
                      'settings': {'presentation': {'timezone': ZONE}},
                  }),
              }]}
    model, _ = _records(tables)
    zone, _ = timezone_for_records(model)
    assert zone == ZONE
    view = editorial('index', model, {
        'coverage': 'N/D', 'attempt_count': 0, 'totals': {}, 'entries': [],
    }, load())
    assert 'Instantâneo do console em 17/11/2026 13:09:25 (America/Sao_Paulo)' in view
    assert raw not in view


def test_crux_civil_window_dates_keep_day_and_original_bytes(tmp_path, monkeypatch):
    dates = ('2026-01-18', '2026-02-14', '2026-10-18', '2026-11-14')
    series = [{'period_start': dates[0], 'period_end': dates[1], 'p75': 1200}]
    groups = [{
        'target': 'https://example.test', 'scope': 'URL',
        'form_factor': 'PHONE', 'metric': 'largest_contentful_paint',
        'unit': 'ms', 'periods': 2,
        'first_start': dates[0], 'first_end': dates[1], 'first_p75': 1200,
        'last_start': dates[2], 'last_end': dates[3], 'last_p75': 1000,
        'series': series,
    }]
    monkeypatch.setattr(executive_evidence, 'crux_history', lambda *_: {
        'state': 'AVAILABLE', 'groups': groups,
        'sources': [], 'limitations': [],
    })
    rendered, _ = executive_evidence.summaries(
        tmp_path, {}, {}, (), {'state': 'SOURCE_ABSENT', 'sources': []},
        timezone_name=ZONE)
    page = rendered['performance']
    for raw, local in zip(dates, ('18/01/2026', '14/02/2026',
                                  '18/10/2026', '14/11/2026')):
        assert local in page
        assert raw not in page
    assert groups[0]['first_start'] == dates[0]
    assert series[0]['period_end'] == dates[1]


def test_technical_detail_only_converts_typed_dates_not_literal_headlines():
    source = {
        'source_date': '2026-10-11',
        'collection_window_start': '2026-11-17T15:41:12+00:00',
        'headline': '2026-11-17T15:41:12+00:00',
    }
    html = table('Data por tipo', [source], [
        ('source_date', 'Data civil'),
        ('collection_window_start', 'Coleta'),
        ('headline', 'Título literal'),
    ], timezone_name=ZONE)
    assert '11/10/2026' in html
    assert '17/11/2026 12:41:12 (America/Sao_Paulo)' in html
    assert '2026-11-17T15:41:12+00:00' in html
    assert source['source_date'] == '2026-10-11'
