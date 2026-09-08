"""Additive semantic-provider extensions kept outside the M18 homologated core.

The legacy M18 implementation remains the source of truth for NONE, OPENAI,
DEEPSEEK, MIMO and AUTO.  This module only intercepts explicitly selected
extension providers and delegates every legacy selection unchanged.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
import os
import time
from typing import Any, Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from rasai.ai_resilience import (
    DECISION_RETRY, DECISION_STOP, DECISION_SUCCESS, DECISION_SUCCESS_AFTER_RETRY,
    MAX_PROVIDER_ATTEMPTS_PER_CONTEXT, parse_retry_after, retry_policy,
)
from rasai.m18_ai import (
    AttemptStatus,
    ProviderAttempt,
    ProviderDiagnostic,
    ProviderErrorClass,
    ProviderPolicy,
    ProviderUsage,
    RuntimeProviderState,
    estimate_cost,
    SemanticProviderResult,
    build_semantic_provider as _legacy_build_semantic_provider,
)
from rasai.openai_provider import SEMANTIC_RULE_CRITERIA, hardened_semantic_output_schema
from rasai.semantic import (
    ProviderState,
    SEMANTIC_RULE_IDS,
    SemanticEvidenceError,
    SemanticInput,
    SemanticProviderError,
    SemanticSchemaError,
    normalize_provider_payload,
)


EXTENSION_QUALIFICATION_VERSION = "RASAI-PROVIDER-EXT-QUAL-2026-09-03"
EXTENSION_SEMANTIC_CONTRACT_VERSION = "M18-SEMANTIC-22-v1"

EXTENDED_SUPPORTED_MODELS: dict[str, tuple[str, ...]] = {
    "XAI": ("grok-4.6",),
    "QWEN": ("qwen3.8-max", "qwen3.8-flash"),
    "GEMINI": ("gemini-3.8-flash",),
    "ANTHROPIC": ("claude-sonnet-5",),
}
EXTENDED_DEFAULT_MODELS = {
    "XAI": "grok-4.6",
    "QWEN": "qwen3.8-max",
    "GEMINI": "gemini-3.8-flash",
    "ANTHROPIC": "claude-sonnet-5",
}
EXTENDED_KEY_ENV = {
    "XAI": "XAI_API_KEY",
    "QWEN": "DASHSCOPE_API_KEY",
    "GEMINI": "GEMINI_API_KEY",
    "ANTHROPIC": "ANTHROPIC_API_KEY",
}
EXTENDED_MODEL_ENV = {
    "XAI": "RASAI_XAI_MODEL",
    "QWEN": "RASAI_QWEN_MODEL",
    "GEMINI": "RASAI_GEMINI_MODEL",
    "ANTHROPIC": "RASAI_ANTHROPIC_MODEL",
}
EXTENDED_ENDPOINT_ENV = {
    "XAI": "RASAI_XAI_ENDPOINT",
    "QWEN": "RASAI_QWEN_ENDPOINT",
    "GEMINI": "RASAI_GEMINI_ENDPOINT",
    "ANTHROPIC": "RASAI_ANTHROPIC_ENDPOINT",
}

EXTENSION_POLICIES: dict[tuple[str, str], ProviderPolicy] = {
    ("XAI", "grok-4.6"): ProviderPolicy(
        101, "XAI", "grok-4.6", "HIGH", "PROVISIONAL-A", "PROVISIONAL",
        "explicit qualification only",
    ),
    ("QWEN", "qwen3.8-max"): ProviderPolicy(
        102, "QWEN", "qwen3.8-max", "PROVIDER_DEFAULT", "PROVISIONAL-A",
        "PROVISIONAL", "explicit qualification only",
    ),
    ("QWEN", "qwen3.8-flash"): ProviderPolicy(
        103, "QWEN", "qwen3.8-flash", "PROVIDER_DEFAULT", "PROVISIONAL-A-",
        "PROVISIONAL", "explicit qualification only",
    ),
    ("GEMINI", "gemini-3.8-flash"): ProviderPolicy(
        104, "GEMINI", "gemini-3.8-flash", "PROVIDER_DEFAULT", "PROVISIONAL-A",
        "PROVISIONAL", "explicit qualification only",
    ),
    ("ANTHROPIC", "claude-sonnet-5"): ProviderPolicy(
        105, "ANTHROPIC", "claude-sonnet-5", "ADAPTIVE", "PROVISIONAL-A",
        "PROVISIONAL", "explicit qualification only",
    ),
}

_PROVIDER_ALIASES = {
    "XAI": "XAI",
    "GROK": "XAI",
    "QWEN": "QWEN",
    "GEMINI": "GEMINI",
    "ANTHROPIC": "ANTHROPIC",
    "CLAUDE": "ANTHROPIC",
}

Transport = Callable[[str, dict[str, str], bytes, float], dict[str, Any]]


def _http_transport(
    url: str,
    headers: dict[str, str],
    body: bytes,
    timeout: float,
) -> dict[str, Any]:
    request = Request(url, data=body, headers=headers, method="POST")
    with urlopen(request, timeout=timeout) as response:
        raw = response.read()
    decoded = json.loads(raw.decode("utf-8"))
    if not isinstance(decoded, dict):
        raise SemanticProviderError("provider response envelope must be an object")
    return decoded


def _safe_token(value: Any) -> str | None:
    if value is None:
        return None
    token = "".join(
        character if character.isalnum() or character in "_.-" else "_"
        for character in str(value).strip()
    )[:96].strip("_")
    return token or None


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


def _diagnostic_from_http(exc: HTTPError) -> ProviderDiagnostic:
    error_type = None
    error_code = None
    try:
        decoded = json.loads(exc.read(65536).decode("utf-8", errors="replace"))
        error = decoded.get("error") if isinstance(decoded, dict) else None
        if isinstance(error, Mapping):
            error_type = _safe_token(error.get("type"))
            error_code = _safe_token(error.get("code"))
    except (OSError, UnicodeError, json.JSONDecodeError, AttributeError, TypeError, ValueError):
        pass

    request_id = None
    try:
        if exc.headers is not None:
            request_id = _safe_token(
                exc.headers.get("x-request-id")
                or exc.headers.get("request-id")
                or exc.headers.get("request_id")
            )
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


def _int_or_none(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        result = int(value)
    except (TypeError, ValueError):
        return None
    return result if result >= 0 else None


def _semantic_instructions() -> str:
    criteria = "\n".join(
        f"- {rule_id}: {SEMANTIC_RULE_CRITERIA[rule_id]}"
        for rule_id in SEMANTIC_RULE_IDS
    )
    return (
        "Evaluate only the supplied page evidence for Search & AI Readiness. "
        "Return JSON only and conform exactly to the requested schema. "
        "Never invent evidence_ids or hidden facts. Do not score the website. "
        "Use UNKNOWN when evidence is insufficient and NOT_APPLICABLE only when "
        "the rule genuinely does not apply. The assessments array MUST contain "
        "exactly one item for every rule listed below, with no omissions, "
        "duplicates or unknown rule ids.\n\nSemantic rule contract:\n" + criteria
    )


class IsolatedStructuredSemanticProvider:
    """Common fail-closed contract for explicit-only extension providers."""

    name = "GENERIC_EXTENSION"
    endpoint = ""
    reasoning_profile = "PROVIDER_DEFAULT"
    capabilities = (
        "STRUCTURED_OUTPUT",
        "LOCAL_SCHEMA_VALIDATION",
        "USAGE_TELEMETRY",
        "EXPLICIT_ONLY",
        "PROVISIONAL",
    )

    def __init__(
        self,
        *,
        model: str,
        api_key: str | None,
        endpoint: str | None = None,
        timeout: float = 45.0,
        transport: Transport | None = None,
    ) -> None:
        if not model.strip():
            raise ValueError(f"{self.name} model must be configured")
        if timeout <= 0:
            raise ValueError("timeout must be greater than zero")
        self.model = model.strip()
        self.api_key = api_key
        self.endpoint = (endpoint or self.endpoint).strip()
        self.timeout = timeout
        self.configuration_version = "1"
        self.prompt_id = "rasai-semantic-v1"
        self.prompt_version = "1"
        self._transport = transport or _http_transport
        self.policy = EXTENSION_POLICIES[(self.name, self.model)]
        self._last_attempt: ProviderAttempt | None = None
        self._last_attempts: tuple[ProviderAttempt, ...] = ()
        self._history: list[ProviderAttempt] = []
        self._runtime_state = RuntimeProviderState.ACTIVE
        self._successful_urls: set[str] = set()

    def _headers(self) -> dict[str, str]:
        raise NotImplementedError

    def _request_payload(self, semantic_input: SemanticInput) -> dict[str, Any]:
        raise NotImplementedError

    def _extract_payload(self, raw: Mapping[str, Any]) -> Any:
        raise NotImplementedError

    def _usage(self, raw: Mapping[str, Any]) -> ProviderUsage | None:
        return None

    def _native_error(self, raw: Mapping[str, Any]) -> ProviderDiagnostic | None:
        return None

    def analyze(
        self,
        semantic_input: SemanticInput,
        *,
        max_attempts: int = MAX_PROVIDER_ATTEMPTS_PER_CONTEXT,
    ) -> SemanticProviderResult:
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
                decision = (
                    DECISION_SUCCESS_AFTER_RETRY if result.status is ProviderState.AVAILABLE and ordinal > 1
                    else DECISION_SUCCESS if result.status is ProviderState.AVAILABLE
                    else DECISION_RETRY if policy.eligible and ordinal < bounded
                    else DECISION_STOP
                )
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
                self._runtime_state = RuntimeProviderState.ACTIVE
                if policy.delay_seconds > 0:
                    time.sleep(policy.delay_seconds)
                continue
            self._last_attempts = tuple(collected)
            return result
        self._last_attempts = tuple(collected)
        return last_result or SemanticProviderResult(ProviderState.UNAVAILABLE, reason="AI_PROVIDER_UNAVAILABLE", provider=self.name, model=self.model, reasoning_profile=self.reasoning_profile)

    def _analyze_once(self, semantic_input: SemanticInput) -> SemanticProviderResult:
        self._last_attempt = None
        if self._runtime_state is RuntimeProviderState.QUARANTINED_FOR_AUDIT:
            return SemanticProviderResult(
                ProviderState.UNAVAILABLE,
                reason="AI_PROVIDER_UNAVAILABLE:PROVIDER_QUARANTINED",
                provider=self.name,
                model=self.model,
                reasoning_profile=self.reasoning_profile,
                diagnostic=ProviderDiagnostic(
                    ProviderErrorClass.UNKNOWN_PROVIDER_ERROR,
                    error_code="PROVIDER_QUARANTINED",
                ),
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
        request_payload = self._request_payload(semantic_input)
        body = json.dumps(
            request_payload, ensure_ascii=False, separators=(",", ":")
        ).encode("utf-8")
        summary = (
            f"semantic_contract={EXTENSION_SEMANTIC_CONTRACT_VERSION};"
            f"rules={len(SEMANTIC_RULE_IDS)};"
            f"evidence={len(semantic_input.evidence)};"
            f"snapshot={semantic_input.snapshot_id}"
        )
        payload_hash = hashlib.sha256(body).hexdigest()

        try:
            raw = self._transport(self.endpoint, self._headers(), body, self.timeout)
        except HTTPError as exc:
            return self._failure_result(
                semantic_input, started_at, started_perf, summary, payload_hash,
                _diagnostic_from_http(exc), AttemptStatus.TECHNICAL_ERROR,
            )
        except TimeoutError:
            return self._failure_result(
                semantic_input, started_at, started_perf, summary, payload_hash,
                ProviderDiagnostic(ProviderErrorClass.TIMEOUT_ERROR),
                AttemptStatus.TECHNICAL_ERROR,
            )
        except (URLError, OSError):
            return self._failure_result(
                semantic_input, started_at, started_perf, summary, payload_hash,
                ProviderDiagnostic(ProviderErrorClass.NETWORK_ERROR),
                AttemptStatus.TECHNICAL_ERROR,
            )
        except Exception:
            return self._failure_result(
                semantic_input, started_at, started_perf, summary, payload_hash,
                ProviderDiagnostic(ProviderErrorClass.UNKNOWN_PROVIDER_ERROR),
                AttemptStatus.TECHNICAL_ERROR,
            )

        if not isinstance(raw, Mapping):
            return self._failure_result(
                semantic_input, started_at, started_perf, summary, payload_hash,
                ProviderDiagnostic(ProviderErrorClass.INVALID_RESPONSE),
                AttemptStatus.CONTRACT_ERROR,
            )

        usage = self._usage(raw)
        native_error = self._native_error(raw)
        if native_error is not None:
            return self._failure_result(
                semantic_input, started_at, started_perf, summary, payload_hash,
                native_error, AttemptStatus.TECHNICAL_ERROR, usage=usage,
            )

        try:
            payload = self._extract_payload(raw)
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
            if (
                len(received) != len(SEMANTIC_RULE_IDS)
                or frozenset(received) != frozenset(SEMANTIC_RULE_IDS)
            ):
                raise SemanticSchemaError("INCOMPLETE_SEMANTIC_OUTPUT")
        except (SemanticSchemaError, SemanticEvidenceError) as exc:
            return self._failure_result(
                semantic_input, started_at, started_perf, summary, payload_hash,
                ProviderDiagnostic(
                    ProviderErrorClass.CONTRACT_ERROR,
                    error_type=type(exc).__name__,
                ),
                AttemptStatus.CONTRACT_ERROR,
                usage=usage,
            )
        except SemanticProviderError as exc:
            error_class = (
                ProviderErrorClass.EMPTY_RESPONSE
                if "no textual output" in str(exc).casefold()
                else ProviderErrorClass.INVALID_RESPONSE
            )
            return self._failure_result(
                semantic_input, started_at, started_perf, summary, payload_hash,
                ProviderDiagnostic(error_class, error_type=type(exc).__name__),
                AttemptStatus.CONTRACT_ERROR,
                usage=usage,
            )
        except (json.JSONDecodeError, UnicodeError, TypeError, ValueError, KeyError, IndexError) as exc:
            return self._failure_result(
                semantic_input, started_at, started_perf, summary, payload_hash,
                ProviderDiagnostic(
                    ProviderErrorClass.INVALID_RESPONSE,
                    error_type=type(exc).__name__,
                ),
                AttemptStatus.CONTRACT_ERROR,
                usage=usage,
            )

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
            status=AttemptStatus.SUCCESS,
            usage=usage,
            estimated_cost=None,
            cost_currency=None,
            pricing_version=None,
            request_message_summary=summary,
            request_payload_hash=payload_hash,
            provider_qualification=self.policy.qualification,
            provider_reliability_score=self.policy.reliability_score,
            qualification_version=EXTENSION_QUALIFICATION_VERSION,
            semantic_contract_version=EXTENSION_SEMANTIC_CONTRACT_VERSION,
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
            qualification_version=EXTENSION_QUALIFICATION_VERSION,
            semantic_contract_version=EXTENSION_SEMANTIC_CONTRACT_VERSION,
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


class XAIProvider(IsolatedStructuredSemanticProvider):
    name = "XAI"
    endpoint = "https://api.x.ai/v1/responses"
    reasoning_profile = "HIGH"
    capabilities = IsolatedStructuredSemanticProvider.capabilities + (
        "RESPONSES_API",
        "REASONING",
    )

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key or ''}",
            "Content-Type": "application/json",
        }

    def _request_payload(self, semantic_input: SemanticInput) -> dict[str, Any]:
        return {
            "model": self.model,
            "instructions": _semantic_instructions(),
            "input": [{
                "role": "user",
                "content": [{
                    "type": "input_text",
                    "text": "JSON page evidence:\n"
                    + json.dumps(semantic_input.provider_payload(), ensure_ascii=False),
                }],
            }],
            "reasoning": {"effort": "high"},
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "rasai_semantic_assessment",
                    "schema": hardened_semantic_output_schema(semantic_input.allowed_evidence_ids),
                    "strict": True,
                }
            },
        }

    def _extract_payload(self, raw: Mapping[str, Any]) -> Any:
        if isinstance(raw.get("output_text"), str):
            return json.loads(raw["output_text"])
        for item in raw.get("output", []):
            if not isinstance(item, Mapping):
                continue
            for content in item.get("content", []):
                if (
                    isinstance(content, Mapping)
                    and content.get("type") == "output_text"
                    and isinstance(content.get("text"), str)
                ):
                    return json.loads(content["text"])
        raise SemanticProviderError("XAI response contained no textual output")

    def _usage(self, raw: Mapping[str, Any]) -> ProviderUsage | None:
        usage = raw.get("usage")
        if not isinstance(usage, Mapping):
            return None
        input_details = usage.get("input_tokens_details")
        output_details = usage.get("output_tokens_details")
        return ProviderUsage(
            input_tokens=_int_or_none(usage.get("input_tokens")),
            cached_input_tokens=(
                _int_or_none(input_details.get("cached_tokens"))
                if isinstance(input_details, Mapping) else None
            ),
            output_tokens=_int_or_none(usage.get("output_tokens")),
            reasoning_tokens=(
                _int_or_none(output_details.get("reasoning_tokens"))
                if isinstance(output_details, Mapping) else None
            ),
            total_tokens=_int_or_none(usage.get("total_tokens")),
        )


class QwenProvider(IsolatedStructuredSemanticProvider):
    name = "QWEN"
    endpoint = "https://dashscope-us.aliyuncs.com/compatible-mode/v1/chat/completions"
    capabilities = IsolatedStructuredSemanticProvider.capabilities + (
        "OPENAI_COMPATIBLE_CHAT_COMPLETIONS",
    )

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key or ''}",
            "Content-Type": "application/json",
        }

    def _request_payload(self, semantic_input: SemanticInput) -> dict[str, Any]:
        return {
            "model": self.model,
            "messages": [
                {"role": "system", "content": _semantic_instructions()},
                {
                    "role": "user",
                    "content": "JSON page evidence:\n"
                    + json.dumps(semantic_input.provider_payload(), ensure_ascii=False),
                },
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "rasai_semantic_assessment",
                    "schema": hardened_semantic_output_schema(semantic_input.allowed_evidence_ids),
                    "strict": True,
                },
            },
        }

    def _extract_payload(self, raw: Mapping[str, Any]) -> Any:
        choices = raw.get("choices")
        if not isinstance(choices, list) or not choices:
            raise SemanticProviderError("Qwen response contained no textual output")
        message = choices[0].get("message") if isinstance(choices[0], Mapping) else None
        content = message.get("content") if isinstance(message, Mapping) else None
        if not isinstance(content, str):
            raise SemanticProviderError("Qwen response contained no textual output")
        return json.loads(content)

    def _usage(self, raw: Mapping[str, Any]) -> ProviderUsage | None:
        usage = raw.get("usage")
        if not isinstance(usage, Mapping):
            return None
        prompt_details = usage.get("prompt_tokens_details")
        cached = (
            _int_or_none(prompt_details.get("cached_tokens"))
            if isinstance(prompt_details, Mapping) else None
        )
        return ProviderUsage(
            input_tokens=_int_or_none(
                usage.get("prompt_tokens")
                if usage.get("prompt_tokens") is not None
                else usage.get("input_tokens")
            ),
            cached_input_tokens=cached,
            output_tokens=_int_or_none(
                usage.get("completion_tokens")
                if usage.get("completion_tokens") is not None
                else usage.get("output_tokens")
            ),
            reasoning_tokens=None,
            total_tokens=_int_or_none(usage.get("total_tokens")),
        )


class GeminiProvider(IsolatedStructuredSemanticProvider):
    name = "GEMINI"
    endpoint = "https://generativelanguage.googleapis.com/v1beta/interactions"
    capabilities = IsolatedStructuredSemanticProvider.capabilities + (
        "GEMINI_INTERACTIONS_API",
    )

    def _headers(self) -> dict[str, str]:
        return {
            "x-goog-api-key": self.api_key or "",
            "Content-Type": "application/json",
        }

    def _request_payload(self, semantic_input: SemanticInput) -> dict[str, Any]:
        return {
            "model": self.model,
            "input": _semantic_instructions()
            + "\n\nJSON page evidence:\n"
            + json.dumps(semantic_input.provider_payload(), ensure_ascii=False),
            "response_format": {
                "type": "text",
                "mime_type": "application/json",
                "schema": hardened_semantic_output_schema(semantic_input.allowed_evidence_ids),
            },
        }

    def _extract_payload(self, raw: Mapping[str, Any]) -> Any:
        if isinstance(raw.get("output_text"), str):
            return json.loads(raw["output_text"])
        steps = raw.get("steps")
        if isinstance(steps, list):
            for step in reversed(steps):
                if not isinstance(step, Mapping) or step.get("type") != "model_output":
                    continue
                for content in step.get("content", []):
                    if (
                        isinstance(content, Mapping)
                        and content.get("type") == "text"
                        and isinstance(content.get("text"), str)
                    ):
                        return json.loads(content["text"])
        raise SemanticProviderError("Gemini response contained no textual output")

    def _usage(self, raw: Mapping[str, Any]) -> ProviderUsage | None:
        usage = raw.get("usage")
        if not isinstance(usage, Mapping):
            usage = raw.get("usage_metadata")
        if not isinstance(usage, Mapping):
            return None

        input_tokens = _int_or_none(
            usage.get("prompt_tokens")
            if usage.get("prompt_tokens") is not None
            else usage.get("prompt_token_count")
        )
        output_tokens = _int_or_none(
            usage.get("completion_tokens")
            if usage.get("completion_tokens") is not None
            else usage.get("candidates_token_count")
        )
        total_tokens = _int_or_none(
            usage.get("total_tokens")
            if usage.get("total_tokens") is not None
            else usage.get("total_token_count")
        )
        cached_tokens = _int_or_none(
            usage.get("cached_content_token_count")
            if usage.get("cached_content_token_count") is not None
            else usage.get("cached_tokens")
        )
        thought_tokens = _int_or_none(
            usage.get("thoughts_token_count")
            if usage.get("thoughts_token_count") is not None
            else usage.get("reasoning_tokens")
        )
        return ProviderUsage(
            input_tokens=input_tokens,
            cached_input_tokens=cached_tokens,
            output_tokens=output_tokens,
            reasoning_tokens=thought_tokens,
            total_tokens=total_tokens,
        )


class AnthropicProvider(IsolatedStructuredSemanticProvider):
    name = "ANTHROPIC"
    endpoint = "https://api.anthropic.com/v1/messages"
    reasoning_profile = "ADAPTIVE"
    capabilities = IsolatedStructuredSemanticProvider.capabilities + (
        "ANTHROPIC_MESSAGES_API",
        "ADAPTIVE_THINKING_MODEL",
    )

    def _headers(self) -> dict[str, str]:
        return {
            "x-api-key": self.api_key or "",
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }

    def _request_payload(self, semantic_input: SemanticInput) -> dict[str, Any]:
        return {
            "model": self.model,
            "max_tokens": 16384,
            "system": _semantic_instructions(),
            "messages": [{
                "role": "user",
                "content": "JSON page evidence:\n"
                + json.dumps(semantic_input.provider_payload(), ensure_ascii=False),
            }],
            "output_config": {
                "format": {
                    "type": "json_schema",
                    "schema": hardened_semantic_output_schema(semantic_input.allowed_evidence_ids),
                }
            },
        }

    def _extract_payload(self, raw: Mapping[str, Any]) -> Any:
        content = raw.get("content")
        if isinstance(content, list):
            for item in content:
                if (
                    isinstance(item, Mapping)
                    and item.get("type") == "text"
                    and isinstance(item.get("text"), str)
                ):
                    return json.loads(item["text"])
        raise SemanticProviderError("Anthropic response contained no textual output")

    def _native_error(self, raw: Mapping[str, Any]) -> ProviderDiagnostic | None:
        if str(raw.get("stop_reason") or "").casefold() == "refusal":
            return ProviderDiagnostic(
                ProviderErrorClass.INVALID_RESPONSE,
                error_code="REFUSAL",
            )
        return None

    def _usage(self, raw: Mapping[str, Any]) -> ProviderUsage | None:
        usage = raw.get("usage")
        if not isinstance(usage, Mapping):
            return None
        base_input = _int_or_none(usage.get("input_tokens")) or 0
        cache_creation = _int_or_none(usage.get("cache_creation_input_tokens")) or 0
        cache_read = _int_or_none(usage.get("cache_read_input_tokens")) or 0
        output = _int_or_none(usage.get("output_tokens"))
        total_input = base_input + cache_creation + cache_read
        return ProviderUsage(
            input_tokens=total_input,
            cached_input_tokens=cache_read,
            output_tokens=output,
            reasoning_tokens=None,
            total_tokens=(total_input + output) if output is not None else None,
        )


def _resolve_extension_config(
    provider_name: str,
    *,
    model_override: str | None = None,
    env: Mapping[str, str] | None = None,
) -> tuple[str, str | None, str | None]:
    environment = env if env is not None else os.environ
    model = (
        model_override
        or environment.get(EXTENDED_MODEL_ENV[provider_name])
        or EXTENDED_DEFAULT_MODELS[provider_name]
    ).strip()
    if model not in EXTENDED_SUPPORTED_MODELS[provider_name]:
        raise ValueError(
            f"unsupported RASAi model for {provider_name}: {model}; allowed: "
            + ", ".join(EXTENDED_SUPPORTED_MODELS[provider_name])
        )
    key = environment.get(EXTENDED_KEY_ENV[provider_name])
    endpoint = environment.get(EXTENDED_ENDPOINT_ENV[provider_name])
    return model, key, endpoint


def _extension_provider_instance(
    provider_name: str,
    *,
    model: str,
    key: str | None,
    endpoint: str | None,
) -> IsolatedStructuredSemanticProvider:
    provider_type: type[IsolatedStructuredSemanticProvider]
    if provider_name == "XAI":
        provider_type = XAIProvider
    elif provider_name == "QWEN":
        provider_type = QwenProvider
    elif provider_name == "GEMINI":
        provider_type = GeminiProvider
    elif provider_name == "ANTHROPIC":
        provider_type = AnthropicProvider
    else:
        raise ValueError(provider_name)
    return provider_type(model=model, api_key=key, endpoint=endpoint)


def build_semantic_provider(
    selection: str,
    *,
    model_override: str | None = None,
    env: Mapping[str, str] | None = None,
) -> Any:
    """Build an extension provider or delegate legacy selections unchanged.

    AUTO intentionally delegates to M18 and therefore continues to consider
    only OPENAI, DEEPSEEK and MIMO. Extension providers remain explicit-only
    until their provisional qualification is completed by human smoke.
    """

    selected = selection.strip().upper()
    provider_name = _PROVIDER_ALIASES.get(selected)
    if provider_name is None:
        return _legacy_build_semantic_provider(
            selection,
            model_override=model_override,
            env=env,
        )

    model, key, endpoint = _resolve_extension_config(
        provider_name,
        model_override=model_override,
        env=env,
    )
    return _extension_provider_instance(
        provider_name,
        model=model,
        key=key,
        endpoint=endpoint,
    )
