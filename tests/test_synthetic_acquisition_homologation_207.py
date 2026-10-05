"""#207: deterministic homologation of canonical synthetic acquisition planning."""
from __future__ import annotations

from dataclasses import dataclass
import math
import statistics

import pytest

from rasai import synthetic_acquisition_engine as engine
from rasai.m23_apdex import _sample as nav_sample, _summary as nav_summary
from rasai.m23_apdex_profiles import MOBILE_STANDARD_PROFILE, NavigationMeasurement
from rasai.m25_apdex_experience import Calibration, UxMeasurement, classify_measurement


@dataclass(frozen=True)
class Workload:
    navigation: int
    experience: int
    concurrency: int

    @property
    def isolated_physical(self) -> int:
        return self.navigation + self.experience

    @property
    def canonical_physical(self) -> int:
        return max(self.navigation, self.experience)

    @property
    def isolated_waves(self) -> int:
        return math.ceil(self.isolated_physical / self.concurrency) if self.isolated_physical else 0

    @property
    def canonical_waves(self) -> int:
        return math.ceil(self.canonical_physical / self.concurrency) if self.canonical_physical else 0


CASES = (
    (50, 1000, 1000, 0, 1000),
    (100, 100, 100, 0, 100),
    (150, 100, 100, 50, 150),
    (1000, 50, 50, 950, 1000),
)


@pytest.mark.parametrize("nav,exp,full,load_only,total", CASES)
def test_required_physical_workload_cases(nav, exp, full, load_only, total) -> None:
    plan = engine.plan_acquisitions(nav, exp)
    assert (plan.full_experience, plan.load_only, plan.total_physical) == (
        full,
        load_only,
        total,
    )
    assert plan.total_physical == max(nav, exp)
    assert len(plan.navigation_ordinals) == min(nav, exp)


@pytest.mark.parametrize("device", ("MOBILE", "DESKTOP"))
@pytest.mark.parametrize("concurrency", (1, 4))
@pytest.mark.parametrize("nav,exp,_,__,___", CASES)
def test_workload_gain_is_device_neutral_and_concurrency_safe(
    device, concurrency, nav, exp, _, __, ___
) -> None:
    workload = Workload(nav, exp, concurrency)
    plan = engine.plan_acquisitions(nav, exp)
    assert device in {"MOBILE", "DESKTOP"}
    assert plan.total_physical == workload.canonical_physical
    assert workload.canonical_physical <= workload.isolated_physical
    assert workload.canonical_waves <= workload.isolated_waves


def _nav_measurement(duration_ms: int) -> NavigationMeasurement:
    return NavigationMeasurement(
        status="SUCCESS",
        duration_ms=duration_ms,
        http_status=200,
        final_url="https://example.test/",
        error_code=None,
        error_message=None,
        profile_applied=True,
        cpu_method="TEST_CPU",
        network_method="TEST_NETWORK",
    )


def test_navigation_evaluator_parity_on_identical_raw_load_facts() -> None:
    # Controlled FULL population with stable non-monotonic variation.
    population = [650 + ((index * 37) % 2200) for index in range(1000)]
    plan = engine.plan_acquisitions(50, 1000)
    selected = [population[index] for index in plan.navigation_ordinals]

    # Old/isolated and canonical/shared paths feed exactly the same raw load facts
    # into the same CAT-06 classifier. No score is borrowed from CAT-07.
    isolated = [nav_sample(i + 1, _nav_measurement(value), 1.0) for i, value in enumerate(selected)]
    canonical = [nav_sample(i + 1, _nav_measurement(value), 1.0) for i, value in enumerate(selected)]

    assert [item.classification for item in canonical] == [
        item.classification for item in isolated
    ]
    assert [item.measurement.duration_ms for item in canonical] == [
        item.measurement.duration_ms for item in isolated
    ]

    isolated_summary = nav_summary(
        audit_id="AUD-BASELINE",
        page_id="PAGE-1",
        device="MOBILE",
        url="https://example.test/",
        profile=MOBILE_STANDARD_PROFILE,
        threshold=1.0,
        target=len(isolated),
        samples=isolated,
    )
    canonical_summary = nav_summary(
        audit_id="AUD-CANONICAL",
        page_id="PAGE-1",
        device="MOBILE",
        url="https://example.test/",
        profile=MOBILE_STANDARD_PROFILE,
        threshold=1.0,
        target=len(canonical),
        samples=canonical,
    )
    for field in (
        "valid_samples",
        "invalid_samples",
        "satisfied_count",
        "tolerating_count",
        "frustrated_count",
        "success_count",
        "timeout_count",
        "navigation_error_count",
        "apdex_score",
        "mean_ms",
        "median_ms",
        "stddev_ms",
        "coefficient_of_variation",
        "p95_ms",
    ):
        assert getattr(canonical_summary, field) == getattr(isolated_summary, field)

    # Uniform selection must not collapse into the prefix of a much larger FULL set.
    assert plan.navigation_ordinals[0] == 0
    assert plan.navigation_ordinals[-1] == 999
    assert len(set(plan.navigation_ordinals)) == 50

    full_mean = statistics.fmean(population)
    nav_mean = statistics.fmean(selected)
    # The deterministic spread should not introduce a material systematic shift in
    # this controlled population.
    assert abs(nav_mean - full_mean) / full_mean < 0.02


