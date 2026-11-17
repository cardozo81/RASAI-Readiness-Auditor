"""Information coverage is observable values, not record-anchor counts."""
import json
import sqlite3
from html import escape

from rasai.parallel_report.analytical_views import build_analytical_views
from rasai.parallel_report.read_model import build, SEARCH_PAGE
from rasai.parallel_report.artifact_reader import inventory
from rasai.parallel_report.history_projection import crux_history
from test_executive_projection import history_fixture


def project(name, rows):
    tables={name:rows}
    schema={name:dict(primary_key=['id'],columns=list(rows[0]))}
    return build_analytical_views(tables,build(tables,schema),schema,'America/Sao_Paulo')


def test_one_hundred_results_have_every_title_and_full_snippet_outside_modals():
    rows=[dict(id=str(i),position=i+1,title='Unique title '+str(i),
               snippet='Captured '+'long sentence '*30+'END-'+str(i),url='https://example.test/'+str(i)) for i in range(100)]
    html,receipt=project('serp_results',rows)
    direct=html[SEARCH_PAGE].split('<dialog')[0]
    assert direct.count('<tr>')==101
    for row in rows:
        assert escape(row['title']) in direct
        assert escape(row['snippet']) in direct
    scope=receipt[SEARCH_PAGE+'.html']['serp_results']
    assert scope['analytical_records']==100 and scope['field_cells']['snippet']==100
    assert scope['adequate_representation_certified'] is False
    assert 'id' in scope['fields_not_in_this_projection']


def test_feature_classification_and_description_are_not_replaced_by_null_metric():
    html,receipt=project('standards_metric_observations',[dict(id='m1',label='feature one',value=None,
        details_json=json.dumps(dict(classification='LIMITED_AVAILABILITY',description='Observed feature description')))])
    direct=html['descoberta'].split('<dialog')[0]
    assert 'Observed feature description' in direct and 'Disponibilidade limitada' in direct
    assert receipt['descoberta.html']['standards_metric_observations']['field_cells']['classification']==1


def test_nested_evidence_is_not_falsely_certified_as_interpreted():
    html,receipt=project('evidence',[dict(id='e1',observed_value={'unknown_contract':{'value':42}})])
    scope=receipt['extracao.html']['evidence']
    assert 'observed_value' not in scope['direct_fields']
    assert scope['structured_fields_in_detail']==['observed_value']
    assert scope['executive_interpretation_certified'] is False


def test_rule_criterion_and_persisted_result_are_both_direct():
    html,receipt=project('rule_executions',[dict(id='r1',rule_id='RULE-X',result='WARNING',
        observed_value='actual fact',expected_condition='required condition')])
    direct=html['indices'].split('<dialog')[0]
    assert 'actual fact' in direct and 'required condition' in direct and 'RULE-X' in direct
    assert receipt['indices.html']['rule_executions']['field_cells']['expected_condition']==1


def test_history_keeps_middle_window_value_not_only_endpoints(tmp_path):
    tables=history_fixture(tmp_path)
    folder=tmp_path/'artifacts/observability'
    p=folder/'history.json';data=json.loads(p.read_text())
    data['response']['record']['collectionPeriods'].append(dict(firstDate=dict(year=2026,month=9,day=15),lastDate=dict(year=2026,month=10,day=12)))
    data['response']['record']['metrics']['largest_contentful_paint']['percentilesTimeseries']['p75s'].append(2500)
    raw=json.dumps(data).encode();p.write_bytes(raw)
    from hashlib import sha256
    with sqlite3.connect(folder/'observability.db') as con:
        con.execute('UPDATE datasets SET artifact_sha256=?',(sha256(raw).hexdigest(),))
        con.execute('INSERT INTO crux_history VALUES(?,?,?,?,?,?,?,?)',('OBS-1','https://example.test','ORIGIN','PHONE','largest_contentful_paint','2026-09-15','2026-10-12',2500))
    con.close()
    result=crux_history(tmp_path,tables,inventory(tmp_path))
    assert result['state']=='AVAILABLE'
    assert [r['p75'] for r in result['groups'][0]['series']]==[2000,2500,3000]
    from rasai.parallel_report.executive_evidence import summaries
    from html.parser import HTMLParser
    class Visible(HTMLParser):
        def __init__(self):
            super().__init__(); self.dialog=0; self.values=[]
        def handle_starttag(self,tag,attrs):
            if tag=='dialog': self.dialog+=1
        def handle_endtag(self,tag):
            if tag=='dialog': self.dialog-=1
        def handle_data(self,value):
            if not self.dialog: self.values.append(value)
    html,_=summaries(tmp_path,tables,inventory(tmp_path),(),dict(state='SOURCE_ABSENT',sources=[]))
    parser=Visible();parser.feed(html['performance'])
    assert '2500' in ' '.join(parser.values)
