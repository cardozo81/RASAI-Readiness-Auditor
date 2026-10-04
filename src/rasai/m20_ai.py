"""M20 optional AI-assisted content remediation.

Separate from M18 semantic scoring: suggestions never mutate findings, rule
executions, scores or recommendations.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
import hashlib
import json
import re
import time
from typing import Any, Mapping
from urllib.error import HTTPError, URLError

from rasai.ai_resilience import (
    DECISION_FALLBACK,
    DECISION_FALLBACK_SUCCESS,
    DECISION_STOP,
    DECISION_SUCCESS,
    MAX_PROVIDER_ATTEMPTS_PER_CONTEXT,
)
from rasai.content_context import configured_content_analysis_context
from rasai.m18_ai import (
    AttemptStatus,
    ProviderAttempt,
    ProviderDiagnostic,
    ProviderErrorClass,
    ProviderState,
    ResponsesSemanticProvider,
    RuntimeProviderState,
    _diagnostic_from_http,
    _response_error,
    _usage_from_native,
    estimate_cost,
    resolve_provider_cost,
    provider_session_snapshot,
)
from rasai.semantic import _extract_json_payload

CONTENT_REMEDIATION_CONTRACT_VERSION = "M20-CONTENT-REMEDIATION-v3"
_NUMERIC_TOKEN = re.compile(r"(?<!\w)[+-]?(?:\d[\d.,:/-]*\d|\d)(?!\w)")


@dataclass(frozen=True, slots=True)
class ContentFindingInput:
    finding_id: str
    rule_id: str
    title: str
    severity: str
    expected_condition: str
    observed_value: Any
    evidence_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ContentEvidenceInput:
    evidence_id: str
    evidence_type: str
    source: str
    observed_value: Any


@dataclass(frozen=True, slots=True)
class ContentRemediationRequest:
    snapshot_id: str
    page_id: str
    page_url: str
    device: str
    title: str | None
    main_content: str
    findings: tuple[ContentFindingInput, ...]
    evidence: tuple[ContentEvidenceInput, ...]

    @property
    def allowed_finding_ids(self) -> frozenset[str]:
        return frozenset(item.finding_id for item in self.findings)

    @property
    def evidence_by_finding(self) -> dict[str, frozenset[str]]:
        return {item.finding_id: frozenset(item.evidence_ids) for item in self.findings}

    @property
    def source_corpus(self) -> str:
        parts = [self.title or "", self.main_content]
        parts.extend(json.dumps(item.observed_value, ensure_ascii=False, sort_keys=True) for item in self.evidence)
        return "\n".join(parts)

    def provider_payload(self) -> dict[str, Any]:
        context = configured_content_analysis_context()
        return {
            "snapshot_id": self.snapshot_id,
            "page_id": self.page_id,
            "page_url": self.page_url,
            "device": self.device,
            "title": self.title,
            "main_content": self.main_content,
            "content_analysis_context": context.provider_payload(),
            "findings": [
                {
                    "finding_id": item.finding_id,
                    "rule_id": item.rule_id,
                    "title": item.title,
                    "severity": item.severity,
                    "expected_condition": item.expected_condition,
                    "observed_value": item.observed_value,
                    "evidence_ids": list(item.evidence_ids),
                }
                for item in self.findings
            ],
            "evidence": [
                {
                    "evidence_id": item.evidence_id,
                    "evidence_type": item.evidence_type,
                    "source": item.source,
                    "observed_value": item.observed_value,
                }
                for item in self.evidence
            ],
        }


@dataclass(frozen=True, slots=True)
class ContentSuggestion:
    finding_id: str
    objective: str
    target_location: str
    proposed_text: str
    evidence_ids: tuple[str, ...]
    confidence: float
    review_note: str


@dataclass(frozen=True, slots=True)
class ContentRemediationResult:
    state: ProviderState
    suggestions: tuple[ContentSuggestion, ...] = ()
    reason: str | None = None
    provider: str | None = None
    model: str | None = None
    reasoning_profile: str | None = None


class ContentRemediationContractError(ValueError):
    """Safe, persisted M20 contract failure with no provider response leakage."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def content_remediation_schema(request: ContentRemediationRequest | None = None) -> dict[str, Any]:
    finding_id_schema: dict[str, Any] = {"type": "string", "minLength": 1}
    evidence_id_schema: dict[str, Any] = {"type": "string", "minLength": 1}
    if request is not None:
        finding_ids = sorted(request.allowed_finding_ids)
        evidence_ids = sorted({item for values in request.evidence_by_finding.values() for item in values})
        if finding_ids:
            finding_id_schema["enum"] = finding_ids
        if evidence_ids:
            evidence_id_schema["enum"] = evidence_ids
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "suggestions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "finding_id": finding_id_schema,
                        "objective": {"type": "string", "minLength": 1, "maxLength": 1200},
                        "target_location": {"type": "string", "minLength": 1, "maxLength": 700},
                        "proposed_text": {"type": "string", "minLength": 1, "maxLength": 8000},
                        "evidence_ids": {
                            "type": "array",
                            "minItems": 1,
                            "uniqueItems": True,
                            "items": evidence_id_schema,
                        },
                        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                        "current_degradation": {
                            "type": "string",
                            "minLength": 1,
                            "maxLength": 2000,
                            "description": "Current evidence-supported content/semantic limitation caused by the finding.",
                        },
                        "expected_benefit": {
                            "type": "string",
                            "minLength": 1,
                            "maxLength": 2000,
                            "description": "Qualitative evidence-bound benefit expected after applying the proposed text; do not promise ranking, traffic or conversion.",
                        },
                        "review_note": {"type": "string", "minLength": 1, "maxLength": 1200},
                    },
                    "required": [
                        "finding_id", "objective", "target_location", "proposed_text",
                        "evidence_ids", "confidence", "current_degradation", "expected_benefit",
                        "review_note",
                    ],
                },
            }
        },
        "required": ["suggestions"],
    }


