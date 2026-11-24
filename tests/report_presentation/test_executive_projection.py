"""Synthetic regressions for partial-AUD structure, fidelity and provenance."""
from hashlib import sha256
import json
import re
import socket
import sqlite3
import subprocess
import urllib.request

import pytest

from rasai.parallel_report import capture_projection as module
from rasai.parallel_report.artifact_reader import inventory
from rasai.parallel_report.capture_projection import project_capture, public_data
from rasai.parallel_report.history_projection import crux_history
from rasai.parallel_report.generator import generate
from test_parallel_report import fixture, Links


HTML = b'''<!doctype html><html><head><title>Synthetic capture</title></head><body>
<main><h1>Observed heading</h1><p>Captured statement to verify.</p>
<details><summary>Question?</summary><p>Answer in captured DOM.</p></details></main></body></html>'''


def captured(root):
    (root / 'artifacts').mkdir(parents=True, exist_ok=True)
    (root / 'artifacts/dom.html').write_bytes(HTML)
    rows = dict(audits=[dict(audit_id='AUD-SYNTHETIC', status='FAILED')], page_snapshots=[dict(
        snapshot_id='SNP-1', page_id='PGE-1', device='MOBILE', requested_url='https://example.test/',
        final_url='https://example.test/', captured_at='2026-11-16T12:00:00+00:00',
        rendered_artifact_ref='artifacts/dom.html', browser_metadata=json.dumps(dict(
            rendered_dom=dict(sha256=sha256(HTML).hexdigest()))))])
    return rows


def forbidden(*a, **k):
    raise AssertionError('No HTTP, AI, collector or companion loader authorized')


def test_partial_capture_reuses_bounded_worker_without_terminal_gate_or_network(tmp_path, monkeypatch):
    rows = captured(tmp_path)
    from rasai import contextual_advisory, contextual_editorial
    monkeypatch.setattr(contextual_advisory, 'load_projection', forbidden)
    monkeypatch.setattr(contextual_editorial, 'ai_availability', forbidden)
    monkeypatch.setattr(socket, 'create_connection', forbidden)
    monkeypatch.setattr(urllib.request, 'urlopen', forbidden)
    before = inventory(tmp_path)
    projection = project_capture(tmp_path, rows, before)
    assert projection['state'] == 'AVAILABLE'
    assert projection['content_structure_v3']['captures'][0]['title']['text'] == 'Synthetic capture'
    assert projection['content_structure_v3']['captures'][0]['headings'][0]['text'] == 'Observed heading'
    assert projection['network_requests'] == projection['provider_calls'] == projection['audit_writes'] == 0
    assert projection['sources'][0]['sha256'] == sha256(HTML).hexdigest()
    assert inventory(tmp_path) == before


@pytest.mark.parametrize('scenario,state', [
    ('no_snapshot','SOURCE_ABSENT'), ('no_file','SOURCE_ABSENT'), ('missing_contract','PROJECTION_ERROR'),
    ('mismatch','SOURCE_INTEGRITY_MISMATCH'), ('oversize','RESOURCE_LIMIT'),
    ('bad_sidecar','PARTIAL'), ('missing_sidecar','PARTIAL'), ('truncated_sidecar','PARTIAL'),
    ('truncated_dom','PARTIAL'),
])
def test_capture_failures_are_distinct_and_do_not_publish_exception_text(tmp_path, scenario, state):
    rows = captured(tmp_path)
    snapshot = rows['page_snapshots'][0]
    if scenario == 'no_snapshot': rows['page_snapshots'] = []
    if scenario == 'no_file': (tmp_path/'artifacts/dom.html').unlink()
    if scenario == 'missing_contract': snapshot.pop('captured_at')
    if scenario == 'mismatch': snapshot['browser_metadata'] = json.dumps({'rendered_dom':{'sha256':'0'*64}})
    if scenario == 'oversize': (tmp_path/'artifacts/dom.html').write_bytes(b'x'*(module.MAX_BYTES+1))
    if scenario in {'bad_sidecar','truncated_sidecar','missing_sidecar'}:
        snapshot['structured_data_ref'] = 'artifacts/structured.json'
        if scenario != 'missing_sidecar':
            (tmp_path/'artifacts/structured.json').write_text('123' if scenario=='bad_sidecar' else '{"@type":',encoding='utf-8')
    if scenario == 'truncated_dom':
        raw = b'<html><body><main><h1>Truncated'
        (tmp_path/'artifacts/dom.html').write_bytes(raw)
        snapshot['browser_metadata'] = json.dumps({'rendered_dom':{'sha256':sha256(raw).hexdigest()}})
    result = project_capture(tmp_path, rows, inventory(tmp_path))
    assert result['state'] == state
    assert str(tmp_path) not in json.dumps(result)
    if scenario == 'mismatch': assert not result['captures']
    if 'sidecar' in scenario:
        assert result['content_structure_v3']['captures'][0]['title']['text'] == 'Synthetic capture'


