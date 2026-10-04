from datetime import datetime, timezone
from types import SimpleNamespace

from rasai import ai_economic_telemetry as economic
from rasai.ai_cost_policy import PricingApplication


def test_canonical_total_tokens_prefers_provider_total_and_never_adds_reasoning() -> None:
    assert economic.canonical_total_tokens(
        {"input_tokens": 100, "output_tokens": 40, "reasoning_tokens": 25, "total_tokens": 140}
    ) == 140
    assert economic.canonical_total_tokens(
        {"input_tokens": 100, "output_tokens": 40, "reasoning_tokens": 25, "total_tokens": None}
    ) == 140
    assert economic.canonical_total_tokens(
        {"input_tokens": None, "output_tokens": None, "reasoning_tokens": 25, "total_tokens": None}
    ) is None


def test_monetary_aggregation_keeps_currencies_separate_and_unpriced_distinct_from_zero() -> None:
    attempts = [
        {"input_tokens": 10, "output_tokens": 5, "estimated_cost": 0.10, "cost_currency": "USD"},
        {"input_tokens": 20, "output_tokens": 8, "estimated_cost": 0.20, "cost_currency": "EUR"},
        {"input_tokens": 30, "output_tokens": 9, "estimated_cost": None, "cost_currency": None},
        {"input_tokens": 1, "output_tokens": 1, "estimated_cost": 0.0, "cost_currency": "USD"},
    ]

    aggregate = economic.aggregate_attempt_costs(attempts)

    assert aggregate.totals == (("EUR", 0.2), ("USD", 0.1))
    assert aggregate.mixed_currency is True
    assert aggregate.single_currency is None
    assert aggregate.unpriced_attempts == 1


def test_missing_currency_remains_unpriced_instead_of_string_none() -> None:
    amount, currency, basis = economic.attempt_monetary_cost(
        {"estimated_cost": 0.30, "cost_currency": None}
    )
    assert amount == 0.30
    assert currency is None
    assert basis == "USAGE_DERIVED_ESTIMATE"

    aggregate = economic.aggregate_attempt_costs(
        [{"input_tokens": 1, "output_tokens": 1, "estimated_cost": 0.30, "cost_currency": None}]
    )
    assert aggregate.totals == ()
    assert aggregate.unpriced_attempts == 1


def test_provider_observed_monetary_cost_wins_over_usage_derived_estimate() -> None:
    amount, currency, basis = economic.attempt_monetary_cost(
        {
            "estimated_cost": 0.30,
            "cost_currency": "USD",
            "observed_cost": 0.27,
            "observed_cost_currency": "USD",
        }
    )
    assert amount == 0.27
    assert currency == "USD"
    assert basis == "PROVIDER_OBSERVED"


def test_price_provider_usage_is_the_operational_delegate(monkeypatch) -> None:
    captured = {}

    monkeypatch.setattr(
        economic,
        "runtime_pricing_conditions",
        lambda provider: {"region": "GLOBAL", "service_tier": "STANDARD"},
    )

    def fake_resolver(provider, model, usage, at, *, runtime_conditions=None, surface=None):
        captured.update(
            provider=provider,
            model=model,
            usage=usage,
            at=at,
            runtime_conditions=runtime_conditions,
            surface=surface,
        )
        return PricingApplication(0.123, "USD", "test-pricing")

    monkeypatch.setattr(economic, "resolve_observed_cost", fake_resolver)
    provider = SimpleNamespace(name="TEST", model="model-1", surface="SEMANTIC")
    usage = SimpleNamespace(input_tokens=10, output_tokens=5)
    at = datetime(2026, 10, 4, tzinfo=timezone.utc)

    application = economic.price_provider_usage(provider, usage, at)

    assert application.estimated_cost == 0.123
    assert captured == {
        "provider": "TEST",
        "model": "model-1",
        "usage": usage,
        "at": at,
        "runtime_conditions": {"region": "GLOBAL", "service_tier": "STANDARD"},
        "surface": "SEMANTIC",
    }
