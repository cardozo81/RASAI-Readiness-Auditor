from __future__ import annotations

from dataclasses import dataclass

import pytest

from rasai.ai_canonical_orchestration import (
    AiExecutionPolicy,
    AiNeedFinalState,
    AiProviderInvocation,
    AiProviderOutcome,
    effective_cycle_delay,
    invocation_from_diagnostic,
    run_ai_need,
)
from rasai.m18_ai import ProviderDiagnostic, ProviderErrorClass
from rasai.provider_runtime_policy import (
    build_semantic_provider,
    configured_ai_cycle_delay_seconds,
    configured_ai_execution_policy,
    configured_ai_max_cycles,
)


@dataclass
class _Candidate:
    name: str


def test_single_provider_uses_three_cycles_without_hidden_retry() -> None:
    candidate = _Candidate("A")
    calls: list[tuple[str, int, int]] = []
    sleeps: list[float] = []

    execution = run_ai_need(
        candidates=lambda: (candidate,),
        invoke=lambda item, cycle, attempt: (
            calls.append((item.name, cycle, attempt))
            or AiProviderInvocation(AiProviderOutcome.TRANSIENT_FAILURE)
        ),
        policy=AiExecutionPolicy(max_cycles=3, cycle_delay_seconds=60),
        sleeper=sleeps.append,
    )

    assert execution.state is AiNeedFinalState.UNAVAILABLE
    assert calls == [("A", 1, 1), ("A", 2, 2), ("A", 3, 3)]
    assert sleeps == [60, 60]


def test_multiple_providers_are_called_once_each_per_cycle() -> None:
    candidates = (_Candidate("A"), _Candidate("B"))
    calls: list[tuple[str, int]] = []

    execution = run_ai_need(
        candidates=lambda: candidates,
        invoke=lambda item, cycle, _attempt: (
            calls.append((item.name, cycle))
            or AiProviderInvocation(AiProviderOutcome.NO_PROGRESS)
        ),
        policy=AiExecutionPolicy(max_cycles=3, cycle_delay_seconds=0),
        sleeper=lambda _seconds: pytest.fail("zero delay must not sleep"),
    )

    assert execution.state is AiNeedFinalState.UNAVAILABLE
    assert calls == [
        ("A", 1), ("B", 1),
        ("A", 2), ("B", 2),
        ("A", 3), ("B", 3),
    ]


def test_complete_stops_remaining_providers_and_skips_wait() -> None:
    candidates = (_Candidate("A"), _Candidate("B"), _Candidate("C"))
    calls: list[str] = []

    execution = run_ai_need(
        candidates=lambda: candidates,
        invoke=lambda item, _cycle, _attempt: (
            calls.append(item.name)
            or AiProviderInvocation(
                AiProviderOutcome.COMPLETE
                if item.name == "B"
                else AiProviderOutcome.NO_PROGRESS
            )
        ),
        policy=AiExecutionPolicy(max_cycles=3, cycle_delay_seconds=60),
        sleeper=lambda _seconds: pytest.fail("complete must not wait"),
    )

    assert execution.state is AiNeedFinalState.COMPLETE
    assert calls == ["A", "B"]


def test_partial_progress_continues_to_next_provider_in_same_cycle() -> None:
    candidates = (_Candidate("A"), _Candidate("B"))
    calls: list[str] = []

    def invoke(item, _cycle, _attempt):
        calls.append(item.name)
        if item.name == "A":
            return AiProviderInvocation(AiProviderOutcome.PARTIAL_PROGRESS)
        return AiProviderInvocation(AiProviderOutcome.COMPLETE)

    execution = run_ai_need(
        candidates=lambda: candidates,
        invoke=invoke,
        policy=AiExecutionPolicy(max_cycles=3, cycle_delay_seconds=60),
        sleeper=lambda _seconds: pytest.fail("same-cycle completion must not wait"),
    )

    assert execution.state is AiNeedFinalState.COMPLETE
    assert execution.progress_observed is True
    assert calls == ["A", "B"]


def test_input_blocked_stops_without_trying_other_models() -> None:
    candidates = (_Candidate("A"), _Candidate("B"))
    calls: list[str] = []

    execution = run_ai_need(
        candidates=lambda: candidates,
        invoke=lambda item, _cycle, _attempt: (
            calls.append(item.name)
            or AiProviderInvocation(AiProviderOutcome.INPUT_BLOCKED)
        ),
        policy=AiExecutionPolicy(),
        sleeper=lambda _seconds: pytest.fail("input blocked must not wait"),
    )

    assert execution.state is AiNeedFinalState.INPUT_BLOCKED
    assert calls == ["A"]


