from __future__ import annotations

from rasai.open_web_metrics import (
    DEFAULT_OPEN_WEB_METRICS_ENABLED,
    capture_open_web_metrics,
)


class _Page:
    def __init__(self, result=None, error: Exception | None = None) -> None:
        self.result = result
        self.error = error
        self.scripts: list[str] = []

    def evaluate(self, script: str):
        self.scripts.append(script)
        if self.error is not None:
            raise self.error
        return self.result


def test_open_web_metrics_are_default_on_and_zero_additional_acquisition() -> None:
    assert DEFAULT_OPEN_WEB_METRICS_ENABLED is True
    page = _Page(
        {
            "navigation": {"ttfb_from_navigation_start_ms": 50.0},
            "paint": {"first_contentful_paint_ms": 100.0},
            "layout": {"cumulative_layout_shift": 0.0},
        }
    )

    result = capture_open_web_metrics(page)

    assert result["state"] == "CAPTURED"
    assert result["enabled_by_default"] is True
    assert result["additional_navigation_requests"] == 0
    assert result["additional_external_api_calls"] == 0
    assert result["score_impact"] == "NONE"
    assert "PerformanceObserver" in page.scripts[0]


def test_open_web_metrics_fail_open_when_browser_observation_fails() -> None:
    result = capture_open_web_metrics(_Page(error=RuntimeError("boom")))

    assert result["state"] == "UNAVAILABLE"
    assert result["reason"] == "METRICS_CAPTURE_FAILED"
    assert result["additional_navigation_requests"] == 0
    assert result["score_impact"] == "NONE"
