"""Scoped offline regressions: governance, money, methods and readable labels."""
from copy import deepcopy
from hashlib import sha256
from html.parser import HTMLParser
import json
from pathlib import Path

from rasai.parallel_report.action_plan import render_plan
from rasai.parallel_report.cost_reconciliation import reconcile
from rasai.parallel_report.execution_context import build_execution_context
from rasai.parallel_report.executive_evidence import summaries
from rasai.parallel_report.generator import generate
from rasai.parallel_report.governance import Governance
from rasai.parallel_report.page_views import editorial
from rasai.parallel_report.presentation_labels import public_value
from rasai.parallel_report.read_model import build
from rasai.parallel_report.scope_context import network_context, _network_metric_rows
from rasai.parallel_report.thresholds import load
from test_parallel_report import fixture


def records(tables):
    return build(tables, {n: {'primary_key': []} for n in tables})


class Surface(HTMLParser):
    """Exclude technical payloads and modals, including their raw enum values."""
    def __init__(self, html):
        super().__init__(); self.hidden = 0; self.values = []; self.feed(html)

    def handle_starttag(self, tag, attrs):
        if tag in {'details', 'dialog'}: self.hidden += 1

    def handle_endtag(self, tag):
        if tag in {'details', 'dialog'}: self.hidden -= 1

    def handle_data(self, value):
        if not self.hidden: self.values.append(value)


def test_two_discovery_findings_are_material_not_an_approved_plan(tmp_path):
    tables = {
        'audit_fulfillment_contracts': [{'processing_status':'PARTIAL_RETRYABLE'}],
        'findings': [dict(finding_id='F-'+str(i), title='Captured finding '+str(i),
                          category='DISCOVERY_ACCESS', status='OPEN', severity='LOW',
                          source='deterministic-rules-engine', evidence_ids=['EV-'+str(i)])
                     for i in range(2)],
    }
    original = deepcopy(tables)
    plan = render_plan(lambda names: [r for n in names for r in tables.get(n, [])],
                       'UTC', Governance([]))
    assert 'Plano de ação não produzido nesta auditoria parcial' in plan
    assert 'Ações propostas registradas</dt><dd>0' in plan
    assert 'Ações aprovadas registradas</dt><dd>0' in plan
    assert 'Crítica</dt>' not in plan and 'action-card-' not in plan
    html, receipt = summaries(tmp_path, tables, {}, records(tables),
                              dict(state='SOURCE_ABSENT', sources=[]))
    surface = ' '.join(Surface(html['plano']).values)
    assert surface.count('Captured finding') == 2
    assert 'Acesso e descoberta do conteúdo' in surface and 'DISCOVERY_ACCESS' not in surface
    assert 'Em aberto' in surface and 'Motor de regras determinísticas' in surface
    assert 'EV-0' in surface and 'EV-1' in surface
    assert 'não constituem plano de ação' in surface
    assert 'DISCOVERY_ACCESS' in html['plano']  # raw data remain in details
    assert len(receipt['pages']['plano.html'][0]['sources']) == 2
    assert tables == original


def test_category_translation_is_typed_and_keeps_unrelated_evidence():
    assert public_value('DISCOVERY_ACCESS', 'category') == 'Acesso e descoberta do conteúdo'
    for key in ('title', 'observed_value', 'finding_id', 'evidence_ids'):
        assert public_value('DISCOVERY_ACCESS', key) == 'DISCOVERY_ACCESS'
    assert public_value('BOA', 'confidence') == 'Boa'
    assert public_value('OPEN', 'status') == 'Em aberto'
    assert public_value('CDP_MAIN_DOCUMENT_RESPONSE', 'provenance').startswith('Resposta principal')
    assert public_value(0, 'requested') == 'Não'
    assert public_value(0, 'attempt_count') == 0
    for value, field in [('THIRD_PARTY','party'), ('DOM_ELEMENT','evidence_type'),
                         ('LIVE_RECOLLECTION','temporal_mode'), ('TLS_EXTERNAL','integration_id'),
                         ('CUSTOMER_CONTENT_NOT_COMPARABLE','comparison_status')]:
        assert public_value(value, field) != value
        assert public_value(value, 'observed_value') == value


