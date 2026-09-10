"""Grouped and guided environment-variable configuration for the console.

The catalog covers the complete product configuration surface known at build time:
local audit runtime, Search/observability integrations, control-plane/SaaS deployment,
Web API/Identity and remote-client settings.

Secrets may be edited for the current process (and optionally persisted in the Windows
User environment after explicit confirmation), but are never written to the console
INI. Variables whose value names another secret environment variable are configuration
references, not secrets themselves, and may be persisted normally.
"""
from __future__ import annotations

from dataclasses import dataclass
from getpass import getpass
import os
from pathlib import Path
from urllib.parse import urlparse

from rasai.console_artifacts import open_external_path
from rasai.console_config import (
    ENV_NAMES as BASE_ENV_NAMES,
    KEY_ENV,
    PROVIDERS,
    apply_environment_defaults,
    is_secret,
)
from rasai.console_m23 import (
    M23_ENV_NAMES,
    apply_m23_environment_defaults,
    validate_env_value as validate_existing,
)
from rasai.console_runtime import render_header
from rasai.console_session import clear_secret_volatile, mark_secret_volatile
from rasai.console_ui import CYAN, DIM, GREEN, paint
from rasai.content_context import (
    CONTENT_ORIGIN_ENV,
    CONTENT_RISK_PROFILE_ENV,
    EXPERIENCE_REQUIREMENT_ENV,
    FRESHNESS_SENSITIVITY_ENV,
    INTENDED_AUDIENCE_ENV,
    PAGE_PURPOSE_ENV,
    YMYL_CATEGORY_ENV,
)
from rasai.m23_cli import (
    APDEX_CONCURRENCY_ENV,
    APDEX_DELAY_ENV,
    APDEX_ENABLED_ENV,
    APDEX_MAX_ATTEMPTS_ENV,
    APDEX_MAX_PAGES_ENV,
    APDEX_SAMPLES_ENV,
    APDEX_THRESHOLD_ENV,
    APDEX_TIMEOUT_ENV,
)
from rasai.m25_cli import (
    DEFAULT_UX_CONCURRENCY,
    DEFAULT_UX_DELAY_SECONDS,
    DEFAULT_UX_DEVICE_MIX,
    DEFAULT_UX_ERROR_SCOPE,
    DEFAULT_UX_FRUSTRATED_SECONDS,
    DEFAULT_UX_KPM,
    DEFAULT_UX_MAX_PAGES,
    DEFAULT_UX_SAMPLES,
    DEFAULT_UX_SATISFIED_SECONDS,
    DEFAULT_UX_SESSION_MODE,
    DEFAULT_UX_SETTLE_SECONDS,
    DYNATRACE_APPLICATION_ID_ENV,
    DYNATRACE_BASE_URL_ENV,
    DYNATRACE_CONFIG_JSON_ENV,
    DYNATRACE_IMPORT_ENV,
    M25_ENV_NAMES,
    UX_CONCURRENCY_ENV,
    UX_DELAY_ENV,
    UX_DEVICE_MIX_ENV,
    UX_ENABLED_ENV,
    UX_ERRORS_ENV,
    UX_ERROR_SCOPE_ENV,
    UX_FRUSTRATED_ENV,
    UX_KPM_ENV,
    UX_MAX_ATTEMPTS_ENV,
    UX_MAX_PAGES_ENV,
    UX_SAMPLES_ENV,
    UX_SATISFIED_ENV,
    UX_SESSION_MODE_ENV,
    UX_SETTLE_ENV,
)
from rasai.m25_dynatrace import DYNATRACE_API_TOKEN_ENV, SUPPORTED_TIME_KPMS
from rasai.provider_registry import provider_registrations
from rasai.provider_runtime_policy import (
    AI_TIMEOUT_ENV,
    LOWEST_REASONING,
    REASONING_OPTIONS,
    SIMPLE_DEFAULT_MODELS,
    WEB_PERFORMANCE_TIMEOUT_ENV,
    provider_reasoning_env,
)
from rasai.search_intelligence.config import (
    SERP_ENV_NAMES,
    SERP_FIXTURE_PATH_ENV,
    SERP_MAX_COMPETITORS_ENV,
    SERP_MAX_DEPTH_ENV,
    SERP_MAX_QUERIES_ENV,
    SERP_MAX_REQUESTS_ENV,
    SERP_MIN_INTERVAL_ENV,
    SERP_MODE_ENV,
    SERP_PROVIDER_ENV,
    SERP_RETRIES_ENV,
    SERP_TIMEOUT_ENV,
    SERPAPI_KEY_ENV,
)
from rasai.secret_safety import is_secret_reference_name, validate_environment_reference
from rasai.windows_environment import (
    current_matches_persisted,
    environment_origin,
    machine_environment_value,
    persist_user_environment,
    remove_user_environment,
    user_environment_value,
)

CONSOLE_INI_ENV = "RASAI_CONSOLE_INI"
SEARCH_AI_PROVIDER_ENV = "RASAI_SEARCH_AI_PROVIDER"
GSC_ACCESS_TOKEN_ENV = "RASAI_GOOGLE_SEARCH_CONSOLE_ACCESS_TOKEN"
PLATFORM_BACKEND_ENV = "RASAI_PLATFORM_DB_BACKEND"
PLATFORM_DATABASE_URL_ENV = "RASAI_PLATFORM_DATABASE_URL"
API_DOCS_ENV = "RASAI_API_DOCS_ENABLED"
API_AUDITS_ROOT_ENV = "RASAI_API_AUDITS_ROOT"
API_AUTH_MODE_ENV = "RASAI_API_AUTH_MODE"
API_TRUSTED_HEADER_ENV = "RASAI_API_TRUSTED_USER_HEADER"
OIDC_ISSUER_ENV = "RASAI_OIDC_ISSUER"
OIDC_CLIENT_ID_ENV = "RASAI_OIDC_CLIENT_ID"
OIDC_AUDIENCE_ENV = "RASAI_OIDC_AUDIENCE"
OIDC_REDIRECT_URI_ENV = "RASAI_OIDC_REDIRECT_URI"
OIDC_SESSION_SECRET_ENV = "RASAI_OIDC_SESSION_SECRET"
OIDC_CLIENT_SECRET_ENV_REF = "RASAI_OIDC_CLIENT_SECRET_ENV"
OIDC_ALGORITHMS_ENV = "RASAI_OIDC_ALGORITHMS"
OIDC_SCOPES_ENV = "RASAI_OIDC_SCOPES"
OIDC_SESSION_TTL_ENV = "RASAI_OIDC_SESSION_TTL_SECONDS"
REMOTE_BASE_URL_ENV = "RASAI_REMOTE_BASE_URL"
REMOTE_TOKEN_ENV_REF = "RASAI_REMOTE_TOKEN_ENV"
REMOTE_USER_ID_ENV = "RASAI_REMOTE_USER_ID"
REMOTE_TIMEOUT_ENV = "RASAI_REMOTE_TIMEOUT_SECONDS"

