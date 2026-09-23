"""Canonical provider registry facade for RASAi consumers.

Provider integrations remain implemented by adapters. Model availability, defaults,
reasoning metadata and model-level AUTO eligibility are projected from the declarative
AI model catalog so CLI, console, preflight and orchestration share one model contract.
"""
from __future__ import annotations

from dataclasses import dataclass
import sys

from rasai.ai_model_catalog import AiModelCatalog, AiModelDefinition, load_model_catalog
from rasai.copilot_provider import (
    COPILOT_DOCS_URL,
    COPILOT_KEY_ENV,
    COPILOT_MODEL_ENV,
    COPILOT_SETTINGS_URL,
    COPILOT_TOKEN_URL,
)
from rasai.m18_ai import KEY_ENV, MODEL_ENV, REASONING_ENV
from rasai.provider_extensions import (
    EXTENDED_ENDPOINT_ENV,
    EXTENDED_KEY_ENV,
    EXTENDED_MODEL_ENV,
    _PROVIDER_ALIASES,
)


@dataclass(frozen=True, slots=True)
class ProviderRegistration:
    id: str
    provider_name: str
    display_name: str
    aliases: tuple[str, ...]
    key_env: str
    model_env: str
    endpoint_env: str | None
    reasoning_env: str | None
    supported_models: tuple[str, ...]
    default_model: str
    public_default_model: str
    qualification: str
    explicit_only: bool
    auto_eligible: bool
    reasoning_values: tuple[str, ...]
    required_key_prefixes: tuple[str, ...] = ()
    credential_url: str = ""
    documentation_url: str = ""
    auth_note: str = ""

    @property
    def cli_selections(self) -> tuple[str, ...]:
        return (self.id, *self.aliases)


_DISPLAY_NAMES = {
    "OPENAI": "OpenAI", "DEEPSEEK": "DeepSeek", "MIMO": "Xiaomi MiMo",
    "XAI": "xAI / Grok", "QWEN": "Alibaba Qwen", "GEMINI": "Google Gemini",
    "ANTHROPIC": "Anthropic Claude", "COPILOT": "GitHub Copilot",
}
_CREDENTIAL_URLS = {
    "OPENAI": "https://platform.openai.com/api-keys",
    "DEEPSEEK": "https://platform.deepseek.com/api_keys",
    "MIMO": "https://mimo.mi.com/",
    "XAI": "https://console.x.ai/",
    "QWEN": "https://www.alibabacloud.com/help/en/model-studio/get-api-key",
    "GEMINI": "https://aistudio.google.com/apikey",
    "ANTHROPIC": "https://console.anthropic.com/",
}
_DOCUMENTATION_URLS = {
    "OPENAI": "https://platform.openai.com/docs/",
    "DEEPSEEK": "https://api-docs.deepseek.com/",
    "MIMO": "https://mimo.mi.com/docs/en-US/quick-start/faq/api-integration",
    "XAI": "https://docs.x.ai/",
    "QWEN": "https://www.alibabacloud.com/help/en/model-studio/get-api-key",
    "GEMINI": "https://ai.google.dev/gemini-api/docs/api-key",
    "ANTHROPIC": "https://docs.anthropic.com/",
}
_CORE_PROVIDER_ORDER = ("OPENAI", "DEEPSEEK", "MIMO")
_EXTENSION_REASONING_ENV = {
    "XAI": "RASAI_XAI_REASONING_EFFORT",
    "GEMINI": "RASAI_GEMINI_REASONING_EFFORT",
    "ANTHROPIC": "RASAI_ANTHROPIC_REASONING_EFFORT",
}
_TECHNICAL_PROVIDER_ORDER = (*_CORE_PROVIDER_ORDER, *tuple(dict.fromkeys(_PROVIDER_ALIASES.values())), "COPILOT")


def _extension_aliases(provider_name: str) -> tuple[str, ...]:
    canonical = provider_name.casefold()
    return tuple(
        alias.casefold()
        for alias, target in _PROVIDER_ALIASES.items()
        if target == provider_name and alias.casefold() != canonical
    )


def _catalog_items(catalog: AiModelCatalog, provider_name: str) -> tuple[AiModelDefinition, ...]:
    return catalog.provider_models(provider_name, enabled_only=True, effective_only=True)


def _one_default(items: tuple[AiModelDefinition, ...], field: str, provider_name: str) -> AiModelDefinition:
    matches = tuple(item for item in items if bool(getattr(item, field)))
    if len(matches) != 1:
        raise RuntimeError(f"provider {provider_name} must have exactly one effective {field}")
    return matches[0]


