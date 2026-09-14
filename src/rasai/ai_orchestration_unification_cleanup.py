"""Final public-surface cleanup for canonical AI orchestration.

No provider policy lives here. This module removes feature-local provider choices from
configuration/report metadata and keeps monitoring validation aligned with the canonical
provider registry.
"""
from __future__ import annotations

from dataclasses import replace
from typing import Any


_INSTALLED = False


def _install_search_monitor_validation() -> None:
    from rasai.provider_registry import cli_provider_choices
    from rasai.search_intelligence import monitoring

    allowed = frozenset((*cli_provider_choices(), "fixture"))

    def validate(self):
        if not self.query.strip():
            raise ValueError("monitor query must not be empty")
        if not self.domain_of_interest.strip():
            raise ValueError("monitor domain_of_interest must not be empty")
        if self.requested_depth <= 0:
            raise ValueError("monitor requested_depth must be greater than zero")
        if self.device not in {"mobile", "desktop"}:
            raise ValueError("monitor device must be mobile or desktop")
        if self.mode not in {"disabled", "live", "fixture"}:
            raise ValueError("monitor mode must be disabled, live or fixture")
        if self.max_content_pages < 0:
            raise ValueError("monitor max_content_pages must be >= 0")
        if self.ai_competitive and not self.compare_content:
            raise ValueError("Competitive AI monitoring requires compare_content")
        if self.ai_provider not in allowed:
            raise ValueError(
                "monitor AI provider must be a canonical RASAi provider, auto, none or fixture"
            )
        if self.ai_provider == "auto" and self.ai_model:
            raise ValueError("monitor ai_model cannot override AUTO provider selection")
        if self.ymyl_mode not in {"AUTO", "ON", "OFF"}:
            raise ValueError("monitor YMYL mode must be AUTO, ON or OFF")
        return self

    monitoring.SearchMonitorQuery.validate = validate


def _install_improvement_console_settings() -> None:
    from rasai import improvement_intelligence_console as console

    def install_settings(console_module) -> None:
        from rasai import console_settings as settings

        if getattr(settings, "_rasai_improvement_intelligence_settings", False):
            return
        original_values = settings._state_values
        original_assign = settings._assign

        def state_values(state: Any) -> dict[str, dict[str, str]]:
            values = dict(original_values(state))
            values["improvement_intelligence"] = {
                "enabled": "true" if bool(getattr(state, "improvement_enabled", False)) else "false",
                "domains": ",".join(
                    getattr(state, "improvement_domains", console.DEFAULT_DOMAINS)
                ),
                "max_recommendations": str(
                    int(getattr(state, "improvement_max_recommendations", 30))
                ),
                "timeout_seconds": f"{float(getattr(state, 'improvement_timeout', 240.0)):g}",
            }
            return values

        def assign(state: Any, section: str, option: str, raw: str) -> None:
            if section != "improvement_intelligence":
                original_assign(state, section, option, raw)
                return
            if option == "enabled":
                state.improvement_enabled = settings._parse_bool(raw)
            elif option == "domains":
                state.improvement_domains = console.parse_domains(raw)
            elif option == "max_recommendations":
                value = int(raw)
                if value < 1 or value > 100:
                    raise ValueError("use inteiro entre 1 e 100")
                state.improvement_max_recommendations = value
            elif option == "timeout_seconds":
                value = float(raw)
                if value <= 0:
                    raise ValueError("use número > 0")
                state.improvement_timeout = value
            else:
                raise ValueError(
                    f"opção desconhecida em improvement_intelligence: {option}"
                )

        settings._state_values = state_values
        settings._assign = assign
        settings._rasai_improvement_intelligence_settings = True

    console._install_settings = install_settings


def _install_improvement_report_contract() -> None:
    from rasai import improvement_intelligence_runtime as runtime

    original = runtime._install_report_contract
    if getattr(original, "_rasai_primary_ai_contract", False):
        return

    def install_report_contract() -> None:
        original()
        from rasai import report_contract, report_manifest, report_registry

        surfaces = []
        for surface in report_contract.REPORT_SURFACES:
            if surface.id == "improvement-intelligence":
                surface = replace(
                    surface,
                    optional_dependencies=(
                        "exatamente uma URL de entrada",
                        "IA principal habilitada (provider explícito ou AUTO)",
                        "Web Performance/Lighthouse",
                        "Search Intelligence",
                    ),
                    ai_usage=(
                        "Quando habilitada, executa o contrato estruturado de Improvement Intelligence "
                        "usando a seleção principal de IA. Em AUTO, reutiliza a política canônica de "
                        "custo, elegibilidade, quarentena, circuit breaker e fallback. Cada tentativa "
                        "é registrada em ai_provider_attempts."
                    ),
                )
            surfaces.append(surface)
        report_contract.REPORT_SURFACES = tuple(surfaces)
        report_contract.CANONICAL_NAV_ITEMS = tuple(
            (item.label, item.filename) for item in report_contract.REPORT_SURFACES
        )
        report_contract.CANONICAL_FILENAMES = tuple(
            item.filename for item in report_contract.REPORT_SURFACES
        )
        report_registry.REPORT_SURFACES = report_contract.REPORT_SURFACES
        report_manifest.REPORT_SURFACES = report_contract.REPORT_SURFACES

    install_report_contract._rasai_primary_ai_contract = True
    install_report_contract._rasai_original = original
    runtime._install_report_contract = install_report_contract


def _materialize_patched_saas_contract() -> None:
    """Run the dynamically patched SaaS installer before stale import aliases can run."""
    from rasai import improvement_intelligence_saas as saas

    saas.install()


def install_ai_orchestration_unification_cleanup() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    _install_search_monitor_validation()
    _install_improvement_console_settings()
    _install_improvement_report_contract()
    _materialize_patched_saas_contract()
    _INSTALLED = True
