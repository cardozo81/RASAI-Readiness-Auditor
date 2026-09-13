"""Authoritative compatibility guard for PageSpeed/Lighthouse transport.

The PageSpeed Insights v5 ``runPagespeed`` transport accepts the standard Lighthouse
categories performance, accessibility, best-practices and seo.  RASAi has its own
agent/AI-readiness diagnostics, but those must not be serialized as a PageSpeed
``category`` parameter.

This module is deliberately a runtime compatibility layer so old persisted console
settings that still contain ``agentic-browsing`` do not poison the whole PageSpeed
request.  The obsolete token is removed when other valid categories exist; arbitrary
unknown categories are still rejected.
"""
from __future__ import annotations

from dataclasses import replace
from typing import Any, Iterable

OFFICIAL_PSI_CATEGORIES: tuple[str, ...] = (
    "performance",
    "accessibility",
    "best-practices",
    "seo",
)
OFFICIAL_PSI_CATEGORIES_CSV = ",".join(OFFICIAL_PSI_CATEGORIES)
LEGACY_UNSUPPORTED_CATEGORY = "agentic-browsing"
_INSTALLED = False


def _normalized_categories(values: Iterable[str], *, fallback: bool = False) -> tuple[str, ...]:
    raw = tuple(dict.fromkeys(str(item).strip().casefold() for item in values if str(item).strip()))
    unknown = tuple(
        item for item in raw
        if item not in OFFICIAL_PSI_CATEGORIES and item != LEGACY_UNSUPPORTED_CATEGORY
    )
    if unknown:
        raise ValueError("unsupported Lighthouse categories: " + ", ".join(sorted(unknown)))
    normalized = tuple(item for item in raw if item in OFFICIAL_PSI_CATEGORIES)
    if normalized:
        return normalized
    if fallback and raw and set(raw) == {LEGACY_UNSUPPORTED_CATEGORY}:
        return OFFICIAL_PSI_CATEGORIES
    if not raw and fallback:
        return OFFICIAL_PSI_CATEGORIES
    raise ValueError(
        "at least one PageSpeed/Lighthouse category is required: "
        + OFFICIAL_PSI_CATEGORIES_CSV
    )


def _normalize_csv(raw: str, *, fallback: bool = False) -> str:
    return ",".join(_normalized_categories(raw.split(","), fallback=fallback))


def _install_m21_guard() -> None:
    from rasai import m21_web_performance as m21

    m21.DEFAULT_CATEGORIES = OFFICIAL_PSI_CATEGORIES
    m21.ALLOWED_CATEGORIES = frozenset(OFFICIAL_PSI_CATEGORIES)

    original_validate = m21.WebPerformanceConfig.validate
    if not getattr(original_validate, "_rasai_official_psi_categories", False):
        def validate(self):
            categories = _normalized_categories(self.categories, fallback=True)
            if categories != tuple(self.categories):
                sanitized = m21.WebPerformanceConfig(
                    enabled=self.enabled,
                    max_pages=self.max_pages,
                    timeout_seconds=self.timeout_seconds,
                    categories=categories,
                    field_source=self.field_source,
                    pagespeed_api_key=self.pagespeed_api_key,
                    crux_api_key=self.crux_api_key,
                )
                return original_validate(sanitized)
            return original_validate(self)

        validate._rasai_official_psi_categories = True
        validate._rasai_original = original_validate
        m21.WebPerformanceConfig.validate = validate

    original_run = m21.PageSpeedInsightsClient.run
    if not getattr(original_run, "_rasai_official_psi_categories", False):
        def run(self, *, url: str, strategy: str, categories: tuple[str, ...], timeout_seconds: float):
            safe_categories = _normalized_categories(categories, fallback=True)
            return original_run(
                self,
                url=url,
                strategy=strategy,
                categories=safe_categories,
                timeout_seconds=timeout_seconds,
            )

        run._rasai_official_psi_categories = True
        run._rasai_original = original_run
        m21.PageSpeedInsightsClient.run = run


def _install_runtime_constants() -> None:
    # runtime_completion_extensions is installed earlier at the public entrypoint.
    # Updating its globals also keeps its already-installed closures honest.
    try:
        from rasai import runtime_completion_extensions as completion
        completion._PAGESPEED_LIGHTHOUSE_CATEGORIES = OFFICIAL_PSI_CATEGORIES
        completion._PAGESPEED_LIGHTHOUSE_CATEGORIES_CSV = OFFICIAL_PSI_CATEGORIES_CSV
    except Exception:
        pass

    try:
        from rasai import documented_contract_reconciliation as legacy
        legacy._CURRENT_PSI_CATEGORIES = OFFICIAL_PSI_CATEGORIES
    except Exception:
        pass

    for module_name in ("cli",):
        try:
            module = __import__(f"rasai.{module_name}", fromlist=[module_name])
        except Exception:
            continue
        if hasattr(module, "DEFAULT_CATEGORIES"):
            module.DEFAULT_CATEGORIES = OFFICIAL_PSI_CATEGORIES


