"""Interactive-console reconciliation for standards service settings."""
from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

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


def _ensure_nonsecret_service_context_spec(legacy: object) -> None:
    specs = list(legacy.SPECS)
    if any(spec.name == GSC_SITE_URL_ENV for spec in specs):
        return
    specs.append(legacy.EnvironmentSpec(
        GSC_SITE_URL_ENV,
        "Métricas e padrões",
        "Propriedade Google Search Console usada por Search Analytics, Sitemaps e URL Inspection.",
        "texto",
        required_when="Obrigatória quando Google Search Console estiver habilitado.",
        sensitive=False,
        impact="Sem custo externo direto; restringe as consultas à propriedade autenticada configurada.",
        example="sc-domain:example.com",
        source="docs/STANDARDS_METRICS_AND_SERVICES.md",
        notes=(
            "Aceita propriedade de domínio no formato sc-domain:<domínio> ou propriedade "
            "URL-prefix http(s) absoluta. É configuração não secreta e pode ser persistida no INI."
        ),
    ))
    legacy.SPECS = tuple(specs)
    legacy.SPEC_BY_NAME = {spec.name: spec for spec in specs}
    if GSC_SITE_URL_ENV not in legacy.ENV_NAMES:
        legacy.ENV_NAMES = (*legacy.ENV_NAMES, GSC_SITE_URL_ENV)


def install() -> None:
    install_console_service_catalog()
    from rasai import console_environment as legacy
    from rasai import console_provider_environment as facade

    _ensure_nonsecret_service_context_spec(legacy)
    if getattr(legacy, "_rasai_standards_console_validation", False):
        facade.CATEGORIES = legacy.CATEGORIES
        facade.refresh_specs()
        return

    enabled_names = {item.enabled_env for item in services()}
    original_validate = legacy._validate

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
        return original_validate(name, raw)

    legacy._validate = validate
    legacy._rasai_standards_console_validation = True
    facade.CATEGORIES = legacy.CATEGORIES
    facade.refresh_specs()
