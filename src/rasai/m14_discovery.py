"""Explicit URL-set discovery for M14.

URL_SET mode audits exactly the normalized URLs supplied by the operator.  It
still acquires robots.txt and sitemap resources once for the shared origin, but
those resources do not expand the explicit page set.
"""

from __future__ import annotations

from rasai.discovery import (
    DiscoveredPage,
    DiscoveryEngine,
    DiscoveryProvenance,
    DiscoveryResult,
    RobotsResult,
    RobotsState,
    SitemapResult,
    SitemapState,
)
from rasai.domain import DiscoverySource
from rasai.url_utils import is_same_origin, normalize_url, normalized_origin


def discover_url_set(
    engine: DiscoveryEngine,
    urls: tuple[str, ...],
    *,
    max_pages: int,
) -> DiscoveryResult:
    if not urls:
        raise ValueError("URL_SET requires at least one URL")
    if max_pages <= 0:
        raise ValueError("max_pages must be greater than zero")

    normalized = tuple(dict.fromkeys(normalize_url(url) for url in urls))
    if len(normalized) > max_pages:
        raise ValueError(
            f"explicit URL set contains {len(normalized)} unique URLs but --max-pages is {max_pages}; "
            "increase --max-pages so no supplied URL is silently omitted"
        )

    origin = normalized_origin(normalized[0])
    incompatible = [url for url in normalized if normalized_origin(url) != origin]
    if incompatible:
        raise ValueError(
            "all explicit URLs must belong to the same normalized origin; "
            f"expected {origin}, got {normalized_origin(incompatible[0])}"
        )

    robots_url = normalize_url("/robots.txt", base_url=f"{origin}/")
    robots_acquisition = engine.http_client.acquire(robots_url)
    robots_state, robots_parser, declared_sitemaps = engine._interpret_robots(  # noqa: SLF001
        robots_url,
        robots_acquisition,
        origin,
    )

    default_sitemap = normalize_url("/sitemap.xml", base_url=f"{origin}/")
    sitemap_queue: list[str] = []
    sitemap_seen: set[str] = set()
    for sitemap_url in (*declared_sitemaps, default_sitemap):
        if sitemap_url not in sitemap_seen and is_same_origin(sitemap_url, origin):
            sitemap_seen.add(sitemap_url)
            sitemap_queue.append(sitemap_url)

    sitemap_results: list[SitemapResult] = []
    index = 0
    while index < len(sitemap_queue):
        sitemap_url = sitemap_queue[index]
        index += 1
        result = engine._acquire_sitemap(sitemap_url, origin)  # noqa: SLF001
        sitemap_results.append(result)
        if result.state is not SitemapState.OBTAINED:
            continue
        for child in result.child_sitemaps:
            if child not in sitemap_seen and is_same_origin(child, origin):
                sitemap_seen.add(child)
                sitemap_queue.append(child)

    pages: list[DiscoveredPage] = []
    provenance: list[DiscoveryProvenance] = []
    page_acquisitions = {}
    for position, url in enumerate(normalized):
        source = DiscoverySource.SEED if position == 0 else DiscoverySource.MANUAL
        pages.append(
            DiscoveredPage(
                normalized_url=url,
                discovered_url=url,
                discovery_sources=(source,),
                depth=0,
                internal_references=0,
            )
        )
        provenance.append(
            DiscoveryProvenance(
                target_url=url,
                source=source,
                source_url=None,
                discovered_url=url,
            )
        )
        page_acquisitions[url] = engine.http_client.acquire(url)

    crawler_access: dict[str, dict[str, bool | None]] = {}
    for url in normalized:
        if robots_state is RobotsState.OBTAINED and robots_parser is not None:
            crawler_access[url] = {
                crawler: bool(robots_parser.can_fetch(crawler, url))
                for crawler in engine.crawlers
            }
        elif robots_state is RobotsState.ABSENT:
            crawler_access[url] = {crawler: True for crawler in engine.crawlers}
        else:
            crawler_access[url] = {crawler: None for crawler in engine.crawlers}

    robots = RobotsResult(
        url=robots_url,
        state=robots_state,
        acquisition=robots_acquisition,
        sitemap_urls=tuple(declared_sitemaps),
        crawler_access=crawler_access,
    )

    return DiscoveryResult(
        origin=origin,
        pages=tuple(pages),
        page_acquisitions=page_acquisitions,
        provenance=tuple(provenance),
        robots=robots,
        sitemaps=tuple(sitemap_results),
        total_discovered=len(pages),
        total_audited=len(pages),
        max_pages=max_pages,
        limit_reached=False,
    )