def _install_console_contract() -> None:
    from rasai import console_config

    original_defaults = console_config.apply_environment_defaults
    if not getattr(original_defaults, "_rasai_official_psi_categories", False):
        def apply_environment_defaults(state: Any, env=None, names=None):
            issues = tuple(original_defaults(state, env, names))
            raw = str(getattr(state, "lighthouse_categories", "") or "")
            try:
                normalized = _normalize_csv(raw, fallback=True)
            except ValueError as exc:
                return (*issues, f"RASAI_LIGHTHOUSE_CATEGORIES: {exc}")
            if normalized != raw:
                state.lighthouse_categories = normalized
                if LEGACY_UNSUPPORTED_CATEGORY in raw.casefold():
                    issues = (*issues, "RASAI_LIGHTHOUSE_CATEGORIES: agentic-browsing removido do transporte PageSpeed; AI Readiness permanece no RASAi")
            return issues

        apply_environment_defaults._rasai_official_psi_categories = True
        apply_environment_defaults._rasai_original = original_defaults
        console_config.apply_environment_defaults = apply_environment_defaults

    original_validate = console_config.validate_env_value
    if not getattr(original_validate, "_rasai_official_psi_categories", False):
        def validate_env_value(name: str, value: str) -> str:
            if name == "RASAI_LIGHTHOUSE_CATEGORIES":
                return _normalize_csv(value, fallback=False)
            return original_validate(name, value)

        validate_env_value._rasai_official_psi_categories = True
        validate_env_value._rasai_original = original_validate
        console_config.validate_env_value = validate_env_value

    # Dataclass defaults were compiled when the module was imported. Normalize every
    # newly-created base console state without changing unrelated initialization.
    original_state_init = console_config.State.__init__
    if not getattr(original_state_init, "_rasai_official_psi_categories", False):
        def state_init(self, *args, **kwargs):
            original_state_init(self, *args, **kwargs)
            current = str(getattr(self, "lighthouse_categories", "") or "")
            if LEGACY_UNSUPPORTED_CATEGORY in current.casefold():
                self.lighthouse_categories = _normalize_csv(current, fallback=True)

        state_init._rasai_official_psi_categories = True
        state_init._rasai_original = original_state_init
        console_config.State.__init__ = state_init

    try:
        from rasai import console_environment
        original_environment_validate = console_environment._validate
        if not getattr(original_environment_validate, "_rasai_official_psi_categories", False):
            def environment_validate(name: str, raw: str) -> str:
                if name == "RASAI_LIGHTHOUSE_CATEGORIES":
                    return _normalize_csv(raw, fallback=False)
                return original_environment_validate(name, raw)

            environment_validate._rasai_official_psi_categories = True
            environment_validate._rasai_original = original_environment_validate
            console_environment._validate = environment_validate

        original_fixed_specs = console_environment._fixed_specs
        if not getattr(original_fixed_specs, "_rasai_official_psi_categories", False):
            def fixed_specs():
                output = []
                for spec in original_fixed_specs():
                    if spec.name == "RASAI_LIGHTHOUSE_CATEGORIES":
                        spec = replace(
                            spec,
                            accepted=OFFICIAL_PSI_CATEGORIES,
                            default=OFFICIAL_PSI_CATEGORIES_CSV,
                            example=f"RASAI_LIGHTHOUSE_CATEGORIES={OFFICIAL_PSI_CATEGORIES_CSV}",
                            notes=(
                                "Categorias oficiais transportadas ao PageSpeed Insights. "
                                "AI/GEO Readiness é analisado pelo RASAi e não é uma categoria PSI."
                            ),
                        )
                    output.append(spec)
                return tuple(output)

            fixed_specs._rasai_official_psi_categories = True
            fixed_specs._rasai_original = original_fixed_specs
            console_environment._fixed_specs = fixed_specs
    except Exception:
        pass


def _install_profile_contract() -> None:
    try:
        from rasai import console_execution_profiles as profiles
    except Exception:
        return

    modules = []
    for module in profiles.MODULES:
        categories = tuple(item for item in module.lighthouse_categories if item in OFFICIAL_PSI_CATEGORIES)
        if module.id == "geo":
            module = replace(
                module,
                description=(
                    "Prioriza evidências para descoberta/consumo por agentes e conteúdo semântico, "
                    "usando Lighthouse SEO/boas práticas apenas como evidência Web complementar."
                ),
                lighthouse_categories=categories,
            )
        elif categories != module.lighthouse_categories:
            module = replace(module, lighthouse_categories=categories)
        modules.append(module)
    profiles.MODULES = tuple(modules)
    profiles.MODULE_BY_ID = {item.id: item for item in profiles.MODULES}
    profiles._CATEGORY_ORDER = OFFICIAL_PSI_CATEGORIES


def _install_cli_contract() -> None:
    try:
        from rasai import cli_extensions
    except Exception:
        return
    original = cli_extensions.build_parser
    if getattr(original, "_rasai_official_psi_categories", False):
        return

    def build_parser():
        parser = original()
        try:
            subparsers = next(
                action for action in parser._actions
                if getattr(action, "choices", None) and "audit" in action.choices
            )
            audit_parser = subparsers.choices["audit"]
            for action in audit_parser._actions:
                if action.dest == "lighthouse_categories":
                    action.default = OFFICIAL_PSI_CATEGORIES_CSV
                    action.help = (
                        "categorias PageSpeed/Lighthouse: " + OFFICIAL_PSI_CATEGORIES_CSV
                        + "; AI/GEO Readiness é analisado separadamente pelo RASAi"
                    )
        except Exception:
            pass
        return parser

    build_parser._rasai_official_psi_categories = True
    build_parser._rasai_original = original
    cli_extensions.build_parser = build_parser


def install_lighthouse_transport_contract() -> None:
    """Install the official PSI category contract idempotently."""
    global _INSTALLED
    if _INSTALLED:
        return
    _install_runtime_constants()
    _install_m21_guard()
    _install_console_contract()
    _install_profile_contract()
    _install_cli_contract()
    _INSTALLED = True
