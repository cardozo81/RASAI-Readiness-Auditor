"""Deterministic seed/sitemap/internal-link discovery for M2."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
import gzip
from html.parser import HTMLParser
from io import BytesIO
from urllib import robotparser
import xml.etree.ElementTree as ET

from rasai.acquisition import HttpAcquisitionResult, HttpClient, decode_body
from rasai.domain import DiscoverySource
from rasai.url_utils import is_same_origin, normalize_url, normalized_origin, resolve_http_url


DEFAULT_CRAWLERS = (
    "Googlebot",
    "Googlebot Smartphone",
    "Bingbot",
    "OAI-SearchBot",
    "GPTBot",
)


class RobotsState(StrEnum):
    OBTAINED = "OBTAINED"
    ABSENT = "ABSENT"
    HTTP_ERROR = "HTTP_ERROR"
    NETWORK_ERROR = "NETWORK_ERROR"


class SitemapState(StrEnum):
    OBTAINED = "OBTAINED"
    ABSENT = "ABSENT"
    HTTP_ERROR = "HTTP_ERROR"
    NETWORK_ERROR = "NETWORK_ERROR"
    INVALID = "INVALID"


@dataclass(frozen=True, slots=True)
class DiscoveryProvenance:
    target_url: str
    source: DiscoverySource
    source_url: str | None
    discovered_url: str


@dataclass(frozen=True, slots=True)
class DiscoveredPage:
    normalized_url: str
    discovered_url: str
    discovery_sources: tuple[DiscoverySource, ...]
    depth: int
    internal_references: int


@dataclass(frozen=True, slots=True)
class RobotsResult:
    url: str
    state: RobotsState
    acquisition: HttpAcquisitionResult
    sitemap_urls: tuple[str, ...]
    crawler_access: dict[str, dict[str, bool | None]]


@dataclass(frozen=True, slots=True)
class SitemapResult:
    url: str
    state: SitemapState
    acquisition: HttpAcquisitionResult
    page_urls: tuple[str, ...] = ()
    child_sitemaps: tuple[str, ...] = ()
    error: str | None = None


@dataclass(frozen=True, slots=True)
class DiscoveryResult:
    origin: str
    pages: tuple[DiscoveredPage, ...]
    page_acquisitions: dict[str, HttpAcquisitionResult]
    provenance: tuple[DiscoveryProvenance, ...]
    robots: RobotsResult
    sitemaps: tuple[SitemapResult, ...]
    total_discovered: int
    total_audited: int
    max_pages: int
    limit_reached: bool


@dataclass(slots=True)
class _Candidate:
    normalized_url: str
    discovered_url: str
    depth: int
    sources: set[DiscoverySource] = field(default_factory=set)
    internal_references: int = 0


class _LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.casefold() != "a":
            return
        for key, value in attrs:
            if key.casefold() == "href" and value is not None:
                self.hrefs.append(value)
                break


class DiscoveryEngine:
    """Discover and acquire the bounded M2 page universe."""

    _SOURCE_PRIORITY = {
        DiscoverySource.SEED: 0,
        DiscoverySource.SITEMAP: 1,
        DiscoverySource.INTERNAL_LINK: 2,
        DiscoverySource.REDIRECT: 3,
        DiscoverySource.MANUAL: 4,
    }

    def __init__(
        self,
        http_client: HttpClient | None = None,
        *,
        crawlers: tuple[str, ...] = DEFAULT_CRAWLERS,
    ) -> None:
        self.http_client = http_client or HttpClient()
        self.crawlers = crawlers

    def discover(self, seed_url: str, *, max_pages: int) -> DiscoveryResult:
        if max_pages <= 0:
            raise ValueError("max_pages must be greater than zero")

        seed = normalize_url(seed_url)
        origin = normalized_origin(seed)
        candidates: dict[str, _Candidate] = {}
        provenance: list[DiscoveryProvenance] = []
        provenance_keys: set[tuple[str, DiscoverySource, str | None, str]] = set()

        def add_candidate(
            discovered_url: str,
            source: DiscoverySource,
            *,
            source_url: str | None,
            depth: int,
            reference_increment: int = 0,
        ) -> str | None:
            try:
                normalized = normalize_url(discovered_url)
            except ValueError:
                return None
            if not is_same_origin(normalized, origin):
                return None
            candidate = candidates.get(normalized)
            if candidate is None:
                candidate = _Candidate(
                    normalized_url=normalized,
                    discovered_url=discovered_url,
                    depth=depth,
                )
                candidates[normalized] = candidate
            else:
                candidate.depth = min(candidate.depth, depth)
            candidate.sources.add(source)
            candidate.internal_references += reference_increment
            key = (normalized, source, source_url, discovered_url)
            if key not in provenance_keys:
                provenance_keys.add(key)
                provenance.append(
                    DiscoveryProvenance(
                        target_url=normalized,
                        source=source,
                        source_url=source_url,
                        discovered_url=discovered_url,
                    )
                )
            return normalized

        add_candidate(seed, DiscoverySource.SEED, source_url=None, depth=0)

        robots_url = normalize_url("/robots.txt", base_url=f"{origin}/")
        robots_acquisition = self.http_client.acquire(robots_url)
        robots_state, robots_parser, declared_sitemaps = self._interpret_robots(
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
        sitemap_index = 0
        while sitemap_index < len(sitemap_queue):
            sitemap_url = sitemap_queue[sitemap_index]
            sitemap_index += 1
            result = self._acquire_sitemap(sitemap_url, origin)
            sitemap_results.append(result)
            if result.state is not SitemapState.OBTAINED:
                continue
            for page_url in result.page_urls:
                add_candidate(
                    page_url,
                    DiscoverySource.SITEMAP,
                    source_url=sitemap_url,
                    depth=0,
                )
            for child in result.child_sitemaps:
                if child not in sitemap_seen and is_same_origin(child, origin):
                    sitemap_seen.add(child)
                    sitemap_queue.append(child)

        selected: list[str] = []
        selected_set: set[str] = set()
        page_acquisitions: dict[str, HttpAcquisitionResult] = {}

        while len(selected) < max_pages:
            eligible = [candidate for url, candidate in candidates.items() if url not in selected_set]
            if not eligible:
                break
            candidate = min(eligible, key=self._selection_key)
            selected.append(candidate.normalized_url)
            selected_set.add(candidate.normalized_url)

            acquisition = self.http_client.acquire(candidate.normalized_url)
            page_acquisitions[candidate.normalized_url] = acquisition

            if acquisition.final_url and acquisition.final_url != candidate.normalized_url:
                add_candidate(
                    acquisition.final_url,
                    DiscoverySource.REDIRECT,
                    source_url=candidate.normalized_url,
                    depth=candidate.depth,
                )

            if not self._is_analyzable_html(acquisition):
                continue
            parser = _LinkParser()
            try:
                parser.feed(decode_body(acquisition))
                parser.close()
            except (AssertionError, ValueError):
                continue
            base = acquisition.final_url or candidate.normalized_url
            for href in parser.hrefs:
                resolved = resolve_http_url(base, href)
                if resolved is None or not is_same_origin(resolved, origin):
                    continue
                add_candidate(
                    resolved,
                    DiscoverySource.INTERNAL_LINK,
                    source_url=candidate.normalized_url,
                    depth=candidate.depth + 1,
                    reference_increment=1,
                )

        pages = tuple(
            DiscoveredPage(
                normalized_url=url,
                discovered_url=candidates[url].discovered_url,
                discovery_sources=tuple(
                    sorted(candidates[url].sources, key=lambda item: (self._SOURCE_PRIORITY[item], item.value))
                ),
                depth=candidates[url].depth,
                internal_references=candidates[url].internal_references,
            )
            for url in selected
        )

        crawler_access: dict[str, dict[str, bool | None]] = {}
        for page in pages:
            if robots_state is RobotsState.OBTAINED and robots_parser is not None:
                crawler_access[page.normalized_url] = {
                    crawler: bool(robots_parser.can_fetch(crawler, page.normalized_url))
                    for crawler in self.crawlers
                }
            elif robots_state is RobotsState.ABSENT:
                crawler_access[page.normalized_url] = {crawler: True for crawler in self.crawlers}
            else:
                crawler_access[page.normalized_url] = {crawler: None for crawler in self.crawlers}

        robots = RobotsResult(
            url=robots_url,
            state=robots_state,
            acquisition=robots_acquisition,
            sitemap_urls=tuple(declared_sitemaps),
            crawler_access=crawler_access,
        )

        return DiscoveryResult(
            origin=origin,
            pages=pages,
            page_acquisitions=page_acquisitions,
            provenance=tuple(provenance),
            robots=robots,
            sitemaps=tuple(sitemap_results),
            total_discovered=len(candidates),
            total_audited=len(pages),
            max_pages=max_pages,
            limit_reached=any(url not in selected_set for url in candidates),
        )

    def _selection_key(self, candidate: _Candidate) -> tuple[int, int, int, str]:
        # Normative order: seed, sitemap, then crawl depth, internal references
        # and a stable URL tie-break. Redirect/manual/internal-link candidates
        # share the same third tier rather than introducing a new heuristic.
        if DiscoverySource.SEED in candidate.sources:
            tier = 0
        elif DiscoverySource.SITEMAP in candidate.sources:
            tier = 1
        else:
            tier = 2
        return (
            tier,
            candidate.depth,
            -candidate.internal_references,
            candidate.normalized_url,
        )

    @staticmethod
    def _is_analyzable_html(acquisition: HttpAcquisitionResult) -> bool:
        if acquisition.network_error is not None or acquisition.status is None:
            return False
        if not 200 <= acquisition.status <= 299:
            return False
        content_type = (acquisition.header("Content-Type") or "").split(";", 1)[0].strip().casefold()
        return content_type in {"text/html", "application/xhtml+xml"}

    def _interpret_robots(
        self,
        robots_url: str,
        acquisition: HttpAcquisitionResult,
        origin: str,
    ) -> tuple[RobotsState, robotparser.RobotFileParser | None, tuple[str, ...]]:
        if acquisition.network_error is not None:
            return RobotsState.NETWORK_ERROR, None, ()
        if acquisition.status in {404, 410}:
            return RobotsState.ABSENT, None, ()
        if acquisition.status is None or not 200 <= acquisition.status <= 299:
            return RobotsState.HTTP_ERROR, None, ()

        parser = robotparser.RobotFileParser()
        parser.set_url(robots_url)
        parser.parse(decode_body(acquisition).splitlines())
        raw_sitemaps = parser.site_maps() or []
        normalized_sitemaps: list[str] = []
        for raw_sitemap in raw_sitemaps:
            try:
                sitemap = normalize_url(raw_sitemap, base_url=robots_url)
            except ValueError:
                continue
            if is_same_origin(sitemap, origin) and sitemap not in normalized_sitemaps:
                normalized_sitemaps.append(sitemap)
        return RobotsState.OBTAINED, parser, tuple(normalized_sitemaps)

    def _acquire_sitemap(self, sitemap_url: str, origin: str) -> SitemapResult:
        acquisition = self.http_client.acquire(sitemap_url)
        if acquisition.network_error is not None:
            return SitemapResult(sitemap_url, SitemapState.NETWORK_ERROR, acquisition)
        if acquisition.status in {404, 410}:
            return SitemapResult(sitemap_url, SitemapState.ABSENT, acquisition)
        if acquisition.status is None or not 200 <= acquisition.status <= 299:
            return SitemapResult(sitemap_url, SitemapState.HTTP_ERROR, acquisition)

        payload = acquisition.body
        if sitemap_url.casefold().endswith(".gz") or "gzip" in (acquisition.header("Content-Type") or "").casefold():
            try:
                payload = gzip.GzipFile(fileobj=BytesIO(payload)).read()
            except OSError as exc:
                return SitemapResult(
                    sitemap_url,
                    SitemapState.INVALID,
                    acquisition,
                    error=f"invalid gzip sitemap: {exc}",
                )
        try:
            root = ET.fromstring(payload)
        except ET.ParseError as exc:
            return SitemapResult(
                sitemap_url,
                SitemapState.INVALID,
                acquisition,
                error=f"invalid sitemap XML: {exc}",
            )

        root_name = _local_name(root.tag)
        locations = [
            (element.text or "").strip()
            for element in root.iter()
            if _local_name(element.tag) == "loc" and (element.text or "").strip()
        ]
        normalized_locations: list[str] = []
        for location in locations:
            try:
                normalized = normalize_url(location, base_url=sitemap_url)
            except ValueError:
                continue
            if is_same_origin(normalized, origin) and normalized not in normalized_locations:
                normalized_locations.append(normalized)

        if root_name == "urlset":
            return SitemapResult(
                sitemap_url,
                SitemapState.OBTAINED,
                acquisition,
                page_urls=tuple(normalized_locations),
            )
        if root_name == "sitemapindex":
            return SitemapResult(
                sitemap_url,
                SitemapState.OBTAINED,
                acquisition,
                child_sitemaps=tuple(normalized_locations),
            )
        return SitemapResult(
            sitemap_url,
            SitemapState.INVALID,
            acquisition,
            error=f"unsupported sitemap root element: {root_name}",
        )


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].casefold()
