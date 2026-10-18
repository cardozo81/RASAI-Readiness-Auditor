"""Conservative HTTP-only architecture discovery.

Static HTML provides signals but cannot prove that the DOM would remain
unchanged after JavaScript. Therefore it never fabricates a RAW/rendered pair
or labels the application STATIC_OR_SSR from a single network response.
"""
from __future__ import annotations

from rasai.architecture_public_html import public_html_failure
from rasai.architecture_probe import ProbeCaptures
from rasai.domain import DeviceContext
from rasai.geo_competitor_pinned_egress import PublicWebPinnedOpener
from rasai.search_intelligence.content import (
    ContentFetchStatus, PublicWebFetcher, _default_resolver, _validate_public_url,
)
from rasai.url_utils import normalize_url


def capture_static_public_architecture(url: str, device: DeviceContext) -> ProbeCaptures:
    if device not in (DeviceContext.MOBILE, DeviceContext.DESKTOP):
        raise ValueError("Unsupported device")
    try:
        target = _validate_public_url(normalize_url(url), _default_resolver)
    except (ValueError, OSError):
        return ProbeCaptures(url, url, device, None, None, "PUBLIC_TARGET_REJECTED")
    document = PublicWebFetcher(
        timeout_seconds=8.0, max_redirects=0, max_bytes=1_000_000,
        opener=PublicWebPinnedOpener(),
    ).fetch(target)
    reason = public_html_failure(document, target)
    if reason is None:
        # A valid RAW document is not proof of rendered DOM fidelity.
        return ProbeCaptures(
            target, target, device, document.body.decode("utf-8", errors="replace"),
            None, "STATIC_MODE_NO_RENDERED_DOM",
        )
    return ProbeCaptures(target, target, device, None, None, reason)
