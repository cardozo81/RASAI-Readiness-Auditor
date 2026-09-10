"""Public runtime defaults and execution-wide AI provider selection policy.

Explicit provider selections keep provider-specific retry semantics. AUTO builds every
configured registry provider that is not explicitly excluded by the user, uses
round-robin routing, and shares one execution coordinator across semantic analysis,
remediation and compatible specialist AI calls.
"""
from __future__ import annotations

from types import MethodType
import os
from typing import Any, Mapping, MutableMapping

from rasai.ai_exchange_log import AiExchangeRecorder
from rasai.ai_execution_state import clear_current_ai_execution, set_current_ai_execution
from rasai.content_context import configured_content_analysis_context
from rasai.dynamic_ai_routing import (
    DynamicProviderRoutingSession,
    build_dynamic_content_remediation_router,
    install_dynamic_specialist_hooks,
    prepare_provider_for_execution,
)
from rasai.provider_extensions import (
    AnthropicProvider,
    GeminiProvider,
    IsolatedStructuredSemanticProvider,
    QwenProvider,
    XAIProvider,
    build_semantic_provider as _build_semantic_provider,
)
from rasai.provider_extensions_m20 import ExtensionContentRemediationProvider
from rasai.provider_registry import get_provider_registration, provider_registrations
from rasai.provider_wire_schema import project_provider_request_body

SIMPLE_DEFAULT_MODELS: dict[str, str] = {
    "OPENAI": "gpt-5.6-luna",
    "DEEPSEEK": "deepseek-v4-flash",
    "MIMO": "mimo-v2.5",
    "XAI": "grok-4.6",
    "QWEN": "qwen3.8-flash",
    "GEMINI": "gemini-3.8-flash",
    "ANTHROPIC": "claude-sonnet-5",
}
LOWEST_REASONING: dict[str, str] = {
    "OPENAI": "NONE", "DEEPSEEK": "NONE", "MIMO": "NONE", "XAI": "LOW",
    "QWEN": "PROVIDER_DEFAULT", "GEMINI": "LOW", "ANTHROPIC": "LOW",
}
EXTENSION_REASONING_ENV: dict[str, str] = {
    "XAI": "RASAI_XAI_REASONING_EFFORT",
    "GEMINI": "RASAI_GEMINI_REASONING_EFFORT",
    "ANTHROPIC": "RASAI_ANTHROPIC_REASONING_EFFORT",
}
REASONING_OPTIONS: dict[str, tuple[str, ...]] = {
    "OPENAI": ("NONE", "LOW", "MEDIUM", "HIGH", "XHIGH", "MAX"),
    "DEEPSEEK": ("NONE", "LOW", "HIGH", "MAX"),
    "MIMO": ("NONE", "LOW", "MEDIUM", "HIGH"),
    "XAI": ("LOW", "MEDIUM", "HIGH", "XHIGH"),
    "QWEN": ("PROVIDER_DEFAULT",),
    "GEMINI": ("LOW", "MEDIUM", "HIGH"),
    "ANTHROPIC": ("LOW", "MEDIUM", "HIGH", "XHIGH", "MAX"),
}
DEFAULT_AI_TIMEOUT_SECONDS = 180.0
DEFAULT_WEB_PERFORMANCE_TIMEOUT_SECONDS = 120.0
AI_TIMEOUT_ENV = "RASAI_AI_TIMEOUT_SECONDS"
AUTO_EXCLUDE_ENV = "RASAI_AI_AUTO_EXCLUDE"
WEB_PERFORMANCE_TIMEOUT_ENV = "RASAI_WEB_PERFORMANCE_TIMEOUT_SECONDS"


def provider_reasoning_env(provider_name: str) -> str | None:
    registration = get_provider_registration(provider_name)
    if registration is not None and registration.reasoning_env:
        return registration.reasoning_env
    return EXTENSION_REASONING_ENV.get(provider_name.strip().upper())


def configured_reasoning(provider_name: str, env: Mapping[str, str] | None = None) -> str:
    name = provider_name.strip().upper()
    environment = env if env is not None else os.environ
    variable = provider_reasoning_env(name)
    raw = (environment.get(variable) if variable else None) or LOWEST_REASONING[name]
    value = raw.strip().upper()
    allowed = REASONING_OPTIONS[name]
    if value not in allowed:
        raise ValueError(f"reasoning effort inválido para {name}: {value}; use {', '.join(allowed)}")
    return value


