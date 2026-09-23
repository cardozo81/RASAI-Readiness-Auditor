"""Register CAT-10 passive-security configuration in the canonical console catalog."""
from __future__ import annotations

from rasai.passive_security import (
    COOKIES_ENV,
    ENABLED_ENV,
    EXTERNAL_TIMEOUT_ENV,
    HEADERS_ENV,
    KEV_ENV,
    OSV_ENV,
    RESOURCES_ENV,
    RUNTIME_ENV,
    THIRD_PARTY_ENV,
)

CORE_CATEGORY = "CAT-10 / Segurança passiva"
VULN_CATEGORY = "CAT-10 / Vulnerability Intelligence"


def install() -> None:
    from rasai import console_environment as base

    if getattr(base, "_rasai_passive_security_environment_installed", False):
        return

    original_fixed_specs = base._fixed_specs
    original_validate = base._validate

    for name in (
        ENABLED_ENV, HEADERS_ENV, COOKIES_ENV, RESOURCES_ENV, THIRD_PARTY_ENV,
        RUNTIME_ENV, OSV_ENV, KEV_ENV, EXTERNAL_TIMEOUT_ENV,
    ):
        if name not in base.ENV_NAMES:
            base.ENV_NAMES = (*base.ENV_NAMES, name)

    categories = list(base.CATEGORIES)
    anchor = categories.index("Search Intelligence / Observability") if "Search Intelligence / Observability" in categories else len(categories)
    for category in reversed((CORE_CATEGORY, VULN_CATEGORY)):
        if category not in categories:
            categories.insert(anchor, category)
    base.CATEGORIES = tuple(categories)

    def fixed_specs_with_passive_security():
        items = list(original_fixed_specs())
        by_name = {item.name: index for index, item in enumerate(items)}
        additions = (
            base.EnvironmentSpec(
                ENABLED_ENV, CORE_CATEGORY,
                "Habilita o CAT-10 no runtime. Normalmente é projetado automaticamente pela seleção do catálogo.",
                "booleano", ("true", "false"), "false",
                impact="Não executa active scanning; apenas consome evidência persistida e fontes externas explicitamente habilitadas.",
                example=f"{ENABLED_ENV}=true",
                source="docs/PASSIVE_SECURITY_CATALOG.md",
            ),
            base.EnvironmentSpec(
                HEADERS_ENV, CORE_CATEGORY,
                "Analisa HTTPS/redirects, security headers, CSP, CORS e políticas cross-origin já persistidas.",
                "booleano", ("true", "false"), "true",
                example=f"{HEADERS_ENV}=true", source="docs/PASSIVE_SECURITY_CATALOG.md",
            ),
            base.EnvironmentSpec(
                COOKIES_ENV, CORE_CATEGORY,
                "Analisa apenas atributos de Set-Cookie; valores de cookies não são copiados para o CAT-10.",
                "booleano", ("true", "false"), "true",
                example=f"{COOKIES_ENV}=true", source="docs/PASSIVE_SECURITY_CATALOG.md",
            ),
            base.EnvironmentSpec(
                RESOURCES_ENV, CORE_CATEGORY,
                "Inventaria scripts, recursos, forms e iframes a partir do HTML bruto/renderizado já persistido.",
                "booleano", ("true", "false"), "true",
                example=f"{RESOURCES_ENV}=true", source="docs/PASSIVE_SECURITY_CATALOG.md",
            ),
            base.EnvironmentSpec(
                THIRD_PARTY_ENV, CORE_CATEGORY,
                "Habilita classificação/diagnóstico contextual de recursos first-party/third-party, SRI e destinos externos.",
                "booleano", ("true", "false"), "true",
                example=f"{THIRD_PARTY_ENV}=true", source="docs/PASSIVE_SECURITY_CATALOG.md",
            ),
            base.EnvironmentSpec(
                RUNTIME_ENV, CORE_CATEGORY,
                "Correlaciona requestfailed, HTTP errors, console.error e page errors persistidos; não altera Apdex.",
                "booleano", ("true", "false"), "true",
                example=f"{RUNTIME_ENV}=true", source="docs/PASSIVE_SECURITY_CATALOG.md",
            ),
            base.EnvironmentSpec(
                OSV_ENV, VULN_CATEGORY,
                "Consulta OSV somente quando biblioteca + versão + ecosystem foram identificados com confiança suficiente.",
                "booleano", ("true", "false"), "true",
                impact="Chamada externa contém somente componente/versionamento; nenhuma URL auditada é enviada.",
                example=f"{OSV_ENV}=true", source="docs/PASSIVE_SECURITY_CATALOG.md",
            ),
            base.EnvironmentSpec(
                KEV_ENV, VULN_CATEGORY,
                "Correlaciona CVEs retornados por OSV com CISA Known Exploited Vulnerabilities (KEV).",
                "booleano", ("true", "false"), "true",
                impact="KEV altera priorização operacional, não reescreve a severidade canônica da fonte.",
                example=f"{KEV_ENV}=true", source="docs/PASSIVE_SECURITY_CATALOG.md",
            ),
            base.EnvironmentSpec(
                EXTERNAL_TIMEOUT_ENV, VULN_CATEGORY,
                "Timeout por chamada externa de vulnerability intelligence.",
                "número > 0", default="15",
                impact="Limita espera de OSV/CISA KEV; indisponibilidade externa reduz cobertura e não vira finding do site.",
                example=f"{EXTERNAL_TIMEOUT_ENV}=15", source="docs/PASSIVE_SECURITY_CATALOG.md",
            ),
        )
        for spec in additions:
            index = by_name.get(spec.name)
            if index is None:
                by_name[spec.name] = len(items)
                items.append(spec)
            else:
                items[index] = spec
        return tuple(items)

    bool_names = {
        ENABLED_ENV, HEADERS_ENV, COOKIES_ENV, RESOURCES_ENV, THIRD_PARTY_ENV,
        RUNTIME_ENV, OSV_ENV, KEV_ENV,
    }

    def validate_with_passive_security(name: str, raw: str) -> str:
        value = str(raw).strip()
        if name in bool_names:
            lowered = value.casefold()
            if lowered in {"1", "true", "yes", "on", "sim", "s"}:
                return "true"
            if lowered in {"0", "false", "no", "off", "nao", "não", "n"}:
                return "false"
            raise ValueError(f"{name} aceita true/false")
        if name == EXTERNAL_TIMEOUT_ENV:
            number = float(value)
            if number <= 0 or number > 300:
                raise ValueError(f"{name} deve estar entre >0 e 300 segundos")
            return f"{number:g}"
        return original_validate(name, raw)

    base._fixed_specs = fixed_specs_with_passive_security
    base._validate = validate_with_passive_security
    base.SPECS = base.environment_specs()
    base.SPEC_BY_NAME = {spec.name: spec for spec in base.SPECS}
    base._rasai_passive_security_environment_installed = True

    from rasai import console_provider_environment as facade
    facade.CATEGORIES = base.CATEGORIES
    facade.refresh_specs()


__all__ = ["install", "CORE_CATEGORY", "VULN_CATEGORY"]
