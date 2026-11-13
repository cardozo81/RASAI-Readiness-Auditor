"""Focal offline Chromium smoke; no installation or operational pipeline."""
from pathlib import Path
import pytest
from playwright.sync_api import sync_playwright
from test_parallel_report import fixture
from rasai.parallel_report.generator import generate


def test_browser_offline(tmp_path):
    output = generate(fixture(tmp_path / 'audit'))
    with sync_playwright() as playwright:
        if not Path(playwright.chromium.executable_path).exists():
            pytest.skip('Existing Chromium unavailable; do not install')
        browser = playwright.chromium.launch()
        context = browser.new_context(offline=True)
        requests, errors = [], []
        context.route('**/*', lambda route: route.abort() if route.request.url.startswith(('http:', 'https:')) else route.continue_())
        page = context.new_page()
        page.on('request', lambda request: requests.append(request.url) if request.url.startswith(('http:', 'https:')) else None)
        page.on('pageerror', lambda error: errors.append(str(error)))
        for width in (1440, 1920, 768):
            page.set_viewport_size({'width': width, 'height': 1080})
            for path in output.glob('*.html'):
                page.goto(path.as_uri())
                assert page.locator('nav[aria-label="Páginas"] a').count() == 10
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), path.name
                page.locator('#theme').click()
                assert page.locator('body').evaluate('(e) => e.classList.contains("dark")')
                page.locator('#expand').click()
                assert page.locator('details:not([open])').count() == 0
                page.locator('#expand').click()
                assert page.locator('details[open]').count() == 0
                for selector in ('.shell', '.top', '.rail'):
                    assert page.locator(selector).count() == 1
                if page.locator('table').count():
                    header = page.locator('table thead th').first
                    header.focus()
                    page.keyboard.press('Enter')
                    assert header.get_attribute('aria-sort') == 'ascending'
                    page.keyboard.press('Space')
                    assert header.get_attribute('aria-sort') == 'descending'
                for field in page.locator('.tools input').all():
                    field.fill('no-match-unique')
                    assert '0 de ' in field.locator('..').inner_text()
                    field.fill('')
        page.goto((output / 'index.html').as_uri())
        page.keyboard.press('Tab')
        assert page.evaluate('document.activeElement.className') == 'skip'
        assert page.evaluate('getComputedStyle(document.activeElement).outlineStyle') != 'none'
        page.emulate_media(media='print')
        page.pdf(path=str(tmp_path / 'smoke-a4.pdf'), format='A4')
        assert not requests and not errors
        browser.close()
