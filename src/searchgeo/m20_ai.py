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

from searchgeo.content_context import configured_content_analysis_context
from searchgeo.m18_ai import (
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
    provider_session_snapshot,
)
from searchgeo.semantic import _extract_json_payload

CONTENT_REMEDIATION_CONTRACT_VERSION = "M20-CONTENT-REMEDIATION-v2"
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


def content_remediation_schema() -> dict[str, Any]:
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
                        "finding_id": {"type": "string", "minLength": 1},
                        "objective": {"type": "string", "minLength": 1, "maxLength": 1200},
                        "target_location": {"type": "string", "minLength": 1, "maxLength": 700},
                        "proposed_text": {"type": "string", "minLength": 1, "maxLength": 8000},
                        "evidence_ids": {
                            "type": "array",
                            "minItems": 1,
                            "uniqueItems": True,
                            "items": {"type": "string", "minLength": 1},
                        },
                        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                        "review_note": {"type": "string", "minLength": 1, "maxLength": 1200},
                    },
                    "required": [
                        "finding_id", "objective", "target_location", "proposed_text",
                        "evidence_ids", "confidence", "review_note",
                    ],
                },
            }
        },
        "required": ["suggestions"],
    }


def _validate_response(payload: Any, request: ContentRemediationRequest) -> tuple[ContentSuggestion, ...]:
    if not isinstance(payload, Mapping) or not isinstance(payload.get("suggestions"), list):
        raise ValueError("M20 response has invalid root schema")
    evidence_by_finding = request.evidence_by_finding
    source_corpus = request.source_corpus.casefold()
    seen: set[str] = set()
    output: list[ContentSuggestion] = []
    for raw in payload["suggestions"]:
        if not isinstance(raw, Mapping):
            raise ValueError("M20 suggestion item must be an object")
        finding_id = str(raw.get("finding_id") or "").strip()
        if finding_id not in request.allowed_finding_ids or finding_id in seen:
            raise ValueError("M20 suggestion references invalid/duplicate finding")
        seen.add(finding_id)
        evidence_raw = raw.get("evidence_ids")
        if not isinstance(evidence_raw, list) or not evidence_raw:
            raise ValueError("M20 suggestion requires evidence_ids")
        evidence_ids = tuple(str(item).strip() for item in evidence_raw if str(item).strip())
        if not evidence_ids or not set(evidence_ids).issubset(evidence_by_finding[finding_id]):
            raise ValueError("M20 suggestion references evidence outside its finding")
        proposed_text = str(raw.get("proposed_text") or "").strip()
        objective = str(raw.get("objective") or "").strip()
        target_location = str(raw.get("target_location") or "").strip()
        review_note = str(raw.get("review_note") or "").strip()
        if not proposed_text or not objective or not target_location or not review_note:
            raise ValueError("M20 suggestion contains empty required text")
        confidence = float(raw.get("confidence"))
        if not 0 <= confidence <= 1:
            raise ValueError("M20 confidence must be between 0 and 1")
        if any(token.casefold() not in source_corpus for token in _NUMERIC_TOKEN.findall(proposed_text)):
            raise ValueError("M20 suggestion introduces unsupported numeric claim")
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
        self._last_attempt: ProviderAttempt | None = None

    def analyze(self, request: ContentRemediationRequest) -> ContentRemediationResult:
        self._last_attempt = None
        if self._runtime_state is RuntimeProviderState.QUARANTINED_FOR_AUDIT:
            return ContentRemediationResult(ProviderState.UNAVAILABLE, reason="AI_PROVIDER_UNAVAILABLE:PROVIDER_QUARANTINED", provider=self.name, model=self.model, reasoning_profile=self.reasoning_profile)
        if not self.api_key:
            return ContentRemediationResult(ProviderState.NOT_CONFIGURED, reason="AI_NOT_CONFIGURED", provider=self.name, model=self.model, reasoning_profile=self.reasoning_profile)

        schema = content_remediation_schema()
        context = configured_content_analysis_context()
        instructions = (
            "You are an evidence-bound website content remediation assistant. Return JSON only. "
            "Suggest exact text only for supplied findings and cite only evidence_ids attached to that finding. "
            "Use people-first language improving usefulness, clarity, completeness or trust. Do not write for "
            "search engines or AI systems, keyword-stuff, target word counts, or fabricate claims, dates, prices, "
            "statistics, credentials, experience, guarantees or sources. Do not alter facts. If evidence is "
            "insufficient for safe exact wording, omit that finding. Do not propose JSON-LD here; SearchGEO "
            "handles structured-data guidance deterministically. Human review is mandatory before publication. "
            + context.prompt_directive()
        )
        if self.structured_mode == "json_object":
            instructions += "\nNormative local JSON Schema:\n" + json.dumps(schema, ensure_ascii=False, separators=(",", ":"))
            fmt: dict[str, Any] = {"type": "json_object"}
        else:
            fmt = {"type": "json_schema", "name": "searchgeo_content_remediation", "schema": schema}
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
        except Exception as exc:
            return self._failure(request, started_at, started_perf, summary, payload_hash, ProviderDiagnostic(ProviderErrorClass.CONTRACT_ERROR, error_type=type(exc).__name__), AttemptStatus.CONTRACT_ERROR, usage=usage)

        finished_at = datetime.now(timezone.utc)
        duration_ms = max(0, int((time.perf_counter() - started_perf) * 1000))
        estimated, currency, pricing_version = estimate_cost(self.name, self.model, usage, finished_at)
        self._last_attempt = ProviderAttempt(
            provider=self.name, model=self.model, reasoning_profile=self.reasoning_profile,
            provider_rank=self.policy.rank, attempt_index=1, snapshot_id=request.snapshot_id,
            url=request.page_url, started_at=started_at, finished_at=finished_at,
            duration_ms=duration_ms, status=AttemptStatus.SUCCESS, usage=usage,
            estimated_cost=estimated, cost_currency=currency, pricing_version=pricing_version,
            request_message_summary=summary, request_payload_hash=payload_hash,
            provider_qualification=self.policy.qualification,
            provider_reliability_score=self.policy.reliability_score,
            semantic_contract_version=CONTENT_REMEDIATION_CONTRACT_VERSION,
        )
        return ContentRemediationResult(ProviderState.AVAILABLE, suggestions=suggestions, provider=self.name, model=self.model, reasoning_profile=self.reasoning_profile)

    def _failure(self, request, started_at, started_perf, summary, payload_hash, diagnostic, status, *, usage=None):
        finished_at = datetime.now(timezone.utc)
        self._last_attempt = ProviderAttempt(
            provider=self.name, model=self.model, reasoning_profile=self.reasoning_profile,
            provider_rank=self.policy.rank, attempt_index=1, snapshot_id=request.snapshot_id,
            url=request.page_url, started_at=started_at, finished_at=finished_at,
            duration_ms=max(0, int((time.perf_counter() - started_perf) * 1000)),
            status=status, diagnostic=diagnostic, usage=usage,
            request_message_summary=summary, request_payload_hash=payload_hash,
            provider_qualification=self.policy.qualification,
            provider_reliability_score=self.policy.reliability_score,
            semantic_contract_version=CONTENT_REMEDIATION_CONTRACT_VERSION,
        )
        self._runtime_state = RuntimeProviderState.QUARANTINED_FOR_AUDIT
        return ContentRemediationResult(ProviderState.UNAVAILABLE, reason=diagnostic.reason, provider=self.name, model=self.model, reasoning_profile=self.reasoning_profile)

    def consume_attempts(self) -> tuple[ProviderAttempt, ...]:
        item = self._last_attempt
        self._last_attempt = None
        return (item,) if item else ()


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
        self._last_attempts = ()
        if not self.providers:
            return ContentRemediationResult(ProviderState.NOT_CONFIGURED, reason="AI_NOT_CONFIGURED")
        candidates = self._healthy_candidates()
        pinned = self._pins.get(request.page_url)
        if pinned:
            candidates = tuple(item for item in candidates if item.name == pinned)
            if not candidates:
                return ContentRemediationResult(ProviderState.UNAVAILABLE, reason="AI_PROVIDER_UNAVAILABLE:PINNED_PROVIDER_QUARANTINED", provider=pinned)
        attempts: list[ProviderAttempt] = []
        last: ContentRemediationResult | None = None
        for index, provider in enumerate(candidates, 1):
            result = provider.analyze(request)
            attempts.extend(replace(item, attempt_index=index) for item in provider.consume_attempts())
            last = result
            if result.state is ProviderState.AVAILABLE:
                self._pins[request.page_url] = provider.name
                self._last_attempts = tuple(attempts)
                return result
            if result.state is not ProviderState.NOT_CONFIGURED:
                self._states[provider.name] = RuntimeProviderState.QUARANTINED_FOR_AUDIT
        self._last_attempts = tuple(attempts)
        if not self._healthy_candidates():
            return ContentRemediationResult(ProviderState.UNAVAILABLE, reason="AI_PROVIDER_CHAIN_EXHAUSTED")
        return last or ContentRemediationResult(ProviderState.UNAVAILABLE, reason="AI_PROVIDER_UNAVAILABLE")

    def consume_attempts(self) -> tuple[ProviderAttempt, ...]:
        items = self._last_attempts
        self._last_attempts = ()
        return items

    def _healthy_candidates(self) -> tuple[ContentRemediationProvider, ...]:
        return tuple(item for item in self.providers if self._states.get(item.name) is not RuntimeProviderState.QUARANTINED_FOR_AUDIT)


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