_PLATFORM_ENV_NAMES = (PLATFORM_BACKEND_ENV, PLATFORM_DATABASE_URL_ENV)
_API_ENV_NAMES = (
    API_DOCS_ENV,
    API_AUDITS_ROOT_ENV,
    API_AUTH_MODE_ENV,
    API_TRUSTED_HEADER_ENV,
    OIDC_ISSUER_ENV,
    OIDC_CLIENT_ID_ENV,
    OIDC_AUDIENCE_ENV,
    OIDC_REDIRECT_URI_ENV,
    OIDC_SESSION_SECRET_ENV,
    OIDC_CLIENT_SECRET_ENV_REF,
    OIDC_ALGORITHMS_ENV,
    OIDC_SCOPES_ENV,
    OIDC_SESSION_TTL_ENV,
)
_REMOTE_ENV_NAMES = (
    REMOTE_BASE_URL_ENV,
    REMOTE_TOKEN_ENV_REF,
    REMOTE_USER_ID_ENV,
    REMOTE_TIMEOUT_ENV,
)
_SEARCH_ENV_NAMES = (*SERP_ENV_NAMES, SEARCH_AI_PROVIDER_ENV, GSC_ACCESS_TOKEN_ENV)

ENV_NAMES = tuple(
    dict.fromkeys(
        (
            *BASE_ENV_NAMES,
            *M23_ENV_NAMES,
            *M25_ENV_NAMES,
            DYNATRACE_API_TOKEN_ENV,
            CONSOLE_INI_ENV,
            *_SEARCH_ENV_NAMES,
            *_PLATFORM_ENV_NAMES,
            *_API_ENV_NAMES,
            *_REMOTE_ENV_NAMES,
        )
    )
)
DOCUMENT_NAME = "ENVIRONMENT_VARIABLES.md"
CATEGORIES = (
    "Aplicação e execução",
    "IA - credenciais",
    "IA - modelos e reasoning",
    "IA - endpoints avançados",
    "IA - contexto editorial / YMYL",
    "Web Performance / Google APIs",
    "Synthetic Apdex",
    "Search Intelligence / Observability",
    "Control plane / SaaS",
    "Web API / Identity",
    "Remote control plane",
    "Browser / Playwright",
)


@dataclass(frozen=True, slots=True)
class EnvironmentSpec:
    name: str
    category: str
    purpose: str
    value_type: str
    accepted: tuple[str, ...] = ()
    default: str | None = None
    required_when: str = "Nunca; override opcional."
    sensitive: bool = False
    impact: str = "Sem custo externo direto."
    example: str = ""
    source: str = "docs/ENVIRONMENT_VARIABLES.md"
    notes: str = ""


ENDPOINT_DEFAULTS = {
    "XAI": "https://api.x.ai/v1/responses",
    "QWEN": "https://dashscope-us.aliyuncs.com/compatible-mode/v1/chat/completions",
    "GEMINI": "https://generativelanguage.googleapis.com/v1beta/interactions",
    "ANTHROPIC": "https://api.anthropic.com/v1/messages",
}
KEY_SOURCES = {
    "OPENAI": "OpenAI Platform > API Keys - https://platform.openai.com/api-keys",
    "DEEPSEEK": "DeepSeek Platform > API Keys - https://platform.deepseek.com/api_keys",
    "MIMO": "Xiaomi MiMo Console > API Keys - docs/ENVIRONMENT_VARIABLES.md",
    "XAI": "xAI Console > API Keys - https://console.x.ai/",
    "QWEN": "Alibaba Cloud Model Studio > API Key - docs/ENVIRONMENT_VARIABLES.md",
    "GEMINI": "Google AI Studio > API Keys - https://aistudio.google.com/apikey",
    "ANTHROPIC": "Anthropic Console > API Keys - https://console.anthropic.com/",
}


def _application_specs() -> tuple[EnvironmentSpec, ...]:
    return (
        EnvironmentSpec(
            CONSOLE_INI_ENV,
            "Aplicação e execução",
            "Seleciona o arquivo INI persistente do console.",
            "caminho",
            default="rasai-console.ini",
            example=f"{CONSOLE_INI_ENV}=rasai-console.ini",
        ),
        EnvironmentSpec(
            "RASAI_CONFIG",
            "Aplicação e execução",
            "Força um arquivo TOML geral; usado principalmente para logging.",
            "caminho de arquivo existente",
            default="rasai.toml opcional quando não há override",
            required_when="Somente para apontar explicitamente para outro TOML.",
        ),
        EnvironmentSpec(
            "RASAI_CONSOLE_MODE",
            "Aplicação e execução",
            "Seleciona o console local de auditoria ou o cliente do control plane remoto.",
            "enum",
            ("local", "remote"),
            "local",
            required_when="Use `remote` somente quando um control plane remoto estiver configurado.",
        ),
        EnvironmentSpec(
            "RASAI_LOG_LEVEL",
            "Aplicação e execução",
            "Controla a verbosidade do log operacional.",
            "enum",
            ("CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"),
            "INFO",
        ),
        EnvironmentSpec(
            "RASAI_DEVICE_CONTEXT",
            "Aplicação e execução",
            "Define o device default quando menu/CLI não fornecem valor explícito.",
            "enum",
            ("mobile", "desktop", "both"),
            "mobile",
            impact="`both` multiplica contextos, tempo e carga de coleta.",
        ),
        EnvironmentSpec(
            AI_TIMEOUT_ENV,
            "Aplicação e execução",
            "Timeout máximo de uma tentativa de IA.",
            "número > 0 (segundos)",
            default="180",
        ),
        EnvironmentSpec(
            "RASAI_AI_CONTENT_REMEDIATION",
            "Aplicação e execução",
            "Default da remediação de conteúdo por IA.",
            "booleano",
            ("true", "false"),
            "false",
            required_when="Só tem efeito com provider de IA apto.",
            impact="Quando true, pode gerar chamadas/tokens adicionais de IA.",
        ),
        EnvironmentSpec(
            "RASAI_AI_TECHNICAL_REMEDIATION",
            "Aplicação e execução",
            "Default da remediação técnica advisory de crawling/discovery por IA.",
            "booleano",
            ("true", "false"),
            "false",
            required_when="Só tem efeito com provider de IA apto.",
            impact="Quando true, pode gerar chamadas/tokens adicionais de IA.",
        ),
    )


