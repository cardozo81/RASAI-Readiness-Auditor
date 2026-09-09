"""Search Intelligence foundation: provider-neutral SERP observation."""
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
    "DomainMatchStatus",
    "QueryOrigin",
    "SearchIntelligenceResult",
    "SearchIntelligenceService",
    "SerpDataMode",
    "SerpObservation",
    "SerpObservationStatus",
    "SerpProvider",
    "SerpQueryRequest",
    "SerpResult",
    "analyze_observation",
]
