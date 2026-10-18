"""Canonical, bounded public HTML acquisition and failure diagnostics.

Shared by static and OCI architecture acquisition. No browser or Docker code.
"""
from __future__ import annotations

from rasai.geo_competitor_pinned_egress import PublicWebPinnedOpener
from rasai.search_intelligence.content import (
    ContentFetchStatus, PublicWebFetcher, _validate_public_url, _default_resolver,
)
from rasai.url_utils import normalize_url


def public_html_failure(document, target: str) -> str | None:
    """Return a stable reason code; never expose URLs, response bodies or exceptions."""
    error = str(getattr(document, "error_code", "") or "")
    status = getattr(document, "http_status", None)
    if error == "TOO_MANY_REDIRECTS":
        return "PUBLIC_REDIRECT_NOT_FOLLOWED"
    if error == "CONTENT_BODY_LIMIT":
        return "PUBLIC_HTML_SIZE_LIMIT"
    if error == "CONTENT_TIMEOUT":
        return "PUBLIC_TIMEOUT"
    if error == "CONTENT_TLS_ERROR":
        return "PUBLIC_TLS_FAILURE"
    if error == "CONTENT_NETWORK_ERROR":
        return "PUBLIC_NETWORK_FAILURE"
    if document.status == ContentFetchStatus.BLOCKED:
        return "PUBLIC_DESTINATION_REJECTED"
    if document.status != ContentFetchStatus.OBSERVED:
        return "PUBLIC_TRANSPORT_UNAVAILABLE"
    if isinstance(status, int) and 300 <= status < 400:
        return "PUBLIC_REDIRECT_NOT_FOLLOWED"
    if status is None or not 200 <= status < 300:
        return "PUBLIC_HTTP_NOT_SUCCESS"
    if document.final_url != target:
        return "PUBLIC_FINAL_URL_MISMATCH"
    if "text/html" not in document.headers.get("content-type", "").lower():
        return "PUBLIC_RESPONSE_NOT_HTML"
    return None


def acquire_public_html(url: str):
    """Bounded pinned transport, one canonical redirect policy for both modes.

    Raises ValueError/OSError when target URL validation fails. Never follows
    arbitrary redirects or delegates network I/O to a Chromium host process.
    """
    target = _validate_public_url(normalize_url(url), _default_resolver)
    fetcher = PublicWebFetcher(
        timeout_seconds=8.0, max_redirects=0, max_bytes=1_000_000,
        opener=PublicWebPinnedOpener(),
    )
    return target, fetcher.fetch(target)