def _content_specs() -> tuple[EnvironmentSpec, ...]:
    source = "docs/CONTENT_ANALYSIS_CONTEXT.md"
    return (
        EnvironmentSpec(CONTENT_RISK_PROFILE_ENV, "IA - contexto editorial / YMYL", "Perfil de risco editorial.", "enum", ("auto", "standard", "ymyl"), "auto", source=source),
        EnvironmentSpec(YMYL_CATEGORY_ENV, "IA - contexto editorial / YMYL", "Categoria de risco YMYL.", "enum", ("auto", "none", "health-safety", "financial-security", "civic-societal", "other-significant-welfare"), "auto", source=source),
        EnvironmentSpec(PAGE_PURPOSE_ENV, "IA - contexto editorial / YMYL", "Finalidade principal da página.", "enum", ("auto", "informational", "transactional", "product-service", "review-comparison", "news-editorial", "support-documentation", "forum-ugc", "other"), "auto", source=source),
        EnvironmentSpec(INTENDED_AUDIENCE_ENV, "IA - contexto editorial / YMYL", "Público pretendido.", "enum", ("auto", "general", "professional", "mixed"), "auto", source=source),
        EnvironmentSpec(EXPERIENCE_REQUIREMENT_ENV, "IA - contexto editorial / YMYL", "Expectativa de experiência em primeira mão.", "enum", ("auto", "required", "beneficial", "not-expected"), "auto", source=source),
        EnvironmentSpec(FRESHNESS_SENSITIVITY_ENV, "IA - contexto editorial / YMYL", "Sensibilidade temporal do conteúdo.", "enum", ("auto", "low", "medium", "high"), "auto", source=source),
        EnvironmentSpec(CONTENT_ORIGIN_ENV, "IA - contexto editorial / YMYL", "Origem editorial do conteúdo.", "enum", ("auto", "first-party", "third-party", "user-generated", "mixed"), "auto", source=source),
    )


def _web_specs() -> tuple[EnvironmentSpec, ...]:
    return (
        EnvironmentSpec("RASAI_WEB_PERFORMANCE", "Web Performance / Google APIs", "Habilita PageSpeed/Lighthouse/CrUX.", "booleano", ("true", "false"), "false", impact="Quando true, consome quota externa."),
        EnvironmentSpec("RASAI_WEB_PERFORMANCE_MAX_PAGES", "Web Performance / Google APIs", "Máximo de páginas enviadas às integrações externas; 0=todas.", "inteiro >= 0", default="10"),
        EnvironmentSpec(WEB_PERFORMANCE_TIMEOUT_ENV, "Web Performance / Google APIs", "Timeout por request PageSpeed/CrUX.", "número > 0 (segundos)", default="120"),
        EnvironmentSpec("RASAI_WEB_PERFORMANCE_FIELD_SOURCE", "Web Performance / Google APIs", "Política de dados de campo CrUX.", "enum", ("auto", "pagespeed", "crux", "none"), "auto", required_when="`crux` exige RASAI_CRUX_API_KEY."),
        EnvironmentSpec("RASAI_LIGHTHOUSE_CATEGORIES", "Web Performance / Google APIs", "Categorias Lighthouse solicitadas; Agentic Browsing é experimental e opcional na resposta.", "lista CSV", ("performance", "accessibility", "best-practices", "seo", "agentic-browsing"), "performance,accessibility,best-practices,seo,agentic-browsing"),
        EnvironmentSpec("RASAI_PAGESPEED_API_KEY", "Web Performance / Google APIs", "Chave PageSpeed Insights API.", "segredo/API key", sensitive=True, source="docs/GOOGLE_API_KEYS.md"),
        EnvironmentSpec("RASAI_CRUX_API_KEY", "Web Performance / Google APIs", "Chave Chrome UX Report API.", "segredo/API key", sensitive=True, source="docs/GOOGLE_API_KEYS.md"),
    )


