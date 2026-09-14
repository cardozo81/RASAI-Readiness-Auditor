"""Unify specialist AI consumers with the canonical RASAi provider runtime.

This module is intentionally an integration layer. It does not redefine AUTO ranking,
pricing, quarantine, circuit-breaker thresholds or retry limits. Specialist features keep
their own evidence/schema contracts while provider selection and AUTO candidate ordering
come from :mod:`rasai.provider_runtime_policy` / :mod:`rasai.dynamic_ai_routing`.
"""
from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from hashlib import sha256
import json
import math
import os
import time
from typing import Any, Mapping
from urllib.error import HTTPError, URLError


_INSTALLED = False
_PRIMARY_AI_CONTEXT: ContextVar[tuple[str, str, str] | None] = ContextVar(
    "rasai_primary_ai_context", default=None
)


@dataclass(frozen=True, slots=True)
class _TokenHint:
    estimated_input_tokens: int
    estimated_output_tokens: int


def _token_hint(text: str, *, output_tokens: int = 2400) -> _TokenHint:
    return _TokenHint(
        estimated_input_tokens=max(1000, int(math.ceil(len(text) / 4.0))),
        estimated_output_tokens=max(600, int(output_tokens)),
    )


def _provider_candidates(runtime: Any, request: Any, *, scope: str) -> tuple[Any, ...]:
    ordered = getattr(runtime, "ordered_candidates_for_need", None)
    if callable(ordered):
        return tuple(ordered(request, scope=scope))
    name = str(getattr(runtime, "name", "NONE") or "NONE").upper()
    if name in {"NONE", ""}:
        return ()
    if not bool(getattr(runtime, "api_key", None)):
        return ()
    return (runtime,)


def _apply_timeout(runtime: Any, timeout: float) -> None:
    routed = getattr(runtime, "providers", None)
    if isinstance(routed, tuple):
        for item in routed:
            if hasattr(item, "timeout"):
                item.timeout = timeout
        return
    if hasattr(runtime, "timeout"):
        runtime.timeout = timeout


def _structured_payload(
    provider: Any,
    *,
    schema_name: str,
    instructions: str,
    user_text: str,
    schema: dict[str, Any],
) -> dict[str, Any]:
    from rasai.m18_ai import ResponsesSemanticProvider
    from rasai.provider_extensions import (
        AnthropicProvider,
        GeminiProvider,
        QwenProvider,
        XAIProvider,
        gemini_wire_schema,
    )

    name = str(getattr(provider, "name", "")).upper()
    model = str(getattr(provider, "model", ""))
    if isinstance(provider, ResponsesSemanticProvider):
        if provider.structured_mode == "json_object":
            instructions += "\nNormative local JSON Schema:\n" + json.dumps(
                schema, ensure_ascii=False, separators=(",", ":")
            )
            fmt: dict[str, Any] = {"type": "json_object"}
        else:
            fmt = {"type": "json_schema", "name": schema_name, "schema": schema}
            if name == "OPENAI":
                fmt["strict"] = True
        payload: dict[str, Any] = {
            "model": model,
            "instructions": instructions,
            "input": [
                {
                    "role": "user",
                    "content": [{"type": "input_text", "text": user_text}],
                }
            ],
            "text": {"format": fmt},
        }
        effort = str(getattr(provider, "requested_reasoning_effort", "NONE")).casefold()
        if effort != "none":
            payload["reasoning"] = {"effort": effort}
        return payload
    if name == "COPILOT":
        return {
            "model": model,
            "prompt": instructions
            + "\n\nJSON Schema:\n"
            + json.dumps(schema, ensure_ascii=False)
            + "\n\n"
            + user_text,
        }
    if isinstance(provider, XAIProvider):
        return {
            "model": model,
            "instructions": instructions,
            "input": [{"role": "user", "content": [{"type": "input_text", "text": user_text}]}],
            "reasoning": {
                "effort": str(getattr(provider, "reasoning_profile", "HIGH")).casefold()
            },
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": schema_name,
                    "schema": schema,
                    "strict": True,
                }
            },
        }
    if isinstance(provider, QwenProvider):
        return {
            "model": model,
            "messages": [
                {"role": "system", "content": instructions},
                {"role": "user", "content": user_text},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": schema_name, "schema": schema, "strict": True},
            },
        }
    if isinstance(provider, GeminiProvider):
        return {
            "model": model,
            "input": instructions + "\n\n" + user_text,
            "response_format": {
                "type": "text",
                "mime_type": "application/json",
                "schema": gemini_wire_schema(schema),
            },
        }
    if isinstance(provider, AnthropicProvider):
        return {
            "model": model,
            "max_tokens": 16384,
            "system": instructions,
            "messages": [{"role": "user", "content": user_text}],
            "output_config": {"format": {"type": "json_schema", "schema": schema}},
        }
    raise ValueError(f"provider sem contrato estruturado compatível: {type(provider).__name__}")


def _provider_usage(provider: Any, raw: Mapping[str, Any]):
    from rasai.improvement_intelligence import _provider_usage

    return _provider_usage(provider, raw)


def _provider_native_error(provider: Any, raw: Mapping[str, Any]):
    from rasai.improvement_intelligence import _provider_native_error

    return _provider_native_error(provider, raw)


def _provider_extract(provider: Any, raw: Mapping[str, Any]):
    from rasai.improvement_intelligence import _provider_extract

    return _provider_extract(provider, raw)


def _http_diagnostic(provider: Any, exc: HTTPError):
    from rasai.m18_ai import ResponsesSemanticProvider, _diagnostic_from_http as core_diagnostic
    from rasai.provider_extensions import _diagnostic_from_http as extension_diagnostic

    return core_diagnostic(exc) if isinstance(provider, ResponsesSemanticProvider) else extension_diagnostic(exc)


def _candidate_call(
    provider: Any,
    *,
    body: bytes,
    timeout: float,
) -> tuple[Mapping[str, Any] | None, Any, Any, Any, int]:
    from rasai.m18_ai import AttemptStatus, ProviderDiagnostic, ProviderErrorClass

    started_perf = time.perf_counter()
    raw: Mapping[str, Any] | None = None
    usage = None
    diagnostic = None
    status = AttemptStatus.TECHNICAL_ERROR
    try:
        candidate = provider._transport(provider.endpoint, provider._headers(), body, timeout)
        if not isinstance(candidate, Mapping):
            diagnostic = ProviderDiagnostic(ProviderErrorClass.INVALID_RESPONSE)
        else:
            raw = candidate
            usage = _provider_usage(provider, raw)
            diagnostic = _provider_native_error(provider, raw)
            if diagnostic is None:
                status = AttemptStatus.SUCCESS
    except HTTPError as exc:
        diagnostic = _http_diagnostic(provider, exc)
    except TimeoutError:
        diagnostic = ProviderDiagnostic(ProviderErrorClass.TIMEOUT_ERROR)
    except (URLError, OSError):
        diagnostic = ProviderDiagnostic(ProviderErrorClass.NETWORK_ERROR)
    except Exception as exc:
        diagnostic = ProviderDiagnostic(
            ProviderErrorClass.UNKNOWN_PROVIDER_ERROR,
            error_type=type(exc).__name__,
        )
    duration_ms = max(0, int((time.perf_counter() - started_perf) * 1000))
    return raw, usage, diagnostic, status, duration_ms


