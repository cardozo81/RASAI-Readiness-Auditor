"""Provider-neutral Search Intelligence application service."""
from __future__ import annotations

from dataclasses import replace
from typing import Iterable, Protocol

from .domain import canonical_hostname, domain_matches
from .evidence import SerpEvidenceSink
from .models import (
    DomainMatchStatus,
    SearchIntelligenceResult,
    SerpObservation,
    SerpObservationStatus,
    SerpQueryRequest,
    new_identifier,
    utc_now,
)
from .provider import (
    SerpProvider,
    SerpProviderError,
    SerpProviderUnavailable,
)


class SerpResultRepository(Protocol):
    def save(self, result: SearchIntelligenceResult) -> None: ...


def analyze_observation(
    request: SerpQueryRequest,
    observation: SerpObservation,
    *,
    max_competitors: int,
) -> SearchIntelligenceResult:
    if max_competitors < 0:
        raise ValueError("max_competitors must be >= 0")
    if observation.status is SerpObservationStatus.UNAVAILABLE:
        return SearchIntelligenceResult(
            request=request,
            observation=observation,
            domain_status=DomainMatchStatus.UNAVAILABLE,
            customer_position=None,
            error_code=str(observation.quality_metadata.get("error_code") or "SERP_PROVIDER_UNAVAILABLE"),
            error_message=str(observation.quality_metadata.get("error_message") or "provider unavailable"),
        )
    if observation.status is SerpObservationStatus.ERROR:
        return SearchIntelligenceResult(
            request=request,
            observation=observation,
            domain_status=DomainMatchStatus.ERROR,
            customer_position=None,
            error_code=str(observation.quality_metadata.get("error_code") or "SERP_PROVIDER_ERROR"),
            error_message=str(observation.quality_metadata.get("error_message") or "provider error"),
        )
    if not request.domain_of_interest:
        return SearchIntelligenceResult(
            request=request,
            observation=observation,
            domain_status=DomainMatchStatus.NOT_REQUESTED,
            customer_position=None,
        )

    interest = canonical_hostname(request.domain_of_interest)
    customer_result = next(
        (
            result
            for result in observation.results
            if domain_matches(result.domain, interest)
        ),
        None,
    )
    if customer_result is None:
        if observation.quality_metadata.get("requested_depth_complete") is False:
            return SearchIntelligenceResult(
                request=request,
                observation=observation,
                domain_status=DomainMatchStatus.UNAVAILABLE,
                customer_position=None,
                error_code="SERP_REQUESTED_DEPTH_INCOMPLETE",
                error_message=(
                    "requested SERP depth was not fully observed within the bounded provider request budget"
                ),
            )
        return SearchIntelligenceResult(
            request=request,
            observation=observation,
            domain_status=DomainMatchStatus.NOT_FOUND_WITHIN_DEPTH,
            customer_position=None,
        )

    ahead = tuple(
        result for result in observation.results if result.position < customer_result.position
    )
    competitor_domains: list[str] = []
    if max_competitors == 0:
        return SearchIntelligenceResult(
            request=request,
            observation=observation,
            domain_status=DomainMatchStatus.FOUND,
            customer_position=customer_result.position,
            results_ahead=ahead,
            competitor_domains_ahead=(),
        )
    for result in ahead:
        if domain_matches(result.domain, interest):
            continue
        normalized = canonical_hostname(result.domain)
        if normalized not in competitor_domains:
            competitor_domains.append(normalized)
        if len(competitor_domains) >= max_competitors:
            break
    return SearchIntelligenceResult(
        request=request,
        observation=observation,
        domain_status=DomainMatchStatus.FOUND,
        customer_position=customer_result.position,
        results_ahead=ahead,
        competitor_domains_ahead=tuple(competitor_domains),
    )


class SearchIntelligenceService:
    def __init__(
        self,
        *,
        provider: SerpProvider,
        max_queries: int = 10,
        max_depth: int = 20,
        max_competitors: int = 10,
        evidence_sink: SerpEvidenceSink | None = None,
        repository: SerpResultRepository | None = None,
    ) -> None:
        if max_queries <= 0:
            raise ValueError("max_queries must be greater than zero")
        if max_depth <= 0:
            raise ValueError("max_depth must be greater than zero")
        if max_competitors < 0:
            raise ValueError("max_competitors must be >= 0")
        self._provider = provider
        self._max_queries = max_queries
        self._max_depth = max_depth
        self._max_competitors = max_competitors
        self._evidence_sink = evidence_sink
        self._repository = repository

    def _error_observation(
        self,
        request: SerpQueryRequest,
        *,
        status: SerpObservationStatus,
        error: SerpProviderError,
    ) -> SerpObservation:
        return SerpObservation(
            observation_id=new_identifier("SERP"),
            run_id=request.run_id,
            query=request.query,
            query_origin=request.query_origin,
            engine=request.engine,
            country=request.country,
            region=request.region,
            language=request.language,
            device=request.device,
            collected_at=utc_now(),
            provider=self._provider.provider_id,
            provider_request_id=None,
            requested_depth=request.depth,
            result_count=0,
            results=(),
            data_mode=self._provider.data_mode,
            status=status,
            config_metadata=dict(request.config_metadata),
            quality_metadata={
                "error_code": getattr(error, "code", "SERP_PROVIDER_ERROR"),
                "error_message": str(error)[:512],
            },
        )

    def observe(self, request: SerpQueryRequest) -> SearchIntelligenceResult:
        request.validate()
        if request.domain_of_interest:
            canonical_hostname(request.domain_of_interest)
        if request.depth > self._max_depth:
            raise ValueError(
                f"requested SERP depth {request.depth} exceeds configured max_depth {self._max_depth}"
            )
        try:
            provider_response = self._provider.observe(request)
            observation = provider_response.observation
            bounded_results = tuple(
                item for item in observation.results if item.position <= request.depth
            )
            if len(bounded_results) != len(observation.results):
                quality = dict(observation.quality_metadata)
                quality["results_outside_requested_depth_dropped"] = (
                    len(observation.results) - len(bounded_results)
                )
                observation = replace(
                    observation,
                    results=bounded_results,
                    result_count=len(bounded_results),
                    quality_metadata=quality,
                )
            if provider_response.raw_evidence is not None and self._evidence_sink is not None:
                stored = self._evidence_sink.store(
                    observation.observation_id,
                    provider_response.raw_evidence,
                    provider_response.content_type,
                )
                observation = replace(
                    observation,
                    raw_evidence_ref=stored.reference,
                    raw_evidence_sha256=stored.sha256,
                )
        except SerpProviderUnavailable as exc:
            observation = self._error_observation(
                request, status=SerpObservationStatus.UNAVAILABLE, error=exc
            )
        except SerpProviderError as exc:
            observation = self._error_observation(
                request, status=SerpObservationStatus.ERROR, error=exc
            )

        result = analyze_observation(
            request,
            observation,
            max_competitors=self._max_competitors,
        )
        if self._repository is not None:
            self._repository.save(result)
        return result

    def observe_many(self, requests: Iterable[SerpQueryRequest]) -> tuple[SearchIntelligenceResult, ...]:
        items = tuple(requests)
        if len(items) > self._max_queries:
            raise ValueError(
                f"SERP query count {len(items)} exceeds configured max_queries {self._max_queries}"
            )
        return tuple(self.observe(request) for request in items)
