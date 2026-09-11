from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from rasai.open_web_metrics import (
    DEFAULT_OPEN_WEB_METRICS_ENABLED,
    OPEN_WEB_METRICS_CONTRACT_VERSION,
    capture_open_web_metrics,
)
from rasai import open_web_metrics_reporting as reporting


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


def _sample_metrics() -> dict:
    return {
        "contract_version": OPEN_WEB_METRICS_CONTRACT_VERSION,
        "state": "CAPTURED",
        "enabled_by_default": True,
        "scope": "DEVICE_SNAPSHOT",
        "additional_navigation_requests": 0,
        "additional_external_api_calls": 0,
        "score_impact": "NONE",
        "methodology": "W3C Web Performance APIs; same-session browser observation",
        "supported_entry_types": ["navigation", "paint", "resource", "layout-shift"],
        "navigation": {
            "next_hop_protocol": "h2",
            "ttfb_from_navigation_start_ms": 120.0,
            "dns_ms": 5.0,
            "connect_ms": 10.0,
            "tls_ms": 7.0,
            "response_download_ms": 40.0,
            "load_event_end_ms": 900.0,
            "transfer_size_bytes": 8192,
            "server_timing_metric_count": 1,
        },
        "paint": {
            "first_contentful_paint_ms": 700.0,
            "largest_contentful_paint_ms": 1800.0,
        },
        "layout": {"cumulative_layout_shift": 0.05},
        "responsiveness": {
            "observed_interaction_event_count": 0,
            "max_observed_interaction_event_duration_ms": None,
            "note": "No qualifying interaction was observed in this synthetic snapshot; INP is not inferred.",
        },
        "main_thread": {"long_task_count": 2},
        "resources": {
            "count": 20,
            "third_party_count": 4,
            "transfer_size_bytes": 100000,
            "entries_without_size_visibility": 2,
            "initiator_counts": {"script": 5, "img": 8},
        },
        "user_timing": {"mark_count": 2, "measure_count": 1, "measured_duration_total_ms": 15.0},
        "document_platform": {
            "standards_mode": True,
            "doctype_present": True,
            "document_language_present": True,
            "charset": "UTF-8",
            "viewport_meta_present": True,
            "secure_context": True,
            "cross_origin_isolated": False,
        },
    }


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


def test_open_web_section_is_explicit_about_scope_cost_and_methodology() -> None:
    items = [
        {"snapshot_id": "S1", "device": "MOBILE", "url": "https://example.test/a", "metrics": _sample_metrics()},
        {"snapshot_id": "S2", "device": "DESKTOP", "url": "https://example.test/b", "metrics": _sample_metrics()},
    ]

    html = reporting._section(items)

    assert "Open Web Performance APIs" in html
    assert "https://example.test/a" in html
    assert "MOBILE" in html
    assert "mínimo–máximo" in html
    assert "não existe média implícita" in html
    assert "INP não é inferido" in html
    assert "additional_navigation_requests=0" in html
    assert "additional_external_api_calls=0" in html
    assert "SARI-001/SCORE-GEO-004" in html
    assert "Sem “W3C score”" in html


def test_web_performance_enrichment_is_idempotent(tmp_path: Path, monkeypatch) -> None:
    report_dir = tmp_path / "report"
    report_dir.mkdir()
    target = report_dir / "web-performance.html"
    target.write_text("<html><body><main><h1>Web Performance</h1></main></body></html>", encoding="utf-8")
    items = [
        {"snapshot_id": "S1", "device": "MOBILE", "url": "https://example.test/a", "metrics": _sample_metrics()},
    ]
    monkeypatch.setattr(reporting, "_load", lambda audit_id, workspace: items)
    workspace = SimpleNamespace(root=tmp_path)

    reporting.enrich_web_performance_report(audit_id="AUD-TEST", workspace=workspace)
    reporting.enrich_web_performance_report(audit_id="AUD-TEST", workspace=workspace)

    html = target.read_text(encoding="utf-8")
    assert html.count("rasai-open-web-metrics-start") == 1
    assert html.count("rasai-open-web-metrics-end") == 1
    assert html.count("id='open-web-performance-apis'") == 1
