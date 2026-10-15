"""#322: cost gate is an isolated pilot; no synthetic Apdex modification."""
from __future__ import annotations

from dataclasses import asdict

import pytest

from rasai.readiness_probe_cost_pilot_322 import measure_existing_playwright_probe_cost

READY = {
    "main_text_characters": 400,
    "heading_text_characters": 20,
    "skeleton_present": False,
}
LOADING = {
    "main_text_characters": 0,
    "heading_text_characters": 0,
    "skeleton_present": True,
}


class Clock:
    def __init__(self) -> None:
        self.origin_ns = 1_000_000_000
        self.now = self.origin_ns + 300_000_000
    def ns(self) -> int:
        return self.now
    def secs(self) -> float:
        return self.now / 1e9
    def sleep(self, amount: float) -> None:
        self.now += int(amount * 1e9)


class Page:
    def __init__(self, clock, values, *, evaluation_ms=5):
        self.clock = clock
        self.values = list(values)
        self.evaluation_ms = evaluation_ms
        self.calls = 0
    def evaluate(self, script):
        self.calls += 1
        self.clock.now += int(self.evaluation_ms * 1e6)
        return self.values[min(self.calls-1, len(self.values)-1)]
    def goto(self, *_args, **_kwargs):
        raise AssertionError("probe must not navigate")
    def close(self):
        raise AssertionError("probe must not close browser")


def run(page, clock, **changes):
    config = {
        "page": page, "sample_id": "SNP-TEST",
        "context_id": "CTX-TEST", "page_id": "P-TEST",
        "device": "MOBILE", "architecture": "CSR_SPA",
        "navigation_started_monotonic_ns": clock.origin_ns,
        "load_ms": 200.0, "enabled": True,
        "window_ms": 1000, "poll_ms": 125,
        "evaluation_budget_ms": 30.0,
        "monotonic_ns": clock.ns, "perf_counter": clock.secs,
        "sleep": clock.sleep,
    }
    config.update(changes)
    return measure_existing_playwright_probe_cost(**config)


def test_two_actual_evaluations_timed_and_waits_excluded_from_active_cost():
    clock = Clock()
    page = Page(clock, [READY, READY], evaluation_ms=5)
    result = run(page, clock)
    assert result.observation.status == "OBSERVED"
    assert result.number_of_dom_evaluations == 2
    assert result.total_dom_evaluation_ms == 10
    assert result.maximum_dom_evaluation_ms == 5
    assert result.measured_sleep_ms == 125
    assert result.active_probe_wall_ms == 10
    assert result.elapsed_probe_wall_ms == 135
    assert result.local_evaluation_budget_met is True
    assert result.integration_gate == "PILOT_ONLY_REQUIRES_MATCHED_BASELINE_AND_GATEWAY_IDENTITY"
    assert result.identity_proof == "CALLER_DECLARED_NOT_ATTESTED_BY_M25"
    assert result.source_page_reused is True
    assert result.provider_requests == result.audit_writes == 0
    assert result.apdex_changed is False
    assert page.calls == 2
    assert "DOM" not in str(asdict(result)["observation"].get("reason"))


def test_slow_browser_evaluation_blocks_overhead_gate_even_if_observation_valid():
    clock = Clock()
    result = run(Page(clock, [READY, READY], evaluation_ms=125), clock)
    assert result.observation.status == "OBSERVED"
    assert result.maximum_dom_evaluation_ms == 125
    assert result.local_evaluation_budget_met is False
    assert result.integration_gate == "BLOCKED_BY_LOCAL_DOM_OVERHEAD"
    assert result.apdex_changed is False


def test_disabled_and_ssr_do_not_touch_page_or_invent_overhead_or_scores():
    for enabled, arch in ((False, "CSR_SPA"), (True, "STATIC_OR_SSR"), (True, "UNKNOWN")):
        clock = Clock()
        page = Page(clock, [READY])
        result = run(page, clock, enabled=enabled, architecture=arch)
        assert result.observation.status == "NOT_APPLICABLE"
        assert page.calls == 0
        assert result.number_of_dom_evaluations == 0
        assert result.local_evaluation_budget_met is None
        assert result.integration_gate == "NOT_APPLICABLE_OR_NO_DOM_EVALUATION"


def test_censored_skeleton_produces_no_readiness_delta_and_measured_cost():
    clock = Clock()
    result = run(Page(clock, [LOADING] * 20, evaluation_ms=3), clock,
                 window_ms=350, poll_ms=125)
    assert result.observation.status == "TIMEOUT"
    assert result.observation.primary_content_ms is None
    assert result.observation.post_load_delta_ms is None
    assert result.number_of_dom_evaluations <= 4
    assert result.total_dom_evaluation_ms > 0
    assert result.integration_gate == "PILOT_ONLY_REQUIRES_MATCHED_BASELINE_AND_GATEWAY_IDENTITY"


def test_failed_dom_probe_does_not_leak_exception_and_still_records_cost():
    class SecretFailPage:
        def evaluate(self, _script):
            raise RuntimeError("secret credentials and HTML")
    clock = Clock()
    result = run(SecretFailPage(), clock)
    assert result.observation.status == "ERROR"
    assert result.observation.reason == "same_sample_dom_probe_failed"
    assert result.number_of_dom_evaluations == 1
    assert "secret" not in str(asdict(result))


@pytest.mark.parametrize("value", [0, -1, float("nan"), float("inf"), 1001, True])
def test_bad_budget_is_rejected_before_any_dom_call(value):
    clock = Clock()
    page = Page(clock, [READY])
    with pytest.raises(ValueError):
        run(page, clock, evaluation_budget_ms=value)
    assert page.calls == 0


def test_not_a_production_gateway_module():
    from rasai import readiness_probe_cost_pilot_322 as module
    for name in ("sqlite3", "requests", "httpx", "execute_m25_experience",
                 "m23_apdex", "persist_current_configuration"):
        assert name not in module.__dict__
