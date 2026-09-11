from __future__ import annotations

import time

import pytest

from rasai import external_measurement_runtime as runtime
from rasai import m21_web_performance as m21


def test_wallclock_deadline_returns_without_waiting_for_stuck_worker() -> None:
    started = time.monotonic()

    with pytest.raises(m21.ExternalServiceError) as excinfo:
        runtime._run_with_wallclock_deadline(
            lambda: time.sleep(0.25),
            service="PAGESPEED_INSIGHTS",
            timeout_seconds=0.02,
            error_type=m21.ExternalServiceError,
        )

    elapsed = time.monotonic() - started
    assert elapsed < 0.20
    assert excinfo.value.error_code == "WALL_CLOCK_TIMEOUT"


def test_pagespeed_runtime_does_not_retry_transient_provider_error(monkeypatch: pytest.MonkeyPatch) -> None:
    runtime.install()
    calls: list[int] = []

    def fail_once(*, service, request, timeout_seconds):  # noqa: ANN001
        del request, timeout_seconds
        calls.append(1)
        raise m21.ExternalServiceError(
            service,
            "transient",
            http_status=503,
            error_code="SERVICE_UNAVAILABLE",
            duration_ms=1,
        )

    monkeypatch.setattr(m21, "_request_json", fail_once)
    client = m21.PageSpeedInsightsClient("test-key")
    with pytest.raises(m21.ExternalServiceError):
        client.run(
            url="https://example.test/",
            strategy="mobile",
            categories=("performance",),
            timeout_seconds=1.0,
        )
    assert len(calls) == 1
    assert m21._PAGESPEED_MAX_ATTEMPTS == 1


def test_strategy_declares_independent_measurements_without_redundant_retry() -> None:
    summary = runtime.strategy_summary()
    assert summary["core_http"] == "ONE_DIRECT_HTTP_ACQUISITION_PER_URL"
    assert summary["core_browser"] == "ONE_BROWSER_NAVIGATION_PER_URL_DEVICE"
    assert "NO_RETRY" in summary["pagespeed"]
    assert summary["crux"] == "DATA_API_LOOKUP_NO_TARGET_NAVIGATION_FALLBACK_ONLY"