def configured_auto_exclusions(env: Mapping[str, str] | None = None) -> tuple[str, ...]:
    """Return canonical provider IDs explicitly excluded from AUTO.

    This changes AUTO membership only. Provider credentials/models remain untouched and
    the same provider can still be selected explicitly.
    """
    environment = env if env is not None else os.environ
    raw = (environment.get(AUTO_EXCLUDE_ENV) or "").strip()
    if not raw:
        return ()
    exclusions: list[str] = []
    for item in raw.replace(";", ",").split(","):
        token = item.strip()
        if not token:
            continue
        registration = get_provider_registration(token)
        if registration is None or not registration.auto_eligible:
            raise ValueError(f"provider não elegível para AUTO em {AUTO_EXCLUDE_ENV}: {token}")
        if registration.id not in exclusions:
            exclusions.append(registration.id)
    return tuple(exclusions)


def configured_simple_model(provider_name: str, env: Mapping[str, str] | None = None) -> str:
    name = provider_name.strip().upper()
    registration = get_provider_registration(name)
    if registration is None:
        raise ValueError(f"provider desconhecido: {provider_name}")
    environment = env if env is not None else os.environ
    raw = (environment.get(registration.model_env) or SIMPLE_DEFAULT_MODELS[name]).strip()
    if raw not in registration.supported_models:
        raise ValueError(f"modelo inválido para {name}: {raw}; use {', '.join(registration.supported_models)}")
    return raw


def environment_with_public_defaults(env: Mapping[str, str] | None = None) -> dict[str, str]:
    source = os.environ if env is None else env
    result = dict(source)
    for registration in provider_registrations():
        name = registration.provider_name
        result.setdefault(registration.model_env, SIMPLE_DEFAULT_MODELS[name])
        reasoning_env = provider_reasoning_env(name)
        if reasoning_env:
            result.setdefault(reasoning_env, LOWEST_REASONING[name])
    result.setdefault(AI_TIMEOUT_ENV, f"{DEFAULT_AI_TIMEOUT_SECONDS:g}")
    result.setdefault(WEB_PERFORMANCE_TIMEOUT_ENV, f"{DEFAULT_WEB_PERFORMANCE_TIMEOUT_SECONDS:g}")
    return result


def _patch_extension_semantic_reasoning(provider: IsolatedStructuredSemanticProvider, effort: str) -> None:
    name = provider.name
    if name == "QWEN":
        provider.reasoning_profile = "PROVIDER_DEFAULT"
        return
    provider.reasoning_profile = effort
    original = provider._request_payload

    def request_payload(_self: Any, semantic_input: Any) -> dict[str, Any]:
        payload = original(semantic_input)
        if isinstance(provider, XAIProvider):
            payload.setdefault("reasoning", {})["effort"] = effort.casefold()
        elif isinstance(provider, GeminiProvider):
            payload["generation_config"] = {"thinking_level": effort.casefold()}
        elif isinstance(provider, AnthropicProvider):
            payload.setdefault("output_config", {})["effort"] = effort.casefold()
        return payload

    provider._request_payload = MethodType(request_payload, provider)


def _install_provider_wire_projection(provider: Any) -> None:
    """Project provider-specific schemas immediately before the external transport.

    The wrapper is deliberately installed outside the exchange logger. The logger
    therefore receives and persists the exact sanitized body that is actually sent
    after projection, while local RASAi validators keep the canonical stricter
    contract.
    """
    if getattr(provider, "_rasai_wire_projection_installed", False):
        return
    original = getattr(provider, "_transport", None)
    if not callable(original):
        return
    provider._rasai_wire_projection_installed = True

    def projected(url: str, headers: dict[str, str], body: bytes, timeout: float):
        wire_body = project_provider_request_body(str(getattr(provider, "name", "")), body)
        return original(url, headers, wire_body, timeout)

    provider._transport = projected


def _prepare_concrete_provider(provider: Any, *, effective_env: Mapping[str, str], recorder: AiExchangeRecorder, context: Any) -> Any:
    if isinstance(provider, IsolatedStructuredSemanticProvider):
        _patch_extension_semantic_reasoning(provider, configured_reasoning(provider.name, effective_env))
    prepare_provider_for_execution(provider, recorder=recorder, context=context)
    _install_provider_wire_projection(provider)
    return provider


