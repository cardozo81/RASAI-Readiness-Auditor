"""Versioned technical references for M14 remediation reporting.

Only URLs verified against current primary/authoritative documentation on
2026-09-06 are stored here. Rules without a specific normative external
source are explicitly reported as internal/heuristic instead of receiving an
invented authority.
"""

from __future__ import annotations

from dataclasses import dataclass


VERIFIED_ON = "2026-09-06"


@dataclass(frozen=True, slots=True)
class RuleReference:
    rule_id: str
    source_type: str
    authority: str | None
    title: str | None
    url: str | None
    reference_scope: str
    basis: str
    verified_on: str | None = VERIFIED_ON


_GOOGLE_SITEMAP = (
    "Google Search Central",
    "Build and Submit a Sitemap",
    "https://developers.google.com/search/docs/crawling-indexing/sitemaps/build-sitemap",
)
_GOOGLE_CANONICAL = (
    "Google Search Central",
    "What is URL Canonicalization",
    "https://developers.google.com/search/docs/crawling-indexing/canonicalization",
)
_GOOGLE_STRUCTURED = (
    "Google Search Central",
    "Intro to How Structured Data Markup Works",
    "https://developers.google.com/search/docs/appearance/structured-data/intro-structured-data",
)
_GOOGLE_HELPFUL_CONTENT = (
    "Google Search Central",
    "Creating Helpful, Reliable, People-First Content",
    "https://developers.google.com/search/docs/fundamentals/creating-helpful-content",
)
_GOOGLE_ROBOTS = (
    "Google Crawling Infrastructure",
    "How Google Interprets the robots.txt Specification",
    "https://developers.google.com/crawling/docs/robots-txt/robots-txt-spec",
)
_RFC_9309 = (
    "IETF / RFC Editor",
    "RFC 9309 — Robots Exclusion Protocol",
    "https://www.rfc-editor.org/rfc/rfc9309.html",
)
_RFC_9110 = (
    "IETF / RFC Editor",
    "RFC 9110 — HTTP Semantics",
    "https://www.rfc-editor.org/rfc/rfc9110.html",
)
_WHATWG_SECTIONS = (
    "WHATWG",
    "HTML Living Standard — Sections",
    "https://html.spec.whatwg.org/dev/sections.html",
)
_OPENAI_PUBLISHERS = (
    "OpenAI Help Center",
    "Publishers and Developers — FAQ",
    "https://help.openai.com/en/articles/12627856-publishers-and-developers-faq",
)


# Basis values follow the current BR-GEO baseline/RULES_GUIDE. This list is
# intentionally explicit so reporting never promotes a heuristic to a standard.
_HEURISTIC_RULES = frozenset({
    "BR-GEO-008", "BR-GEO-010", "BR-GEO-014", "BR-GEO-016",
    "BR-GEO-023", "BR-GEO-024", "BR-GEO-025", "BR-GEO-026", "BR-GEO-027",
    "BR-GEO-029", "BR-GEO-030", "BR-GEO-031", "BR-GEO-032", "BR-GEO-033",
    "BR-GEO-036", "BR-GEO-037", "BR-GEO-038", "BR-GEO-039", "BR-GEO-040",
    "BR-GEO-041", "BR-GEO-042", "BR-GEO-043", "BR-GEO-044", "BR-GEO-045",
    "BR-GEO-046", "BR-GEO-047", "BR-GEO-048", "BR-GEO-049",
})
_STANDARD_RULES = frozenset({
    "BR-GEO-003", "BR-GEO-005", "BR-GEO-006", "BR-GEO-007", "BR-GEO-009",
    "BR-GEO-011", "BR-GEO-012", "BR-GEO-013", "BR-GEO-015", "BR-GEO-017",
    "BR-GEO-018", "BR-GEO-019", "BR-GEO-020", "BR-GEO-021", "BR-GEO-022",
    "BR-GEO-028", "BR-GEO-034", "BR-GEO-035",
})
_OFFICIAL_RULES = frozenset({"BR-GEO-001", "BR-GEO-002", "BR-GEO-004"})


