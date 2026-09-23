"""Interactive-console registration for the configurable AI model catalog."""
from __future__ import annotations

from dataclasses import replace

from rasai.ai_model_catalog import MODEL_FILE_ENV, MODEL_SOURCE_ENV

OPERATOR_MODEL_FILE = "config/ai-models.toml"


def install() -> None:
    # Task/persona profile settings are another AI catalog surface and must always join
    # the managed console environment when model configuration is installed. Install it
    # before the model idempotency guard so repeated composition cannot omit the newer
    # public settings in long-lived/test processes.
    from rasai.ai_task_profile_console import install as install_ai_task_profile_console

    install_ai_task_profile_console()

    from rasai import console_environment as base

    if getattr(base, "_rasai_ai_model_environment_installed", False):
        return

    original_fixed_specs = base._fixed_specs
    original_validate = base._validate

    for name in (MODEL_SOURCE_ENV, MODEL_FILE_ENV):
        if name not in base.ENV_NAMES:
            base.ENV_NAMES = (*base.ENV_NAMES, name)

    def fixed_specs_with_ai_models():
        items = list(original_fixed_specs())
        by_name = {item.name: index for index, item in enumerate(items)}
        specs = (
            base.EnvironmentSpec(
                MODEL_SOURCE_ENV,
                "IA - modelos e reasoning",
                "Seleciona a origem do catálogo de modelos usados pelos providers já integrados ao RASAi.",
                "enum",
                ("factory", "file", "auto"),
                "auto",
                required_when=(
                    "Nunca. auto usa config/ai-models.toml quando presente e a baseline de fábrica quando ausente; "
                    "file exige o TOML configurado; factory ignora o arquivo do operador."
                ),
                impact=(
                    "Controla modelos habilitados, defaults, reasoning permitido e elegibilidade ao AUTO. "
                    "Não cria um provider novo nem altera protocolo, autenticação ou endpoint do adapter."
                ),
                example="RASAI_AI_MODELS_SOURCE=auto",
                source="docs/AI_MODEL_CONFIGURATION.md",
                notes=(
                    "Alterações no arquivo do operador entram na próxima AUD sem reiniciar o console; "
                    "a execução iniciada usa snapshot imutável."
                ),
            ),
            base.EnvironmentSpec(
                MODEL_FILE_ENV,
                "IA - modelos e reasoning",
                "Caminho do catálogo TOML editável de modelos usado quando a origem é file/auto.",
                "caminho de arquivo TOML",
                default=OPERATOR_MODEL_FILE,
                required_when=f"Obrigatório quando {MODEL_SOURCE_ENV}=file.",
                impact=(
                    "Permite adicionar, desativar ou alterar modelos de providers já integrados sem mudar código, "
                    "desde que o modelo use o mesmo contrato técnico do adapter existente."
                ),
                example="RASAI_AI_MODELS_FILE=config/ai-models.toml",
                source="docs/AI_MODEL_CONFIGURATION.md",
                notes="Arquivo humano na pasta config/; credenciais continuam fora do catálogo.",
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

    def validate_with_ai_models(name: str, raw: str) -> str:
        if name == MODEL_SOURCE_ENV:
            value = raw.strip().casefold()
            if value not in {"factory", "file", "auto"}:
                raise ValueError("use factory, file ou auto")
            return value
        if name == MODEL_FILE_ENV:
            value = raw.strip()
            if not value:
                raise ValueError("informe um caminho TOML ou remova o override")
            if "\x00" in value:
                raise ValueError("caminho inválido")
            return value
        return original_validate(name, raw)

    base._fixed_specs = fixed_specs_with_ai_models
    base._validate = validate_with_ai_models
    base.SPECS = base.environment_specs()
    base.SPEC_BY_NAME = {spec.name: spec for spec in base.SPECS}
    base._rasai_ai_model_environment_installed = True

    from rasai import console_provider_environment as facade

    facade.refresh_specs()
