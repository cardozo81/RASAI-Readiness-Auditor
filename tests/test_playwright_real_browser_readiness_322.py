"""#322 physical offline Chromium evidence: not a production M23/M25 sample.

A single browser/context/page supplies navigation monotonic origin, its load
boundary, and the delayed DOM. Browser requests are blocked: no real site,
third-party API, credential, invoice, scoring, or audit state is involved.
"""
from __future__ import annotations

import os
import time

from playwright.sync_api import sync_playwright

from rasai.readiness_probe_cost_pilot_322 import measure_existing_playwright_probe_cost

BODY = " ".join(["Cobertura, condições e benefícios da apólice verificáveis."] * 10)


def _headless_browser(playwright):
    # GitHub ubuntu-latest image contains Google Chrome already. CI sets an
    # explicit channel, avoiding browser/apt downloads and network-dependent
    # install delays. Local environments can use their normal Playwright build.
    return playwright.chromium.launch(
        channel=os.environ.get("RASAI_322_CHROME_CHANNEL") or None,
        headless=True,
    )


def _pilot(page, *, architecture="CSR_SPA", enabled=True, window_ms=1500):
    origin_ns = time.monotonic_ns()
    page.set_content(
        """<html><head><title>Offline readiness</title></head><body>
        <main id="principal" aria-busy="true">
          <h1>Carregando informações</h1>
          <div class="skeleton" data-loading="true">Carregando</div>
        </main>
        <script>
         window.setTimeout(() => {
            const main = document.getElementById('principal');
            main.removeAttribute('aria-busy');
            main.innerHTML = '<h1>Seguro de vida acessível</h1><p>"""
        + BODY +
        """</p>';
         }, 280);
        </script></body></html>""",
        wait_until="load",
    )
    load_ms = (time.monotonic_ns() - origin_ns) / 1e6
    return measure_existing_playwright_probe_cost(
        page=page, sample_id="PILOT-LOAD-001", context_id="CTX-CHROMIUM-001",
        page_id="PAGE-OFFLINE-001", device="MOBILE",
        architecture=architecture,
        navigation_started_monotonic_ns=origin_ns, load_ms=load_ms,
        enabled=enabled, window_ms=window_ms, poll_ms=125,
        evaluation_budget_ms=150,
    )


def test_real_offline_chromium_same_page_load_then_late_spa_content():
    with sync_playwright() as playwright:
        browser = _headless_browser(playwright)
        try:
            context = browser.new_context(service_workers="block")
            # Offline fixture: network requests are explicitly rejected, and
            # the adapter itself has no capability to navigate/fetch.
            requested = []
            context.route("**/*", lambda route: (
                requested.append(route.request.url), route.abort()
            ))
            page = context.new_page()
            result = _pilot(page)
            assert result.observation.status == "OBSERVED"
            assert result.observation.primary_content_ms is not None
            assert result.observation.primary_content_ms >= result.observation.load_ms
            assert result.observation.post_load_delta_ms is not None
            assert result.observation.post_load_delta_ms >= 0
            assert result.number_of_dom_evaluations >= 2
            assert result.total_dom_evaluation_ms >= 0
            assert result.elapsed_probe_wall_ms >= result.total_dom_evaluation_ms
            assert result.integration_gate in {
                "PILOT_ONLY_REQUIRES_MATCHED_BASELINE_AND_GATEWAY_IDENTITY",
                "BLOCKED_BY_LOCAL_DOM_OVERHEAD",
            }
            assert result.identity_proof == "CALLER_DECLARED_NOT_ATTESTED_BY_M25"
            assert requested == []
            assert page.is_closed() is False
            context.close()
        finally:
            browser.close()


def test_real_offline_chromium_aria_hidden_bootstrap_never_proves_readiness():
    with sync_playwright() as playwright:
        browser = _headless_browser(playwright)
        try:
            context = browser.new_context(service_workers="block")
            context.route("**/*", lambda route: route.abort())
            page = context.new_page()
            origin = time.monotonic_ns()
            page.set_content(
                "<main><div aria-hidden='true'><h1>Oferta pronta</h1><p>"
                + BODY + "</p></div></main>",
                wait_until="load",
            )
            load_ms = (time.monotonic_ns() - origin) / 1e6
            result = measure_existing_playwright_probe_cost(
                page=page, sample_id="PILOT-LOAD-002", context_id="CTX-002",
                page_id="PAGE-002", device="MOBILE", architecture="HYDRATED",
                navigation_started_monotonic_ns=origin, load_ms=load_ms,
                enabled=True, window_ms=300, poll_ms=100,
                evaluation_budget_ms=150,
            )
            assert result.observation.status == "TIMEOUT"
            assert result.observation.primary_content_ms is None
            assert result.observation.post_load_delta_ms is None
            assert result.number_of_dom_evaluations > 0
            context.close()
        finally:
            browser.close()


def test_real_offline_chromium_ssr_opt_out_zero_dom_overhead():
    with sync_playwright() as playwright:
        browser = _headless_browser(playwright)
        try:
            context = browser.new_context(service_workers="block")
            page = context.new_page()
            origin = time.monotonic_ns()
            page.set_content("<main><h1>Documento estático</h1><p>" + BODY + "</p></main>")
            load_ms = (time.monotonic_ns() - origin) / 1e6
            result = measure_existing_playwright_probe_cost(
                page=page, sample_id="PILOT-SSR", context_id="CTX-SSR",
                page_id="PAGE-SSR", device="MOBILE", architecture="STATIC_OR_SSR",
                navigation_started_monotonic_ns=origin, load_ms=load_ms,
                enabled=True, evaluation_budget_ms=150,
            )
            assert result.observation.status == "NOT_APPLICABLE"
            assert result.number_of_dom_evaluations == 0
            assert result.local_evaluation_budget_met is None
            context.close()
        finally:
            browser.close()
