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
    assert 'Mapa geográfico consultivo' in body['rede']
    assert 'data-map-layer' in body['rede']
    assert 'network-context-modal' in body['rede']
    assert 'report-catalog/network.html' not in body['rede']
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


def test_sensitive_cookie_fields_keep_safe_cross_references_and_redact_values():
    from rasai.parallel_report.sanitization import sanitize
    raw = {
        'cookie_attribution_id': 'ATTR-0042',
        'cookie_ref': 'ATTR-0042',
        'cookie_name_display': 'SID',
        'set_cookie_index': 0,
        'cookie_value': 'private-session-value',
        'authorization': 'Bearer private-secret',
        'selector': '.sk-navigation-98765432109876',
        'nested': '{"cookie_ref":"ATTR-0042","cookie_value":"PRIVATE"}',
    }
    out = sanitize(raw)
    assert out['cookie_attribution_id'] == out['cookie_ref'] == 'ATTR-0042'
    assert out['cookie_name_display'] == 'SID'
    assert out['set_cookie_index'] == 0
    assert out['selector'] == raw['selector']
    assert out['cookie_value'] == out['authorization'] == '[REDACTED]'
    assert out['nested']['cookie_ref'] == 'ATTR-0042'
    assert out['nested']['cookie_value'] == '[REDACTED]'
    dubious = sanitize({'cookie_ref': 'ghp_' + 'a' * 25, 'other': 'sk-' + 'b' * 24})
    assert dubious['cookie_ref'].startswith('[REF-')
    assert 'ghp_' not in str(dubious) and 'sk-' not in str(dubious)
    assert sanitize({'set_cookie_index': '0'})['set_cookie_index'] == '[REDACTED]'


def test_network_inventory_is_local_nonempty_and_sanitized(tmp_path, monkeypatch):
    from collections import defaultdict
    from rasai.parallel_report import scope_context as network
    from rasai.parallel_report import catalog_context as catalog
    from rasai.parallel_report.render import render
    from rasai.parallel_report.cost_reconciliation import reconcile
    from rasai.parallel_report.thresholds import load

    monkeypatch.setattr(network, 'read_network_observations', lambda *_: [{
        'audit_id': 'AUD-TEST', 'observation_id': 'NET-AUD-001',
        'protocol': 'h2', 'secret': 'private-token-value',
    }])
    monkeypatch.setattr(network, 'read_authorized_probes', lambda *_: [])
    monkeypatch.setattr(network, 'build_network_assessment', lambda *_: {
        'analysis_method': 'DETERMINISTIC_PERSISTED_EVIDENCE',
        'coverage': {'audit_captures': 1, 'authorized_probes': 0},
        'findings': [],
    })
    html, _, inventory = network.network_context(tmp_path, 'AUD-TEST', 'UTC')
    assert 'Captura passiva verificada 1 de 1' in inventory
    assert 'NET-AUD-001' in inventory
    assert 'private-token-value' not in inventory
    pages = render((), defaultdict(list), {}, [], [], reconcile({}), {},
                   load(), [], {'rede': html, 'rede:inventory': inventory})
    rendered = pages['rede.html']
    assert 'id="network-evidence-inventory"' in rendered
    assert 'Captura passiva verificada 1 de 1' in rendered
    assert 'private-token-value' not in rendered
    assert 'network-context-modal' in rendered
    assert 'href="#network-evidence-inventory"' in rendered
    assert 'href="#network-map"' in rendered

    monkeypatch.setattr(catalog, '_verified_links', lambda *_: set())
    independent = catalog.catalog_context(tmp_path, 'logical', 'AUD-TEST', {})
    assert 'data-modal="network-context-modal"' in independent['rede']
    assert '../report-catalog/network.html' not in independent['rede']
    monkeypatch.setattr(catalog, '_verified_links', lambda *_: {'network.html'})
    optional = catalog.catalog_context(tmp_path, 'logical', 'AUD-TEST', {})
    assert 'data-modal="network-context-modal"' in optional['rede']
    assert '../report-catalog/network.html' not in optional['rede']
    assert 'report-catalog' not in optional['rede']


