"""Register CAT-03 semantic context in the canonical interactive-console catalog.

This installer runs before INI preparation. Therefore the same EnvironmentSpec surface
controls discovery, validation, save/reload and defaults; there is no CAT-03-only shadow
configuration.
"""
from __future__ import annotations

from dataclasses import replace

from rasai.content_context import (
    CONTENT_ORIGIN_ENV,
    CONTENT_RISK_PROFILE_ENV,
    EXPERIENCE_REQUIREMENT_ENV,
    FRESHNESS_SENSITIVITY_ENV,
    INTENDED_AUDIENCE_ENV,
    PAGE_PURPOSE_ENV,
    YMYL_CATEGORY_ENV,
)
from rasai.property_semantic_profile import (
    BUSINESS_DESCRIPTION_ENV,
    BUSINESS_SECTOR_ENV,
    POSITIONING_ENV,
    PRIMARY_GOAL_ENV,
    PRIMARY_OFFERING_ENV,
    PROPERTY_SEMANTIC_PROFILE_ENV_NAMES,
    TARGET_AUDIENCE_PROFILE_ENV,
    build_property_semantic_profile,
)

PROPERTY_CATEGORY = "CAT-03 / Contexto da propriedade"
EDITORIAL_CATEGORY = "CAT-03 / Contexto editorial"
TRUST_CATEGORY = "CAT-03 / Risco e confiança"
_OLD_CONTENT_CATEGORY = "IA - contexto editorial / YMYL"

_PROPERTY_FIELD_BY_ENV = {
    BUSINESS_SECTOR_ENV: "business_sector",
    BUSINESS_DESCRIPTION_ENV: "business_description",
    PRIMARY_OFFERING_ENV: "primary_offering",
    TARGET_AUDIENCE_PROFILE_ENV: "target_audience_profile",
    PRIMARY_GOAL_ENV: "primary_goal",
    POSITIONING_ENV: "positioning",
}


def _validated_property_value(name: str, raw: str) -> str:
    field = _PROPERTY_FIELD_BY_ENV[name]
    profile = build_property_semantic_profile(**{field: raw})
    return str(getattr(profile, field))