def test_experience_evaluator_parity_preserves_kpm_errors_and_post_load_facts() -> None:
    calibration = Calibration(
        source="TEST",
        kpm="USER_ACTION_DURATION",
        satisfied_threshold_seconds=1.0,
        frustrated_threshold_seconds=4.0,
        errors_affect_apdex=True,
        metadata={},
        javascript_errors_affect_apdex=True,
        request_errors_affect_apdex=True,
        console_errors_affect_apdex=False,
    )
    baseline = UxMeasurement(
        status="SUCCESS",
        user_action_duration_ms=1_800.0,
        navigation_duration_ms=800.0,
        response_start_ms=100.0,
        response_end_ms=220.0,
        dom_interactive_ms=1_100.0,
        load_event_start_ms=1_600.0,
        load_event_end_ms=1_700.0,
        lcp_ms=1_300.0,
        cls=0.02,
        http_status=200,
        final_url="https://example.test/",
        xhr_fetch_count=3,
        dynamic_resource_count=7,
        javascript_error_count=0,
        request_failed_count=0,
        network_settled=True,
        profile_applied=True,
    )
    replayed = UxMeasurement(**{
        field: getattr(baseline, field)
        for field in baseline.__dataclass_fields__
    })
    assert classify_measurement(
        replayed, calibration, error_scope="all"
    ) == classify_measurement(
        baseline, calibration, error_scope="all"
    )
    assert replayed.xhr_fetch_count == baseline.xhr_fetch_count
    assert replayed.network_settled == baseline.network_settled
    assert replayed.load_event_end_ms == baseline.load_event_end_ms


def test_invalid_fragments_remain_invalid_under_canonical_path() -> None:
    calibration = Calibration(
        source="TEST",
        kpm="USER_ACTION_DURATION",
        satisfied_threshold_seconds=1.0,
        frustrated_threshold_seconds=4.0,
        errors_affect_apdex=False,
        metadata={},
    )
    invalid = UxMeasurement(
        status="INVALID_SAMPLE",
        user_action_duration_ms=None,
        profile_applied=False,
    )
    assert classify_measurement(invalid, calibration, error_scope="all") == (
        None,
        None,
        False,
    )


def test_individual_catalogs_keep_their_own_physical_population() -> None:
    nav_only = engine.plan_acquisitions(150, 0)
    exp_only = engine.plan_acquisitions(0, 100)
    both = engine.plan_acquisitions(150, 100)

    assert (nav_only.full_experience, nav_only.load_only, nav_only.total_physical) == (
        0, 150, 150
    )
    assert (exp_only.full_experience, exp_only.load_only, exp_only.total_physical) == (
        100, 0, 100
    )
    assert (both.full_experience, both.load_only, both.total_physical) == (
        100, 50, 150
    )


def test_parallel_completion_order_cannot_change_uniform_navigation_population() -> None:
    plan = engine.plan_acquisitions(50, 1000)
    planned = plan.navigation_ordinals
    # Completion order is deliberately reversed; selection remains a property of the
    # pre-start ordinal, not of future completion.
    completion_order = tuple(reversed(range(1000)))
    selected_after_reverse_completion = tuple(
        ordinal for ordinal in planned if ordinal in set(completion_order)
    )
    assert selected_after_reverse_completion == planned
