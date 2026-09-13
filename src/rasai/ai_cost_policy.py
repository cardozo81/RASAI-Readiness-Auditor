"""Canonical AI pricing and cost-aware routing policy for RASAi.

Commercial values are loaded from the declarative pricing catalog. This module keeps the
stable runtime API used by AUTO routing, telemetry, console estimation and persistence.
Pricing is an operational estimate, not a provider invoice.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import math
from typing import Any, Mapping

from rasai.ai_pricing_catalog import PricingCatalog, PricingModelPolicy, load_pricing_catalog, resolve_catalog_rule

_EFFECTIVE_CATALOG: PricingCatalog = load_pricing_catalog()
PRICING_VERSION = _EFFECTIVE_CATALOG.metadata.catalog_version
PRICING_VERIFIED_ON = _EFFECTIVE_CATALOG.metadata.verified_on
PRICING_REFERENCE_DATE = _EFFECTIVE_CATALOG.metadata.reference_date
PRICING_REVIEW_RECOMMENDED_ON = _EFFECTIVE_CATALOG.metadata.review_recommended_on

_TOKEN_CHARS_ESTIMATE = 4.0
_SCOPE_DEFAULT_INPUT_TOKENS: dict[str, int] = {
    "SEMANTIC": 8_000,
    "CONTENT_REMEDIATION": 12_000,
    "M24_TECHNICAL_REMEDIATION": 6_000,
    "SOURCE_QUALITY": 2_500,
    "CONSOLIDATED_SPECIALIST": 10_000,
}
_SCOPE_DEFAULT_OUTPUT_TOKENS: dict[str, int] = {
    "SEMANTIC": 4_000,
    "CONTENT_REMEDIATION": 2_500,
    "M24_TECHNICAL_REMEDIATION": 3_200,
    "SOURCE_QUALITY": 1_800,
    "CONSOLIDATED_SPECIALIST": 3_500,
}
_REASONING_OUTPUT_MULTIPLIER: dict[str, float] = {
    "NONE": 1.00,
    "LOW": 1.10,
    "MEDIUM": 1.35,
    "HIGH": 1.70,
    "XHIGH": 2.20,
    "MAX": 2.80,
    "ADAPTIVE": 1.50,
    "PROVIDER_DEFAULT": 1.20,
    "THINKING_ENABLED": 1.70,
}


@dataclass(frozen=True, slots=True)
class PricingRule:
    provider: str
    model: str
    input_price_per_million: float
    cached_input_price_per_million: float
    output_price_per_million: float
    currency: str
    source_reference: str
    effective_from: str
    effective_until: str | None = None
    pricing_context: str = "STANDARD"
    pricing_version: str = PRICING_VERSION


@dataclass(frozen=True, slots=True)
class ResolvedPrice:
    provider: str
    model: str
    input_price_per_million: float
    cached_input_price_per_million: float
    output_price_per_million: float
    currency: str
    source_reference: str
    pricing_context: str
    pricing_version: str = PRICING_VERSION


@dataclass(frozen=True, slots=True)
class CandidateCostEstimate:
    provider: str
    model: str
    scope: str
    reasoning_profile: str
    estimated_input_tokens: int
    estimated_cached_input_tokens: int
    estimated_output_tokens: int
    estimated_cost: float | None
    currency: str | None
    pricing_context: str | None
    pricing_version: str = PRICING_VERSION
    basis: str = "STATIC_SCOPE"


def _flatten_catalog(catalog: PricingCatalog) -> tuple[PricingRule, ...]:
    rows: list[PricingRule] = []
    for policy in catalog.models:
        for rule in policy.rules:
            rows.append(PricingRule(
                provider=policy.provider,
                model=policy.model,
                input_price_per_million=rule.input_price_per_million,
                cached_input_price_per_million=rule.cached_input_price_per_million,
                output_price_per_million=rule.output_price_per_million,
                currency=policy.currency,
                source_reference=policy.source_reference,
                effective_from=rule.effective_from,
                effective_until=rule.effective_until,
                pricing_context=rule.context,
                pricing_version=catalog.metadata.catalog_version,
            ))
    return tuple(rows)


PRICING_CATALOG: tuple[PricingRule, ...] = _flatten_catalog(_EFFECTIVE_CATALOG)


def effective_pricing_catalog() -> PricingCatalog:
    return _EFFECTIVE_CATALOG


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def pricing_review_due(at: datetime | None = None) -> bool:
    instant = _utc(at or datetime.now(timezone.utc))
    review = datetime.fromisoformat(PRICING_REVIEW_RECOMMENDED_ON).replace(tzinfo=timezone.utc)
    return instant >= review


def _policy_for(provider: str, model: str) -> PricingModelPolicy | None:
    return _EFFECTIVE_CATALOG.model_policy(provider, model)


def pricing_context(provider: str, at: datetime, *, input_tokens: int = 0) -> str:
    """Compatibility helper for callers that only request a provider context."""
    provider_name = provider.strip().upper()
    policies = [item for item in _EFFECTIVE_CATALOG.models if item.provider == provider_name]
    if not policies:
        return "STANDARD"
    resolved = resolve_catalog_rule(
        _EFFECTIVE_CATALOG,
        provider_name,
        policies[0].model,
        at=at,
        input_tokens=input_tokens,
    )
    return resolved[1].context if resolved is not None else "STANDARD"


def resolve_price(provider: str, model: str, *, at: datetime, input_tokens: int) -> ResolvedPrice | None:
    provider_name = provider.strip().upper()
    resolved = resolve_catalog_rule(
        _EFFECTIVE_CATALOG,
        provider_name,
        model,
        at=at,
        input_tokens=input_tokens,
    )
    if resolved is None:
        return None
    policy, rule = resolved
    return ResolvedPrice(
        provider=provider_name,
        model=model,
        input_price_per_million=rule.input_price_per_million,
        cached_input_price_per_million=rule.cached_input_price_per_million,
        output_price_per_million=rule.output_price_per_million,
        currency=policy.currency,
        source_reference=policy.source_reference,
        pricing_context=rule.context,
        pricing_version=_EFFECTIVE_CATALOG.metadata.catalog_version,
    )


def _billable_output_tokens(provider: str, model: str, usage: Any) -> int | None:
    output = getattr(usage, "output_tokens", None)
    if output is None:
        return None
    billed = max(int(output), 0)
    policy = _policy_for(provider, model)
    if policy is not None and policy.reasoning_billing == "ADD_REASONING_TO_OUTPUT":
        reasoning = getattr(usage, "reasoning_tokens", None)
        if reasoning is not None:
            billed += max(int(reasoning), 0)
    return billed


def estimate_observed_cost(provider: str, model: str, usage: Any, at: datetime) -> tuple[float | None, str | None, str]:
    if usage is None:
        return None, None, PRICING_VERSION
    input_tokens = getattr(usage, "input_tokens", None)
    cached_raw = getattr(usage, "cached_input_tokens", None)
    output_tokens = _billable_output_tokens(provider, model, usage)
    if input_tokens is None or cached_raw is None or output_tokens is None:
        return None, None, PRICING_VERSION
    input_tokens = max(int(input_tokens), 0)
    cached_tokens = max(min(int(cached_raw), input_tokens), 0)
    price = resolve_price(provider, model, at=at, input_tokens=input_tokens)
    if price is None:
        return None, None, PRICING_VERSION
    uncached = max(input_tokens - cached_tokens, 0)
    amount = (
        uncached * price.input_price_per_million
        + cached_tokens * price.cached_input_price_per_million
        + output_tokens * price.output_price_per_million
    ) / 1_000_000
    return round(amount, 10), price.currency, PRICING_VERSION


def _request_token_hint(request: Any, field: str) -> int | None:
    try:
        value = getattr(request, field, None)
        if callable(value):
            value = value()
        if value is None:
            return None
        numeric = int(value)
        return numeric if numeric > 0 else None
    except (TypeError, ValueError, OverflowError):
        return None


def _estimate_payload_tokens(provider: Any, request: Any, scope: str) -> tuple[int, str]:
    hinted = _request_token_hint(request, "estimated_input_tokens")
    if hinted is not None:
        return hinted, "REQUEST_HINT"
    builder = getattr(provider, "_request_payload", None)
    if callable(builder) and request is not None:
        try:
            payload = builder(request)
            raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
            return max(1, int(math.ceil(len(raw) / _TOKEN_CHARS_ESTIMATE))), "PROVIDER_PAYLOAD"
        except Exception:
            pass
    return _SCOPE_DEFAULT_INPUT_TOKENS.get(scope, 8_000), "STATIC_SCOPE"


def _base_output_tokens(request: Any, scope: str) -> int:
    hinted = _request_token_hint(request, "estimated_output_tokens")
    if hinted is not None:
        return hinted
    if scope == "CONTENT_REMEDIATION" and request is not None:
        findings = getattr(request, "findings", ())
        try:
            count = len(findings)
        except TypeError:
            count = 0
        return min(16_000, 900 + 650 * max(count, 1))
    if scope == "SEMANTIC" and request is not None:
        evidence = getattr(request, "evidence", ())
        try:
            count = len(evidence)
        except TypeError:
            count = 0
        return min(12_000, 3_200 + 18 * count)
    return _SCOPE_DEFAULT_OUTPUT_TOKENS.get(scope, 3_000)


def reasoning_output_multiplier(reasoning_profile: str | None) -> float:
    key = str(reasoning_profile or "PROVIDER_DEFAULT").strip().upper()
    return _REASONING_OUTPUT_MULTIPLIER.get(key, 1.25)


def estimate_candidate_cost(
    provider: Any,
    request: Any,
    *,
    scope: str,
    at: datetime,
    history_hint: Mapping[str, float] | None = None,
) -> CandidateCostEstimate:
    provider_name = str(getattr(provider, "name", "")).upper()
    model = str(getattr(provider, "model", "") or "")
    reasoning = str(
        getattr(provider, "reasoning_profile", None)
        or getattr(provider, "requested_reasoning_effort", None)
        or "PROVIDER_DEFAULT"
    ).upper()
    input_tokens, basis = _estimate_payload_tokens(provider, request, scope)
    output_tokens = int(math.ceil(_base_output_tokens(request, scope) * reasoning_output_multiplier(reasoning)))
    cached_tokens = 0
    if history_hint:
        historical_input = int(history_hint.get("input_tokens", 0) or 0)
        historical_output = int(history_hint.get("output_tokens", 0) or 0)
        cache_ratio = float(history_hint.get("cache_ratio", 0.0) or 0.0)
        if historical_input > 0:
            input_tokens = max(1, int(round(input_tokens * 0.70 + historical_input * 0.30)))
            basis += "+HISTORY_INPUT"
        if historical_output > 0:
            output_tokens = max(1, int(round(output_tokens * 0.70 + historical_output * 0.30)))
            basis += "+HISTORY_OUTPUT"
        if cache_ratio > 0:
            cached_tokens = max(0, min(input_tokens, int(round(input_tokens * min(cache_ratio, 1.0)))))
            basis += "+HISTORY_CACHE"
    price = resolve_price(provider_name, model, at=at, input_tokens=input_tokens)
    if price is None:
        return CandidateCostEstimate(
            provider=provider_name,
            model=model,
            scope=scope,
            reasoning_profile=reasoning,
            estimated_input_tokens=input_tokens,
            estimated_cached_input_tokens=cached_tokens,
            estimated_output_tokens=output_tokens,
            estimated_cost=None,
            currency=None,
            pricing_context=None,
            basis=basis,
        )
    uncached = max(input_tokens - cached_tokens, 0)
    amount = (
        uncached * price.input_price_per_million
        + cached_tokens * price.cached_input_price_per_million
        + output_tokens * price.output_price_per_million
    ) / 1_000_000
    return CandidateCostEstimate(
        provider=provider_name,
        model=model,
        scope=scope,
        reasoning_profile=reasoning,
        estimated_input_tokens=input_tokens,
        estimated_cached_input_tokens=cached_tokens,
        estimated_output_tokens=output_tokens,
        estimated_cost=round(amount, 10),
        currency=price.currency,
        pricing_context=price.pricing_context,
        basis=basis,
    )


def catalog_models() -> frozenset[tuple[str, str]]:
    return _EFFECTIVE_CATALOG.catalog_models()