def test_network_inventory_explains_missing_measurements(tmp_path, monkeypatch):
    from rasai.parallel_report import scope_context as network
    monkeypatch.setattr(network, 'read_network_observations', lambda *_: [])
    monkeypatch.setattr(network, 'read_authorized_probes', lambda *_: [])
    monkeypatch.setattr(network, 'build_network_assessment', lambda *_: None)
    _, _, inventory = network.network_context(tmp_path, 'AUD-TEST', 'UTC')
    assert 'Nenhuma captura passiva ou sonda de rede verificável' in inventory
    assert 'falha de conectividade' in inventory


def test_catalog_html_does_not_supply_structured_facts(tmp_path, monkeypatch):
    from rasai.parallel_report.catalog_context import catalog_context
    from rasai.parallel_report import catalog_context as module
    monkeypatch.setattr(module, '_verified_links', lambda *_: set())
    source = {'audit_fulfillment_work_items': [{
        'component': 'SEARCH', 'status': 'NOT_REQUESTED', 'required': 0,
    }]}
    first = catalog_context(tmp_path, 'digest', 'AUD-X', source)
    (tmp_path / 'report-catalog').mkdir()
    (tmp_path / 'report-catalog' / 'execution-evidence.html').write_text(
        '<table><tr><td>FORGED_SUCCESS</td></tr></table>', encoding='utf-8')
    second = catalog_context(tmp_path, 'digest', 'AUD-X', source)
    assert first['index'] == second['index']
    assert 'Pesquisa em mecanismos de busca' in second['index'] and 'FORGED_SUCCESS' not in second['index']
    assert 'Não solicitado' in second['index']
    assert '>SEARCH<' not in second['index'] and '>NOT_REQUESTED<' not in second['index']


def test_sari_measured_score_without_breakdown_is_not_reported_as_unmeasured():
    from rasai.parallel_report.page_views import editorial
    from rasai.parallel_report.thresholds import load
    data = {'scores': [{'score_id':'s-1', 'dimension':'OVERALL_READINESS',
                        'value':89.8, 'confidence':'HIGH'}]}
    records = build(data, {'scores': {'columns': list(data['scores'][0]),
                                     'primary_key': ['score_id']}})
    html = editorial('indices', records, {}, load())
    assert 'Decomposição de regras desta dimensão não disponível' in html
    assert 'O índice acima permanece medido' in html
    assert '89,8' in html


def test_action_plan_separates_governed_undecided_and_excluded():
    decisions = [
        dict(source_kind='DETERMINISTIC', source_id='ok', decision='ACCEPTED'),
        dict(source_kind='DETERMINISTIC', source_id='deny', decision='REJECTED'),
    ]
    data = {'directed_analysis_actions': [
        dict(action_id='1', title='Action-OK', source_kind='DETERMINISTIC', source_id='ok'),
        dict(action_id='2', title='Action-PENDING', source_kind='DETERMINISTIC', source_id='pending'),
        dict(action_id='3', title='Action-DENIED', source_kind='DETERMINISTIC', source_id='deny')],
        'recommendation_governance': decisions}
    html = render_plan(lambda names: [r for name in names for r in data.get(name, [])],
                       'UTC', Governance(decisions))
    approved = html.split('Plano aprovado pela governança', 1)[1].split('Recomendações técnicas sem aprovação', 1)[0]
    pending = html.split('Recomendações técnicas sem aprovação', 1)[1].split('Decisões rejeitadas', 1)[0]
    assert 'Action-OK' in approved and 'Action-PENDING' not in approved
    assert 'Action-PENDING' in pending and 'Action-OK' not in pending
    assert 'Action-DENIED' not in html
    assert 'Ações direcionadas excluídas da execução' in html