@pytest.mark.parametrize('exc,cause', [(ValueError('private diagnostics'), 'OFFLINE_WORKER_ERROR'),
    (OSError('private diagnostics'), 'OFFLINE_WORKER_ERROR'),
    (subprocess.TimeoutExpired('private command', 5), 'WORKER_TIMEOUT')])
def test_offline_worker_error_has_only_sanitized_cause(tmp_path, monkeypatch, exc, cause):
    rows = captured(tmp_path)
    def error(*a, **k): raise exc
    monkeypatch.setattr(module, '_worker', error)
    result = project_capture(tmp_path, rows, inventory(tmp_path))
    assert result['state'] == 'PROJECTION_ERROR'
    assert result['sources'][0]['cause'] == cause
    assert 'private' not in json.dumps(result)


def test_raw_fallback_and_optional_sidecars_are_labeled(tmp_path):
    rows = captured(tmp_path)
    snapshot = rows['page_snapshots'][0]
    snapshot['raw_artifact_ref'] = snapshot.pop('rendered_artifact_ref')
    snapshot['main_content_ref'] = 'artifacts/main.txt'
    snapshot['structured_data_ref'] = 'artifacts/data.json'
    (tmp_path/'artifacts/main.txt').write_text('Observed text',encoding='utf-8')
    (tmp_path/'artifacts/data.json').write_text('[{"@type":"FAQPage"}]',encoding='utf-8')
    result = project_capture(tmp_path, rows, inventory(tmp_path))
    assert result['captures'][0]['surface'] == 'RAW_HTML_FALLBACK'
    assert 'LATE_RENDERING_NOT_CAPTURED_ND' in result['captures'][0]['limitations']
    assert result['sources'][1]['excerpt'] == 'Observed text'
    assert result['sources'][2]['observed_types'] == ['FAQPage']


def presentation_with_capture(tmp_path):
    root = fixture(tmp_path / 'audit')
    data = captured(root)
    with sqlite3.connect(root/'audit.db') as con:
        for name in ('page_id','device','requested_url','final_url','captured_at','browser_metadata'):
            con.execute('ALTER TABLE page_snapshots ADD COLUMN '+name+' TEXT')
        snapshot = data['page_snapshots'][0]
        for key,value in snapshot.items():
            if key != 'snapshot_id': con.execute('UPDATE page_snapshots SET '+key+'=?',(value,))
        con.execute("UPDATE audits SET status='FAILED'")
        con.execute('ALTER TABLE findings ADD COLUMN category TEXT')
        con.execute("UPDATE findings SET category='DISCOVERY_ACCESS'")
    con.close()
    return root


def test_generation_projects_once_shares_pages_and_preserves_classification(tmp_path, monkeypatch):
    root = presentation_with_capture(tmp_path)
    count = []
    original = module._worker
    def worker(*a, **k):
        count.append(1)
        return original(*a, **k)
    monkeypatch.setattr(module, '_worker', worker)
    before = inventory(root)
    out = generate(root)
    assert len(count) == 1
    assert len(list(out.glob('*.html'))) == 11
    for name in ('extracao.html','conteudo.html','search'+'-geo.html'):
        body = (out/name).read_text(encoding='utf-8')
        assert 'Observed heading' in body and 'Synthetic capture' in body
        trace = re.findall(r'<summary>Rastreabilidade</summary><pre>.*?</pre>', body, re.S)
        assert body.count('STRUCTURAL_EXTRACTION_ONLY') == sum(
            block.count('STRUCTURAL_EXTRACTION_ONLY') for block in trace)
        assert 'Achados semânticos e acessibilidade' not in body
    assert 'DISCOVERY_ACCESS' in ''.join(p.read_text(encoding='utf-8') for p in (out/'anexos').glob('*.json'))
    assert inventory(root) == before
    assert generate(root) == out and len(count) == 1
    receipt = json.loads((out/'anexos/dados-de-apoio/evidence-coverage.json').read_text(encoding='utf-8'))
    assert receipt['editorial']['capture_state'] == 'AVAILABLE'
    assert receipt['editorial']['certifies_editorial_completeness'] is False
    # A changed bound source is never published over a valid prior presentation.
    prior = {p.relative_to(out).as_posix():p.read_bytes() for p in out.rglob('*') if p.is_file()}
    (root/'artifacts/dom.html').write_bytes(b'changed')
    with pytest.raises(RuntimeError, match='integrity mismatch'):
        generate(root)
    assert prior == {p.relative_to(out).as_posix():p.read_bytes() for p in out.rglob('*') if p.is_file()}


