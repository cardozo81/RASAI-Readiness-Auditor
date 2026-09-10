"""Execution-wide dynamic AI routing for AUTO mode.

AUTO uses every configured provider that is eligible in the registry, rotates the
starting provider between AI needs, and applies a bounded execution-wide circuit
breaker. Provider-specific adapters remain responsible for wire contracts; this
module coordinates eligibility only.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field, replace
import json
from types import MethodType
from typing import Any, Mapping

from rasai.ai_exchange_log import AiExchangeRecorder, instrument_provider_transport
from rasai.content_context import ContentAnalysisContext
from rasai.m18_ai import (
    AttemptStatus,
    ProviderAttempt,
    ProviderErrorClass,
    ProviderState,
    RuntimeProviderState,
    SemanticProviderResult,
)
from rasai.ai_resilience import DECISION_FALLBACK, DECISION_FALLBACK_SUCCESS, DECISION_SUCCESS

ROLLING_WINDOW_SIZE = 5
FAILURES_TO_OPEN_CIRCUIT = 3

_TERMINAL_ERROR_CLASSES = frozenset({
    ProviderErrorClass.AUTH_ERROR.value,
    ProviderErrorClass.CREDIT_ERROR.value,
    ProviderErrorClass.QUOTA_ERROR.value,
    ProviderErrorClass.MODEL_ERROR.value,
    ProviderErrorClass.PERMISSION_ERROR.value,
})
_TERMINAL_HTTP_STATUS = frozenset({401, 403, 404, 410})
_CONTEXT_FIELD_VALUES: dict[str, tuple[str, ...]] = {
    "risk_profile": ("standard", "ymyl"),
    "ymyl_category": ("none", "health-safety", "financial-security", "civic-societal", "other-significant-welfare"),
    "page_purpose": ("informational", "transactional", "product-service", "review-comparison", "news-editorial", "support-documentation", "forum-ugc", "other"),
    "intended_audience": ("general", "professional", "mixed"),
    "experience_requirement": ("required", "beneficial", "not-expected"),
    "freshness_sensitivity": ("low", "medium", "high"),
    "content_origin": ("first-party", "third-party", "user-generated", "mixed"),
}


@dataclass(slots=True)
class ProviderExecutionHealth:
    name: str
    eligible: bool = True
    attempts: int = 0
    successes: int = 0
    temporary_failures: int = 0
    terminal_failures: int = 0
    exclusion_reason: str | None = None
    last_error_class: str | None = None
    last_http_status: int | None = None
    outcomes: deque[int] = field(default_factory=lambda: deque(maxlen=ROLLING_WINDOW_SIZE))

    def as_dict(self) -> dict[str, Any]:
        return {
            "eligible": self.eligible,
            "attempts": self.attempts,
            "successes": self.successes,
            "temporary_failures": self.temporary_failures,
            "terminal_failures": self.terminal_failures,
            "exclusion_reason": self.exclusion_reason,
            "last_error_class": self.last_error_class,
            "last_http_status": self.last_http_status,
            "rolling_failures": sum(self.outcomes),
            "rolling_observations": len(self.outcomes),
        }


class AiExecutionCoordinator:
    """Round-robin cursor plus execution-wide provider circuit breakers."""

    def __init__(self, provider_names: tuple[str, ...]) -> None:
        self.provider_names = tuple(dict.fromkeys(provider_names))
        self._health = {name: ProviderExecutionHealth(name=name) for name in self.provider_names}
        self._cursor = 0
        self.last_successful_provider: str | None = None
        self._successful_urls: dict[str, set[str]] = {name: set() for name in self.provider_names}

    def ordered_names(self) -> tuple[str, ...]:
        if not self.provider_names:
            return ()
        order = self.provider_names[self._cursor:] + self.provider_names[:self._cursor]
        return tuple(name for name in order if self._health[name].eligible)

    def is_eligible(self, name: str) -> bool:
        item = self._health.get(name)
        return bool(item and item.eligible)

    def record_attempt(self, attempt: ProviderAttempt, *, page_url: str | None = None) -> None:
        name = attempt.provider
        health = self._health.get(name)
        if health is None:
            return
        health.attempts += 1
        self._advance_after(name)

        if attempt.status is AttemptStatus.SUCCESS:
            health.successes += 1
            health.outcomes.append(0)
            health.last_error_class = None
            health.last_http_status = None
            self.last_successful_provider = name
            if page_url:
                self._successful_urls.setdefault(name, set()).add(page_url)
            return

        health.outcomes.append(1)
        diagnostic = attempt.diagnostic
        error_class = diagnostic.error_class.value if diagnostic is not None and diagnostic.error_class is not None else None
        http_status = diagnostic.http_status if diagnostic is not None else None
        health.last_error_class = error_class
        health.last_http_status = http_status

        terminal = error_class in _TERMINAL_ERROR_CLASSES or http_status in _TERMINAL_HTTP_STATUS
        if terminal:
            health.terminal_failures += 1
            health.eligible = False
            health.exclusion_reason = f"TERMINAL:{error_class or 'HTTP_ERROR'}" + (f":HTTP_{http_status}" if http_status is not None else "")
            return

        health.temporary_failures += 1
        if len(health.outcomes) >= FAILURES_TO_OPEN_CIRCUIT and sum(health.outcomes) >= FAILURES_TO_OPEN_CIRCUIT:
            health.eligible = False
            health.exclusion_reason = f"CIRCUIT_BREAKER:{FAILURES_TO_OPEN_CIRCUIT}_FAILURES_IN_LAST_{ROLLING_WINDOW_SIZE}"

    def exclude_configuration(self, name: str, reason: str) -> None:
        item = self._health.get(name)
        if item is None:
            return
        item.eligible = False
        item.exclusion_reason = reason

    def _advance_after(self, name: str) -> None:
        if not self.provider_names:
            return
        try:
            index = self.provider_names.index(name)
        except ValueError:
            return
        self._cursor = (index + 1) % len(self.provider_names)

    def provider_states(self) -> dict[str, str]:
        ordered = self.ordered_names()
        active = ordered[0] if ordered else None
        states: dict[str, str] = {}
        for name in self.provider_names:
            health = self._health[name]
            if not health.eligible:
                states[name] = RuntimeProviderState.QUARANTINED_FOR_AUDIT.value
            elif name == active:
                states[name] = RuntimeProviderState.ACTIVE.value
            else:
                states[name] = RuntimeProviderState.STANDBY.value
        return states

    def health_snapshot(self) -> dict[str, dict[str, Any]]:
        return {name: self._health[name].as_dict() for name in self.provider_names}

    def successful_urls(self) -> dict[str, int]:
        return {name: len(values) for name, values in self._successful_urls.items()}


@dataclass(slots=True)
class DynamicProviderRoutingSession:
    _providers: tuple[Any, ...]
    excluded_configurations: tuple[str, ...] = ()
    strategy: str = "AUTO"
    recorder: AiExchangeRecorder | None = None
    coordinator: AiExecutionCoordinator = field(init=False)
    _last_attempts: tuple[ProviderAttempt, ...] = field(init=False, default=())
    _history: list[ProviderAttempt] = field(init=False, default_factory=list)

    def __post_init__(self) -> None:
        self._providers = tuple(sorted(self._providers, key=lambda item: int(getattr(item.policy, "rank", 9999))))
        self.coordinator = AiExecutionCoordinator(tuple(str(item.name) for item in self._providers))
        for provider in self._providers:
            provider._rasai_execution_coordinator = self.coordinator

    @property
    def providers(self) -> tuple[Any, ...]:
        return self._providers

    def ordered_candidates_for_need(self) -> tuple[Any, ...]:
        by_name = {str(item.name): item for item in self._providers}
        return tuple(by_name[name] for name in self.coordinator.ordered_names() if name in by_name)

    def analyze(self, semantic_input: Any) -> SemanticProviderResult:
        self._last_attempts = ()
        candidates = self.ordered_candidates_for_need()
        if not candidates:
            return SemanticProviderResult(ProviderState.UNAVAILABLE, reason="AI_PROVIDER_CHAIN_EXHAUSTED")

        attempts: list[ProviderAttempt] = []
        last: SemanticProviderResult | None = None
        fallback_from: str | None = None
        fallback_reason: str | None = None

        for index, provider in enumerate(candidates):
            result = provider.analyze(semantic_input, max_attempts=1)
            local = list(provider.consume_attempts())
            if fallback_from is not None:
                local = [replace(item, fallback_from_provider=fallback_from, fallback_reason=fallback_reason) for item in local]
            local = [replace(item, attempt_index=len(attempts) + offset) for offset, item in enumerate(local, 1)]
            attempts.extend(local)
            last = result

            attempt = local[-1] if local else None
            if attempt is not None:
                self.coordinator.record_attempt(attempt, page_url=str(getattr(semantic_input, "page_url", "") or ""))

            if result.state is ProviderState.AVAILABLE:
                if fallback_from is not None and attempts:
                    attempts[-1] = replace(attempts[-1], decision=DECISION_FALLBACK_SUCCESS, fallback_from_provider=fallback_from, fallback_reason=fallback_reason)
                elif attempts:
                    attempts[-1] = replace(attempts[-1], decision=DECISION_SUCCESS)
                self._history.extend(attempts)
                self._last_attempts = tuple(attempts)
                return result

            if result.state is ProviderState.NOT_CONFIGURED:
                if attempt is None:
                    self.coordinator.exclude_configuration(str(provider.name), "NOT_CONFIGURED_DURING_EXECUTION")
                continue

            if self.coordinator.is_eligible(str(provider.name)):
                _reactivate(provider)
            if index < len(candidates) - 1:
                if attempts:
                    attempts[-1] = replace(attempts[-1], decision=DECISION_FALLBACK)
                fallback_from = str(provider.name)
                fallback_reason = result.reason or "AI_PROVIDER_UNAVAILABLE"

        self._history.extend(attempts)
        self._last_attempts = tuple(attempts)
        if not self.coordinator.ordered_names():
            return SemanticProviderResult(ProviderState.UNAVAILABLE, reason="AI_PROVIDER_CHAIN_EXHAUSTED")
        return last or SemanticProviderResult(ProviderState.UNAVAILABLE, reason="AI_PROVIDER_UNAVAILABLE")

    def consume_attempts(self) -> tuple[ProviderAttempt, ...]:
        items = self._last_attempts
        self._last_attempts = ()
        return items

    def attempt_history(self) -> tuple[ProviderAttempt, ...]:
        return tuple(self._history)

    def session_snapshot(self) -> dict[str, Any]:
        effective = self.coordinator.last_successful_provider
        provider_by_name = {str(item.name): item for item in self._providers}
        effective_provider = provider_by_name.get(effective) if effective else None
        first = self._providers[0] if self._providers else None
        return {
            "strategy": "AUTO",
            "enabled": bool(self._providers),
            "initial_provider": getattr(first, "name", None),
            "initial_model": getattr(first, "model", None),
            "initial_reasoning_profile": getattr(first, "reasoning_profile", None),
            "effective_provider": effective,
            "effective_model": getattr(effective_provider, "model", None),
            "effective_reasoning_profile": getattr(effective_provider, "reasoning_profile", None),
            "configured_chain": [{
                "provider": str(item.name),
                "model": getattr(item, "model", None),
                "reasoning_profile": getattr(item, "reasoning_profile", None),
                "rank": int(getattr(item.policy, "rank", 9999)),
                "qualification": getattr(item.policy, "qualification", None),
            } for item in self._providers],
            "provider_states": self.coordinator.provider_states(),
            "provider_health": self.coordinator.health_snapshot(),
            "successful_urls": self.coordinator.successful_urls(),
            "excluded_configurations": list(self.excluded_configurations),
            "routing_policy": {
                "strategy": "ROUND_ROBIN_WITH_CIRCUIT_BREAKER",
                "same_need_provider_attempts": 1,
                "failure_window": ROLLING_WINDOW_SIZE,
                "failure_threshold": FAILURES_TO_OPEN_CIRCUIT,
            },
        }


@dataclass(slots=True)
class DynamicContentRemediationRoutingSession:
    semantic_session: DynamicProviderRoutingSession
    providers: tuple[Any, ...]
    strategy: str = "AUTO"
    excluded_configurations: tuple[str, ...] = ()
    _last_attempts: tuple[ProviderAttempt, ...] = field(init=False, default=())

    @property
    def coordinator(self) -> AiExecutionCoordinator:
        return self.semantic_session.coordinator

    def analyze(self, request: Any) -> Any:
        from rasai.m20_ai import ContentRemediationResult
        self._last_attempts = ()
        by_name = {str(item.name): item for item in self.providers}
        candidates = tuple(by_name[name] for name in self.coordinator.ordered_names() if name in by_name)
        if not candidates:
            return ContentRemediationResult(ProviderState.UNAVAILABLE, reason="AI_PROVIDER_CHAIN_EXHAUSTED")

        attempts: list[ProviderAttempt] = []
        last = None
        fallback_from = None
        fallback_reason = None
        for index, provider in enumerate(candidates):
            result = provider.analyze(request, max_attempts=1)
            local = list(provider.consume_attempts())
            if fallback_from is not None:
                local = [replace(item, fallback_from_provider=fallback_from, fallback_reason=fallback_reason) for item in local]
            local = [replace(item, attempt_index=len(attempts) + offset) for offset, item in enumerate(local, 1)]
            attempts.extend(local)
            last = result
            attempt = local[-1] if local else None
            if attempt is not None:
                self.coordinator.record_attempt(attempt, page_url=str(getattr(request, "page_url", "") or ""))

            if result.state is ProviderState.AVAILABLE:
                if fallback_from is not None and attempts:
                    attempts[-1] = replace(attempts[-1], decision=DECISION_FALLBACK_SUCCESS, fallback_from_provider=fallback_from, fallback_reason=fallback_reason)
                self._last_attempts = tuple(attempts)
                return result

            if self.coordinator.is_eligible(str(provider.name)):
                _reactivate(provider)
            if index < len(candidates) - 1:
                if attempts:
                    attempts[-1] = replace(attempts[-1], decision=DECISION_FALLBACK)
                fallback_from = str(provider.name)
                fallback_reason = result.reason or "AI_PROVIDER_UNAVAILABLE"

        self._last_attempts = tuple(attempts)
        if not self.coordinator.ordered_names():
            return ContentRemediationResult(ProviderState.UNAVAILABLE, reason="AI_PROVIDER_CHAIN_EXHAUSTED")
        return last or ContentRemediationResult(ProviderState.UNAVAILABLE, reason="AI_PROVIDER_UNAVAILABLE")

    def consume_attempts(self) -> tuple[ProviderAttempt, ...]:
        items = self._last_attempts
        self._last_attempts = ()
        return items


def build_dynamic_content_remediation_router(session: DynamicProviderRoutingSession) -> DynamicContentRemediationRoutingSession:
    from rasai.m18_ai import ResponsesSemanticProvider
    from rasai.m20_ai import ContentRemediationProvider
    from rasai.provider_extensions import IsolatedStructuredSemanticProvider
    from rasai.provider_extensions_m20 import ExtensionContentRemediationProvider

    wrapped: list[Any] = []
    for base in session.providers:
        if isinstance(base, ResponsesSemanticProvider):
            wrapped.append(ContentRemediationProvider(base))
        elif isinstance(base, IsolatedStructuredSemanticProvider):
            wrapped.append(ExtensionContentRemediationProvider(base))
    return DynamicContentRemediationRoutingSession(
        semantic_session=session,
        providers=tuple(wrapped),
        strategy="AUTO",
        excluded_configurations=session.excluded_configurations,
    )


def prepare_provider_for_execution(provider: Any, *, recorder: AiExchangeRecorder, context: ContentAnalysisContext) -> None:
    """Install transport logging and optional transient AUTO-context output."""
    instrument_provider_transport(provider, recorder)
    if context.auto_fields:
        _patch_semantic_context_output(provider, context)


def _patch_semantic_context_output(provider: Any, context: ContentAnalysisContext) -> None:
    if getattr(provider, "_rasai_context_output_patched", False):
        return
    original = getattr(provider, "_request_payload", None)
    if not callable(original):
        return
    provider._rasai_context_output_patched = True

    def patched(_self: Any, semantic_input: Any) -> dict[str, Any]:
        payload = original(semantic_input)
        if not isinstance(payload, dict):
            return payload
        output = json.loads(json.dumps(payload, ensure_ascii=False))
        _extend_semantic_schemas(output)
        _append_provider_instruction(output, _context_interpretation_directive(context))
        return output

    provider._request_payload = MethodType(patched, provider)


def _context_field_schema(values: tuple[str, ...]) -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "status": {"type": "string", "enum": ["INTERPRETED", "NOT_DETERMINABLE", "NOT_REQUESTED"]},
            "value": {"type": ["string", "null"], "enum": [None, *values]},
            "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
            "rationale": {"type": "string"},
            "evidence_ids": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["status", "value", "confidence", "rationale", "evidence_ids"],
    }


def _context_output_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {field: _context_field_schema(values) for field, values in _CONTEXT_FIELD_VALUES.items()},
        "required": list(_CONTEXT_FIELD_VALUES),
    }


def _extend_semantic_schemas(value: Any) -> None:
    if isinstance(value, dict):
        properties = value.get("properties")
        if isinstance(properties, dict) and {"assessments", "entities", "primary_intent", "secondary_intents"}.issubset(properties):
            properties.setdefault("content_context_interpretation", _context_output_schema())
            required = value.get("required")
            if isinstance(required, list) and "content_context_interpretation" not in required:
                required.append("content_context_interpretation")
        for item in value.values():
            _extend_semantic_schemas(item)
    elif isinstance(value, list):
        for item in value:
            _extend_semantic_schemas(item)


def _append_provider_instruction(payload: dict[str, Any], directive: str) -> None:
    if isinstance(payload.get("instructions"), str):
        payload["instructions"] += "\n\n" + directive
        return
    if isinstance(payload.get("system"), str):
        payload["system"] += "\n\n" + directive
        return
    messages = payload.get("messages")
    if isinstance(messages, list):
        for message in messages:
            if isinstance(message, dict) and str(message.get("role") or "").casefold() == "system" and isinstance(message.get("content"), str):
                message["content"] += "\n\n" + directive
                return
    if isinstance(payload.get("input"), str):
        payload["input"] = directive + "\n\n" + payload["input"]


def _context_interpretation_directive(context: ContentAnalysisContext) -> str:
    allowed = "; ".join(f"{field}={','.join(values)}" for field, values in _CONTEXT_FIELD_VALUES.items())
    return (
        "Additional presentation-only task: return the top-level property 'content_context_interpretation'. "
        "It MUST contain all seven fields. Interpret ONLY fields listed in content_analysis_context.auto_fields. "
        "For an AUTO field, use INTERPRETED only when supplied visible page evidence supports one allowed value; "
        "otherwise use NOT_DETERMINABLE with value=null. For a field explicitly configured by the user, use "
        "NOT_REQUESTED with value=null and do not reinterpret or override it. Cite only supplied evidence_ids. "
        "This interpretation is contextual, transient, must not affect SCORE-GEO-004/SARI-001, and must never "
        "invent credentials, reputation, legal status, professional review, first-hand experience, or hidden facts. "
        f"Current configured context: {json.dumps(context.provider_payload(), ensure_ascii=False, separators=(',', ':'))}. "
        f"Allowed interpreted values: {allowed}. Each field object must contain status,value,confidence,rationale,evidence_ids. "
        "Auxiliary schema: " + json.dumps(_context_output_schema(), ensure_ascii=False, separators=(",", ":"))
    )


def _reactivate(provider: Any) -> None:
    try:
        provider._runtime_state = RuntimeProviderState.ACTIVE
    except Exception:
        pass


_M24_HOOKS_INSTALLED = False
_SOURCE_QUALITY_HOOKS_INSTALLED = False


def install_dynamic_specialist_hooks() -> None:
    """Make specialist AI calls participate in the same AUTO cursor/breaker."""
    _install_m24_hooks()
    _install_source_quality_hooks()


def _install_m24_hooks() -> None:
    global _M24_HOOKS_INSTALLED
    if _M24_HOOKS_INSTALLED:
        return
    try:
        from rasai import m24_ai
    except Exception:
        return
    original_candidates = m24_ai._candidates
    original_call = m24_ai._call

    def candidates(provider: Any):
        if isinstance(provider, DynamicProviderRoutingSession):
            return tuple(item for item in provider.ordered_candidates_for_need() if m24_ai._supported_candidate(item))
        return original_candidates(provider)

    def call(candidate: Any, **kwargs):
        result, attempt = original_call(candidate, **kwargs)
        coordinator = getattr(candidate, "_rasai_execution_coordinator", None)
        if isinstance(coordinator, AiExecutionCoordinator):
            coordinator.record_attempt(attempt, page_url=str(attempt.url or ""))
            if coordinator.is_eligible(str(candidate.name)):
                _reactivate(candidate)
        return result, attempt

    m24_ai._candidates = candidates
    m24_ai._call = call
    _M24_HOOKS_INSTALLED = True


def _install_source_quality_hooks() -> None:
    global _SOURCE_QUALITY_HOOKS_INSTALLED
    if _SOURCE_QUALITY_HOOKS_INSTALLED:
        return
    try:
        from rasai import source_quality_ai
        from rasai.m18_ai import ResponsesSemanticProvider
    except Exception:
        return
    original_candidates = source_quality_ai._candidates
    original_call = source_quality_ai._call

    def candidates(provider: Any):
        if isinstance(provider, DynamicProviderRoutingSession):
            return tuple(item for item in provider.ordered_candidates_for_need() if isinstance(item, ResponsesSemanticProvider) and bool(getattr(item, "api_key", None)))
        return original_candidates(provider)

    def call(candidate: Any, assessment: Any, page_row: Mapping[str, Any], *, attempt_index: int):
        result, attempt = original_call(candidate, assessment, page_row, attempt_index=attempt_index)
        coordinator = getattr(candidate, "_rasai_execution_coordinator", None)
        if isinstance(coordinator, AiExecutionCoordinator):
            coordinator.record_attempt(attempt, page_url=str(attempt.url or ""))
            if coordinator.is_eligible(str(candidate.name)):
                _reactivate(candidate)
        return result, attempt

    source_quality_ai._candidates = candidates
    source_quality_ai._call = call
    _SOURCE_QUALITY_HOOKS_INSTALLED = True
