from __future__ import annotations

from types import SimpleNamespace

import pytest

from rasai.discovery import RobotsState, SitemapState
from rasai.domain import RuleResult
from rasai.m5 import _evaluate_robots, _evaluate_sitemaps
from rasai.m7 import _deterministic_outcome
from rasai.m21_web_performance import ExternalServiceError, HttpJsonResult, PageSpeedInsightsClient
from rasai.m24_ai import _schema
from rasai.m24_scoring import _bounded_result
from rasai.scoring import _metadata


def _m2(*, robots: RobotsState, sitemaps: tuple[SitemapState, ...]):
    return SimpleNamespace(
        discovery=SimpleNamespace(
            robots=SimpleNamespace(state=robots, url="https://example.test/robots.txt"),
            sitemaps=tuple(
                SimpleNamespace(url=f"https://example.test/sitemap-{index}.xml", state=state, error=None)
                for index, state in enumerate(sitemaps)
            ),
        )
    )


def test_absent_discovery_resources_are_not_positive_passes() -> None:
    m2 = _m2(robots=RobotsState.ABSENT, sitemaps=(SitemapState.ABSENT,))
    assert _evaluate_robots(m2).result is RuleResult.WARNING
    assert _evaluate_sitemaps(m2).result is RuleResult.WARNING


def test_invalid_sitemap_is_materially_unfavorable() -> None:
    m2 = _m2(robots=RobotsState.OBTAINED, sitemaps=(SitemapState.INVALID,))
    assert _evaluate_sitemaps(m2).result is RuleResult.FAIL


def test_discovery_weights_are_static_and_ai_shares_deterministic_group() -> None:
    sitemap = _metadata("BR-GEO-003")
    sitemap_ai = _metadata("BR-GEO-055")
    robots = _metadata("BR-GEO-017")
    robots_ai = _metadata("BR-GEO-056")
    assert sitemap.dimension == sitemap_ai.dimension == "DISCOVERY_ACCESS"
    assert sitemap.weight == sitemap_ai.weight == pytest.approx(0.05)
    assert sitemap.scoring_group == sitemap_ai.scoring_group == "SITEMAP"
    assert robots.dimension == robots_ai.dimension == "DISCOVERY_ACCESS"
    assert robots.weight == robots_ai.weight == pytest.approx(0.15)
    assert robots.scoring_group == robots_ai.scoring_group == "ROBOTS"
    assert sitemap.evidence_role != sitemap_ai.evidence_role
    assert robots.evidence_role != robots_ai.evidence_role


def test_missing_jsonld_is_measured_as_modest_warning() -> None:
    outcome = _deterministic_outcome(
        "BR-GEO-034",
        "Example",
        {"present": False, "invalid_blocks": 0, "types": []},
        "EV-1",
    )
    assert outcome is not None
    assert outcome.evaluation.result is RuleResult.WARNING
    assert _metadata("BR-GEO-034").warning_factor == pytest.approx(0.80)


def test_technical_ai_schema_never_exposes_arbitrary_weight() -> None:
    schema = _schema()
    resource = schema["properties"]["resource_assessments"]["items"]
    assert resource["properties"]["verdict"]["enum"] == ["POSITIVE", "NEUTRAL", "NEGATIVE"]
    assert "weight" not in resource["properties"]


def test_low_confidence_ai_cannot_create_hard_pass_or_fail() -> None:
    assert _bounded_result("POSITIVE", 0.59) is RuleResult.WARNING
    assert _bounded_result("NEGATIVE", 0.59) is RuleResult.WARNING
    assert _bounded_result("NEGATIVE", 0.90) is RuleResult.FAIL


def test_pagespeed_retries_one_transient_failure(monkeypatch) -> None:
    calls = []

    def fake_request_json(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            raise ExternalServiceError("PAGESPEED_INSIGHTS", "temporary", http_status=500)
        return HttpJsonResult(payload={"lighthouseResult": {}}, http_status=200, duration_ms=1)

    monkeypatch.setattr("rasai.m21_web_performance._request_json", fake_request_json)
    monkeypatch.setattr("rasai.m21_web_performance.time.sleep", lambda _value: None)
    result = PageSpeedInsightsClient("key").run(
        url="https://example.test/",
        strategy="mobile",
        categories=("performance",),
        timeout_seconds=1.0,
    )
    assert result.http_status == 200
    assert len(calls) == 2
