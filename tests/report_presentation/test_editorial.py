import json
from html.parser import HTMLParser
import pytest
from rasai.parallel_report.components import chip, table, ruler
from rasai.parallel_report.presentation_labels import public_value, timezone_for_records, timezone_provenance, metric_label
from rasai.parallel_report.read_model import build
from rasai.parallel_report.page_views import editorial, _metric_proposal
from rasai.parallel_report.action_plan import grouped_actions, content
from rasai.parallel_report.thresholds import load
from rasai.parallel_report.generator import generate
from test_parallel_report import fixture


@pytest.mark.parametrize('value,field,label,tone',[
 ('CRITICAL','severity','Crítica','bad critical'),('HIGH','severity','Alta','bad'),
 ('MEDIUM','severity','Média','warn'),('LOW','severity','Baixa','none'),
 ('HIGH','priority','Alta','bad'),('HIGH','confidence','Alta','none'),
 ('SUCCESS','status','Concluído','ok'),('PARTIAL','coverage','Parcial','warn'),
 ('FAILED','status','Falhou','bad'),('NOT_APPLICABLE','status','Não aplicável','none')])
def test_typed_chips(value,field,label,tone):
    html=chip(value,field)
    assert f'class="chip {tone}"' in html and f'>{label}</span>' in html
    assert f'title="{value}"' in html


def records(tables):
    return build(tables,{name:{'primary_key':[]} for name in tables})


def test_apdex_sources():
    for source,label in [('synthetic_apdex_summaries','navegação'),('synthetic_ux_apdex_summaries','experiência'),('synthetic_population_apdex_summaries','populacional')]:
        assert label in metric_label({'_source_table':source,'device':'MOBILE'},'apdex_score',{})
    label=metric_label({'_source_table':'synthetic_ux_apdex_summaries','device':'POPULATION'},'apdex_score',{})
    assert 'experiência — agregado dos dispositivos' in label and 'populacional' not in label
    data=records({source:[{'device':'MOBILE','apdex_score':.55}] for source in ('synthetic_apdex_summaries','synthetic_ux_apdex_summaries','synthetic_population_apdex_summaries')})
    html=editorial('performance',data,{},load())
    for family in ('navegação','experiência','populacional'):
        assert 'Apdex sintético '+family in html if family=='populacional' else 'Apdex sintético de '+family in html
    assert '>Apdex sintético<' not in html


def test_ruler_origin():
    for key,label in [('value','Proposta de produto'),('performance_score','Contrato persistido'),('apdex_score','Contrato persistido')]:
        html=ruler(key,.5,proposal=_metric_proposal(key,load()),href='#technical-record')
        assert label in html
        assert '<strong><a ' not in html
        assert 'Referência técnica' not in html
        assert 'Abrir registro técnico' in html
        if key!='value':
            assert '>Proposta<' not in html


def test_timestamp_and_context(monkeypatch):
    monkeypatch.setenv('RASAI_PRESENTATION_TIMEZONE','Asia/Tokyo')
    data=records({'audits':[{'audit_id':'a','status':'COMPLETED','created_at':'2026-09-11T00:00:00Z'}],
        'audit_execution_configurations':[{'audit_id':'a','configuration_json':json.dumps({'settings':{'presentation':{'timezone':'America/Sao_Paulo'}}})}],
        'audit_targets':[{'normalized_origin':'https://example.test'}],
        'page_snapshots':[{'device':'MOBILE'},{'device':'DESKTOP'}]})
    zone,reason=timezone_for_records(data)
    assert zone=='America/Sao_Paulo' and reason=='settings.presentation.timezone'
    assert public_value('2026-09-11T00:00:00Z','created_at',zone)=='10/09/2026 21:00:00 (America/Sao_Paulo)'
    assert public_value('2026-09-11','created_at',zone)=='2026-09-11'
    assert public_value('2026-09-11T00:00:00','created_at',zone)=='10/09/2026 21:00:00 (America/Sao_Paulo)'
    assert public_value('2026-09-11T00:00:00Z','title',zone)=='2026-09-11T00:00:00Z'
    html=editorial('index',data,{'coverage':'Não medido','attempt_count':0,'totals':{}},load())
    for expected in ('Domínio auditado','Dispositivo','Fuso de apresentação','Móvel','Desktop','10/09/2026 21:00:00','https://example.test'):
        assert expected in html
    fallback,reason=timezone_for_records(records({'audits':[{'audit_id':'a'}]}))
    assert fallback=='America/Sao_Paulo' and 'não persistido' in timezone_provenance(reason)


def test_action_plan_identity_and_literals():
    actions=[{'action_id':'a','title':'Same','priority':'LOW'},{'action_id':'b','title':'Same','priority':'HIGH'},{'action_id':'a','title':'Same','priority':'LOW'}]
    groups=grouped_actions(actions)
    assert [len(g) for g in groups]==[1,2]
    data=records({'directed_analysis_actions':actions,'improvement_intelligence_recommendations':[{'title':'Fix','original_html':'<script>privateLiteral()</script>','suggested_html':'<h1>New</h1>'}], 'content_remediation_suggestions':[{'objective':'Title','proposed_text':'Original English suggestion'}]})
    html=editorial('plano',data,{},load())
    for title in ('Visão geral','Ações por prioridade','Cartões de ação','Correções técnicas propostas (código)','Textos sugeridos por IA'):
        assert '<h2>'+title+'</h2>' in html
    assert 'Como fazer' in html and 'Como validar' in html
    assert '&lt;script&gt;privateLiteral()&lt;/script&gt;' in html
    assert 'Original English suggestion' in html
    assert 'Proposta persistida' in html
    assert '>Cartão<' not in html
    assert 'Evidências e origem persistida' not in html
    assert 'Referência técnica persistida' in html
    assert 'Abrir registro técnico' in html