def _apdex_specs() -> tuple[EnvironmentSpec, ...]:
    return (
        EnvironmentSpec(APDEX_ENABLED_ENV, "Synthetic Apdex", "Habilita Synthetic Navigation Apdex.", "booleano", ("true", "false"), "false", impact="Gera navegações HTTP reais contra o alvo."),
        EnvironmentSpec(APDEX_THRESHOLD_ENV, "Synthetic Apdex", "Threshold T do Navigation Apdex.", "número > 0 (segundos)", required_when="Obrigatória quando Navigation Apdex=true.", notes="Não existe default metodológico universal; use o SLO/KPM do sistema."),
        EnvironmentSpec(APDEX_SAMPLES_ENV, "Synthetic Apdex", "Amostras válidas por URL/device.", "inteiro >= 1", default="100"),
        EnvironmentSpec(APDEX_MAX_ATTEMPTS_ENV, "Synthetic Apdex", "Teto de tentativas por contexto.", "inteiro >= amostras", default="ceil(1.25 × samples)"),
        EnvironmentSpec(APDEX_MAX_PAGES_ENV, "Synthetic Apdex", "Máximo de páginas; 0=todas.", "inteiro >= 0", default="1"),
        EnvironmentSpec(APDEX_TIMEOUT_ENV, "Synthetic Apdex", "Timeout por navegação.", "número > 0 e > 4T", default="max(45, 4T + 5)"),
        EnvironmentSpec(APDEX_DELAY_ENV, "Synthetic Apdex", "Intervalo mínimo entre navegações.", "número >= 0", default="1"),
        EnvironmentSpec(APDEX_CONCURRENCY_ENV, "Synthetic Apdex", "Workers Navigation Apdex simultâneos.", "enum inteiro", ("1", "2"), "1"),
        EnvironmentSpec(UX_ENABLED_ENV, "Synthetic Apdex", "Habilita Synthetic User Experience Apdex e apdex-experience.html.", "booleano", ("true", "false"), "false", required_when="Exige Synthetic Navigation Apdex ativo."),
        EnvironmentSpec(UX_SAMPLES_ENV, "Synthetic Apdex", "Amostras válidas totais por página na população Experience.", "inteiro >= 1", default=str(DEFAULT_UX_SAMPLES)),
        EnvironmentSpec(UX_MAX_ATTEMPTS_ENV, "Synthetic Apdex", "Teto de tentativas por página Experience.", "inteiro >= samples", default="ceil(1.25 × samples)"),
        EnvironmentSpec(UX_MAX_PAGES_ENV, "Synthetic Apdex", "Máximo de páginas Experience; 0=todas.", "inteiro >= 0", default=str(DEFAULT_UX_MAX_PAGES)),
        EnvironmentSpec(
            UX_DEVICE_MIX_ENV,
            "Synthetic Apdex",
            "Distribuição percentual das amostras/user actions entre Mobile/Desktop/Tablet; soma obrigatória de 100%.",
            "percentuais CSV",
            default=DEFAULT_UX_DEVICE_MIX,
            example=f"{UX_DEVICE_MIX_ENV}={DEFAULT_UX_DEVICE_MIX}",
            notes="É peso populacional de amostras, não contagem bruta de subrequests HTTP; cada user action pode gerar vários requests.",
        ),
        EnvironmentSpec(UX_SESSION_MODE_ENV, "Synthetic Apdex", "Sessão Experience cold/warm.", "enum", ("cold", "warm"), DEFAULT_UX_SESSION_MODE),
        EnvironmentSpec(UX_KPM_ENV, "Synthetic Apdex", "KPM temporal do Experience Apdex.", "enum", tuple(sorted(SUPPORTED_TIME_KPMS)), DEFAULT_UX_KPM),
        EnvironmentSpec(
            UX_SATISFIED_ENV,
            "Synthetic Apdex",
            "Threshold Satisfied/Tolerating do Experience Apdex.",
            "número > 0",
            default=f"{DEFAULT_UX_SATISFIED_SECONDS:g}",
            required_when="Nunca; override opcional ou substituição por importação Dynatrace.",
            notes="Baseline executável alinhado ao fallback/referência Dynatrace Load; o relatório registra PADRÃO, CUSTOMIZADO ou DYNATRACE IMPORT.",
        ),
        EnvironmentSpec(
            UX_FRUSTRATED_ENV,
            "Synthetic Apdex",
            "Threshold Frustrated independente de 4T.",
            "número > 0",
            default=f"{DEFAULT_UX_FRUSTRATED_SECONDS:g}",
            required_when="Nunca; override opcional ou substituição por importação Dynatrace.",
            notes="Baseline executável alinhado ao fallback/referência Dynatrace Load; o relatório registra PADRÃO, CUSTOMIZADO ou DYNATRACE IMPORT.",
        ),
        EnvironmentSpec(UX_ERRORS_ENV, "Synthetic Apdex", "Erros qualificáveis forçam Frustrated.", "booleano", ("true", "false"), "true"),
        EnvironmentSpec(UX_ERROR_SCOPE_ENV, "Synthetic Apdex", "Escopo dos erros que afetam Experience Apdex.", "enum", ("navigation", "first-party", "all"), DEFAULT_UX_ERROR_SCOPE),
        EnvironmentSpec(UX_SETTLE_ENV, "Synthetic Apdex", "Janela pós-load para recursos tardios.", "número > 0", default=f"{DEFAULT_UX_SETTLE_SECONDS:g}"),
        EnvironmentSpec(UX_DELAY_ENV, "Synthetic Apdex", "Intervalo mínimo entre user actions.", "número >= 0", default=f"{DEFAULT_UX_DELAY_SECONDS:g}"),
        EnvironmentSpec(UX_CONCURRENCY_ENV, "Synthetic Apdex", "Workers Experience simultâneos.", "enum inteiro", ("1", "2"), str(DEFAULT_UX_CONCURRENCY)),
        EnvironmentSpec(DYNATRACE_IMPORT_ENV, "Synthetic Apdex", "Importa calibração Dynatrace.", "booleano", ("true", "false"), "false"),
        EnvironmentSpec(DYNATRACE_BASE_URL_ENV, "Synthetic Apdex", "URL HTTPS do ambiente Dynatrace.", "URL HTTPS", required_when="Importação Dynatrace live."),
        EnvironmentSpec(DYNATRACE_APPLICATION_ID_ENV, "Synthetic Apdex", "Application ID Dynatrace.", "texto", required_when="Importação Dynatrace live."),
        EnvironmentSpec(DYNATRACE_CONFIG_JSON_ENV, "Synthetic Apdex", "JSON exportado da configuração Dynatrace.", "caminho de arquivo", required_when="Alternativa reproduzível à importação live."),
        EnvironmentSpec(DYNATRACE_API_TOKEN_ENV, "Synthetic Apdex", "Token Dynatrace para importação live.", "segredo/token", sensitive=True, required_when="Importação Dynatrace live."),
    )


