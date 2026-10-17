"""Same-document FAQ click pilot in an offline, independently owned Chrome page."""
from __future__ import annotations

import os

from playwright.sync_api import sync_playwright

from rasai.faq_existing_page_pilot import inspect_existing_page_faq


_URL = "https://faq-fixture.test/faq"
_HTML = """<!doctype html><html><body>
<button id="trigger" aria-controls="faq-answer" aria-expanded="false">
Qual e a cobertura?</button><main id="slot"></main>
<script>
document.getElementById("trigger").addEventListener("click", () => {
    document.getElementById("trigger").setAttribute("aria-expanded", "true");
    document.getElementById("slot").innerHTML =
        '<section id="faq-answer"><p>A cobertura consta do contrato.</p></section>';
});
</script></body></html>"""


def test_offline_browser_faq_disclosure_only_after_opt_in_on_same_page():
    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            channel=os.environ.get("RASAI_322_CHROME_CHANNEL") or None,
            headless=True,
        )
        try:
            context = browser.new_context(service_workers="block")
            seen = []
            def fixture_route(route):
                seen.append(route.request.url)
                if route.request.url == _URL:
                    route.fulfill(status=200, content_type="text/html", body=_HTML)
                else:
                    route.abort()
            context.route("**/*", fixture_route)
            page = context.new_page()
            page.goto(_URL, wait_until="load")
            assert seen == [_URL]
            first = page.content()
            skipped = inspect_existing_page_faq(
                page, target_id="faq-answer",
                explicit_opt_in=False, isolated_context_acknowledged=True,
            )
            assert skipped["status"] == "NOT_OBSERVED"
            assert skipped["action_performed"] is False
            assert page.content() == first
            observed = inspect_existing_page_faq(
                page, target_id="faq-answer",
                explicit_opt_in=True, isolated_context_acknowledged=True,
            )
            assert observed["status"] == "LOCAL_FAQ_ACTION_OBSERVED_NOT_ATTESTED"
            assert observed["before_state"] == "COLLAPSED_UNMOUNTED"
            assert observed["after_state"] == "EXPANDED_DOM_TEXT"
            assert observed["network_isolation_enforced_during_action"] is True
            assert observed["authenticated_collector_receipt"] is False
            assert observed["same_aud_sample_verified"] is False
            assert observed["crawler_discovery_verified"] is False
            assert observed["score_change_authorized"] is False
            assert observed["audit_writes"] == 0
            assert seen == [_URL]
            assert page.url == _URL
            page.set_content(
                '<form><button aria-controls="faq-answer" aria-expanded="false">'
                'Nao clicar</button></form>'
            )
            blocked = inspect_existing_page_faq(
                page, target_id="faq-answer", explicit_opt_in=True,
                isolated_context_acknowledged=True,
            )
            assert blocked["status"] == "NOT_OBSERVED"
            assert blocked["reason"] == "UNSAFE_FORM_CONTROL"
            assert page.locator("button").get_attribute("aria-expanded") == "false"
            context.close()
        finally:
            browser.close()
