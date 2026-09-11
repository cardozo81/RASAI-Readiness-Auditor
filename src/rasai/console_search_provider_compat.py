"""Provider-aware compatibility layer for the interactive Search console.

Search Intelligence predates the live provider registry and originally assumed every
live credential was a SerpApi key. Keep the existing console interaction intact while
resolving provider capabilities and credentials dynamically from the canonical catalog.
"""
from __future__ import annotations

import os
from types import ModuleType
from typing import Mapping

from rasai.search_intelligence.config import SerpRuntimeConfig, provider_key_env
from rasai.search_intelligence.provider_catalog import serp_provider_registration
from rasai.search_intelligence.runtime import (
    projected_http_request_ceiling,
    validate_live_provider_engine,
)


def install(console_search_module: ModuleType) -> None:
    if getattr(console_search_module, "_provider_catalog_compat_installed", False):
        return

    original_configure = console_search_module.configure_search_intelligence

    def configured_search(state: object, env: Mapping[str, str] | None = None) -> SerpRuntimeConfig:
        environment = os.environ if env is None else env
        config = SerpRuntimeConfig.from_environment(environment)
        queries = tuple(getattr(state, "search_queries", ()) or ())
        if not queries:
            return config
        if config.mode == "disabled":
            raise ValueError(
                "Search Intelligence possui termos, mas RASAI_SERP_MODE está disabled; use live ou fixture"
            )
        if len(queries) > config.max_queries:
            raise ValueError(
                f"{len(queries)} termo(s) excedem RASAI_SERP_MAX_QUERIES={config.max_queries}"
            )
        depth = int(getattr(state, "search_depth", 20))
        if depth <= 0:
            raise ValueError("profundidade SERP deve ser > 0")
        if depth > config.max_depth:
            raise ValueError(
                f"profundidade SERP {depth} excede RASAI_SERP_MAX_DEPTH={config.max_depth}"
            )
        device = str(getattr(state, "search_device", "mobile")).casefold()
        if device not in {"mobile", "desktop"}:
            raise ValueError("dispositivo SERP deve ser mobile ou desktop")
        if config.mode == "live":
            registration = serp_provider_registration(config.provider)
            if registration is None:
                raise ValueError(f"provider SERP live desconhecido: {config.provider}")
            validate_live_provider_engine(config.provider, registration.engine)
            key_env = provider_key_env(config.provider)
            if not (environment.get(key_env) or "").strip():
                raise ValueError(
                    f"{key_env} não configurada para Search Intelligence live; "
                    f"obtenha a chave em {registration.credential_url}"
                )
            projected = projected_http_request_ceiling(
                config, depths=(depth for _ in queries)
            )
            if registration.pagination_mode != "provider-driven" and projected > config.max_requests:
                raise ValueError(
                    f"teto projetado de {projected} requests SERP excede "
                    f"RASAI_SERP_MAX_REQUESTS={config.max_requests}"
                )
        return config

    def configure(state) -> None:
        try:
            config = SerpRuntimeConfig.from_environment()
            if config.mode == "live":
                registration = serp_provider_registration(config.provider)
                if registration is not None:
                    # The legacy renderer reads this module global. Point it at the
                    # selected provider credential before rendering status/prompts.
                    console_search_module.SERPAPI_KEY_ENV = registration.key_env
                    print(
                        f"\nProvider SERP: {registration.id} ({registration.display_name})\n"
                        f"Engine: {registration.engine} | Paginação: {registration.pagination_mode}\n"
                        f"Chave/login: {registration.credential_url}\n"
                        f"Plano gratuito: {'sim' if registration.free_tier else 'não'} | "
                        f"{registration.free_tier_note}"
                    )
        except ValueError:
            pass
        original_configure(state)

    console_search_module._configured_search = configured_search
    console_search_module.configure_search_intelligence = configure
    console_search_module._provider_catalog_compat_installed = True
