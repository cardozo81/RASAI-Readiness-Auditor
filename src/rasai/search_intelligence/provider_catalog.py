"""Canonical metadata for live SERP adapters exposed by RASAi.

Free-tier labels are informational snapshots used for onboarding. They never alter
request budgets and must not be interpreted as a guarantee that a vendor will keep the
same commercial terms. Provider-enforced quotas remain authoritative.
"""
from __future__ import annotations

from dataclasses import dataclass


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


def free_serp_provider_ids() -> tuple[str, ...]:
    return tuple(item.id for item in SERP_PROVIDER_REGISTRY if item.free_tier)
