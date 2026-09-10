"""M24 additive discovery extensions.

Installed by ``cli_extensions`` before the legacy audit starts. The extension keeps
M2's public dataclasses stable while expanding sitemap formats, preserving
cross-origin sitemap declarations without fetching arbitrary origins, and installing
bounded llms.txt v2 discovery for root/scoped files explicitly advertised by the site.
"""
from __future__ import annotations

import gzip
from io import BytesIO
from urllib import robotparser
import xml.etree.ElementTree as ET

from rasai.discovery import (
    DiscoveryEngine,
    RobotsState,
    SitemapResult,
    SitemapState,
)
from rasai.url_utils import is_same_origin, normalize_url

MAX_SITEMAP_BYTES = 50 * 1024 * 1024
MAX_SITEMAP_URLS = 50_000


def install_discovery_extensions() -> None:
    """Install sitemap and llms.txt discovery extensions idempotently."""
    if not getattr(DiscoveryEngine, "_m24_extensions_installed", False):
        DiscoveryEngine._interpret_robots = _interpret_robots_m24  # type: ignore[method-assign]
        DiscoveryEngine._acquire_sitemap = _acquire_sitemap_m24  # type: ignore[method-assign]
        DiscoveryEngine._m24_extensions_installed = True  # type: ignore[attr-defined]

    # Keep this outside the guard above. Test/process ordering can leave the
    # DiscoveryEngine patch installed while the separate M24 analyzer has not yet
    # been imported. The llms installer has its own idempotency guard.
    from rasai.m24_llms_discovery import install_llms_discovery_patch

    install_llms_discovery_patch()


def _interpret_robots_m24(
    self: DiscoveryEngine,
    robots_url: str,
    acquisition,
    origin: str,
):
    """Preserve valid sitemap declarations regardless of host.

    Discovery still fetches only same-origin sitemap URLs because the existing
    queue applies ``is_same_origin``. This preserves standards-valid declarations
    while avoiding an implicit cross-origin/SSRF expansion of the audit.
    """
    if acquisition.network_error is not None:
        return RobotsState.NETWORK_ERROR, None, ()
    if acquisition.status in {404, 410}:
        return RobotsState.ABSENT, None, ()
    if acquisition.status is None or not 200 <= acquisition.status <= 299:
        return RobotsState.HTTP_ERROR, None, ()

    parser = robotparser.RobotFileParser()
    parser.set_url(robots_url)
    parser.parse(acquisition.body.decode("utf-8", errors="replace").splitlines())
    raw_sitemaps = parser.site_maps() or []
    normalized_sitemaps: list[str] = []
    for raw_sitemap in raw_sitemaps:
        try:
            sitemap = normalize_url(raw_sitemap, base_url=robots_url)
        except ValueError:
            continue
        if sitemap not in normalized_sitemaps:
            normalized_sitemaps.append(sitemap)
    return RobotsState.OBTAINED, parser, tuple(normalized_sitemaps)


def _acquire_sitemap_m24(
    self: DiscoveryEngine,
    sitemap_url: str,
    origin: str,
) -> SitemapResult:
    acquisition = self.http_client.acquire(sitemap_url)
    if acquisition.network_error is not None:
        return SitemapResult(sitemap_url, SitemapState.NETWORK_ERROR, acquisition)
    if acquisition.status in {404, 410}:
        return SitemapResult(sitemap_url, SitemapState.ABSENT, acquisition)
    if acquisition.status is None or not 200 <= acquisition.status <= 299:
        return SitemapResult(sitemap_url, SitemapState.HTTP_ERROR, acquisition)

    payload = acquisition.body
    content_type = (acquisition.header("Content-Type") or "").casefold()
    if sitemap_url.casefold().endswith(".gz") or "gzip" in content_type:
        try:
            payload = gzip.GzipFile(fileobj=BytesIO(payload)).read(MAX_SITEMAP_BYTES + 1)
        except OSError as exc:
            return SitemapResult(
                sitemap_url,
                SitemapState.INVALID,
                acquisition,
                error=f"invalid gzip sitemap: {exc}",
            )
    if len(payload) > MAX_SITEMAP_BYTES:
        return SitemapResult(
            sitemap_url,
            SitemapState.INVALID,
            acquisition,
            error="sitemap exceeds 50 MB uncompressed limit",
        )

    stripped = payload.lstrip(b"\xef\xbb\xbf \t\r\n")
    if _looks_like_text_sitemap(sitemap_url, content_type, stripped):
        urls, invalid_count = _parse_text_urls(payload, sitemap_url, origin)
        if len(urls) > MAX_SITEMAP_URLS:
            return SitemapResult(
                sitemap_url,
                SitemapState.INVALID,
                acquisition,
                error="text sitemap exceeds 50,000 URL limit",
            )
        error = f"ignored {invalid_count} invalid/non-http/cross-origin URL line(s)" if invalid_count else None
        return SitemapResult(
            sitemap_url,
            SitemapState.OBTAINED,
            acquisition,
            page_urls=tuple(urls),
            error=error,
        )

    try:
        root = ET.fromstring(payload)
    except ET.ParseError as exc:
        return SitemapResult(
            sitemap_url,
            SitemapState.INVALID,
            acquisition,
            error=f"invalid sitemap/feed XML: {exc}",
        )

    root_name = _local_name(root.tag)
    if root_name == "urlset":
        urls = _xml_urlset_urls(root, sitemap_url, origin)
        if len(urls) > MAX_SITEMAP_URLS:
            return SitemapResult(
                sitemap_url,
                SitemapState.INVALID,
                acquisition,
                error="XML sitemap exceeds 50,000 URL limit",
            )
        return SitemapResult(
            sitemap_url,
            SitemapState.OBTAINED,
            acquisition,
            page_urls=tuple(urls),
        )
    if root_name == "sitemapindex":
        children = _xml_index_urls(root, sitemap_url, origin)
        if len(children) > MAX_SITEMAP_URLS:
            return SitemapResult(
                sitemap_url,
                SitemapState.INVALID,
                acquisition,
                error="sitemap index exceeds 50,000 loc limit",
            )
        return SitemapResult(
            sitemap_url,
            SitemapState.OBTAINED,
            acquisition,
            child_sitemaps=tuple(children),
        )
    if root_name == "rss":
        urls = _rss_urls(root, sitemap_url, origin)
        return SitemapResult(
            sitemap_url,
            SitemapState.OBTAINED,
            acquisition,
            page_urls=tuple(urls[:MAX_SITEMAP_URLS]),
            error="RSS feed truncated at 50,000 URLs" if len(urls) > MAX_SITEMAP_URLS else None,
        )
    if root_name == "feed":
        urls = _atom_urls(root, sitemap_url, origin)
        return SitemapResult(
            sitemap_url,
            SitemapState.OBTAINED,
            acquisition,
            page_urls=tuple(urls[:MAX_SITEMAP_URLS]),
            error="Atom feed truncated at 50,000 URLs" if len(urls) > MAX_SITEMAP_URLS else None,
        )
    return SitemapResult(
        sitemap_url,
        SitemapState.INVALID,
        acquisition,
        error=f"unsupported sitemap/feed root element: {root_name}",
    )