def _search_specs() -> tuple[EnvironmentSpec, ...]:
    return (
        EnvironmentSpec(SERP_MODE_ENV, "Search Intelligence / Observability", "Modo global SERP.", "enum", ("disabled", "live", "fixture"), "disabled"),
        EnvironmentSpec(SERP_PROVIDER_ENV, "Search Intelligence / Observability", "Provider de Search live.", "enum", ("serpapi", "serpapi-bing"), "serpapi"),
        EnvironmentSpec(SERPAPI_KEY_ENV, "Search Intelligence / Observability", "Credencial BYOK SerpApi.", "segredo/API key", sensitive=True, required_when="SERP mode=live."),
        EnvironmentSpec(SERP_FIXTURE_PATH_ENV, "Search Intelligence / Observability", "Fixture canônica do modo fixture.", "caminho de arquivo", required_when="SERP mode=fixture."),
        EnvironmentSpec(SERP_MAX_QUERIES_ENV, "Search Intelligence / Observability", "Teto de queries por execução.", "inteiro > 0", default="10"),
        EnvironmentSpec(SERP_MAX_REQUESTS_ENV, "Search Intelligence / Observability", "Orçamento máximo de tentativas HTTP do provider.", "inteiro > 0", default="10"),
        EnvironmentSpec(SERP_MAX_DEPTH_ENV, "Search Intelligence / Observability", "Profundidade máxima de resultados.", "inteiro > 0", default="20"),
        EnvironmentSpec(SERP_MAX_COMPETITORS_ENV, "Search Intelligence / Observability", "Teto de concorrentes derivados.", "inteiro >= 0", default="10"),
        EnvironmentSpec(SERP_TIMEOUT_ENV, "Search Intelligence / Observability", "Timeout por request Search.", "número > 0", default="20"),
        EnvironmentSpec(SERP_RETRIES_ENV, "Search Intelligence / Observability", "Retries do Search provider.", "inteiro >= 0", default="1"),
        EnvironmentSpec(SERP_MIN_INTERVAL_ENV, "Search Intelligence / Observability", "Intervalo mínimo entre requests Search.", "número >= 0", default="1"),
        EnvironmentSpec(SEARCH_AI_PROVIDER_ENV, "Search Intelligence / Observability", "Provider da análise competitiva por IA.", "enum", ("none", "fixture", "openai"), "none"),
        EnvironmentSpec(GSC_ACCESS_TOKEN_ENV, "Search Intelligence / Observability", "OAuth bearer token temporário do Google Search Console.", "segredo/token", sensitive=True, required_when="Collectors GSC live."),
    )


def _platform_specs() -> tuple[EnvironmentSpec, ...]:
    return (
        EnvironmentSpec(PLATFORM_BACKEND_ENV, "Control plane / SaaS", "Backend do control plane.", "enum", ("sqlite", "postgresql"), "sqlite", notes="Opção de operador/deployment; não é configuração de tenant."),
        EnvironmentSpec(PLATFORM_DATABASE_URL_ENV, "Control plane / SaaS", "DSN PostgreSQL do control plane.", "segredo/DSN", sensitive=True, required_when="backend=postgresql", notes="Pode conter credenciais; nunca é gravado no INI."),
        EnvironmentSpec(API_DOCS_ENV, "Web API / Identity", "Habilita documentação interativa da API.", "booleano", ("true", "false"), "false"),
        EnvironmentSpec(API_AUDITS_ROOT_ENV, "Web API / Identity", "Raiz de auditorias usada pela Web API.", "caminho", default="audits"),
        EnvironmentSpec(API_AUTH_MODE_ENV, "Web API / Identity", "Modo de autenticação da API.", "enum", ("deny", "trusted-header", "oidc"), "deny"),
        EnvironmentSpec(API_TRUSTED_HEADER_ENV, "Web API / Identity", "Header de identidade no modo trusted-header.", "header HTTP", default="x-rasai-user-id"),
        EnvironmentSpec(OIDC_ISSUER_ENV, "Web API / Identity", "Issuer OIDC HTTPS exato.", "URL HTTPS", required_when="auth mode=oidc"),
        EnvironmentSpec(OIDC_CLIENT_ID_ENV, "Web API / Identity", "Client ID OIDC.", "texto", required_when="auth mode=oidc"),
        EnvironmentSpec(OIDC_AUDIENCE_ENV, "Web API / Identity", "Audience esperada para bearer JWT.", "texto", default="client_id configurado", required_when="auth mode=oidc"),
        EnvironmentSpec(OIDC_REDIRECT_URI_ENV, "Web API / Identity", "Redirect URI do Authorization Code flow.", "URL HTTPS; HTTP apenas loopback", required_when="auth mode=oidc"),
        EnvironmentSpec(OIDC_SESSION_SECRET_ENV, "Web API / Identity", "Segredo HMAC da sessão web.", "segredo", sensitive=True, required_when="auth mode=oidc"),
        EnvironmentSpec(OIDC_CLIENT_SECRET_ENV_REF, "Web API / Identity", "Nome da variável que contém o client secret OIDC.", "referência de variável", required_when="IdP que exija confidential client.", notes="O valor persistido é somente o nome da variável; o secret real continua fora do INI."),
        EnvironmentSpec(OIDC_ALGORITHMS_ENV, "Web API / Identity", "Algoritmos JWT aceitos.", "lista CSV", default="RS256,ES256"),
        EnvironmentSpec(OIDC_SCOPES_ENV, "Web API / Identity", "Scopes OIDC solicitados.", "lista CSV", default="openid,profile,email"),
        EnvironmentSpec(OIDC_SESSION_TTL_ENV, "Web API / Identity", "TTL da sessão web em segundos.", "inteiro 300..86400", default="28800"),
        EnvironmentSpec(REMOTE_BASE_URL_ENV, "Remote control plane", "URL do control plane remoto.", "URL HTTPS; HTTP apenas loopback", required_when="Modo remoto.", notes="Configuração do cliente do control plane SaaS."),
        EnvironmentSpec(REMOTE_TOKEN_ENV_REF, "Remote control plane", "Nome da variável que contém o bearer token remoto.", "referência de variável", required_when="Autenticação bearer remota.", notes="O token real não é persistido; apenas a referência pode ser salva."),
        EnvironmentSpec(REMOTE_USER_ID_ENV, "Remote control plane", "User ID trusted-header apenas para desenvolvimento loopback.", "texto", required_when="Somente loopback; proibido para host remoto."),
        EnvironmentSpec(REMOTE_TIMEOUT_ENV, "Remote control plane", "Timeout do cliente remoto.", "número > 0 e <= 300", default="30"),
    )


def _fixed_specs() -> tuple[EnvironmentSpec, ...]:
    return (
        *_application_specs(),
        *_content_specs(),
        *_web_specs(),
        *_apdex_specs(),
        *_search_specs(),
        *_platform_specs(),
        EnvironmentSpec(
            "RASAI_PLAYWRIGHT_CHROMIUM_EXECUTABLE",
            "Browser / Playwright",
            "Caminho opcional para um executável Chromium específico.",
            "caminho de arquivo existente",
            required_when="Somente para substituir a descoberta/instalação padrão do Playwright.",
        ),
        EnvironmentSpec(
            "RASAI_BROWSER_LOCALE",
            "Browser / Playwright",
            "Locale do contexto Playwright/browser usado na aquisição renderizada.",
            "locale BCP 47",
            default="pt-BR",
            impact="Pode alterar idioma ou variante entregue por sites que negociam conteúdo pelo locale.",
        ),
    )