def test_empty_pool_does_not_sleep() -> None:
    execution = run_ai_need(
        candidates=lambda: (),
        invoke=lambda *_args: pytest.fail("empty pool must not invoke"),
        policy=AiExecutionPolicy(),
        sleeper=lambda _seconds: pytest.fail("empty pool must not wait"),
    )
    assert execution.state is AiNeedFinalState.UNAVAILABLE
    assert execution.cycles_executed == 0
    assert execution.provider_calls == 0


def test_retry_after_is_applied_only_between_cycles_and_is_capped() -> None:
    assert effective_cycle_delay(60, (20, 120)) == 120
    assert effective_cycle_delay(60, (999,)) == 300
    assert effective_cycle_delay(0, (None, -1, float("nan"))) == 0


def test_normalized_error_class_not_http_status_drives_terminal_decision() -> None:
    terminal = invocation_from_diagnostic(
        ProviderDiagnostic(
            ProviderErrorClass.CREDIT_ERROR,
            http_status=429,
            error_code="insufficient_quota",
        )
    )
    temporary = invocation_from_diagnostic(
        ProviderDiagnostic(
            ProviderErrorClass.RATE_LIMIT_ERROR,
            http_status=429,
            error_code="rate_limit",
            retry_after_seconds=10,
        )
    )
    unknown_404 = invocation_from_diagnostic(
        ProviderDiagnostic(
            ProviderErrorClass.UNKNOWN_PROVIDER_ERROR,
            http_status=404,
        )
    )

    assert terminal.outcome is AiProviderOutcome.PROVIDER_TERMINAL
    assert temporary.outcome is AiProviderOutcome.TRANSIENT_FAILURE
    assert temporary.retry_after_seconds == 10
    assert unknown_404.outcome is AiProviderOutcome.TRANSIENT_FAILURE


def test_new_logical_need_restarts_cycle_counter() -> None:
    candidate = _Candidate("A")
    seen_cycles: list[int] = []

    def execute_once() -> None:
        run_ai_need(
            candidates=lambda: (candidate,),
            invoke=lambda _item, cycle, _attempt: (
                seen_cycles.append(cycle)
                or AiProviderInvocation(AiProviderOutcome.TRANSIENT_FAILURE)
            ),
            policy=AiExecutionPolicy(max_cycles=2, cycle_delay_seconds=0),
            sleeper=lambda _seconds: None,
        )

    execute_once()
    execute_once()

    assert seen_cycles == [1, 2, 1, 2]


def test_policy_environment_defaults_and_bounds() -> None:
    policy = configured_ai_execution_policy({})
    assert policy.max_cycles == 3
    assert policy.cycle_delay_seconds == 60
    assert configured_ai_max_cycles({"RASAI_AI_MAX_CYCLES": "1"}) == 1
    assert configured_ai_cycle_delay_seconds(
        {"RASAI_AI_CYCLE_DELAY_SECONDS": "0"}
    ) == 0

    with pytest.raises(ValueError):
        configured_ai_max_cycles({"RASAI_AI_MAX_CYCLES": "11"})
    with pytest.raises(ValueError):
        configured_ai_cycle_delay_seconds(
            {"RASAI_AI_CYCLE_DELAY_SECONDS": "301"}
        )


def test_auto_and_explicit_receive_same_execution_policy_contract() -> None:
    env = {
        "OPENAI_API_KEY": "test-key",
        "RASAI_AI_MAX_CYCLES": "2",
        "RASAI_AI_CYCLE_DELAY_SECONDS": "0",
        "RASAI_AI_TIMEOUT_SECONDS": "180",
    }

    explicit = build_semantic_provider("openai", env=env)
    auto = build_semantic_provider("auto", env=env)

    assert explicit._rasai_execution_policy == auto._rasai_execution_policy
    assert explicit._rasai_execution_policy.max_cycles == 2
    assert explicit._rasai_execution_policy.cycle_delay_seconds == 0
    assert explicit._rasai_execution_coordinator.provider_names == ("OPENAI",)
    assert auto.coordinator.provider_names == ("OPENAI",)
