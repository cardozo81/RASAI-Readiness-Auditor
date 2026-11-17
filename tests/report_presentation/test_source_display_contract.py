"""Surgical source-only presentation assertions for the presentation source contract.

Fixtures simulate persisted rows; they do not assert that a physical AUD was
inspected or that historical data can be regenerated without its audit.db.
"""
import json

from rasai.parallel_report.read_model import build
from rasai.parallel_report.page_views import editorial
from rasai.parallel_report.thresholds import load
from rasai.parallel_report.cost_reconciliation import reconcile
from rasai.parallel_report.execution_context import build_execution_context
from rasai.parallel_report.analytical_views import build_analytical_views
from rasai.parallel_report.action_plan import render_plan
from rasai.parallel_report.governance import Governance
from rasai.parallel_report.render import record_html


def model(tables):
    schema = {
        name: {'columns': sorted({k for row in rows for k in row}),
               'primary_key': [], 'foreign_keys': []}
        for name, rows in tables.items()
    }
    return build(tables, schema), schema


def test_costs_keep_estimate_and_dated_snapshot_distinct():
    priced = [
        {'attempt_id': f'AI-{i}', 'provider': 'example', 'model': 'mock',
         'status': 'SUCCESS', 'estimated_cost': 0.02, 'observed_cost': None,
         'cost_currency': 'USD', 'started_at': '2026-11-17T17:30:00'}
        for i in range(6)
    ]
    remediation = [{
        'attempt_id': 'REMED-1', 'provider': 'example', 'model': 'mock',
        'estimated_cost': 0.084055, 'observed_cost': None,
        'cost_currency': 'USD', 'started_at': '2026-11-17T17:31:00'
    }]
    tables = {
        'ai_provider_attempts': priced,
        'content_remediation_attempts': remediation,
        'console_cost_forecast_outcomes': [{
            'evaluated_at': '2026-11-17T16:09:25',
            'actual_cost': 0.005, 'currency': 'USD'
        }],
    }
    records, _ = model(tables)
    result = reconcile(tables)
    html = editorial('ia-custos', records, result, load())
    assert 'USD 0.204055 em 7 tentativas com preço' in html
    assert 'N/D — nenhum custo observado pelo provedor' in html
    assert '2026-11-17T16:09:25' in html
    assert 'anterior a 7 tentativa(s)' in html
    assert 'Custo técnico conciliado' not in html
    assert html.count('Preço por tentativa') >= 1


def test_forecast_note_is_superseded_only_when_contract_is_newer():
    tables = {
        'console_cost_forecast_outcomes': [{
            'evaluated_at': '2026-11-17T16:09:25',
            'notes': '5 requisitos obrigatórios incompletos', 'status': 'NOT_COMPARABLE',
            'currency': 'USD',
        }],
        'audit_fulfillment_contracts': [{
            'completed_at': '2026-11-17T17:32:04',
        }],
    }
    records, schema = model(tables)
    pages, _ = build_analytical_views(tables, records, schema, 'UTC')
    html = pages['ia-custos']
    assert 'Registrado em 2026-11-17T16:09:25' in html
    assert 'superado pelo contrato de fulfillment concluído em 2026-11-17T17:32:04' in html
    assert '5 requisitos obrigatórios incompletos' in html


def test_reprocessing_history_two_rows_and_archived_receipt():
    tables = {
        'audit_fulfillment_contracts': [{
            'processing_status': 'COMPLETE', 'score_status': 'FINAL',
            'report_status': 'FINAL', 'required_items': 15,
            'successful_items': 15, 'pending_items': 0, 'blocked_items': 0,
            'consolidation_eligible': 1,
        }],
        'audit_reprocess_runs': [
            {'reprocess_id': 'RPR-A', 'status': 'FAILED_RETRYABLE',
             'attempted_items': 0, 'successful_items': 0, 'remaining_items': 4,
             'configuration': '{"selected_items":["A"]}'},
            {'reprocess_id': 'RPR-B', 'status': 'SUCCESS',
             'attempted_items': 4, 'successful_items': 4, 'remaining_items': 0,
             'configuration': '{"selected_items":["B"]}'},
        ],
        'audit_reprocess_derived_archive': [{'archive_id': f'AR-{i}'} for i in range(271)],
    }
    pages, _ = build_execution_context(tables, {'pages': {}})
    panel = pages['index:execution']
    assert 'Histórico de execução — 2 reprocessamentos' in panel
    assert 'RPR-A' in panel and 'RPR-B' in panel
    assert 'Registros derivados arquivados: 271' in panel
    assert 'selected_items' in panel
    assert 'anexos/' in panel


