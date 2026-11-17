"""Focal offline Chromium smoke; no installation or operational pipeline."""
from pathlib import Path
import pytest
from playwright.sync_api import sync_playwright
from test_parallel_report import fixture
from rasai.parallel_report.generator import generate


def test_browser_offline(tmp_path):
    root = fixture(tmp_path / 'audit')
    import sqlite3
    with sqlite3.connect(root / 'audit.db') as database:
        database.execute('UPDATE findings SET title=?',('Persisted technical identifier: '+'LONG_IDENTIFIER_'*12,))
    database.close()
    output = generate(root)
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
        for width in (1440, 1920, 768, 390):
            page.set_viewport_size({'width': width, 'height': 1080})
            for path in output.glob('*.html'):
                page.goto(path.as_uri())
                assert page.locator('nav[aria-label="Páginas"] a').count() == 11
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), path.name
                # The theme is persisted across pages. A click must invert the
                # *current* effective choice, not always force dark mode.
                was_dark = page.evaluate('''() => document.body.classList.contains("dark") ||
                    (!document.body.classList.contains("light") &&
                     matchMedia("(prefers-color-scheme: dark)").matches)''')
                page.locator('#theme').click()
                assert page.locator('body').evaluate('(e) => e.classList.contains("dark")') is (not was_dark)
                assert page.locator('body').evaluate('(e) => e.classList.contains("light")') is was_dark
                page.locator('#expand').click()
                assert page.locator('details:not([open])').count() == 0
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), (path.name,'expanded')
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
                if page.locator('.modal-open:not(.capture-image-button)').count():
                    # Screenshot zoom has a dedicated browser test below;
                    # the generic detail-dialog contract expects provenance details.
                    trigger = page.locator('.modal-open:not(.capture-image-button)').first
                    trigger.focus()
                    trigger.click()
                    assert page.locator('dialog.detail-dialog[open]').count() == 1
                    assert page.locator('body').evaluate('(e) => e.classList.contains("modal-active")')
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), (path.name,'modal')
                    assert page.locator('dialog.detail-dialog[open] details').count() >= 1
                    page.keyboard.press('Escape')
                    assert page.locator('dialog.detail-dialog[open]').count() == 0
                    assert not page.locator('body').evaluate('(e) => e.classList.contains("modal-active")')
                    assert page.evaluate('document.activeElement.classList.contains("modal-open")')
        page.goto((output / 'index.html').as_uri())
        page.keyboard.press('Tab')
        assert page.evaluate('document.activeElement.className') == 'skip'
        assert page.evaluate('getComputedStyle(document.activeElement).outlineStyle') != 'none'
        page.emulate_media(media='print')
        page.pdf(path=str(tmp_path / 'smoke-a4.pdf'), format='A4')
        assert not requests and not errors
        browser.close()


def test_capture_preview_button_opens_offline_modal(tmp_path):
    """Exercise the exact control reported inert by a user, not just its href."""
    root = fixture(tmp_path / 'audit')
    output = generate(root)
    with sync_playwright() as playwright:
        if not Path(playwright.chromium.executable_path).exists():
            pytest.skip('Existing Chromium unavailable; do not install')
        browser = playwright.chromium.launch()
        context = browser.new_context(offline=True)
        context.route(
            '**/*',
            lambda route: route.abort()
            if route.request.url.startswith(('http:', 'https:'))
            else route.continue_(),
        )
        page = context.new_page()
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        for width in (1440, 390):
            page.set_viewport_size({'width': width, 'height': 900})
            page.goto((output / 'extracao.html').as_uri())
            button = page.get_by_role('button', name='Captura e prévia técnica local')
            assert button.count() == 1
            assert button.get_attribute('aria-controls') == 'capture-context-modal'
            button.click()
            modal = page.locator('dialog#capture-context-modal[open]')
            assert modal.is_visible(), 'Click must open an actual dialog, not only change a hash'
            assert modal.get_by_text('Capturas persistidas na auditoria').count() >= 1
            assert modal.get_by_text('Consultar contagens derivadas da captura').count() == 1
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            page.keyboard.press('Escape')
            assert not modal.is_visible()
            assert button.evaluate('(element) => element === document.activeElement')
            button.click()
            modal.get_by_role('link', name='Consultar a prévia da captura nesta página').click()
            assert not modal.is_visible()
            assert page.evaluate('location.hash') == '#capture-preview'
            # hashchange is dispatched asynchronously after the fragment changes.
            # Wait on the actual open state; do not race against the browser event.
            page.locator('details#capture-preview[open]').wait_for(state='visible', timeout=10000)
            # The control must work even after navigating to the same fragment.
            button.click()
            assert modal.is_visible()
            modal.get_by_role('button', name='Fechar').last.click()
            assert not modal.is_visible()
        assert not errors, errors
        browser.close()


def test_screenshot_is_visible_before_click_and_enlarges_offline(tmp_path):
    """The page itself shows the persisted screenshot; zoom is optional."""
    from test_capture_gallery import _audit_with_screenshot

    root, _ = _audit_with_screenshot(tmp_path)
    output = generate(root)
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
        for width in (1440, 390):
            page.set_viewport_size({'width': width, 'height': 900})
            page.goto((output / 'extracao.html').as_uri())
            screenshot = page.locator('img.capture-image-preview')
            assert screenshot.count() == 1
            assert screenshot.is_visible(), 'Screenshot must render in the HTML before opening any dialog'
            screenshot.scroll_into_view_if_needed()
            page.wait_for_function('document.querySelector("img.capture-image-preview").complete && document.querySelector("img.capture-image-preview").naturalWidth > 0')
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            button = page.get_by_role('button', name='Ampliar Captura 1 - Móvel')
            button.click()
            dialog = page.locator('dialog.capture-image-dialog[open]')
            assert dialog.is_visible()
            page.wait_for_function('document.querySelector("dialog.capture-image-dialog[open] img").complete && document.querySelector("dialog.capture-image-dialog[open] img").naturalWidth > 0')
            page.keyboard.press('Escape')
            assert not dialog.is_visible()
            assert screenshot.is_visible()
        assert not requests and not errors, (requests, errors)
        browser.close()
