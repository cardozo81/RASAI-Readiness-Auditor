from __future__ import annotations

import pytest

from rasai.content_context import (
    build_content_analysis_context,
    configured_content_analysis_context,
)
from rasai.m20_ai import ContentRemediationRequest
from rasai.m20_reporting import _context_panel, _telemetry_summary
from rasai.openai_provider import SEMANTIC_RULE_CRITERIA
from rasai.provider_runtime_policy import build_semantic_provider


def test_content_context_defaults_are_explicitly_auto() -> None:
    context = build_content_analysis_context()
    assert context.is_fully_auto is True
    assert context.configured_fields == ()
    assert set(context.auto_fields) == {
        "risk_profile",
        "ymyl_category",
        "page_purpose",
        "intended_audience",
        "experience_requirement",
        "freshness_sensitivity",
        "content_origin",
    }
    payload = context.provider_payload()
    assert payload["risk_profile"] == "auto"
    assert "not official ranking factors" in payload["analysis_policy"]


def test_explicit_financial_ymyl_context_is_valid() -> None:
    context = build_content_analysis_context(
        risk_profile="ymyl",
        ymyl_category="financial-security",
        page_purpose="product-service",
        intended_audience="general",
        experience_requirement="not-expected",
        freshness_sensitivity="high",
        content_origin="first-party",
    )
    assert context.is_fully_auto is False
    assert context.auto_fields == ()
    assert context.risk_profile.value == "ymyl"
    assert context.ymyl_category.value == "financial-security"
    assert "risk_profile=ymyl" in context.compact_summary()


def test_inconsistent_ymyl_combinations_fail_closed() -> None:
    with pytest.raises(ValueError):
        build_content_analysis_context(
            risk_profile="standard",
            ymyl_category="financial-security",
        )
    with pytest.raises(ValueError):
        build_content_analysis_context(
            risk_profile="ymyl",
            ymyl_category="none",
        )


def test_environment_context_is_normalized_and_validated() -> None:
    context = configured_content_analysis_context(
        {
            "RASAI_CONTENT_RISK_PROFILE": "YMYL",
            "RASAI_YMYL_CATEGORY": "HEALTH-SAFETY",
            "RASAI_PAGE_PURPOSE": "INFORMATIONAL",
        }
    )
    assert context.risk_profile.value == "ymyl"
    assert context.ymyl_category.value == "health-safety"
    assert context.page_purpose.value == "informational"
    assert "intended_audience" in context.auto_fields


def test_provider_build_validates_context_even_when_ai_is_none() -> None:
    with pytest.raises(ValueError):
        build_semantic_provider(
            "none",
            env={
                "RASAI_CONTENT_RISK_PROFILE": "standard",
                "RASAI_YMYL_CATEGORY": "financial-security",
            },
        )


def test_semantic_prompt_contract_receives_context(monkeypatch) -> None:
    monkeypatch.setenv("RASAI_CONTENT_RISK_PROFILE", "ymyl")
    monkeypatch.setenv("RASAI_YMYL_CATEGORY", "financial-security")
    rendered = f"{SEMANTIC_RULE_CRITERIA['BR-GEO-049']}"
    assert "content_analysis_context" in rendered
    assert '"risk_profile": "ymyl"' in rendered
    assert "higher trust/evidence bar" in rendered


def test_m20_payload_carries_same_context(monkeypatch) -> None:
    monkeypatch.setenv("RASAI_CONTENT_RISK_PROFILE", "ymyl")
    monkeypatch.setenv("RASAI_YMYL_CATEGORY", "financial-security")
    request = ContentRemediationRequest(
        snapshot_id="SNP-1",
        page_id="PAG-1",
        page_url="https://example.test/finance",
        device="MOBILE",
        title="Finance",
        main_content="Visible evidence",
        findings=(),
        evidence=(),
    )
    payload = request.provider_payload()
    assert payload["content_analysis_context"]["risk_profile"] == "ymyl"
    assert payload["content_analysis_context"]["ymyl_category"] == "financial-security"
    assert "analysis_policy" in payload["content_analysis_context"]


def test_report_context_panel_marks_manual_and_auto_fields() -> None:
    context = build_content_analysis_context(
        risk_profile="ymyl",
        ymyl_category="financial-security",
    )
    html = _context_panel(
        (
            context,
            {
                "source_mode": "MIXED",
                "configured_fields": ["risk_profile", "ymyl_category"],
                "auto_fields": list(context.auto_fields),
                "created_at": "2026-09-06T00:00:00+00:00",
            },
        )
    )
    assert "Contexto editorial aplicado à IA" in html
    assert "CONFIGURADO" in html
    assert "AUTO" in html
    assert "SCORE-GEO-004" in html
    assert "title=" in html


def test_telemetry_summary_uses_persisted_attempt_values() -> None:
    attempts = [
        {
            "provider": "OPENAI",
            "model": "gpt-5.6-luna",
            "reasoning_profile": "NONE",
            "duration_ms": 1250,
            "total_tokens": 300,
            "estimated_cost": 0.001,
            "cost_currency": "USD",
        },
        {
            "provider": "OPENAI",
            "model": "gpt-5.6-luna",
            "reasoning_profile": "NONE",
            "duration_ms": 750,
            "total_tokens": 200,
            "estimated_cost": 0.002,
            "cost_currency": "USD",
        },
    ]
    summary = _telemetry_summary(attempts)  # type: ignore[arg-type]
    assert summary["providers"] == "OPENAI"
    assert summary["models"] == "gpt-5.6-luna"
    assert summary["reasoning"] == "NONE"
    assert summary["calls"] == 2
    assert summary["duration"] == "2.00 s"
    assert summary["tokens"] == 500
    assert summary["cost"] == "0.00300000 USD"
