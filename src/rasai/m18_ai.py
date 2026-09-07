"""M18 multi-provider semantic adapters, routing policy and usage telemetry models."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from enum import StrEnum
import hashlib
import json
import os
import re
import time
from typing import Any, Callable, Mapping
from urllib.error import HTTPError, URLError

from rasai.ai_resilience import (
    DECISION_FALLBACK,
    DECISION_FALLBACK_SUCCESS,
    DECISION_RETRY,
    DECISION_STOP,
    DECISION_SUCCESS,
    DECISION_SUCCESS_AFTER_RETRY,
    MAX_AUTO_ATTEMPTS_PER_CONTEXT,
    MAX_PROVIDER_ATTEMPTS_PER_CONTEXT,
    parse_retry_after,
    retry_policy,
)
from rasai.openai_provider import (
    OpenAIProvider as _HardenedOpenAIProvider,
    SEMANTIC_RULE_CRITERIA,
    hardened_semantic_output_schema,
)
from rasai.semantic import (
    EntityCandidate,
    ProviderCallResult,
    ProviderState,
    SEMANTIC_RULE_IDS,
    SemanticEvidenceError,
    SemanticInput,
    SemanticProviderError,
    SemanticProviderResponse,
    SemanticRuleAssessment,
    SemanticSchemaError,
    _extract_json_payload,
    normalize_provider_payload,
)

SEMANTIC_CONTRACT_VERSION = "M18-SEMANTIC-22-v1"
QUALIFICATION_VERSION = "RASAI-PROVIDER-QUAL-2026-09-03"
PRICING_VERSION = "RASAI-PRICING-2026-09-03"


class ProviderErrorClass(StrEnum):
    AUTH_ERROR = "AUTH_ERROR"
    QUOTA_ERROR = "QUOTA_ERROR"
    CREDIT_ERROR = "CREDIT_ERROR"
    RATE_LIMIT_ERROR = "RATE_LIMIT_ERROR"
    MODEL_ERROR = "MODEL_ERROR"
    PERMISSION_ERROR = "PERMISSION_ERROR"
    NETWORK_ERROR = "NETWORK_ERROR"
    TIMEOUT_ERROR = "TIMEOUT_ERROR"
    SERVER_ERROR = "SERVER_ERROR"
    CONTRACT_ERROR = "CONTRACT_ERROR"
    EMPTY_RESPONSE = "EMPTY_RESPONSE"
    INVALID_RESPONSE = "INVALID_RESPONSE"
    UNKNOWN_PROVIDER_ERROR = "UNKNOWN_PROVIDER_ERROR"


class AttemptStatus(StrEnum):
    SUCCESS = "SUCCESS"
    TECHNICAL_ERROR = "TECHNICAL_ERROR"
    BUSINESS_ERROR = "BUSINESS_ERROR"
    CONTRACT_ERROR = "CONTRACT_ERROR"
    SKIPPED = "SKIPPED"
    QUARANTINED = "QUARANTINED"


class RuntimeProviderState(StrEnum):
    ACTIVE = "ACTIVE"
    STANDBY = "STANDBY"
    QUARANTINED_FOR_AUDIT = "QUARANTINED_FOR_AUDIT"


@dataclass(frozen=True, slots=True)
class ProviderUsage:
    input_tokens: int | None = None
    cached_input_tokens: int | None = None
    output_tokens: int | None = None
    reasoning_tokens: int | None = None
    total_tokens: int | None = None


@dataclass(frozen=True, slots=True)
class ProviderDiagnostic:
    error_class: ProviderErrorClass | None = None
    http_status: int | None = None
    error_type: str | None = None
    error_code: str | None = None
    request_id: str | None = None
    retry_after_seconds: float | None = None

    @property
    def reason(self) -> str | None:
        if self.error_class is None:
            return None
        parts = ["AI_PROVIDER_UNAVAILABLE", self.error_class.value]
        if self.http_status is not None:
            parts.append(f"HTTP_{self.http_status}")
        if self.error_type:
            parts.append(f"type={self.error_type}")
        if self.error_code:
            parts.append(f"code={self.error_code}")
        if self.request_id:
            parts.append(f"request_id={self.request_id}")
        return ":".join(parts)


@dataclass(frozen=True, slots=True)
class ProviderAttempt:
    provider: str
    model: str | None
    reasoning_profile: str
    provider_rank: int
    attempt_index: int
    snapshot_id: str
    url: str
    started_at: datetime
    finished_at: datetime
    duration_ms: int
    status: AttemptStatus
    diagnostic: ProviderDiagnostic | None = None
    usage: ProviderUsage | None = None
    estimated_cost: float | None = None
    cost_currency: str | None = None
    pricing_version: str | None = None
    request_message_summary: str = ""
    request_payload_hash: str | None = None
    provider_qualification: str | None = None
    provider_reliability_score: float | None = None
    qualification_version: str = QUALIFICATION_VERSION
    semantic_contract_version: str = SEMANTIC_CONTRACT_VERSION
    retry_eligible: bool = False
    decision: str = DECISION_STOP
    fallback_from_provider: str | None = None
    fallback_reason: str | None = None


@dataclass(frozen=True, slots=True)
class SemanticProviderResult(ProviderCallResult):
    """Provider-neutral result with a legacy ProviderCallResult compatibility surface."""

    provider: str = ""
    model: str | None = None
    reasoning_profile: str = "NONE"
    usage: ProviderUsage | None = None
    diagnostic: ProviderDiagnostic | None = None

    @property
    def status(self) -> ProviderState:
        return self.state

    @property
    def assessments(self) -> tuple[SemanticRuleAssessment, ...]:
        return self.response.assessments if self.response is not None else ()

    @property
    def entities(self) -> tuple[EntityCandidate, ...]:
        return self.response.entities if self.response is not None else ()

    @property
    def primary_intent(self) -> str | None:
        return self.response.primary_intent if self.response is not None else None

    @property
    def secondary_intents(self) -> tuple[str, ...]:
        return self.response.secondary_intents if self.response is not None else ()


@dataclass(frozen=True, slots=True)
class ProviderPolicy:
    rank: int
    provider: str
    model: str
    recommended_depth: str
    rasai_class: str
    qualification: str
    recommended_use: str
    reliability_score: float | None = None


ROUTING_POLICY: tuple[ProviderPolicy, ...] = (
    ProviderPolicy(1, "OPENAI", "gpt-5.6-sol", "HIGH/XHIGH", "QUALIFIED-A+", "QUALIFIED", "máxima qualidade"),
    ProviderPolicy(2, "OPENAI", "gpt-5.6-terra", "HIGH", "QUALIFIED-A", "QUALIFIED", "default"),
    ProviderPolicy(3, "DEEPSEEK", "deepseek-v4-pro", "HIGH", "PROVISIONAL-A-", "PROVISIONAL", "alternativa forte"),
    ProviderPolicy(4, "MIMO", "mimo-v2.5-pro", "THINKING_ENABLED", "PROVISIONAL-B+", "PROVISIONAL", "alternativa forte"),
    ProviderPolicy(5, "OPENAI", "gpt-5.6-luna", "HIGH", "QUALIFIED-B+", "QUALIFIED", "volume/custo"),
    ProviderPolicy(6, "DEEPSEEK", "deepseek-v4-flash", "HIGH", "PROVISIONAL-B", "PROVISIONAL", "volume/custo"),
    ProviderPolicy(7, "MIMO", "mimo-v2.5", "THINKING_ENABLED", "PROVISIONAL-B", "PROVISIONAL", "volume/multimodal"),
)
_POLICY_BY_KEY = {(item.provider, item.model): item for item in ROUTING_POLICY}

SUPPORTED_MODELS: dict[str, tuple[str, ...]] = {
    "OPENAI": ("gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna"),
    "DEEPSEEK": ("deepseek-v4-pro", "deepseek-v4-flash"),
    "MIMO": ("mimo-v2.5-pro", "mimo-v2.5"),
}
DEFAULT_MODELS = {
    "OPENAI": "gpt-5.6-terra",
    "DEEPSEEK": "deepseek-v4-pro",
    "MIMO": "mimo-v2.5-pro",
}
DEFAULT_REASONING = {"OPENAI": "HIGH", "DEEPSEEK": "HIGH", "MIMO": "HIGH"}
MODEL_ENV = {
    "OPENAI": "RASAI_OPENAI_MODEL",
    "DEEPSEEK": "RASAI_DEEPSEEK_MODEL",
    "MIMO": "RASAI_MIMO_MODEL",
}
REASONING_ENV = {
    "OPENAI": "RASAI_OPENAI_REASONING_EFFORT",
    "DEEPSEEK": "RASAI_DEEPSEEK_REASONING_EFFORT",
    "MIMO": "RASAI_MIMO_REASONING_EFFORT",
}
KEY_ENV = {"OPENAI": "OPENAI_API_KEY", "DEEPSEEK": "DEEPSEEK_API_KEY", "MIMO": "MIMO_API_KEY"}


@dataclass(frozen=True, slots=True)
class ProviderPricing:
    provider: str
    model: str
    effective_from: str
    input_price_per_million: float
    cached_input_price_per_million: float
    output_price_per_million: float
    currency: str
    source_reference: str
    pricing_version: str = PRICING_VERSION
    pricing_context: str = "STANDARD"


# Current public pay-as-you-go prices verified on 2026-09-03. OpenAI GPT-5.6 Sol
# is under promotional pricing through at least 2026-11-21. DeepSeek switches
# between deterministic UTC peak/off-peak contexts.
PRICING_CATALOG: tuple[ProviderPricing, ...] = (
    ProviderPricing("OPENAI", "gpt-5.6-sol", "2026-08-21", 4.0, 0.40, 20.0, "USD", "https://developers.openai.com/api/docs/models/gpt-5.6-sol"),
    ProviderPricing("OPENAI", "gpt-5.6-terra", "2026-08-21", 2.0, 0.20, 12.0, "USD", "https://developers.openai.com/api/docs/models/gpt-5.6-terra"),
    ProviderPricing("OPENAI", "gpt-5.6-luna", "2026-08-21", 0.20, 0.02, 1.20, "USD", "https://developers.openai.com/api/docs/models/gpt-5.6-luna"),
    ProviderPricing("DEEPSEEK", "deepseek-v4-pro", "2026-08-16T16:00:00Z", 1.32, 0.044, 3.96, "USD", "https://api-docs.deepseek.com/quick_start/pricing/", pricing_context="PEAK"),
    ProviderPricing("DEEPSEEK", "deepseek-v4-pro", "2026-08-16T16:00:00Z", 0.66, 0.022, 1.98, "USD", "https://api-docs.deepseek.com/quick_start/pricing/", pricing_context="OFF_PEAK"),
    ProviderPricing("DEEPSEEK", "deepseek-v4-flash", "2026-08-16T16:00:00Z", 0.44, 0.014, 1.32, "USD", "https://api-docs.deepseek.com/quick_start/pricing/", pricing_context="PEAK"),
    ProviderPricing("DEEPSEEK", "deepseek-v4-flash", "2026-08-16T16:00:00Z", 0.22, 0.007, 0.66, "USD", "https://api-docs.deepseek.com/quick_start/pricing/", pricing_context="OFF_PEAK"),
    ProviderPricing("MIMO", "mimo-v2.5-pro", "2026-05-27T00:00:00+08:00", 0.435, 0.0036, 0.87, "USD", "https://mimo.mi.com/docs/en-US/price/pay-as-you-go"),
    ProviderPricing("MIMO", "mimo-v2.5", "2026-05-27T00:00:00+08:00", 0.14, 0.0028, 0.28, "USD", "https://mimo.mi.com/docs/en-US/price/pay-as-you-go"),
)

_SAFE_TOKEN = re.compile(r"[^A-Za-z0-9_.-]+")
Transport = Callable[[str, dict[str, str], bytes, float], dict[str, Any]]


def _safe_token(value: Any) -> str | None:
    if value is None:
        return None
    token = _SAFE_TOKEN.sub("_", str(value).strip())[:96].strip("_")
    return token or None


def _policy(provider: str, model: str) -> ProviderPolicy:
    try:
        return _POLICY_BY_KEY[(provider, model)]
    except KeyError as exc:
        raise ValueError(f"unsupported RASAi model for {provider}: {model}") from exc


def _pricing_context(provider: str, at: datetime) -> str:
    if provider != "DEEPSEEK":
        return "STANDARD"
    hour = at.astimezone(timezone.utc).hour
    # Peak: 01:00-04:00 and 06:00-10:00 UTC, all other hours off-peak.
    return "PEAK" if 1 <= hour < 4 or 6 <= hour < 10 else "OFF_PEAK"


def estimate_cost(provider: str, model: str, usage: ProviderUsage | None, at: datetime) -> tuple[float | None, str | None, str | None]:
    if usage is None or usage.input_tokens is None or usage.output_tokens is None:
        return None, None, None
    context = _pricing_context(provider, at)
    price = next((item for item in PRICING_CATALOG if item.provider == provider and item.model == model and item.pricing_context == context), None)
    if price is None:
        return None, None, None
    cached = usage.cached_input_tokens
    if cached is None:
        # Never assume zero cached tokens when the provider did not report it.
        return None, price.currency, price.pricing_version
    uncached = max(usage.input_tokens - cached, 0)
    amount = (
        uncached * price.input_price_per_million
        + cached * price.cached_input_price_per_million
        + usage.output_tokens * price.output_price_per_million
    ) / 1_000_000
    return round(amount, 10), price.currency, price.pricing_version


def _usage_from_native(raw: Mapping[str, Any]) -> ProviderUsage | None:
    usage = raw.get("usage")
    if not isinstance(usage, Mapping):
        return None
    input_details = usage.get("input_tokens_details")
    output_details = usage.get("output_tokens_details")
    return ProviderUsage(
        input_tokens=_int_or_none(usage.get("input_tokens")),
        cached_input_tokens=_int_or_none(input_details.get("cached_tokens")) if isinstance(input_details, Mapping) else None,
        output_tokens=_int_or_none(usage.get("output_tokens")),
        reasoning_tokens=_int_or_none(output_details.get("reasoning_tokens")) if isinstance(output_details, Mapping) else None,
        total_tokens=_int_or_none(usage.get("total_tokens")),
    )


def _int_or_none(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        result = int(value)
    except (TypeError, ValueError):
        return None
    return result if result >= 0 else None


def _diagnostic_from_http(exc: HTTPError) -> ProviderDiagnostic:
    error_type = None
    error_code = None
    try:
        raw = exc.read(65536)
        decoded = json.loads(raw.decode("utf-8", errors="replace"))
        error = decoded.get("error") if isinstance(decoded, dict) else None
        if isinstance(error, dict):
            error_type = _safe_token(error.get("type"))
            error_code = _safe_token(error.get("code"))
    except (OSError, UnicodeError, json.JSONDecodeError, AttributeError, TypeError, ValueError):
        pass
    request_id = None
    try:
        if exc.headers is not None:
            request_id = _safe_token(exc.headers.get("x-request-id") or exc.headers.get("request-id"))
    except (AttributeError, TypeError):
        pass
    retry_after_seconds = None
    try:
        if exc.headers is not None:
            retry_after_seconds = parse_retry_after(exc.headers.get('Retry-After'))
    except (AttributeError, TypeError, ValueError):
        pass
    return ProviderDiagnostic(
        error_class=_classify_http_error(int(exc.code), error_type, error_code),
        http_status=int(exc.code),
        error_type=error_type,
        error_code=error_code,
        request_id=request_id,
        retry_after_seconds=retry_after_seconds,
    )


def _classify_http_error(status: int, error_type: str | None, error_code: str | None) -> ProviderErrorClass:
    token = " ".join(item.casefold() for item in (error_type, error_code) if item)
    if status == 401:
        return ProviderErrorClass.AUTH_ERROR
    if status == 403:
        return ProviderErrorClass.PERMISSION_ERROR
    if "credit" in token or "balance" in token:
        return ProviderErrorClass.CREDIT_ERROR
    if "quota" in token:
        return ProviderErrorClass.QUOTA_ERROR
    if status == 429:
        return ProviderErrorClass.RATE_LIMIT_ERROR
    if status == 404 or "model" in token:
        return ProviderErrorClass.MODEL_ERROR
    if status >= 500:
        return ProviderErrorClass.SERVER_ERROR
    return ProviderErrorClass.UNKNOWN_PROVIDER_ERROR


def _response_error(raw: Mapping[str, Any]) -> ProviderDiagnostic | None:
    status = str(raw.get("status") or "").casefold()
    error = raw.get("error")
    if status not in {"failed", "incomplete"} and not error:
        return None
    error_type = None
    error_code = None
    if isinstance(error, Mapping):
        error_type = _safe_token(error.get("type"))
        error_code = _safe_token(error.get("code"))
    return ProviderDiagnostic(
        error_class=ProviderErrorClass.INVALID_RESPONSE,
        error_type=error_type,
        error_code=error_code or (_safe_token(status) if status else None),
    )


def _deepseek_semantic_output_schema() -> dict[str, Any]:
    # Provider-wire schema that guarantees all 22 semantic rules without
    # array cardinality keywords. The RASAi canonical model remains an
    # ordered assessment array after local normalization.
    schema = json.loads(json.dumps(hardened_semantic_output_schema()))
    canonical_assessment = schema["properties"]["assessments"]["items"]
    assessment_value = json.loads(json.dumps(canonical_assessment))
    assessment_value["properties"].pop("rule_id", None)
    assessment_value["required"] = [
        field for field in assessment_value["required"] if field != "rule_id"
    ]
    schema["properties"]["assessments"] = {
        "type": "object",
        "properties": {
            rule_id: json.loads(json.dumps(assessment_value))
            for rule_id in SEMANTIC_RULE_IDS
        },
        "required": list(SEMANTIC_RULE_IDS),
        "additionalProperties": False,
    }
    # DeepSeek documents maxItems/minItems as unsupported in its strict schema
    # subset. Local RASAi validation continues to enforce <= 5 intents.
    schema["properties"]["secondary_intents"].pop("maxItems", None)
    return schema


def _canonicalize_deepseek_wire_payload(payload: Any) -> Any:
    # Convert the DeepSeek keyed assessment object to the canonical RASAi array.
    if not isinstance(payload, Mapping):
        return payload
    assessments = payload.get("assessments")
    if not isinstance(assessments, Mapping):
        # Backward-compatible acceptance of an already-canonical array response.
        return payload

    expected = frozenset(SEMANTIC_RULE_IDS)
    received = frozenset(str(key) for key in assessments)
    if received != expected or len(assessments) != len(SEMANTIC_RULE_IDS):
        raise SemanticSchemaError("INCOMPLETE_SEMANTIC_OUTPUT")

    canonical_assessments: list[dict[str, Any]] = []
    for rule_id in SEMANTIC_RULE_IDS:
        raw = assessments.get(rule_id)
        if not isinstance(raw, Mapping):
            raise SemanticSchemaError(f"INVALID_ASSESSMENT_OBJECT_{rule_id}")
        if "rule_id" in raw:
            raise SemanticSchemaError(f"UNEXPECTED_RULE_ID_FIELD_{rule_id}")
        canonical_assessments.append({"rule_id": rule_id, **dict(raw)})

    canonical = dict(payload)
    canonical["assessments"] = canonical_assessments
    return canonical


class ResponsesSemanticProvider(_HardenedOpenAIProvider):
    """Shared provider adapter using Responses-compatible HTTPS and RASAi validation."""

    name = "GENERIC"
    endpoint = ""
    auth_mode = "bearer"
    structured_mode = "json_schema"
    capabilities = ("RESPONSES_API", "STRUCTURED_OUTPUT", "LOCAL_SCHEMA_VALIDATION", "REASONING", "USAGE")

    def __init__(
        self,
        *,
        model: str,
        reasoning_effort: str,
        api_key: str | None = None,
        endpoint: str | None = None,
        timeout: float = 45.0,
        transport: Transport | None = None,
    ) -> None:
        # Reuse the hardened provider's transport/configuration fields; API key
        # is passed explicitly so subclasses do not accidentally read OPENAI_API_KEY.
        super().__init__(model=model, api_key=api_key, endpoint=endpoint or self.endpoint, timeout=timeout, transport=transport)
        self.requested_reasoning_effort = self._validate_reasoning(reasoning_effort)
        self.reasoning_profile = self._reasoning_profile(self.requested_reasoning_effort)
        self._last_attempt: ProviderAttempt | None = None
        self._last_attempts: tuple[ProviderAttempt, ...] = ()
        self._history: list[ProviderAttempt] = []
        self.policy = _policy(self.name, self.model)
        self._runtime_state = RuntimeProviderState.ACTIVE
        self._successful_urls: set[str] = set()

    def _validate_reasoning(self, value: str) -> str:
        normalized = value.strip().upper()
        allowed = {"NONE", "LOW", "MEDIUM", "HIGH", "XHIGH", "MAX"}
        if normalized not in allowed:
            raise ValueError(f"unsupported reasoning effort for {self.name}: {value}")
        return normalized

    def _reasoning_profile(self, value: str) -> str:
        return value

    def _headers(self) -> dict[str, str]:
        if self.auth_mode == "api-key":
            return {"api-key": self.api_key or "", "Content-Type": "application/json"}
        return {"Authorization": f"Bearer {self.api_key or ''}", "Content-Type": "application/json"}

    def _request_payload(self, semantic_input: SemanticInput) -> dict[str, Any]:
        criteria = "\n".join(f"- {rule_id}: {SEMANTIC_RULE_CRITERIA[rule_id]}" for rule_id in SEMANTIC_RULE_IDS)
        instructions = (
            "Evaluate only the supplied page evidence for Search & AI Readiness. Return JSON only. "
            "Never invent evidence_ids or hidden facts. Do not score the website. Use UNKNOWN when "
            "evidence is insufficient and NOT_APPLICABLE only when the rule genuinely does not apply. "
            "The assessments array MUST contain exactly one item for every rule listed below, with no "
            "omissions, duplicates or unknown rule ids.\n\nSemantic rule contract:\n" + criteria
        )
        semantic_schema = hardened_semantic_output_schema()
        if self.name == "DEEPSEEK":
            semantic_schema = _deepseek_semantic_output_schema()
            instructions += (
                "\n\nDeepSeek wire contract: assessments MUST be a JSON object keyed by every "
                "rule id BR-GEO-028 through BR-GEO-049 exactly once. Each keyed value contains "
                "the assessment fields except rule_id; RASAi derives rule_id from the key."
            )

        format_payload: dict[str, Any]
        if self.structured_mode == "json_object":
            instructions += "\n\nThe complete JSON Schema below is normative and will be validated locally:\n" + json.dumps(semantic_schema, ensure_ascii=False, separators=(",", ":"))
            format_payload = {"type": "json_object"}
        else:
            format_payload = {
                "type": "json_schema",
                "name": "rasai_semantic_assessment",
                "schema": semantic_schema,
            }
            if self.name == "OPENAI":
                format_payload["strict"] = True
        return {
            "model": self.model,
            "instructions": instructions,
            "input": [{"role": "user", "content": [{"type": "input_text", "text": "JSON page evidence:\n" + json.dumps(semantic_input.provider_payload(), ensure_ascii=False)}]}],
            "reasoning": {"effort": self.requested_reasoning_effort.casefold()},
            "text": {"format": format_payload},
        }

    def analyze(
        self,
        semantic_input: SemanticInput,
        *,
        max_attempts: int = MAX_PROVIDER_ATTEMPTS_PER_CONTEXT,
    ) -> SemanticProviderResult:
        """Execute at most one bounded retry for transient integration failures."""
        self._last_attempts = ()
        collected: list[ProviderAttempt] = []
        bounded = max(1, min(int(max_attempts), MAX_PROVIDER_ATTEMPTS_PER_CONTEXT))
        last_result: SemanticProviderResult | None = None
        for ordinal in range(1, bounded + 1):
            result = self._analyze_once(semantic_input)
            last_result = result
            attempt = self._last_attempt
            self._last_attempt = None
            policy = retry_policy(None)
            if attempt is not None:
                diagnostic = attempt.diagnostic
                policy = retry_policy(
                    diagnostic.error_class if diagnostic else None,
                    diagnostic.retry_after_seconds if diagnostic else None,
                )
                estimated = attempt.estimated_cost
                currency = attempt.cost_currency
                pricing_version = attempt.pricing_version
                if attempt.usage is not None and estimated is None:
                    estimated, currency, pricing_version = estimate_cost(
                        attempt.provider, attempt.model or "", attempt.usage, attempt.finished_at
                    )
                if result.status is ProviderState.AVAILABLE:
                    decision = DECISION_SUCCESS_AFTER_RETRY if ordinal > 1 else DECISION_SUCCESS
                elif policy.eligible and ordinal < bounded:
                    decision = DECISION_RETRY
                else:
                    decision = DECISION_STOP
                annotated = replace(
                    attempt,
                    attempt_index=ordinal,
                    retry_eligible=policy.eligible,
                    decision=decision,
                    estimated_cost=estimated,
                    cost_currency=currency,
                    pricing_version=pricing_version,
                )
                if self._history and self._history[-1] == attempt:
                    self._history[-1] = annotated
                collected.append(annotated)

            if result.status is ProviderState.AVAILABLE:
                self._last_attempts = tuple(collected)
                return result
            if result.status is ProviderState.NOT_CONFIGURED:
                self._last_attempts = tuple(collected)
                return result
            if attempt is not None and policy.eligible and ordinal < bounded:
                # _analyze_once quarantines every failure. A transient retry is the
                # only case allowed to reactivate it, and only for this one retry.
                self._runtime_state = RuntimeProviderState.ACTIVE
                if policy.delay_seconds > 0:
                    time.sleep(policy.delay_seconds)
                continue
            self._last_attempts = tuple(collected)
            return result

        self._last_attempts = tuple(collected)
        return last_result or SemanticProviderResult(
            ProviderState.UNAVAILABLE,
            reason="AI_PROVIDER_UNAVAILABLE",
            provider=self.name,
            model=self.model,
            reasoning_profile=self.reasoning_profile,
        )

    def _analyze_once(self, semantic_input: SemanticInput) -> SemanticProviderResult:
        self._last_attempt = None
        if self._runtime_state is RuntimeProviderState.QUARANTINED_FOR_AUDIT:
            return SemanticProviderResult(
                ProviderState.UNAVAILABLE,
                reason="AI_PROVIDER_UNAVAILABLE:PROVIDER_QUARANTINED",
                provider=self.name,
                model=self.model,
                reasoning_profile=self.reasoning_profile,
                diagnostic=ProviderDiagnostic(ProviderErrorClass.UNKNOWN_PROVIDER_ERROR, error_code="PROVIDER_QUARANTINED"),
            )
        if not self.api_key:
            return SemanticProviderResult(
                ProviderState.NOT_CONFIGURED,
                reason="AI_NOT_CONFIGURED",
                provider=self.name,
                model=self.model,
                reasoning_profile=self.reasoning_profile,
            )

        started_at = datetime.now(timezone.utc)
        started_perf = time.perf_counter()
        request = self._request_payload(semantic_input)
        body = json.dumps(request, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        summary = f"semantic_contract={SEMANTIC_CONTRACT_VERSION};rules=22;evidence={len(semantic_input.evidence)};snapshot={semantic_input.snapshot_id}"
        payload_hash = hashlib.sha256(body).hexdigest()

        try:
            raw = self._transport(self.endpoint, self._headers(), body, self.timeout)
        except HTTPError as exc:
            return self._failure_result(semantic_input, started_at, started_perf, summary, payload_hash, _diagnostic_from_http(exc), AttemptStatus.TECHNICAL_ERROR)
        except TimeoutError:
            return self._failure_result(semantic_input, started_at, started_perf, summary, payload_hash, ProviderDiagnostic(ProviderErrorClass.TIMEOUT_ERROR), AttemptStatus.TECHNICAL_ERROR)
        except (URLError, OSError):
            return self._failure_result(semantic_input, started_at, started_perf, summary, payload_hash, ProviderDiagnostic(ProviderErrorClass.NETWORK_ERROR), AttemptStatus.TECHNICAL_ERROR)
        except Exception:
            return self._failure_result(semantic_input, started_at, started_perf, summary, payload_hash, ProviderDiagnostic(ProviderErrorClass.UNKNOWN_PROVIDER_ERROR), AttemptStatus.TECHNICAL_ERROR)

        if not isinstance(raw, Mapping):
            return self._failure_result(semantic_input, started_at, started_perf, summary, payload_hash, ProviderDiagnostic(ProviderErrorClass.INVALID_RESPONSE), AttemptStatus.CONTRACT_ERROR)
        if not raw.get("output_text") and not raw.get("output"):
            return self._failure_result(semantic_input, started_at, started_perf, summary, payload_hash, ProviderDiagnostic(ProviderErrorClass.EMPTY_RESPONSE), AttemptStatus.CONTRACT_ERROR, usage=_usage_from_native(raw))
        native_error = _response_error(raw)
        if native_error is not None:
            return self._failure_result(semantic_input, started_at, started_perf, summary, payload_hash, native_error, AttemptStatus.TECHNICAL_ERROR)

        usage = _usage_from_native(raw)
        try:
            payload = _extract_json_payload(dict(raw))
            if self.name == "DEEPSEEK":
                payload = _canonicalize_deepseek_wire_payload(payload)
            normalized = normalize_provider_payload(
                payload,
                semantic_input.allowed_evidence_ids,
                provider=self.name,
                model=self.model,
                configuration_version=self.configuration_version,
                prompt_id=self.prompt_id,
                prompt_version=self.prompt_version,
            )
            received = tuple(item.rule_id for item in normalized.assessments)
            if len(received) != len(SEMANTIC_RULE_IDS) or frozenset(received) != frozenset(SEMANTIC_RULE_IDS):
                raise SemanticSchemaError("INCOMPLETE_SEMANTIC_OUTPUT")
        except (SemanticSchemaError, SemanticEvidenceError) as exc:
            return self._failure_result(
                semantic_input,
                started_at,
                started_perf,
                summary,
                payload_hash,
                ProviderDiagnostic(
                    ProviderErrorClass.CONTRACT_ERROR,
                    error_type=type(exc).__name__,
                    error_code=_safe_token(str(exc)),
                ),
                AttemptStatus.CONTRACT_ERROR,
                usage=usage,
            )
        except SemanticProviderError as exc:
            error_class = ProviderErrorClass.EMPTY_RESPONSE if "no textual output" in str(exc).casefold() else ProviderErrorClass.INVALID_RESPONSE
            return self._failure_result(semantic_input, started_at, started_perf, summary, payload_hash, ProviderDiagnostic(error_class, error_type=type(exc).__name__), AttemptStatus.CONTRACT_ERROR, usage=usage)
        except (json.JSONDecodeError, UnicodeError, TypeError, ValueError) as exc:
            return self._failure_result(semantic_input, started_at, started_perf, summary, payload_hash, ProviderDiagnostic(ProviderErrorClass.INVALID_RESPONSE, error_type=type(exc).__name__), AttemptStatus.CONTRACT_ERROR, usage=usage)

        finished_at = datetime.now(timezone.utc)
        duration_ms = max(0, int((time.perf_counter() - started_perf) * 1000))
        estimated, currency, pricing_version = estimate_cost(self.name, self.model, usage, finished_at)
        self._last_attempt = ProviderAttempt(
            provider=self.name,
            model=self.model,
            reasoning_profile=self.reasoning_profile,
            provider_rank=self.policy.rank,
            attempt_index=1,
            snapshot_id=semantic_input.snapshot_id,
            url=semantic_input.page_url,
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=duration_ms,
            status=AttemptStatus.SUCCESS,
            usage=usage,
            estimated_cost=estimated,
            cost_currency=currency,
            pricing_version=pricing_version,
            request_message_summary=summary,
            request_payload_hash=payload_hash,
            provider_qualification=self.policy.qualification,
            provider_reliability_score=self.policy.reliability_score,
        )
        self._runtime_state = RuntimeProviderState.ACTIVE
        self._successful_urls.add(semantic_input.page_url)
        self._history.append(self._last_attempt)
        return SemanticProviderResult(
            ProviderState.AVAILABLE,
            response=normalized,
            provider=self.name,
            model=self.model,
            reasoning_profile=self.reasoning_profile,
            usage=usage,
        )

    def _failure_result(
        self,
        semantic_input: SemanticInput,
        started_at: datetime,
        started_perf: float,
        summary: str,
        payload_hash: str,
        diagnostic: ProviderDiagnostic,
        status: AttemptStatus,
        *,
        usage: ProviderUsage | None = None,
    ) -> SemanticProviderResult:
        finished_at = datetime.now(timezone.utc)
        duration_ms = max(0, int((time.perf_counter() - started_perf) * 1000))
        self._last_attempt = ProviderAttempt(
            provider=self.name,
            model=self.model,
            reasoning_profile=self.reasoning_profile,
            provider_rank=self.policy.rank,
            attempt_index=1,
            snapshot_id=semantic_input.snapshot_id,
            url=semantic_input.page_url,
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=duration_ms,
            status=status,
            diagnostic=diagnostic,
            usage=usage,
            request_message_summary=summary,
            request_payload_hash=payload_hash,
            provider_qualification=self.policy.qualification,
            provider_reliability_score=self.policy.reliability_score,
        )
        self._runtime_state = RuntimeProviderState.QUARANTINED_FOR_AUDIT
        self._history.append(self._last_attempt)
        return SemanticProviderResult(
            ProviderState.UNAVAILABLE,
            reason=diagnostic.reason,
            provider=self.name,
            model=self.model,
            reasoning_profile=self.reasoning_profile,
            usage=usage,
            diagnostic=diagnostic,
        )

    def consume_attempts(self) -> tuple[ProviderAttempt, ...]:
        attempts = self._last_attempts
        self._last_attempts = ()
        self._last_attempt = None
        return attempts

    def attempt_history(self) -> tuple[ProviderAttempt, ...]:
        return tuple(self._history)

    def session_snapshot(self) -> dict[str, Any]:
        successful = bool(self._successful_urls)
        return {
            "strategy": "SINGLE_PROVIDER",
            "enabled": True,
            "initial_provider": self.name,
            "initial_model": self.model,
            "initial_reasoning_profile": self.reasoning_profile,
            "effective_provider": self.name if successful else None,
            "effective_model": self.model if successful else None,
            "effective_reasoning_profile": self.reasoning_profile if successful else None,
            "configured_chain": [{
                "provider": self.name,
                "model": self.model,
                "reasoning_profile": self.reasoning_profile,
                "rank": self.policy.rank,
                "qualification": self.policy.qualification,
            }],
            "provider_states": {self.name: self._runtime_state.value},
            "successful_urls": {self.name: len(self._successful_urls)},
            "excluded_configurations": [],
        }


class OpenAIProvider(ResponsesSemanticProvider):
    name = "OPENAI"
    endpoint = "https://api.openai.com/v1/responses"
    auth_mode = "bearer"
    structured_mode = "json_schema"

    def __init__(self, *, model: str = DEFAULT_MODELS["OPENAI"], reasoning_effort: str = DEFAULT_REASONING["OPENAI"], api_key: str | None = None, endpoint: str | None = None, timeout: float = 45.0, transport: Transport | None = None) -> None:
        super().__init__(model=model, reasoning_effort=reasoning_effort, api_key=api_key if api_key is not None else os.environ.get("OPENAI_API_KEY"), endpoint=endpoint, timeout=timeout, transport=transport)


class DeepSeekProvider(ResponsesSemanticProvider):
    name = "DEEPSEEK"
    endpoint = "https://api.deepseek.com/responses"
    auth_mode = "bearer"
    structured_mode = "json_schema"

    def __init__(self, *, model: str = DEFAULT_MODELS["DEEPSEEK"], reasoning_effort: str = DEFAULT_REASONING["DEEPSEEK"], api_key: str | None = None, endpoint: str | None = None, timeout: float = 45.0, transport: Transport | None = None) -> None:
        super().__init__(model=model, reasoning_effort=reasoning_effort, api_key=api_key if api_key is not None else os.environ.get("DEEPSEEK_API_KEY"), endpoint=endpoint, timeout=timeout, transport=transport)


class MiMoProvider(ResponsesSemanticProvider):
    name = "MIMO"
    endpoint = "https://api.xiaomimimo.com/v1/responses"
    auth_mode = "api-key"
    # Xiaomi currently documents JSON structured output with local schema
    # validation rather than a Responses JSON-Schema guarantee.
    structured_mode = "json_object"

    def _validate_reasoning(self, value: str) -> str:
        normalized = value.strip().upper()
        if normalized not in {"NONE", "LOW", "MEDIUM", "HIGH"}:
            raise ValueError(f"unsupported reasoning effort for MIMO: {value}")
        return normalized

    def _reasoning_profile(self, value: str) -> str:
        return "NONE" if value == "NONE" else "THINKING_ENABLED"

    def __init__(self, *, model: str = DEFAULT_MODELS["MIMO"], reasoning_effort: str = DEFAULT_REASONING["MIMO"], api_key: str | None = None, endpoint: str | None = None, timeout: float = 45.0, transport: Transport | None = None) -> None:
        super().__init__(model=model, reasoning_effort=reasoning_effort, api_key=api_key if api_key is not None else os.environ.get("MIMO_API_KEY"), endpoint=endpoint, timeout=timeout, transport=transport)


@dataclass(slots=True)
class ProviderRoutingSession:
    providers: tuple[ResponsesSemanticProvider, ...]
    strategy: str = "AUTO"
    excluded_configurations: tuple[str, ...] = ()
    _states: dict[str, RuntimeProviderState] = field(init=False, default_factory=dict)
    _pins: dict[str, str] = field(init=False, default_factory=dict)
    _last_attempts: tuple[ProviderAttempt, ...] = field(init=False, default=())
    _active_provider: str | None = field(init=False, default=None)
    _successful_urls: dict[str, set[str]] = field(init=False, default_factory=dict)
    _history: list[ProviderAttempt] = field(init=False, default_factory=list)

    def __post_init__(self) -> None:
        ordered = tuple(sorted(self.providers, key=lambda item: item.policy.rank))
        self.providers = ordered
        for index, provider in enumerate(ordered):
            self._states[provider.name] = RuntimeProviderState.ACTIVE if index == 0 else RuntimeProviderState.STANDBY
            self._successful_urls.setdefault(provider.name, set())
        self._active_provider = ordered[0].name if ordered else None

    @property
    def name(self) -> str:
        return "AUTO"

    @property
    def model(self) -> str | None:
        provider = self._provider_by_name(self._active_provider)
        return provider.model if provider else None

    @property
    def reasoning_profile(self) -> str:
        provider = self._provider_by_name(self._active_provider)
        return provider.reasoning_profile if provider else "NONE"

    @property
    def capabilities(self) -> tuple[str, ...]:
        return ("MULTI_PROVIDER_ROUTING", "AUDIT_QUARANTINE", "BOUNDED_RETRY", "BOUNDED_AUTO_FALLBACK", "USAGE_TELEMETRY")

    @property
    def initial_provider(self) -> ResponsesSemanticProvider | None:
        return self.providers[0] if self.providers else None

    @property
    def effective_provider(self) -> ResponsesSemanticProvider | None:
        return self._provider_by_name(self._active_provider)

    def analyze(self, semantic_input: SemanticInput) -> SemanticProviderResult:
        self._last_attempts = ()
        if not self.providers:
            return SemanticProviderResult(ProviderState.NOT_CONFIGURED, reason="AI_NOT_CONFIGURED", provider="AUTO", reasoning_profile="NONE")

        candidates = list(self._healthy_candidates())
        pinned_name = self._pins.get(semantic_input.page_url)
        if pinned_name:
            # A previous success keeps preference, but an integration failure may
            # legitimately fall back to another healthy provider for this context.
            candidates.sort(key=lambda item: (0 if item.name == pinned_name else 1, item.policy.rank))
        if not candidates:
            return SemanticProviderResult(ProviderState.UNAVAILABLE, reason="AI_PROVIDER_CHAIN_EXHAUSTED", provider="AUTO", reasoning_profile="NONE")

        attempts: list[ProviderAttempt] = []
        last_result: SemanticProviderResult | None = None
        fallback_from: str | None = None
        fallback_reason: str | None = None

        for candidate_index, provider in enumerate(candidates):
            remaining = MAX_AUTO_ATTEMPTS_PER_CONTEXT - len(attempts)
            if remaining <= 0:
                break
            result = provider.analyze(
                semantic_input,
                max_attempts=min(MAX_PROVIDER_ATTEMPTS_PER_CONTEXT, remaining),
            )
            local = list(provider.consume_attempts())
            if fallback_from is not None:
                local = [
                    replace(
                        item,
                        fallback_from_provider=fallback_from,
                        fallback_reason=fallback_reason,
                    )
                    for item in local
                ]
            local = [
                replace(item, attempt_index=len(attempts) + offset)
                for offset, item in enumerate(local, 1)
            ]
            attempts.extend(local)
            last_result = result

            if result.status is ProviderState.AVAILABLE:
                if fallback_from is not None and attempts:
                    attempts[-1] = replace(
                        attempts[-1],
                        decision=DECISION_FALLBACK_SUCCESS,
                        fallback_from_provider=fallback_from,
                        fallback_reason=fallback_reason,
                    )
                self._pins[semantic_input.page_url] = provider.name
                self._promote(provider.name)
                self._successful_urls[provider.name].add(semantic_input.page_url)
                self._last_attempts = tuple(attempts)
                self._history.extend(self._last_attempts)
                return result

            if result.status is ProviderState.NOT_CONFIGURED:
                continue

            self._quarantine(provider.name)
            has_next = (
                candidate_index < len(candidates) - 1
                and len(attempts) < MAX_AUTO_ATTEMPTS_PER_CONTEXT
            )
            if has_next:
                if attempts:
                    attempts[-1] = replace(attempts[-1], decision=DECISION_FALLBACK)
                fallback_from = provider.name
                fallback_reason = result.reason or "AI_PROVIDER_UNAVAILABLE"

        self._last_attempts = tuple(attempts)
        self._history.extend(self._last_attempts)
        if len(attempts) >= MAX_AUTO_ATTEMPTS_PER_CONTEXT and self._healthy_candidates():
            return SemanticProviderResult(
                ProviderState.UNAVAILABLE,
                reason="AI_PROVIDER_ATTEMPT_BUDGET_EXHAUSTED",
                provider="AUTO",
                reasoning_profile="NONE",
            )
        if self._healthy_candidates():
            return last_result or SemanticProviderResult(ProviderState.UNAVAILABLE, reason="AI_PROVIDER_UNAVAILABLE", provider="AUTO", reasoning_profile="NONE")
        return SemanticProviderResult(ProviderState.UNAVAILABLE, reason="AI_PROVIDER_CHAIN_EXHAUSTED", provider="AUTO", reasoning_profile="NONE")

    def consume_attempts(self) -> tuple[ProviderAttempt, ...]:
        attempts = self._last_attempts
        self._last_attempts = ()
        return attempts

    def attempt_history(self) -> tuple[ProviderAttempt, ...]:
        return tuple(self._history)

    def session_snapshot(self) -> dict[str, Any]:
        initial = self.initial_provider
        effective = self.effective_provider
        return {
            "strategy": self.strategy,
            "enabled": bool(self.providers),
            "initial_provider": initial.name if initial else None,
            "initial_model": initial.model if initial else None,
            "initial_reasoning_profile": initial.reasoning_profile if initial else None,
            "effective_provider": effective.name if effective and any(self._successful_urls.values()) else None,
            "effective_model": effective.model if effective and any(self._successful_urls.values()) else None,
            "effective_reasoning_profile": effective.reasoning_profile if effective and any(self._successful_urls.values()) else None,
            "configured_chain": [
                {"provider": item.name, "model": item.model, "reasoning_profile": item.reasoning_profile, "rank": item.policy.rank, "qualification": item.policy.qualification}
                for item in self.providers
            ],
            "provider_states": {key: value.value for key, value in self._states.items()},
            "successful_urls": {key: len(value) for key, value in self._successful_urls.items()},
            "excluded_configurations": list(self.excluded_configurations),
        }

    def _healthy_candidates(self) -> tuple[ResponsesSemanticProvider, ...]:
        healthy = [item for item in self.providers if self._states.get(item.name) is not RuntimeProviderState.QUARANTINED_FOR_AUDIT]
        if self._active_provider:
            healthy.sort(key=lambda item: (0 if item.name == self._active_provider else 1, item.policy.rank))
        else:
            healthy.sort(key=lambda item: item.policy.rank)
        return tuple(healthy)

    def _quarantine(self, provider_name: str) -> None:
        if provider_name in self._states:
            self._states[provider_name] = RuntimeProviderState.QUARANTINED_FOR_AUDIT
        if self._active_provider == provider_name:
            remaining = self._healthy_candidates()
            self._active_provider = remaining[0].name if remaining else None
            if self._active_provider:
                self._states[self._active_provider] = RuntimeProviderState.ACTIVE

    def _promote(self, provider_name: str) -> None:
        for name, state in tuple(self._states.items()):
            if state is RuntimeProviderState.QUARANTINED_FOR_AUDIT:
                continue
            self._states[name] = RuntimeProviderState.ACTIVE if name == provider_name else RuntimeProviderState.STANDBY
        self._active_provider = provider_name

    def _provider_by_name(self, name: str | None) -> ResponsesSemanticProvider | None:
        return next((item for item in self.providers if item.name == name), None)


def provider_session_snapshot(provider: Any) -> dict[str, Any]:
    if hasattr(provider, "session_snapshot"):
        return provider.session_snapshot()
    name = str(getattr(provider, "name", "NONE")).upper()
    model = getattr(provider, "model", None)
    reasoning = getattr(provider, "reasoning_profile", None)
    enabled = name not in {"NONE", ""}
    return {
        "strategy": "SINGLE_PROVIDER" if enabled else "NONE",
        "enabled": enabled,
        "initial_provider": name if enabled else None,
        "initial_model": model,
        "initial_reasoning_profile": reasoning,
        "effective_provider": None,
        "effective_model": None,
        "effective_reasoning_profile": None,
        "configured_chain": ([{"provider": name, "model": model, "reasoning_profile": reasoning, "rank": _POLICY_BY_KEY.get((name, model)).rank if (name, model) in _POLICY_BY_KEY else None}] if enabled else []),
        "provider_states": {},
        "successful_urls": {},
        "excluded_configurations": [],
    }


def consume_provider_attempts(provider: Any) -> tuple[ProviderAttempt, ...]:
    consumer = getattr(provider, "consume_attempts", None)
    if callable(consumer):
        return tuple(consumer())
    return ()


def provider_attempt_history(provider: Any) -> tuple[ProviderAttempt, ...]:
    history = getattr(provider, "attempt_history", None)
    if callable(history):
        return tuple(history())
    return ()


def _resolve_config(provider_name: str, *, model_override: str | None = None, env: Mapping[str, str] | None = None) -> tuple[str, str, str | None]:
    environment = env if env is not None else os.environ
    model = (model_override or environment.get(MODEL_ENV[provider_name]) or DEFAULT_MODELS[provider_name]).strip()
    if model not in SUPPORTED_MODELS[provider_name]:
        raise ValueError(f"unsupported RASAi model for {provider_name}: {model}; allowed: {', '.join(SUPPORTED_MODELS[provider_name])}")
    reasoning = (environment.get(REASONING_ENV[provider_name]) or DEFAULT_REASONING[provider_name]).strip().upper()
    key = environment.get(KEY_ENV[provider_name])
    return model, reasoning, key


def build_semantic_provider(selection: str, *, model_override: str | None = None, env: Mapping[str, str] | None = None) -> Any:
    selected = selection.strip().upper()
    if selected == "NONE":
        from rasai.semantic import NoneProvider
        return NoneProvider()
    if selected == "AUTO":
        environment = env if env is not None else os.environ
        providers: list[ResponsesSemanticProvider] = []
        excluded: list[str] = []
        for provider_name in ("OPENAI", "DEEPSEEK", "MIMO"):
            if not environment.get(KEY_ENV[provider_name]):
                continue
            try:
                model, reasoning, key = _resolve_config(provider_name, env=environment)
                providers.append(_provider_instance(provider_name, model=model, reasoning=reasoning, key=key))
            except ValueError:
                excluded.append(f"{provider_name}:INVALID_CONFIGURATION")
        return ProviderRoutingSession(tuple(providers), strategy="AUTO", excluded_configurations=tuple(excluded))
    if selected not in SUPPORTED_MODELS:
        raise ValueError(f"unsupported AI provider: {selection}")
    model, reasoning, key = _resolve_config(selected, model_override=model_override, env=env)
    return _provider_instance(selected, model=model, reasoning=reasoning, key=key)


def _provider_instance(provider_name: str, *, model: str, reasoning: str, key: str | None) -> ResponsesSemanticProvider:
    if provider_name == "OPENAI":
        return OpenAIProvider(model=model, reasoning_effort=reasoning, api_key=key)
    if provider_name == "DEEPSEEK":
        return DeepSeekProvider(model=model, reasoning_effort=reasoning, api_key=key)
    if provider_name == "MIMO":
        return MiMoProvider(model=model, reasoning_effort=reasoning, api_key=key)
    raise ValueError(provider_name)
