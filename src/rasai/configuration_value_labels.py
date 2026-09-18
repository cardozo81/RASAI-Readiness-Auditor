"""Presentation-only labels for closed configuration domains.

Canonical runtime values remain unchanged.  These helpers only project pt-BR labels
next to persisted/accepted technical values in the console and HTML reports.
"""
from __future__ import annotations

from typing import Any

_FIELD_TO_ENV = {
    "risk_profile": "RASAI_CONTENT_RISK_PROFILE",
    "ymyl_category": "RASAI_YMYL_CATEGORY",
    "page_purpose": "RASAI_PAGE_PURPOSE",
    "intended_audience": "RASAI_INTENDED_AUDIENCE",
    "experience_requirement": "RASAI_EXPERIENCE_REQUIREMENT",
    "freshness_sensitivity": "RASAI_FRESHNESS_SENSITIVITY",
    "content_origin": "RASAI_CONTENT_ORIGIN",
    "field_source": "RASAI_WEB_PERFORMANCE_FIELD_SOURCE",
    "lighthouse_categories": "RASAI_LIGHTHOUSE_CATEGORIES",
    "session_mode": "RASAI_APDEX_EXPERIENCE_SESSION_MODE",
    "error_scope": "RASAI_APDEX_EXPERIENCE_ERROR_SCOPE",
    "device": "RASAI_DEVICE_CONTEXT",
    "ymyl_mode": "SEARCH_YMYL_MODE",
    "source_mode": "CONTENT_CONTEXT_SOURCE_MODE",
}

_BY_NAME: dict[str, dict[str, str]] = {
    "RASAI_CONTENT_RISK_PROFILE": {
        "auto": "Automático",
        "standard": "Padrão",
        "ymyl": "YMYL",
    },
    "RASAI_YMYL_CATEGORY": {
        "auto": "Automático",
        "none": "Não YMYL",
        "health-safety": "Saúde e segurança",
        "financial-security": "Segurança financeira",
        "civic-societal": "Cívico e social",
        "other-significant-welfare": "Outro impacto significativo no bem-estar",
    },
    "RASAI_PAGE_PURPOSE": {
        "auto": "Automático",
        "informational": "Informacional",
        "transactional": "Transacional",
        "product-service": "Produto ou serviço",
        "review-comparison": "Avaliação ou comparação",
        "news-editorial": "Notícia ou editorial",
        "support-documentation": "Suporte ou documentação",
        "forum-ugc": "Fórum / conteúdo gerado por usuários",
        "other": "Outro",
    },
    "RASAI_INTENDED_AUDIENCE": {
        "auto": "Automático",
        "general": "Público geral",
        "professional": "Profissional",
        "mixed": "Misto",
    },
    "RASAI_EXPERIENCE_REQUIREMENT": {
        "auto": "Automático",
        "required": "Necessária",
        "beneficial": "Benéfica",
        "not-expected": "Não esperada",
    },
    "RASAI_FRESHNESS_SENSITIVITY": {
        "auto": "Automático",
        "low": "Baixa",
        "medium": "Média",
        "high": "Alta",
    },
    "RASAI_CONTENT_ORIGIN": {
        "auto": "Automático",
        "first-party": "Conteúdo próprio",
        "third-party": "Conteúdo de terceiros",
        "user-generated": "Conteúdo gerado por usuários",
        "mixed": "Misto",
    },
    "RASAI_CONSOLE_MODE": {
        "local": "Local",
        "remote": "Remoto",
    },
    "RASAI_LOG_LEVEL": {
        "critical": "Crítico",
        "error": "Erro",
        "warning": "Aviso",
        "info": "Informativo",
        "debug": "Depuração",
    },
    "RASAI_DEVICE_CONTEXT": {
        "mobile": "Dispositivo móvel",
        "desktop": "Computador",
        "both": "Móvel e computador",
    },
    "RASAI_WEB_PERFORMANCE_FIELD_SOURCE": {
        "auto": "Automática",
        "pagespeed": "PageSpeed",
        "crux": "Chrome UX Report (CrUX)",
        "none": "Sem dados de campo",
    },
    "RASAI_LIGHTHOUSE_CATEGORIES": {
        "performance": "Desempenho",
        "accessibility": "Acessibilidade",
        "best-practices": "Boas práticas",
        "seo": "SEO",
        "agentic-browsing": "Navegação agêntica",
    },
    "RASAI_APDEX_EXPERIENCE_SESSION_MODE": {
        "cold": "Sessão fria",
        "warm": "Sessão aquecida",
    },
    "RASAI_APDEX_EXPERIENCE_ERROR_SCOPE": {
        "navigation": "Navegação",
        "first-party": "Recursos próprios",
        "all": "Todos os recursos",
    },
    "RASAI_APDEX_ACQUISITION_MODE": {
        "auto": "Automática",
        "isolated": "Isolada",
    },
    "RASAI_SERP_MODE": {
        "disabled": "Desabilitado",
        "live": "Ao vivo",
        "fixture": "Dados de teste (fixture)",
    },
    "RASAI_SEARCH_AI_PROVIDER": {
        "none": "Nenhum",
        "fixture": "Dados de teste (fixture)",
        "openai": "OpenAI",
    },
    "RASAI_PLATFORM_DB_BACKEND": {
        "sqlite": "SQLite",
        "postgresql": "PostgreSQL",
    },
    "RASAI_API_AUTH_MODE": {
        "deny": "Negar acesso",
        "trusted-header": "Cabeçalho confiável",
        "oidc": "OpenID Connect (OIDC)",
    },
    "SEARCH_YMYL_MODE": {
        "auto": "Automático",
        "on": "Ativado",
        "off": "Desativado",
    },
    "CONTENT_CONTEXT_SOURCE_MODE": {
        "auto": "Automático",
        "manual": "Manual",
        "mixed": "Misto",
    },
    "RASAI_APDEX_EXPERIENCE_KPM": {
        "user_action_duration": "Duração da ação do usuário",
        "dom_interactive": "DOM interativo",
        "load_event_start": "Início do evento load",
        "load_event_end": "Fim do evento load",
        "response_start": "Início da resposta",
        "response_end": "Fim da resposta",
        "largest_contentful_paint": "Largest Contentful Paint (LCP)",
    },
}

