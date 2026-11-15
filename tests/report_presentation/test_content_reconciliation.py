from types import SimpleNamespace

import pytest

from rasai.catalog_report_integrations import _cost_basis_cards, _token_pair_display, _token_value_display
from rasai.catalog_report_search_trust import overview_citation
from rasai.parallel_report.action_plan import render_plan
from rasai.parallel_report.governance import Governance
from rasai.parallel_report.read_model import build
from rasai.parallel_report.render import record_html
from rasai.parallel_report.scope_context import scope_context


@pytest.mark.parametrize('values,expected', [
    ([{'page_token': 'continuation'}], 'N/D'),
    ([{'references': [{'link': 'https://else.test'}, {}]}], 'N/D'),
    ([{'sources': ['https://else.test']}], 'Não'),
    ([{'references': [{'link': 'https://www.target.test/a'}, {}]}], 'Sim'),
])
def test_overview_reference_universe(values, expected):
    assert overview_citation(values, {'target.test'}) == expected


def test_cost_basis_and_unknown_tokens():
    result = _cost_basis_cards([{'estimated_cost': 1.5, 'cost_currency': 'USD'},
                                {'observed_cost': 0, 'observed_cost_currency': 'USD'},
                                {'input_tokens': None}])
    observed, estimated = result.split('Custo estimado')
    assert 'Custo observado' in observed and '1.50000000' not in observed
    assert '1.50000000' in estimated
    assert _token_pair_display(None, 0, cost=None) == 'N/D / 0'
    assert _token_value_display(None, cost=0) == 'N/D'


def test_partial_tokens_keep_known_input_without_claiming_complete_total():
    from rasai.ai_economic_telemetry import known_token_subtotal
    from rasai.catalog_report_integrations import _token_summary_cards

    attempts = [{'input_tokens': 7}, {'total_tokens': 0}, {'input_tokens': 2, 'output_tokens': 5}]
    assert known_token_subtotal(attempts, 'input_tokens') == (9, 2)
    assert known_token_subtotal(attempts, 'total_tokens') == (7, 2)
    assert known_token_subtotal(attempts, 'reasoning_tokens') == (None, 0)
    assert '2 de 3 tentativa(s) com valor conhecido' in _token_summary_cards(attempts, False)


def test_governance_conflict_excludes_client_card_preserves_distinct_count():
    decisions = [dict(source_kind='DEEP_ANALYSIS', source_id='x', decision='ACCEPTED'),
                 dict(source_kind='DEEP_ANALYSIS', source_id='x', decision='REJECTED'),
                 dict(source_kind='DEEP_ANALYSIS', source_id='y', decision='ACCEPTED', target_class='AUDITOR_INTERNAL')]
    data = {'directed_analysis_actions': [dict(action_id=i, title='Item '+i, source_kind='DEEP_ANALYSIS', source_id=i)
                                          for i in ('x','y','z')], 'recommendation_governance': decisions}
    html = render_plan(lambda names: [r for n in names for r in data.get(n, [])], 'UTC', Governance(decisions))
    assert 'Item x' not in html and 'Item y' not in html
    assert 'Item z' in html and 'id="action-card-0"' in html and 'action-card-1' not in html


def test_origin_and_observation_in_human_record():
    data = {'serp_observations': [{'query':'test','observation_status':'OBSERVED'}],
            'jsonld_remediation_suggestions':[{'suggestion_id':'s','proposed_json':{'@type':'WebPage'}}]}
    for r in build(data, {k:{'columns':list(v[0]),'primary_key':[]} for k,v in data.items()}):
        human = record_html(r, {r.href: []}).split('<details>')[0]
        assert ('Proposta determinística do RASAi' if r.table.startswith('jsonld') else 'Observado') in human
        assert 'IA sugeriu' not in human