def test_ai_failures_have_visible_fallback_and_status_aggregation():
    tables = {'ai_provider_attempts': [
        {'attempt_id': 'AI-FAIL', 'provider': 'mock', 'model': 'stub',
         'status': 'TECHNICAL_ERROR', 'error_code': 'TIMEOUT',
         'fallback_reason': 'indisponível temporariamente',
         'request_message_summary': 'diagnóstico técnico'}
    ]}
    records, _ = model(tables)
    html = editorial('ia-custos', records, reconcile(tables), load())
    assert 'Contagens por status persistido' in html
    assert 'Contagens por categoria de erro' in html
    assert 'TECHNICAL_ERROR' in html and 'TIMEOUT' in html
    assert 'indisponível temporariamente' in html
    assert 'diagnóstico técnico' in html


def test_root_groups_and_occurrences_do_not_authorize_client_execution():
    groups = [
        {'group_id': f'RG-{i}', 'rule_id': f'RULE-{i}',
         'root_cause': f'Causa {i}', 'priority_class': 'P1' if i == 0 else 'P2',
         'priority_score': 80 - i, 'severity': 'HIGH', 'impact': 'MEDIUM',
         'effort': 'LOW', 'affected_findings': json.dumps([f'F-{i}'])}
        for i in range(8)
    ]
    actions = [
        {'action_id': f'ACT-{i}', 'title': f'Ação {i % 40}',
         'source_id': 'test', 'source_kind': 'DETERMINISTIC',
         'priority': 'LOW'}
        for i in range(59)
    ]
    tables = {'remediation_groups': groups, 'directed_analysis_actions': actions}
    records, _ = model(tables)
    indexed = {row.table: [] for row in records}
    from rasai.parallel_report.read_model import thaw
    for row in records:
        indexed[row.table].append({**thaw(row.data), '_ref': row.href})
    html = render_plan(lambda names: [item for name in names for item in indexed.get(name, [])],
                       'UTC', Governance([]))
    assert 'Grupos por causa-raiz' in html
    assert 'Causa 0' in html and 'Causa 7' in html
    assert '59 ocorrências / 40 títulos' in html
    assert 'F-0' in html and 'F-7' in html
    assert 'Prioridade do motor' in html
    assert 'Prioridade do plano direcionado' in html
    assert 'Plano aprovado pela governança' in html


def test_crosslinked_records_use_unique_accessible_link_names():
    tables = {'findings': [
        {'finding_id': 'F-1', 'title': 'Título idêntico'},
        {'finding_id': 'F-2', 'title': 'Título idêntico'}]}
    schema = {'findings': {'columns': ['finding_id', 'title'],
                           'primary_key': ['finding_id'], 'foreign_keys': []}}
    records = build(tables, schema)
    source = records[0]
    targets = {r.href: r for r in records}
    html = record_html(source, {source.href: (records[1].href,)}, lookup=targets)
    assert 'relacionado 1' not in html
    assert 'aria-label="Detalhe: findings' in html
    assert records[1].anchor in html


def test_security_platform_text_hides_non_public_raw_identifiers():
    tables = {'passive_security_platforms': [
        {'platform_ref': 'P-1', 'platform_name': 'Example analytics',
         'confidence': 'HIGH',
         'identifiers_json': json.dumps([
             {'identifier_class': 'PUBLIC_IDENTIFIER', 'identifier_display': 'GTM-PUBLIC'},
             {'identifier_class': 'PRIVATE_IDENTIFIER', 'identifier_display': 'SECRET-INNER',
              'identifier_hash': 'hashed-only'},
         ]),
         'evidence_ids_json': '["E-1"]'},
    ]}
    records, _ = model(tables)
    html = editorial('seguranca', records, reconcile(tables), load())
    assert 'GTM-PUBLIC' in html and 'hashed-only' in html
    assert 'SECRET-INNER' not in html
    details = record_html(records[0], {records[0].href: ()})
    assert 'GTM-PUBLIC' in details and 'hashed-only' in details
    assert 'SECRET-INNER' not in details
