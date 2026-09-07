"""Public runtime defaults for provider model/effort selection.

This module intentionally sits above the historical provider adapters. It keeps
backward-compatible adapters untouched while defining the product-level default
policy used by the public CLI and interactive console:

* choose the simplest/lowest-cost supported model when the user did not select
  a model explicitly;
* choose the lowest reasoning/thinking effort actually supported by the adapter
  and provider API;
* preserve explicit environment/model selections.

Provider-specific payload tuning is limited to parameters confirmed by the
current adapters/provider contracts. Qwen remains PROVIDER_DEFAULT because the
current RASAI adapter does not expose a validated reasoning-effort control.
"""
from __future__ import annotations

from types import MethodType
import os
from typing import Any, Mapping, MutableMapping

from searchgeo.content_context import configured_content_analysis_context
from searchgeo.provider_extensions import (
    EXTENDED_MODEL_ENV,
    AnthropicProvider,
    GeminiProvider,
    IsolatedStructuredSemanticProvider,
    QwenProvider,
    XAIProvider,
    build_semantic_provider as _build_semantic_provider,
)
from searchgeo.provider_extensions_m20 import (
    ExtensionContentRemediationProvider,
    build_content_remediation_router as _build_content_remediation_router,
)
from searchgeo.provider_registry import get_provider_registration, provider_registrations


SIMPLE_DEFAULT_MODELS: dict[str, str] = {
    "OPENAI": "gpt-5.6-luna",
    "DEEPSEEK": "deepseek-v4-flash",
    "MIMO": "mimo-v2.5",
    "XAI": "grok-4.6",
    "QWEN": "qwen3.8-flash",
    "GEMINI": "gemini-3.8-flash",
    "ANTHROPIC": "claude-sonnet-5",
}

# Lowest supported/effective level for each current adapter/provider contract.
LOWEST_REASONING: dict[str, str] = {
    "OPENAI": "NONE",
    "DEEPSEEK": "NONE",
    "MIMO": "NONE",
    "XAI": "LOW",
    "QWEN": "PROVIDER_DEFAULT",
    "GEMINI": "LOW",
    "ANTHROPIC": "LOW",
}

EXTENSION_REASONING_ENV: dict[str, str] = {
    "XAI": "SEARCHGEO_XAI_REASONING_EFFORT",
    "GEMINI": "SEARCHGEO_GEMINI_REASONING_EFFORT",
    "ANTHROPIC": "SEARCHGEO_ANTHROPIC_REASONING_EFFORT",
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
AI_TIMEOUT_ENV = "SEARCHGEO_AI_TIMEOUT_SECONDS"
WEB_PERFORMANCE_TIMEOUT_ENV = "SEARCHGEO_WEB_PERFORMANCE_TIMEOUT_SECONDS"


def provider_reasoning_env(provider_name: str) -> str | None:
    registration = get_provider_registration(provider_name)
    if registration is not None and registration.reasoning_env:
        return registration.reasoning_env
    return EXTENSION_REASONING_ENV.get(provider_name.strip().upper())


def configured_reasoning(
    provider_name: str,
    env: Mapping[str, str] | None = None,
) -> str:
    name = provider_name.strip().upper()
    environment = env if env is not None else os.environ
    variable = provider_reasoning_env(name)
    raw = (environment.get(variable) if variable else None) or LOWEST_REASONING[name]
    value = raw.strip().upper()
    allowed = REASONING_OPTIONS[name]
    if value not in allowed:
        raise ValueError(
            f"reasoning effort inválido para {name}: {value}; use {', '.join(allowed)}"
        )
    return value


def configured_simple_model(
    provider_name: str,
    env: Mapping[str, str] | None = None,
) -> str:
    name = provider_name.strip().upper()
    registration = get_provider_registration(name)
    if registration is None:
        raise ValueError(f"provider desconhecido: {provider_name}")
    environment = env if env is not None else os.environ
    raw = (environment.get(registration.model_env) or SIMPLE_DEFAULT_MODELS[name]).strip()
    if raw not in registration.supported_models:
        raise ValueError(
            f"modelo inválido para {name}: {raw}; use {', '.join(registration.supported_models)}"
        )
    return raw


def environment_with_public_defaults(
    env: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Return a copy with public defaults filled only where the user is silent."""
    source = os.environ if env is None else env
    result = dict(source)
    for registration in provider_registrations():
        name = registration.provider_name
        result.setdefault(registration.model_env, SIMPLE_DEFAULT_MODELS[name])
        reasoning_env = provider_reasoning_env(name)
        if reasoning_env:
            result.setdefault(reasoning_env, LOWEST_REASONING[name])
    result.setdefault(AI_TIMEOUT_ENV, f"{DEFAULT_AI_TIMEOUT_SECONDS:g}")
    result.setdefault(
        WEB_PERFORMANCE_TIMEOUT_ENV,
        f"{DEFAULT_WEB_PERFORMANCE_TIMEOUT_SECONDS:g}",
    )
    return result


def _patch_extension_semantic_reasoning(
    provider: IsolatedStructuredSemanticProvider,
    effort: str,
) -> None:
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


def build_semantic_provider(
    selection: str,
    *,
    model_override: str | None = None,
    env: Mapping[str, str] | None = None,
) -> Any:
    """Build a provider using lowest public defaults unless explicitly overridden."""
    effective_env = environment_with_public_defaults(env)
    # Validate the full editorial/AI context before any audit work starts. This
    # also applies when selection=none, preventing a malformed persisted context
    # from failing only during report generation.
    configured_content_analysis_context(effective_env)
    registration = get_provider_registration(selection)
    effective_model = model_override
    if registration is not None and not effective_model:
        effective_model = configured_simple_model(registration.provider_name, effective_env)

    provider = _build_semantic_provider(
        selection,
        model_override=effective_model,
        env=effective_env,
    )
    if isinstance(provider, IsolatedStructuredSemanticProvider):
        effort = configured_reasoning(provider.name, effective_env)
        _patch_extension_semantic_reasoning(provider, effort)
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
    """Keep content remediation on the same effective provider effort."""
    router = _build_content_remediation_router(semantic_provider)
    for provider in getattr(router, "providers", ()):
        _patch_content_provider_reasoning(provider)
    return router


def apply_console_reasoning_environment(
    provider_name: str,
    effort: str,
    environment: MutableMapping[str, str] | None = None,
) -> None:
    env = environment if environment is not None else os.environ
    name = provider_name.strip().upper()
    allowed = REASONING_OPTIONS[name]
    value = effort.strip().upper()
    if value not in allowed:
        raise ValueError(f"use {', '.join(allowed)}")
    variable = provider_reasoning_env(name)
    if variable:
        env[variable] = value
