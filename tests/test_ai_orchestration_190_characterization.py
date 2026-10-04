"""Characterization guards captured before canonical cycle migration (#190).

These tests intentionally cover invariants that must survive the orchestration rewrite:
one external call per provider opportunity, early completion, terminal execution-wide
quarantine, and provider-neutral attempt telemetry.
"""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from rasai.dynamic_ai_routing import AiExecutionCoordinator, DynamicProviderRoutingSession
from rasai.m18_ai import (
    AttemptStatus,
    ProviderAttempt,
    ProviderDiagnostic,
    ProviderErrorClass,
    ProviderState,
    RuntimeProviderState,
    SemanticProviderResult,
)


def _attempt(provider: str, *, error: ProviderErrorClass | None = None) -> ProviderAttempt:
    now = datetime.now(timezone.utc)
    return ProviderAttempt(
        provider=provider,
        model=f"{provider.lower()}-model",
        reasoning_profile="NONE",
        provider_rank=1,
        attempt_index=1,
        snapshot_id="SNP-CHAR",
        url="https://example.test/",
        started_at=now,
        finished_at=now,
        duration_ms=1,
        status=AttemptStatus.SUCCESS if error is None else AttemptStatus.TECHNICAL_ERROR,
        diagnostic=None if error is None else ProviderDiagnostic(error_class=error),
    )


class _Provider:
    def __init__(self, name: str, rank: int, results: list[ProviderErrorClass | None]) -> None:
        self.name = name
        self.model = f"{name.lower()}-model"
        self.reasoning_profile = "NONE"
        self.policy = SimpleNamespace(rank=rank, qualification="TEST")
        self._results = list(results)
        self._last: tuple[ProviderAttempt, ...] = ()
        self._runtime_state = RuntimeProviderState.ACTIVE
        self.calls = 0

    def analyze(self, semantic_input, *, max_attempts: int = 1):
        assert max_attempts == 1
        self.calls += 1
        error = self._results.pop(0)
        attempt = _attempt(self.name, error=error)
        self._last = (attempt,)
        if error is None:
            return SemanticProviderResult(
                ProviderState.AVAILABLE,
                provider=self.name,
                model=self.model,
            )
        return SemanticProviderResult(
            ProviderState.UNAVAILABLE,
            reason=attempt.diagnostic.reason,
            provider=self.name,
            model=self.model,
            diagnostic=attempt.diagnostic,
        )

    def consume_attempts(self):
        result = self._last
        self._last = ()
        return result


def test_characterization_one_provider_opportunity_per_auto_pass_and_early_stop() -> None:
    first = _Provider("A", 1, [ProviderErrorClass.TIMEOUT_ERROR])
    second = _Provider("B", 2, [None])
    third = _Provider("C", 3, [None])
    session = DynamicProviderRoutingSession((first, second, third))

    result = session.analyze(SimpleNamespace(page_url="https://example.test/"))

    assert result.provider == "B"
    assert [first.calls, second.calls, third.calls] == [1, 1, 0]
    assert len(session.consume_attempts()) == 2


def test_characterization_terminal_provider_is_quarantined_for_execution() -> None:
    coordinator = AiExecutionCoordinator(("A", "B"))
    coordinator.record_attempt(
        _attempt("A", error=ProviderErrorClass.AUTH_ERROR),
        scope="CHARACTERIZATION",
    )

    assert coordinator.is_eligible("A") is False
    assert coordinator.ordered_names() == ("B",)
    health = coordinator.health_snapshot()["A"]
    assert health["terminal_failures"] == 1
    assert str(health["exclusion_reason"]).startswith("TERMINAL:AUTH_ERROR")


def test_characterization_success_attempt_keeps_usage_independent_of_routing_state() -> None:
    coordinator = AiExecutionCoordinator(("A",))
    attempt = _attempt("A")
    coordinator.record_attempt(attempt, scope="CHARACTERIZATION")

    health = coordinator.health_snapshot()["A"]
    assert health["eligible"] is True
    assert health["successes"] == 1
    assert coordinator.last_successful_provider == "A"
