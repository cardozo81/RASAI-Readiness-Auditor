"""Provider-independent Search/SERP observation models."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Mapping
from uuid import uuid4


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def new_identifier(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex.upper()}"


class SerpDataMode(str, Enum):
    OBSERVED_API = "OBSERVED_API"
    OBSERVED_SYNTHETIC = "OBSERVED_SYNTHETIC"
    IMPORTED = "IMPORTED"
    FIXTURE = "FIXTURE"
    MODELED = "MODELED"
    AI_INFERRED = "AI_INFERRED"


class SerpObservationStatus(str, Enum):
    OBSERVED = "OBSERVED"
    UNAVAILABLE = "UNAVAILABLE"
    ERROR = "ERROR"


class DomainMatchStatus(str, Enum):
    FOUND = "FOUND"
    NOT_FOUND_WITHIN_DEPTH = "NOT_FOUND_WITHIN_DEPTH"
    NOT_REQUESTED = "NOT_REQUESTED"
    UNAVAILABLE = "UNAVAILABLE"
    ERROR = "ERROR"
    DISABLED = "DISABLED"


class QueryOrigin(str, Enum):
    MANUAL = "MANUAL"
    SEARCH_CONSOLE = "SEARCH_CONSOLE"
    BING_WEBMASTER = "BING_WEBMASTER"
    PAGE_CONTENT = "PAGE_CONTENT"
    AI_HYPOTHESIS = "AI_HYPOTHESIS"
    SERP_RELATED = "SERP_RELATED"
    COMPETITOR_DISCOVERY = "COMPETITOR_DISCOVERY"
    EXTERNAL = "EXTERNAL"


@dataclass(frozen=True, slots=True)
class SerpQueryRequest:
    query: str
    engine: str = "google"
    country: str = "BR"
    region: str | None = None
    language: str = "pt-BR"
    device: str = "desktop"
    depth: int = 20
    requested_at: datetime = field(default_factory=utc_now)
    domain_of_interest: str | None = None
    run_id: str = field(default_factory=lambda: new_identifier("SERP-RUN"))
    query_origin: QueryOrigin = QueryOrigin.MANUAL
    config_metadata: Mapping[str, Any] = field(default_factory=dict)

    def validate(self) -> "SerpQueryRequest":
        if not self.query.strip():
            raise ValueError("SERP query must not be empty")
        if not self.engine.strip():
            raise ValueError("SERP engine must not be empty")
        if not self.country.strip():
            raise ValueError("SERP country must not be empty")
        if not self.language.strip():
            raise ValueError("SERP language must not be empty")
        if not self.device.strip():
            raise ValueError("SERP device must not be empty")
        if self.depth <= 0:
            raise ValueError("SERP depth must be greater than zero")
        if not self.run_id.strip():
            raise ValueError("SERP run_id must not be empty")
        return self


@dataclass(frozen=True, slots=True)
class SerpResult:
    position: int
    domain: str
    url: str
    title: str | None = None
    snippet: str | None = None
    result_type: str = "organic"
    serp_features: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def validate(self) -> "SerpResult":
        if self.position <= 0:
            raise ValueError("SERP result position must be greater than zero")
        if not self.domain:
            raise ValueError("SERP result domain must not be empty")
        if not self.url:
            raise ValueError("SERP result URL must not be empty")
        if not self.result_type:
            raise ValueError("SERP result type must not be empty")
        return self


@dataclass(frozen=True, slots=True)
class SerpObservation:
    observation_id: str
    run_id: str
    query: str
    query_origin: QueryOrigin
    engine: str
    country: str
    region: str | None
    language: str
    device: str
    collected_at: datetime
    provider: str
    provider_request_id: str | None
    requested_depth: int
    result_count: int
    results: tuple[SerpResult, ...]
    data_mode: SerpDataMode
    status: SerpObservationStatus = SerpObservationStatus.OBSERVED
    raw_evidence_ref: str | None = None
    raw_evidence_sha256: str | None = None
    config_metadata: Mapping[str, Any] = field(default_factory=dict)
    quality_metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class SearchIntelligenceResult:
    request: SerpQueryRequest
    observation: SerpObservation | None
    domain_status: DomainMatchStatus
    customer_position: int | None
    results_ahead: tuple[SerpResult, ...] = ()
    competitor_domains_ahead: tuple[str, ...] = ()
    error_code: str | None = None
    error_message: str | None = None

    @property
    def found(self) -> bool:
        return self.domain_status is DomainMatchStatus.FOUND