def _validate_response(payload: Any, request: ContentRemediationRequest) -> tuple[ContentSuggestion, ...]:
    if not isinstance(payload, Mapping) or not isinstance(payload.get("suggestions"), list):
        raise ContentRemediationContractError("M20_INVALID_ROOT_SCHEMA", "M20 response has invalid root schema")
    evidence_by_finding = request.evidence_by_finding
    source_corpus = request.source_corpus.casefold()
    seen: set[str] = set()
    output: list[ContentSuggestion] = []
    for raw in payload["suggestions"]:
        if not isinstance(raw, Mapping):
            raise ContentRemediationContractError("M20_INVALID_SUGGESTION_ITEM", "M20 suggestion item must be an object")
        finding_id = str(raw.get("finding_id") or "").strip()
        if finding_id not in request.allowed_finding_ids:
            raise ContentRemediationContractError("M20_INVALID_FINDING_REFERENCE", "M20 suggestion references unknown finding")
        if finding_id in seen:
            raise ContentRemediationContractError("M20_DUPLICATE_FINDING_REFERENCE", "M20 suggestion duplicates finding")
        seen.add(finding_id)
        evidence_raw = raw.get("evidence_ids")
        if not isinstance(evidence_raw, list) or not evidence_raw:
            raise ContentRemediationContractError("M20_MISSING_EVIDENCE_IDS", "M20 suggestion requires evidence_ids")
        evidence_ids = tuple(str(item).strip() for item in evidence_raw if str(item).strip())
        if not evidence_ids or not set(evidence_ids).issubset(evidence_by_finding[finding_id]):
            raise ContentRemediationContractError("M20_EVIDENCE_OUTSIDE_FINDING", "M20 suggestion references evidence outside its finding")
        proposed_text = str(raw.get("proposed_text") or "").strip()
        objective = str(raw.get("objective") or "").strip()
        target_location = str(raw.get("target_location") or "").strip()
        review_note = str(raw.get("review_note") or "").strip()
        if not proposed_text or not objective or not target_location or not review_note:
            raise ContentRemediationContractError("M20_EMPTY_REQUIRED_TEXT", "M20 suggestion contains empty required text")
        try:
            confidence = float(raw.get("confidence"))
        except (TypeError, ValueError) as exc:
            raise ContentRemediationContractError("M20_INVALID_CONFIDENCE", "M20 confidence is not numeric") from exc
        if not 0 <= confidence <= 1:
            raise ContentRemediationContractError("M20_INVALID_CONFIDENCE", "M20 confidence must be between 0 and 1")
        if any(token.casefold() not in source_corpus for token in _NUMERIC_TOKEN.findall(proposed_text)):
            raise ContentRemediationContractError("M20_UNSUPPORTED_NUMERIC_CLAIM", "M20 suggestion introduces unsupported numeric claim")
        current_degradation = str(raw.get("current_degradation") or "").strip()
        expected_benefit = str(raw.get("expected_benefit") or "").strip()
        if not current_degradation or not expected_benefit:
            raise ContentRemediationContractError(
                "CONTENT_REMEDIATION_MISSING_IMPACT_EXPLANATION",
                "content suggestion requires current degradation and expected benefit",
            )
        review_note = "\n".join(
            (
                "Degradação/risco atual: " + current_degradation,
                "Benefício esperado se aplicado: " + expected_benefit,
                "Revisão humana: " + review_note,
            )
        )
        output.append(ContentSuggestion(
            finding_id=finding_id,
            objective=objective,
            target_location=target_location,
            proposed_text=proposed_text,
            evidence_ids=evidence_ids,
            confidence=confidence,
            review_note=review_note,
        ))
    return tuple(output)


