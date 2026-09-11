"""Make the legacy environment catalog provider-registry aware.

The environment UI predates the extensible AI/SERP registries. This patch keeps the
existing interaction model but replaces closed provider enums/generic credential rows
with the current registry metadata, including the URL where a user obtains each key.
"""
from __future__ import annotations

from dataclasses import replace
from types import ModuleType

from rasai.provider_registry import provider_registrations
from rasai.search_intelligence.config import SERP_PROVIDER_ENV
from rasai.search_intelligence.provider_catalog import SERP_PROVIDER_REGISTRY
from rasai.search_intelligence.runtime import live_provider_ids


def install(console_environment: ModuleType) -> None:
    if getattr(console_environment, "_provider_registry_environment_installed", False):
        return

    original_validate = console_environment._validate

    def validate(name: str, raw: str) -> str:
        if name == SERP_PROVIDER_ENV:
            # Preserve the base validator's trimming/empty-value semantics without
            # invoking its obsolete closed provider enum.
            value = str(raw).strip().casefold()
            if not value:
                raise ValueError("valor vazio; remova a variável em vez de gravar vazio")
            if value not in set(live_provider_ids()):
                raise ValueError("use " + ", ".join(live_provider_ids()))
            return value
        return original_validate(name, raw)

    console_environment._validate = validate

    specs = list(console_environment.SPECS)
    by_name = {spec.name: index for index, spec in enumerate(specs)}

    provider_spec = console_environment.SPEC_BY_NAME.get(SERP_PROVIDER_ENV)
    if provider_spec is not None:
        specs[by_name[SERP_PROVIDER_ENV]] = replace(
            provider_spec,
            accepted=live_provider_ids(),
            notes=(
                "O provider selecionado determina a variável de credencial. "
                "O detalhe da credencial mostra a URL oficial de cadastro/login."
            ),
        )

    for registration in SERP_PROVIDER_REGISTRY:
        current = console_environment.SPEC_BY_NAME.get(registration.key_env)
        if current is None:
            continue
        replacement = replace(
            current,
            category="Search Intelligence / Observability",
            purpose=f"Credencial BYOK do provider {registration.display_name}.",
            value_type="segredo/API key",
            required_when=f"Obrigatória quando RASAI_SERP_MODE=live e RASAI_SERP_PROVIDER={registration.id}.",
            sensitive=True,
            impact="Consome quota/créditos do provider; os limites do RASAi não substituem a quota do fornecedor.",
            source=f"{registration.display_name} chave/login - {registration.credential_url}",
            notes=registration.free_tier_note,
        )
        specs[by_name[registration.key_env]] = replacement

    # AI specs are already generated from provider_registrations(); enrich notes with
    # canonical onboarding metadata without changing secret handling.
    ai_by_key = {registration.key_env: registration for registration in provider_registrations()}
    for index, spec in enumerate(specs):
        registration = ai_by_key.get(spec.name)
        if registration is None:
            continue
        notes = registration.auth_note or (
            f"Obtenha/gerencie a credencial em {registration.credential_url}. "
            f"Documentação: {registration.documentation_url}"
        )
        specs[index] = replace(
            spec,
            source=f"{registration.display_name} credencial/login - {registration.credential_url}",
            notes=notes,
        )

    console_environment.SPECS = tuple(specs)
    console_environment.SPEC_BY_NAME = {spec.name: spec for spec in console_environment.SPECS}
    console_environment._provider_registry_environment_installed = True