def test_persisted_strategic_synthesis_keeps_governance_classes():
    from rasai.parallel_report.action_plan import strategic_context
    import json
    data = {
        'directed_analysis_runs': [{
            'status':'COMPLETE', 'provider':'Persisted', 'model':'Previous',
            'strategic_summary_json': json.dumps({
                'strengths':['Retenção comprovada no snapshot'],
                'risks':['Risco condicional, verificar escopo']}),
            'roadmap_json': json.dumps([
                {'phase':'Fase 1', 'objective':'Conferir evidências', 'action_ids':['a','b']}]),
        }],
        'directed_analysis_actions': [
            {'action_id':'a', 'source_kind':'DETERMINISTIC', 'source_id':'ok'},
            {'action_id':'b', 'source_kind':'DETERMINISTIC', 'source_id':'pending'}],
    }
    decisions = [dict(source_kind='DETERMINISTIC', source_id='ok', decision='ACCEPTED')]
    html = strategic_context(lambda names: [r for n in names for r in data.get(n, [])],
                             Governance(decisions))
    assert 'Retenção comprovada no snapshot' in html and 'Risco condicional' in html
    assert 'Fase 1' in html and 'Aceitas pela governança' in html
    assert 'Sem decisão ou pendentes' in html


def test_editorial_verification_tasks_keep_source_and_validation(monkeypatch, tmp_path):
    from rasai.parallel_report.scope_context import editorial_evidence
    from rasai import contextual_advisory
    monkeypatch.setattr(contextual_advisory, 'load_projection', lambda *_a, **_kw: {
        'faq_aria_v3': {'counts': {}},
        'semantic_v2': {'counts': {}},
        'reverse_review': {
            'counts': {'verification_tasks': 1},
            'tasks': [{'task_id': 'T1', 'status': 'VALIDACAO_NECESSARIA',
                       'title': 'Conferir alegação',
                       'rationale': 'Alegação observada, não autenticada',
                       'validation': 'Solicitar prova vigente',
                       'evidence_sufficiency': 'INSUFICIENTE',
                       'evidence_refs': [{'label':'H1', 'text':'Até 25',
                                          'source_ref':'artifacts/page.html',
                                          'source_sha256': 'a' * 64}]}],
        },
    })
    html = editorial_evidence(tmp_path, {'page_snapshots':[{'rendered_artifact_ref':'artifacts/page.html'}]})
    assert 'Conferir alegação' in html and 'Solicitar prova vigente' in html
    assert 'Até 25' in html and 'artifacts/page.html' in html
    assert 'Insuficiente' in html and '>INSUFICIENTE<' not in html


def test_network_diagnosis_uses_persisted_assessor_not_html(monkeypatch, tmp_path):
    from rasai.parallel_report import scope_context as ctx
    monkeypatch.setattr(ctx, 'read_network_observations', lambda *_: [])
    monkeypatch.setattr(ctx, 'read_authorized_probes', lambda *_: [])
    monkeypatch.setattr(ctx, 'build_network_assessment', lambda *_: {
        'analysis_method':'DETERMINISTIC_PERSISTED_EVIDENCE',
        'confidence_scope':'LIMITED',
        'confidence_explanation':'Uma única sessão',
        'coverage': {'audit_captures':1, 'authorized_probes':0,
                     'dns_samples':0, 'tcp_samples':0, 'tls_samples':0},
        'findings': [{'title':'Escopo insuficiente', 'conclusion':'Sem causa atribuída',
                      'confidence':'LOW', 'evidence_refs':[],
                      'limitation':'Sem rota comprovada', 'recommendation':'Obter autorização',
                      'validation':'Repetir medição autorizada'}]})
    html, _, _ = ctx.network_context(tmp_path, 'AUD-X', 'UTC')
    assert 'Escopo insuficiente' in html and 'Uma única sessão' in html
    assert 'Sem rota comprovada' in html and 'Repetir medição autorizada' in html