def references_for(rule_id: str) -> tuple[RuleReference, ...]:
    """Return authoritative references when they directly support rule context.

    A primary guidance reference does not change ``basis``. In particular,
    semantic rules remain HEURISTIC where the RASAI evaluator/threshold is
    an internal implementation even when the underlying quality concept is
    discussed in official Google documentation.
    """

    basis = basis_for(rule_id)
    rows: list[tuple[str, str, str, str]] = []

    if rule_id == "BR-GEO-003":
        rows.append((*_GOOGLE_SITEMAP, "sitemap discovery, syntax and submission context"))
    elif rule_id in {"BR-GEO-005", "BR-GEO-006", "BR-GEO-007", "BR-GEO-008"}:
        rows.append((*_RFC_9110, "HTTP response/status/redirect semantics"))
    elif rule_id in {"BR-GEO-013", "BR-GEO-014", "BR-GEO-015"}:
        rows.append((*_GOOGLE_CANONICAL, "canonical signals and canonicalization context"))
    elif rule_id == "BR-GEO-017":
        rows.extend(
            (
                (*_RFC_9309, "normative Robots Exclusion Protocol"),
                (*_GOOGLE_ROBOTS, "Google crawler interpretation of robots.txt"),
            )
        )
    elif rule_id == "BR-GEO-018":
        rows.extend(
            (
                (*_RFC_9309, "robots.txt crawler policy protocol"),
                (*_OPENAI_PUBLISHERS, "OAI-SearchBot search access and GPTBot training controls"),
            )
        )
    elif rule_id in {"BR-GEO-025", "BR-GEO-028", "BR-GEO-029", "BR-GEO-030"}:
        rows.append((*_WHATWG_SECTIONS, "HTML sectioning and heading semantics"))
    elif rule_id in {"BR-GEO-034", "BR-GEO-035", "BR-GEO-036", "BR-GEO-037"}:
        rows.append((*_GOOGLE_STRUCTURED, "structured data relationship to page content"))
    elif rule_id in {"BR-GEO-038", "BR-GEO-039", "BR-GEO-040", "BR-GEO-044", "BR-GEO-048", "BR-GEO-049"}:
        rows.append(
            (*_GOOGLE_HELPFUL_CONTENT, "people-first purpose, intended audience, usefulness, completeness and user-needs context")
        )
    elif rule_id in {"BR-GEO-041", "BR-GEO-042", "BR-GEO-043", "BR-GEO-045"}:
        rows.append(
            (*_GOOGLE_HELPFUL_CONTENT, "factual accuracy, sourcing/evidence and trust self-assessment context")
        )
    elif rule_id == "BR-GEO-046":
        rows.append(
            (*_GOOGLE_HELPFUL_CONTENT, "Who created the content, authorship/byline and trust context")
        )
    elif rule_id == "BR-GEO-047":
        rows.append(
            (*_GOOGLE_HELPFUL_CONTENT, "content freshness/usefulness context without artificial date changes")
        )

    if not rows:
        return (
            RuleReference(
                rule_id=rule_id,
                source_type="INTERNAL_RULE",
                authority=None,
                title=None,
                url=None,
                reference_scope=f"Referência interna {rule_id}",
                basis=basis,
                verified_on=None,
            ),
        )

    return tuple(
        RuleReference(
            rule_id=rule_id,
            source_type="PRIMARY_AUTHORITY",
            authority=authority,
            title=title,
            url=url,
            reference_scope=scope,
            basis=basis,
        )
        for authority, title, url, scope in rows
    )


def basis_for(rule_id: str) -> str:
    if rule_id in _HEURISTIC_RULES:
        return "HEURISTIC"
    if rule_id in _STANDARD_RULES:
        return "STANDARD"
    if rule_id in _OFFICIAL_RULES:
        return "OFFICIAL"
    # BR-GEO-050..054 currently do not materialize a RuleDefinition.basis.
    return "INTERNAL_BASELINE"