class ContentRemediationProvider:
    """Structured M20 client cloned from one configured M18 provider."""

    def __init__(self, base: ResponsesSemanticProvider) -> None:
        self.base = base
        self.name = base.name
        self.model = base.model
        self.reasoning_profile = base.reasoning_profile
        self.requested_reasoning_effort = base.requested_reasoning_effort
        self.api_key = base.api_key
        self.endpoint = base.endpoint
        self.timeout = base.timeout
        self.structured_mode = base.structured_mode
        self.policy = base.policy
        self._transport = base._transport
        self._headers = base._headers
        self._runtime_state = RuntimeProviderState.ACTIVE
        self._rasai_execution_coordinator = getattr(base, "_rasai_execution_coordinator", None)
        self._rasai_execution_policy = getattr(base, "_rasai_execution_policy", None)
        self._rasai_cycle_sleeper = getattr(base, "_rasai_cycle_sleeper", None)
        self._last_attempt: ProviderAttempt | None = None
        self._last_attempts: tuple[ProviderAttempt, ...] = ()

    def analyze(
        self, request: ContentRemediationRequest, *, max_attempts: int = MAX_PROVIDER_ATTEMPTS_PER_CONTEXT
    ) -> ContentRemediationResult:
        """Execute exactly one provider call; logical retry/cadence belongs to the orchestrator."""
        del max_attempts  # compatibility argument; adapters never own logical retries.
        self._last_attempts = ()
        result = self._analyze_once(request)
        attempt = self._last_attempt
        self._last_attempt = None
        if attempt is not None:
            annotated = replace(
                attempt,
                attempt_index=1,
                retry_eligible=False,
                decision=(
                    DECISION_SUCCESS
                    if result.state is ProviderState.AVAILABLE
                    else DECISION_STOP
                ),
            )
            self._last_attempts = (annotated,)
        return result

    def _analyze_once(self, request: ContentRemediationRequest) -> ContentRemediationResult:
        self._last_attempt = None
        if self._runtime_state is RuntimeProviderState.QUARANTINED_FOR_AUDIT:
            return ContentRemediationResult(ProviderState.UNAVAILABLE, reason="AI_PROVIDER_UNAVAILABLE:PROVIDER_QUARANTINED", provider=self.name, model=self.model, reasoning_profile=self.reasoning_profile)
        if not self.api_key:
            return ContentRemediationResult(ProviderState.NOT_CONFIGURED, reason="AI_NOT_CONFIGURED", provider=self.name, model=self.model, reasoning_profile=self.reasoning_profile)

        schema = content_remediation_schema(request)
        context = configured_content_analysis_context()
        instructions = (
            "You are an evidence-bound website content remediation assistant. Return JSON only. "
            "Suggest exact text only for supplied findings and cite only evidence_ids attached to that finding. "
            "Use people-first language improving usefulness, clarity, completeness or trust. Do not write for "
            "search engines or AI systems, keyword-stuff, target word counts, or fabricate claims, dates, prices, "
            "statistics, credentials, experience, guarantees or sources. Do not alter facts. If evidence is "
            "insufficient for safe exact wording, omit that finding. Do not propose JSON-LD here; RASAi "
            "handles structured-data guidance deterministically. Human review is mandatory before publication. "
            "For every suggestion, current_degradation and expected_benefit are mandatory, evidence-bound, "
            "qualitative and non-promissory. "
            + context.prompt_directive()
        )
        if self.structured_mode == "json_object":
            instructions += "\nNormative local JSON Schema:\n" + json.dumps(schema, ensure_ascii=False, separators=(",", ":"))
            fmt: dict[str, Any] = {"type": "json_object"}
        else:
            fmt = {"type": "json_schema", "name": "rasai_content_remediation", "schema": schema}
            if self.name == "OPENAI":
                fmt["strict"] = True
        payload = {
            "model": self.model,
            "instructions": instructions,
            "input": [{"role": "user", "content": [{"type": "input_text", "text": "Persisted page evidence and findings:\n" + json.dumps(request.provider_payload(), ensure_ascii=False)}]}],
            "reasoning": {"effort": self.requested_reasoning_effort.casefold()},
            "text": {"format": fmt},
        }
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        summary = (
            f"contract={CONTENT_REMEDIATION_CONTRACT_VERSION};findings={len(request.findings)};"
            f"evidence={len(request.evidence)};snapshot={request.snapshot_id};context={context.compact_summary()}"
        )
        payload_hash = hashlib.sha256(body).hexdigest()
        started_at = datetime.now(timezone.utc)
        started_perf = time.perf_counter()
        try:
            raw = self._transport(self.endpoint, self._headers(), body, self.timeout)
        except HTTPError as exc:
            return self._failure(request, started_at, started_perf, summary, payload_hash, _diagnostic_from_http(exc), AttemptStatus.TECHNICAL_ERROR)
        except TimeoutError:
            return self._failure(request, started_at, started_perf, summary, payload_hash, ProviderDiagnostic(ProviderErrorClass.TIMEOUT_ERROR), AttemptStatus.TECHNICAL_ERROR)
        except (URLError, OSError):
            return self._failure(request, started_at, started_perf, summary, payload_hash, ProviderDiagnostic(ProviderErrorClass.NETWORK_ERROR), AttemptStatus.TECHNICAL_ERROR)
        except Exception:
            return self._failure(request, started_at, started_perf, summary, payload_hash, ProviderDiagnostic(ProviderErrorClass.UNKNOWN_PROVIDER_ERROR), AttemptStatus.TECHNICAL_ERROR)

        if not isinstance(raw, Mapping):
            return self._failure(request, started_at, started_perf, summary, payload_hash, ProviderDiagnostic(ProviderErrorClass.INVALID_RESPONSE), AttemptStatus.CONTRACT_ERROR)
        usage = _usage_from_native(raw)
        if not raw.get("output_text") and not raw.get("output"):
            return self._failure(request, started_at, started_perf, summary, payload_hash, ProviderDiagnostic(ProviderErrorClass.EMPTY_RESPONSE), AttemptStatus.CONTRACT_ERROR, usage=usage)
        native_error = _response_error(raw)
        if native_error is not None:
            return self._failure(request, started_at, started_perf, summary, payload_hash, native_error, AttemptStatus.TECHNICAL_ERROR, usage=usage)
        try:
            suggestions = _validate_response(_extract_json_payload(dict(raw)), request)
        except ContentRemediationContractError as exc:
            return self._failure(
                request, started_at, started_perf, summary, payload_hash,
                ProviderDiagnostic(ProviderErrorClass.CONTRACT_ERROR, error_type=type(exc).__name__, error_code=exc.code),
                AttemptStatus.CONTRACT_ERROR, usage=usage,
            )
        except Exception as exc:
            return self._failure(
                request, started_at, started_perf, summary, payload_hash,
                ProviderDiagnostic(ProviderErrorClass.CONTRACT_ERROR, error_type=type(exc).__name__, error_code="M20_UNEXPECTED_CONTRACT_ERROR"),
                AttemptStatus.CONTRACT_ERROR, usage=usage,
            )

        finished_at = datetime.now(timezone.utc)
        duration_ms = max(0, int((time.perf_counter() - started_perf) * 1000))
        pricing = resolve_provider_cost(self, usage, finished_at)
        self._last_attempt = ProviderAttempt(
            provider=self.name, model=self.model, reasoning_profile=self.reasoning_profile,
            provider_rank=self.policy.rank, attempt_index=1, snapshot_id=request.snapshot_id,
            url=request.page_url, started_at=started_at, finished_at=finished_at,
            duration_ms=duration_ms, status=AttemptStatus.SUCCESS, usage=usage,
            estimated_cost=pricing.estimated_cost, cost_currency=pricing.currency, pricing_version=pricing.pricing_version,
            pricing_context=pricing.pricing_context, pricing_rule_id=pricing.pricing_rule_id,
            pricing_source_reference=pricing.pricing_source_reference, pricing_runtime_conditions=pricing.runtime_conditions,
            request_message_summary=summary, request_payload_hash=payload_hash,
            provider_qualification=self.policy.qualification,
            provider_reliability_score=self.policy.reliability_score,
            semantic_contract_version=CONTENT_REMEDIATION_CONTRACT_VERSION,
        )
        return ContentRemediationResult(ProviderState.AVAILABLE, suggestions=suggestions, provider=self.name, model=self.model, reasoning_profile=self.reasoning_profile)

    def _failure(self, request, started_at, started_perf, summary, payload_hash, diagnostic, status, *, usage=None):
        finished_at = datetime.now(timezone.utc)
        pricing = resolve_provider_cost(self, usage, finished_at)
        self._last_attempt = ProviderAttempt(
            provider=self.name, model=self.model, reasoning_profile=self.reasoning_profile,
            provider_rank=self.policy.rank, attempt_index=1, snapshot_id=request.snapshot_id,
            url=request.page_url, started_at=started_at, finished_at=finished_at,
            duration_ms=max(0, int((time.perf_counter() - started_perf) * 1000)),
            status=status, diagnostic=diagnostic, usage=usage,
            estimated_cost=pricing.estimated_cost, cost_currency=pricing.currency, pricing_version=pricing.pricing_version,
            pricing_context=pricing.pricing_context, pricing_rule_id=pricing.pricing_rule_id,
            pricing_source_reference=pricing.pricing_source_reference, pricing_runtime_conditions=pricing.runtime_conditions,
            request_message_summary=summary, request_payload_hash=payload_hash,
            provider_qualification=self.policy.qualification,
            provider_reliability_score=self.policy.reliability_score,
            semantic_contract_version=CONTENT_REMEDIATION_CONTRACT_VERSION,
        )
        return ContentRemediationResult(ProviderState.UNAVAILABLE, reason=diagnostic.reason, provider=self.name, model=self.model, reasoning_profile=self.reasoning_profile)

    def consume_attempts(self) -> tuple[ProviderAttempt, ...]:
        items = self._last_attempts
        self._last_attempts = ()
        self._last_attempt = None
        return items


