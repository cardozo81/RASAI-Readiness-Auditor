"""Cost-aware routing policy used only by the public AI=AUTO runtime.

The catalog intentionally models only synchronous request modes already used by RASAi.
It does not silently opt a request into Batch, Flex, Priority, token-plan, or any other
provider service tier that changes latency, quota, or contractual semantics.

Pricing is a routing estimate, not an invoice. When cache telemetry is unavailable,
pre-call routing assumes a cache miss and observed-cost normalization also uses the
uncached price as a conservative ceiling.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import math
from typing import Any, Mapping

PRICING_VERSION = "RASAI-PRICING-2026-09-12"
PRICING_VERIFIED_ON = "2026-09-12"
PRICING_REVIEW_RECOMMENDED_ON = "2026-10-12"

# Approximation used only before the provider returns native usage. The router learns
# from native usage during the same execution and replaces these defaults progressively.
_TOKEN_CHARS_ESTIMATE = 4.0
_SCOPE_DEFAULT_INPUT_TOKENS: dict[str, int] = {
    "SEMANTIC": 8_000,
    "CONTENT_REMEDIATION": 12_000,
    "M24_TECHNICAL_REMEDIATION": 6_000,
    "SOURCE_QUALITY": 2_500,
}
_SCOPE_DEFAULT_OUTPUT_TOKENS: dict[str, int] = {
    "SEMANTIC": 4_000,
    "CONTENT_REMEDIATION": 2_500,
    "M24_TECHNICAL_REMEDIATION": 3_200,
    "SOURCE_QUALITY": 1_800,
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


# Public synchronous API prices verified on 2026-09-12. DeepSeek Flash changed at
# 2026-09-10 12:00 Beijing Time == 2026-09-10 04:00 UTC; the live platform usage
# banner is the source for the new Flash unit prices. The historical rules are kept so
# attempt timestamps before the change remain priceable.
PRICING_CATALOG: tuple[PricingRule, ...] = (
    PricingRule("OPENAI", "gpt-5.6-sol", 4.00, 0.40, 20.00, "USD", "https://developers.openai.com/api/docs/models/gpt-5.6-sol", "2026-08-21T00:00:00Z"),
    PricingRule("OPENAI", "gpt-5.6-terra", 2.00, 0.20, 12.00, "USD", "https://developers.openai.com/api/docs/models/gpt-5.6-terra", "2026-08-21T00:00:00Z"),
    PricingRule("OPENAI", "gpt-5.6-luna", 0.20, 0.02, 1.20, "USD", "https://developers.openai.com/api/docs/models/gpt-5.6-luna", "2026-08-21T00:00:00Z"),

    PricingRule("DEEPSEEK", "deepseek-v4-pro", 1.32, 0.044, 3.96, "USD", "https://api-docs.deepseek.com/quick_start/pricing/", "2026-08-16T16:00:00Z", pricing_context="PEAK"),
    PricingRule("DEEPSEEK", "deepseek-v4-pro", 0.66, 0.022, 1.98, "USD", "https://api-docs.deepseek.com/quick_start/pricing/", "2026-08-16T16:00:00Z", pricing_context="OFF_PEAK"),
    PricingRule("DEEPSEEK", "deepseek-v4-flash", 0.44, 0.014, 1.32, "USD", "https://api-docs.deepseek.com/quick_start/pricing/", "2026-08-16T16:00:00Z", "2026-09-10T04:00:00Z", "PEAK"),
    PricingRule("DEEPSEEK", "deepseek-v4-flash", 0.22, 0.007, 0.66, "USD", "https://api-docs.deepseek.com/quick_start/pricing/", "2026-08-16T16:00:00Z", "2026-09-10T04:00:00Z", "OFF_PEAK"),
    PricingRule("DEEPSEEK", "deepseek-v4-flash", 0.30, 0.006, 1.20, "USD", "https://platform.deepseek.com/usage", "2026-09-10T04:00:00Z", pricing_context="PEAK"),
    PricingRule("DEEPSEEK", "deepseek-v4-flash", 0.15, 0.003, 0.60, "USD", "https://platform.deepseek.com/usage", "2026-09-10T04:00:00Z", pricing_context="OFF_PEAK"),
    PricingRule("DEEPSEEK", "deepseek-flash", 0.30, 0.006, 1.20, "USD", "https://platform.deepseek.com/usage", "2026-09-10T04:00:00Z", pricing_context="PEAK"),
    PricingRule("DEEPSEEK", "deepseek-flash", 0.15, 0.003, 0.60, "USD", "https://platform.deepseek.com/usage", "2026-09-10T04:00:00Z", pricing_context="OFF_PEAK"),

    PricingRule("MIMO", "mimo-v2.5-pro", 0.435, 0.0036, 0.87, "USD", "https://mimo.mi.com/docs/en-US/price/pay-as-you-go", "2026-08-06T00:00:00Z"),
    PricingRule("MIMO", "mimo-v2.5", 0.14, 0.0028, 0.28, "USD", "https://mimo.mi.com/docs/en-US/price/pay-as-you-go", "2026-08-06T00:00:00Z"),

    PricingRule("XAI", "grok-4.6", 2.00, 0.50, 6.00, "USD", "https://docs.x.ai/developers/pricing", "2026-09-02T00:00:00Z", pricing_context="SHORT_CONTEXT"),
    PricingRule("XAI", "grok-4.6", 4.00, 1.00, 12.00, "USD", "https://docs.x.ai/developers/pricing", "2026-09-02T00:00:00Z", pricing_context="LONG_CONTEXT"),

    PricingRule("QWEN", "qwen3.8-flash", 0.113, 0.014, 0.382, "USD", "https://www.alibabacloud.com/help/en/model-studio/qwen3-8-flash", "2026-09-07T00:00:00Z"),
    PricingRule("QWEN", "qwen3.8-max", 1.65, 0.206, 4.951, "USD", "https://www.alibabacloud.com/help/en/model-studio/qwen3-8-max", "2026-09-07T00:00:00Z"),

    PricingRule("GEMINI", "gemini-3.8-flash", 0.75, 0.075, 3.75, "USD", "https://ai.google.dev/gemini-api/docs/pricing", "2026-09-02T00:00:00Z", "2027-01-01T00:00:00Z"),
    PricingRule("GEMINI", "gemini-3.8-flash", 1.50, 0.15, 7.50, "USD", "https://ai.google.dev/gemini-api/docs/pricing", "2027-01-01T00:00:00Z"),

    PricingRule("ANTHROPIC", "claude-sonnet-5", 2.00, 0.20, 10.00, "USD", "https://platform.claude.com/docs/en/about-claude/pricing", "2026-09-01T00:00:00Z"),
)


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _parse_instant(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def pricing_review_due(at: datetime | None = None) -> bool:
    instant = _utc(at or datetime.now(timezone.utc))
    review = datetime.fromisoformat(PRICING_REVIEW_RECOMMENDED_ON).replace(tzinfo=timezone.utc)
    return instant >= review


def pricing_context(provider: str, at: datetime, *, input_tokens: int = 0) -> str:
    name = provider.strip().upper()
    instant = _utc(at)
    if name == "DEEPSEEK":
        # Provider policy is explicitly UTC and Monday-Friday. Converting weekday in a
        # consumer timezone is wrong because the first UTC window begins on Sunday 22:00
        # in Brazil (UTC-3).
        weekday_peak = instant.weekday() < 5
        hour = instant.hour
        return "PEAK" if weekday_peak and (1 <= hour < 4 or 6 <= hour < 10) else "OFF_PEAK"
    if name == "XAI":
        return "LONG_CONTEXT" if int(input_tokens) >= 200_000 else "SHORT_CONTEXT"
    return "STANDARD"


def _active_rule(provider: str, model: str, at: datetime, context: str) -> PricingRule | None:
    instant = _utc(at)
    candidates: list[PricingRule] = []
    for item in PRICING_CATALOG:
        if item.provider != provider.upper() or item.model != model or item.pricing_context != context:
            continue
        if instant < _parse_instant(item.effective_from):
            continue
        if item.effective_until is not None and instant >= _parse_instant(item.effective_until):
            continue
        candidates.append(item)
    if not candidates:
        return None
    return max(candidates, key=lambda item: _parse_instant(item.effective_from))


def resolve_price(provider: str, model: str, *, at: datetime, input_tokens: int) -> ResolvedPrice | None:
    provider_name = provider.strip().upper()
    context = pricing_context(provider_name, at, input_tokens=input_tokens)
    rule = _active_rule(provider_name, model, at, context)
    if rule is None:
        return None

    input_price = rule.input_price_per_million
    cached_price = rule.cached_input_price_per_million
    output_price = rule.output_price_per_million
    resolved_context = context

    # GPT-5.6 family pages state that prompts above 272k input tokens price the full
    # request at 2x input and 1.5x output. Apply the input multiplier to cached input too
    # so the pre-call estimate does not understate the long-context request.
    if provider_name == "OPENAI" and input_tokens > 272_000:
        input_price *= 2.0
        cached_price *= 2.0
        output_price *= 1.5
        resolved_context = "LONG_CONTEXT_GT_272K"

    return ResolvedPrice(
        provider=provider_name,
        model=model,
        input_price_per_million=input_price,
        cached_input_price_per_million=cached_price,
        output_price_per_million=output_price,
        currency=rule.currency,
        source_reference=rule.source_reference,
        pricing_context=resolved_context,
    )


def _billable_output_tokens(provider: str, usage: Any) -> int | None:
    output = getattr(usage, "output_tokens", None)
    if output is None:
        return None
    billed = max(int(output), 0)
    # Gemini usage exposes thought/reasoning tokens separately while its price explicitly
    # bills output including thinking tokens.
    if provider.strip().upper() == "GEMINI":
        reasoning = getattr(usage, "reasoning_tokens", None)
        if reasoning is not None:
            billed += max(int(reasoning), 0)
    return billed


def estimate_observed_cost(
    provider: str,
    model: str,
    usage: Any,
    at: datetime,
) -> tuple[float | None, str | None, str]:
    if usage is None:
        return None, None, PRICING_VERSION
    input_tokens = getattr(usage, "input_tokens", None)
    output_tokens = _billable_output_tokens(provider, usage)
    if input_tokens is None or output_tokens is None:
        return None, None, PRICING_VERSION
    input_tokens = max(int(input_tokens), 0)
    cached_raw = getattr(usage, "cached_input_tokens", None)
    cached_tokens = max(min(int(cached_raw or 0), input_tokens), 0)
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


def _estimate_payload_tokens(provider: Any, request: Any, scope: str) -> tuple[int, str]:
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
            output_tokens = max(1, int(round(output_tokens * 0.45 + historical_output * 0.55)))
            basis += "+HISTORY_OUTPUT"
        if 0.0 < cache_ratio <= 1.0:
            cached_tokens = max(0, min(input_tokens, int(round(input_tokens * cache_ratio))))
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
    return frozenset((item.provider, item.model) for item in PRICING_CATALOG)