def test_forecast_zero_partial_and_no_attempts_never_become_final_spend():
    tables = {
        'audit_fulfillment_contracts':[{'processing_status':'PARTIAL_RETRYABLE'}],
        'audit_fulfillment_work_items':[{'component':'TECHNICAL_AI', 'status':'REQUESTED_NOT_EXECUTED'}],
        'console_cost_forecast_outcomes':[dict(currency='USD', expected_cost=0.0411926,
            actual_cost=0, likely_low=0.0328769, likely_high=0.05544473,
            source='local-audit-history', status='NOT_COMPARABLE')],
        'serp_observations':[dict(engine='Google', provider='Recorded Search provider',
                                  observation_status='OBSERVED', query='Recorded query')],
    }
    execution, _ = build_execution_context(tables, {'pages':{}})
    body = execution['ia-custos:execution'] + editorial('ia-custos', records(tables), reconcile(tables), load())
    visible = ' '.join(Surface(body).values)
    for phrase in ('0,041193', '0,032877', '0,055445', 'Histórico local de auditorias',
                   'NOT_COMPARABLE', '0 tentativas registradas', 'IA não executada',
                   'Tokens de entrada', 'N/D — não medidos', 'Custo total da auditoria:',
                   'execução parcial', 'Pesquisa Perplexity: nenhuma execução registrada',
                   'Recorded Search provider'):
        assert phrase in visible
    assert 'Não constitui custo final' in visible
    assert 'Tokens de entrada</dt><dd>0' not in body
    assert 'Custo por chamada' not in body  # no repeated empty telemetry panels


def test_existing_attempts_keep_provider_and_separate_estimated_observed_money():
    tables = {'ai_provider_attempts': [dict(attempt_id='A', provider='Recorded provider',
              model='Recorded model', status='SUCCESS', observed_cost=0,
              observed_cost_currency='USD', estimated_cost=1, cost_currency='EUR',
              input_tokens=0, output_tokens=None)]}
    body = editorial('ia-custos', records(tables), reconcile(tables), load())
    assert 'Recorded provider' in body and 'Recorded model' in body
    assert 'Custo por chamada' in body and '0 tentativas registradas' not in body
    assert 'Moeda da estimativa' in body and 'Moeda observada' in body
    assert '>EUR<' in body and '>USD<' in body
    assert reconcile(tables)['totals']['USD'] == {'observado':'0','estimado':None,'conciliado':'0'}


def passive():
    return dict(observation_id='SNP-ONE', device='MOBILE', target_host='example.org',
                capture_utc='2026-11-16T12:00:00Z', method='PASSIVE_READ_ONLY', sha256='a'*64,
                metrics={k:dict(state='OBSERVED', value=v, source='CDP_MAIN_DOCUMENT_RESPONSE')
                         for k,v in [('connected_public_ip','8.8.8.8'),('http_protocol','h2'),('tls_protocol','TLS 1.3')]})


def test_passive_connection_has_identity_method_timezone_and_no_invented_latency(tmp_path, monkeypatch):
    from rasai.parallel_report import scope_context as module
    monkeypatch.setattr(module, 'read_network_observations', lambda *_:[passive()])
    monkeypatch.setattr(module, 'read_authorized_probes', lambda *_:[])
    monkeypatch.setattr(module, 'build_network_assessment', lambda *_:None)
    body, _, detail = network_context(tmp_path, 'AUD-TEST', 'America/Sao_Paulo')
    visible = ' '.join(Surface(body).values)
    for phrase in ('8.8.8.8', 'h2', 'TLS 1.3', '16/11/2026 09:00:00', 'Móvel',
                   'SNP-ONE', 'a'*64, 'Leitura da captura passiva',
                   'Ping / ICMP independente', 'Sem fonte persistida', 'não mede latência ou RTT'):
        assert phrase in visible
    assert 'Condição técnica não catalogada' not in visible
    assert 'id="network-passive-1"' in detail
    rows = _network_metric_rows([passive()], [], 'UTC')
    for row in rows:
        if row['indicator'] in {'Conexão TCP (ms)', 'Negociação TLS (ms)', 'Consulta DNS (ms)'}:
            assert row['value'] is None and row['state'] == 'NOT_OBSERVED'
    assert '<circle' not in body and 'network-route' not in body


