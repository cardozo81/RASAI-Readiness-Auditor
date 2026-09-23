"""Final configuration-detail guidance for open-domain values.

The runtime remains the validation authority.  This layer makes accepted format,
example and activation criteria visible before the operator types an open value.
"""
from __future__ import annotations

from rasai.configuration_value_labels import configuration_value_info

from dataclasses import replace
from typing import Any

from rasai.console_ui import CYAN, paint


def _patch_dynatrace_metadata() -> None:
    from rasai import console_environment as base
    from rasai import console_provider_environment as facade
    from rasai.m25_cli import (
        DYNATRACE_APPLICATION_ID_ENV,
        DYNATRACE_BASE_URL_ENV,
        DYNATRACE_CONFIG_JSON_ENV,
        DYNATRACE_IMPORT_ENV,
    )
    from rasai.m25_dynatrace import DYNATRACE_API_TOKEN_ENV

    source = "docs/SYNTHETIC_USER_EXPERIENCE_APDEX.md"
    specs = list(base.SPECS)
    changed = False
    for index, spec in enumerate(specs):
        if spec.name == DYNATRACE_IMPORT_ENV:
            specs[index] = replace(
                spec,
                purpose="Habilita importação live da calibração Dynatrace para o Apdex de experiência.",
                required_when=(
                    "Opcional. Use true somente para importação live. Um RASAI_DYNATRACE_CONFIG_JSON "
                    "válido é uma alternativa offline e não exige este toggle."
                ),
                notes=(
                    "No modo live, base URL + Application ID + DYNATRACE_API_TOKEN são necessários. "
                    "O perfil de execução não inventa esses valores."
                ),
                source=source,
            )
            changed = True
        elif spec.name == DYNATRACE_BASE_URL_ENV:
            specs[index] = replace(
                spec,
                value_type="URL HTTPS absoluta do ambiente Dynatrace",
                purpose="Base HTTPS do ambiente Dynatrace usada somente pela Config API na importação live.",
                required_when=(
                    "Somente no modo live: RASAI_APDEX_DYNATRACE_IMPORT=true e "
                    "RASAI_DYNATRACE_CONFIG_JSON ausente."
                ),
                example="https://SEU-AMBIENTE.live.dynatrace.com",
                notes="Não inclua credenciais, fragmento ou endpoint /api/...; informe apenas a base do ambiente.",
                source=source,
            )
            changed = True
        elif spec.name == DYNATRACE_APPLICATION_ID_ENV:
            specs[index] = replace(
                spec,
                value_type="identificador de Web Application Dynatrace (texto não vazio)",
                purpose=(
                    "Identifica a Web Application cuja configuração de Load Action/KPM/thresholds será "
                    "lida pela Config API."
                ),
                required_when=(
                    "Somente no modo live: RASAI_APDEX_DYNATRACE_IMPORT=true e "
                    "RASAI_DYNATRACE_CONFIG_JSON ausente."
                ),
                example="APPLICATION-XXXXXXXXXXXX",
                notes=(
                    "Use o ID técnico da Web Application exibido/retornado pelo Dynatrace, não o nome amigável. "
                    "O runtime não restringe o texto a um prefixo fixo para preservar compatibilidade com IDs válidos do provider."
                ),
                source=source,
            )
            changed = True
        elif spec.name == DYNATRACE_CONFIG_JSON_ENV:
            specs[index] = replace(
                spec,
                value_type="caminho para arquivo JSON existente",
                purpose=(
                    "Importa offline uma configuração exportada da Web Application Dynatrace para calibração "
                    "reproduzível do Apdex de experiência."
                ),
                required_when=(
                    "Alternativa ao modo live. Quando definido, o JSON é preferido e base URL, Application ID "
                    "e token não são necessários para carregar a calibração."
                ),
                example=r"C:\dados\dynatrace-web-application.json",
                notes=(
                    "O arquivo deve existir, conter um objeto JSON de configuração compatível e fornecer "
                    "thresholds de Load Action utilizáveis. O payload bruto não é persistido no relatório."
                ),
                source=source,
            )
            changed = True
        elif spec.name == DYNATRACE_API_TOKEN_ENV:
            specs[index] = replace(
                spec,
                purpose="Token da Config API Dynatrace usado exclusivamente na importação live de calibração.",
                required_when=(
                    "Somente no modo live: RASAI_APDEX_DYNATRACE_IMPORT=true e "
                    "RASAI_DYNATRACE_CONFIG_JSON ausente."
                ),
                notes="Secret: permanece fora do INI, SQLite, HTML e logs sanitizados.",
                source=source,
            )
            changed = True

    if changed:
        base.SPECS = tuple(specs)
        base.SPEC_BY_NAME = {spec.name: spec for spec in specs}
        facade.refresh_specs()


def _render_enrichment(spec: Any) -> None:
    from rasai import console_configuration_guidance as guidance

    print(f"Contexto       : {paint(guidance.context_for(spec), CYAN, bold=True)}")
    if spec.accepted:
        mode = (
            "seleção múltipla"
            if str(spec.value_type).casefold() in {"lista csv", "lista", "csv"}
            else "seleção única"
        )
        print(f"Como preencher : {mode}; escolha somente entre os valores apresentados pelo console.")
        print("Valores aceitos : " + ", ".join(configuration_value_info(spec.name, value) for value in spec.accepted))
    else:
        print(f"Como preencher : entrada específica validada pelo runtime; formato aceito: {spec.value_type}.")
        if getattr(spec, "example", ""):
            print(f"Exemplo válido  : {spec.example}")
    criterion = str(getattr(spec, "required_when", "") or "").strip()
    if criterion:
        print(f"Critério de uso : {criterion}")

    references = guidance.reference_lines(spec)
    source = str(getattr(spec, "source", "") or "").strip()
    if source and source != "docs/ENVIRONMENT_VARIABLES.md":
        references = (*references, f"Contrato RASAi: {source}")
    if references:
        print("Referências     :")
        for line in dict.fromkeys(references):
            print(f"  - {line}")


def install() -> None:
    """Install after all catalog enrichments so final metadata is what the user sees."""
    from rasai import console_configuration_guidance as guidance
    from rasai import console_provider_environment as facade

    if getattr(guidance, "_rasai_open_value_guidance_refined", False):
        return

    _patch_dynatrace_metadata()
    guidance.render_enrichment = _render_enrichment
    facade.render_enrichment = _render_enrichment
    guidance._rasai_open_value_guidance_refined = True
