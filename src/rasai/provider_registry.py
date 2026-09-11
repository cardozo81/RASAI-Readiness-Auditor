"""Canonical provider registry facade for RASAi consumers.

The core provider module and adapter extensions are normalized into one public registry
consumed by CLI, interactive console, preflight/help and orchestration. AUTO eligibility
is a registry property; runtime still requires valid credentials and configuration.
"""
from __future__ import annotations

from dataclasses import dataclass
import sys

from rasai.copilot_provider import (
    COPILOT_DEFAULT_MODEL,
    COPILOT_DOCS_URL,
    COPILOT_KEY_ENV,
    COPILOT_MODEL_ENV,
    COPILOT_SETTINGS_URL,
    COPILOT_SUPPORTED_MODELS,
    COPILOT_TOKEN_URL,
)
from rasai.m18_ai import DEFAULT_MODELS, KEY_ENV, MODEL_ENV, REASONING_ENV, ROUTING_POLICY, SUPPORTED_MODELS
from rasai.provider_extensions import EXTENDED_DEFAULT_MODELS, EXTENDED_ENDPOINT_ENV, EXTENDED_KEY_ENV, EXTENDED_MODEL_ENV, EXTENDED_SUPPORTED_MODELS, EXTENSION_POLICIES, _PROVIDER_ALIASES


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
_RUNTIME_REASONING_VALUES = {
    "OPENAI": ("NONE", "LOW", "MEDIUM", "HIGH", "XHIGH", "MAX"),
    "DEEPSEEK": ("NONE", "LOW", "HIGH", "MAX"),
    "MIMO": ("NONE", "LOW", "MEDIUM", "HIGH"),
    "XAI": ("LOW", "MEDIUM", "HIGH", "XHIGH"),
    "QWEN": ("PROVIDER_DEFAULT",),
    "GEMINI": ("LOW", "MEDIUM", "HIGH"),
    "ANTHROPIC": ("LOW", "MEDIUM", "HIGH", "XHIGH", "MAX"),
    "COPILOT": ("PROVIDER_DEFAULT",),
}


def _qualification(provider_name: str, *, extension: bool) -> str:
    policies = tuple(policy for (provider, _model), policy in EXTENSION_POLICIES.items() if provider == provider_name) if extension else tuple(policy for policy in ROUTING_POLICY if policy.provider == provider_name)
    values = tuple(dict.fromkeys(policy.qualification for policy in policies))
    if not values:
        return "UNQUALIFIED"
    return values[0] if len(values) == 1 else "/".join(values)


def _extension_aliases(provider_name: str) -> tuple[str, ...]:
    canonical = provider_name.casefold()
    return tuple(alias.casefold() for alias, target in _PROVIDER_ALIASES.items() if target == provider_name and alias.casefold() != canonical)


def _core_registration(provider_name: str) -> ProviderRegistration:
    return ProviderRegistration(
        id=provider_name.casefold(), provider_name=provider_name, display_name=_DISPLAY_NAMES[provider_name], aliases=(),
        key_env=KEY_ENV[provider_name], model_env=MODEL_ENV[provider_name], endpoint_env=None,
        reasoning_env=REASONING_ENV[provider_name], supported_models=tuple(SUPPORTED_MODELS[provider_name]),
        default_model=DEFAULT_MODELS[provider_name], qualification=_qualification(provider_name, extension=False),
        explicit_only=False, auto_eligible=True, reasoning_values=_RUNTIME_REASONING_VALUES[provider_name],
        required_key_prefixes=("sk-",) if provider_name == "MIMO" else (),
        credential_url=_CREDENTIAL_URLS[provider_name], documentation_url=_DOCUMENTATION_URLS[provider_name],
    )


def _extension_registration(provider_name: str) -> ProviderRegistration:
    return ProviderRegistration(
        id=provider_name.casefold(), provider_name=provider_name,
        display_name=_DISPLAY_NAMES.get(provider_name, provider_name.title()), aliases=_extension_aliases(provider_name),
        key_env=EXTENDED_KEY_ENV[provider_name], model_env=EXTENDED_MODEL_ENV[provider_name],
        endpoint_env=EXTENDED_ENDPOINT_ENV.get(provider_name), reasoning_env=None,
        supported_models=tuple(EXTENDED_SUPPORTED_MODELS[provider_name]), default_model=EXTENDED_DEFAULT_MODELS[provider_name],
        qualification=_qualification(provider_name, extension=True), explicit_only=False, auto_eligible=True,
        reasoning_values=_RUNTIME_REASONING_VALUES[provider_name],
        credential_url=_CREDENTIAL_URLS[provider_name], documentation_url=_DOCUMENTATION_URLS[provider_name],
    )