def test_verified_persisted_probe_is_read_without_executing_a_probe(tmp_path, monkeypatch):
    from rasai.network_active_probe import CONTRACT, probe_path, read_authorized_probes
    from rasai.parallel_report import scope_context as module
    audit_id = 'AUD-SYNTHETIC'
    row = dict(contract=CONTRACT, audit_id=audit_id, hostname='example.org', port=443,
               state='OBSERVED', capture_utc='2026-11-16T12:00:00Z',
               method='EXPLICIT_DNS_TCP_TLS_PROBE', measurement_origin='LOCAL_OPERATOR_PROCESS',
               metrics={'dns_elapsed_ms':dict(state='OBSERVED', value=0, source='LOCAL_DNS_RESOLVER'),
                        'tcp_handshake_ms':dict(state='OBSERVED', value=4.25, source='LOCAL_TCP_SOCKET'),
                        'tls_handshake_ms':dict(state='OBSERVED', value=9.5, source='LOCAL_TLS_SOCKET'),
                        'traceroute':dict(state='OBSERVED', value=dict(method='WINDOWS_TRACERT',
                            probe_protocol='ICMP', target_reached=False, max_hops=16,
                            hops=[dict(hop=1, state='PUBLIC_HOP', public_ip='8.8.8.8',
                                       rtt_ms=7.25, rtt_samples_ms=[7.0,7.5])]))})
    digest = sha256(json.dumps(row, sort_keys=True, separators=(',', ':'),
                              ensure_ascii=False, allow_nan=False).encode()).hexdigest()
    row.update(sha256=digest, digest_scope='INTEGRITY_ONLY_NOT_AUTHORSHIP')
    path = probe_path(tmp_path, audit_id, 'example.org', 443)
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(row), encoding='utf-8')
    assert len(read_authorized_probes(tmp_path, audit_id)) == 1
    monkeypatch.setattr(module, 'read_network_observations', lambda *_:[])
    monkeypatch.setattr(module, 'build_network_assessment', lambda *_:None)
    before = path.read_bytes()
    body, _, detail = network_context(tmp_path, audit_id, 'UTC')
    visible = ' '.join(Surface(body).values)
    for phrase in ('4,25', '9,5', '7,25', 'RTT (ms)', 'ICMP', '8.8.8.8'):
        assert phrase in body
    # The method remains intact in the sealed sidecar, but is humanized in HTML.
    assert 'WINDOWS_TRACERT' not in visible
    assert 'Sonda autorizada de DNS, TCP e TLS' in visible
    assert 'Rastreamento ICMP registrado pelo tracert' in visible
    assert 'caminho completo não confirmado' in visible
    assert 'id="network-probe-1"' in detail and digest in body
    assert path.read_bytes() == before


def test_analytical_receipt_keeps_compatibility_without_calling_fields_technical_only(tmp_path):
    import sqlite3
    audit = fixture(tmp_path/'audit')
    with sqlite3.connect(audit/'audit.db') as con:
        con.executescript('CREATE TABLE web_performance_attempts(id TEXT, duration_ms REAL);'
                          "INSERT INTO web_performance_attempts VALUES('W1', 123.5);")
    con.close()
    output = generate(audit)
    receipt = json.loads((output/'anexos/dados-de-apoio/evidence-coverage.json').read_text(encoding='utf-8'))['editorial']
    assert receipt['certifies_editorial_completeness'] is False
    for topics in receipt['pages'].values():
        for topic in topics:
            assert 'state' in topic and 'representation_level' in topic
            if topic['state'] == 'PRESENT_TECHNICAL_ONLY':
                assert topic['representation_level'] in {'TECHNICAL_DETAIL_ONLY','PRESENT_ANALYTICAL_FIELDS'}
    topic = next(t for t in receipt['pages']['performance.html']
                 if t['families'] == ['web_performance_attempts'])
    assert topic['state'] == 'PRESENT_TECHNICAL_ONLY'  # compatible legacy state
    assert topic['representation_level'] == 'PRESENT_ANALYTICAL_FIELDS'
    assert '123,5' in (output/'performance.html').read_text(encoding='utf-8')


def test_effective_main_max_width_in_chromium(tmp_path):
    from playwright.sync_api import sync_playwright
    import pytest
    output = generate(fixture(tmp_path/'audit'))
    with sync_playwright() as p:
        if not Path(p.chromium.executable_path).is_file(): pytest.skip('Existing Chromium unavailable')
        browser = p.chromium.launch()
        page = browser.new_page(offline=True)
        for width in (390,1440,2560):
            page.set_viewport_size(dict(width=width,height=1000))
            page.goto((output/'index.html').as_uri())
            assert page.locator('main').evaluate('(e)=>getComputedStyle(e).maxWidth') == '1980px'
            assert page.locator('main').evaluate('(e)=>e.getBoundingClientRect().width') <= 1980
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        assert page.locator('main').evaluate('(e)=>e.getBoundingClientRect().width') == 1980
        page.emulate_media(media='print')
        assert page.locator('main').evaluate('(e)=>getComputedStyle(e).maxWidth') == 'none'
        browser.close()
