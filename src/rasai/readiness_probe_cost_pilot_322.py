"""#322: measured, strictly opt-in same-page probe cost gate (pilot only).

This *observes* an existing Playwright page after its caller measured the
navigation start and Load boundary. It never opens a browser, navigates,
persists, changes M23/M25, or reports a new Apdex. The caller-supplied IDs
and clocks alone are not proof that the page came from an M25 sample.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import math
import time
from typing import Any, Callable

from rasai.apdex_content_readiness_observation import PrimaryContentReadiness
from rasai.playwright_primary_content_probe_322 import observe_existing_playwright_page

VERSION = "RASAI-READINESS-PHYSICAL-PROBE-PILOT-001"


@dataclass(frozen=True, slots=True)
class PrimaryContentProbeCost:
    contract_version: str
    observation: PrimaryContentReadiness
    number_of_dom_evaluations: int
    total_dom_evaluation_ms: float
    maximum_dom_evaluation_ms: float
    elapsed_probe_wall_ms: float
    measured_sleep_ms: float
    active_probe_wall_ms: float
    evaluation_budget_ms: float
    local_evaluation_budget_met: bool | None
    integration_gate: str
    identity_proof: str
    source_page_reused: bool
    provider_requests: int
    audit_writes: int
    apdex_changed: bool


class _TimedPage:
    """Proxy only the permitted DOM evaluation method; no navigation APIs."""
    def __init__(self, page: Any, clock: Callable[[], float]) -> None:
        self._page = page
        self._clock = clock
        self.durations: list[float] = []

    def evaluate(self, script: str) -> Any:
        start = self._clock()
        try:
            return self._page.evaluate(script)
        finally:
            spent = self._clock() - start
            self.durations.append(max(0.0, spent * 1000) if math.isfinite(spent) else 0.0)


def measure_existing_playwright_probe_cost(
    *,
    page: Any,
    sample_id: str,
    context_id: str,
    page_id: str,
    device: str,
    architecture: str,
    navigation_started_monotonic_ns: int | None,
    load_ms: float | None,
    enabled: bool = False,
    window_ms: int = 1200,
    poll_ms: int = 125,
    evaluation_budget_ms: float = 30.0,
    monotonic_ns: Callable[[], int] = time.monotonic_ns,
    perf_counter: Callable[[], float] = time.perf_counter,
    sleep: Callable[[float], None] = time.sleep,
) -> PrimaryContentProbeCost:
    """Time extra DOM evaluations and wait separately from a physical Load sample.

    This is *not* an Apdex M25 hook: a human or separate instrumented harness
    must demonstrate the page and monotonic clock belong to that very sample.
    Without a matched control/baseline or a production hook, no pass is an
    authorization to enable collection or publish claims in CAT-06/CAT-07.
    """
    if (
        type(evaluation_budget_ms) not in (int, float)
        or not math.isfinite(evaluation_budget_ms)
        or not 0 < evaluation_budget_ms <= 1000
    ):
        raise ValueError("evaluation_budget_ms must be finite within (0,1000]")
    page_proxy = _TimedPage(page, perf_counter) if page is not None else None
    slept = [0.0]
    def measured_sleep(seconds: float) -> None:
        start = perf_counter()
        try:
            sleep(seconds)
        finally:
            spent = perf_counter() - start
            if math.isfinite(spent) and spent >= 0:
                slept[0] += spent * 1000

    begin = perf_counter()
    observation = observe_existing_playwright_page(
        page=page_proxy,
        sample_id=sample_id,
        context_id=context_id,
        page_id=page_id,
        device=device,
        architecture=architecture,
        navigation_started_monotonic_ns=navigation_started_monotonic_ns,
        load_ms=load_ms,
        enabled=enabled,
        window_ms=window_ms,
        poll_ms=poll_ms,
        monotonic_ns=monotonic_ns,
        sleep=measured_sleep,
    )
    elapsed = perf_counter() - begin
    total = max(0.0, elapsed * 1000) if math.isfinite(elapsed) else 0.0
    samples = page_proxy.durations if page_proxy is not None else []
    max_sample = max(samples, default=0.0)
    budget = max_sample <= evaluation_budget_ms if samples else None
    return PrimaryContentProbeCost(
        contract_version=VERSION,
        observation=observation,
        number_of_dom_evaluations=len(samples),
        total_dom_evaluation_ms=round(sum(samples), 3),
        maximum_dom_evaluation_ms=round(max_sample, 3),
        elapsed_probe_wall_ms=round(total, 3),
        measured_sleep_ms=round(slept[0], 3),
        active_probe_wall_ms=round(max(0.0, total - slept[0]), 3),
        evaluation_budget_ms=float(evaluation_budget_ms),
        local_evaluation_budget_met=budget,
        integration_gate=(
            "NOT_APPLICABLE_OR_NO_DOM_EVALUATION"
            if not samples else
            "BLOCKED_BY_LOCAL_DOM_OVERHEAD"
            if not budget else
            "PILOT_ONLY_REQUIRES_MATCHED_BASELINE_AND_GATEWAY_IDENTITY"
        ),
        identity_proof="CALLER_DECLARED_NOT_ATTESTED_BY_M25",
        source_page_reused=page is not None,
        provider_requests=0,
        audit_writes=0,
        apdex_changed=False,
    )
