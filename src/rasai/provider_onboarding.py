"""Unified public onboarding projection for AI and SERP providers.

This module exposes provider metadata without ever returning credential values. It is
safe for CLI/UI support surfaces and intentionally reports only whether a credential is
configured in the supplied environment.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import os
from typing import Any, Mapping
from urllib.parse import urlparse

from rasai.provider_registry import get_provider_registration, provider_registrations
from rasai.provider_runtime_policy import REASONING_OPTIONS, SIMPLE_DEFAULT_MODELS
from rasai.search_intelligence.provider_catalog import (
    SERP_PROVIDER_REGISTRY,
    serp_provider_registration,
)


@dataclass(frozen=True, slots=True)
class ProviderOnboardingRecord:
    kind: str
    id: str
    display_name: str
    aliases: tuple[str, ...]
    credential_env: str
    configured: bool
    credential_url: str
    documentation_url: str
    auto_eligible: bool | None = None
    explicit_only: bool | None = None
    default_model: str | None = None
    reasoning_values: tuple[str, ...] = ()
    qualification: str | None = None
    engine: str | None = None
    free_tier: bool | None = None
    free_tier_note: str = ""

    def public_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation containing no credential value."""
        payload = asdict(self)
        payload["aliases"] = list(self.aliases)
        payload["reasoning_values"] = list(self.reasoning_values)
        return payload


def _configured(environment: Mapping[str, str], name: str) -> bool:
    return bool((environment.get(name) or "").strip())


def provider_onboarding_records(
    env: Mapping[str, str] | None = None,
    *,
    kind: str = "all",
    configured_only: bool = False,
) -> tuple[ProviderOnboardingRecord, ...]:
    environment = os.environ if env is None else env
    normalized_kind = kind.strip().casefold()
    if normalized_kind not in {"all", "ai", "serp"}:
        raise ValueError("provider kind must be one of: all, ai, serp")

    result: list[ProviderOnboardingRecord] = []
    if normalized_kind in {"all", "ai"}:
        for registration in provider_registrations():
            name = registration.provider_name
            result.append(
                ProviderOnboardingRecord(
                    kind="ai",
                    id=registration.id,
                    display_name=registration.display_name,
                    aliases=registration.aliases,
                    credential_env=registration.key_env,
                    configured=_configured(environment, registration.key_env),
                    credential_url=registration.credential_url,
                    documentation_url=registration.documentation_url,
                    auto_eligible=registration.auto_eligible,
                    explicit_only=registration.explicit_only,
                    default_model=SIMPLE_DEFAULT_MODELS[name],
                    reasoning_values=REASONING_OPTIONS[name],
                    qualification=registration.qualification,
                )
            )
    if normalized_kind in {"all", "serp"}:
        for registration in SERP_PROVIDER_REGISTRY:
            result.append(
                ProviderOnboardingRecord(
                    kind="serp",
                    id=registration.id,
                    display_name=registration.display_name,
                    aliases=(),
                    credential_env=registration.key_env,
                    configured=_configured(environment, registration.key_env),
                    credential_url=registration.credential_url,
                    documentation_url=registration.documentation_url,
                    engine=registration.engine,
                    free_tier=registration.free_tier,
                    free_tier_note=registration.free_tier_note,
                )
            )
    if configured_only:
        result = [item for item in result if item.configured]
    return tuple(result)


def find_provider_onboarding(
    selection: str,
    env: Mapping[str, str] | None = None,
    *,
    kind: str = "all",
) -> tuple[ProviderOnboardingRecord, ...]:
    token = selection.strip().casefold()
    if not token:
        return ()
    return tuple(
        item
        for item in provider_onboarding_records(env, kind=kind)
        if token == item.id or token in item.aliases
    )


def provider_onboarding_integrity_issues() -> tuple[str, ...]:
    """Validate support-facing metadata without inspecting any secret value."""
    issues: list[str] = []
    seen: set[tuple[str, str]] = set()
    for item in provider_onboarding_records({}, kind="all"):
        key = (item.kind, item.id)
        if key in seen:
            issues.append(f"duplicate provider identity: {item.kind}:{item.id}")
        seen.add(key)
        if not item.credential_env.strip():
            issues.append(f"{item.kind}:{item.id} missing credential environment variable")
        for label, url in (
            ("credential", item.credential_url),
            ("documentation", item.documentation_url),
        ):
            parsed = urlparse(url)
            if parsed.scheme != "https" or not parsed.netloc:
                issues.append(f"{item.kind}:{item.id} invalid {label} URL")
        if item.kind == "ai":
            registration = get_provider_registration(item.id)
            if registration is None:
                issues.append(f"ai:{item.id} missing canonical AI registration")
                continue
            if registration.default_model not in registration.supported_models:
                issues.append(f"ai:{item.id} adapter default model is not supported")
            if item.default_model not in registration.supported_models:
                issues.append(f"ai:{item.id} public default model is not supported")
            if tuple(item.reasoning_values) != tuple(registration.reasoning_values):
                issues.append(f"ai:{item.id} reasoning contract drift between registry and runtime")
            if registration.explicit_only and registration.auto_eligible:
                issues.append(f"ai:{item.id} explicit-only provider cannot be AUTO eligible")
        else:
            registration = serp_provider_registration(item.id)
            if registration is None:
                issues.append(f"serp:{item.id} missing canonical SERP registration")
            if item.free_tier and not item.free_tier_note.strip():
                issues.append(f"serp:{item.id} free-tier metadata has no quota note")
    return tuple(issues)
