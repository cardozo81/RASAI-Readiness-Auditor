"""Interactive-console registration for configurable AI task/persona profiles."""
from __future__ import annotations

from dataclasses import replace

from rasai.ai_task_profiles import (
    DEFAULT_USER_PROFILE_FILE,
    PROFILE_FILE_ENV,
    PROFILE_SOURCE_ENV,
)


def install() -> None:
    from rasai import console_environment as base

    if getattr(base, "_rasai_ai_task_profile_environment_installed", False):
        return

    original_fixed_specs = base._fixed_specs
    original_validate = base._validate

    for name in (PROFILE_SOURCE_ENV, PROFILE_FILE_ENV):
        if name not in base.ENV_NAMES:
            base.ENV_NAMES = (*base.ENV_NAMES, name)

    def fixed_specs_with_ai_task_profiles():
        items = list(original_fixed_specs())
        by_name = {item.name: index for index, item in enumerate(items)}
        specs = (
            base.EnvironmentSpec(
                PROFILE_SOURCE_ENV,
                "IA - perfis de tarefa",
                "Seleciona a origem do catálogo versionado de personas/especializações usado nas chamadas de IA.",
                "enum",
                ("factory", "file", "auto"),
                "auto",
                required_when=(
                    "Nunca. auto usa o arquivo configurado quando existir e recua para o catálogo de fábrica; "
                    "file exige o TOML configurado; factory ignora overrides locais."
                ),
                impact=(
                    "Controla somente papel, objetivo, competências e orientação da persona por tipo de tarefa. "
                    "Não altera provider/modelo, preço, retry, fallback, quarentena, schema, scoring, segurança ou evidências."
                ),
                example="RASAI_AI_TASK_PROFILES_SOURCE=auto",
                source="docs/AI_TASK_PROFILES.md",
                notes="Configuração inválida falha antes de qualquer chamada paga. Restore Defaults volta para auto.",
            ),
            base.EnvironmentSpec(
                PROFILE_FILE_ENV,
                "IA - perfis de tarefa",
                "Caminho do TOML editável contendo overrides versionados das personas de IA.",
                "caminho de arquivo TOML",
                default=DEFAULT_USER_PROFILE_FILE,
                required_when=f"Obrigatório quando {PROFILE_SOURCE_ENV}=file.",
                impact=(
                    "Permite ajuste fino de personas sem modificar os contratos técnicos protegidos do RASAi. "
                    "Perfis omitidos no arquivo continuam herdando os valores de fábrica."
                ),
                example=f"{PROFILE_FILE_ENV}={DEFAULT_USER_PROFILE_FILE}",
                source="docs/AI_TASK_PROFILES.md",
                notes="Não contém credenciais. Campos fora de version, role, objective, competencies e guidance são rejeitados.",
            ),
        )
        for spec in specs:
            index = by_name.get(spec.name)
            if index is None:
                items.append(spec)
            else:
                items[index] = replace(
                    items[index],
                    **{
                        field: getattr(spec, field)
                        for field in (
                            "category",
                            "purpose",
                            "value_type",
                            "accepted",
                            "default",
                            "required_when",
                            "sensitive",
                            "impact",
                            "example",
                            "source",
                            "notes",
                        )
                    },
                )
        return tuple(items)

    def validate_with_ai_task_profiles(name: str, raw: str) -> str:
        if name == PROFILE_SOURCE_ENV:
            value = raw.strip().casefold()
            if value not in {"factory", "file", "auto"}:
                raise ValueError("use factory, file ou auto")
            return value
        if name == PROFILE_FILE_ENV:
            value = raw.strip()
            if not value:
                raise ValueError("informe um caminho TOML ou remova o override")
            if "\x00" in value:
                raise ValueError("caminho inválido")
            return value
        return original_validate(name, raw)

    base._fixed_specs = fixed_specs_with_ai_task_profiles
    base._validate = validate_with_ai_task_profiles
    base.SPECS = base.environment_specs()
    base.SPEC_BY_NAME = {spec.name: spec for spec in base.SPECS}
    base._rasai_ai_task_profile_environment_installed = True

    from rasai import console_provider_environment as facade

    facade.refresh_specs()
