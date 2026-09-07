"""Canonical provider registry facade for RASAI consumers.

The homologated M18 module remains authoritative for legacy provider behavior and
provider_extensions remains authoritative for explicit-only adapter internals.
This module normalizes both sources into one public registry consumed by CLI,
interactive console, preflight/help and future orchestration surfaces.

Consumers MUST use this module instead of maintaining independent provider lists.
"""

from __future__ import annotations

from dataclasses import dataclass

from searchgeo.m18_ai import (
    DEFAULT_MODELS,
    KEY_ENV,
    MODEL_ENV,
    REASONING_ENV,
    ROUTING_POLICY,
    SUPPORTED_MODELS,
)
from searchgeo.provider_extensions import (
    EXTENDED_DEFAULT_MODELS,
    EXTENDED_ENDPOINT_ENV,
    EXTENDED_KEY_ENV,
    EXTENDED_MODEL_ENV,
    EXTENDED_SUPPORTED_MODELS,
    EXTENSION_POLICIES,
    _PROVIDER_ALIASES,
)


@dataclass(frozen=True, slots=True)
class ProviderRegistration:
    """Normalized metadata required by user-facing provider consumers."""

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

    @property
    def cli_selections(self) -> tuple[str, ...]:
        return (self.id, *self.aliases)


_DISPLAY_NAMES = {
    "OPENAI": "OpenAI",
    "DEEPSEEK": "DeepSeek",
    "MIMO": "Xiaomi MiMo",
    "XAI": "xAI / Grok",
    "QWEN": "Alibaba Qwen",
    "GEMINI": "Google Gemini",
    "ANTHROPIC": "Anthropic Claude",
}

_LEGACY_PROVIDER_ORDER = ("OPENAI", "DEEPSEEK", "MIMO")
_LEGACY_REASONING_VALUES = {
    "OPENAI": ("NONE", "LOW", "MEDIUM", "HIGH", "XHIGH", "MAX"),
    "DEEPSEEK": ("NONE", "LOW", "MEDIUM", "HIGH", "XHIGH", "MAX"),
    "MIMO": ("NONE", "LOW", "MEDIUM", "HIGH"),
}


def _qualification(provider_name: str, *, extension: bool) -> str:
    policies = (
        tuple(
            policy
            for (provider, _model), policy in EXTENSION_POLICIES.items()
            if provider == provider_name
        )
        if extension
        else tuple(policy for policy in ROUTING_POLICY if policy.provider == provider_name)
    )
    values = tuple(dict.fromkeys(policy.qualification for policy in policies))
    if not values:
        return "UNQUALIFIED"
    return values[0] if len(values) == 1 else "/".join(values)


def _extension_aliases(provider_name: str) -> tuple[str, ...]:
    canonical = provider_name.casefold()
    return tuple(
        alias.casefold()
        for alias, target in _PROVIDER_ALIASES.items()
        if target == provider_name and alias.casefold() != canonical
    )


def _legacy_registration(provider_name: str) -> ProviderRegistration:
    provider_id = provider_name.casefold()
    return ProviderRegistration(
        id=provider_id,
        provider_name=provider_name,
        display_name=_DISPLAY_NAMES[provider_name],
        aliases=(),
        key_env=KEY_ENV[provider_name],
        model_env=MODEL_ENV[provider_name],
        endpoint_env=None,
        reasoning_env=REASONING_ENV[provider_name],
        supported_models=tuple(SUPPORTED_MODELS[provider_name]),
        default_model=DEFAULT_MODELS[provider_name],
        qualification=_qualification(provider_name, extension=False),
        explicit_only=False,
        auto_eligible=True,
        reasoning_values=_LEGACY_REASONING_VALUES[provider_name],
        required_key_prefixes=("sk-",) if provider_name == "MIMO" else (),
    )


def _extension_registration(provider_name: str) -> ProviderRegistration:
    policies = tuple(
        policy
        for (provider, _model), policy in EXTENSION_POLICIES.items()
        if provider == provider_name
    )
    reasoning_values = tuple(dict.fromkeys(policy.recommended_depth for policy in policies))
    return ProviderRegistration(
        id=provider_name.casefold(),
        provider_name=provider_name,
        display_name=_DISPLAY_NAMES.get(provider_name, provider_name.title()),
        aliases=_extension_aliases(provider_name),
        key_env=EXTENDED_KEY_ENV[provider_name],
        model_env=EXTENDED_MODEL_ENV[provider_name],
        endpoint_env=EXTENDED_ENDPOINT_ENV.get(provider_name),
        reasoning_env=None,
        supported_models=tuple(EXTENDED_SUPPORTED_MODELS[provider_name]),
        default_model=EXTENDED_DEFAULT_MODELS[provider_name],
        qualification=_qualification(provider_name, extension=True),
        explicit_only=True,
        auto_eligible=False,
        reasoning_values=reasoning_values or ("PROVIDER_DEFAULT",),
    )


def _build_registry() -> tuple[ProviderRegistration, ...]:
    legacy = tuple(_legacy_registration(name) for name in _LEGACY_PROVIDER_ORDER)
    extension_names = tuple(dict.fromkeys(_PROVIDER_ALIASES.values()))
    extensions = tuple(_extension_registration(name) for name in extension_names)
    registrations = legacy + extensions

    ids = [registration.id for registration in registrations]
    if len(ids) != len(set(ids)):
        raise RuntimeError("duplicate canonical provider id in RASAI registry")

    selections = [
        selection
        for registration in registrations
        for selection in registration.cli_selections
    ]
    if len(selections) != len(set(selections)):
        raise RuntimeError("duplicate provider CLI selection in RASAI registry")
    return registrations


PROVIDER_REGISTRY: tuple[ProviderRegistration, ...] = _build_registry()
_PROVIDER_BY_ID = {registration.id: registration for registration in PROVIDER_REGISTRY}
_PROVIDER_BY_SELECTION = {
    selection: registration
    for registration in PROVIDER_REGISTRY
    for selection in registration.cli_selections
}


def provider_registrations() -> tuple[ProviderRegistration, ...]:
    """Return all concrete providers in stable public order."""
    return PROVIDER_REGISTRY


def get_provider_registration(selection: str) -> ProviderRegistration | None:
    """Resolve a canonical provider id or alias; NONE/AUTO return None."""
    return _PROVIDER_BY_SELECTION.get(selection.strip().casefold())


def extension_cli_choices() -> tuple[str, ...]:
    """Return explicit-only CLI selections in adapter-declared alias order."""
    return tuple(alias.casefold() for alias in _PROVIDER_ALIASES)


def cli_provider_choices() -> tuple[str, ...]:
    """Return the complete public CLI surface while preserving legacy order."""
    return (
        "none",
        *tuple(name.casefold() for name in _LEGACY_PROVIDER_ORDER),
        "auto",
        *extension_cli_choices(),
    )


def auto_provider_ids() -> tuple[str, ...]:
    """Return the homologated AUTO chain candidates; extensions stay excluded."""
    return tuple(
        registration.id
        for registration in PROVIDER_REGISTRY
        if registration.auto_eligible
    )


def provider_environment_names() -> tuple[str, ...]:
    """Return all registry-owned environment variable names without values."""
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