def _provider_specs() -> tuple[EnvironmentSpec, ...]:
    result: list[EnvironmentSpec] = []
    for reg in provider_registrations():
        name = reg.provider_name
        mimo_note = " O adapter atual exige chave PAYG `sk-...`; Token Plan `tp-...` não é compatível." if name == "MIMO" else ""
        result.append(
            EnvironmentSpec(
                reg.key_env,
                "IA - credenciais",
                f"Credencial do provider {reg.display_name}.{mimo_note}",
                "segredo/API key",
                required_when=f"Obrigatória ao selecionar `{reg.id}`; em AUTO torna o provider elegível quando aplicável.",
                sensitive=True,
                impact="Pode habilitar chamadas externas e cobrança do provider.",
                source=KEY_SOURCES[name],
            )
        )
        result.append(
            EnvironmentSpec(
                reg.model_env,
                "IA - modelos e reasoning",
                f"Modelo usado por {reg.display_name} sem --ai-model explícito.",
                "enum",
                tuple(reg.supported_models),
                SIMPLE_DEFAULT_MODELS[name],
                impact="Modelos podem ter preço, latência e capacidade diferentes.",
            )
        )
        effort_env = provider_reasoning_env(name)
        if effort_env:
            result.append(
                EnvironmentSpec(
                    effort_env,
                    "IA - modelos e reasoning",
                    f"Esforço/profundidade de reasoning para {reg.display_name}.",
                    "enum",
                    tuple(REASONING_OPTIONS[name]),
                    LOWEST_REASONING[name],
                    impact="Esforço maior pode elevar latência, tokens e custo.",
                )
            )
        if reg.endpoint_env:
            result.append(
                EnvironmentSpec(
                    reg.endpoint_env,
                    "IA - endpoints avançados",
                    f"Override do endpoint HTTP usado por {reg.display_name}.",
                    "URL absoluta HTTP(S)",
                    default=ENDPOINT_DEFAULTS.get(name),
                    required_when="Nunca no uso normal; altere apenas para endpoint compatível/proxy controlado.",
                    impact="Endpoint incorreto pode enviar dados ao destino errado ou causar falha/cobrança inesperada.",
                )
            )
    return tuple(result)


def environment_specs() -> tuple[EnvironmentSpec, ...]:
    known = {spec.name: spec for spec in (*_fixed_specs(), *_provider_specs())}
    return tuple(
        known.get(
            name,
            EnvironmentSpec(
                name,
                "Aplicação e execução",
                "Variável reconhecida pelo RASAi.",
                "texto",
                sensitive=(is_secret(name) and not is_secret_reference_name(name)),
                required_when="Sem default seguro; consulte a documentação antes de definir.",
                impact="Impacto não classificado automaticamente.",
            ),
        )
        for name in ENV_NAMES
    )


SPECS = environment_specs()
SPEC_BY_NAME = {spec.name: spec for spec in SPECS}


def _is_sensitive_spec(spec: EnvironmentSpec) -> bool:
    if spec.sensitive:
        return True
    if is_secret_reference_name(spec.name):
        return False
    return is_secret(spec.name)


def _status(spec: EnvironmentSpec) -> str:
    value = (os.environ.get(spec.name) or "").strip()
    sensitive = _is_sensitive_spec(spec)
    if value:
        if sensitive:
            origin = environment_origin(spec.name, value)
            suffix = f" [{origin}]" if origin else ""
            return paint("[SET]" + suffix, GREEN, bold=True)
        if value.casefold() in {"true", "1", "yes", "on"}:
            return paint(value, GREEN, bold=True)
        if value.casefold() in {"false", "0", "no", "off"}:
            return paint(value, DIM)
        return paint(value[:60], CYAN)
    if sensitive:
        origin = environment_origin(spec.name, None)
        if origin:
            return paint(f"<não ativa> [{origin}]", DIM)
    if spec.default is not None:
        return paint(f"<default efetivo: {spec.default}>", DIM)
    return paint("<sem default; condicional>", DIM)


def _docs_path() -> Path | None:
    for path in (
        Path.cwd() / "docs" / DOCUMENT_NAME,
        Path(__file__).resolve().parents[2] / "docs" / DOCUMENT_NAME,
    ):
        if path.is_file():
            return path
    return None


def _open_docs(state: object) -> None:
    path = _docs_path()
    if path is None:
        setattr(state, "error", f"documentação não encontrada: docs/{DOCUMENT_NAME}")
        return
    ok, detail = open_external_path(path)
    setattr(state, "operation", "LOCAL:OPEN_ENV_DOCUMENTATION")
    setattr(state, "error", "" if ok else detail)


def _absolute_url(value: str, *, https_only: bool = False, loopback_http: bool = False) -> str:
    parsed = urlparse(value)
    if not parsed.hostname or parsed.username is not None or parsed.password is not None or parsed.fragment:
        raise ValueError("use URL absoluta sem credenciais ou fragment")
    if https_only:
        if parsed.scheme != "https":
            raise ValueError("use URL HTTPS absoluta")
    elif parsed.scheme not in {"http", "https"}:
        raise ValueError("use URL HTTP(S) absoluta")
    if parsed.scheme == "http" and loopback_http and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError("HTTP permitido somente em loopback")
    return value