def _attempt(
    provider: Any,
    *,
    index: int,
    started: datetime,
    duration_ms: int,
    status: Any,
    diagnostic: Any,
    usage: Any,
    request_hash: str,
    contract: str,
    url: str | None = None,
    snapshot_id: str | None = None,
    decision: str | None = None,
):
    from rasai.m18_ai import ProviderAttempt, estimate_cost

    finished = datetime.now(timezone.utc)
    estimated, currency, pricing_version = estimate_cost(
        str(provider.name), str(provider.model), usage, finished
    )
    return ProviderAttempt(
        provider=str(provider.name),
        model=str(provider.model),
        reasoning_profile=str(getattr(provider, "reasoning_profile", "PROVIDER_DEFAULT")),
        provider_rank=int(getattr(getattr(provider, "policy", None), "rank", 9999)),
        attempt_index=index,
        snapshot_id=snapshot_id,
        url=url,
        started_at=started,
        finished_at=finished,
        duration_ms=duration_ms,
        status=status,
        diagnostic=diagnostic,
        usage=usage,
        estimated_cost=estimated,
        cost_currency=currency,
        pricing_version=pricing_version,
        request_message_summary=f"contract={contract}",
        request_payload_hash=request_hash,
        provider_qualification=str(
            getattr(getattr(provider, "policy", None), "qualification", "PROVISIONAL")
        ),
        provider_reliability_score=getattr(
            getattr(provider, "policy", None), "reliability_score", None
        ),
        semantic_contract_version=contract,
        retry_eligible=False,
        decision=decision,
    )


