"""Composition root for SERP providers, persistence and evidence sinks."""
from __future__ import annotations

from dataclasses import dataclass, replace
import os
from pathlib import Path
import sqlite3
from typing import Iterable, Mapping

from .budget import RequestBudget
from .config import SERPAPI_KEY_ENV, SerpRuntimeConfig
from .evidence import FilesystemSerpEvidenceSink, SerpEvidenceSink
from .models import DomainMatchStatus, SearchIntelligenceResult, SerpQueryRequest
from .persistence import SerpObservationRepository
from .providers import FixtureSerpProvider, SerpApiBingProvider, SerpApiProvider
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
    "serpapi-bing": SerpApiBingProvider,
}


def live_provider_ids() -> tuple[str, ...]:
    return tuple(_LIVE_PROVIDER_BUILDERS)


def _refresh_search_intelligence_report(workspace_root: Path | None) -> None:
    """Best-effort projection of already-persisted Search Intelligence evidence.

    Report rendering is ancillary to observation persistence. A presentation failure must
    not turn a successfully persisted SERP observation into a provider/runtime failure.
    The report can always be regenerated from audit.db later.
    """
    if workspace_root is None:
        return
    try:
        from .reporting import write_search_intelligence_report

        write_search_intelligence_report(workspace_root)
    except (OSError, ValueError, sqlite3.Error):
        return


def _projected_request_ceiling(
    items: tuple[SerpQueryRequest, ...], config: SerpRuntimeConfig
) -> int:
    if config.mode != "live" or not items:
        return 0
    if config.provider == "serpapi-bing":
        # Bing exposes provider-driven variable pagination. The global hard request budget
        # is therefore the only safe preflight ceiling; the adapter stops when that budget
        # cannot continue the requested depth.
        return config.max_requests
    return sum(config.worst_case_http_requests(1, depth=item.depth) for item in items)


def execute_search(
    requests: Iterable[SerpQueryRequest],
    *,
    config: SerpRuntimeConfig,
    environment: Mapping[str, str] | None = None,
    workspace_root: Path | None = None,
    fixture_path: Path | None = None,
    evidence_sink: SerpEvidenceSink | None = None,
) -> SearchExecution:
    """Execute provider-neutral Search observation.

    ``workspace_root`` retains the legacy per-audit persistence behavior. ``evidence_sink``
    is an additive operational seam used by recurring monitoring so raw provider evidence
    can be stored without mutating immutable ``AUD-*/audit.db`` workspaces.
    """
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

    projected = _projected_request_ceiling(items, config)
    if config.provider != "serpapi-bing" and projected > config.max_requests:
        raise ValueError(
            f"worst-case SERP HTTP requests {projected} exceed configured max_requests {config.max_requests}; "
            "reduce queries/depth/retries or raise the explicit limit"
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
    audit_id = None
    selected_evidence_sink = evidence_sink
    if workspace_root is not None:
        repository = SerpObservationRepository.from_workspace(workspace_root)
        audit_id = repository.audit_id
        if selected_evidence_sink is None:
            selected_evidence_sink = FilesystemSerpEvidenceSink(
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
        evidence_sink=selected_evidence_sink,
        repository=_BoundRepository() if repository is not None else None,
    )
    try:
        results = service.observe_many(items)
    finally:
        if repository is not None:
            repository.close()
    _refresh_search_intelligence_report(workspace_root)
    return SearchExecution(
        mode=config.mode,
        provider=provider_name,
        results=results,
        projected_http_request_ceiling=projected,
        actual_http_requests=budget.used if config.mode == "live" else 0,
        persisted=workspace_root is not None,
    )
