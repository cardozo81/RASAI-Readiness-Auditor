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
            page.set_content(
                '<button type="button" aria-controls="faq-answer" '
                'aria-expanded="false" '
                'onclick="document.body.dataset.clicked=\'true\'">'
                'Nao executar handler inline</button>'
            )
            unsafe = inspect_existing_page_faq(
                page, target_id="faq-answer", explicit_opt_in=True,
                isolated_context_acknowledged=True,
            )
            assert unsafe["status"] == "NOT_OBSERVED"
            assert unsafe["reason"] == "UNSAFE_OR_AMBIGUOUS_FAQ_ACTION_TARGET"
            assert page.locator("body").get_attribute("data-clicked") is None
            assert page.locator("button").get_attribute("aria-expanded") == "false"
            page.set_content(
                '<button type="submit" aria-controls="faq-answer" '
                'aria-expanded="false">Nao submeter</button>'
            )
            submit = inspect_existing_page_faq(
                page, target_id="faq-answer", explicit_opt_in=True,
                isolated_context_acknowledged=True,
            )
            assert submit["status"] == "NOT_OBSERVED"
            assert submit["reason"] == "UNSAFE_OR_AMBIGUOUS_FAQ_ACTION_TARGET"
            assert page.locator("button").get_attribute("aria-expanded") == "false"
            context.close()
        finally:
            browser.close()



def test_late_mounted_spa_faq_is_observed_with_bounded_in_document_settle():
    """#601: a deferred DOM mount must not be missed after a safe click."""
    html = """<!doctype html><html><body>
<button type="button" aria-controls="faq-answer" aria-expanded="false">
O que cobre?</button><main id="slot"></main>
<script>
document.querySelector('button').addEventListener('click', () => {
    setTimeout(() => {
        document.querySelector('button').setAttribute('aria-expanded', 'true');
        document.getElementById('slot').innerHTML =
            '<section id="faq-answer"><p>Resposta carregada depois.</p></section>';
    }, 120);
});
</script></body></html>"""
    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            channel=os.environ.get("RASAI_322_CHROME_CHANNEL") or None,
            headless=True,
        )
        try:
            context = browser.new_context(service_workers="block")
            requests = []
            def fixture_route(route):
                requests.append(route.request.url)
                if route.request.url == _URL:
                    route.fulfill(status=200, content_type="text/html", body=html)
                else:
                    route.abort()
            context.route("**/*", fixture_route)
            page = context.new_page()
            page.goto(_URL, wait_until="load")
            observed = inspect_existing_page_faq(
                page, target_id="faq-answer",
                explicit_opt_in=True, isolated_context_acknowledged=True,
            )
            assert observed["status"] == "LOCAL_FAQ_ACTION_OBSERVED_NOT_ATTESTED"
            assert observed["before_state"] == "COLLAPSED_UNMOUNTED"
            assert observed["after_state"] == "EXPANDED_DOM_TEXT"
            assert observed["faq_settle_timed_out"] is False
            assert observed["faq_settle_timeout_ms"] == 900
            assert observed["before_utc"] < observed["after_utc"]
            assert observed["before_sha256"] != observed["after_sha256"]
            assert observed["crawler_discovery_verified"] is False
            assert observed["same_aud_sample_verified"] is False
            assert observed["authenticated_collector_receipt"] is False
            assert observed["score_change_authorized"] is False
            assert requests == [_URL]
            assert page.url == _URL
            context.close()
        finally:
            browser.close()


def test_delayed_faq_without_answer_does_not_claim_materialized_text():
    """#601: a bounded timeout is not proof of editorial absence."""
    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            channel=os.environ.get("RASAI_322_CHROME_CHANNEL") or None,
            headless=True,
        )
        try:
            context = browser.new_context(service_workers="block")
            context.route("**/*", lambda route: route.abort())
            page = context.new_page()
            page.set_content(
                '<button type="button" aria-controls="faq-answer" '
                'aria-expanded="false">Sem resposta</button>'
                '<script>document.querySelector("button").addEventListener('
                '"click", () => {document.querySelector("button").'
                'setAttribute("aria-expanded", "true");});</script>'
            )
            # about:blank has no verified physical page identity. The pilot
            # must decline before interacting, regardless of its DOM content.
            output = inspect_existing_page_faq(
                page, target_id="faq-answer",
                explicit_opt_in=True, isolated_context_acknowledged=True,
            )
            assert output["status"] == "NOT_OBSERVED"
            assert output["reason"] == "DOCUMENT_IDENTITY_UNVERIFIABLE"
            assert output["action_performed"] is False
            context.close()
        finally:
            browser.close()