def _install_search_competitive() -> None:
    from rasai.ai_resilience import DECISION_FALLBACK, DECISION_FALLBACK_SUCCESS, DECISION_STOP, DECISION_SUCCESS
    from rasai.m18_ai import AttemptStatus, ProviderDiagnostic, ProviderErrorClass
    from rasai.provider_registry import cli_provider_choices, get_provider_registration
    from rasai.provider_runtime_policy import build_semantic_provider, provider_reasoning_env
    from rasai.search_intelligence import competitive_ai as competitive

    class OrchestratedCompetitiveAiProvider:
        """Competitive contract over the canonical provider runtime."""

        def __init__(
            self,
            selection: str,
            *,
            model: str | None = None,
            reasoning_effort: str | None = None,
            timeout: float = 45.0,
        ) -> None:
            normalized = selection.strip().casefold()
            if timeout <= 0:
                raise ValueError("competitive AI timeout must be > 0")
            if normalized == "auto" and model:
                raise ValueError(
                    "--ai-model cannot be used with --ai-provider=auto; configure per-provider RASAI_*_MODEL variables"
                )
            environment = dict(os.environ)
            registration = get_provider_registration(normalized)
            if registration is not None and reasoning_effort:
                reasoning_env = provider_reasoning_env(registration.provider_name)
                if reasoning_env:
                    environment[reasoning_env] = reasoning_effort.strip().upper()
            self.runtime = build_semantic_provider(
                normalized,
                model_override=model if normalized not in {"auto", "none"} else None,
                env=environment,
            )
            _apply_timeout(self.runtime, timeout)
            self.timeout = timeout
            self.name = "AUTO" if normalized == "auto" else str(
                getattr(self.runtime, "name", normalized.upper())
            )
            self.calls = 0
            self._last_attempts: tuple[Any, ...] = ()
            self._history: list[Any] = []

        def consume_attempts(self) -> tuple[Any, ...]:
            items = self._last_attempts
            self._last_attempts = ()
            return items

        def attempt_history(self) -> tuple[Any, ...]:
            return tuple(self._history)

        def analyze(self, competitive_input: Any):
            instructions = (
                "Analyze only the supplied deterministic RASAI Search Intelligence evidence. "
                "Return content/search opportunities, not a ranking score. Never invent evidence_ids, "
                "facts, entities, competitor observations or causes. Every opportunity must cite at "
                "least one supplied evidence_id. Treat differences as correlational observations: "
                "never state or imply that a content difference caused a SERP position. "
                "For YMYL, obey ymyl_mode: ON means apply heightened caution; OFF means do not classify "
                "the page as YMYL; AUTO permits a cautious evidence-bound assessment. "
                "Recommendations may cover query intent, topic/entity coverage, information architecture, "
                "structured data, E-E-A-T/YMYL safeguards and SEO/AEO/GEO discoverability. "
                "Do not recommend deception, keyword stuffing, fake expertise, fake reviews or hidden text."
            )
            user_text = "Competitive evidence JSON:\n" + json.dumps(
                competitive_input.provider_payload(), ensure_ascii=False, separators=(",", ":")
            )
            hint = _token_hint(user_text, output_tokens=2600)
            candidates = _provider_candidates(
                self.runtime, hint, scope="COMPETITIVE_INTELLIGENCE"
            )
            if not candidates:
                state = (
                    competitive.CompetitiveAiState.NOT_CONFIGURED
                    if self.name in {"NONE", ""}
                    else competitive.CompetitiveAiState.UNAVAILABLE
                )
                reason = (
                    "COMPETITIVE_AI_DISABLED"
                    if state is competitive.CompetitiveAiState.NOT_CONFIGURED
                    else "AI_PROVIDER_CHAIN_EXHAUSTED"
                )
                return competitive.CompetitiveAiResult(state, reason=reason)

            coordinator = getattr(self.runtime, "coordinator", None)
            attempts: list[Any] = []
            fallback_from: str | None = None
            fallback_reason: str | None = None
            for index, provider in enumerate(candidates, 1):
                payload = _structured_payload(
                    provider,
                    schema_name="rasai_competitive_ai",
                    instructions=instructions,
                    user_text=user_text,
                    schema=competitive.competitive_ai_output_schema(),
                )
                body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
                request_hash = sha256(body).hexdigest()
                started = datetime.now(timezone.utc)
                self.calls += 1
                raw, usage, diagnostic, status, duration_ms = _candidate_call(
                    provider, body=body, timeout=self.timeout
                )
                assessment = None
                if status is AttemptStatus.SUCCESS and raw is not None:
                    try:
                        assessment = competitive.normalize_competitive_ai_payload(
                            _provider_extract(provider, raw),
                            allowed_evidence_ids=competitive_input.allowed_evidence_ids,
                            provider=str(provider.name),
                            model=str(provider.model),
                            provider_request_id=(
                                str(raw.get("id")) if raw.get("id") is not None else None
                            ),
                        )
                    except Exception as exc:
                        status = AttemptStatus.CONTRACT_ERROR
                        diagnostic = ProviderDiagnostic(
                            ProviderErrorClass.CONTRACT_ERROR,
                            error_type=type(exc).__name__,
                            error_code="COMPETITIVE_AI_OUTPUT_INVALID",
                        )
                decision = DECISION_STOP
                if assessment is not None:
                    decision = DECISION_FALLBACK_SUCCESS if fallback_from else DECISION_SUCCESS
                elif index < len(candidates):
                    decision = DECISION_FALLBACK
                attempt = _attempt(
                    provider,
                    index=index,
                    started=started,
                    duration_ms=duration_ms,
                    status=status,
                    diagnostic=diagnostic,
                    usage=usage,
                    request_hash=request_hash,
                    contract=competitive.COMPETITIVE_AI_CONTRACT_VERSION,
                    decision=decision,
                )
                if fallback_from:
                    attempt = replace(
                        attempt,
                        fallback_from_provider=fallback_from,
                        fallback_reason=fallback_reason,
                    )
                attempts.append(attempt)
                if coordinator is not None:
                    coordinator.record_attempt(attempt, scope="COMPETITIVE_INTELLIGENCE")
                if assessment is not None:
                    self._last_attempts = tuple(attempts)
                    self._history.extend(attempts)
                    return competitive.CompetitiveAiResult(
                        competitive.CompetitiveAiState.AVAILABLE, assessment=assessment
                    )
                fallback_from = str(provider.name)
                fallback_reason = (
                    diagnostic.reason if diagnostic is not None else "AI_PROVIDER_UNAVAILABLE"
                )

            self._last_attempts = tuple(attempts)
            self._history.extend(attempts)
            reason = fallback_reason or "AI_PROVIDER_CHAIN_EXHAUSTED"
            return competitive.CompetitiveAiResult(
                competitive.CompetitiveAiState.UNAVAILABLE,
                reason=f"COMPETITIVE_AI_PROVIDER_UNAVAILABLE:{reason}",
            )

    def build_provider(
        provider: str,
        *,
        fixture_path=None,
        model=None,
        reasoning_effort=None,
        timeout: float = 45.0,
    ):
        normalized = provider.strip().casefold()
        if normalized == "none":
            return competitive.NoneCompetitiveAiProvider()
        if normalized == "fixture":
            if fixture_path is None:
                raise ValueError("competitive AI fixture provider requires --ai-fixture")
            return competitive.FixtureCompetitiveAiProvider(fixture_path)
        return OrchestratedCompetitiveAiProvider(
            normalized,
            model=model,
            reasoning_effort=reasoning_effort,
            timeout=timeout,
        )

    competitive.OrchestratedCompetitiveAiProvider = OrchestratedCompetitiveAiProvider
    competitive.build_competitive_ai_provider = build_provider

    # The public Search CLI keeps the same switch name, but its values now come from
    # the canonical registry. Fixture remains test-only and is not a production provider.
    from rasai.search_intelligence import cli as search_cli

    search_cli.build_competitive_ai_provider = build_provider
    original_build_parser = search_cli.build_parser

    def build_parser():
        parser = original_build_parser()
        action = next(item for item in parser._actions if item.dest == "ai_provider")
        action.choices = tuple(dict.fromkeys((*cli_provider_choices(), "fixture")))
        action.help = (
            "AI selection from the canonical RASAi provider registry; AUTO reuses the standard "
            "cost-aware orchestration/quarantine policy. fixture is test-only."
        )
        reasoning = next(item for item in parser._actions if item.dest == "ai_reasoning_effort")
        reasoning.help = "reasoning override for an explicit AI provider; AUTO uses each provider configuration"
        return parser

    def validate_args(parser, args, config):
        del parser
        if args.depth <= 0:
            raise ValueError("--depth must be greater than zero")
        if args.max_content_pages < 0:
            raise ValueError("--max-content-pages must be >= 0")
        if args.max_content_pages > config.max_competitors:
            raise ValueError(
                f"--max-content-pages {args.max_content_pages} exceeds configured max_competitors {config.max_competitors}"
            )
        if args.customer_url and not args.compare_content:
            raise ValueError("--customer-url requires --compare-content")
        if args.compare_content and len(args.query) > 1 and args.customer_url:
            raise ValueError("--customer-url with --compare-content is supported for one query at a time")
        if args.ai_competitive and not args.compare_content:
            raise ValueError("--ai-competitive requires --compare-content")
        if args.ai_timeout <= 0:
            raise ValueError("--ai-timeout must be greater than zero")
        if args.ai_fixture and not args.ai_competitive:
            raise ValueError("--ai-fixture requires --ai-competitive")
        if args.ai_provider and not args.ai_competitive:
            raise ValueError("--ai-provider requires --ai-competitive")
        if config.mode == "live":
            search_cli.validate_live_provider_engine(config.provider, args.engine)
        provider_name = str(args.ai_provider or "none").strip().casefold()
        allowed = set(cli_provider_choices()) | {"fixture"}
        if provider_name not in allowed:
            raise ValueError("unsupported Competitive AI provider selection")
        if provider_name == "fixture" and args.ai_competitive and args.ai_fixture is None:
            raise ValueError("--ai-provider fixture requires --ai-fixture")
        if provider_name == "auto" and args.ai_model:
            raise ValueError("--ai-model cannot be used with --ai-provider=auto")
        if provider_name == "auto" and args.ai_reasoning_effort:
            raise ValueError(
                "--ai-reasoning-effort cannot be used with --ai-provider=auto; configure per-provider reasoning"
            )
        return provider_name

    search_cli.build_parser = build_parser
    search_cli._validate_args = validate_args

    from rasai.search_intelligence import monitoring_cli

    original_monitor_parser = monitoring_cli.build_parser

    def monitor_parser():
        parser = original_monitor_parser()
        sub = next(item for item in parser._actions if getattr(item, "choices", None))
        query_parser = sub.choices["query"]
        qsub = next(item for item in query_parser._actions if getattr(item, "choices", None))
        add_parser = qsub.choices["add"]
        action = next(item for item in add_parser._actions if item.dest == "ai_provider")
        action.choices = tuple(dict.fromkeys((*cli_provider_choices(), "fixture")))
        return parser

    monitoring_cli.build_parser = monitor_parser