def test_typed_residual_values_and_customer_text():
    for token in ('MISSING_PROPOSED','MEASURED','READY','LIMITED_AVAILABILITY','NEWLY_AVAILABLE','WIDELY_AVAILABLE'):
        assert public_value(token,'status') != token
        assert public_value(token,'title') == token
    assert public_value('HIGH','priority')=='Alta'
    assert public_value('P1','priority')=='P1'
    assert public_value('AI','source')=='IA'
    assert public_value('Original provider message','source')=='Original provider message'
    assert public_value('0.0657104','estimated_cost')=='0,0657104'
    dimensions=content([{'dimension':'SECURITY','expected_gain':'HIGH'}],'affected_dimensions_json')
    assert 'Segurança · Ganho esperado na fonte: Alto' in dimensions
    assert 'SECURITY' in dimensions and 'HIGH' in dimensions


class PublicLabels(HTMLParser):
    """Inspect exact public label nodes, not arbitrary client substrings."""
    def __init__(self):
        super().__init__();self.stack=[];self.bad=[]
    def handle_starttag(self,tag,attrs):
        self.stack.append(tag)
    def handle_endtag(self,tag):
        if tag in self.stack:
            self.stack=self.stack[:len(self.stack)-1-self.stack[::-1].index(tag)]
    def handle_data(self,data):
        if any(tag in self.stack for tag in ('pre','code')):
            return
        if self.stack and self.stack[-1] in {'th','dt','button','h1','h2','h3'} and data.strip() in {'Status','Severity','Priority','Provider','Model','Source','Reference','References','Scope','Device','Requests','Input tokens','Output tokens','Duration','Observed','Estimated','Canonical'}:
            self.bad.append(data.strip())


def test_public_labels_across_ten_pages(tmp_path):
    root=fixture(tmp_path/'audit')
    output=generate(root)
    from rasai.parallel_report.read_model import SEARCH_PAGE
    assert SEARCH_PAGE.split('-')==['search','geo']
    assert (output/(SEARCH_PAGE+'.html')).is_file()
    coverage=json.loads((output/'assets/coverage-map.json').read_text(encoding='utf-8'))
    assert coverage['canonical_pages']['cat-05.html']==[SEARCH_PAGE+'.html']
    assert all((output/name).is_file() for pages in coverage['canonical_pages'].values() for name in pages)
    from rasai.parallel_report.parity import compare
    assert compare({},tmp_path)['status']=='PENDING'
    for path in output.glob('*.html'):
        parser=PublicLabels();parser.feed(path.read_text(encoding='utf-8'))
        assert not parser.bad,(path.name,parser.bad)
    html=table('Telemetria',[{'provider':'Provider literal','captured_at':'2026-09-11T00:00:00Z','_ref':'#record'}],[('provider','Provider'),('captured_at','Capturado em'),('_ref','Fonte')],timezone_name='America/Sao_Paulo')
    assert '<th scope="col">Provedor</th>' in html and 'Provider literal' in html
    assert '10/09/2026 21:00:00' in html and 'title="2026-09-11T00:00:00Z"' in html
    assert 'Evidência e detalhes' not in html
    assert 'Abrir registro técnico' in html
    assert 'class="modal-open"' in html
    assert 'Ver detalhes' in html
    assert '<dialog class="detail-dialog"' in html
    assert 'Dados persistidos completos' in html
    assert 'Abrir registro técnico completo' in html

    for path in output.glob('*.html'):
        page_html=path.read_text(encoding='utf-8')
        assert 'Evidência e detalhes' not in page_html
        assert 'Evidências e origem persistida' not in page_html
        assert 'href="#">' not in page_html


def test_chip_palette_contrast():
    from pathlib import Path
    import re
    css=(Path(__file__).parents[2]/'src/rasai/parallel_report/assets/site.css').read_text(encoding='utf-8')
    def luminance(color):
        color=color.lstrip('#')
        if len(color)==3:
            color=''.join(c*2 for c in color)
        rgb=[int(color[i:i+2],16)/255 for i in (0,2,4)]
        rgb=[c/12.92 if c<=.04045 else ((c+.055)/1.055)**2.4 for c in rgb]
        return sum(c*w for c,w in zip(rgb,(.2126,.7152,.0722)))
    for selector in (':root','body.dark'):
        block=re.search(re.escape(selector)+r'\{([^}]+)',css).group(1)
        tokens=dict(re.findall(r'--([a-z]+):(#[0-9a-f]+)',block))
        for foreground in ('ok','warn','bad','none','acc'):
            for background in ('card','bg'):
                low,high=sorted((luminance(tokens[foreground]),luminance(tokens[background])))
                assert (high+.05)/(low+.05)>=4.5,(selector,foreground,background)
