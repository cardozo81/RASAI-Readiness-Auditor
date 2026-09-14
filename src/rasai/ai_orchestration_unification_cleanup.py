"""Final public-surface cleanup for canonical AI orchestration.

No provider policy lives here. This module removes feature-local provider choices from
configuration/report metadata and keeps monitoring, execution profiles and console state
aligned with the canonical provider runtime.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import replace
from typing import Any, Iterator


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


def _install_execution_profile_contract() -> None:
    """Make deep-analysis profiles consume the same primary AI selection as the audit."""
    from rasai import console_execution_profile_readiness as readiness
    from rasai import console_execution_profiles as profiles
    from rasai.improvement_intelligence_console import _single_url_ready

    modules = []
    for item in profiles.MODULES:
        if item.id == "deep-analysis":
            item = replace(
                item,
                cost_note=(
                    "Gera chamadas adicionais de IA pela seleção principal da auditoria; em AUTO, "
                    "reutiliza custo, quarentena, circuit breaker e fallback do core."
                ),
                dependency_note=(
                    "Exige item 13 habilitado, URL única e IA principal apta (provider explícito ou AUTO). "
                    "Não existe provider/model/reasoning exclusivo desta feature."
                ),
            )
        modules.append(item)
    profiles.MODULES = tuple(modules)
    profiles.MODULE_BY_ID = {item.id: item for item in profiles.MODULES}

    class CanonicalProfileSessions(dict):
        def __setitem__(self, key, value):
            if (
                value is not None
                and "deep-analysis" in tuple(getattr(value, "modules", ()) or ())
                and getattr(value, "ai_mode", profiles.AI_OFF) == profiles.AI_OFF
            ):
                value.ai_mode = profiles.AI_IF_AVAILABLE
            super().__setitem__(key, value)

    if not isinstance(profiles._SESSIONS, CanonicalProfileSessions):
        profiles._SESSIONS = CanonicalProfileSessions(profiles._SESSIONS)

    original_effective = profiles.effective_profile
    if not getattr(original_effective, "_rasai_primary_ai_deep_profile", False):
        @contextmanager
        def effective_profile(
            state: Any,
            session: Any | None = None,
        ) -> Iterator[None]:
            current = session or profiles.active_profile(state)
            if current is None or "deep-analysis" not in tuple(current.modules):
                with original_effective(state, current):
                    yield
                return
            previous_mode = current.ai_mode
            if "ai" not in current.manual_overrides and previous_mode == profiles.AI_OFF:
                current.ai_mode = profiles.AI_IF_AVAILABLE
            try:
                with original_effective(state, current):
                    yield
            finally:
                current.ai_mode = previous_mode

        effective_profile._rasai_primary_ai_deep_profile = True
        effective_profile._rasai_original = original_effective
        profiles.effective_profile = effective_profile

    original_dependency = profiles.dependency_status
    if not getattr(original_dependency, "_rasai_primary_ai_deep_profile", False):
        def dependency_status(state: Any, session: Any | None = None):
            ready, base_blockers, advisories = original_dependency(state, session)
            current = session or profiles.active_profile(state)
            if current is None or "deep-analysis" not in tuple(current.modules):
                return ready, base_blockers, advisories
            blockers = list(base_blockers)
            if bool(getattr(state, "improvement_enabled", False)):
                with profiles.effective_profile(state, current):
                    selection = str(getattr(state, "ai_provider", "none") or "none").casefold()
                    from rasai.console_config import provider_capabilities
                    capabilities = provider_capabilities(
                        blocks=getattr(state, "runtime_blocks", {})
                    )
                    capability = capabilities.get(selection)
                    if selection == "none" or capability is None or not capability.available:
                        reason = capability.reason if capability is not None else "nenhum provider APTO"
                        message = (
                            "Análise profunda usa a IA principal: configure provider explícito ou AUTO "
                            f"com ao menos um provider APTO ({reason})"
                        )
                        if message not in blockers:
                            blockers.append(message)
            return not blockers, tuple(blockers), advisories

        dependency_status._rasai_primary_ai_deep_profile = True
        dependency_status._rasai_original = original_dependency
        profiles.dependency_status = dependency_status

    def choose_ai_mode(state: Any) -> str | None:
        print("\nIA DA EXECUÇÃO")
        print("1. Não usar IA opcional nos módulos que não a exigem")
        print("2. Usar a IA principal se houver provider APTO")
        print(
            "   Regra: se o perfil incluir Análise profunda, ela usa esta mesma IA principal e "
            "não pode ter provider/model/reasoning paralelo."
        )
        print("V. Voltar")
        raw = input("Escolha: ").strip().upper()
        if raw == "1":
            return profiles.AI_OFF
        if raw == "2":
            return profiles.AI_IF_AVAILABLE
        if raw == "V":
            return None
        state.error = "opção de IA do perfil inválida"
        return None

    profiles._choose_ai_mode = choose_ai_mode

    def enhanced_dependency_status(
        state: Any,
        session: Any | None = None,
    ):
        assert readiness._ORIGINAL_DEPENDENCY_STATUS is not None
        current = session or profiles.active_profile(state)
        ready, base_blockers, base_advisories = readiness._ORIGINAL_DEPENDENCY_STATUS(
            state, current
        )
        if current is None:
            return ready, base_blockers, base_advisories

        blockers = list(base_blockers)
        advisories = list(base_advisories)

        if "search-intelligence" in current.modules and tuple(
            getattr(state, "search_queries", ()) or ()
        ):
            try:
                readiness._configured_search(state)
            except (TypeError, ValueError) as exc:
                readiness._append_unique(blockers, f"Search Intelligence: {exc}")

        if "deep-analysis" in current.modules and bool(
            getattr(state, "improvement_enabled", False)
        ):
            with profiles.effective_profile(state, current):
                deep_ready, reason = _single_url_ready(state)
            if not deep_ready:
                readiness._append_unique(blockers, f"Análise profunda: {reason}")

        gsc_blockers, gsc_advisories = readiness._gsc_dependency_status(state, current)
        for item in gsc_blockers:
            readiness._append_unique(blockers, item)
        for item in gsc_advisories:
            readiness._append_unique(advisories, item)

        return not blockers, tuple(blockers), tuple(advisories)

    readiness._enhanced_dependency_status = enhanced_dependency_status


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
    _install_execution_profile_contract()
    _install_improvement_report_contract()
    _materialize_patched_saas_contract()
    _INSTALLED = True
