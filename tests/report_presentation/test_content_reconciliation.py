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
    monkeypatch.setattr(context, 'read_authorized_probes', lambda *_: [
        {'metrics': {'dns_elapsed_ms': {'value': 0}, 'tls_handshake_ms': {'value': 13.4}}}])
    tables = {'audits': [{'audit_id':'a'}], 'passive_security_runs':[{}],
              'passive_security_script_observations':[{},{}],
              'geo_observation_runs':[{'projection_json':{'source_count':8, 'descriptive_overlap':{'common_urls':0,'perplexity_denominator':8,'serp_denominator':3}}}]}
    body = scope_context(tmp_path,tables,'UTC',{})
    assert 'Scripts observados na captura passiva</dt><dd>2' in body['performance']
    assert 'DNS (ms)</dt><dd>0' in body['performance'] and 'TCP (ms)</dt><dd>N/D' in body['performance']
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