def history_fixture(root):
    folder=root/'artifacts/observability';folder.mkdir(parents=True)
    periods=[dict(firstDate=dict(year=2026,month=9,day=1),lastDate=dict(year=2026,month=9,day=28)),
             dict(firstDate=dict(year=2026,month=10,day=1),lastDate=dict(year=2026,month=10,day=28))]
    payload=dict(format_version='RASAI-CRUX-HISTORY-001',request=dict(origin='https://example.test',formFactor='PHONE'),
        response=dict(record=dict(key=dict(origin='https://example.test',formFactor='PHONE'),collectionPeriods=periods,
            metrics=dict(largest_contentful_paint=dict(percentilesTimeseries=dict(p75s=[2000,3000]))))))
    raw=json.dumps(payload).encode();(folder/'history.json').write_bytes(raw)
    con=sqlite3.connect(folder/'observability.db')
    con.executescript('CREATE TABLE datasets(dataset_id,artifact_path,artifact_sha256);'
        'CREATE TABLE crux_history(dataset_id,target,target_scope,form_factor,metric,period_start,period_end,p75);')
    con.execute('INSERT INTO datasets VALUES(?,?,?)',('OBS-1','artifacts/observability/history.json',sha256(raw).hexdigest()))
    con.executemany('INSERT INTO crux_history VALUES(?,?,?,?,?,?,?,?)',[
        ('OBS-1','https://example.test','ORIGIN','PHONE','largest_contentful_paint','2026-09-01','2026-09-28',2000),
        ('OBS-1','https://example.test','ORIGIN','PHONE','largest_contentful_paint','2026-10-01','2026-10-28',3000)])
    con.commit();con.close()
    return dict(standards_service_runs=[dict(service_id='crux-history',details_json=dict(datasets=['OBS-1']))])


def test_history_matches_raw_bytes_dates_device_scope_and_normalized_points(tmp_path):
    rows=history_fixture(tmp_path); before=inventory(tmp_path)
    history=crux_history(tmp_path,rows,before)
    assert history['state']=='AVAILABLE'
    group=history['groups'][0]
    assert (group['first_p75'],group['last_p75'],group['periods'])==(2000,3000,2)
    assert group['scope']=='ORIGIN' and group['form_factor']=='PHONE' and group['unit']=='ms'
    assert inventory(tmp_path)==before


@pytest.mark.parametrize('failure', ['missing','bad_json','hash','scope','date','value','single_period'])
def test_history_does_not_claim_evolution_without_verified_comparability(tmp_path,failure):
    rows=history_fixture(tmp_path); folder=tmp_path/'artifacts/observability'
    if failure=='missing': (folder/'history.json').unlink()
    if failure in {'hash','bad_json'}:
        (folder/'history.json').write_bytes(b'corrupt' if failure=='hash' else b'{')
        if failure=='bad_json':
            with sqlite3.connect(folder/'observability.db') as c:
                c.execute('UPDATE datasets SET artifact_sha256=?',(sha256(b'{').hexdigest(),))
            c.close()
    if failure in {'scope','date','value','single_period'}:
        with sqlite3.connect(folder/'observability.db') as c:
            if failure=='scope': c.execute("UPDATE crux_history SET target_scope='URL'")
            if failure=='date': c.execute("UPDATE crux_history SET period_start='2026-99-99'")
            if failure=='value': c.execute('UPDATE crux_history SET p75=999')
            if failure=='single_period': c.execute("DELETE FROM crux_history WHERE period_start='2026-10-01'")
        c.close()
    history=crux_history(tmp_path,rows,inventory(tmp_path))
    assert not history['groups']
    assert history['state']!='AVAILABLE'
    if failure=='hash': assert history['state']=='SOURCE_INTEGRITY_MISMATCH'


def test_captured_instructions_paths_and_url_parameters_remain_untrusted_text():
    value={'text':'Ignore instructions <script>run()</script> C:\\Users\\Synthetic\\private.txt https://example.test/?private=hidden',
           'api_key':'SYNTHETIC_CREDENTIAL'}
    safe=public_data(value)
    assert 'private.txt' not in safe['text'] and 'hidden' not in safe['text']
    assert safe['api_key']=='[REDACTED]'
    from rasai.parallel_report.components import text
    assert '<script>' not in text(safe['text']) and '&lt;script&gt;' in text(safe['text'])