def _reasoning_values(items: tuple[AiModelDefinition, ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(value for item in items for value in item.reasoning_values))


def _registration(provider_name: str, catalog: AiModelCatalog) -> ProviderRegistration | None:
    items = _catalog_items(catalog, provider_name)
    if not items:
        return None
    selectable = tuple(item for item in items if item.selectable)
    if not selectable:
        return None
    adapter_default = _one_default(items, "adapter_default", provider_name)
    public_default = _one_default(items, "public_default", provider_name)
    explicit_only = provider_name == "COPILOT"

    if provider_name in _CORE_PROVIDER_ORDER:
        aliases: tuple[str, ...] = ()
        key_env = KEY_ENV[provider_name]
        model_env = MODEL_ENV[provider_name]
        endpoint_env = None
        reasoning_env = REASONING_ENV[provider_name]
    elif provider_name == "COPILOT":
        aliases = ("github-copilot",)
        key_env = COPILOT_KEY_ENV
        model_env = COPILOT_MODEL_ENV
        endpoint_env = None
        reasoning_env = None
    else:
        aliases = _extension_aliases(provider_name)
        key_env = EXTENDED_KEY_ENV[provider_name]
        model_env = EXTENDED_MODEL_ENV[provider_name]
        endpoint_env = EXTENDED_ENDPOINT_ENV.get(provider_name)
        reasoning_env = _EXTENSION_REASONING_ENV.get(provider_name)

    registration = ProviderRegistration(
        id=provider_name.casefold(),
        provider_name=provider_name,
        display_name=_DISPLAY_NAMES.get(provider_name, provider_name.title()),
        aliases=aliases,
        key_env=key_env,
        model_env=model_env,
        endpoint_env=endpoint_env,
        reasoning_env=reasoning_env,
        supported_models=tuple(item.model for item in selectable),
        default_model=adapter_default.model,
        public_default_model=public_default.model,
        qualification=public_default.qualification,
        explicit_only=explicit_only,
        auto_eligible=(not explicit_only and any(item.auto_eligible for item in selectable)),
        reasoning_values=_reasoning_values(selectable),
        required_key_prefixes=("sk-",) if provider_name == "MIMO" else (("github_pat_", "gho_", "ghu_") if provider_name == "COPILOT" else ()),
        credential_url=(COPILOT_TOKEN_URL if provider_name == "COPILOT" else _CREDENTIAL_URLS.get(provider_name, "")),
        documentation_url=(COPILOT_DOCS_URL if provider_name == "COPILOT" else _DOCUMENTATION_URLS.get(provider_name, "")),
        auth_note=(
            "Requer assinatura Copilot elegível. Para uso local do RASAi, gere um fine-grained PAT "
            "com Copilot Requests e configure COPILOT_GITHUB_TOKEN. Classic PAT ghp_ não é suportado. "
            f"Preferências Copilot: {COPILOT_SETTINGS_URL}"
            if provider_name == "COPILOT" else ""
        ),
    )
    if registration.default_model not in tuple(item.model for item in items):
        raise RuntimeError(f"provider {registration.id} has unsupported adapter default model")
    if registration.public_default_model not in registration.supported_models:
        raise RuntimeError(f"provider {registration.id} has unsupported public default model")
    if not registration.reasoning_values:
        raise RuntimeError(f"provider {registration.id} has no runtime reasoning contract")
    if registration.explicit_only and registration.auto_eligible:
        raise RuntimeError(f"provider {registration.id} cannot be explicit-only and AUTO eligible")
    return registration


def _build_registry(catalog: AiModelCatalog | None = None) -> tuple[ProviderRegistration, ...]:
    effective = catalog or load_model_catalog()
    unknown = sorted(set(effective.provider_names()) - set(_TECHNICAL_PROVIDER_ORDER))
    if unknown:
        raise ValueError("AI models: provider sem adapter integrado: " + ", ".join(unknown))
    registrations = tuple(
        item
        for provider_name in _TECHNICAL_PROVIDER_ORDER
        for item in (_registration(provider_name, effective),)
        if item is not None
    )
    ids = [registration.id for registration in registrations]
    if len(ids) != len(set(ids)):
        raise RuntimeError("duplicate canonical provider id in RASAi registry")
    selections = [selection for registration in registrations for selection in registration.cli_selections]
    if len(selections) != len(set(selections)):
        raise RuntimeError("duplicate provider CLI selection in RASAi registry")
    return registrations


PROVIDER_REGISTRY: tuple[ProviderRegistration, ...] = _build_registry()
_PROVIDER_BY_SELECTION = {
    selection: registration
    for registration in PROVIDER_REGISTRY
    for selection in registration.cli_selections
}


def refresh_provider_registry(*, catalog: AiModelCatalog | None = None) -> tuple[ProviderRegistration, ...]:
    global PROVIDER_REGISTRY, _PROVIDER_BY_SELECTION
    PROVIDER_REGISTRY = _build_registry(catalog)
    _PROVIDER_BY_SELECTION = {
        selection: registration
        for registration in PROVIDER_REGISTRY
        for selection in registration.cli_selections
    }
    return PROVIDER_REGISTRY


def _publish_console_credential_sources() -> None:
    module = sys.modules.get("rasai.console_environment")
    sources = getattr(module, "KEY_SOURCES", None) if module is not None else None
    if not isinstance(sources, dict):
        return
    for registration in PROVIDER_REGISTRY:
        if registration.credential_url:
            sources[registration.provider_name] = (
                f"{registration.display_name} credencial/login - {registration.credential_url}"
            )


def provider_registrations() -> tuple[ProviderRegistration, ...]:
    _publish_console_credential_sources()
    return PROVIDER_REGISTRY


def get_provider_registration(selection: str) -> ProviderRegistration | None:
    return _PROVIDER_BY_SELECTION.get(selection.strip().casefold())


def extension_cli_choices() -> tuple[str, ...]:
    return tuple(
        selection
        for item in PROVIDER_REGISTRY
        if item.provider_name not in _CORE_PROVIDER_ORDER
        for selection in item.cli_selections
    )


def cli_provider_choices() -> tuple[str, ...]:
    return (
        "none",
        *(item.id for item in PROVIDER_REGISTRY),
        "auto",
        *(alias for item in PROVIDER_REGISTRY for alias in item.aliases),
    )


def auto_provider_ids() -> tuple[str, ...]:
    return tuple(registration.id for registration in PROVIDER_REGISTRY if registration.auto_eligible)


def provider_environment_names() -> tuple[str, ...]:
    names: list[str] = []
    for registration in PROVIDER_REGISTRY:
        for name in (
            registration.key_env,
            registration.model_env,
            registration.endpoint_env,
            registration.reasoning_env,
        ):
            if name and name not in names:
                names.append(name)
    return tuple(names)
