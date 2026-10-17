"""Single-URL architecture diagnostic; never opens an audit workspace.

HTTP requests are fulfilled only through a pinned-IP, public-only transport.
Chromium may still originate native WebRTC or other non-HTTP traffic, so an
independent network-grade egress policy remains mandatory for live capture.
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
    max_total_bytes: int = 3_000_000,
    initial_document: Any = None,
    resource_fetcher: Any = None,
) -> BrowserRequestGate:
    """Serve same-origin GETs through pinned HTTP, never native browser sockets.

    All ordinary HTTP requests, including the first popup request, must be
    fulfilled from the validated Python transport. No route.continue_ or
    route.fetch is allowed: both could bypass the pinned destination policy.
    WebSocket is denied. This does NOT isolate WebRTC/native Chromium traffic,
    so physical capture still requires an independently protected environment.
    """
    if max_requests <= 0 or max_total_bytes <= 0:
        raise ValueError("Browser request and byte budgets must be positive")
    gate = BrowserRequestGate()
    fetched_bytes = [0]
    pinned_fetcher = resource_fetcher or PublicWebFetcher(
        timeout_seconds=4.0,
        max_redirects=0,
        max_bytes=min(500_000, max_total_bytes),
        opener=PublicWebPinnedOpener(resolver=resolver),
    )

    def deny(route: Any) -> None:
        gate.blocked += 1
        route.abort()

    def guarded_http(route: Any) -> None:
        gate.requested += 1
        if gate.requested > max_requests or route.request.method != "GET":
            deny(route)
            return
        try:
            candidate = _validate_public_url(route.request.url, resolver)
            if normalized_origin(candidate) != normalized_origin(target):
                deny(route)
                return
            # Keep the raw page and browser document on the same HTTP evidence
            # snapshot; do not fetch an unobserved second root response.
            evidence = (
                initial_document
                if initial_document is not None and candidate == target
                else pinned_fetcher.fetch(candidate)
            )
            if (
                evidence.status != ContentFetchStatus.OBSERVED
                or evidence.final_url != candidate
                or evidence.http_status is None
                or not 200 <= evidence.http_status < 300
            ):
                deny(route)
                return
            body = evidence.body
            if not isinstance(body, bytes) or fetched_bytes[0] + len(body) > max_total_bytes:
                deny(route)
                return
            content_type = evidence.headers.get("content-type", "")
            if not content_type or "\r" in content_type or "\n" in content_type:
                deny(route)
                return
            # Exclude set-cookie, location, encoding/length and transport
            # headers. Retain CSP/other response policy where applicable.
            headers = {"content-type": content_type}
            for header in (
                "content-security-policy", "x-content-type-options",
                "cross-origin-resource-policy", "cross-origin-opener-policy",
                "cross-origin-embedder-policy", "referrer-policy",
            ):
                value = evidence.headers.get(header, "")
                if value and "\r" not in value and "\n" not in value:
                    headers[header] = value
            fetched_bytes[0] += len(body)
            route.fulfill(status=evidence.http_status, body=body, headers=headers)
        except (ValueError, OSError):
            deny(route)

    def guarded_websocket(socket_route: Any) -> None:
        gate.blocked += 1
        socket_route.close()

    # Context routes are installed before page creation. The browser must
    # never perform routine HTTP egress, even when Chromium DNS rebinding occurs.
    context.route("**/*", guarded_http)
    context.route_web_socket("**/*", guarded_websocket)
    return gate


def capture_public_architecture(url: str, device: DeviceContext) -> ProbeCaptures:
    """Safe default: never launch network-capable Chromium in the host process.

    The old EGRESS_GUARDED flag is intentionally insufficient. The explicitly
    installed OCI renderer enforces --network none for the browser.
    """
    if os.environ.get("RASAI_ARCH_PROBE_OFFLINE_CONTAINER") == "1":
        from rasai.architecture_isolated_capture import capture_isolated_public_architecture
        return capture_isolated_public_architecture(url, device)
    return ProbeCaptures(str(url), str(url), device, None, None, "SAFE_EGRESS_NOT_CONFIGURED")
