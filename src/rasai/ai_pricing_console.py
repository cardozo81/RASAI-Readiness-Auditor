"""Interactive-console registration for configurable AI pricing.

Pricing source/path are non-secret operator settings. The human-editable catalog lives
under root ``config/``; packaged defaults remain an internal product baseline.
"""
from __future__ import annotations

from dataclasses import replace

from rasai.ai_pricing_catalog import PRICING_FILE_ENV, PRICING_SOURCE_ENV

OPERATOR_PRICING_FILE = "config/ai-pricing.toml"


def install() -> None:
    from rasai import console_environment as base

    if getattr(base, "_rasai_ai_pricing_environment_installed", False):
        return

    original_fixed_specs = base._fixed_specs
    original_validate = base._validate

    for name in (PRICING_SOURCE_ENV, PRICING_FILE_ENV):
        if name not in base.ENV_NAMES:
            base.ENV_NAMES = (*base.ENV_NAMES, name)

    def fixed_specs_with_ai_pricing():
        items = list(original_fixed_specs())
        by_name = {item.name: index for index, item in enumerate(items)}
        specs = (
            base.EnvironmentSpec(
                PRICING_SOURCE_ENV,
                "IA - modelos e reasoning",
                "Seleciona a origem da política de preços usada nas estimativas e no ranking econômico do AI=AUTO.",
                "enum",
                ("factory", "file", "auto"),
                "auto",
                required_when=(
                    "Nunca. auto usa config/ai-pricing.toml quando presente e a baseline de fábrica quando ausente; "
                    "file exige o TOML configurado; factory ignora o arquivo do operador."
                ),
                impact=(
                    "Pode alterar estimativas de custo e a ordem econômica dos providers no AI=AUTO; "
                    "não altera credenciais, elegibilidade, quarentena ou circuit breaker."
                ),
                example="RASAI_AI_PRICING_SOURCE=auto",
                source="docs/AI_PRICING_CONFIGURATION.md",
                notes=(
                    "Alterações no arquivo do operador entram na próxima AUD sem reiniciar o console; "
                    "a execução iniciada usa snapshot imutável."
                ),
            ),
            base.EnvironmentSpec(
                PRICING_FILE_ENV,
                "IA - modelos e reasoning",
                "Caminho do catálogo TOML editável usado quando a origem de pricing é file/auto.",
                "caminho de arquivo TOML",
                default=OPERATOR_PRICING_FILE,
                required_when=f"Obrigatório quando {PRICING_SOURCE_ENV}=file.",
                impact=(
                    "O conteúdo do arquivo determina preços, vigências, janelas e faixas de contexto "
                    "usadas pelo motor de custo."
                ),
                example="RASAI_AI_PRICING_FILE=config/ai-pricing.toml",
                source="docs/AI_PRICING_CONFIGURATION.md",
                notes="Arquivo humano na pasta config/; não contém segredos.",
            ),
        )
        for spec in specs:
            index = by_name.get(spec.name)
            if index is None:
                items.append(spec)
            else:
                items[index] = replace(items[index], **{
                    field: getattr(spec, field)
                    for field in (
                        "category", "purpose", "value_type", "accepted", "default",
                        "required_when", "sensitive", "impact", "example", "source", "notes",
                    )
                })
        return tuple(items)

    def validate_with_ai_pricing(name: str, raw: str) -> str:
        if name == PRICING_SOURCE_ENV:
            value = raw.strip().casefold()
            if value not in {"factory", "file", "auto"}:
                raise ValueError("use factory, file ou auto")
            return value
        if name == PRICING_FILE_ENV:
            value = raw.strip()
            if not value:
                raise ValueError("informe um caminho TOML ou remova o override")
            if "\x00" in value:
                raise ValueError("caminho inválido")
            return value
        return original_validate(name, raw)

    base._fixed_specs = fixed_specs_with_ai_pricing
    base._validate = validate_with_ai_pricing
    base.SPECS = base.environment_specs()
    base.SPEC_BY_NAME = {spec.name: spec for spec in base.SPECS}
    base._rasai_ai_pricing_environment_installed = True

    # Provider-aware facade is imported early by console_entrypoint. Refresh it after the
    # base catalog changes so the final UI and Restore Defaults see these variables.
    from rasai import console_provider_environment as facade

    facade.refresh_specs()
