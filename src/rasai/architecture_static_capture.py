"""Conservative HTTP-only architecture discovery.

Static HTML provides signals but cannot prove that the DOM would remain
unchanged after JavaScript. Therefore it never fabricates a RAW/rendered pair
or labels the application STATIC_OR_SSR from a single network response.
"""
from __future__ import annotations

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
    error = getattr(document, "error_code", None)
    if error == "TOO_MANY_REDIRECTS":
        reason = "PUBLIC_REDIRECT_NOT_FOLLOWED"
    elif error == "CONTENT_BODY_LIMIT":
        reason = "PUBLIC_HTML_SIZE_LIMIT"
    elif document.status == ContentFetchStatus.BLOCKED:
        reason = "PUBLIC_DESTINATION_REJECTED"
    elif document.status != ContentFetchStatus.OBSERVED:
        reason = "PUBLIC_TRANSPORT_UNAVAILABLE"
    elif document.http_status is None or not 200 <= document.http_status < 300:
        reason = "PUBLIC_HTTP_NOT_SUCCESS"
    elif document.final_url != target:
        reason = "PUBLIC_FINAL_URL_MISMATCH"
    elif "text/html" not in document.headers.get("content-type", "").lower():
        reason = "PUBLIC_RESPONSE_NOT_HTML"
    else:
        # A valid RAW document is useful evidence, but cannot certify the
        # architecture class without an independently rendered DOM.
        return ProbeCaptures(
            target, target, device, document.body.decode("utf-8", errors="replace"),
            None, "STATIC_MODE_NO_RENDERED_DOM",
        )
    return ProbeCaptures(target, target, device, None, None, reason)
