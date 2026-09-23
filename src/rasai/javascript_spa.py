"""Deterministic JavaScript/SPA diagnostics for M6."""

from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Callable

from playwright.sync_api import Error as PlaywrightError, TimeoutError as PlaywrightTimeoutError, sync_playwright

from rasai.domain import ArchitectureClassification, DeviceContext, RuleResult
from rasai.extraction import ContentExtractor, ExtractedPage
from rasai.rendering import DESKTOP_PROFILE, MOBILE_PROFILE, BrowserRenderResult, RenderErrorKind
from rasai.url_utils import is_same_origin, normalize_url


@dataclass(frozen=True, slots=True)
class StateComparison:
    architecture: ArchitectureClassification
    changed_fields: tuple[str, ...]
    raw_main_content: str
    rendered_main_content: str
    raw_links: tuple[str, ...]
    rendered_links: tuple[str, ...]
    raw_structured_types: tuple[str, ...]
    rendered_structured_types: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class NavigationAssessment:
    crawlable_internal_links: tuple[str, ...]
    non_crawlable_navigation_controls: int


@dataclass(frozen=True, slots=True)
class LazyAssessment:
    has_lazy_signals: bool
    initial_content_recoverable: bool
    after_probe_content_recoverable: bool | None
    result: RuleResult
    reason: str | None


class JavascriptSpaAnalyzer:
    """Compare RAW and rendered states without semantic-provider dependency."""

    def __init__(self) -> None:
        self._extractor = ContentExtractor()

    def compare(self, raw_html: str, rendered_html: str) -> StateComparison:
        raw = self._extractor.extract(raw_html)
        rendered = self._extractor.extract(rendered_html)
        changed: list[str] = []
        if raw.title != rendered.title:
            changed.append("title")
        if raw.description != rendered.description:
            changed.append("description")
        if raw.canonical != rendered.canonical:
            changed.append("canonical")
        if raw.meta_robots != rendered.meta_robots:
            changed.append("robots")
        if tuple((item.level, item.text) for item in raw.headings) != tuple((item.level, item.text) for item in rendered.headings):
            changed.append("headings")
        if raw.main_content != rendered.main_content:
            changed.append("main_content")
        raw_links = tuple(item.href for item in raw.links)
        rendered_links = tuple(item.href for item in rendered.links)
        if raw_links != rendered_links:
            changed.append("links")
        raw_types = _structured_types(raw)
        rendered_types = _structured_types(rendered)
        if raw_types != rendered_types:
            changed.append("structured_data")
        return StateComparison(
            architecture=_classify_architecture(raw, rendered),
            changed_fields=tuple(changed),
            raw_main_content=raw.main_content,
            rendered_main_content=rendered.main_content,
            raw_links=raw_links,
            rendered_links=rendered_links,
            raw_structured_types=raw_types,
            rendered_structured_types=rendered_types,
        )

    def navigation(self, rendered_html: str, *, base_url: str, origin: str) -> NavigationAssessment:
        parser = _NavigationParser()
        parser.feed(rendered_html)
        parser.close()
        links: list[str] = []
        for href in parser.hrefs:
            try:
                normalized = normalize_url(href, base_url=base_url)
            except ValueError:
                continue
            if is_same_origin(normalized, origin):
                links.append(normalized)
        return NavigationAssessment(
            crawlable_internal_links=tuple(dict.fromkeys(links)),
            non_crawlable_navigation_controls=parser.non_crawlable_controls,
        )

    def soft404(self, *, http_status: int | None, rendered_html: str) -> bool:
        if http_status is None or not (200 <= http_status <= 299):
            return False
        page = self._extractor.extract(rendered_html)
        prominent = [page.title or "", *(item.text for item in page.headings[:3])]
        prominent_error = any(_is_error_label(value) for value in prominent)
        if not prominent_error:
            return False
        # Soft-404 is intentionally conservative: a numeric/title coincidence is
        # insufficient. Require a corroborating error phrase in main content.
        return _contains_error_phrase(page.main_content)

    def lazy_loading(
        self,
        rendered_html: str,
        *,
        after_probe_html: str | None,
    ) -> LazyAssessment:
        parser = _LazyParser()
        parser.feed(rendered_html)
        parser.close()
        has_lazy = parser.lazy_signals > 0
        before = bool(self._extractor.extract(rendered_html).main_content)
        if not has_lazy:
            return LazyAssessment(False, before, None, RuleResult.PASS, None)
        if before:
            return LazyAssessment(True, True, None, RuleResult.PASS, None)
        if after_probe_html is None:
            return LazyAssessment(True, False, None, RuleResult.UNKNOWN, "LAZY_PROBE_UNAVAILABLE")
        after = bool(self._extractor.extract(after_probe_html).main_content)
        if after:
            return LazyAssessment(True, False, True, RuleResult.PASS, "CONTENT_RECOVERED_BY_BOUNDED_SCROLL")
        return LazyAssessment(True, False, False, RuleResult.FAIL, "ESSENTIAL_CONTENT_NOT_RECOVERED_BY_BOUNDED_SCROLL")


def _structured_types(page: ExtractedPage) -> tuple[str, ...]:
    return tuple(dict.fromkeys(value for block in page.structured_data for value in block.types))


