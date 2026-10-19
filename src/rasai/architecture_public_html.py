"""Canonical, bounded public HTML acquisition and failure diagnostics.

Shared by static and OCI architecture acquisition. No browser or Docker code.
"""
from __future__ import annotations

from rasai.geo_competitor_pinned_egress import PublicWebPinnedOpener
from rasai.search_intelligence.content import (
    ContentFetchStatus, PublicWebFetcher, _validate_public_url, _default_resolver,
)
from rasai.url_utils import normalize_url
from urllib.parse import urlsplit


def verified_public_redirect_chain(
    requested: str, final: str, redirects: tuple[str, ...] | list[str],
) -> bool:
    """Accept at most two canonical public, host-related redirects.

    Public-IP eligibility, pinned DNS/egress and TLS are enforced by the
    transport per hop. This pure guard prevents treating unrelated public
    destinations, HTTPS downgrade or an unbound final page as same-target
    architectural evidence. It does not request either endpoint.
    """
    if not isinstance(redirects, (tuple, list)) or not 1 <= len(redirects) <= 2:
        return False
    chain = (requested, *redirects)
    if chain[-1] != final or len(set(chain)) != len(chain):
        return False
    try:
        if any(normalize_url(url) != url for url in chain):
            return False
        base = urlsplit(requested)
        original_host = (base.hostname or "").lower()
        canonical = original_host.removeprefix("www.")
        if not original_host or base.scheme not in {"http", "https"}:
            return False
        for previous_url, current_url in zip(chain, chain[1:]):
            previous, current = urlsplit(previous_url), urlsplit(current_url)
            host = (current.hostname or "").lower()
            if (host.removeprefix("www.") != canonical
                    or current.scheme not in {"http", "https"}
                    or (previous.scheme == "https" and current.scheme != "https")
                    or current.username is not None or current.password is not None):
                return False
    except (ValueError, TypeError):
        return False
    return True


def public_html_failure(document, target: str) -> str | None:
    """Return a stable reason code; never expose URLs, response bodies or exceptions."""
    error = str(getattr(document, "error_code", "") or "")
    status = getattr(document, "http_status", None)
    if error == "TOO_MANY_REDIRECTS":
        return "PUBLIC_REDIRECT_NOT_FOLLOWED"
    if error in {"REDIRECT_LOOP", "INVALID_REDIRECT"}:
        return "PUBLIC_REDIRECT_UNVERIFIABLE"
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
    if document.final_url != target and not verified_public_redirect_chain(
        target, document.final_url, getattr(document, "redirects", ()),
    ):
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
        timeout_seconds=8.0, max_redirects=2, max_bytes=1_000_000,
        opener=PublicWebPinnedOpener(),
    )
    return target, fetcher.fetch(target)