def _install_improvement_runtime() -> None:
    from rasai.ai_resilience import DECISION_FALLBACK, DECISION_FALLBACK_SUCCESS, DECISION_STOP, DECISION_SUCCESS
    from rasai.m18_ai import AttemptStatus, ProviderDiagnostic, ProviderErrorClass
    from rasai.provider_registry import get_provider_registration
    from rasai.provider_runtime_policy import build_semantic_provider, provider_reasoning_env
    from rasai import improvement_intelligence as improvement

    original_validate = improvement.ImprovementConfig.validate

    def validate(config, env: Mapping[str, str] | None = None):
        environment = os.environ if env is None else env
        domains = improvement.parse_domains(config.domains)
        if config.max_recommendations < 1 or config.max_recommendations > 100:
            raise ValueError("Improvement Intelligence max_recommendations deve estar entre 1 e 100")
        if not math.isfinite(float(config.timeout_seconds)) or float(config.timeout_seconds) <= 0:
            raise ValueError("Improvement Intelligence timeout deve ser > 0")
        language = improvement.validate_analysis_language(config.language)
        provider = str(config.provider or "").strip().casefold()
        model = str(config.model or "").strip()
        reasoning = str(config.reasoning or "").strip().upper()
        if not config.enabled:
            return replace(
                config,
                provider=provider,
                model=model,
                reasoning=reasoning,
                domains=domains,
                language=language,
            )
        # Provider selection is now owned by the primary AI configuration. Empty here
        # means the final runtime handoff has not happened yet, not a second config error.
        if provider in {"", "none"}:
            return replace(
                config,
                provider=provider,
                model="",
                reasoning="",
                domains=domains,
                language=language,
            )
        if provider == "auto":
            return replace(
                config,
                provider="auto",
                model="",
                reasoning="",
                domains=domains,
                language=language,
            )
        registration = get_provider_registration(provider)
        if registration is None:
            raise ValueError(f"provider principal de IA desconhecido: {provider}")
        if not (environment.get(registration.key_env) or "").strip():
            raise ValueError(
                f"Improvement Intelligence requer a credencial principal {registration.key_env} para {registration.display_name}"
            )
        effective_model = model or registration.public_default_model
        if effective_model not in registration.supported_models:
            raise ValueError(
                f"modelo {effective_model!r} não é suportado por {registration.display_name}"
            )
        effective_reasoning = reasoning
        if effective_reasoning and effective_reasoning not in registration.reasoning_values:
            raise ValueError(
                f"esforço {effective_reasoning!r} não é suportado por {registration.display_name}"
            )
        return replace(
            config,
            provider=registration.id,
            model=effective_model,
            reasoning=effective_reasoning,
            domains=domains,
            language=language,
        )

    @classmethod
    def from_environment(cls, env: Mapping[str, str] | None = None):
        environment = os.environ if env is None else env
        try:
            maximum = int((environment.get(improvement.MAX_RECOMMENDATIONS_ENV) or "30").strip())
            timeout = float((environment.get(improvement.TIMEOUT_ENV) or "240").strip())
        except ValueError as exc:
            raise ValueError("Improvement Intelligence possui limite/timeout inválido") from exc
        primary = _PRIMARY_AI_CONTEXT.get()
        provider, model, reasoning = primary if primary is not None else ("", "", "")
        return cls(
            enabled=improvement._truthy(environment.get(improvement.ENABLED_ENV)),
            provider=provider,
            model=model,
            reasoning=reasoning,
            domains=improvement.parse_domains(
                environment.get(improvement.DOMAINS_ENV) or improvement.DEFAULT_DOMAINS
            ),
            max_recommendations=maximum,
            timeout_seconds=timeout,
            language=environment.get(improvement.AI_ANALYSIS_LANGUAGE_ENV, "auto"),
        ).validate(environment)

    def build_provider(config, env: Mapping[str, str] | None = None):
        environment = dict(os.environ if env is None else env)
        selection = str(config.provider or "none").strip().casefold()
        registration = get_provider_registration(selection)
        if registration is not None and config.reasoning:
            reasoning_env = provider_reasoning_env(registration.provider_name)
            if reasoning_env:
                environment[reasoning_env] = config.reasoning
        runtime = build_semantic_provider(
            selection,
            model_override=(config.model or None) if selection not in {"auto", "none", ""} else None,
            env=environment,
        )
        _apply_timeout(runtime, float(config.timeout_seconds))
        return runtime

    def ai_analyze(
        *,
        audit_id,
        workspace,
        context,
        config,
        findings,
        evidence_context,
        language,
        progress=None,
    ):
        runtime = build_provider(config)
        schema = improvement._schema(findings, config.max_recommendations)
        request_context = {
            "contract_version": improvement.CONTRACT_VERSION,
            "target": {
                "url": context.url,
                "input_url": context.input_url,
                "device_snapshot_used": context.device,
                "market": context.market,
            },
            "selected_domains": list(config.domains),
            "page": {
                "title": context.title,
                "description": context.description,
                "canonical": context.canonical,
            },
            "findings": findings,
            "supporting_context": evidence_context,
            "governance": {
                "sari_score_impact": "NONE",
                "security_mode": "PASSIVE_ONLY",
                "ranking_causality": "FORBIDDEN",
                "human_review_required": True,
            },
        }
        user_text = "Persisted RASAi evidence for one URL:\n" + json.dumps(
            request_context, ensure_ascii=False, default=str
        )
        instructions = improvement._instructions(language, config.domains)
        hint = _token_hint(
            user_text,
            output_tokens=min(8000, 1600 + config.max_recommendations * 180),
        )
        candidates = _provider_candidates(
            runtime, hint, scope="IMPROVEMENT_INTELLIGENCE"
        )
        if not candidates:
            return "", [], (
                "AI_NOT_CONFIGURED" if str(config.provider or "").casefold() in {"", "none"}
                else "AI_PROVIDER_CHAIN_EXHAUSTED"
            )
        coordinator = getattr(runtime, "coordinator", None)
        last_reason = None
        fallback_from = None
        fallback_reason = None
        for ordinal, provider in enumerate(candidates, 1):
            if progress:
                progress(
                    "AI_ANALYSIS",
                    min(92.0, 72.0 + ordinal * 6.0),
                    f"consultando {provider.name}/{provider.model}; candidato {ordinal}/{len(candidates)}",
                )
            payload = _structured_payload(
                provider,
                schema_name="rasai_improvement_intelligence",
                instructions=instructions,
                user_text=user_text,
                schema=schema,
            )
            body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            request_hash = sha256(body).hexdigest()
            started = datetime.now(timezone.utc)
            raw, usage, diagnostic, status, duration_ms = _candidate_call(
                provider, body=body, timeout=float(config.timeout_seconds)
            )
            ai_summary = ""
            recommendations: list[dict[str, Any]] = []
            if status is AttemptStatus.SUCCESS and raw is not None:
                try:
                    ai_summary, recommendations = improvement._validate_ai_payload(
                        _provider_extract(provider, raw), findings, config.max_recommendations
                    )
                except Exception as exc:
                    status = AttemptStatus.CONTRACT_ERROR
                    diagnostic = ProviderDiagnostic(
                        ProviderErrorClass.CONTRACT_ERROR,
                        error_type=type(exc).__name__,
                        error_code="IMPROVEMENT_OUTPUT_INVALID",
                    )
            success = status is AttemptStatus.SUCCESS and diagnostic is None
            decision = DECISION_STOP
            if success:
                decision = DECISION_FALLBACK_SUCCESS if fallback_from else DECISION_SUCCESS
            elif ordinal < len(candidates):
                decision = DECISION_FALLBACK
            attempt = _attempt(
                provider,
                index=ordinal,
                started=started,
                duration_ms=duration_ms,
                status=status,
                diagnostic=diagnostic,
                usage=usage,
                request_hash=request_hash,
                contract=improvement.CONTRACT_VERSION,
                url=context.url,
                snapshot_id=context.snapshot_id,
                decision=decision,
            )
            if fallback_from:
                attempt = replace(
                    attempt,
                    fallback_from_provider=fallback_from,
                    fallback_reason=fallback_reason,
                )
            improvement._persist_attempt(workspace, audit_id, context, attempt)
            if coordinator is not None:
                coordinator.record_attempt(
                    attempt,
                    page_url=context.url,
                    scope="IMPROVEMENT_INTELLIGENCE",
                )
            if success:
                return ai_summary, recommendations, None
            last_reason = diagnostic.reason if diagnostic is not None else "AI_PROVIDER_UNAVAILABLE"
            fallback_from = str(provider.name)
            fallback_reason = last_reason
        return "", [], last_reason or "AI_PROVIDER_CHAIN_EXHAUSTED"

    improvement.ImprovementConfig.validate = validate
    improvement.ImprovementConfig.from_environment = from_environment
    improvement._build_provider = build_provider
    improvement._ai_analyze = ai_analyze

    # Improvement finalization receives the already computed primary routing snapshot.
    # Make it the sole source of provider selection for env-driven/SaaS execution.
    from rasai import improvement_intelligence_runtime as runtime_module

    original_install_completion = runtime_module._install_report_completion

    def install_report_completion():
        original_install_completion()
        from rasai import report_completion

        current = report_completion.finalize_audit_report_site
        if getattr(current, "_rasai_primary_ai_context", False):
            return

        def finalize_with_primary_ai(
            *, audit_id, workspace, context_interpretations=(), routing_snapshot=None
        ):
            primary = _selection_from_snapshot(routing_snapshot)
            token = _PRIMARY_AI_CONTEXT.set(primary)
            try:
                return current(
                    audit_id=audit_id,
                    workspace=workspace,
                    context_interpretations=context_interpretations,
                    routing_snapshot=routing_snapshot,
                )
            finally:
                _PRIMARY_AI_CONTEXT.reset(token)

        finalize_with_primary_ai._rasai_primary_ai_context = True
        finalize_with_primary_ai._rasai_original = current
        report_completion.finalize_audit_report_site = finalize_with_primary_ai

    runtime_module._install_report_completion = install_report_completion


