from pathlib import Path
from rasai.parallel_report.components import ruler, stack
from rasai.parallel_report.page_views import SECTIONS
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


def test_stack_and_editorial_ownership():
    html = stack([('a',1),('b',3)])
    assert 'data-width="25"' in html and 'data-width="75"' in html
    assert len(SECTIONS) == 8  # dashboard and indices have dedicated metric composition
    assert SECTIONS['plano'][0][1] == ['directed_analysis_actions']


def test_prototype_tokens_and_components():
    css = (Path(__file__).parents[2] / 'src/rasai/parallel_report/assets/site.css').read_text(encoding='utf-8')
    for token in ('--ink:#18222f','--bg:#f4f6f8','--acc:#1f5fa8','--ink:#e6ebf1','--acc:#7db2ec'):
        assert token in css
    for component in ('.shell','.rail','.top','.ruler','.bar','.mk','.chip','.org','.kv','.tw','.callout'):
        assert component in css