def install() -> None:
    from rasai import console_environment as base

    if getattr(base, "_rasai_semantic_context_environment_installed", False):
        return

    original_fixed_specs = base._fixed_specs
    original_validate = base._validate

    for name in PROPERTY_SEMANTIC_PROFILE_ENV_NAMES:
        if name not in base.ENV_NAMES:
            base.ENV_NAMES = (*base.ENV_NAMES, name)

    # Keep the historical category during composition because older additive installers
    # still use it as an insertion anchor. CAT-03 variables themselves are re-owned by
    # the three categories below, so the old label no longer groups the content context.
    categories = list(base.CATEGORIES)
    insert_at = categories.index(_OLD_CONTENT_CATEGORY) if _OLD_CONTENT_CATEGORY in categories else (
        categories.index("Aplicação e execução") + 1 if "Aplicação e execução" in categories else 0
    )
    for category in reversed((PROPERTY_CATEGORY, EDITORIAL_CATEGORY, TRUST_CATEGORY)):
        if category not in categories:
            categories.insert(insert_at, category)
    base.CATEGORIES = tuple(categories)

    def fixed_specs_with_semantic_context():
        items = list(original_fixed_specs())
        by_name = {item.name: index for index, item in enumerate(items)}

        reclassifications = {
            PAGE_PURPOSE_ENV: (EDITORIAL_CATEGORY, "Finalidade principal da página usada para interpretar completude, intenção e CTA."),
            INTENDED_AUDIENCE_ENV: (EDITORIAL_CATEGORY, "Classificação do público pretendido da página; complementa o perfil detalhado da propriedade."),
            CONTENT_ORIGIN_ENV: (EDITORIAL_CATEGORY, "Origem editorial do conteúdo para interpretar responsabilidade e atribuição."),
            CONTENT_RISK_PROFILE_ENV: (TRUST_CATEGORY, "Perfil de risco editorial; YMYL eleva o rigor de confiança/evidência sem criar score proprietário."),
            YMYL_CATEGORY_ENV: (TRUST_CATEGORY, "Categoria YMYL aplicável ao conteúdo; contexto de risco, não fator de ranking."),
            EXPERIENCE_REQUIREMENT_ENV: (TRUST_CATEGORY, "Necessidade de experiência em primeira mão quando relevante ao propósito da página."),
            FRESHNESS_SENSITIVITY_ENV: (TRUST_CATEGORY, "Sensibilidade temporal para qualificar exigência de atualização e consistência de datas."),
        }
        for name, (category, purpose) in reclassifications.items():
            index = by_name.get(name)
            if index is not None:
                items[index] = replace(items[index], category=category, purpose=purpose)

        additions = (
            base.EnvironmentSpec(
                BUSINESS_SECTOR_ENV,
                PROPERTY_CATEGORY,
                "Ramo/setor declarado da propriedade digital.",
                "texto livre ou auto",
                default="auto",
                impact="Condiciona a análise de coerência; não altera scoring por si só.",
                example=f"{BUSINESS_SECTOR_ENV}=Software B2B",
                source="docs/SEMANTIC_COHERENCE_AUDIT.md",
                notes="Texto declarado pelo operador é tratado como dado não confiável, nunca como instrução ao provider.",
            ),
            base.EnvironmentSpec(
                BUSINESS_DESCRIPTION_ENV,
                PROPERTY_CATEGORY,
                "Descrição objetiva declarada do negócio/propriedade.",
                "texto livre ou auto; até 2000 caracteres",
                default="auto",
                impact="Usada para comparar contexto declarado com conteúdo e entidades observados.",
                example=f"{BUSINESS_DESCRIPTION_ENV}=Plataforma de gestão financeira empresarial",
                source="docs/SEMANTIC_COHERENCE_AUDIT.md",
            ),
            base.EnvironmentSpec(
                PRIMARY_OFFERING_ENV,
                PROPERTY_CATEGORY,
                "Oferta principal declarada (produto, serviço ou combinação).",
                "texto livre ou auto; até 500 caracteres",
                default="auto",
                impact="Permite avaliar coerência entre oferta declarada, conteúdo, entidades, schema e CTA.",
                example=f"{PRIMARY_OFFERING_ENV}=SaaS financeiro",
                source="docs/SEMANTIC_COHERENCE_AUDIT.md",
            ),
            base.EnvironmentSpec(
                TARGET_AUDIENCE_PROFILE_ENV,
                PROPERTY_CATEGORY,
                "Perfil detalhado do público-alvo declarado da propriedade.",
                "texto livre ou auto; até 1000 caracteres",
                default="auto",
                impact="Complementa RASAI_INTENDED_AUDIENCE com contexto semântico específico do negócio.",
                example=f"{TARGET_AUDIENCE_PROFILE_ENV}=CFOs e gestores financeiros de PMEs brasileiras",
                source="docs/SEMANTIC_COHERENCE_AUDIT.md",
            ),
            base.EnvironmentSpec(
                PRIMARY_GOAL_ENV,
                PROPERTY_CATEGORY,
                "Objetivo principal declarado do site/propriedade.",
                "texto livre ou auto; até 500 caracteres",
                default="auto",
                impact="Usado para avaliar coerência entre intenção, conteúdo e chamadas para ação.",
                example=f"{PRIMARY_GOAL_ENV}=Gerar demonstrações qualificadas",
                source="docs/SEMANTIC_COHERENCE_AUDIT.md",
            ),
            base.EnvironmentSpec(
                POSITIONING_ENV,
                PROPERTY_CATEGORY,
                "Posicionamento/proposta central declarada da propriedade.",
                "texto livre ou auto; até 1000 caracteres",
                default="auto",
                impact="Usado na leitura de consistência entre páginas e mensagem central observada.",
                example=f"{POSITIONING_ENV}=Reduzir complexidade do controle financeiro empresarial",
                source="docs/SEMANTIC_COHERENCE_AUDIT.md",
            ),
        )
        by_name = {item.name: index for index, item in enumerate(items)}
        for spec in additions:
            index = by_name.get(spec.name)
            if index is None:
                items.append(spec)
            else:
                items[index] = spec
        return tuple(items)

    def validate_with_semantic_context(name: str, raw: str) -> str:
        if name in _PROPERTY_FIELD_BY_ENV:
            return _validated_property_value(name, raw)
        return original_validate(name, raw)

    base._fixed_specs = fixed_specs_with_semantic_context
    base._validate = validate_with_semantic_context
    base.SPECS = base.environment_specs()
    base.SPEC_BY_NAME = {spec.name: spec for spec in base.SPECS}
    base._rasai_semantic_context_environment_installed = True

    from rasai import console_provider_environment as facade

    facade.CATEGORIES = base.CATEGORIES
    facade.refresh_specs()