def _selection_from_snapshot(snapshot: Mapping[str, Any] | None) -> tuple[str, str, str]:
    if not isinstance(snapshot, Mapping) or not snapshot.get("enabled"):
        return ("none", "", "")
    if str(snapshot.get("strategy") or "").upper() == "AUTO":
        return ("auto", "", "")
    provider_name = str(snapshot.get("initial_provider") or "").strip()
    if not provider_name:
        return ("none", "", "")
    from rasai.provider_registry import get_provider_registration

    registration = get_provider_registration(provider_name)
    selection = registration.id if registration is not None else provider_name.casefold()
    return (
        selection,
        str(snapshot.get("initial_model") or ""),
        "",
    )


def _install_improvement_saas() -> None:
    from rasai import improvement_intelligence_saas as saas
    from rasai.improvement_intelligence import DEFAULT_DOMAINS, parse_domains, validate_analysis_language

    saas._FIELDS = frozenset(
        {
            "improvement_intelligence",
            "improvement_domains",
            "improvement_max_recommendations",
            "improvement_ai_timeout_seconds",
            "ai_analysis_language",
        }
    )

    def validate_extension(payload, normalized):
        enabled = saas._bool(payload, "improvement_intelligence", False)
        language = validate_analysis_language(
            saas._text(payload, "ai_analysis_language", "auto") or "auto"
        )
        raw_domains = payload.get("improvement_domains", ",".join(DEFAULT_DOMAINS))
        if not isinstance(raw_domains, str):
            raise ValueError("AUDIT payload field improvement_domains must be comma-separated text")
        domains = parse_domains(raw_domains)
        maximum = saas._positive_int(
            payload, "improvement_max_recommendations", 30, maximum=100
        )
        timeout = saas._positive_number(
            payload, "improvement_ai_timeout_seconds", 240.0
        )
        if enabled:
            urls = normalized.get("urls")
            if not isinstance(urls, list) or len(urls) != 1 or not str(urls[0]).strip():
                raise ValueError(
                    "Improvement Intelligence requires exactly one explicit URL in AUDIT payload urls"
                )
            selection = str(normalized.get("ai_provider") or "none").casefold()
            if selection == "none":
                raise ValueError(
                    "Improvement Intelligence requires the primary AUDIT ai_provider to be enabled"
                )
        normalized.update(
            {
                "improvement_intelligence": enabled,
                "improvement_domains": ",".join(domains),
                "improvement_max_recommendations": maximum,
                "improvement_ai_timeout_seconds": timeout,
                "ai_analysis_language": language,
            }
        )
        return normalized

    saas._validate_extension = validate_extension

    # Replace install so job options/defaults/environment expose only feature-specific
    # controls; provider/model/reasoning remain the canonical AUDIT fields.
    original_install = saas.install

    def install():
        if getattr(saas, "_rasai_primary_ai_saas_installed", False):
            return
        original_install()
        from rasai import audit_execution_contract as contract

        specialized = {
            "improvement_ai_provider",
            "improvement_ai_model",
            "improvement_ai_reasoning",
        }
        contract.AUDIT_JOB_FIELDS = frozenset(
            item for item in contract.AUDIT_JOB_FIELDS if item not in specialized
        )
        old_options = contract.audit_job_options
        old_defaults = contract.audit_job_defaults
        old_normalize = contract.normalize_audit_job_payload
        old_environment = contract.audit_job_environment_overrides

        def options():
            return tuple(item for item in old_options() if item.name not in specialized)

        def defaults():
            values = dict(old_defaults())
            for key in specialized:
                values.pop(key, None)
            return values

        def normalize(payload):
            if specialized.intersection(payload):
                raise ValueError(
                    "Improvement Intelligence uses the primary ai_provider/ai_model/ai_reasoning fields; specialized AI fields are not supported"
                )
            return old_normalize(payload)

        def environment(payload):
            values = dict(old_environment(payload))
            for name in (
                "RASAI_IMPROVEMENT_AI_PROVIDER",
                "RASAI_IMPROVEMENT_AI_MODEL",
                "RASAI_IMPROVEMENT_AI_REASONING",
            ):
                values.pop(name, None)
            return values

        contract.audit_job_options = options
        contract.audit_job_defaults = defaults
        contract.normalize_audit_job_payload = normalize
        contract.audit_job_environment_overrides = environment
        saas._rasai_primary_ai_saas_installed = True

    saas.install = install