_GENERIC = {
    "true": "Ativado",
    "false": "Desativado",
    "auto": "Automático",
    "none": "Nenhum",
    "disabled": "Desabilitado",
    "live": "Ao vivo",
    "fixture": "Dados de teste (fixture)",
    "mobile": "Dispositivo móvel",
    "desktop": "Computador",
    "both": "Móvel e computador",
    "cold": "Sessão fria",
    "warm": "Sessão aquecida",
    "navigation": "Navegação",
    "first-party": "Recursos próprios",
    "all": "Todos",
    "minimal": "Mínimo",
    "low": "Baixo",
    "medium": "Médio",
    "high": "Alto",
    "xhigh": "Extra alto",
    "max": "Máximo",
    "on": "Ativado",
    "off": "Desativado",
}


def _name(value: Any) -> str:
    raw = str(value or "").strip()
    return _FIELD_TO_ENV.get(raw, raw).upper()


def _token(value: Any) -> str:
    return str(value or "").strip()


def _preset_label(name: str, raw: str) -> str | None:
    if not name.startswith("RASAI_APDEX_") or not name.endswith("_PROFILE"):
        return None
    kind = (
        "client" if "_CLIENT_PROFILE" in name
        else "hardware" if "_HARDWARE_PROFILE" in name
        else "network" if "_NETWORK_PROFILE" in name
        else None
    )
    if kind is None:
        return None
    try:
        from rasai.synthetic_runtime_profiles import describe_preset
        return describe_preset(kind, raw)
    except (ImportError, KeyError):
        return None


def configuration_value_label(name: Any, value: Any) -> str | None:
    """Return a pt-BR label without changing the canonical value."""
    raw = _token(value)
    if not raw:
        return None
    canonical_name = _name(name)
    lowered = raw.casefold()
    specific = _BY_NAME.get(canonical_name, {})
    if lowered in specific:
        return specific[lowered]
    preset = _preset_label(canonical_name, raw)
    if preset:
        return preset
    if "REASONING" in canonical_name and lowered in _GENERIC:
        return _GENERIC[lowered]
    if canonical_name.endswith("_PROVIDER") or "_PROVIDER_" in canonical_name:
        if lowered == "auto":
            return "Automático"
        if lowered == "none":
            return "Nenhum"
        return None
    return _GENERIC.get(lowered)


def _combined(name: Any, value: Any, *, translated_first: bool) -> str:
    raw = _token(value)
    if not raw:
        return "-"
    label = configuration_value_label(name, raw)
    if not label or label.casefold() == raw.casefold():
        return raw
    return f"{label} ({raw})" if translated_first else f"{raw} ({label})"


def configuration_value_choice(name: Any, value: Any) -> str:
    """Selection item: human pt-BR first, canonical token in parentheses."""
    return _combined(name, value, translated_first=True)


def configuration_value_info(name: Any, value: Any) -> str:
    """Informational domain: canonical token first, pt-BR meaning in parentheses."""
    return _combined(name, value, translated_first=False)


def configuration_value_report(name: Any, value: Any) -> str:
    """HTML report: pt-BR label first while preserving the canonical token."""
    return _combined(name, value, translated_first=True)


def configuration_csv_info(name: Any, value: Any) -> str:
    items = [item.strip() for item in str(value or "").split(",") if item.strip()]
    return ", ".join(configuration_value_info(name, item) for item in items) or "-"


def configuration_csv_report(name: Any, value: Any, *, separator: str = " · ") -> str:
    items = [item.strip() for item in str(value or "").split(",") if item.strip()]
    return separator.join(configuration_value_report(name, item) for item in items) or "-"


__all__ = [
    "configuration_value_label",
    "configuration_value_choice",
    "configuration_value_info",
    "configuration_value_report",
    "configuration_csv_info",
    "configuration_csv_report",
]
