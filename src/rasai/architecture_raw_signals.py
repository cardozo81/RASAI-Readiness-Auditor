"""Bounded, content-free structural signals from ONE observed RAW HTML (#646).

These facts do not establish rendered DOM, SPA, SSR, framework execution,
crawler indexability, or any usable Apdex/score. No network, HTML persistence,
external resources, JS execution, OCR or inferred framework/version.
"""
from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser

MAX_HTML_CHARS = 1_000_000
MAX_TAGS = 20_000
_MAX_MAIN_CHARS = 4096
_APP_ROOT_IDS = frozenset({"app", "root", "__next", "__nuxt", "app-root", "application"})
_FRAMEWORK_ATTRIBUTES = frozenset({
    "data-reactroot", "data-reactid", "data-v-app", "ng-version",
    "data-server-rendered", "data-hydrate", "data-hydration",
})


@dataclass(frozen=True, slots=True)
class RawHtmlSignals:
    """Only bounded counts/booleans and literal methodology status."""
    status: str
    tag_count: int = 0
    raw_main_text_present: bool = False
    h1_present: bool = False
    app_root_marker_present: bool = False
    framework_attribute_present: bool = False
    external_script_tags: int = 0
    inline_script_tags: int = 0
    hidden_placeholder_present: bool = False
    iframe_tags: int = 0
    iframe_src_tags: int = 0
    iframe_srcdoc_tags: int = 0
    rendered_dom_observed: bool = False
    architecture_inferred: bool = False
    rules_version: str = "architecture-raw-signals-v1"


class _StructuralParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tags = 0
        self._ignored = 0
        self._main = 0
        self._main_buffer = ""
        self._script_stack = 0
        self._inline_script = 0
        self.h1 = False
        self.root_marker = False
        self.framework_attribute = False
        self.external_scripts = 0
        self.inline_scripts = 0
        self.hidden_placeholder = False
        self.iframes = 0
        self.iframe_src = 0
        self.iframe_srcdoc = 0

    def handle_starttag(self, tag, attrs):
        self.tags += 1
        if self.tags > MAX_TAGS:
            raise ValueError("RAW_HTML_TAG_BUDGET_EXCEEDED")
        attributes = dict(attrs)
        if tag in {"script", "style", "template", "noscript", "svg"}:
            self._ignored += 1
        if tag in {"main", "article"} and not self._ignored:
            self._main += 1
        if tag == "h1" and not self._ignored:
            self.h1 = True
        if tag in {"div", "main", "section", "body", "article"}:
            marker = attributes.get("id")
            self.root_marker |= isinstance(marker, str) and marker.lower() in _APP_ROOT_IDS
        self.framework_attribute |= bool(_FRAMEWORK_ATTRIBUTES.intersection(attributes))
        if tag == "iframe":
            self.iframes = min(self.iframes + 1, 1000)
            self.iframe_src += int(bool(attributes.get("src")) and self.iframe_src < 1000)
            self.iframe_srcdoc += int("srcdoc" in attributes and self.iframe_srcdoc < 1000)
        if tag == "script":
            if attributes.get("src"):
                self.external_scripts = min(self.external_scripts + 1, 1000)
            else:
                self.inline_scripts = min(self.inline_scripts + 1, 1000)
        classes = attributes.get("class") or ""
        if isinstance(classes, str):
            self.hidden_placeholder |= any(
                token in classes.lower().split()
                for token in ("skeleton", "placeholder", "loading-state")
            )

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if tag in {"main", "article"}:
            self._main = max(self._main - 1, 0)
        if tag in {"script", "style", "template", "noscript", "svg"}:
            self._ignored = max(self._ignored - 1, 0)

    def handle_data(self, data):
        if self._main and not self._ignored and len(self._main_buffer) < _MAX_MAIN_CHARS:
            self._main_buffer += data[: _MAX_MAIN_CHARS - len(self._main_buffer)]

    def signals(self):
        substantive = len(" ".join(self._main_buffer.split())) >= 80
        return RawHtmlSignals(
            status="RAW_STRUCTURAL_SIGNALS_OBSERVED",
            tag_count=self.tags,
            raw_main_text_present=substantive,
            h1_present=self.h1,
            app_root_marker_present=self.root_marker,
            framework_attribute_present=self.framework_attribute,
            external_script_tags=self.external_scripts,
            inline_script_tags=self.inline_scripts,
            hidden_placeholder_present=self.hidden_placeholder,
            iframe_tags=self.iframes,
            iframe_src_tags=self.iframe_src,
            iframe_srcdoc_tags=self.iframe_srcdoc,
        )


def inspect_raw_html_signals(raw_html: str | None) -> RawHtmlSignals:
    """Abstain on malformed/unbounded data rather than projecting partial counts."""
    if raw_html is None:
        return RawHtmlSignals(status="RAW_HTML_UNAVAILABLE")
    if not isinstance(raw_html, str) or len(raw_html) > MAX_HTML_CHARS:
        return RawHtmlSignals(status="RAW_HTML_INVALID_OR_OVERSIZE")
    parser = _StructuralParser()
    try:
        parser.feed(raw_html)
        parser.close()
    except (ValueError, TypeError, RecursionError):
        return RawHtmlSignals(status="RAW_HTML_STRUCTURE_UNVERIFIABLE")
    return parser.signals()


__all__ = ["inspect_raw_html_signals", "RawHtmlSignals"]
