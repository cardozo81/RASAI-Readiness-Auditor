"""Runtime orchestration for evidence-bound Competitive AI."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .competitive_ai import (
    CompetitiveAiProvider,
    CompetitiveAiResult,
    CompetitiveAiState,
    build_competitive_ai_input,
)
from .competitive_ai_persistence import (
    CompetitiveAiRepository,
    FilesystemCompetitiveAiEvidenceSink,
)
from .competitive_runtime import CompetitiveExecution
from .runtime import SearchExecution


@dataclass(frozen=True, slots=True)
class CompetitiveAiExecution:
    results: tuple[CompetitiveAiResult, ...]
    provider: str
    eligible_analyses: int
    provider_calls: int
    persisted: bool


def _actual_provider_call_delta(provider: CompetitiveAiProvider, before: object) -> int:
    """Return observed network-call delta when the adapter exposes a call counter.

    Built-in live adapters expose ``calls`` and increment it only when a provider request is
    actually attempted. Provider-neutral third-party adapters without that surface are counted
    conservatively after analyze unless they report NOT_CONFIGURED.
    """
    after = getattr(provider, "calls", None)
    if isinstance(before, int) and not isinstance(before, bool) and isinstance(after, int):
        return max(after - before, 0)
    return -1


def execute_competitive_ai(
    search_execution: SearchExecution,
    competitive_execution: CompetitiveExecution,
    *,
    provider: CompetitiveAiProvider,
    market: str,
    language: str,
    ymyl_mode: str = "AUTO",
    workspace_root: Path | None = None,
) -> CompetitiveAiExecution:
    """Run AI only after deterministic content comparison has consolidated evidence."""
    if len(search_execution.results) != len(competitive_execution.analyses):
        raise ValueError("search and competitive executions must have the same result count")

    repository = None
    sink = None
    if workspace_root is not None:
        repository = CompetitiveAiRepository.from_workspace(workspace_root)
        sink = FilesystemCompetitiveAiEvidenceSink(workspace_root)

    outputs: list[CompetitiveAiResult] = []
    eligible = 0
    provider_calls = 0
    try:
        for search_result, analysis in zip(
            search_execution.results,
            competitive_execution.analyses,
            strict=True,
        ):
            observation = search_result.observation
            if observation is None:
                outputs.append(
                    CompetitiveAiResult(
                        CompetitiveAiState.NOT_ELIGIBLE,
                        reason="COMPETITIVE_AI_REQUIRES_SERP_OBSERVATION",
                    )
                )
                continue

            if analysis.comparison_status != "CONSOLIDATED":
                result = CompetitiveAiResult(
                    CompetitiveAiState.NOT_ELIGIBLE,
                    reason=(
                        "COMPETITIVE_AI_REQUIRES_CONSOLIDATED_CONTENT:"
                        + analysis.comparison_status
                    ),
                )
            else:
                eligible += 1
                artifact_ref = None
                if workspace_root is not None:
                    candidate = (
                        Path(workspace_root)
                        / "artifacts"
                        / "search-intelligence"
                        / "competitive"
                        / f"{observation.observation_id}.json"
                    )
                    if candidate.is_file():
                        artifact_ref = candidate.relative_to(workspace_root).as_posix()
                competitive_input = build_competitive_ai_input(
                    observation.observation_id,
                    analysis,
                    market=market,
                    language=language,
                    ymyl_mode=ymyl_mode,
                    artifact_reference=artifact_ref,
                )
                calls_before = getattr(provider, "calls", None)
                result = provider.analyze(competitive_input)
                delta = _actual_provider_call_delta(provider, calls_before)
                if delta >= 0:
                    provider_calls += delta
                elif (
                    provider.name not in {"NONE", "FIXTURE"}
                    and result.state is not CompetitiveAiState.NOT_CONFIGURED
                ):
                    provider_calls += 1

            outputs.append(result)
            if repository is not None:
                evidence_ref = None
                evidence_sha256 = None
                if sink is not None:
                    evidence_ref, evidence_sha256 = sink.write(
                        observation.observation_id,
                        result,
                    )
                repository.save(
                    observation.observation_id,
                    result,
                    evidence_ref=evidence_ref,
                    evidence_sha256=evidence_sha256,
                )
    finally:
        if repository is not None:
            repository.close()

    return CompetitiveAiExecution(
        results=tuple(outputs),
        provider=provider.name,
        eligible_analyses=eligible,
        provider_calls=provider_calls,
        persisted=workspace_root is not None,
    )
