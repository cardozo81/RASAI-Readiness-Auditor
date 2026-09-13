from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

import rasai.m18_ai as m18_ai
from rasai.ai_cost_policy import (
    PRICING_CATALOG,
    PRICING_REVIEW_RECOMMENDED_ON,
    estimate_candidate_cost,
    estimate_observed_cost,
    pricing_context,
    reasoning_output_multiplier,
    resolve_price,
)
from rasai.dynamic_ai_routing import DynamicProviderRoutingSession
from rasai.m18_ai import ProviderUsage

UTC = timezone.utc
BRT = timezone(timedelta(hours=-3))


def test_deepseek_peak_uses_utc_weekday_and_not_consumer_weekday() -> None:
    # Sunday 22:30 in GMT-3 is Monday 01:30 UTC, therefore peak.
    local_sunday = datetime(2026, 9, 13, 22, 30, tzinfo=BRT)
    assert pricing_context("DEEPSEEK", local_sunday) == "PEAK"

    # Saturday 02:00 UTC is always off-peak even though its clock hour is inside a
    # weekday peak interval. This protects against an hour-only implementation.
    saturday = datetime(2026, 9, 12, 2, 0, tzinfo=UTC)
    assert pricing_context("DEEPSEEK", saturday) == "OFF_PEAK"

    monday_first_window = datetime(2026, 9, 14, 1, 0, tzinfo=UTC)
    monday_gap = datetime(2026, 9, 14, 4, 0, tzinfo=UTC)
    monday_second_window = datetime(2026, 9, 14, 6, 0, tzinfo=UTC)
    assert pricing_context("DEEPSEEK", monday_first_window) == "PEAK"
    assert pricing_context("DEEPSEEK", monday_gap) == "OFF_PEAK"
    assert pricing_context("DEEPSEEK", monday_second_window) == "PEAK"


def test_deepseek_flash_current_prices_apply_from_2026_08_16_change() -> None:
    peak = resolve_price(
        "DEEPSEEK",
        "deepseek-v4-flash",
        at=datetime(2026, 9, 14, 1, 30, tzinfo=UTC),
        input_tokens=10_000,
    )
    off_peak = resolve_price(
        "DEEPSEEK",
        "deepseek-v4-flash",
        at=datetime(2026, 9, 14, 12, 0, tzinfo=UTC),
        input_tokens=10_000,
    )
    assert peak is not None
    assert off_peak is not None
    assert (peak.input_price_per_million, peak.cached_input_price_per_million, peak.output_price_per_million) == pytest.approx((0.44, 0.014, 1.32))
    assert (off_peak.input_price_per_million, off_peak.cached_input_price_per_million, off_peak.output_price_per_million) == pytest.approx((0.22, 0.007, 0.66))


def test_deepseek_flash_is_unpriced_before_current_contract_effective_time() -> None:
    before_current_contract = resolve_price(
        "DEEPSEEK",
        "deepseek-v4-flash",
        at=datetime(2026, 8, 16, 15, 59, tzinfo=UTC),
        input_tokens=10_000,
    )
    assert before_current_contract is None


def test_every_public_auto_default_model_has_a_current_price() -> None:
    at = datetime(2026, 9, 12, 18, 0, tzinfo=UTC)
    pairs = (
        ("OPENAI", "gpt-5.6-luna"),
        ("DEEPSEEK", "deepseek-v4-flash"),
        ("MIMO", "mimo-v2.5"),
        ("XAI", "grok-4.6"),
        ("QWEN", "qwen3.8-flash"),
        ("GEMINI", "gemini-3.8-flash"),
        ("ANTHROPIC", "claude-sonnet-5"),
    )
    for provider, model in pairs:
        assert resolve_price(provider, model, at=at, input_tokens=10_000) is not None


def test_m18_and_auto_share_the_exact_same_pricing_catalog() -> None:
    assert m18_ai.PRICING_CATALOG is PRICING_CATALOG


