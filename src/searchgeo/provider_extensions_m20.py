"""M20 adapters for explicit-only provider extensions.

Legacy M20 routing is delegated unchanged for OpenAI, DeepSeek, MiMo and AUTO.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
import time
from typing import Any, Mapping
from urllib.error import HTTPError, URLError

from searchgeo.ai_resilience import (
    DECISION_RETRY,
    DECISION_STOP,
    DECISION_SUCCESS,
    DECISION_SUCCESS_AFTER_RETRY,
    MAX_PROVIDER_ATTEMPTS_PER_CONTEXT,
    retry_policy,
)
from searchgeo.m18_ai import (
    AttemptStatus,
    ProviderAttempt,
    ProviderDiagnostic,
    ProviderErrorClass,
    ProviderState,
    RuntimeProviderState,
    estimate_cost,
)
from searchgeo.m20_ai import (
    CONTENT_REMEDIATION_CONTRACT_VERSION,
    ContentRemediationRequest,
    ContentRemediationResult,
    ContentRemediationRoutingSession,
    build_content_remediation_router as _legacy_build_content_remediation_router,
    content_remediation_schema,
    _validate_response,
)
from searchgeo.provider_extensions import (
    AnthropicProvider,
    GeminiProvider,
    IsolatedStructuredSemanticProvider,
    QwenProvider,
    XAIProvider,
    _diagnostic_from_http,
)


def _instructions() -> str:
    return (
        "You are an evidence-bound website content remediation assistant. Return JSON only. "
        "Suggest exact text only for supplied findings and cite only evidence_ids attached to that finding. "
        "Use people-first language improving usefulness, clarity, completeness or trust. Do not write for "
        "search engines or AI systems, keyword-stuff, target word counts, or fabricate claims, dates, prices, "
        "statistics, credentials, experience, guarantees or sources. Do not alter facts. If evidence is "
        "insufficient for safe exact wording, omit that finding. Do not propose JSON-LD here; RASAi "
        "handles structured-data guidance deterministically. Human review is mandatory before publication."
    )


class ExtensionContentRemediationProvider:
    """M20 structured-output client backed by one healthy extension provider."""

    def __init__(self, base: IsolatedStructuredSemanticProvider) -> None:
        self.base = base
        self.name = base.name
        self.model = base.model
        self.reasoning_profile = base.reasoning_profile
        self.api_key = base.api_key
        self.endpoint = base.endpoint
        self.timeout = base.timeout
        self.policy = base.policy
        self._transport = base._transport
        self._runtime_state = RuntimeProviderState.ACTIVE
        self._last_attempt: ProviderAttempt | None = None
        self._last_attempts: tuple[ProviderAttempt, ...] = ()

    def _request_payload(self, request: ContentRemediationRequest) -> dict[str, Any]:
        schema = content_remediation_schema()
        user_text = "Persisted page evidence and findings:\n" + json.dumps(
            request.provider_payload(), ensure_ascii=False
        )
        instructions = _instructions()

        if isinstance(self.base, XAIProvider):
            return {
                "model": self.model,
                "instructions": instructions,
                "input": [{
                    "role": "user",
                    "content": [{"type": "input_text", "text": user_text}],
                }],
                "reasoning": {"effort": "high"},
                "text": {
                    "format": {
                        "type": "json_schema",
                        "name": "searchgeo_content_remediation",
                        "schema": schema,
                        "strict": True,
                    }
                },
            }

        if isinstance(self.base, QwenProvider):
            return {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": instructions},
                    {"role": "user", "content": user_text},
                ],
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "searchgeo_content_remediation",
                        "schema": schema,
                        "strict": True,
                    },
                },
            }

        if isinstance(self.base, GeminiProvider):
            return {
                "model": self.model,
                "input": instructions + "\n\n" + user_text,
                "response_format": {
                    "type": "text",
                    "mime_type": "application/json",
                    "schema": schema,
                },
            }

        if isinstance(self.base, AnthropicProvider):
            return {
                "model": self.model,
                "max_tokens": 16384,
                "system": instructions,
                "messages": [{"role": "user", "content": user_text}],
                "output_config": {
                    "format": {
                        "type": "json_schema",
                        "schema": schema,
                    }
                },
            }

        raise ValueError(f"unsupported extension provider for M20: {self.name}")

    def analyze(
        self,
        request: ContentRemediationRequest,
        *,
        max_attempts: int = MAX_PROVIDER_ATTEMPTS_PER_CONTEXT,
    ) -> ContentRemediationResult:
        """Retry only one transient integration failure; never loop paid calls."""
        self._last_attempts = ()
        collected: list[ProviderAttempt] = []
        bounded = max(1, min(int(max_attempts), MAX_PROVIDER_ATTEMPTS_PER_CONTEXT))
        last: ContentRemediationResult | None = None
        for ordinal in range(1, bounded + 1):
            result = self._analyze_once(request)
            last = result
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
                        attempt.provider,
                        attempt.model or "",
                        attempt.usage,
                        attempt.finished_at,
                    )
                if result.state is ProviderState.AVAILABLE:
                    decision = DECISION_SUCCESS_AFTER_RETRY if ordinal > 1 else DECISION_SUCCESS
                elif policy.eligible and ordinal < bounded:
                    decision = DECISION_RETRY
                else:
                    decision = DECISION_STOP
                collected.append(
                    replace(
                        attempt,
                        attempt_index=ordinal,
                        retry_eligible=policy.eligible,
                        decision=decision,
                        estimated_cost=estimated,
                        cost_currency=currency,
                        pricing_version=pricing_version,
                    )
                )

            if result.state is ProviderState.AVAILABLE:
                self._last_attempts = tuple(collected)
                return result
            if result.state is ProviderState.NOT_CONFIGURED:
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
        return last or ContentRemediationResult(
            ProviderState.UNAVAILABLE,
            reason="AI_PROVIDER_UNAVAILABLE",
            provider=self.name,
            model=self.model,
            reasoning_profile=self.reasoning_profile,
        )

    def _analyze_once(self, request: ContentRemediationRequest) -> ContentRemediationResult:
        self._last_attempt = None
        if self._runtime_state is RuntimeProviderState.QUARANTINED_FOR_AUDIT:
            return ContentRemediationResult(
                ProviderState.UNAVAILABLE,
                reason="AI_PROVIDER_UNAVAILABLE:PROVIDER_QUARANTINED",
                provider=self.name,
                model=self.model,
                reasoning_profile=self.reasoning_profile,
            )
        if not self.api_key:
            return ContentRemediationResult(
                ProviderState.NOT_CONFIGURED,
                reason="AI_NOT_CONFIGURED",
                provider=self.name,
                model=self.model,
                reasoning_profile=self.reasoning_profile,
            )

        payload = self._request_payload(request)
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        summary = (
            f"contract={CONTENT_REMEDIATION_CONTRACT_VERSION};"
            f"findings={len(request.findings)};"
            f"evidence={len(request.evidence)};"
            f"snapshot={request.snapshot_id}"
        )
        payload_hash = hashlib.sha256(body).hexdigest()
        started_at = datetime.now(timezone.utc)
        started_perf = time.perf_counter()

        try:
            raw = self._transport(self.endpoint, self.base._headers(), body, self.timeout)
        except HTTPError as exc:
            return self._failure(
                request, started_at, started_perf, summary, payload_hash,
                _diagnostic_from_http(exc), AttemptStatus.TECHNICAL_ERROR,
            )
        except TimeoutError:
            return self._failure(
                request, started_at, started_perf, summary, payload_hash,
                ProviderDiagnostic(ProviderErrorClass.TIMEOUT_ERROR),
                AttemptStatus.TECHNICAL_ERROR,
            )
        except (URLError, OSError):
            return self._failure(
                request, started_at, started_perf, summary, payload_hash,
                ProviderDiagnostic(ProviderErrorClass.NETWORK_ERROR),
                AttemptStatus.TECHNICAL_ERROR,
            )
        except Exception:
            return self._failure(
                request, started_at, started_perf, summary, payload_hash,
                ProviderDiagnostic(ProviderErrorClass.UNKNOWN_PROVIDER_ERROR),
                AttemptStatus.TECHNICAL_ERROR,
            )

        if not isinstance(raw, Mapping):
            return self._failure(
                request, started_at, started_perf, summary, payload_hash,
                ProviderDiagnostic(ProviderErrorClass.INVALID_RESPONSE),
                AttemptStatus.CONTRACT_ERROR,
            )

        usage = self.base._usage(raw)
        native_error = self.base._native_error(raw)
        if native_error is not None:
            return self._failure(
                request, started_at, started_perf, summary, payload_hash,
                native_error, AttemptStatus.TECHNICAL_ERROR, usage=usage,
            )

        try:
            suggestions = _validate_response(self.base._extract_payload(raw), request)
        except Exception as exc:
            return self._failure(
                request, started_at, started_perf, summary, payload_hash,
                ProviderDiagnostic(
                    ProviderErrorClass.CONTRACT_ERROR,
                    error_type=type(exc).__name__,
                ),
                AttemptStatus.CONTRACT_ERROR,
                usage=usage,
            )

        finished_at = datetime.now(timezone.utc)
        self._last_attempt = ProviderAttempt(
            provider=self.name,
            model=self.model,
            reasoning_profile=self.reasoning_profile,
            provider_rank=self.policy.rank,
            attempt_index=1,
            snapshot_id=request.snapshot_id,
            url=request.page_url,
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=max(0, int((time.perf_counter() - started_perf) * 1000)),
            status=AttemptStatus.SUCCESS,
            usage=usage,
            estimated_cost=None,
            cost_currency=None,
            pricing_version=None,
            request_message_summary=summary,
            request_payload_hash=payload_hash,
            provider_qualification=self.policy.qualification,
            provider_reliability_score=self.policy.reliability_score,
            semantic_contract_version=CONTENT_REMEDIATION_CONTRACT_VERSION,
        )
        return ContentRemediationResult(
            ProviderState.AVAILABLE,
            suggestions=suggestions,
            provider=self.name,
            model=self.model,
            reasoning_profile=self.reasoning_profile,
        )

    def _failure(
        self,
        request: ContentRemediationRequest,
        started_at: datetime,
        started_perf: float,
        summary: str,
        payload_hash: str,
        diagnostic: ProviderDiagnostic,
        status: AttemptStatus,
        *,
        usage=None,
    ) -> ContentRemediationResult:
        finished_at = datetime.now(timezone.utc)
        self._last_attempt = ProviderAttempt(
            provider=self.name,
            model=self.model,
            reasoning_profile=self.reasoning_profile,
            provider_rank=self.policy.rank,
            attempt_index=1,
            snapshot_id=request.snapshot_id,
            url=request.page_url,
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=max(0, int((time.perf_counter() - started_perf) * 1000)),
            status=status,
            diagnostic=diagnostic,
            usage=usage,
            request_message_summary=summary,
            request_payload_hash=payload_hash,
            provider_qualification=self.policy.qualification,
            provider_reliability_score=self.policy.reliability_score,
            semantic_contract_version=CONTENT_REMEDIATION_CONTRACT_VERSION,
        )
        self._runtime_state = RuntimeProviderState.QUARANTINED_FOR_AUDIT
        return ContentRemediationResult(
            ProviderState.UNAVAILABLE,
            reason=diagnostic.reason,
            provider=self.name,
            model=self.model,
            reasoning_profile=self.reasoning_profile,
        )

    def consume_attempts(self) -> tuple[ProviderAttempt, ...]:
        items = self._last_attempts
        self._last_attempts = ()
        self._last_attempt = None
        return items


def build_content_remediation_router(semantic_provider: Any) -> ContentRemediationRoutingSession:
    """Add M20 support only for explicit extension providers; delegate legacy otherwise."""
    if not isinstance(semantic_provider, IsolatedStructuredSemanticProvider):
        return _legacy_build_content_remediation_router(semantic_provider)

    state = getattr(semantic_provider, "_runtime_state", RuntimeProviderState.ACTIVE)
    if not semantic_provider.api_key or state is RuntimeProviderState.QUARANTINED_FOR_AUDIT:
        providers: tuple[ExtensionContentRemediationProvider, ...] = ()
    else:
        providers = (ExtensionContentRemediationProvider(semantic_provider),)

    snapshot = semantic_provider.session_snapshot()
    return ContentRemediationRoutingSession(
        providers,
        strategy=str(snapshot.get("strategy") or "SINGLE_PROVIDER"),
        excluded_configurations=tuple(snapshot.get("excluded_configurations") or ()),
    )
