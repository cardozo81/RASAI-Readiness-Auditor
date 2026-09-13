"""Interactive-console reconciliation for standards service settings."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from urllib.parse import urlparse

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
from rasai.standards_gsc_policy import (
    DEFAULT_GSC_FINAL_DATA_LAG_DAYS,
    DEFAULT_GSC_SEARCH_ANALYTICS_DAYS,
    DEFAULT_GSC_SEARCH_MAX_ROWS,
    GSC_FINAL_DATA_LAG_DAYS_ENV,
    GSC_SEARCH_ANALYTICS_DAYS_ENV,
    GSC_SEARCH_MAX_ROWS_ENV,
    final_data_lag_days,
    search_analytics_days,
    search_max_rows,
)
from rasai.standards_runtime import install_console_service_catalog
from rasai.standards_service_registry import (
    GSC_SITE_URL_ENV,
    STANDARDS_MAX_URLS_ENV,
    STANDARDS_TIMEOUT_ENV,
    WEB_FEATURES_DATASET_ENV,
    boolean_value,
    services,
)


def _validate_gsc_site_url(raw: str) -> str:
    value = str(raw).strip()
    if not value:
        raise ValueError(f"{GSC_SITE_URL_ENV}: valor vazio; remova o override em vez de gravar vazio")
    if value.startswith("sc-domain:"):
        domain = value.removeprefix("sc-domain:").strip().strip(".")
        if not domain or "/" in domain or "://" in domain:
            raise ValueError(f"{GSC_SITE_URL_ENV}: use sc-domain:<domínio> válido")
        return f"sc-domain:{domain}"
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(
            f"{GSC_SITE_URL_ENV}: use propriedade URL-prefix http(s) absoluta ou sc-domain:<domínio>"
        )
    return value


def _ensure_nonsecret_service_context_specs(base_environment: object, console_config: object) -> None:
    """Upsert service context/settings so repeated installs repair catalog drift."""
    category = "Métricas e padrões"
    source = "docs/STANDARDS_METRICS_AND_SERVICES.md"
    external_source = "docs/EXTERNAL_OBSERVABILITY_INTEGRATIONS.md"
    specs = list(base_environment.SPECS)
    by_name = {spec.name: index for index, spec in enumerate(specs)}
    additions = (
        base_environment.EnvironmentSpec(
            GSC_SITE_URL_ENV,
            category,
            "Propriedade Google Search Console usada por Search Analytics, Sitemaps e URL Inspection.",
            "texto",
            required_when="Obrigatória quando Google Search Console estiver habilitado.",
            sensitive=False,
            impact="Sem custo externo direto; restringe as consultas à propriedade autenticada configurada.",
            example="sc-domain:example.com",
            source=source,
            notes=(
                "Aceita propriedade de domínio no formato sc-domain:<domínio> ou propriedade "
                "URL-prefix http(s) absoluta. É configuração não secreta e pode ser persistida no INI."
            ),
        ),
        base_environment.EnvironmentSpec(
            GSC_SEARCH_ANALYTICS_DAYS_ENV,
            category,
            "Dias de Search Analytics finalizados coletados automaticamente por auditoria; 0 desliga somente essa subcoleta.",
            "inteiro",
            default=str(DEFAULT_GSC_SEARCH_ANALYTICS_DAYS),
            impact="Aumentar o período aumenta carga/quota no Search Console.",
            source=source,
            notes="Faixa aceita: 0 a 31 dias.",
        ),
        base_environment.EnvironmentSpec(
            GSC_SEARCH_MAX_ROWS_ENV,
            category,
            "Teto de linhas de Search Analytics persistidas por auditoria.",
            "inteiro",
            default=str(DEFAULT_GSC_SEARCH_MAX_ROWS),
            impact="Aumentar o teto pode elevar chamadas paginadas, armazenamento e tempo de execução.",
            source=source,
            notes="Faixa aceita: 1 a 50000 linhas.",
        ),
        base_environment.EnvironmentSpec(
            GSC_FINAL_DATA_LAG_DAYS_ENV,
            category,
            "Defasagem usada para preferir dados Search Analytics finalizados.",
            "inteiro",
            default=str(DEFAULT_GSC_FINAL_DATA_LAG_DAYS),
            impact="Sem custo direto; altera o período consultado.",
            source=source,
            notes="Default 3 dias, alinhado à disponibilidade típica documentada pelo Google; faixa 0 a 30.",
        ),
        base_environment.EnvironmentSpec(
            WEB_FEATURES_DATASET_ENV,
            category,
            (
                "Caminho local para um arquivo de dataset versionado do projeto WebDX/web-features. "
                "É usado como requisito da capacidade Web Platform Baseline; não é uma enumeração."
            ),
            "caminho de arquivo existente",
            default=None,
            required_when=(
                "Opcional. Necessário para configurar o requisito de dataset da análise Web Platform Baseline. "
                "Sem ele, o serviço fica NOT_CONFIGURED."
            ),
            sensitive=False,
            impact="Leitura local; sem chamada externa e sem custo de provider.",
            example=r"C:\dados\web-features\web-features.json",
            source=(
                "docs/WEB_PLATFORM_BASELINE.md | dataset oficial: "
                "https://github.com/web-platform-dx/web-features"
            ),
            notes=(
                "Valor permitido: qualquer caminho para arquivo existente acessível ao processo. "
                "O runtime atual valida a existência e registra a referência, mas ainda não possui o detector/mapeador "
                "versionado de uso de features; portanto a análise Baseline permanece NO_DATA mesmo com o arquivo "
                "configurado. Não interpretar esta variável, isoladamente, como capacidade Baseline plenamente ativa."
            ),
        ),
        base_environment.EnvironmentSpec(
            CLARITY_TOKEN_ENV,
            category,
            "Token JWT do Microsoft Clarity Data Export usado somente para agregados observacionais.",
            "segredo/token",
            sensitive=True,
            required_when="Somente quando Microsoft Clarity estiver explicitamente habilitado.",
            impact="Sem cobrança de provider; sujeito à quota diária do projeto Clarity.",
            source=external_source,
            notes="Nunca é persistido no INI, AuditJob, artifacts ou HTML.",
        ),
        base_environment.EnvironmentSpec(
            CLARITY_DAYS_ENV,
            category,
            "Janela móvel consultada no Microsoft Clarity Data Export.",
            "enum inteiro",
            accepted=("1", "2", "3"),
            default=str(DEFAULT_CLARITY_DAYS),
            required_when="Usado somente quando Microsoft Clarity estiver habilitado.",
            impact="Cada coleta consome uma request da quota diária do projeto.",
            source=external_source,
            notes="1, 2 e 3 representam as últimas 24, 48 ou 72 horas.",
        ),
        base_environment.EnvironmentSpec(
            CLARITY_DIMENSIONS_ENV,
            category,
            "Dimensões do Microsoft Clarity Data Export; URL é obrigatória e até três dimensões são aceitas.",
            "lista CSV",
            default=dimensions_csv(DEFAULT_CLARITY_DIMENSIONS),
            required_when="Usado somente quando Microsoft Clarity estiver habilitado.",
            impact="Altera somente a granularidade do agregado; não cria requests adicionais.",
            example="URL,Device",
            source=external_source,
            notes="Device permanece explícito quando a fonte o retorna; não é inferido para dados sem dimensão de dispositivo.",
        ),
        base_environment.EnvironmentSpec(
            COMMON_CRAWL_MAX_URLS_ENV,
            category,
            "Máximo de URLs auditadas consultadas por execução no Common Crawl; 0 desliga somente a subcoleta.",
            "inteiro",
            default=str(DEFAULT_COMMON_CRAWL_MAX_URLS),
            impact="Sem cobrança/credencial; limita requests ao índice público e não altera o peso máximo do SARI.",
            source=external_source,
            notes="Faixa 0..25; default conservador para reduzir carga e exposição pública.",
        ),
        base_environment.EnvironmentSpec(
            COMMON_CRAWL_INDEX_COUNT_ENV,
            category,
            "Quantidade de índices mensais recentes do Common Crawl consultados por URL.",
            "inteiro",
            default=str(DEFAULT_COMMON_CRAWL_INDEX_COUNT),
            impact="Sem cobrança; aumentar eleva requests e tempo de finalização.",
            source=external_source,
            notes="Faixa 1..6; não consulta todo o histórico por default.",
        ),
    )
    for spec in additions:
        index = by_name.get(spec.name)
        if index is None:
            by_name[spec.name] = len(specs)
            specs.append(spec)
        else:
            specs[index] = spec

    credential_driven = {
        item.enabled_env: item
        for item in services()
        if item.credential_envs and item.auto_enable_with_credentials
    }
    for index, spec in enumerate(specs):
        item = credential_driven.get(spec.name)
        if item is None:
            continue
        specs[index] = replace(
            spec,
            default=None,
            required_when=(
                "Override opcional. Sem override, ativa automaticamente somente quando "
                "credencial e demais configurações obrigatórias estiverem presentes."
            ),
            notes=(
                f"Relação com RASAi: {item.relation_degree}/5. Escopo: {', '.join(item.scopes)}. "
                "Use false para desligamento explícito mesmo quando os requisitos estiverem configurados."
            ),
        )

    base_environment.SPECS = tuple(specs)
    base_environment.SPEC_BY_NAME = {spec.name: spec for spec in specs}
    extra_names = tuple(spec.name for spec in additions)
    base_environment.ENV_NAMES = tuple(dict.fromkeys((*base_environment.ENV_NAMES, *extra_names)))
    console_config.ENV_NAMES = tuple(dict.fromkeys((*console_config.ENV_NAMES, *extra_names)))


def install() -> None:
    from rasai import console_config
    from rasai import console_environment as base_environment
    from rasai import console_provider_environment as facade

    base_environment._rasai_standards_service_catalog = False
    install_console_service_catalog()
    _ensure_nonsecret_service_context_specs(base_environment, console_config)

    if getattr(base_environment, "_rasai_standards_console_validation", False):
        facade.CATEGORIES = base_environment.CATEGORIES
        facade.refresh_specs()
        return

    enabled_names = {item.enabled_env for item in services()}
    original_validate = base_environment._validate

    def validate(name: str, raw: str) -> str:
        value = str(raw).strip()
        if name in enabled_names:
            boolean_value(value, default=False)
            return "true" if value.casefold() in {"1", "true", "yes", "on"} else "false"
        if name == STANDARDS_MAX_URLS_ENV:
            parsed = int(value)
            if parsed < 0:
                raise ValueError(f"{name}: use inteiro >= 0")
            return str(parsed)
        if name == STANDARDS_TIMEOUT_ENV:
            parsed = float(value)
            if parsed <= 0 or parsed >= 3600:
                raise ValueError(f"{name}: use número > 0 e < 3600")
            return f"{parsed:g}"
        if name == WEB_FEATURES_DATASET_ENV:
            path = Path(value).expanduser()
            if not path.is_file():
                raise ValueError(
                    f"{name}: informe o caminho para um arquivo web-features versionado existente; "
                    "não há lista fechada de valores"
                )
            return str(path)
        if name == GSC_SITE_URL_ENV:
            return _validate_gsc_site_url(value)
        if name == GSC_SEARCH_ANALYTICS_DAYS_ENV:
            return str(search_analytics_days(value))
        if name == GSC_SEARCH_MAX_ROWS_ENV:
            return str(search_max_rows(value))
        if name == GSC_FINAL_DATA_LAG_DAYS_ENV:
            return str(final_data_lag_days(value))
        if name == CLARITY_DAYS_ENV:
            return str(clarity_days(value))
        if name == CLARITY_DIMENSIONS_ENV:
            return dimensions_csv(clarity_dimensions(value))
        if name == COMMON_CRAWL_MAX_URLS_ENV:
            return str(common_crawl_max_urls(value))
        if name == COMMON_CRAWL_INDEX_COUNT_ENV:
            return str(common_crawl_index_count(value))
        return original_validate(name, raw)

    base_environment._validate = validate
    base_environment._rasai_standards_console_validation = True
    facade.CATEGORIES = base_environment.CATEGORIES
    facade.refresh_specs()