def _copilot_registration() -> ProviderRegistration:
    return ProviderRegistration(
        id="copilot", provider_name="COPILOT", display_name=_DISPLAY_NAMES["COPILOT"],
        aliases=("github-copilot",), key_env=COPILOT_KEY_ENV, model_env=COPILOT_MODEL_ENV,
        endpoint_env=None, reasoning_env=None, supported_models=COPILOT_SUPPORTED_MODELS,
        default_model=COPILOT_DEFAULT_MODEL, qualification="PROVISIONAL", explicit_only=True,
        auto_eligible=False, reasoning_values=_RUNTIME_REASONING_VALUES["COPILOT"],
        required_key_prefixes=("github_pat_", "gho_", "ghu_"),
        credential_url=COPILOT_TOKEN_URL, documentation_url=COPILOT_DOCS_URL,
        auth_note=(
            "Requer assinatura Copilot elegível. Para uso local do RASAi, gere um fine-grained PAT "
            "com Copilot Requests e configure COPILOT_GITHUB_TOKEN. Classic PAT ghp_ não é suportado. "
            f"Preferências Copilot: {COPILOT_SETTINGS_URL}"
        ),
    )


def _build_registry() -> tuple[ProviderRegistration, ...]:
    core = tuple(_core_registration(name) for name in _CORE_PROVIDER_ORDER)
    extension_names = tuple(dict.fromkeys(_PROVIDER_ALIASES.values()))
    registrations = core + tuple(_extension_registration(name) for name in extension_names) + (_copilot_registration(),)
    ids = [registration.id for registration in registrations]
    if len(ids) != len(set(ids)):
        raise RuntimeError("duplicate canonical provider id in RASAi registry")
    selections = [selection for registration in registrations for selection in registration.cli_selections]
    if len(selections) != len(set(selections)):
        raise RuntimeError("duplicate provider CLI selection in RASAi registry")
    for registration in registrations:
        if registration.default_model not in registration.supported_models:
            raise RuntimeError(f"provider {registration.id} has unsupported adapter default model")
        if not registration.reasoning_values:
            raise RuntimeError(f"provider {registration.id} has no runtime reasoning contract")
        if registration.explicit_only and registration.auto_eligible:
            raise RuntimeError(f"provider {registration.id} cannot be explicit-only and AUTO eligible")
    return registrations


PROVIDER_REGISTRY: tuple[ProviderRegistration, ...] = _build_registry()
_PROVIDER_BY_SELECTION = {selection: registration for registration in PROVIDER_REGISTRY for selection in registration.cli_selections}


def _publish_legacy_console_credential_sources() -> None:
    """Compatibility bridge for the older console environment catalog.

    The general environment editor still owns a historical credential-source mapping.
    Publish canonical onboarding URLs into that mapping when it is already imported.
    The provider-aware console surface then enriches the user-facing records without
    exposing any secret value.
    """
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
    _publish_legacy_console_credential_sources()
    return PROVIDER_REGISTRY


def get_provider_registration(selection: str) -> ProviderRegistration | None:
    return _PROVIDER_BY_SELECTION.get(selection.strip().casefold())


def extension_cli_choices() -> tuple[str, ...]:
    return tuple(selection for item in PROVIDER_REGISTRY if item.provider_name not in _CORE_PROVIDER_ORDER for selection in item.cli_selections)


def cli_provider_choices() -> tuple[str, ...]:
    return ("none", *(item.id for item in PROVIDER_REGISTRY), "auto", *(alias for item in PROVIDER_REGISTRY for alias in item.aliases))


def auto_provider_ids() -> tuple[str, ...]:
    return tuple(registration.id for registration in PROVIDER_REGISTRY if registration.auto_eligible)


def provider_environment_names() -> tuple[str, ...]:
    names: list[str] = []
    for registration in PROVIDER_REGISTRY:
        for name in (registration.key_env, registration.model_env, registration.endpoint_env, registration.reasoning_env):
            if name and name not in names:
                names.append(name)
    return tuple(names)
