"""Composition root for SERP providers, persistence and evidence sinks."""
from __future__ import annotations

from dataclasses import dataclass, replace
import os
from pathlib import Path
from typing import Iterable, Mapping

from .budget import RequestBudget
from .config import SERPAPI_KEY_ENV, SerpRuntimeConfig
from .evidence import FilesystemSerpEvidenceSink
from .models import DomainMatchStatus, SearchIntelligenceResult, SerpQueryRequest
from .persistence import SerpObservationRepository
from .providers import FixtureSerpProvider, SerpApiProvider
from .service import SearchIntelligenceService


@dataclass(frozen=True, slots=True)
class SearchExecution:
    mode: str
    provider: str
    results: tuple[SearchIntelligenceResult, ...]
    projected_http_request_ceiling: int
    actual_http_requests: int
    persisted: bool


_LIVE_PROVIDER_BUILDERS = {
    "serpapi": SerpApiProvider,
}


def live_provider_ids() -> tuple[str, ...]:
    return tuple(_LIVE_PROVIDER_BUILDERS)


def execute_search(
    requests: Iterable[SerpQueryRequest],
    *,
    config: SerpRuntimeConfig,
    environment: Mapping[str, str] | None = None,
    workspace_root: Path | None = None,
    fixture_path: Path | None = None,
) -> SearchExecution:
    if fixture_path is not None:
        config = replace(config, fixture_path=fixture_path)
    config = config.validate()
    items = tuple(requests)
    if len(items) > config.max_queries:
        raise ValueError(
            f"SERP query count {len(items)} exceeds configured max_queries {config.max_queries}"
        )
    for item in items:
        if item.depth > config.max_depth:
            raise ValueError(
                f"requested SERP depth {item.depth} exceeds configured max_depth {config.max_depth}"
            )

    projected = config.worst_case_http_requests(len(items))
    if projected > config.max_requests:
        raise ValueError(
            f"worst-case SERP HTTP requests {projected} exceed configured max_requests {config.max_requests}; "
            "reduce queries/retries or raise the explicit limit"
        )

    if config.mode == "disabled":
        disabled_results = tuple(
            SearchIntelligenceResult(
                request=item,
                observation=None,
                domain_status=DomainMatchStatus.DISABLED,
                customer_position=None,
            )
            for item in items
        )
        return SearchExecution(
            mode="disabled",
            provider="none",
            results=disabled_results,
            projected_http_request_ceiling=0,
            actual_http_requests=0,
            persisted=False,
        )

    repository = None
    evidence_sink = None
    audit_id = None
    if workspace_root is not None:
        repository = SerpObservationRepository.from_workspace(workspace_root)
        audit_id = repository.audit_id
        evidence_sink = FilesystemSerpEvidenceSink(
            workspace_root=workspace_root,
            artifacts_root=workspace_root / "artifacts",
        )

    budget = RequestBudget(config.max_requests)
    if config.mode == "fixture":
        selected_fixture = fixture_path or config.fixture_path
        if selected_fixture is None:
            raise ValueError("SERP fixture mode requires a fixture path")
        provider = FixtureSerpProvider(selected_fixture)
        provider_name = "fixture"
    else:
        provider_id = config.provider
        builder = _LIVE_PROVIDER_BUILDERS.get(provider_id)
        if builder is None:
            available = ", ".join(live_provider_ids())
            raise ValueError(f"unsupported live SERP provider {provider_id!r}; available: {available}")
        env = os.environ if environment is None else environment
        api_key = (env.get(SERPAPI_KEY_ENV) or "").strip()
        provider = builder(
            api_key=api_key,
            timeout_seconds=config.timeout_seconds,
            retries=config.retries,
            min_interval_seconds=config.min_interval_seconds,
            budget=budget,
        )
        provider_name = provider_id

    class _BoundRepository:
        def save(self, result: SearchIntelligenceResult) -> None:
            if repository is not None and audit_id is not None:
                repository.save(result)

    service = SearchIntelligenceService(
        provider=provider,
        max_queries=config.max_queries,
        max_depth=config.max_depth,
        max_competitors=config.max_competitors,
        evidence_sink=evidence_sink,
        repository=_BoundRepository() if repository is not None else None,
    )
    try:
        results = service.observe_many(items)
    finally:
        if repository is not None:
            repository.close()
    return SearchExecution(
        mode=config.mode,
        provider=provider_name,
        results=results,
        projected_http_request_ceiling=projected,
        actual_http_requests=budget.used if config.mode == "live" else 0,
        persisted=workspace_root is not None,
    )