def test_openai_long_context_and_xai_thresholds_are_applied() -> None:
    at = datetime(2026, 9, 12, 18, 0, tzinfo=UTC)
    openai = resolve_price("OPENAI", "gpt-5.6-luna", at=at, input_tokens=272_001)
    xai_short = resolve_price("XAI", "grok-4.6", at=at, input_tokens=199_999)
    xai_long = resolve_price("XAI", "grok-4.6", at=at, input_tokens=200_000)
    assert openai is not None and openai.pricing_context == "LONG_CONTEXT_GT_272K"
    assert (openai.input_price_per_million, openai.cached_input_price_per_million, openai.output_price_per_million) == pytest.approx((0.40, 0.04, 1.80))
    assert xai_short is not None and xai_short.pricing_context == "SHORT_CONTEXT"
    assert xai_long is not None and xai_long.pricing_context == "LONG_CONTEXT"
    assert xai_short.input_price_per_million == pytest.approx(2.0)
    assert xai_long.input_price_per_million == pytest.approx(4.0)


def test_gemini_promotion_expiry_fails_closed_until_catalog_review() -> None:
    current = resolve_price(
        "GEMINI", "gemini-3.8-flash",
        at=datetime(2026, 12, 31, 23, 59, tzinfo=UTC), input_tokens=20_000,
    )
    expired = resolve_price(
        "GEMINI", "gemini-3.8-flash",
        at=datetime(2027, 1, 1, 0, 0, tzinfo=UTC), input_tokens=20_000,
    )
    assert current is not None
    assert current.input_price_per_million == pytest.approx(0.75)
    assert current.output_price_per_million == pytest.approx(3.75)
    assert expired is None


def test_reasoning_effort_increases_expected_output_envelope() -> None:
    assert reasoning_output_multiplier("NONE") < reasoning_output_multiplier("LOW")
    assert reasoning_output_multiplier("LOW") < reasoning_output_multiplier("HIGH")
    assert reasoning_output_multiplier("HIGH") < reasoning_output_multiplier("MAX")


def test_gemini_observed_cost_bills_reported_thought_tokens_as_output() -> None:
    usage = ProviderUsage(
        input_tokens=1_000_000,
        cached_input_tokens=0,
        output_tokens=1_000_000,
        reasoning_tokens=1_000_000,
        total_tokens=3_000_000,
    )
    cost, currency, version = estimate_observed_cost(
        "GEMINI",
        "gemini-3.8-flash",
        usage,
        datetime(2026, 9, 12, 18, 0, tzinfo=UTC),
    )
    assert cost == pytest.approx(8.25)
    assert currency == "USD"
    assert version.startswith("RASAI-PRICING-")


class _PricedProvider:
    def __init__(self, name: str, model: str, rank: int, reasoning: str = "NONE") -> None:
        self.name = name
        self.model = model
        self.reasoning_profile = reasoning
        self.policy = SimpleNamespace(rank=rank, qualification="TEST")

    def _request_payload(self, request):
        return {"model": self.model, "input": "x" * 8_000}


def test_auto_orders_priced_active_candidates_by_estimated_request_cost() -> None:
    # With the same request envelope/reasoning, MiMo V2.5 has the lowest output tariff
    # among this set and is expected to be first. This tests the cost router itself,
    # independently of provider transport behavior.
    openai = _PricedProvider("OPENAI", "gpt-5.6-luna", 1)
    deepseek = _PricedProvider("DEEPSEEK", "deepseek-v4-flash", 2)
    mimo = _PricedProvider("MIMO", "mimo-v2.5", 3)
    session = DynamicProviderRoutingSession((openai, deepseek, mimo))
    ordered = session.ordered_candidates_for_need(SimpleNamespace(evidence=()), scope="SEMANTIC")
    assert ordered[0].name == "MIMO"


def test_unpriced_candidates_keep_deterministic_rotating_order() -> None:
    a = _PricedProvider("A", "a", 1)
    b = _PricedProvider("B", "b", 2)
    c = _PricedProvider("C", "c", 3)
    session = DynamicProviderRoutingSession((a, b, c))
    assert [item.name for item in session.ordered_candidates_for_need()] == ["A", "B", "C"]
    session.coordinator._cursor = 1
    assert [item.name for item in session.ordered_candidates_for_need()] == ["B", "C", "A"]


def test_review_date_is_explicit_and_machine_readable() -> None:
    assert PRICING_REVIEW_RECOMMENDED_ON == "2026-10-13"