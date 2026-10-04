"""Canonical execution cadence for one logical RASAi AI need.

This module owns cycle scheduling and inter-cycle timers. Provider adapters remain
single-call transports; requirement acceptance/persistence remains owned by each
consumer/governed task.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import math
import time
from typing import Any, Callable, Iterable, Sequence


DEFAULT_AI_MAX_CYCLES = 3
DEFAULT_AI_CYCLE_DELAY_SECONDS = 60.0
MAX_AI_MAX_CYCLES = 10
MAX_AI_CYCLE_DELAY_SECONDS = 300.0
MAX_AI_RETRY_AFTER_SECONDS = 300.0

AI_MAX_CYCLES_ENV = "RASAI_AI_MAX_CYCLES"
AI_CYCLE_DELAY_ENV = "RASAI_AI_CYCLE_DELAY_SECONDS"


class AiProviderOutcome(StrEnum):
    COMPLETE = "COMPLETE"
    PARTIAL_PROGRESS = "PARTIAL_PROGRESS"
    NO_PROGRESS = "NO_PROGRESS"
    TRANSIENT_FAILURE = "TRANSIENT_FAILURE"
    PROVIDER_TERMINAL = "PROVIDER_TERMINAL"
    INPUT_BLOCKED = "INPUT_BLOCKED"


class AiNeedFinalState(StrEnum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    UNAVAILABLE = "UNAVAILABLE"
    INPUT_BLOCKED = "INPUT_BLOCKED"


@dataclass(frozen=True, slots=True)
class AiExecutionPolicy:
    max_cycles: int = DEFAULT_AI_MAX_CYCLES
    cycle_delay_seconds: float = DEFAULT_AI_CYCLE_DELAY_SECONDS
    retry_after_cap_seconds: float = MAX_AI_RETRY_AFTER_SECONDS

    def __post_init__(self) -> None:
        if isinstance(self.max_cycles, bool) or not 1 <= int(self.max_cycles) <= MAX_AI_MAX_CYCLES:
            raise ValueError(f"max_cycles must be between 1 and {MAX_AI_MAX_CYCLES}")
        delay = float(self.cycle_delay_seconds)
        if not math.isfinite(delay) or delay < 0 or delay > MAX_AI_CYCLE_DELAY_SECONDS:
            raise ValueError(
                f"cycle_delay_seconds must be between 0 and {MAX_AI_CYCLE_DELAY_SECONDS:g}"
            )
        cap = float(self.retry_after_cap_seconds)
        if not math.isfinite(cap) or cap < 0 or cap > MAX_AI_RETRY_AFTER_SECONDS:
            raise ValueError(
                f"retry_after_cap_seconds must be between 0 and {MAX_AI_RETRY_AFTER_SECONDS:g}"
            )


@dataclass(frozen=True, slots=True)
class AiProviderInvocation:
    outcome: AiProviderOutcome
    retry_after_seconds: float | None = None


@dataclass(frozen=True, slots=True)
class AiNeedExecution:
    state: AiNeedFinalState
    cycles_executed: int
    provider_calls: int
    progress_observed: bool
    last_outcome: AiProviderOutcome | None = None



TERMINAL_PROVIDER_ERROR_CLASSES = frozenset({
    "AUTH_ERROR",
    "CREDIT_ERROR",
    "QUOTA_ERROR",
    "MODEL_ERROR",
    "PERMISSION_ERROR",
})


def provider_error_token(error_class: Any) -> str:
    return str(getattr(error_class, "value", error_class) or "").strip().upper()


def is_terminal_provider_error(error_class: Any) -> bool:
    """Classify deterministically terminal provider failures by normalized class."""
    return provider_error_token(error_class) in TERMINAL_PROVIDER_ERROR_CLASSES


def invocation_from_diagnostic(diagnostic: Any) -> AiProviderInvocation:
    """Translate a normalized adapter diagnostic into orchestration semantics."""
    error_class = getattr(diagnostic, "error_class", None) if diagnostic is not None else None
    outcome = (
        AiProviderOutcome.PROVIDER_TERMINAL
        if is_terminal_provider_error(error_class)
        else AiProviderOutcome.TRANSIENT_FAILURE
    )
    return AiProviderInvocation(
        outcome,
        getattr(diagnostic, "retry_after_seconds", None) if diagnostic is not None else None,
    )

def _provider_key(candidate: Any) -> str:
    return str(getattr(candidate, "name", candidate)).strip().upper()


def unique_cycle_candidates(candidates: Iterable[Any]) -> tuple[Any, ...]:
    """Deduplicate one cycle by provider identity while retaining deterministic order."""
    seen: set[str] = set()
    output: list[Any] = []
    for candidate in candidates:
        key = _provider_key(candidate)
        if not key or key in seen:
            continue
        seen.add(key)
        output.append(candidate)
    return tuple(output)


def effective_cycle_delay(
    configured_delay_seconds: float,
    retry_after_seconds: Iterable[float | None] = (),
    *,
    cap_seconds: float = MAX_AI_RETRY_AFTER_SECONDS,
) -> float:
    """Return the sole inter-cycle delay, respecting bounded Retry-After hints."""
    configured = max(0.0, float(configured_delay_seconds))
    cap = max(0.0, min(float(cap_seconds), MAX_AI_RETRY_AFTER_SECONDS))
    retry_delay = 0.0
    for raw in retry_after_seconds:
        if raw is None:
            continue
        try:
            value = float(raw)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(value) or value < 0:
            continue
        retry_delay = max(retry_delay, min(value, cap))
    return max(configured, retry_delay)


def run_ai_need(
    *,
    candidates: Callable[[], Sequence[Any]],
    invoke: Callable[[Any, int, int], AiProviderInvocation],
    policy: AiExecutionPolicy,
    sleeper: Callable[[float], None] = time.sleep,
) -> AiNeedExecution:
    """Execute one logical need with one call/provider/cycle and one timer owner.

    Candidate eligibility is re-evaluated before each cycle so execution-wide
    terminal quarantine survives across separate logical needs while every call to
    this function starts again at cycle 1.
    """
    progress = False
    calls = 0
    last_outcome: AiProviderOutcome | None = None
    cycles_executed = 0

    for cycle in range(1, policy.max_cycles + 1):
        pool = unique_cycle_candidates(candidates())
        if not pool:
            break
        cycles_executed = cycle
        retry_after_values: list[float | None] = []

        for candidate in pool:
            calls += 1
            result = invoke(candidate, cycle, calls)
            if not isinstance(result, AiProviderInvocation):
                raise TypeError("invoke must return AiProviderInvocation")
            last_outcome = result.outcome

            if result.outcome is AiProviderOutcome.COMPLETE:
                return AiNeedExecution(
                    AiNeedFinalState.COMPLETE,
                    cycles_executed,
                    calls,
                    True,
                    result.outcome,
                )
            if result.outcome is AiProviderOutcome.INPUT_BLOCKED:
                return AiNeedExecution(
                    AiNeedFinalState.INPUT_BLOCKED,
                    cycles_executed,
                    calls,
                    progress,
                    result.outcome,
                )
            if result.outcome is AiProviderOutcome.PARTIAL_PROGRESS:
                progress = True
            elif result.outcome is AiProviderOutcome.TRANSIENT_FAILURE:
                retry_after_values.append(result.retry_after_seconds)

        if cycle >= policy.max_cycles:
            break

        if not unique_cycle_candidates(candidates()):
            break

        delay = effective_cycle_delay(
            policy.cycle_delay_seconds,
            retry_after_values,
            cap_seconds=policy.retry_after_cap_seconds,
        )
        if delay > 0:
            sleeper(delay)

    return AiNeedExecution(
        AiNeedFinalState.PARTIAL if progress else AiNeedFinalState.UNAVAILABLE,
        cycles_executed,
        calls,
        progress,
        last_outcome,
    )
