"""Runtime orchestration for Competitive Search & Content Intelligence."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .competitive import select_competitive_candidates
from .competitive_persistence import (
    CompetitiveIntelligenceRepository,
    FilesystemCompetitiveEvidenceSink,
)
from .content import (
    CompetitiveContentAnalysis,
    PublicWebFetcher,
    analyze_competitive_content,
)
from .runtime import SearchExecution, _refresh_search_intelligence_report


@dataclass(frozen=True, slots=True)
class CompetitiveExecution:
    analyses: tuple[CompetitiveContentAnalysis, ...]
    content_enabled: bool
    content_http_requests: int
    persisted: bool


def execute_competitive_intelligence(
    search_execution: SearchExecution,
    *,
    content_enabled: bool = False,
    customer_url: str | None = None,
    max_competitor_pages: int = 3,
    workspace_root: Path | None = None,
    fetcher: PublicWebFetcher | None = None,
) -> CompetitiveExecution:
    """Classify SERP results and optionally inspect customer/competitor content.

    Classification itself causes no network traffic. Content acquisition is a separate,
    explicit opt-in path and is intentionally non-scoring.
    """
    if max_competitor_pages < 0:
        raise ValueError("max_competitor_pages must be >= 0")
    if customer_url and len(search_execution.results) != 1:
        raise ValueError(
            "an explicit customer_url can only be used when exactly one query is executed"
        )

    shared_fetcher = fetcher
    if content_enabled and shared_fetcher is None:
        shared_fetcher = PublicWebFetcher()

    repository = None
    sink = None
    if workspace_root is not None:
        repository = CompetitiveIntelligenceRepository.from_workspace(workspace_root)
        sink = FilesystemCompetitiveEvidenceSink(workspace_root)

    analyses: list[CompetitiveContentAnalysis] = []
    try:
        for search_result in search_execution.results:
            observation = search_result.observation
            selection = select_competitive_candidates(
                search_result,
                max_pages=max_competitor_pages,
            )
            if observation is None or observation.status.value != "OBSERVED":
                analysis = CompetitiveContentAnalysis(
                    selection=selection,
                    customer_page=None,
                    competitor_pages=(),
                    gaps=(),
                    comparison_status="SERP_OBSERVATION_UNAVAILABLE",
                )
            elif content_enabled:
                analysis = analyze_competitive_content(
                    search_result,
                    customer_url=customer_url,
                    max_competitor_pages=max_competitor_pages,
                    fetcher=shared_fetcher,
                )
            else:
                analysis = CompetitiveContentAnalysis(
                    selection=selection,
                    customer_page=None,
                    competitor_pages=(),
                    gaps=(),
                    comparison_status="CONTENT_COMPARISON_DISABLED",
                )
            analyses.append(analysis)

            if repository is not None and observation is not None:
                evidence_ref = None
                evidence_sha256 = None
                if sink is not None:
                    evidence_ref, evidence_sha256 = sink.write(
                        observation.observation_id, analysis
                    )
                repository.save(
                    observation.observation_id,
                    analysis,
                    evidence_ref=evidence_ref,
                    evidence_sha256=evidence_sha256,
                )
    finally:
        if repository is not None:
            repository.close()

    # Refresh only from persisted evidence. A reporting failure is deliberately
    # fail-open and cannot change the Search/competitive execution result.
    _refresh_search_intelligence_report(workspace_root)
    return CompetitiveExecution(
        analyses=tuple(analyses),
        content_enabled=content_enabled,
        content_http_requests=(
            shared_fetcher.requests_used
            if content_enabled and shared_fetcher is not None
            else 0
        ),
        persisted=workspace_root is not None,
    )
