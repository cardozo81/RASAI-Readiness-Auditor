"""Single-URL architecture diagnostic; never opens an audit workspace.

Both transports are bounded and use existing public-address checks. Browser
requests are limited to same-origin public destinations; deployments requiring
network-grade DNS rebinding protection must also enforce outbound filtering.
"""
from __future__ import annotations

import os

from rasai.architecture_probe import ProbeCaptures
from rasai.domain import DeviceContext
from rasai.rendering import DESKTOP_PROFILE, MOBILE_PROFILE
from rasai.search_intelligence.content import PublicWebFetcher, ContentFetchStatus, _validate_public_url, _default_resolver
from rasai.url_utils import normalize_url, normalized_origin


def capture_public_architecture(url: str, device: DeviceContext) -> ProbeCaptures:
    # An application-level DNS check does not prevent DNS rebinding between
    # resolution and connect. Explicit network-grade egress controls are required.
    # Until they are configured and verified, do not contact the target at all.
    if os.environ.get('RASAI_ARCH_PROBE_EGRESS_GUARDED') != '1':
        return ProbeCaptures(str(url), str(url), device, None, None, 'SAFE_EGRESS_NOT_CONFIGURED')
    target = _validate_public_url(normalize_url(url), _default_resolver)
    fetch = PublicWebFetcher(timeout_seconds=8.0, max_redirects=0, max_bytes=1_000_000)
    document = fetch.fetch(target)
    if document.status != ContentFetchStatus.OBSERVED or document.final_url != target:
        return ProbeCaptures(target, target, device, None, None, "HTTP_CAPTURE_UNAVAILABLE")
    if document.http_status is None or not 200 <= document.http_status < 300:
        return ProbeCaptures(target, target, device, None, None, "HTTP_STATUS_NOT_SUCCESSFUL")
    if "text/html" not in document.headers.get("content-type", "").lower():
        return ProbeCaptures(target, target, device, None, None, "NON_HTML_RESPONSE")
    raw = document.body.decode("utf-8", errors="replace")
    if len(raw) > 1_000_000:
        return ProbeCaptures(target, target, device, None, None, "RAW_HTML_LIMIT")

    # Same browser-device profiles as canonical audit rendering. Browser
    # navigation remains independent: no M2/M3/M6 or AUD persistence.
    from playwright.sync_api import Error as PlaywrightError, TimeoutError as PlaywrightTimeoutError, sync_playwright
    profile = DESKTOP_PROFILE if device is DeviceContext.DESKTOP else MOBILE_PROFILE
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                context = browser.new_context(**profile.context_options)
                try:
                    page = context.new_page()
                    requested = [0]
                    blocked = [0]
                    def guarded(route):
                        requested[0] += 1
                        if requested[0] > 30:
                            blocked[0] += 1
                            route.abort()
                            return
                        try:
                            candidate = _validate_public_url(route.request.url, _default_resolver)
                            if normalized_origin(candidate) != normalized_origin(target):
                                blocked[0] += 1
                                route.abort()
                            else:
                                route.continue_()
                        except (ValueError, OSError):
                            blocked[0] += 1
                            route.abort()
                    page.route("**/*", guarded)
                    response = page.goto(target, wait_until="domcontentloaded", timeout=12_000)
                    page.wait_for_timeout(350)
                    final_url = normalize_url(page.url)
                    if final_url != target or response is None or not 200 <= response.status < 300:
                        return ProbeCaptures(target, target, device, raw, None, "RENDER_NAVIGATION_NOT_ATTESTED")
                    rendered = page.content()
                    if blocked[0]:
                        return ProbeCaptures(target, target, device, raw, rendered, "BROWSER_REQUESTS_BLOCKED_OR_TRUNCATED")
                    if len(rendered) > 1_000_000:
                        return ProbeCaptures(target, target, device, raw, None, "RENDER_HTML_LIMIT")
                    return ProbeCaptures(target, target, device, raw, rendered)
                finally:
                    context.close()
            finally:
                browser.close()
    except (PlaywrightError, PlaywrightTimeoutError, OSError, ValueError):
        return ProbeCaptures(target, target, device, raw, None, "BROWSER_CAPTURE_UNAVAILABLE")
