"""Interactive-console reconciliation for standards service settings."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from urllib.parse import urlparse

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
    category = "Métricas e padrões"
    source = "docs/STANDARDS_METRICS_AND_SERVICES.md"
    specs = list(base_environment.SPECS)
    known = {spec.name for spec in specs}
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
    )
    for spec in additions:
        if spec.name not in known:
            specs.append(spec)
            known.add(spec.name)

    credential_driven = {item.enabled_env: item for item in services() if item.credential_envs and item.auto_enable_with_credentials}
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
    install_console_service_catalog()
    from rasai import console_config
    from rasai import console_environment as base_environment
    from rasai import console_provider_environment as facade

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
                raise ValueError(f"{name}: dataset configurado não existe")
            return str(path)
        if name == GSC_SITE_URL_ENV:
            return _validate_gsc_site_url(value)
        if name == GSC_SEARCH_ANALYTICS_DAYS_ENV:
            return str(search_analytics_days(value))
        if name == GSC_SEARCH_MAX_ROWS_ENV:
            return str(search_max_rows(value))
        if name == GSC_FINAL_DATA_LAG_DAYS_ENV:
            return str(final_data_lag_days(value))
        return original_validate(name, raw)

    base_environment._validate = validate
    base_environment._rasai_standards_console_validation = True
    facade.CATEGORIES = base_environment.CATEGORIES
    facade.refresh_specs()
