"""Canonical registry for non-AI metrics, standards and external services.

The registry is configuration metadata. It does not change SARI-001/SCORE-GEO-004.
Cost-free collectors that require no credential are enabled by default. Services that
require credentials remain disabled until the credential is present, then become
eligible by default unless the user explicitly disables the service.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Mapping


@dataclass(frozen=True, slots=True)
class StandardsService:
    id: str
    label: str
    purpose: str
    relation_degree: int
    scopes: tuple[str, ...]
    enabled_env: str
    default_enabled: bool
    credential_envs: tuple[str, ...] = ()
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
MDN_OBSERVATORY_ENV = "RASAI_MDN_OBSERVATORY"
WEB_PLATFORM_BASELINE_ENV = "RASAI_WEB_PLATFORM_BASELINE"
WEB_FEATURES_DATASET_ENV = "RASAI_WEB_FEATURES_DATASET"
PAGESPEED_ENABLED_ENV = "RASAI_PAGESPEED_ENABLED"
CRUX_ENABLED_ENV = "RASAI_CRUX_ENABLED"
GSC_ENABLED_ENV = "RASAI_GSC_ENABLED"
STANDARDS_MAX_URLS_ENV = "RASAI_STANDARDS_MAX_URLS"
STANDARDS_TIMEOUT_ENV = "RASAI_STANDARDS_TIMEOUT_SECONDS"

DEFAULT_STANDARDS_MAX_URLS = 10
DEFAULT_STANDARDS_TIMEOUT_SECONDS = 20.0


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
        documentation_url="https://validator.w3.org/docs/api",
        cost_model="PUBLIC_FREE_SERVICE_OR_SELF_HOST",
        network_behavior="EXTERNAL_VALIDATOR_FETCHES_URL",
        methodology="W3C Nu HTML Checker JSON outcome",
        notes="Uso publico e bounded; self-host e preferivel para SaaS em escala.",
    ),
    StandardsService(
        id="mdn-observatory",
        label="MDN HTTP Observatory",
        purpose="Avalia postura de headers HTTP de seguranca e preserva grade/score emitidos pela propria fonte.",
        relation_degree=2,
        scopes=("ORIGIN",),
        enabled_env=MDN_OBSERVATORY_ENV,
        default_enabled=True,
        documentation_url="https://developer.mozilla.org/en-US/observatory/docs/faq",
        cost_model="PUBLIC_FREE_SERVICE_OR_SELF_HOST",
        network_behavior="EXTERNAL_PUBLIC_SCAN",
        methodology="MDN HTTP Observatory API v2",
        notes="O scan publico torna o host conhecido pelo servico; pode ser desligado por ambiente/tenant.",
    ),
    StandardsService(
        id="web-platform-baseline",
        label="Web Platform Baseline / WebDX",
        purpose="Classifica recursos Web como Widely Available, Newly Available ou Limited Availability quando um dataset versionado esta disponivel.",
        relation_degree=3,
        scopes=("URL", "DEVICE_SNAPSHOT"),
        enabled_env=WEB_PLATFORM_BASELINE_ENV,
        default_enabled=True,
        dataset_env=WEB_FEATURES_DATASET_ENV,
        documentation_url="https://github.com/web-platform-dx/web-features",
        methodology="W3C WebDX web-features Baseline data",
        notes="Sem dataset versionado o estado e NOT_CONFIGURED; nenhum resultado de compatibilidade e inventado.",
    ),
    StandardsService(
        id="pagespeed",
        label="Google PageSpeed Insights / Lighthouse",
        purpose="Coleta medicao de laboratorio Lighthouse e dados retornados pela PageSpeed Insights API.",
        relation_degree=3,
        scopes=("URL", "DEVICE_SNAPSHOT"),
        enabled_env=PAGESPEED_ENABLED_ENV,
        default_enabled=False,
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
        credential_envs=("RASAI_CRUX_API_KEY",),
        auto_enable_with_credentials=True,
        documentation_url="https://developer.chrome.com/docs/crux/api/",
        credential_url="https://console.cloud.google.com/apis/credentials",
        cost_model="GOOGLE_API_QUOTA",
        network_behavior="EXTERNAL_API",
        methodology="Chrome UX Report API",
    ),
    StandardsService(
        id="google-search-console",
        label="Google Search Console",
        purpose="Fornece Search Analytics, sitemaps e URL Inspection para propriedades verificadas.",
        relation_degree=5,
        scopes=("ORIGIN", "URL", "SEARCH_QUERY"),
        enabled_env=GSC_ENABLED_ENV,
        default_enabled=False,
        credential_envs=("RASAI_GOOGLE_SEARCH_CONSOLE_ACCESS_TOKEN",),
        auto_enable_with_credentials=True,
        documentation_url="https://developers.google.com/webmaster-tools/v1/api_reference_index",
        credential_url="https://console.cloud.google.com/apis/credentials",
        cost_model="GOOGLE_API_AUTHENTICATED",
        network_behavior="EXTERNAL_API",
        methodology="Google Search Console API",
        notes="Tambem exige propriedade Search Console adequada ao target consultado.",
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


def service_state(item: StandardsService, env: Mapping[str, str] | None = None) -> dict[str, object]:
    environment = env if env is not None else os.environ
    credentials_ready = all((environment.get(name) or "").strip() for name in item.credential_envs)
    dataset_ready = True if not item.dataset_env else bool((environment.get(item.dataset_env) or "").strip())
    configured = credentials_ready and dataset_ready
    explicit = (environment.get(item.enabled_env) or "").strip()
    if explicit:
        requested = boolean_value(explicit, default=item.default_enabled)
        source = "EXPLICIT"
    elif item.credential_envs and item.auto_enable_with_credentials:
        requested = credentials_ready
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
    return {
        "id": item.id,
        "label": item.label,
        "requested": requested,
        "configured": configured,
        "effective_enabled": effective,
        "state": state,
        "configuration_source": source,
        "credential_envs": item.credential_envs,
        "dataset_env": item.dataset_env,
    }


def service_states(env: Mapping[str, str] | None = None) -> tuple[dict[str, object], ...]:
    return tuple(service_state(item, env) for item in SERVICES)


def service_environment_names() -> tuple[str, ...]:
    names: list[str] = [STANDARDS_MAX_URLS_ENV, STANDARDS_TIMEOUT_ENV]
    for item in SERVICES:
        for name in (item.enabled_env, item.dataset_env, *item.credential_envs):
            if name and name not in names:
                names.append(name)
    return tuple(names)
