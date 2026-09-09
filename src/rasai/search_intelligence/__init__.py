"""Search Intelligence: provider-neutral SERP and competitive observation."""
from .competitive import (
    ClassifiedSerpResult,
    CompetitiveSelection,
    SearchResultClass,
    classify_result,
    select_competitive_candidates,
)
from .content import (
    CompetitiveContentAnalysis,
    CompetitiveGap,
    CompetitivePageFeatures,
    ContentFetchStatus,
    PublicWebFetcher,
    analyze_competitive_content,
    compare_content_features,
    extract_page_features,
    query_terms,
)
from .models import (
    DomainMatchStatus,
    QueryOrigin,
    SearchIntelligenceResult,
    SerpDataMode,
    SerpObservation,
    SerpObservationStatus,
    SerpQueryRequest,
    SerpResult,
)
from .provider import SerpProvider
from .service import SearchIntelligenceService, analyze_observation

__all__ = [
    "ClassifiedSerpResult",
    "CompetitiveContentAnalysis",
    "CompetitiveGap",
    "CompetitivePageFeatures",
    "CompetitiveSelection",
    "ContentFetchStatus",
    "DomainMatchStatus",
    "PublicWebFetcher",
    "QueryOrigin",
    "SearchIntelligenceResult",
    "SearchIntelligenceService",
    "SearchResultClass",
    "SerpDataMode",
    "SerpObservation",
    "SerpObservationStatus",
    "SerpProvider",
    "SerpQueryRequest",
    "SerpResult",
    "analyze_competitive_content",
    "analyze_observation",
    "classify_result",
    "compare_content_features",
    "extract_page_features",
    "query_terms",
    "select_competitive_candidates",
]