def _classify_architecture(raw: ExtractedPage, rendered: ExtractedPage) -> ArchitectureClassification:
    raw_main = raw.main_content.strip()
    rendered_main = rendered.main_content.strip()
    if not raw_main and rendered_main:
        return ArchitectureClassification.CSR_SPA
    if raw_main and rendered_main:
        if raw_main == rendered_main and raw.title == rendered.title and raw.headings == rendered.headings:
            return ArchitectureClassification.STATIC_OR_SSR
        if raw_main in rendered_main or rendered_main in raw_main:
            return ArchitectureClassification.HYDRATED
        return ArchitectureClassification.MIXED
    if raw_main == rendered_main:
        return ArchitectureClassification.STATIC_OR_SSR
    return ArchitectureClassification.UNKNOWN


def _normalize_signal(value: str) -> str:
    return " ".join(value.casefold().replace("-", " ").replace("-", " ").split())


def _is_error_label(value: str) -> bool:
    normalized = _normalize_signal(value)
    exact = {
        "404",
        "404 not found",
        "not found",
        "page not found",
        "página não encontrada",
        "pagina nao encontrada",
        "conteúdo não encontrado",
        "conteudo nao encontrado",
    }
    if normalized in exact:
        return True
    if normalized.startswith("404 "):
        tail = normalized[4:].strip()
        return tail in {
            "not found",
            "page not found",
            "página não encontrada",
            "pagina nao encontrada",
            "conteúdo não encontrado",
            "conteudo nao encontrado",
            "error",
            "erro",
        }
    return False


def _contains_error_phrase(value: str) -> bool:
    normalized = _normalize_signal(value)
    phrases = (
        "not found",
        "page not found",
        "página não encontrada",
        "pagina nao encontrada",
        "conteúdo não encontrado",
        "conteudo nao encontrado",
    )
    return any(phrase in normalized for phrase in phrases)


class _NavigationParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[tuple[str, bool]] = []
        self.nav_depth = 0
        self.hrefs: list[str] = []
        self.non_crawlable_controls = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        values = {key.lower(): value or "" for key, value in attrs}
        starts_navigation = tag == "nav" or values.get("role", "").lower() == "navigation"
        self.stack.append((tag, starts_navigation))
        if starts_navigation:
            self.nav_depth += 1
        if tag == "a":
            href = values.get("href", "").strip()
            if href:
                self.hrefs.append(href)
            elif self.nav_depth and (values.get("onclick") or values.get("role", "").lower() == "link"):
                self.non_crawlable_controls += 1
        elif self.nav_depth and tag in {"button", "div", "span"} and (
            values.get("onclick") or values.get("role", "").lower() == "link"
        ):
            self.non_crawlable_controls += 1

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        for position in range(len(self.stack) - 1, -1, -1):
            stack_tag, _ = self.stack[position]
            if stack_tag != tag:
                continue
            for _, starts_navigation in self.stack[position:]:
                if starts_navigation and self.nav_depth:
                    self.nav_depth -= 1
            del self.stack[position:]
            break


class _LazyParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.lazy_signals = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key.lower(): value or "" for key, value in attrs}
        if values.get("loading", "").lower() == "lazy" or "data-src" in values or "data-lazy" in values:
            self.lazy_signals += 1

    def handle_data(self, data: str) -> None:
        if "intersectionobserver" in data.casefold():
            self.lazy_signals += 1


class BoundedScrollProbe:
    """Optional M6 browser probe with a fixed, non-arbitrary scroll budget."""

    def __init__(self, *, scroll_steps: int = 3, navigation_timeout_ms: int = 15_000, settle_ms: int = 250) -> None:
        if scroll_steps <= 0 or scroll_steps > 5:
            raise ValueError("scroll_steps must be between 1 and 5")
        self.scroll_steps = scroll_steps
        self.navigation_timeout_ms = navigation_timeout_ms
        self.settle_ms = settle_ms

    def render_after_scroll(self, url: str, device: DeviceContext) -> BrowserRenderResult:
        profile = DESKTOP_PROFILE if device is DeviceContext.DESKTOP else MOBILE_PROFILE
        browser = None
        playwright = None
        context = None
        page = None
        try:
            playwright = sync_playwright().start()
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(**profile.context_options)
            page = context.new_page()
            response = page.goto(url, wait_until="domcontentloaded", timeout=self.navigation_timeout_ms)
            for _ in range(self.scroll_steps):
                page.evaluate("window.scrollBy(0, Math.max(window.innerHeight * 0.8, 1))")
                page.wait_for_timeout(self.settle_ms)
            return BrowserRenderResult(
                requested_url=url,
                final_url=page.url,
                http_status=response.status if response else None,
                content_type=response.headers.get("content-type") if response else None,
                rendered_html=page.content(),
                browser_metadata={
                    "engine": "chromium",
                    "probe": "bounded-scroll",
                    "scroll_steps": self.scroll_steps,
                    "settle_ms": self.settle_ms,
                    "device": device.value,
                },
            )
        except PlaywrightTimeoutError:
            error = RenderErrorKind.NAVIGATION_TIMEOUT
        except PlaywrightError:
            error = RenderErrorKind.NAVIGATION_ERROR
        except Exception:
            error = RenderErrorKind.RENDERER_ERROR
        finally:
            if page is not None:
                try:
                    page.close()
                except PlaywrightError:
                    pass
            if context is not None:
                try:
                    context.close()
                except PlaywrightError:
                    pass
            if browser is not None:
                try:
                    browser.close()
                except PlaywrightError:
                    pass
            if playwright is not None:
                try:
                    playwright.stop()
                except Exception:
                    pass
        return BrowserRenderResult(
            requested_url=url,
            final_url=None,
            http_status=None,
            content_type=None,
            rendered_html=None,
            browser_metadata={"probe": "bounded-scroll", "device": device.value},
            error_kind=error,
        )


LazyProbe = Callable[[str, DeviceContext], BrowserRenderResult]