def test_architecture_overview_is_bound_to_observation_not_inferred(monkeypatch, tmp_path):
    from rasai.parallel_report import architecture_context as ac
    (tmp_path / 'audit.db').write_bytes(b'dummy-read-only-db')
    fake = [{
        'snapshot_id':'SNP-01','device':'MOBILE','captured_at':'2026-11-16T12:50:00+00:00',
        'observed_architecture':'UNKNOWN', 'raw_verified_against_capture_digest':True,
        'hypothesis':{'candidate':'CSR_SPA','confidence':'LOW'},
        'network_facts':{'dom_count':87,'response_count':9,'main_response_security':{
            'remote_public_peer_ip':'8.8.8.8'}},
        'runtime_script_resources_count':5,
    }]
    monkeypatch.setattr(ac, 'read_architecture_audit_facts', lambda *_: fake)
    html=ac.architecture_context(tmp_path,'AUD-TEST','America/Sao_Paulo')
    assert 'Arquitetura identificada na captura' in html
    assert 'Não determinada' in html
    assert 'Hipótese não confirmada: SPA renderizada no cliente' in html
    assert '>87<' in html
    assert 'Recursos declarados' in html
    assert '8.8.8.8' not in html
    assert 'report-catalog/' not in html
    assert 'href="rede.html"' in html


def test_architecture_overview_missing_source_never_invents(monkeypatch,tmp_path):
    from rasai.parallel_report import architecture_context as ac
    assert 'Banco original indisponível' in ac.architecture_context(tmp_path,'AUD-X','UTC')
    (tmp_path/'audit.db').touch()
    monkeypatch.setattr(ac,'read_architecture_audit_facts',lambda *_: [])
    assert 'Nenhuma classificação arquitetural verificável' in ac.architecture_context(tmp_path,'AUD-X','UTC')


def test_architecture_source_is_included_only_on_extraction(monkeypatch,tmp_path):
    from rasai.parallel_report import scope_context as context
    monkeypatch.setattr(context,'architecture_context',lambda *_:'<h2>Arquitetura identificada na captura</h2>')
    monkeypatch.setattr(context,'network_context',lambda *_:('',[],'')) 
    inputs={'audits':[{'audit_id':'AUD-X'}]}
    pages=context.scope_context(tmp_path, inputs, 'UTC',{})
    assert 'Arquitetura identificada na captura' in pages['extracao']
    for page in ('rede','index','performance','seguranca'):
        assert 'Arquitetura identificada na captura' not in pages[page]


def test_network_independent_passive_ip_without_probe_has_explicit_limit(monkeypatch,tmp_path):
    from rasai.parallel_report import scope_context as network
    monkeypatch.setattr(network,'read_network_observations',lambda *_:[{
        'metrics':{'connected_public_ip':{'state':'OBSERVED','value':'8.8.8.8'}},
        'capture_utc':'2026-11-16T12:00:00Z','device':'MOBILE',
    }])
    monkeypatch.setattr(network,'read_authorized_probes',lambda *_:[])
    monkeypatch.setattr(network,'build_network_assessment',lambda *_:None)
    html,_,_=network.network_context(tmp_path,'AUD-X','UTC')
    assert 'IP público observado</dt><dd>1 captura(s) passiva(s); 0 sonda(s) complementar(es)' in html
    assert 'Origem da ausência de sonda</dt><dd>Não comprovada pelos registros desta AUD' in html
    assert '8.8.8.8' in html
    assert 'Rastreamentos registrados</dt><dd>0</dd>' in html
    assert 'network-map' in html
    assert 'report-catalog/' not in html