def _build_auto_provider(*, effective_env: Mapping[str, str]) -> DynamicProviderRoutingSession:
    context = configured_content_analysis_context(effective_env)
    recorder = AiExchangeRecorder()
    providers: list[Any] = []
    excluded: list[str] = []
    user_exclusions = set(configured_auto_exclusions(effective_env))
    for registration in provider_registrations():
        if not registration.auto_eligible:
            continue
        if registration.id in user_exclusions:
            excluded.append(f"{registration.provider_name}:USER_EXCLUDED_FROM_AUTO")
            continue
        if not (effective_env.get(registration.key_env) or "").strip():
            excluded.append(f"{registration.provider_name}:NOT_CONFIGURED")
            continue
        try:
            model = configured_simple_model(registration.provider_name, effective_env)
            provider = _build_semantic_provider(registration.id, model_override=model, env=effective_env)
            _prepare_concrete_provider(provider, effective_env=effective_env, recorder=recorder, context=context)
            providers.append(provider)
        except (TypeError, ValueError) as exc:
            excluded.append(f"{registration.provider_name}:INVALID_CONFIGURATION:{type(exc).__name__}")
    router = DynamicProviderRoutingSession(tuple(providers), excluded_configurations=tuple(excluded), recorder=recorder)
    install_dynamic_specialist_hooks()
    set_current_ai_execution(router, recorder)
    return router


def build_semantic_provider(selection: str, *, model_override: str | None = None, env: Mapping[str, str] | None = None) -> Any:
    effective_env = environment_with_public_defaults(env)
    context = configured_content_analysis_context(effective_env)
    selected = selection.strip().upper()
    if selected == "AUTO":
        if model_override:
            raise ValueError("AUTO does not accept one global model override; configure models per provider")
        return _build_auto_provider(effective_env=effective_env)

    registration = get_provider_registration(selection)
    effective_model = model_override
    if registration is not None and not effective_model:
        effective_model = configured_simple_model(registration.provider_name, effective_env)
    provider = _build_semantic_provider(selection, model_override=effective_model, env=effective_env)
    if selected == "NONE":
        clear_current_ai_execution()
        return provider
    recorder = AiExchangeRecorder()
    _prepare_concrete_provider(provider, effective_env=effective_env, recorder=recorder, context=context)
    set_current_ai_execution(provider, recorder)
    return provider


def _patch_content_provider_reasoning(provider: Any) -> None:
    if not isinstance(provider, ExtensionContentRemediationProvider):
        return
    name = provider.name
    effort = getattr(provider.base, "reasoning_profile", LOWEST_REASONING.get(name, "PROVIDER_DEFAULT"))
    if name == "QWEN":
        provider.reasoning_profile = "PROVIDER_DEFAULT"
        return
    provider.reasoning_profile = str(effort).upper()
    original = provider._request_payload

    def request_payload(_self: Any, request: Any) -> dict[str, Any]:
        payload = original(request)
        effective = provider.reasoning_profile.casefold()
        if isinstance(provider.base, XAIProvider):
            payload.setdefault("reasoning", {})["effort"] = effective
        elif isinstance(provider.base, GeminiProvider):
            payload["generation_config"] = {"thinking_level": effective}
        elif isinstance(provider.base, AnthropicProvider):
            payload.setdefault("output_config", {})["effort"] = effective
        return payload

    provider._request_payload = MethodType(request_payload, provider)


def build_content_remediation_router(semantic_provider: Any) -> Any:
    if isinstance(semantic_provider, DynamicProviderRoutingSession):
        router = build_dynamic_content_remediation_router(semantic_provider)
    else:
        from rasai.provider_extensions_m20 import build_content_remediation_router as _build_content_remediation_router
        router = _build_content_remediation_router(semantic_provider)
    for provider in getattr(router, "providers", ()):
        _patch_content_provider_reasoning(provider)
    return router


def apply_console_reasoning_environment(provider_name: str, effort: str, environment: MutableMapping[str, str] | None = None) -> None:
    env = environment if environment is not None else os.environ
    name = provider_name.strip().upper()
    allowed = REASONING_OPTIONS[name]
    value = effort.strip().upper()
    if value not in allowed:
        raise ValueError(f"use {', '.join(allowed)}")
    variable = provider_reasoning_env(name)
    if variable:
        env[variable] = value
