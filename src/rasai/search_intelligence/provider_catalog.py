"""Canonical metadata for live SERP adapters exposed by RASAi.

Free-tier labels are informational snapshots used for onboarding. They never alter
request budgets and must not be interpreted as a guarantee that a vendor will keep the
same commercial terms. Provider-enforced quotas remain authoritative.
"""
from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse


@dataclass(frozen=True, slots=True)
class SerpProviderRegistration:
    id: str
    display_name: str
    key_env: str
    engine: str
    credential_url: str
    documentation_url: str
    free_tier: bool
    free_tier_note: str
    pagination_mode: str = "fixed-10"


SERP_PROVIDER_REGISTRY: tuple[SerpProviderRegistration, ...] = (
    SerpProviderRegistration(
        id="serpapi",
        display_name="SerpApi / Google",
        key_env="RASAI_SERPAPI_API_KEY",
        engine="google",
        credential_url="https://serpapi.com/manage-api-key",
        documentation_url="https://serpapi.com/search-api",
        free_tier=True,
        free_tier_note="Plano gratuito verificado em 2026-09: 250 pesquisas/mês; confirme a oferta atual no provider.",
    ),
    SerpProviderRegistration(
        id="serpapi-bing",
        display_name="SerpApi / Bing",
        key_env="RASAI_SERPAPI_API_KEY",
        engine="bing",
        credential_url="https://serpapi.com/manage-api-key",
        documentation_url="https://serpapi.com/bing-search-api",
        free_tier=True,
        free_tier_note="Compartilha a franquia da conta SerpApi; confirme a oferta atual no provider.",
        pagination_mode="provider-driven",
    ),
    SerpProviderRegistration(
        id="zenserp",
        display_name="Zenserp / Google",
        key_env="RASAI_ZENSERP_API_KEY",
        engine="google",
        credential_url="https://app.zenserp.com/",
        documentation_url="https://zenserp.com/",
        free_tier=True,
        free_tier_note="Plano gratuito verificado em 2026-09: 50 pesquisas/mês; confirme a oferta atual no provider.",
    ),
    SerpProviderRegistration(
        id="scrapingdog",
        display_name="ScrapingDog / Google",
        key_env="RASAI_SCRAPINGDOG_API_KEY",
        engine="google",
        credential_url="https://api.scrapingdog.com/",
        documentation_url="https://www.scrapingdog.com/documentation/google-search-api/",
        free_tier=True,
        free_tier_note="Plano gratuito verificado em 2026-09: 200 créditos/mês; Google Search padrão custa 5 créditos por request (aprox. 40 requests).",
    ),
)


def _validate_registry() -> None:
    ids = [item.id for item in SERP_PROVIDER_REGISTRY]
    if len(ids) != len(set(ids)):
        raise RuntimeError("duplicate canonical SERP provider id in RASAi registry")
    if any(not item.id.strip() or item.id != item.id.strip().casefold() for item in SERP_PROVIDER_REGISTRY):
        raise RuntimeError("SERP provider ids must be non-empty lowercase canonical tokens")
    for item in SERP_PROVIDER_REGISTRY:
        if not item.key_env.strip():
            raise RuntimeError(f"SERP provider {item.id} has no credential environment variable")
        if not item.engine.strip():
            raise RuntimeError(f"SERP provider {item.id} has no canonical engine")
        if item.pagination_mode not in {"fixed-10", "provider-driven"}:
            raise RuntimeError(
                f"SERP provider {item.id} has unsupported pagination mode {item.pagination_mode!r}"
            )
        for label, url in (
            ("credential", item.credential_url),
            ("documentation", item.documentation_url),
        ):
            parsed = urlparse(url)
            if parsed.scheme != "https" or not parsed.netloc:
                raise RuntimeError(
                    f"SERP provider {item.id} has invalid {label} URL; HTTPS is required"
                )
        if item.free_tier and not item.free_tier_note.strip():
            raise RuntimeError(f"SERP provider {item.id} is free-tier but has no quota note")


_validate_registry()
_BY_ID = {item.id: item for item in SERP_PROVIDER_REGISTRY}


def serp_provider_registration(provider_id: str) -> SerpProviderRegistration | None:
    return _BY_ID.get(provider_id.strip().casefold())


def serp_provider_ids() -> tuple[str, ...]:
    return tuple(item.id for item in SERP_PROVIDER_REGISTRY)


def serp_provider_key_env(provider_id: str) -> str:
    registration = serp_provider_registration(provider_id)
    if registration is None:
        raise ValueError(f"unknown SERP provider: {provider_id}")
    return registration.key_env


def serp_provider_key_envs() -> tuple[str, ...]:
    return tuple(dict.fromkeys(item.key_env for item in SERP_PROVIDER_REGISTRY))


def serp_provider_engine(provider_id: str) -> str:
    registration = serp_provider_registration(provider_id)
    if registration is None:
        raise ValueError(f"unknown SERP provider: {provider_id}")
    return registration.engine


def free_serp_provider_ids() -> tuple[str, ...]:
    return tuple(item.id for item in SERP_PROVIDER_REGISTRY if item.free_tier)
