"""Single-URL architecture diagnostic; never opens an audit workspace.

Both transports are bounded and use existing public-address checks. Browser
requests are limited to same-origin public destinations; deployments requiring
network-grade DNS rebinding protection must also enforce outbound filtering.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Callable

from rasai.geo_competitor_pinned_egress import PublicWebPinnedOpener
from rasai.architecture_probe import ProbeCaptures
from rasai.domain import DeviceContext
from rasai.rendering import DESKTOP_PROFILE, MOBILE_PROFILE
from rasai.search_intelligence.content import PublicWebFetcher, ContentFetchStatus, _validate_public_url, _default_resolver
from rasai.url_utils import normalize_url, normalized_origin


@dataclass(slots=True)
class BrowserRequestGate:
    """Request counters are evidence limits, not a host/network firewall."""
    requested: int = 0
    blocked: int = 0


def install_architecture_browser_routes(
    context: Any,
    target: str,
    *,
    resolver: Callable[..., Any] = _default_resolver,
    max_requests: int = 30,
) -> BrowserRequestGate:
    """Route every page (including first popup requests) before navigation.

    No WebSocket may reach a server, and only same-origin public GETs can be
    delegated to the *separately network-isolated* browser. This does NOT pin
    browser DNS connections and cannot replace network-grade egress isolation.
    """
    gate = BrowserRequestGate()

    def blocked_http(route: Any) -> None:
        gate.blocked += 1
        route.abort()

    def guarded_http(route: Any) -> None:
        gate.requested += 1
        if gate.requested > max_requests or route.request.method != "GET":
            blocked_http(route)
            return
        try:
            candidate = _validate_public_url(route.request.url, resolver)
            if normalized_origin(candidate) != normalized_origin(target):
                blocked_http(route)
                return
        except (ValueError, OSError):
            blocked_http(route)
            return
        route.continue_()

    def guarded_websocket(socket_route: Any) -> None:
        gate.blocked += 1
        # Do not call connect(): the socket stays entirely in the browser.
        socket_route.close()

    # page.route() misses the first request of a popup. Context-wide routing
    # covers all ordinary HTTP requests of the isolated browser context.
    context.route("**/*", guarded_http)
    context.route_web_socket("**/*", guarded_websocket)
    return gate



def capture_public_architecture(url: str, device: DeviceContext) -> ProbeCaptures:
    # An application-level DNS check does not prevent DNS rebinding between
    # resolution and connect. Explicit network-grade egress controls are required.
    # Until they are configured and verified, do not contact the target at all.
    if os.environ.get('RASAI_ARCH_PROBE_EGRESS_GUARDED') != '1':
        return ProbeCaptures(str(url), str(url), device, None, None, 'SAFE_EGRESS_NOT_CONFIGURED')
    target = _validate_public_url(normalize_url(url), _default_resolver)
    fetch = PublicWebFetcher(timeout_seconds=8.0, max_redirects=0, max_bytes=1_000_000, opener=PublicWebPinnedOpener())
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
                context = browser.new_context(**profile.context_options, service_workers='block')
                try:
                    # Install guards before creating any page; popups and
                    # WebSockets must not escape page-local request routing.
                    gate = install_architecture_browser_routes(context, target)
                    page = context.new_page()
                    response = page.goto(target, wait_until="domcontentloaded", timeout=12_000)
                    # Match the bounded wait used by the audit renderer.
                    # A fixed 350 ms delay can miss ordinary client hydration.
                    try:
                        page.wait_for_load_state("networkidle", timeout=2_000)
                    except PlaywrightTimeoutError:
                        pass
                    final_url = normalize_url(page.url)
                    if final_url != target or response is None or not 200 <= response.status < 300:
                        return ProbeCaptures(target, target, device, raw, None, "RENDER_NAVIGATION_NOT_ATTESTED")
                    rendered = page.content()
                    if gate.blocked:
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