def _install_improvement_console() -> None:
    from rasai import improvement_intelligence_console as console
    from rasai.improvement_intelligence import DEFAULT_DOMAINS, DOMAIN_LABELS, ImprovementConfig, parse_domains

    def config_from_state(state):
        selection = str(getattr(state, "ai_provider", "none") or "none").casefold()
        model = str(getattr(state, "ai_model", "") or "") if selection != "auto" else ""
        reasoning = str(getattr(state, "ai_reasoning", "") or "") if selection != "auto" else ""
        return ImprovementConfig(
            enabled=bool(getattr(state, "improvement_enabled", False)),
            provider=selection,
            model=model,
            reasoning=reasoning,
            domains=tuple(getattr(state, "improvement_domains", DEFAULT_DOMAINS)),
            max_recommendations=int(getattr(state, "improvement_max_recommendations", 30)),
            timeout_seconds=float(getattr(state, "improvement_timeout", 240.0)),
            language=(os.environ.get(console.AI_ANALYSIS_LANGUAGE_ENV) or "auto"),
        ).validate()

    def single_url_ready(state):
        if not bool(getattr(state, "improvement_enabled", False)):
            return True, "análise profunda desabilitada"
        if str(getattr(state, "input_mode", "url")) != "url":
            return False, "Análise profunda exige Entrada=URL única"
        if not str(getattr(state, "target", "")).strip():
            return False, "Análise profunda exige uma URL explícita"
        selection = str(getattr(state, "ai_provider", "none") or "none").casefold()
        if selection == "none":
            return False, "Análise profunda usa a IA principal; configure uma IA ou AUTO"
        try:
            config_from_state(state)
        except ValueError as exc:
            return False, str(exc)
        return True, f"análise profunda pronta; IA principal={selection.upper()}"

    def configure(console_module, state):
        console_module.render_header(state)
        print("ANÁLISE PROFUNDA E MELHORIAS\n")
        print("A análise usa exclusivamente a configuração principal de IA do RASAi.")
        print("Se a IA principal estiver em AUTO, são reutilizados ranking por custo, quarentena, circuit breaker e fallback do core.")
        print("O contrato desta feature continua evidence-bound, advisory/non-scoring e restrito a uma URL explícita.\n")
        current = bool(getattr(state, "improvement_enabled", False))
        raw = input(f"Habilitar análise profunda? [{'S/n' if current else 's/N'}]: ").strip().casefold()
        enabled = current if not raw else raw in {"s", "sim", "y", "yes", "1", "true", "on"}
        if not enabled:
            state.improvement_enabled = False
            state.error = ""
            return
        if state.input_mode != "url":
            state.error = "Análise profunda só pode ser habilitada com Entrada=URL única"
            return
        if str(getattr(state, "ai_provider", "none") or "none").casefold() == "none":
            state.error = "Configure a IA principal (provider explícito ou AUTO) antes de habilitar a análise profunda"
            return
        print(f"IA principal: {str(getattr(state, 'ai_provider', 'none')).upper()}")
        print("\nDomínios disponíveis:")
        for index, domain in enumerate(DEFAULT_DOMAINS, 1):
            marker = "*" if domain in set(getattr(state, "improvement_domains", DEFAULT_DOMAINS)) else " "
            print(f" {index:2d}. [{marker}] {DOMAIN_LABELS[domain]} ({domain})")
        raw_domains = input("Selecione números separados por vírgula [ENTER=manter; 'todos'=todos]: ").strip().casefold()
        if raw_domains:
            if raw_domains in {"todos", "all", "*"}:
                state.improvement_domains = DEFAULT_DOMAINS
            else:
                selected = []
                for token in raw_domains.replace(";", ",").split(","):
                    index = int(token.strip())
                    if index < 1 or index > len(DEFAULT_DOMAINS):
                        raise ValueError("domínio fora da lista")
                    selected.append(DEFAULT_DOMAINS[index - 1])
                state.improvement_domains = tuple(dict.fromkeys(selected))
                parse_domains(state.improvement_domains)
        maximum = input(
            f"Máximo de recomendações [{state.improvement_max_recommendations}]: "
        ).strip()
        if maximum:
            value = int(maximum)
            if value < 1 or value > 100:
                raise ValueError("máximo de recomendações deve estar entre 1 e 100")
            state.improvement_max_recommendations = value
        timeout = input(
            f"Timeout da chamada profunda em segundos [{state.improvement_timeout:g}]: "
        ).strip()
        if timeout:
            value = float(timeout)
            if value <= 0:
                raise ValueError("timeout deve ser > 0")
            state.improvement_timeout = value
        state.improvement_enabled = True
        config_from_state(state)
        state.error = ""

    def render_menu(console_module, state):
        from rasai.console_ui import DIM, GREEN, RED, paint

        enabled = bool(getattr(state, "improvement_enabled", False))
        selection = str(getattr(state, "ai_provider", "none") or "none").upper()
        domains = len(tuple(getattr(state, "improvement_domains", DEFAULT_DOMAINS)))
        ready, reason = single_url_ready(state)
        if enabled:
            state_text = paint("ON", GREEN if ready else RED, bold=True)
            detail = (
                f"IA principal={selection} | domínios={domains} | "
                f"idioma IA={os.environ.get(console.AI_ANALYSIS_LANGUAGE_ENV, 'auto')} | orquestração=core"
            )
            if not ready:
                detail += " | " + paint(reason, RED, bold=True)
        else:
            state_text = paint("OFF", DIM)
            detail = "somente URL única; usa IA principal; advisory/non-scoring"
        print(f"13. Análise profunda URL  : {state_text} | {detail}")

    console._config_from_state = config_from_state
    console._single_url_ready = single_url_ready
    console.configure = configure
    console._render_menu_extension = render_menu