def test_network_temporal_comparison_uses_only_same_verified_host_port(monkeypatch,tmp_path):
    from rasai.parallel_report import scope_context as network
    probes=[
      dict(hostname='site.example.org',port=443,capture_utc=t,
           state='SUCCESS',
           metrics={'dns_resolution':{'state':'OBSERVED'},
                    'tcp_handshake_ms':{'state':'OBSERVED'},
                    'tls_handshake_ms':{'state':'OBSERVED'},
                    'traceroute':{'state':'NOT_OBSERVED'}})
      for t in ('2026-11-15T12:00:00Z','2026-11-16T12:00:00Z')
    ]
    probes.append(dict(hostname='other.example.org',port=443,capture_utc='2026-11-15T12:00:00Z'))
    monkeypatch.setattr(network,'read_network_observations',lambda *_:[])
    monkeypatch.setattr(network,'read_authorized_probes',lambda *_:probes)
    monkeypatch.setattr(network,'build_network_assessment',lambda *_:None)
    html,_,_=network.network_context(tmp_path,'AUD-X','UTC')
    assert 'Histórico comparável de sondagens' in html
    assert html.count('site.example.org') >= 2
    assert 'Medições autorizadas por instante' in html
    assert 'other.example.org' not in html.split('Histórico comparável de sondagens')[1].split('Mapa')[0]
    assert 'Nenhuma rota' not in html


def test_network_world_basemap_visible_with_passive_peer_without_geoip(monkeypatch,tmp_path):
    from rasai.parallel_report import scope_context as network
    monkeypatch.setattr(network, 'read_network_observations', lambda *_: [{
        'metrics':{'connected_public_ip':{'state':'OBSERVED','value':'8.8.8.8'},
                   'geoip': {'state':'NOT_OBSERVED','value':None}},
        'capture_utc':'2026-11-16T12:00:00Z', 'device':'MOBILE',
    }])
    monkeypatch.setattr(network,'read_authorized_probes',lambda *_:[])
    monkeypatch.setattr(network,'build_network_assessment',lambda *_:None)
    html, _, _=network.network_context(tmp_path,'AUD-X','UTC')
    assert 'Mapa geográfico consultivo' in html
    assert 'data-map-state="unlocated"' in html
    assert 'data-map-layer=\'land\'' in html
    assert '<svg class="network-map-plot"' in html
    assert '<circle' not in html
    assert "data-map-layer='logical-sequence'" not in html
    assert '8.8.8.8' in html  # present in the network data table, not projected onto map
    assert 'não identifica o IP de origem do usuário' in html
    assert 'Mapa base disponível sem pontos' in html
    assert 'report-catalog/' not in html


def test_network_basemap_without_passive_observation_is_context_not_geo_claim(monkeypatch,tmp_path):
    from rasai.parallel_report import scope_context as network
    monkeypatch.setattr(network,'read_network_observations',lambda *_:[])
    monkeypatch.setattr(network,'read_authorized_probes',lambda *_:[])
    monkeypatch.setattr(network,'build_network_assessment',lambda *_:None)
    html, _, _=network.network_context(tmp_path,'AUD-X','UTC')
    assert 'data-map-state="unlocated"' in html
    assert '<svg class="network-map-plot"' in html
    assert '<circle' not in html
    assert 'Nenhum IP público com geolocalização verificável' in html


def test_verified_geoip_keeps_existing_map_with_exactly_one_marker(monkeypatch,tmp_path):
    from rasai.parallel_report import scope_context as network
    geo={'state':'OBSERVED','value':{'latitude':-30.1,'longitude':-51.2,
         'accuracy_radius_km':100,'source':'LOCAL_MMDB_CITY'}}
    monkeypatch.setattr(network,'read_network_observations',lambda *_:[])
    monkeypatch.setattr(network,'read_authorized_probes',lambda *_:[
        {'hostname':'example.org','capture_utc':'2026-11-16T12:00:00Z',
         'metrics':{'geoip':geo}}
    ])
    monkeypatch.setattr(network,'build_network_assessment',lambda *_:None)
    html, _, _=network.network_context(tmp_path,'AUD-X','UTC')
    assert 'data-map-state="unlocated"' not in html
    assert html.count('<circle') == 1
    assert 'data-map-layer=\'land\'' in html
    assert 'Mapa geográfico aproximado disponível' in html