def test_network_and_serp_do_not_borrow_apdex_or_search_universes(tmp_path, monkeypatch):
    from rasai.parallel_report import scope_context as context
    monkeypatch.setattr(context, 'read_network_observations', lambda *_: [])
    monkeypatch.setattr(context, 'read_authorized_probes', lambda *_: [{
        'hostname': 'example.org',
        'port': 443,
        'capture_utc': '2026-11-15T12:00:00Z',
        'measurement_origin': 'LOCAL_OPERATOR_PROCESS',
        'metrics': {
            'dns_resolution': {'state': 'COLLECTION_FAILED', 'error': 'DNS_NAME_RESOLUTION_FAILED'},
            'dns_elapsed_ms': {'state': 'OBSERVED', 'value': 0, 'source': 'LOCAL_DNS_RESOLVER'},
            'tcp_handshake_ms': {'state': 'NOT_OBSERVED', 'value': None, 'source': 'NO_TCP_TIMING_CAPTURE'},
            'tls_handshake_ms': {'state': 'OBSERVED', 'value': 13.4, 'source': 'LOCAL_TLS_SOCKET'},
            'traceroute': {'state': 'OBSERVED', 'value': {
                'target_reached': False,
                'method': 'WINDOWS_TRACERT',
                'probe_protocol': 'ICMP',
                'max_hops': 16,
                'hops': [{
                    'hop': 1, 'state': 'PUBLIC_HOP', 'public_ip': '8.8.8.8', 'rtt_ms': 12.3,
                    'enrichment': {
                        'asn': {'state': 'OBSERVED', 'value': {'number': 15169, 'organization': 'Google'}},
                        'geoip': {'state': 'OBSERVED', 'value': {
                            'latitude': -30.0, 'longitude': -51.0,
                            'accuracy_radius_km': 20, 'source': 'MAXMIND_MMDB'}},
                    },
                }],
            }},
        },
    }])
    tables = {'audits': [{'audit_id':'a'}], 'passive_security_runs':[{}],
              'passive_security_script_observations':[{},{}],
              'geo_observation_runs':[{'projection_json':{'source_count':8, 'descriptive_overlap':{'common_urls':0,'perplexity_denominator':8,'serp_denominator':3}}}]}
    body = scope_context(tmp_path,tables,'UTC',{})
    assert 'Scripts observados na captura passiva</dt><dd>2' in body['seguranca']
    assert 'Scripts observados na captura passiva' not in body['performance']
    assert 'Consulta DNS (ms)' in body['rede'] and '>0<' in body['rede']
    assert 'Falha na coleta' in body['rede'] and 'Conexão TCP (ms)' in body['rede']
    assert 'caminho completo não confirmado' in body['rede']
    assert 'AS15169' in body['rede'] and 'precisão ±20 km' in body['rede']
    assert '8.8.8.8' in body['rede'] and '12,3' in body['rede']
    assert 'Consulta DNS (ms)' not in body['performance']
    assert 'URLs da SERP</dt><dd>3' in body[context.SEARCH_PAGE]
    assert 'URLs da Search API</dt><dd>8' in body[context.SEARCH_PAGE]

def test_orphaned_governance_reference_keeps_one_destination(monkeypatch):
    from rasai import recommendation_governance_reporting as module
    from rasai.accepted_audit_refinements import _stable_report_anchor
    row = {'source_kind':'DETERMINISTIC','source_id':'r1','title':'Referência'}
    monkeypatch.setattr(module, 'list_governance', lambda *_, decision: [row] if decision == module.ACCEPTED else [])
    anchor = _stable_report_anchor('rem-det', 'r1', '')
    def project(technical):
        return module.governed_plan_html(None, SimpleNamespace(audit_id='a'), technical_html=technical)
    assert f'id="{anchor}"' in project('')
    assert f'id="{anchor}"' not in project(f'<div id="{anchor}"></div>')


def test_contextual_index_links_to_review_entry():
    from rasai.contextual_advisory_html import _v2_panel
    counts = dict(raw=0,observed_v1=0,qualified=0,noise=0,unqualified=0,nd=0)
    from collections import defaultdict
    overlay = dict(counts=defaultdict(int,counts), recommendation_counts=defaultdict(int))
    html = _v2_panel(dict(semantic_v2=overlay,captures=[]), 'index.html', private=False)
    assert "geo-content-review.html#contextual-content" in html
    assert "geo-content-review.html#contextual-semantic-v2" not in html