def _install_console_environment_contract() -> None:
    # Remove feature-specific provider selections from the guided environment catalog.
    try:
        from rasai import console_environment
    except Exception:
        return
    obsolete = {
        "RASAI_SEARCH_AI_PROVIDER",
        "RASAI_IMPROVEMENT_AI_PROVIDER",
        "RASAI_IMPROVEMENT_AI_MODEL",
        "RASAI_IMPROVEMENT_AI_REASONING",
    }
    console_environment.ENV_NAMES = tuple(
        name for name in console_environment.ENV_NAMES if name not in obsolete
    )
    console_environment.SPECS = tuple(
        spec for spec in console_environment.SPECS if spec.name not in obsolete
    )
    console_environment.SPEC_BY_NAME = {
        spec.name: spec for spec in console_environment.SPECS
    }

    from rasai import runtime_completion_extensions as completion

    def install_improvement_environment_contract():
        from rasai import console_environment as base
        from rasai.improvement_intelligence import DEFAULT_DOMAINS, parse_domains, validate_analysis_language

        if getattr(base, "_rasai_improvement_environment_current", False):
            return
        original_fixed_specs = base._fixed_specs
        original_validate = base._validate
        names = (
            completion._AI_ANALYSIS_LANGUAGE_ENV,
            completion._IMPROVEMENT_ENABLED_ENV,
            completion._IMPROVEMENT_DOMAINS_ENV,
            completion._IMPROVEMENT_MAX_RECOMMENDATIONS_ENV,
            completion._IMPROVEMENT_TIMEOUT_ENV,
        )
        for name in names:
            if name not in base.ENV_NAMES:
                base.ENV_NAMES = (*base.ENV_NAMES, name)
        if "IA - análise profunda" not in base.CATEGORIES:
            categories = list(base.CATEGORIES)
            insert_at = categories.index("IA - contexto editorial / YMYL") + 1
            categories.insert(insert_at, "IA - análise profunda")
            base.CATEGORIES = tuple(categories)
        domains_csv = ",".join(DEFAULT_DOMAINS)

        def fixed_specs():
            items = [spec for spec in original_fixed_specs() if spec.name not in obsolete]
            known = {item.name for item in items}

            def add(spec):
                if spec.name not in known:
                    items.append(spec)
                    known.add(spec.name)

            add(base.EnvironmentSpec(
                completion._AI_ANALYSIS_LANGUAGE_ENV,
                "IA - contexto editorial / YMYL",
                "Idioma preferencial das explicações e sugestões geradas por IA; auto usa o idioma da auditoria.",
                "tag BCP-47 ou auto",
                default="auto",
                impact="Altera somente idioma preferencial de leitura/resposta.",
                example="RASAI_AI_ANALYSIS_LANGUAGE=pt-BR",
                source="docs/IMPROVEMENT_INTELLIGENCE.md",
            ))
            add(base.EnvironmentSpec(
                completion._IMPROVEMENT_ENABLED_ENV,
                "IA - análise profunda",
                "Habilita Improvement Intelligence para uma única URL; usa a seleção principal de IA do RASAi.",
                "booleano",
                ("true", "false"),
                "false",
                required_when="Requer IA principal habilitada (provider explícito ou AUTO).",
                impact="Quando true, pode gerar chamadas adicionais de IA, tokens, latência e custo.",
                source="docs/IMPROVEMENT_INTELLIGENCE.md",
            ))
            add(base.EnvironmentSpec(
                completion._IMPROVEMENT_DOMAINS_ENV,
                "IA - análise profunda",
                "Domínios correlacionados pela análise profunda.",
                "lista CSV",
                tuple(DEFAULT_DOMAINS),
                domains_csv,
                impact="Mais domínios podem aumentar contexto enviado e tokens.",
                source="docs/IMPROVEMENT_INTELLIGENCE.md",
            ))
            add(base.EnvironmentSpec(
                completion._IMPROVEMENT_MAX_RECOMMENDATIONS_ENV,
                "IA - análise profunda",
                "Teto de recomendações materializadas.",
                "inteiro 1..100",
                default="30",
                impact="Limite maior pode elevar output tokens e custo.",
                source="docs/IMPROVEMENT_INTELLIGENCE.md",
            ))
            add(base.EnvironmentSpec(
                completion._IMPROVEMENT_TIMEOUT_ENV,
                "IA - análise profunda",
                "Timeout por chamada estruturada desta análise.",
                "número > 0 (segundos)",
                default="240",
                impact="Timeout maior amplia o tempo máximo de espera; não altera a política de orquestração.",
                source="docs/IMPROVEMENT_INTELLIGENCE.md",
            ))
            return tuple(items)

        def validate(name, raw):
            if name not in names:
                return original_validate(name, raw)
            value = raw.strip()
            if not value:
                raise ValueError("valor vazio; remova a variável em vez de gravar vazio")
            if name == completion._AI_ANALYSIS_LANGUAGE_ENV:
                return validate_analysis_language(value)
            if name == completion._IMPROVEMENT_ENABLED_ENV:
                normalized = value.casefold()
                if normalized not in {"true", "false", "1", "0", "yes", "no", "on", "off"}:
                    raise ValueError("use true/false")
                return normalized
            if name == completion._IMPROVEMENT_DOMAINS_ENV:
                return ",".join(parse_domains(value))
            if name == completion._IMPROVEMENT_MAX_RECOMMENDATIONS_ENV:
                parsed = int(value)
                if parsed < 1 or parsed > 100:
                    raise ValueError("use inteiro entre 1 e 100")
                return str(parsed)
            parsed = float(value)
            if parsed <= 0:
                raise ValueError("use número > 0")
            return f"{parsed:g}"

        base._fixed_specs = fixed_specs
        base._validate = validate
        base.SPECS = base.environment_specs()
        base.SPEC_BY_NAME = {spec.name: spec for spec in base.SPECS}
        try:
            from rasai import console_provider_environment
            console_provider_environment.refresh_specs()
        except Exception:
            pass
        base._rasai_improvement_environment_current = True

    completion._install_improvement_environment_contract = install_improvement_environment_contract


