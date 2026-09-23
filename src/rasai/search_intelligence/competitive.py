"""Deterministic competitor/result classification for Search Intelligence.

This layer classifies observed SERP results and selects a bounded subset for optional
content inspection. It intentionally avoids causal ranking claims and does not use AI.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Iterable

from .domain import canonical_hostname, domain_matches
from .models import SearchIntelligenceResult, SerpResult


class SearchResultClass(StrEnum):
    CUSTOMER = "CUSTOMER"
    ORGANIC_CANDIDATE = "ORGANIC_CANDIDATE"
    PUBLIC_AUTHORITY = "PUBLIC_AUTHORITY"
    KNOWLEDGE_REFERENCE = "KNOWLEDGE_REFERENCE"
    SOCIAL_PLATFORM = "SOCIAL_PLATFORM"
    VIDEO_PLATFORM = "VIDEO_PLATFORM"
    MARKETPLACE = "MARKETPLACE"
    NON_ORGANIC = "NON_ORGANIC"


@dataclass(frozen=True, slots=True)
class ClassifiedSerpResult:
    result: SerpResult
    classification: SearchResultClass
    eligible_for_content_comparison: bool
    reason: str


@dataclass(frozen=True, slots=True)
class CompetitiveSelection:
    query: str
    customer_domain: str | None
    customer_result: SerpResult | None
    classified_results: tuple[ClassifiedSerpResult, ...]
    selected_candidates: tuple[ClassifiedSerpResult, ...]


_PUBLIC_DOMAINS = (
    "gov.br", "gov", "gob", "gov.uk", "gc.ca", "gouv.fr",
)
_KNOWLEDGE_DOMAINS = (
    "wikipedia.org", "wikidata.org", "britannica.com",
)
_SOCIAL_DOMAINS = (
    "facebook.com", "instagram.com", "linkedin.com", "x.com", "twitter.com",
    "tiktok.com", "pinterest.com", "reddit.com",
)
_VIDEO_DOMAINS = (
    "youtube.com", "youtu.be", "vimeo.com", "dailymotion.com",
)
_MARKETPLACE_DOMAINS = (
    "amazon.com", "amazon.com.br", "mercadolivre.com.br", "mercadolibre.com",
    "shopee.com.br", "magazineluiza.com.br",
)


def _is_domain_or_subdomain(domain: str, roots: Iterable[str]) -> bool:
    value = canonical_hostname(domain)
    return any(value == root or value.endswith("." + root) for root in roots)


def classify_result(
    result: SerpResult,
    *,
    customer_domain: str | None,
) -> ClassifiedSerpResult:
    if customer_domain and domain_matches(result.domain, customer_domain):
        return ClassifiedSerpResult(
            result=result,
            classification=SearchResultClass.CUSTOMER,
            eligible_for_content_comparison=False,
            reason="matches configured customer domain",
        )

    if result.result_type.casefold() != "organic":
        return ClassifiedSerpResult(
            result=result,
            classification=SearchResultClass.NON_ORGANIC,
            eligible_for_content_comparison=False,
            reason=f"SERP result_type={result.result_type}",
        )

    domain = canonical_hostname(result.domain)
    if _is_domain_or_subdomain(domain, _PUBLIC_DOMAINS):
        return ClassifiedSerpResult(
            result=result,
            classification=SearchResultClass.PUBLIC_AUTHORITY,
            eligible_for_content_comparison=False,
            reason="public-authority domain heuristic",
        )
    if _is_domain_or_subdomain(domain, _KNOWLEDGE_DOMAINS):
        return ClassifiedSerpResult(
            result=result,
            classification=SearchResultClass.KNOWLEDGE_REFERENCE,
            eligible_for_content_comparison=False,
            reason="knowledge/reference platform heuristic",
        )
    if _is_domain_or_subdomain(domain, _SOCIAL_DOMAINS):
        return ClassifiedSerpResult(
            result=result,
            classification=SearchResultClass.SOCIAL_PLATFORM,
            eligible_for_content_comparison=False,
            reason="social platform heuristic",
        )
    if _is_domain_or_subdomain(domain, _VIDEO_DOMAINS):
        return ClassifiedSerpResult(
            result=result,
            classification=SearchResultClass.VIDEO_PLATFORM,
            eligible_for_content_comparison=False,
            reason="video platform heuristic",
        )
    if _is_domain_or_subdomain(domain, _MARKETPLACE_DOMAINS):
        return ClassifiedSerpResult(
            result=result,
            classification=SearchResultClass.MARKETPLACE,
            eligible_for_content_comparison=True,
            reason="marketplace heuristic; retained as a Search competitor candidate",
        )
    return ClassifiedSerpResult(
        result=result,
        classification=SearchResultClass.ORGANIC_CANDIDATE,
        eligible_for_content_comparison=True,
        reason="external organic result; business equivalence is not inferred",
    )


def select_competitive_candidates(
    result: SearchIntelligenceResult,
    *,
    max_pages: int = 3,
) -> CompetitiveSelection:
    """Classify the relevant observed result set and choose bounded content candidates.

    When the customer is found, selection considers only results ahead of the first
    customer result. When it is not found, the bounded observed SERP is still classified,
    but comparison requires a separately supplied customer URL.
    """
    if max_pages < 0:
        raise ValueError("max_pages must be >= 0")
    observation = result.observation
    customer_domain = (
        canonical_hostname(result.request.domain_of_interest)
        if result.request.domain_of_interest
        else None
    )
    if observation is None:
        return CompetitiveSelection(
            query=result.request.query,
            customer_domain=customer_domain,
            customer_result=None,
            classified_results=(),
            selected_candidates=(),
        )

    customer_result = None
    if customer_domain:
        customer_result = next(
            (
                item
                for item in observation.results
                if domain_matches(item.domain, customer_domain)
            ),
            None,
        )

    relevant = (
        tuple(item for item in observation.results if item.position < customer_result.position)
        if customer_result is not None
        else observation.results
    )
    classified = tuple(
        classify_result(item, customer_domain=customer_domain)
        for item in relevant
    )
    if max_pages == 0:
        selected: tuple[ClassifiedSerpResult, ...] = ()
    else:
        chosen: list[ClassifiedSerpResult] = []
        seen_domains: set[str] = set()
        for item in classified:
            if not item.eligible_for_content_comparison:
                continue
            domain = canonical_hostname(item.result.domain)
            if domain in seen_domains:
                continue
            seen_domains.add(domain)
            chosen.append(item)
            if len(chosen) >= max_pages:
                break
        selected = tuple(chosen)

    return CompetitiveSelection(
        query=result.request.query,
        customer_domain=customer_domain,
        customer_result=customer_result,
        classified_results=classified,
        selected_candidates=selected,
    )