def _looks_like_text_sitemap(url: str, content_type: str, stripped: bytes) -> bool:
    if stripped.startswith(b"<"):
        return False
    return url.casefold().split("?", 1)[0].endswith(".txt") or "text/plain" in content_type


def _parse_text_urls(payload: bytes, base_url: str, origin: str) -> tuple[list[str], int]:
    text = payload.decode("utf-8-sig", errors="replace")
    urls: list[str] = []
    seen: set[str] = set()
    invalid = 0
    for line in text.splitlines():
        raw = line.strip()
        if not raw:
            continue
        try:
            normalized = normalize_url(raw, base_url=base_url)
        except ValueError:
            invalid += 1
            continue
        if not is_same_origin(normalized, origin):
            invalid += 1
            continue
        if normalized not in seen:
            seen.add(normalized)
            urls.append(normalized)
    return urls, invalid


def _xml_urlset_urls(root: ET.Element, base_url: str, origin: str) -> list[str]:
    values: list[str] = []
    for url_node in list(root):
        if _local_name(url_node.tag) != "url":
            continue
        loc = next(
            (
                (child.text or "").strip()
                for child in list(url_node)
                if _local_name(child.tag) == "loc" and (child.text or "").strip()
            ),
            "",
        )
        _append_same_origin(values, loc, base_url, origin)
    return values


def _xml_index_urls(root: ET.Element, base_url: str, origin: str) -> list[str]:
    values: list[str] = []
    for sitemap_node in list(root):
        if _local_name(sitemap_node.tag) != "sitemap":
            continue
        loc = next(
            (
                (child.text or "").strip()
                for child in list(sitemap_node)
                if _local_name(child.tag) == "loc" and (child.text or "").strip()
            ),
            "",
        )
        _append_same_origin(values, loc, base_url, origin)
    return values


def _rss_urls(root: ET.Element, base_url: str, origin: str) -> list[str]:
    values: list[str] = []
    for node in root.iter():
        if _local_name(node.tag) != "item":
            continue
        for child in list(node):
            if _local_name(child.tag) == "link" and (child.text or "").strip():
                _append_same_origin(values, (child.text or "").strip(), base_url, origin)
                break
    return values


def _atom_urls(root: ET.Element, base_url: str, origin: str) -> list[str]:
    values: list[str] = []
    for node in root.iter():
        if _local_name(node.tag) != "entry":
            continue
        for child in list(node):
            if _local_name(child.tag) != "link":
                continue
            rel = (child.attrib.get("rel") or "alternate").casefold()
            href = (child.attrib.get("href") or "").strip()
            if rel in {"", "alternate"} and href:
                _append_same_origin(values, href, base_url, origin)
                break
    return values


def _append_same_origin(values: list[str], raw: str, base_url: str, origin: str) -> None:
    if not raw:
        return
    try:
        normalized = normalize_url(raw, base_url=base_url)
    except ValueError:
        return
    if is_same_origin(normalized, origin) and normalized not in values:
        values.append(normalized)


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].casefold()