def _install_source_quality_support() -> None:
    from rasai.m18_ai import AttemptStatus, ProviderDiagnostic, ProviderErrorClass, ResponsesSemanticProvider
    from rasai.provider_extensions import IsolatedStructuredSemanticProvider
    from rasai import source_quality_ai

    original_call = source_quality_ai._call

    def supported(candidate: Any) -> bool:
        return isinstance(candidate, (ResponsesSemanticProvider, IsolatedStructuredSemanticProvider))

    def candidates(provider: Any):
        routed = getattr(provider, "providers", None)
        items = routed if isinstance(routed, tuple) else (provider,)
        return tuple(
            item
            for item in items
            if supported(item) and bool(getattr(item, "api_key", None))
        )

    def call(candidate, assessment, page_row, *, attempt_index: int):
        if isinstance(candidate, ResponsesSemanticProvider):
            return original_call(candidate, assessment, page_row, attempt_index=attempt_index)
        schema = source_quality_ai._schema()
        instructions = (
            "Você é um analista técnico de infraestrutura web. Responda em português do Brasil e somente em JSON. "
            "Use exclusivamente os fatos fornecidos. A classificação técnica determinística do RASAi é soberana: "
            "não transforme erro TLS/DNS/protocolo em comportamento normal e nunca recomende desabilitar validação TLS. "
            "Explique a causa provável, a cadeia de redirecionamentos e ações de correção para um analista humano. "
            "Um redirecionamento HTTP bem-sucedido pode ser intencional; quando a intenção de negócio não estiver nas "
            "evidências, marque que requer validação humana. Não invente detalhes do certificado, CDN, proxy ou servidor."
        )
        facts = {
            "deterministic_contract": "SOURCE-QUALITY-1",
            "all_pages_hard_blocked": assessment.all_pages_hard_blocked,
            "hard_blocker_kinds": list(assessment.hard_blocker_kinds),
            "issues": [item.as_dict() for item in assessment.issues],
        }
        user_text = "Evidências técnicas persistidas:\n" + json.dumps(
            facts, ensure_ascii=False, separators=(",", ":")
        )
        payload = _structured_payload(
            candidate,
            schema_name="rasai_source_quality",
            instructions=instructions,
            user_text=user_text,
            schema=schema,
        )
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        request_hash = sha256(body).hexdigest()
        started = datetime.now(timezone.utc)
        raw, usage, diagnostic, status, duration_ms = _candidate_call(
            candidate, body=body, timeout=float(candidate.timeout)
        )
        explanation = None
        if status is AttemptStatus.SUCCESS and raw is not None:
            try:
                explanation = source_quality_ai._validate_explanation(
                    _provider_extract(candidate, raw)
                )
            except Exception as exc:
                status = AttemptStatus.CONTRACT_ERROR
                diagnostic = ProviderDiagnostic(
                    ProviderErrorClass.CONTRACT_ERROR,
                    error_type=type(exc).__name__,
                )
        attempt = _attempt(
            candidate,
            index=attempt_index,
            started=started,
            duration_ms=duration_ms,
            status=status,
            diagnostic=diagnostic,
            usage=usage,
            request_hash=request_hash,
            contract=source_quality_ai.CONTRACT_VERSION,
            url=str(page_row["url"]),
            snapshot_id=str(page_row["snapshot_id"]),
        )
        if status is AttemptStatus.SUCCESS and explanation is not None:
            return (
                source_quality_ai.SourceQualityAiResult(
                    state=source_quality_ai.ProviderState.AVAILABLE,
                    provider=str(candidate.name),
                    model=str(candidate.model),
                    explanation=explanation,
                ),
                attempt,
            )
        return (
            source_quality_ai.SourceQualityAiResult(
                state=source_quality_ai.ProviderState.UNAVAILABLE,
                provider=str(candidate.name),
                model=str(candidate.model),
                reason=(diagnostic.reason if diagnostic is not None else "SOURCE_QUALITY_AI_UNAVAILABLE"),
            ),
            attempt,
        )

    source_quality_ai._supported_candidate = supported
    source_quality_ai._candidates = candidates
    source_quality_ai._call = call

    # Replace only the specialist hook glue. Ordering/quarantine/circuit-breaker remain
    # owned by DynamicProviderRoutingSession/AiExecutionCoordinator unchanged.
    from rasai import dynamic_ai_routing

    def install_source_quality_hooks():
        if dynamic_ai_routing._SOURCE_QUALITY_HOOKS_INSTALLED:
            return
        source_quality_ai_module = source_quality_ai
        base_call = source_quality_ai_module._call

        def routed_candidates(provider: Any):
            if isinstance(provider, dynamic_ai_routing.DynamicProviderRoutingSession):
                return tuple(
                    item
                    for item in provider.ordered_candidates_for_need(scope="SOURCE_QUALITY")
                    if supported(item) and bool(getattr(item, "api_key", None))
                )
            return candidates(provider)

        def routed_call(candidate: Any, assessment: Any, page_row: Mapping[str, Any], *, attempt_index: int):
            result, attempt = base_call(
                candidate, assessment, page_row, attempt_index=attempt_index
            )
            attempt = dynamic_ai_routing._price_auto_attempt(attempt)
            coordinator = getattr(candidate, "_rasai_execution_coordinator", None)
            if isinstance(coordinator, dynamic_ai_routing.AiExecutionCoordinator):
                coordinator.record_attempt(
                    attempt,
                    page_url=str(attempt.url or ""),
                    scope="SOURCE_QUALITY",
                )
            return result, attempt

        source_quality_ai_module._candidates = routed_candidates
        source_quality_ai_module._call = routed_call
        dynamic_ai_routing._SOURCE_QUALITY_HOOKS_INSTALLED = True

    dynamic_ai_routing._install_source_quality_hooks = install_source_quality_hooks


def install_ai_orchestration_unification() -> None:
    """Install provider-selection unification without changing the core router policy."""
    global _INSTALLED
    if _INSTALLED:
        return
    _install_improvement_runtime()
    _install_improvement_saas()
    _install_improvement_console()
    _install_console_environment_contract()
    _install_source_quality_support()
    _install_search_competitive()
    _INSTALLED = True
