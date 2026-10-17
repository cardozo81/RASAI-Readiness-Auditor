"""Canonical economic telemetry boundary for AI usage, pricing and aggregation.

This module owns operational application of pricing policy to observed AI usage
and provider-neutral accounting semantics reused by reports. Pricing formulas
and catalog resolution remain in rasai.ai_cost_policy.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from math import isfinite
from typing import Any, Iterable, Mapping

from rasai.ai_cost_policy import (
    CandidateCostEstimate,
    PricingApplication,
    estimate_candidate_cost,
    resolve_native_usage_cost,
    resolve_observed_cost,
    runtime_pricing_conditions,
)


@dataclass(frozen=True, slots=True)
class MonetaryAggregate:
    """Currency-safe monetary aggregate for persisted AI attempts."""

    totals: tuple[tuple[str, float], ...]
    unpriced_attempts: int = 0

    @property
    def single_currency(self) -> tuple[str, float] | None:
        return self.totals[0] if len(self.totals) == 1 else None

    @property
    def mixed_currency(self) -> bool:
        return len(self.totals) > 1


def _value(source: Any, key: str) -> Any:
    if isinstance(source, Mapping):
        return source.get(key)
    try:
        return source[key]
    except (KeyError, IndexError, TypeError):
        return getattr(source, key, None)


def _integer(value: Any) -> int | None:
    """Accept exact, nonnegative token counts; never truncate or clamp usage."""
    if type(value) is int:
        return value if 0 <= value <= 999_999_999_999_999_999 else None
    if (isinstance(value, str) and 0 < len(value) <= 18
            and value.isascii() and value.isdecimal()):
        return int(value)
    return None


def _currency(value: Any) -> str | None:
    """Only canonical three-letter monetary denominations can be aggregated."""
    if not isinstance(value, str):
        return None
    text = value.strip().upper()
    return text if len(text) == 3 and text.isascii() and text.isalpha() else None


def canonical_total_tokens(source: Any) -> int | None:
    """Return canonical total tokens without double-counting reasoning.

    Provider-reported total_tokens wins when present. Otherwise the only safe
    derivation is input + output. reasoning_tokens is a breakdown of output
    and is never added again.
    """

    raw_total = _value(source, "total_tokens")
    total = _integer(raw_total)
    if raw_total is not None:
        # A present but corrupt provider total is not permission to
        # substitute a derived total from a different accounting basis.
        return total
    raw_input = _value(source, "input_tokens")
    raw_output = _value(source, "output_tokens")
    input_tokens = _integer(raw_input)
    output_tokens = _integer(raw_output)
    # An explicit invalid count is not an absent count. Deriving a
    # deceptively low total from the remaining field misstates usage.
    if ((raw_input is not None and input_tokens is None)
            or (raw_output is not None and output_tokens is None)):
        return None
    if input_tokens is None and output_tokens is None:
        return None
    derived = int(input_tokens or 0) + int(output_tokens or 0)
    # Two bounded fields can still overflow the canonical token budget.
    return derived if derived <= 999_999_999_999_999_999 else None


def price_usage(
    provider: str,
    model: str,
    usage: Any,
    at: datetime,
    *,
    runtime_conditions: Mapping[str, str] | None = None,
    surface: str | None = None,
) -> PricingApplication:
    """Apply the canonical catalog to usage observed after one provider call."""

    return resolve_observed_cost(
        provider,
        model,
        usage,
        at,
        runtime_conditions=runtime_conditions,
        surface=surface,
    )


def price_provider_usage(provider: Any, usage: Any, at: datetime) -> PricingApplication:
    """Price observed usage using the provider effective runtime conditions."""

    return price_usage(
        str(getattr(provider, "name", "") or ""),
        str(getattr(provider, "model", "") or ""),
        usage,
        at,
        runtime_conditions=runtime_pricing_conditions(provider),
        surface=str(getattr(provider, "surface", "") or ""),
    )


def price_attempt_usage(attempt: Any) -> PricingApplication:
    """Reapply canonical pricing to an already materialized attempt."""

    conditions = _value(attempt, "pricing_runtime_conditions")
    try:
        normalized_conditions = dict(conditions or ())
    except (TypeError, ValueError):
        normalized_conditions = {}
    return price_usage(
        str(_value(attempt, "provider") or ""),
        str(_value(attempt, "model") or ""),
        _value(attempt, "usage"),
        _value(attempt, "finished_at"),
        runtime_conditions=normalized_conditions or None,
        surface=str(_value(attempt, "surface") or ""),
    )


def price_native_usage(
    provider: str,
    surface: str,
    components: Any,
    at: datetime,
    *,
    runtime_conditions: Mapping[str, str] | None = None,
) -> PricingApplication:
    """Apply canonical non-token pricing for one native usage observation."""

    return resolve_native_usage_cost(
        provider,
        surface,
        components,
        at,
        runtime_conditions=runtime_conditions,
    )


def forecast_candidate_cost(
    provider: Any,
    request: Any,
    *,
    scope: str,
    at: datetime,
    history_hint: Mapping[str, float] | None = None,
) -> CandidateCostEstimate:
    """Estimate a pre-call candidate cost for routing/forecast only."""

    return estimate_candidate_cost(
        provider,
        request,
        scope=scope,
        at=at,
        history_hint=history_hint,
    )


def _valid_monetary_amount(raw: Any) -> float | None:
    """Reject corrupted costs rather than publishing negative or nonfinite totals."""
    try:
        if isinstance(raw, bool):
            return None
        value = float(raw)
    except (TypeError, ValueError, OverflowError):
        return None
    return value if isfinite(value) and value >= 0 else None


def attempt_monetary_cost(attempt: Any) -> tuple[float | None, str | None, str]:
    """Return one persisted monetary value without inventing exchange rates."""
    observed = _value(attempt, "observed_cost")
    if observed not in (None, ""):
        currency = (
            _value(attempt, "observed_cost_currency")
            or _value(attempt, "cost_currency")
            or _value(attempt, "currency")
        )
        normalized_currency = _currency(currency)
        value = _valid_monetary_amount(observed)
        return value, normalized_currency, (
            "PROVIDER_OBSERVED" if value is not None else "INVALID"
        )

    estimated = _value(attempt, "estimated_cost")
    if estimated not in (None, ""):
        currency = _value(attempt, "cost_currency") or _value(attempt, "currency")
        normalized_currency = _currency(currency)
        value = _valid_monetary_amount(estimated)
        return value, normalized_currency, (
            "USAGE_DERIVED_ESTIMATE" if value is not None else "INVALID"
        )

    legacy = _value(attempt, "estimated_cost_usd")
    if legacy not in (None, ""):
        value = _valid_monetary_amount(legacy)
        return value, "USD", (
            "LEGACY_USAGE_DERIVED_ESTIMATE" if value is not None else "INVALID"
        )
    return None, None, "UNPRICED"


def _has_usage(attempt: Any) -> bool:
    return any(
        _value(attempt, key) is not None
        for key in (
            "input_tokens",
            "cached_input_tokens",
            "output_tokens",
            "reasoning_tokens",
            "total_tokens",
            "native_usage_quantity",
        )
    ) or bool(_value(attempt, "_native_usage"))


def aggregate_attempt_costs(attempts: Iterable[Any]) -> MonetaryAggregate:
    """Aggregate attempt costs by currency and preserve unpriced observations."""

    totals: dict[str, float] = {}
    unpriced = 0
    for attempt in attempts:
        amount, currency, _basis = attempt_monetary_cost(attempt)
        if amount is None or not currency:
            if _has_usage(attempt):
                unpriced += 1
            continue
        code = currency.upper()
        totals[code] = totals.get(code, 0.0) + float(amount)
    return MonetaryAggregate(
        totals=tuple((currency, round(amount, 10)) for currency, amount in sorted(totals.items())),
        unpriced_attempts=unpriced,
    )
