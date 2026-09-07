"""Deterministic HTML/DOM extraction for M4 - Extraction + Evidence."""

from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser
import json
import re
from typing import Any


_WHITESPACE = re.compile(r"\s+")
_SKIP_CONTENT = {"script", "style", "noscript", "template", "svg"}
_BOILERPLATE = {"nav", "header", "footer", "aside"}
_HEADINGS = {"h1", "h2", "h3", "h4", "h5", "h6"}


def _clean_text(value: str) -> str:
    return _WHITESPACE.sub(" ", value).strip()


def _attrs(items: list[tuple[str, str | None]]) -> dict[str, str]:
    return {key.lower(): value or "" for key, value in items}


@dataclass(frozen=True, slots=True)
class HeadingObservation:
    level: int
    text: str


@dataclass(frozen=True, slots=True)
class LinkObservation:
    href: str
    text: str
    rel: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class StructuredDataBlock:
    index: int
    raw: str
    parsed: Any | None
    parse_error: str | None

    @property
    def types(self) -> tuple[str, ...]:
        found: list[str] = []

        def visit(value: Any) -> None:
            if isinstance(value, dict):
                item_type = value.get("@type")
                if isinstance(item_type, str):
                    found.append(item_type)
                elif isinstance(item_type, list):
                    found.extend(str(item) for item in item_type if isinstance(item, str))
                for child in value.values():
                    visit(child)
            elif isinstance(value, list):
                for child in value:
                    visit(child)

        if self.parsed is not None:
            visit(self.parsed)
        return tuple(dict.fromkeys(found))


@dataclass(frozen=True, slots=True)
class ExtractedPage:
    title: str | None
    description: str | None
    canonical: str | None
    meta_robots: str | None
    headings: tuple[HeadingObservation, ...]
    links: tuple[LinkObservation, ...]
    structured_data: tuple[StructuredDataBlock, ...]
    main_content: str
    text_blocks: tuple[str, ...]
    main_content_source: str


class ContentExtractor:
    """Extract deterministic page features without semantic interpretation."""

    def extract(self, html: str) -> ExtractedPage:
        parser = _ExtractionParser()
        parser.feed(html)
        parser.close()
        return parser.result()


class _ExtractionParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[tuple[str, bool, bool, bool]] = []
        self.skip_depth = 0
        self.boilerplate_depth = 0
        self.main_depth = 0
        self.body_depth = 0
        self.title_depth = 0
        self.title_parts: list[str] = []
        self.description: str | None = None
        self.canonical: str | None = None
        self.meta_robots: str | None = None
        self.headings: list[HeadingObservation] = []
        self.links: list[LinkObservation] = []
        self.body_parts: list[str] = []
        self.main_parts: list[str] = []
        self.text_blocks: list[str] = []
        self.current_heading: tuple[int, list[str]] | None = None
        self.current_link: tuple[str, tuple[str, ...], list[str]] | None = None
        self.current_jsonld: list[str] | None = None
        self.structured_data: list[StructuredDataBlock] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        values = _attrs(attrs)
        starts_skip = tag in _SKIP_CONTENT
        starts_boilerplate = tag in _BOILERPLATE
        role = values.get("role", "").lower()
        starts_main = tag in {"main", "article"} or role == "main"
        self.stack.append((tag, starts_skip, starts_boilerplate, starts_main))

        if tag == "body":
            self.body_depth += 1
        if starts_skip:
            self.skip_depth += 1
        if starts_boilerplate:
            self.boilerplate_depth += 1
        if starts_main:
            self.main_depth += 1
        if tag == "title":
            self.title_depth += 1

        if tag == "meta":
            name = values.get("name", "").strip().lower()
            content = values.get("content", "").strip()
            if name == "description" and content and self.description is None:
                self.description = content
            elif name == "robots" and content and self.meta_robots is None:
                self.meta_robots = content

        if tag == "link":
            rel_tokens = tuple(token.lower() for token in values.get("rel", "").split() if token)
            href = values.get("href", "").strip()
            if "canonical" in rel_tokens and href and self.canonical is None:
                self.canonical = href

        if tag in _HEADINGS and self.skip_depth == 0:
            self.current_heading = (int(tag[1]), [])

        if tag == "a" and self.skip_depth == 0:
            href = values.get("href", "").strip()
            rel = tuple(token.lower() for token in values.get("rel", "").split() if token)
            self.current_link = (href, rel, [])

        if tag == "script" and values.get("type", "").split(";", 1)[0].strip().lower() == "application/ld+json":
            self.current_jsonld = []

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()

        if tag in _HEADINGS and self.current_heading is not None:
            level, parts = self.current_heading
            text = _clean_text(" ".join(parts))
            if text:
                self.headings.append(HeadingObservation(level=level, text=text))
            self.current_heading = None

        if tag == "a" and self.current_link is not None:
            href, rel, parts = self.current_link
            if href:
                self.links.append(LinkObservation(href=href, text=_clean_text(" ".join(parts)), rel=rel))
            self.current_link = None

        if tag == "script" and self.current_jsonld is not None:
            raw = "".join(self.current_jsonld).strip()
            if raw:
                parsed: Any | None = None
                parse_error: str | None = None
                try:
                    parsed = json.loads(raw)
                except (TypeError, ValueError):
                    parse_error = "INVALID_JSON"
                self.structured_data.append(
                    StructuredDataBlock(
                        index=len(self.structured_data),
                        raw=raw,
                        parsed=parsed,
                        parse_error=parse_error,
                    )
                )
            self.current_jsonld = None

        for position in range(len(self.stack) - 1, -1, -1):
            stack_tag, starts_skip, starts_boilerplate, starts_main = self.stack[position]
            if stack_tag != tag:
                continue
            del self.stack[position:]
            if tag == "body" and self.body_depth:
                self.body_depth -= 1
            if tag == "title" and self.title_depth:
                self.title_depth -= 1
            if starts_skip and self.skip_depth:
                self.skip_depth -= 1
            if starts_boilerplate and self.boilerplate_depth:
                self.boilerplate_depth -= 1
            if starts_main and self.main_depth:
                self.main_depth -= 1
            break

    def handle_data(self, data: str) -> None:
        if self.current_jsonld is not None:
            self.current_jsonld.append(data)

        text = _clean_text(data)
        if not text:
            return

        if self.title_depth:
            self.title_parts.append(text)

        if self.current_heading is not None:
            self.current_heading[1].append(text)
        if self.current_link is not None:
            self.current_link[2].append(text)

        if self.body_depth and self.skip_depth == 0:
            self.body_parts.append(text)
            if self.boilerplate_depth == 0:
                self.text_blocks.append(text)
            if self.main_depth > 0 and self.boilerplate_depth == 0:
                self.main_parts.append(text)

    def result(self) -> ExtractedPage:
        title = _clean_text(" ".join(self.title_parts)) or None
        main_content = _clean_text(" ".join(self.main_parts))
        source = "MAIN_OR_ARTICLE"
        if not main_content:
            main_content = _clean_text(" ".join(self.text_blocks))
            source = "BODY_WITHOUT_BOILERPLATE"
        if not main_content:
            main_content = _clean_text(" ".join(self.body_parts))
            source = "BODY_FALLBACK"

        return ExtractedPage(
            title=title,
            description=self.description,
            canonical=self.canonical,
            meta_robots=self.meta_robots,
            headings=tuple(self.headings),
            links=tuple(self.links),
            structured_data=tuple(self.structured_data),
            main_content=main_content,
            text_blocks=tuple(self.text_blocks),
            main_content_source=source,
        )