@dataclass(slots=True)
class ContentRemediationRoutingSession:
    providers: tuple[ContentRemediationProvider, ...]
    strategy: str
    excluded_configurations: tuple[str, ...] = ()
    _states: dict[str, RuntimeProviderState] = field(init=False, default_factory=dict)
    _pins: dict[str, str] = field(init=False, default_factory=dict)
    _last_attempts: tuple[ProviderAttempt, ...] = field(init=False, default=())

    def __post_init__(self) -> None:
        self.providers = tuple(sorted(self.providers, key=lambda item: item.policy.rank))
        for item in self.providers:
            self._states[item.name] = RuntimeProviderState.ACTIVE

    def analyze(self, request: ContentRemediationRequest) -> ContentRemediationResult:
        from rasai.ai_canonical_orchestration import (
            AiExecutionPolicy,
            AiProviderInvocation,
            AiProviderOutcome,
            invocation_from_diagnostic,
            run_ai_need,
        )
        from rasai.dynamic_ai_routing import (
            execution_coordinator_for,
            provider_is_eligible,
            record_canonical_attempt,
        )

        self._last_attempts = ()
        if not self.providers:
            return ContentRemediationResult(ProviderState.NOT_CONFIGURED, reason="AI_NOT_CONFIGURED")

        attempts: list[ProviderAttempt] = []
        last: ContentRemediationResult | None = None
        winner: ContentRemediationResult | None = None
        fallback_from: str | None = None
        fallback_reason: str | None = None

        first = self.providers[0]
        policy = getattr(first, "_rasai_execution_policy", None)
        if not isinstance(policy, AiExecutionPolicy):
            policy = AiExecutionPolicy()
        sleeper = getattr(first, "_rasai_cycle_sleeper", None)

        def candidates() -> tuple[ContentRemediationProvider, ...]:
            items = [item for item in self.providers if provider_is_eligible(item)]
            pinned = self._pins.get(request.page_url)
            if pinned:
                items.sort(key=lambda item: (0 if item.name == pinned else 1, item.policy.rank))
            else:
                items.sort(key=lambda item: item.policy.rank)
            return tuple(items)

        def invoke(provider: ContentRemediationProvider, cycle: int, call_index: int) -> AiProviderInvocation:
            nonlocal last, winner, fallback_from, fallback_reason
            result = provider.analyze(request, max_attempts=1)
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
            last = result
            attempt = local[-1] if local else None
            if attempt is not None:
                record_canonical_attempt(
                    provider,
                    attempt,
                    scope="CONTENT_REMEDIATION",
                    page_url=str(request.page_url),
                )

            if result.state is ProviderState.AVAILABLE:
                if attempts:
                    attempts[-1] = replace(
                        attempts[-1],
                        decision=DECISION_FALLBACK_SUCCESS if fallback_from else DECISION_SUCCESS,
                        fallback_from_provider=fallback_from,
                        fallback_reason=fallback_reason,
                    )
                self._pins[request.page_url] = provider.name
                winner = result
                return AiProviderInvocation(AiProviderOutcome.COMPLETE)

            if result.state is ProviderState.NOT_CONFIGURED:
                coordinator = execution_coordinator_for(provider)
                if coordinator is not None:
                    coordinator.exclude_configuration(provider.name, "NOT_CONFIGURED_DURING_EXECUTION")
                return AiProviderInvocation(AiProviderOutcome.PROVIDER_TERMINAL)

            if attempts:
                attempts[-1] = replace(attempts[-1], decision=DECISION_FALLBACK)
            fallback_from = provider.name
            fallback_reason = result.reason or "AI_PROVIDER_UNAVAILABLE"
            if attempt is not None and attempt.diagnostic is not None:
                return invocation_from_diagnostic(attempt.diagnostic)
            return AiProviderInvocation(AiProviderOutcome.NO_PROGRESS)

        run_ai_need(
            candidates=candidates,
            invoke=invoke,
            policy=policy,
            sleeper=sleeper,
        )
        self._last_attempts = tuple(attempts)
        if winner is not None:
            return winner
        if not candidates():
            return ContentRemediationResult(
                ProviderState.UNAVAILABLE,
                reason="AI_PROVIDER_CHAIN_EXHAUSTED",
            )
        return last or ContentRemediationResult(
            ProviderState.UNAVAILABLE,
            reason="AI_PROVIDER_UNAVAILABLE",
        )

    def consume_attempts(self) -> tuple[ProviderAttempt, ...]:
        items = self._last_attempts
        self._last_attempts = ()
        return items

    def _healthy_candidates(self) -> tuple[ContentRemediationProvider, ...]:
        from rasai.dynamic_ai_routing import provider_is_eligible
        return tuple(item for item in self.providers if provider_is_eligible(item))


def build_content_remediation_router(semantic_provider: Any) -> ContentRemediationRoutingSession:
    """Clone only providers still healthy after M7, preserving audit quarantine."""
    snapshot = provider_session_snapshot(semantic_provider)
    strategy = str(snapshot.get("strategy") or "NONE")
    states = dict(snapshot.get("provider_states") or {})
    excluded = tuple(snapshot.get("excluded_configurations") or ())
    bases: list[ResponsesSemanticProvider] = []
    routed = getattr(semantic_provider, "providers", None)
    if isinstance(routed, tuple):
        for item in routed:
            if isinstance(item, ResponsesSemanticProvider) and item.api_key and states.get(item.name) != RuntimeProviderState.QUARANTINED_FOR_AUDIT.value:
                bases.append(item)
    elif isinstance(semantic_provider, ResponsesSemanticProvider):
        state = getattr(semantic_provider, "_runtime_state", RuntimeProviderState.ACTIVE)
        if semantic_provider.api_key and state is not RuntimeProviderState.QUARANTINED_FOR_AUDIT:
            bases.append(semantic_provider)
    return ContentRemediationRoutingSession(tuple(ContentRemediationProvider(item) for item in bases), strategy=strategy, excluded_configurations=excluded)