def _validate(name: str, raw: str) -> str:
    value = validate_existing(name, raw)
    if name == "RASAI_LOG_LEVEL":
        value = value.upper()
        if value not in {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"}:
            raise ValueError("use CRITICAL, ERROR, WARNING, INFO ou DEBUG")
    elif name == "RASAI_CONFIG":
        path = Path(value).expanduser()
        if not path.is_file():
            raise ValueError("arquivo TOML configurado não existe")
        value = str(path)
    elif name == "RASAI_LIGHTHOUSE_CATEGORIES":
        allowed = ("performance", "accessibility", "best-practices", "seo", "agentic-browsing")
        items = [item.strip().casefold() for item in value.split(",") if item.strip()]
        if not items or any(item not in allowed for item in items):
            raise ValueError("categorias suportadas: " + ", ".join(allowed))
        if len(items) != len(set(items)):
            raise ValueError("não duplique categorias Lighthouse")
        value = ",".join(items)
    elif name == SERP_MODE_ENV:
        value = value.casefold()
        if value not in {"disabled", "live", "fixture"}:
            raise ValueError("use disabled, live ou fixture")
    elif name == SERP_PROVIDER_ENV:
        value = value.casefold()
        if value not in {"serpapi", "serpapi-bing"}:
            raise ValueError("use serpapi ou serpapi-bing")
    elif name in {SERP_MAX_QUERIES_ENV, SERP_MAX_REQUESTS_ENV, SERP_MAX_DEPTH_ENV}:
        if int(value) <= 0:
            raise ValueError("use inteiro > 0")
    elif name in {SERP_MAX_COMPETITORS_ENV, SERP_RETRIES_ENV}:
        if int(value) < 0:
            raise ValueError("use inteiro >= 0")
    elif name == SERP_TIMEOUT_ENV:
        if float(value) <= 0:
            raise ValueError("use número > 0")
    elif name == SERP_MIN_INTERVAL_ENV:
        if float(value) < 0:
            raise ValueError("use número >= 0")
    elif name == SERP_FIXTURE_PATH_ENV:
        path = Path(value).expanduser()
        if not path.is_file():
            raise ValueError("fixture SERP configurada não existe")
        value = str(path)
    elif name == SEARCH_AI_PROVIDER_ENV:
        value = value.casefold()
        if value not in {"none", "fixture", "openai"}:
            raise ValueError("use none, fixture ou openai")
    elif name == PLATFORM_BACKEND_ENV:
        value = value.casefold()
        if value not in {"sqlite", "postgresql"}:
            raise ValueError("use sqlite ou postgresql")
    elif name == PLATFORM_DATABASE_URL_ENV:
        parsed = urlparse(value)
        if parsed.scheme not in {"postgres", "postgresql"} or not parsed.hostname:
            raise ValueError("use DSN PostgreSQL válida")
    elif name == API_DOCS_ENV:
        if value.casefold() not in {"true", "false", "1", "0", "yes", "no", "on", "off"}:
            raise ValueError("use true/false")
    elif name == API_AUTH_MODE_ENV:
        value = value.casefold()
        if value not in {"deny", "trusted-header", "oidc"}:
            raise ValueError("use deny, trusted-header ou oidc")
    elif name == API_TRUSTED_HEADER_ENV:
        value = value.casefold()
        if not value or any(character.isspace() for character in value):
            raise ValueError("header inválido")
    elif name == OIDC_ISSUER_ENV:
        value = _absolute_url(value, https_only=True)
        if urlparse(value).query:
            raise ValueError("issuer OIDC não aceita query")
    elif name == DYNATRACE_BASE_URL_ENV:
        value = _absolute_url(value, https_only=True)
    elif name in {OIDC_REDIRECT_URI_ENV, REMOTE_BASE_URL_ENV}:
        value = _absolute_url(value, loopback_http=True)
    elif name in {OIDC_CLIENT_SECRET_ENV_REF, REMOTE_TOKEN_ENV_REF}:
        value = validate_environment_reference(value)
    elif name == OIDC_ALGORITHMS_ENV:
        allowed = {"RS256", "RS384", "RS512", "ES256", "ES384", "ES512"}
        items = [item.strip().upper() for item in value.split(",") if item.strip()]
        if not items or any(item not in allowed for item in items):
            raise ValueError("algoritmo OIDC não suportado")
        value = ",".join(dict.fromkeys(items))
    elif name == OIDC_SCOPES_ENV:
        items = [item.strip() for item in value.split(",") if item.strip()]
        if "openid" not in items:
            raise ValueError("scopes OIDC devem incluir openid")
        value = ",".join(dict.fromkeys(items))
    elif name == OIDC_SESSION_TTL_ENV:
        ttl = int(value)
        if ttl < 300 or ttl > 86400:
            raise ValueError("TTL deve estar entre 300 e 86400")
    elif name == REMOTE_TIMEOUT_ENV:
        timeout = float(value)
        if timeout <= 0 or timeout > 300:
            raise ValueError("timeout deve ser >0 e <=300")
    elif name == DYNATRACE_CONFIG_JSON_ENV:
        path = Path(value).expanduser()
        if not path.is_file():
            raise ValueError("JSON Dynatrace configurado não existe")
        value = str(path)

    spec = SPEC_BY_NAME.get(name)
    if spec and spec.category == "IA - endpoints avançados":
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("use URL absoluta http:// ou https://")
    return value


def _apply_change(state: object, name: str) -> None:
    issues = list(apply_environment_defaults(state, names={name}))
    issues.extend(apply_m23_environment_defaults(state, names={name}))
    setattr(state, "error", "; ".join(issues))
    for selection, provider in PROVIDERS.items():
        if KEY_ENV[provider] == name:
            getattr(state, "runtime_blocks", {}).pop(selection, None)


def _sync_secret_state(state: object, name: str) -> None:
    if current_matches_persisted(name):
        clear_secret_volatile(state, name)
    else:
        mark_secret_volatile(state, name)


def _prompt_choice(spec: EnvironmentSpec) -> str | None:
    print("\nValores aceitos:")
    for index, item in enumerate(spec.accepted, 1):
        marker = " [default]" if item == spec.default else ""
        print(f" {index}. {item}{marker}")
    print(" V. Voltar")
    raw = input("Escolha: ").strip()
    if raw.upper() == "V":
        return None
    if raw in spec.accepted:
        return raw
    try:
        return spec.accepted[int(raw) - 1]
    except (ValueError, IndexError) as exc:
        raise ValueError("opção inválida") from exc


def _render_detail(spec: EnvironmentSpec) -> None:
    print(spec.name)
    print("=" * min(max(len(spec.name), 40), 100))
    print(f"Grupo          : {spec.category}")
    print(f"Para que serve : {spec.purpose}")
    print(f"Tipo           : {spec.value_type}")
    if spec.accepted:
        print(f"Valores aceitos: {', '.join(spec.accepted)}")
    print(f"Default efetivo: {spec.default if spec.default is not None else 'nenhum seguro/aplicável'}")
    print(f"Obrigatória    : {spec.required_when}")
    print(f"Sensível       : {'SIM - nunca exibida nem gravada no INI' if _is_sensitive_spec(spec) else 'não'}")
    print(f"Custo/impacto  : {spec.impact}")
    print(f"Valor ambiente : {_status(spec)}")
    if spec.example:
        print(f"Exemplo        : {spec.example}")
    if spec.source:
        print(f"Como obter/ref.: {spec.source}")
    if spec.notes:
        print(f"Observação     : {spec.notes}")
    if spec.default is not None and not (os.environ.get(spec.name) or "").strip():
        print(paint("Nota: o default já é aplicado internamente; não é necessário criar a variável apenas para repeti-lo.", DIM))


def _persist_secret(state: object, spec: EnvironmentSpec) -> None:
    name = spec.name
    render_header(state)
    current = (os.environ.get(name) or "").strip()
    user_value = user_environment_value(name)
    machine_value = machine_environment_value(name)
    print("PERSISTÊNCIA DE CREDENCIAL NO WINDOWS\n")
    print(f"Variável           : {name}")
    print(f"Sessão atual       : {'[SET]' if current else '<não definida>'}")
    print(f"Windows / User     : {'[PERSISTIDA]' if user_value else '<não persistida>'}")
    print(f"Windows / Machine  : {'[PERSISTIDA]' if machine_value else '<não persistida>'}")
    print("\nP. Persistir no Windows/User o valor atual da sessão")
    print("R. Remover a persistência Windows/User (mantém a sessão atual)")
    print("V. Voltar")
    action = input("Escolha: ").strip().upper()
    if action == "V":
        return
    if os.name != "nt":
        setattr(state, "error", "persistência de credenciais no SO está disponível somente no Windows")
        return
    if action == "P":
        if not current:
            setattr(state, "error", "defina a credencial na sessão antes de persistir")
            return
        if input(f"Confirmar persistência de {name} no ambiente USER do Windows? Digite SIM: ").strip().upper() != "SIM":
            setattr(state, "error", "persistência cancelada")
            return
        persist_user_environment(name, current)
        _sync_secret_state(state, name)
        setattr(state, "error", "")
        setattr(state, "operation", "LOCAL:PERSIST_USER_SECRET")
    elif action == "R":
        if user_value is None:
            setattr(state, "error", f"{name} não possui persistência no escopo Windows/User")
            return
        if input(f"Confirmar remoção da persistência USER de {name}? Digite SIM: ").strip().upper() != "SIM":
            setattr(state, "error", "remoção cancelada")
            return
        remove_user_environment(name)
        _sync_secret_state(state, name)
        setattr(state, "error", "")
        setattr(state, "operation", "LOCAL:REMOVE_USER_SECRET")


def _variable_menu(state: object, spec: EnvironmentSpec) -> None:
    while True:
        render_header(state)
        _render_detail(spec)
        sensitive = _is_sensitive_spec(spec)
        if sensitive:
            print("\nAÇÕES\nS. Setar/alterar sessão\nR. Remover da sessão\nP. Persistência Windows/User\nD. Documentação\nV. Voltar")
        else:
            print("\nAÇÕES\nS. Setar/alterar\nR. Remover override\nD. Documentação\nV. Voltar")
        action = input("Escolha: ").strip().upper()
        if action == "V":
            return
        if action == "D":
            _open_docs(state)
            continue
        if action == "P" and sensitive:
            try:
                _persist_secret(state, spec)
            except (OSError, ValueError) as exc:
                setattr(state, "error", f"falha de persistência: {type(exc).__name__}: {exc}")
            continue
        if action == "R":
            os.environ.pop(spec.name, None)
            if sensitive:
                _sync_secret_state(state, spec.name)
            _apply_change(state, spec.name)
            continue
        if action != "S":
            continue
        try:
            if spec.accepted and spec.value_type in {"enum", "enum inteiro", "booleano"}:
                raw = _prompt_choice(spec)
                if raw is None:
                    continue
            else:
                raw = getpass(f"{spec.name}: ") if sensitive else input(f"{spec.name}: ")
            os.environ[spec.name] = _validate(spec.name, raw)
            if sensitive:
                _sync_secret_state(state, spec.name)
            _apply_change(state, spec.name)
        except (ValueError, OverflowError) as exc:
            setattr(state, "error", str(exc))


def _category_menu(state: object, title: str, specs: tuple[EnvironmentSpec, ...]) -> None:
    while True:
        render_header(state)
        print(f"VARIÁVEIS DE AMBIENTE - {title}\n")
        for index, spec in enumerate(specs, 1):
            print(f"{index:2d}. {spec.name:<44} {_status(spec)}")
        print("\nAÇÕES\nD. Abrir documentação detalhada\nV. Voltar")
        raw = input("Selecione a variável: ").strip().upper()
        if raw == "V":
            return
        if raw == "D":
            _open_docs(state)
            continue
        try:
            _variable_menu(state, specs[int(raw) - 1])
        except (ValueError, IndexError):
            setattr(state, "error", "variável inválida")


def environment_menu(state: object) -> None:
    """Show all known product environment variables grouped by functional scope."""
    grouped = {
        category: tuple(spec for spec in SPECS if spec.category == category)
        for category in CATEGORIES
    }
    while True:
        render_header(state)
        print("CONFIGURAÇÃO AVANÇADA - VARIÁVEIS DE AMBIENTE\n")
        print("Defaults coerentes são aplicados internamente; defina variável para override/credencial.")
        print("Secrets não entram no INI. Opções de control plane/Identity são de operador, não de tenant.\n")
        choices: dict[str, str] = {}
        for index, category in enumerate(CATEGORIES, 1):
            specs = grouped[category]
            configured = sum(1 for spec in specs if (os.environ.get(spec.name) or "").strip())
            print(f" {index:2d}. {category:<34} {configured}/{len(specs)} override(s) definidos")
            choices[str(index)] = category
        print("\n A. Todas as variáveis")
        print(f" D. Abrir documentação detalhada (docs/{DOCUMENT_NAME})")
        print(" V. Voltar")
        raw = input("Escolha: ").strip().upper()
        if raw == "V":
            return
        if raw == "D":
            _open_docs(state)
            continue
        if raw == "A":
            _category_menu(state, "Todas", SPECS)
            continue
        category = choices.get(raw)
        if category:
            _category_menu(state, category, grouped[category])
        else:
            setattr(state, "error", "grupo inválido")