"""Runtime projection of the declarative AI model catalog onto existing adapters.

Only model metadata is projected. Authentication, endpoints, wire protocols, retries,
quarantine and cost routing remain owned by the existing provider/adaptation layers.
"""
from __future__ import annotations

import sys
from typing import Any

from rasai.ai_model_catalog import AiModelCatalog, AiModelDefinition, load_model_catalog

_INSTALLED = False
_EFFECTIVE_MODEL_CATALOG: AiModelCatalog | None = None


def effective_model_catalog() -> AiModelCatalog:
    global _EFFECTIVE_MODEL_CATALOG
    if _EFFECTIVE_MODEL_CATALOG is None:
        _EFFECTIVE_MODEL_CATALOG = load_model_catalog()
    return _EFFECTIVE_MODEL_CATALOG


def model_definition(provider: str, model: str) -> AiModelDefinition | None:
    return effective_model_catalog().model_definition(provider, model)


def _technical_provider_names() -> frozenset[str]:
    from rasai import m18_ai, provider_extensions
    from rasai.copilot_provider import COPILOT_PROVIDER_NAME

    return frozenset((*m18_ai.SUPPORTED_MODELS.keys(), *provider_extensions.EXTENDED_SUPPORTED_MODELS.keys(), COPILOT_PROVIDER_NAME))


def _enabled(catalog: AiModelCatalog, provider: str) -> tuple[AiModelDefinition, ...]:
    return catalog.provider_models(provider, enabled_only=True, effective_only=True)


def _default(items: tuple[AiModelDefinition, ...], attribute: str, provider: str) -> AiModelDefinition:
    matches = tuple(item for item in items if bool(getattr(item, attribute)))
    if len(matches) != 1:
        raise ValueError(f"AI models: {provider} deve possuir exatamente um {attribute} efetivo")
    return matches[0]


def _reasoning_union(items: tuple[AiModelDefinition, ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(value for item in items for value in item.reasoning_values))


def apply_model_catalog(catalog: AiModelCatalog) -> AiModelCatalog:
    """Project one validated catalog into the already-integrated provider adapters."""
    from rasai import copilot_provider, m18_ai, provider_extensions

    technical = _technical_provider_names()
    unknown = sorted(set(catalog.provider_names()) - set(technical))
    if unknown:
        raise ValueError(
            "AI models: provider sem adapter integrado: " + ", ".join(unknown)
        )

    # Core Responses-compatible adapters.
    core_policies: list[Any] = []
    for provider in tuple(m18_ai.SUPPORTED_MODELS):
        items = _enabled(catalog, provider)
        m18_ai.SUPPORTED_MODELS[provider] = tuple(item.model for item in items)
        if not items:
            continue
        adapter_default = _default(items, "adapter_default", provider)
        m18_ai.DEFAULT_MODELS[provider] = adapter_default.model
        for item in items:
            core_policies.append(m18_ai.ProviderPolicy(
                item.rank,
                provider,
                item.model,
                item.recommended_depth,
                item.rasai_class,
                item.qualification,
                item.recommended_use,
            ))
    m18_ai.ROUTING_POLICY = tuple(sorted(core_policies, key=lambda item: (item.rank, item.provider, item.model)))
    m18_ai._POLICY_BY_KEY.clear()
    m18_ai._POLICY_BY_KEY.update((item.provider, item.model) for item in ())
    m18_ai._POLICY_BY_KEY.update({(item.provider, item.model): item for item in m18_ai.ROUTING_POLICY})

    # Additional providers reuse their existing wire adapter classes.
    extension_policies: dict[tuple[str, str], Any] = {}
    for provider in tuple(provider_extensions.EXTENDED_SUPPORTED_MODELS):
        items = _enabled(catalog, provider)
        provider_extensions.EXTENDED_SUPPORTED_MODELS[provider] = tuple(item.model for item in items)
        if not items:
            continue
        adapter_default = _default(items, "adapter_default", provider)
        provider_extensions.EXTENDED_DEFAULT_MODELS[provider] = adapter_default.model
        for item in items:
            extension_policies[(provider, item.model)] = m18_ai.ProviderPolicy(
                item.rank,
                provider,
                item.model,
                item.recommended_depth,
                item.rasai_class,
                item.qualification,
                item.recommended_use,
            )
    provider_extensions.EXTENSION_POLICIES.clear()
    provider_extensions.EXTENSION_POLICIES.update(extension_policies)

    # Copilot SDK follows the same model-catalog contract while remaining explicit-only.
    copilot_items = _enabled(catalog, copilot_provider.COPILOT_PROVIDER_NAME)
    copilot_provider.COPILOT_SUPPORTED_MODELS = tuple(item.model for item in copilot_items)
    if copilot_items:
        copilot_provider.COPILOT_DEFAULT_MODEL = _default(
            copilot_items, "adapter_default", copilot_provider.COPILOT_PROVIDER_NAME
        ).model

    # Refresh already-imported public facades in-place so every AI consumer observes the
    # same catalog during this process. A normal product run installs once at startup.
    runtime_policy = sys.modules.get("rasai.provider_runtime_policy")
    if runtime_policy is not None:
        for provider in technical:
            items = _enabled(catalog, provider)
            if not items:
                runtime_policy.SIMPLE_DEFAULT_MODELS.pop(provider, None)
                runtime_policy.LOWEST_REASONING.pop(provider, None)
                runtime_policy.REASONING_OPTIONS.pop(provider, None)
                continue
            public_default = _default(items, "public_default", provider)
            runtime_policy.SIMPLE_DEFAULT_MODELS[provider] = public_default.model
            runtime_policy.LOWEST_REASONING[provider] = public_default.default_reasoning
            runtime_policy.REASONING_OPTIONS[provider] = _reasoning_union(items)

    registry = sys.modules.get("rasai.provider_registry")
    refresh = getattr(registry, "refresh_provider_registry", None) if registry is not None else None
    if callable(refresh):
        refresh(catalog=catalog)

    global _EFFECTIVE_MODEL_CATALOG
    _EFFECTIVE_MODEL_CATALOG = catalog
    return catalog


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    apply_model_catalog(load_model_catalog())
    _INSTALLED = True
