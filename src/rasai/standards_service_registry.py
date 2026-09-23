"""Canonical registry for non-AI metrics, standards and external services.

The registry is configuration metadata. It does not change SARI-001/SCORE-GEO-004.
Cost-free collectors that require no credential are enabled by default. Services that
require credentials remain disabled until the credential and mandatory non-secret
context are present, then become eligible by default unless explicitly disabled.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Mapping

from rasai.external_observability_policy import (
    CLARITY_DAYS_ENV,
    CLARITY_DIMENSIONS_ENV,
    CLARITY_ENABLED_ENV,
    CLARITY_TOKEN_ENV,
    COMMON_CRAWL_ENABLED_ENV,
    COMMON_CRAWL_INDEX_COUNT_ENV,
    COMMON_CRAWL_MAX_URLS_ENV,
    CRUX_HISTORY_ENABLED_ENV,
)


@dataclass(frozen=True, slots=True)
class StandardsService:
    id: str
    label: str
    purpose: str
    relation_degree: int
    scopes: tuple[str, ...]
    enabled_env: str
    default_enabled: bool
    job_field: str | None = None
    credential_envs: tuple[str, ...] = ()
    config_envs: tuple[str, ...] = ()
    auto_enable_with_credentials: bool = False
    dataset_env: str | None = None
    documentation_url: str = ""
    credential_url: str = ""
    cost_model: str = "NO_PROVIDER_FEE"
    network_behavior: str = "LOCAL_ONLY"
    methodology: str = ""
    notes: str = ""

    def __post_init__(self) -> None:
        if self.relation_degree < 1 or self.relation_degree > 5:
            raise ValueError("relation_degree must be between 1 and 5")


OPEN_WEB_METRICS_ENV = "RASAI_OPEN_WEB_METRICS"
DERIVED_READINESS_METRICS_ENV = "RASAI_DERIVED_READINESS_METRICS"
RETRIEVAL_METRICS_ENV = "RASAI_RETRIEVAL_METRICS"
W3C_VALIDATOR_ENV = "RASAI_W3C_VALIDATOR"
W3C_CSS_VALIDATOR_ENV = "RASAI_W3C_CSS_VALIDATOR"
MDN_OBSERVATORY_ENV = "RASAI_MDN_OBSERVATORY"
WEB_PLATFORM_BASELINE_ENV = "RASAI_WEB_PLATFORM_BASELINE"
WEB_FEATURES_DATASET_ENV = "RASAI_WEB_FEATURES_DATASET"
PAGESPEED_ENABLED_ENV = "RASAI_PAGESPEED_ENABLED"
CRUX_ENABLED_ENV = "RASAI_CRUX_ENABLED"
GSC_ENABLED_ENV = "RASAI_GSC_ENABLED"
GSC_SITE_URL_ENV = "RASAI_GOOGLE_SEARCH_CONSOLE_SITE_URL"
STANDARDS_MAX_URLS_ENV = "RASAI_STANDARDS_MAX_URLS"
STANDARDS_TIMEOUT_ENV = "RASAI_STANDARDS_TIMEOUT_SECONDS"

DEFAULT_STANDARDS_MAX_URLS = 10
DEFAULT_STANDARDS_TIMEOUT_SECONDS = 20.0
DEFAULT_WEB_FEATURES_DATASET = "auto"


SERVICES: tuple[StandardsService, ...] = (
    StandardsService(
        id="derived-readiness",
        label="RASAi Derived Search & AI Readiness Metrics",
        purpose=(
            "Consolida crawlability, indexability, canonical, sitemap, structured data "
            "e disponibilidade usando evidencias ja persistidas pelo rule engine."
        ),
        relation_degree=5,
        scopes=("ORIGIN", "URL", "DEVICE_SNAPSHOT"),
        enabled_env=DERIVED_READINESS_METRICS_ENV,
        default_enabled=True,
        job_field="derived_readiness_metrics",
        methodology="RASAi derived metrics over deterministic RuleExecutions",
        notes="Advisory/non-scoring unless a future scoring version explicitly adopts a metric.",
    ),
    StandardsService(
        id="retrieval-metrics",
        label="Information Retrieval Metrics",
        purpose="Calcula MRR e, quando existem julgamentos de relevancia, Precision@k, Recall@k e nDCG@k.",
        relation_degree=5,
        scopes=("SEARCH_QUERY", "ORIGIN"),
        enabled_env=RETRIEVAL_METRICS_ENV,
        default_enabled=True,
        job_field="retrieval_metrics",
        methodology="Classical Information Retrieval evaluation metrics",
        notes="nDCG/Precision/Recall nao sao inferidos sem relevance judgments/qrels.",
    ),
    StandardsService(
        id="open-web-metrics",
        label="Open Web Performance APIs",
        purpose="Le Navigation Timing, Resource Timing, Paint, LCP, CLS, Event Timing e sinais relacionados do browser ja aberto.",
        relation_degree=3,
        scopes=("DEVICE_SNAPSHOT",),
        enabled_env=OPEN_WEB_METRICS_ENV,
        default_enabled=True,
        job_field="open_web_metrics",
        documentation_url="https://www.w3.org/TR/performance-timeline/",
        methodology="W3C Web Performance APIs",
        notes="Zero navegacoes adicionais e zero APIs externas.",
    ),
    StandardsService(
        id="w3c-validator",
        label="W3C Nu HTML Checker",
        purpose="Valida conformidade de HTML e reporta erros/warnings sem criar um score W3C artificial.",
        relation_degree=3,
        scopes=("URL",),
        enabled_env=W3C_VALIDATOR_ENV,
        default_enabled=True,
        job_field="w3c_validator",
        documentation_url="https://validator.w3.org/docs/api",
        cost_model="PUBLIC_FREE_SERVICE_OR_SELF_HOST",
        network_behavior="EXTERNAL_VALIDATOR_FETCHES_URL",
        methodology="W3C Nu HTML Checker JSON outcome",
        notes="Uso publico e bounded; self-host e preferivel para SaaS em escala.",
    ),
    StandardsService(
        id="w3c-css-validator",
        label="W3C CSS Validation Service",
        purpose="Valida CSS associado ao documento por URI e preserva validade/contagens emitidas pelo serviço oficial.",
        relation_degree=3,
        scopes=("URL",),
        enabled_env=W3C_CSS_VALIDATOR_ENV,
        default_enabled=True,
        job_field="w3c_css_validator",
        documentation_url="https://jigsaw.w3.org/css-validator/api.html",
        cost_model="PUBLIC_FREE_SERVICE_OR_SELF_HOST",
        network_behavior="EXTERNAL_VALIDATOR_FETCHES_URL_THROTTLED",
        methodology="W3C CSS Validation Service SOAP 1.2",
        notes=(
            "O serviço público pede intervalo mínimo de 1 segundo em automação; "
            "RASAi aplica throttling e limite de URLs. Self-host é preferível em escala."
        ),
    ),
    StandardsService(
        id="mdn-observatory",
        label="MDN HTTP Observatory",
        purpose="Avalia postura de headers HTTP de seguranca e preserva grade/score emitidos pela propria fonte.",
        relation_degree=2,
        scopes=("ORIGIN",),
        enabled_env=MDN_OBSERVATORY_ENV,
        default_enabled=True,
        job_field="mdn_observatory",
        documentation_url="https://developer.mozilla.org/en-US/observatory/docs/faq",
        cost_model="PUBLIC_FREE_SERVICE_OR_SELF_HOST",
        network_behavior="EXTERNAL_PUBLIC_SCAN",
        methodology="MDN HTTP Observatory API v2",
        notes="O scan publico torna o host conhecido pelo servico; pode ser desligado por ambiente/tenant.",
    ),
    StandardsService(
        id="web-platform-baseline",
        label="Web Platform Baseline / WebDX",
        purpose=(
            "Classifica Web Features diretamente observáveis no artefato da página como "
            "Widely Available, Newly Available ou Limited Availability."
        ),
        relation_degree=3,
        scopes=("URL", "DEVICE_SNAPSHOT"),
        enabled_env=WEB_PLATFORM_BASELINE_ENV,
        default_enabled=True,
        job_field="web_platform_baseline",
        dataset_env=WEB_FEATURES_DATASET_ENV,
        documentation_url="https://github.com/web-platform-dx/web-features",
        cost_model="PUBLIC_FREE_DATASET",
        network_behavior="EXTERNAL_DATASET_AUTO_OR_LOCAL_PIN",
        methodology="W3C WebDX web-features + RASAi WEB-PLATFORM-BASELINE-001 deterministic source-to-BCD mapping",
        notes=(
            "A fonte do dataset usa auto por default e é congelada por AUD com versão/SHA-256. "
            "O detector usa somente HTML renderizado/raw já persistido e CSS/JS inline; "
            "não reconsulta assets externos da URL auditada."
        ),
    ),
    StandardsService(
        id="pagespeed",
        label="Google PageSpeed Insights / Lighthouse",
        purpose="Coleta medicao de laboratorio Lighthouse e dados retornados pela PageSpeed Insights API.",
        relation_degree=3,
        scopes=("URL", "DEVICE_SNAPSHOT"),
        enabled_env=PAGESPEED_ENABLED_ENV,
        default_enabled=False,
        job_field="pagespeed_enabled",
        credential_envs=("RASAI_PAGESPEED_API_KEY",),
        auto_enable_with_credentials=True,
        documentation_url="https://developers.google.com/speed/docs/insights/v5/get-started",
        credential_url="https://console.cloud.google.com/apis/credentials",
        cost_model="GOOGLE_API_QUOTA",
        network_behavior="EXTERNAL_API",
        methodology="Google PageSpeed Insights API / Lighthouse",
    ),
    StandardsService(
        id="crux",
        label="Chrome UX Report API",
        purpose="Coleta Core Web Vitals de campo agregados quando URL/origin possui dados elegiveis no CrUX.",
        relation_degree=4,
        scopes=("URL", "ORIGIN", "DEVICE_SNAPSHOT"),
        enabled_env=CRUX_ENABLED_ENV,
        default_enabled=False,
        job_field="crux_enabled",
        credential_envs=("RASAI_CRUX_API_KEY",),
        auto_enable_with_credentials=True,
        documentation_url="https://developer.chrome.com/docs/crux/api/",
        credential_url="https://console.cloud.google.com/apis/credentials",
        cost_model="GOOGLE_API_QUOTA",
        network_behavior="EXTERNAL_API",
        methodology="Chrome UX Report API",
    ),
    StandardsService(
        id="crux-history",
        label="Chrome UX Report History API",
        purpose="Coleta série histórica semanal de Core Web Vitals de campo por origem e form factor.",
        relation_degree=5,
        scopes=("ORIGIN", "DEVICE_SNAPSHOT"),
        enabled_env=CRUX_HISTORY_ENABLED_ENV,
        default_enabled=False,
        job_field="crux_history_enabled",
        credential_envs=("RASAI_CRUX_API_KEY",),
        auto_enable_with_credentials=True,
        documentation_url="https://developer.chrome.com/docs/crux/history-api/",
        credential_url="https://console.cloud.google.com/apis/credentials",
        cost_model="GOOGLE_API_QUOTA_NO_PROVIDER_FEE",
        network_behavior="EXTERNAL_API",
        methodology="Chrome UX Report History API",
        notes="Mantém origem e form factor explícitos; não é média com Lighthouse/Apdex/CrUX current.",
    ),
    StandardsService(
        id="google-search-console",
        label="Google Search Console",
        purpose="Fornece Search Analytics, sitemaps e URL Inspection para propriedades verificadas.",
        relation_degree=5,
        scopes=("ORIGIN", "URL", "SEARCH_QUERY"),
        enabled_env=GSC_ENABLED_ENV,
        default_enabled=False,
        job_field="gsc_enabled",
        credential_envs=("RASAI_GOOGLE_SEARCH_CONSOLE_ACCESS_TOKEN",),
        config_envs=(GSC_SITE_URL_ENV,),
        auto_enable_with_credentials=True,
        documentation_url="https://developers.google.com/webmaster-tools/v1/api_reference_index",
        credential_url="https://console.cloud.google.com/apis/credentials",
        cost_model="GOOGLE_API_AUTHENTICATED",
        network_behavior="EXTERNAL_API",
        methodology="Google Search Console API",
        notes="Exige token OAuth e propriedade siteUrl/sc-domain acessivel ao usuario autenticado.",
    ),
    StandardsService(
        id="microsoft-clarity",
        label="Microsoft Clarity Data Export",
        purpose="Coleta somente métricas comportamentais agregadas, como engagement, scroll, rage/dead clicks e erros de script.",
        relation_degree=5,
        scopes=("ORIGIN", "URL", "DEVICE_SNAPSHOT"),
        enabled_env=CLARITY_ENABLED_ENV,
        default_enabled=False,
        job_field="clarity_enabled",
        credential_envs=(CLARITY_TOKEN_ENV,),
        auto_enable_with_credentials=False,
        documentation_url="https://learn.microsoft.com/clarity/setup-and-installation/clarity-data-export-api",
        credential_url="https://clarity.microsoft.com/",
        cost_model="NO_PROVIDER_FEE_DAILY_QUOTA",
        network_behavior="EXTERNAL_API",
        methodology="Microsoft Clarity Data Export API",
        notes=(
            "Opt-in explícito para preservar a quota de 10 requests/dia/projeto. "
            "RASAi não persiste session replay, IDs de visitante/sessão, teclas ou conteúdo de formulário."
        ),
    ),
    StandardsService(
        id="common-crawl",
        label="Common Crawl CDX History",
        purpose="Consulta presença histórica de URLs auditadas nos índices públicos mensais do Common Crawl.",
        relation_degree=4,
        scopes=("URL",),
        enabled_env=COMMON_CRAWL_ENABLED_ENV,
        default_enabled=True,
        job_field="common_crawl_enabled",
        documentation_url="https://commoncrawl.org/cdxj-index",
        cost_model="PUBLIC_FREE_DATASET",
        network_behavior="EXTERNAL_PUBLIC_INDEX_API_BOUNDED",
        methodology="Common Crawl CDXJ index API",
        notes=(
            "Sem chave/token e habilitado por default com limites conservadores. "
            "Presença no Common Crawl não prova indexação Google/Bing nem disponibilidade atual."
        ),
    ),
)

_BY_ID = {service.id: service for service in SERVICES}


def services() -> tuple[StandardsService, ...]:
    return SERVICES


def service(service_id: str) -> StandardsService:
    try:
        return _BY_ID[service_id]
    except KeyError as exc:
        raise KeyError(f"unknown standards service: {service_id}") from exc


def boolean_value(raw: str | None, *, default: bool) -> bool:
    if raw is None or not raw.strip():
        return default
    value = raw.strip().casefold()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    raise ValueError("use true/false, 1/0, yes/no or on/off")


def _configuration_value(environment: Mapping[str, str], name: str) -> str:
    value = (environment.get(name) or "").strip()
    if value:
        return value
    if name == WEB_FEATURES_DATASET_ENV:
        return DEFAULT_WEB_FEATURES_DATASET
    return ""


def service_state(item: StandardsService, env: Mapping[str, str] | None = None) -> dict[str, object]:
    environment = env if env is not None else os.environ
    credentials_ready = all(_configuration_value(environment, name) for name in item.credential_envs)
    config_ready = all(_configuration_value(environment, name) for name in item.config_envs)
    dataset_ready = True if not item.dataset_env else bool(_configuration_value(environment, item.dataset_env))
    configured = credentials_ready and config_ready and dataset_ready
    explicit = (environment.get(item.enabled_env) or "").strip()
    if explicit:
        requested = boolean_value(explicit, default=item.default_enabled)
        source = "EXPLICIT"
    elif item.credential_envs and item.auto_enable_with_credentials:
        requested = credentials_ready and config_ready
        source = "CREDENTIAL_DRIVEN_DEFAULT"
    else:
        requested = item.default_enabled
        source = "DEFAULT"
    effective = requested and configured
    if not requested:
        state = "DISABLED"
    elif not configured:
        state = "NOT_CONFIGURED"
    else:
        state = "READY"
    missing_config = tuple(
        name for name in (*item.credential_envs, *item.config_envs, *((item.dataset_env,) if item.dataset_env else ()))
        if not _configuration_value(environment, name)
    )
    return {
        "id": item.id,
        "label": item.label,
        "requested": requested,
        "configured": configured,
        "effective_enabled": effective,
        "state": state,
        "configuration_source": source,
        "credential_envs": item.credential_envs,
        "config_envs": item.config_envs,
        "dataset_env": item.dataset_env,
        "missing_configuration": missing_config,
    }


def service_states(env: Mapping[str, str] | None = None) -> tuple[dict[str, object], ...]:
    return tuple(service_state(item, env) for item in SERVICES)


def service_environment_names() -> tuple[str, ...]:
    names: list[str] = [
        STANDARDS_MAX_URLS_ENV,
        STANDARDS_TIMEOUT_ENV,
        CLARITY_DAYS_ENV,
        CLARITY_DIMENSIONS_ENV,
        COMMON_CRAWL_MAX_URLS_ENV,
        COMMON_CRAWL_INDEX_COUNT_ENV,
    ]
    for item in SERVICES:
        for name in (item.enabled_env, item.dataset_env, *item.credential_envs, *item.config_envs):
            if name and name not in names:
                names.append(name)
    return tuple(names)