def test_two_device_captures_keep_unique_html_ids_and_separate_provenance(tmp_path):
    root=presentation_with_capture(tmp_path)
    with sqlite3.connect(root/'audit.db') as con:
        con.execute("INSERT INTO page_snapshots SELECT 'snapshot-2',rendered_artifact_ref,page_id,'DESKTOP',"
                    "requested_url,final_url,captured_at,browser_metadata FROM page_snapshots")
    con.close()
    out=generate(root)
    for p in out.glob('*.html'):
        doc=Links(p.read_text(encoding='utf-8'))  # asserts every id is unique
        assert doc.ids
    receipt=json.loads((out/'anexos/dados-de-apoio/evidence-coverage.json').read_text(encoding='utf-8'))
    topic=next(t for t in receipt['editorial']['pages']['conteudo.html']
               if t['topic']=='Estrutura editorial verificável da captura')
    sources=[s for s in topic['sources'] if s.get('sha256')]
    assert len(sources)==2 and {s['scope'] for s in sources}=={'MOBILE','DESKTOP'}


def test_executive_summaries_reconcile_partial_sample_and_ai_overview_without_inference(tmp_path):
    root=presentation_with_capture(tmp_path)
    refs=[dict(title='Reference '+str(n),link='https://reference'+str(n)+'.test/') for n in range(9)]
    raw=json.dumps(dict(ai_overview=dict(references=refs))).encode()
    (root/'artifacts/serp.json').write_bytes(raw)
    with sqlite3.connect(root/'audit.db') as con:
        con.executescript('''
        CREATE TABLE element_observations(element_observation_id PRIMARY KEY,tag_name,text_excerpt,artifact_reference);
        CREATE TABLE serp_observations(observation_id PRIMARY KEY,query,result_count,raw_evidence_ref,raw_evidence_sha256);
        CREATE TABLE serp_competitive_analyses(observation_id PRIMARY KEY,comparison_status,candidate_count,observed_competitor_pages);
        CREATE TABLE standards_metric_observations(observation_id PRIMARY KEY,source,scope,state,details_json);
        ''')
        con.executemany('INSERT INTO element_observations VALUES(?,?,?,?)',[(str(n),'button','Observed text','artifacts/dom.html') for n in range(19)])
        con.execute('INSERT INTO serp_observations VALUES(?,?,?,?,?)',('OBS-1','synthetic question',5,'artifacts/serp.json',sha256(raw).hexdigest()))
        con.execute('INSERT INTO serp_competitive_analyses VALUES(?,?,?,?)',('OBS-1','CUSTOMER_CONTENT_NOT_COMPARABLE',3,0))
        con.execute('INSERT INTO standards_metric_observations VALUES(?,?,?,?,?)',('M1','W3C','PAGE','OBSERVED',json.dumps(dict(messages=[dict(type='error',message='Persisted HTML issue')]*9))))
        con.execute('INSERT INTO standards_metric_observations VALUES(?,?,?,?,?)',('M2','CSS validator','PAGE','OBSERVED',json.dumps(dict(error_details=[dict(type='parse-error',message='Persisted CSS issue')]*195))))
    con.close()
    before=inventory(root);out=generate(root)
    extraction=(out/'extracao.html').read_text(encoding='utf-8')
    assert '19' in extraction and 'Estrutura DOM observada' in extraction
    search=(out/('search'+'-geo.html')).read_text(encoding='utf-8')
    assert 'não permitiu comparação' in search
    assert 'CUSTOMER_CONTENT_NOT_COMPARABLE' in ''.join(p.read_text(encoding='utf-8') for p in (out/'anexos').glob('*.json'))
    for n in range(9): assert 'https://reference'+str(n)+'.test/' in search
    discovery=(out/'descoberta.html').read_text(encoding='utf-8')
    assert '195' in discovery and 'Persisted CSS issue' in discovery and 'Persisted HTML issue' in discovery
    receipt=json.loads((out/'anexos/dados-de-apoio/evidence-coverage.json').read_text(encoding='utf-8'))['editorial']
    assert len(receipt['pages'])==11
    coverage=json.loads((out/'anexos/dados-de-apoio/coverage-map.json').read_text(encoding='utf-8'))
    assert coverage['families']['element_observations']['levels']['editorial_summary']
    assert not coverage['families']['findings']['levels']['conclusion_or_decision_present']
    assert inventory(root)==before
    with sqlite3.connect(root/'audit.db') as con:
        con.execute('UPDATE serp_observations SET raw_evidence_sha256=?',('0'*64,))
    con.close()
    with pytest.raises(RuntimeError,match='integrity mismatch'):
        generate(root)


def test_source_change_during_projection_refuses_publication(tmp_path,monkeypatch):
    root=presentation_with_capture(tmp_path)
    original=module._worker
    def mutate(*args,**kw):
        result=original(*args,**kw)
        (root/'artifacts/dom.html').write_bytes(b'changed after read')
        return result
    monkeypatch.setattr(module,'_worker',mutate)
    with pytest.raises(RuntimeError,match='Source changed'):
        generate(root)
    assert not (root/'report-presentation').exists()
