from pathlib import Path
from rasai.parallel_report.components import ruler, stack, table
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
    assert html.count('data-explanation=') == 4  # Two bars and two legend entries.
    assert 'title=' not in html  # Avoid a competing native browser tooltip.
    assert len(SECTIONS) == 8  # dashboard and indices have dedicated metric composition
    assert SECTIONS['plano'][0][1] == ['directed_analysis_actions']



def test_status_chip_owns_single_native_tooltip_in_table():
    html = table('Estados', [
        {'status': 'SUCCESS', 'source': 'Captura externa'},
    ], [('status', 'Estado'), ('source', 'Origem')])
    assert '<td><span class="chip ok" title="Concluído">Concluído</span></td>' in html
    assert '<td title="Concluído"><span' not in html
    assert '<td title="Captura externa">Captura externa</td>' in html
    assert 'data-explanation=' not in html


def test_prototype_tokens_and_components():
    css = (Path(__file__).parents[2] / 'src/rasai/parallel_report/assets/site.css').read_text(encoding='utf-8')
    for token in ('--ink:#18222f','--bg:#f4f6f8','--acc:#1f5fa8','--ink:#e6ebf1','--acc:#7db2ec'):
        assert token in css
    for component in ('.shell','.rail','.top','.ruler','.bar','.mk','.chip','.org','.kv','.tw','.callout','.detail-dialog','.modal-open'):
        assert component in css


def test_ruler_marks_only_its_active_zone_in_offline_chromium(tmp_path):
    """Focused rendering: thresholds, 0/100, missing marker, themes and no-JS."""
    import pytest
    sync_playwright = pytest.importorskip('playwright.sync_api').sync_playwright
    assets = Path(__file__).parents[2] / 'src/rasai/parallel_report/assets'
    for name in ('site.css', 'app.js'):
        (tmp_path / name).write_bytes((assets / name).read_bytes())
    proposal = load()[0]  # 60/80/95/100
    values = (0, 59.99, 60, 80, 95, 100, None)
    markup = ''.join(
        f'<section id="case-{i}">' + ruler('Métrica persistida', value, proposal=proposal) + '</section>'
        for i, value in enumerate(values)
    )
    prefix = '<!doctype html><html><head><link rel="stylesheet" href="site.css"></head><body class="light">'
    (tmp_path / 'index.html').write_text(
        prefix + markup + '<script src="app.js"></script></body></html>', encoding='utf-8'
    )
    (tmp_path / 'without-js.html').write_text(prefix + markup + '</body></html>', encoding='utf-8')
    with sync_playwright() as pw:
        if not Path(pw.chromium.executable_path).exists():
            pytest.skip('Existing Chromium unavailable; do not install')
        browser = pw.chromium.launch()
        context = browser.new_context(offline=True)
        page = context.new_page()
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        for width in (390, 1440):
            page.set_viewport_size({'width': width, 'height': 900})
            page.goto((tmp_path / 'index.html').as_uri())
            for theme in ('light', 'dark'):
                page.evaluate('(value) => {document.body.className=value}', theme)
                for index, expected in enumerate((0, 0, 1, 2, 3, 3, None)):
                    actual = page.locator(f'#case-{index} .bar > i').evaluate_all(
                        '(els) => els.map((el,i) => getComputedStyle(el).filter === "none" ? i : null).filter(i => i !== null)'
                    )
                    assert actual == ([] if expected is None else [expected]), (width, theme, index, actual)
            page.emulate_media(media='print')
            assert page.locator('#case-3 .bar > i').evaluate_all(
                '(els) => els.filter(el => getComputedStyle(el).filter === "none").length'
            ) == 1
            page.emulate_media(media='screen')
            page.goto((tmp_path / 'without-js.html').as_uri())
            assert page.locator('.ruler .bar > i').evaluate_all(
                '(els) => els.every(el => getComputedStyle(el).filter === "grayscale(1)")'
            )
        assert errors == []
        browser.close()


def test_stack_tooltip_mouse_and_keyboard_offline(tmp_path):
    import pytest
    sync_playwright = pytest.importorskip('playwright.sync_api').sync_playwright
    assets = Path(__file__).parents[2] / 'src/rasai/parallel_report/assets'
    (tmp_path / 'site.css').write_bytes((assets / 'site.css').read_bytes())
    (tmp_path / 'app.js').write_bytes((assets / 'app.js').read_bytes())
    markup = stack([
        ('IA / integração #1', 0.40, 'ATT-ONE', {
            'kind': 'estimado', 'source': 'IA / integração',
            'purpose': 'Análise semântica', 'provider': 'Provider A',
            'model': 'Model A', 'reasoning': 'Esforço alto solicitado',
        }),
        ('IA / integração #2', 0.60, 'ATT-TWO', {
            'kind': 'observado', 'source': 'IA / integração',
            'purpose': 'Análise direcionada', 'provider': 'Provider B',
            'model': 'Model B', 'reasoning': 'Padrão do provedor (nível não comprovado)',
        }),
    ], unit='USD')
    (tmp_path / 'stack.html').write_text(
        '<!doctype html><html><head><link rel="stylesheet" href="site.css"></head>'
        '<body class="light"><main>' + markup + '</main><script src="app.js"></script></body></html>',
        encoding='utf-8'
    )
    with sync_playwright() as pw:
        if not Path(pw.chromium.executable_path).exists():
            pytest.skip('Use existing Chromium only')
        browser = pw.chromium.launch()
        page = browser.new_page()
        for width in (390, 1440):
            page.set_viewport_size({'width': width, 'height': 900})
            page.goto((tmp_path / 'stack.html').as_uri())
            for theme in ('light', 'dark'):
                page.evaluate('(mode) => document.body.className=mode', theme)
                assert page.locator('.stack[role="img"]').count() == 1
                first = page.locator('.stack > span').first
                first.hover()
                assert 'Análise semântica' in first.get_attribute('data-explanation')
                tooltip = first.evaluate("(node) => getComputedStyle(node, '::after').content")
                assert 'Análise semântica' in tooltip
                item = page.locator('.stack-legend li').nth(1)
                item.focus()
                assert item.get_attribute('tabindex') == '0'
                assert 'observado' in item.get_attribute('data-explanation').lower()
                focused = item.evaluate("(node) => getComputedStyle(node, '::after').content")
                assert 'Model B' in focused
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        browser.close()
