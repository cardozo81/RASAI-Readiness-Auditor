from pathlib import Path
from rasai.parallel_report.components import ruler, stack
from rasai.parallel_report.page_views import SECTIONS, _metric_proposal
from rasai.parallel_report.thresholds import load


def test_ruler_proportions_and_absence():
    html = ruler('SARI', 80, proposal=load()[0])
    assert 'data-position="80"' in html
    assert all(f'data-width="{width}"' in html for width in (60,20,15,5))
    assert 'PRODUCT_PROPOSAL' in html
    assert 'class="mk"' not in ruler('Absent', None)
    assert 'data-position="0"' in ruler('Zero', 0)
    assert 'data-position="100"' in ruler('Overflow', 101)
    assert 'data-position="50"' in ruler('Apdex', .5, maximum=1)


def test_metric_contracts_color_lighthouse_and_apdex_rulers():
    contracts = load()
    lighthouse = _metric_proposal('performance_score', contracts)
    apdex = _metric_proposal('apdex_score', contracts)
    assert lighthouse['thresholds'] == [50, 90]
    assert lighthouse['zone_classes'] == ['z1', 'z2', 'z4']
    assert apdex['thresholds'] == [0.70, 0.85]
    assert apdex['zone_classes'] == ['z1', 'z2', 'z4']
    lighthouse_html = ruler('Lighthouse Performance', 78, 100, lighthouse)
    apdex_html = ruler('Apdex sintético', .85, 1, apdex)
    for html in (lighthouse_html, apdex_html):
        assert 'class="z1"' in html
        assert 'class="z2"' in html
        assert 'class="z4"' in html
        assert 'class="z0"' not in html
    assert 'PERSISTED_CONTRACT' in lighthouse_html
    assert 'PERSISTED_CONTRACT' in apdex_html


def test_stack_and_editorial_ownership():
    html = stack(
        [('IA / integração #1', 1, 'ATTEMPT-A'), ('Remediação de conteúdo #1', 3, 'ATTEMPT-B')],
        title='Composição do custo conciliado por tentativa',
        unit='USD',
    )
    assert 'data-width="25"' in html and 'data-width="75"' in html
    assert 'Composição do custo conciliado por tentativa' in html
    assert 'USD 4' in html
    assert '25,0%' in html and '75,0%' in html
    assert 'ATTEMPT-A' in html and 'ATTEMPT-B' in html
    assert 'class="cat1"' in html and 'class="cat2"' in html
    assert 'class="z1"' not in html and 'class="z2"' not in html
    assert 'stack-legend' in html
    assert len(SECTIONS) == 8  # dashboard and indices have dedicated metric composition
    assert SECTIONS['plano'][0][1] == ['directed_analysis_actions']


def test_prototype_tokens_and_components():
    css = (Path(__file__).parents[2] / 'src/rasai/parallel_report/assets/site.css').read_text(encoding='utf-8')
    for token in ('--ink:#18222f','--bg:#f4f6f8','--acc:#1f5fa8','--ink:#e6ebf1','--acc:#7db2ec'):
        assert token in css
    for component in ('.shell','.rail','.top','.ruler','.bar','.mk','.chip','.org','.kv','.tw','.callout'):
        assert component in css
