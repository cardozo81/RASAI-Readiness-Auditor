"""Interactive-console configuration for external observational integrations."""
from __future__ import annotations

from rasai.external_observability_policy import (
    CLARITY_DAYS_ENV,
    CLARITY_DIMENSIONS_ENV,
    CLARITY_TOKEN_ENV,
    COMMON_CRAWL_INDEX_COUNT_ENV,
    COMMON_CRAWL_MAX_URLS_ENV,
    DEFAULT_CLARITY_DAYS,
    DEFAULT_CLARITY_DIMENSIONS,
    DEFAULT_COMMON_CRAWL_INDEX_COUNT,
    DEFAULT_COMMON_CRAWL_MAX_URLS,
    clarity_days,
    clarity_dimensions,
    common_crawl_index_count,
    common_crawl_max_urls,
    dimensions_csv,
)


def install() -> None:
    from rasai import console_config
    from rasai import console_environment as base
    from rasai import console_provider_environment as facade

    category = "Métricas e padrões"
    source = "docs/EXTERNAL_OBSERVABILITY_INTEGRATIONS.md"
    specs = list(base.SPECS)
    by_name = {spec.name: index for index, spec in enumerate(specs)}

    additions = (
        base.EnvironmentSpec(
            CLARITY_TOKEN_ENV,
            category,
            "Token JWT do Microsoft Clarity Data Export. Nunca é persistido no INI ou em artifacts.",
            "segredo/token",
            sensitive=True,
            required_when="Somente quando Microsoft Clarity estiver explicitamente habilitado.",
            impact="Sem cobrança de provider; sujeito à quota de 10 requests/dia/projeto.",
            source=source,
            notes="Gerado em Clarity > Settings > Data Export. O console trata o valor como segredo volátil/Windows User quando confirmado.",
        ),
        base.EnvironmentSpec(
            CLARITY_DAYS_ENV,
            category,
            "Janela móvel consultada no Microsoft Clarity Data Export.",
            "inteiro",
            accepted=("1", "2", "3"),
            default=str(DEFAULT_CLARITY_DAYS),
            required_when="Usado somente quando Microsoft Clarity estiver habilitado.",
            impact="Cada coleta consome 1 request da quota diária do projeto Clarity.",
            source=source,
            notes="1, 2 ou 3 correspondem às últimas 24, 48 ou 72 horas.",
        ),
        base.EnvironmentSpec(
            CLARITY_DIMENSIONS_ENV,
            category,
            "Dimensões do Clarity Data Export; até três valores separados por vírgula.",
            "lista",
            default=dimensions_csv(DEFAULT_CLARITY_DIMENSIONS),
            required_when="Usado somente quando Microsoft Clarity estiver habilitado.",
            impact="Não aumenta o número de requests; altera a granularidade do agregado retornado.",
            example="URL,Device",
            source=source,
            notes=(
                "Valores aceitos: Browser, Device, Country/Region, OS, Source, Medium, Campaign, Channel, URL. "
                "URL,Device é o default para preservar escopo de página e dispositivo quando a fonte fornecer ambos."
            ),
        ),
        base.EnvironmentSpec(
            COMMON_CRAWL_MAX_URLS_ENV,
            category,
            "Máximo de URLs auditadas consultadas por execução no Common Crawl; 0 desliga somente a subcoleta.",
            "inteiro",
            default=str(DEFAULT_COMMON_CRAWL_MAX_URLS),
            impact=(
                "Sem cobrança e sem credencial; cada URL multiplica requests pelo número de índices consultados. "
                "Quando há corroboração positiva qualificada, BR-GEO-060 pode contribuir no máximo 0,45 ponto no SARI Overall."
            ),
            source=source,
            notes="Faixa 0..25. O default é deliberadamente conservador para o serviço público.",
        ),
        base.EnvironmentSpec(
            COMMON_CRAWL_INDEX_COUNT_ENV,
            category,
            "Quantidade dos índices mensais mais recentes do Common Crawl consultados por URL.",
            "inteiro",
            default=str(DEFAULT_COMMON_CRAWL_INDEX_COUNT),
            impact="Sem cobrança; aumentar eleva requests e tempo de finalização, sem aumentar o peso máximo de BR-GEO-060.",
            source=source,
            notes="Faixa 1..6; não há consulta global a todo o histórico por default.",
        ),
    )
    for spec in additions:
        index = by_name.get(spec.name)
        if index is None:
            by_name[spec.name] = len(specs)
            specs.append(spec)
        else:
            specs[index] = spec

    base.SPECS = tuple(specs)
    base.SPEC_BY_NAME = {spec.name: spec for spec in specs}
    extra_names = tuple(spec.name for spec in additions)
    base.ENV_NAMES = tuple(dict.fromkeys((*base.ENV_NAMES, *extra_names)))
    console_config.ENV_NAMES = tuple(dict.fromkeys((*console_config.ENV_NAMES, *extra_names)))

    if not getattr(base, "_rasai_external_observability_validation", False):
        original_validate = base._validate

        def validate(name: str, raw: str) -> str:
            value = str(raw).strip()
            if name == CLARITY_DAYS_ENV:
                return str(clarity_days(value))
            if name == CLARITY_DIMENSIONS_ENV:
                return dimensions_csv(clarity_dimensions(value))
            if name == COMMON_CRAWL_MAX_URLS_ENV:
                return str(common_crawl_max_urls(value))
            if name == COMMON_CRAWL_INDEX_COUNT_ENV:
                return str(common_crawl_index_count(value))
            return original_validate(name, raw)

        base._validate = validate
        base._rasai_external_observability_validation = True

    facade.CATEGORIES = base.CATEGORIES
    facade.refresh_specs()

    # Interactive-console execution does not pass through the top-level CLI safety
    # installer. Keep the same pre-M9 bounded SARI corroboration, but do not install
    # the retired conventional HTML disclosure layer.
    from rasai.external_sari import install as install_external_sari
    install_external_sari()
