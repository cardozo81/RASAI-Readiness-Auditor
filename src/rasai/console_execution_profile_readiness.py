"""Readiness-first UX for interactive-console execution profiles.

Every preset remains visible, but mandatory dependencies are checked before the profile
can become active. Google Search Console receives an explicit session policy because a
configured GSC property is private account context, not a generic public-domain source.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import replace
import os
from typing import Any, Iterator

from rasai import console_execution_profiles as profiles
from rasai.console_confirmation_contract import confirm_continue
from rasai.console_search_intelligence import _configured_search
from rasai.gsc_scope import (
    GSC_ENABLED_ENV,
    GSC_SITE_URL_ENV,
    GSC_TOKEN_ENV,
    MODE_AUTO,
    MODE_DISABLED,
    MODE_REQUIRED,
    STATE_COMPATIBLE,
    STATE_DISABLED,
    STATE_NOT_CONFIGURED,
    STATE_PROPERTY_URL_MISMATCH,
    assess_gsc_target,
)
from rasai.improvement_intelligence_console import _single_url_ready

_INSTALLED = False
_ORIGINAL_DEPENDENCY_STATUS = None
_ORIGINAL_EFFECTIVE_PROFILE = None
_ORIGINAL_PROFILE_SUMMARY = None
_ORIGINAL_CLEAR_PROFILE = None

GSC_PROFILE_IF_COMPATIBLE = "if-compatible"
GSC_PROFILE_REQUIRED = "required"
GSC_PROFILE_DISABLED = "disabled"
GSC_PROFILE_INHERIT = "inherit"
_GSC_PROFILE_POLICIES = {
    GSC_PROFILE_IF_COMPATIBLE,
    GSC_PROFILE_REQUIRED,
    GSC_PROFILE_DISABLED,
    GSC_PROFILE_INHERIT,
}
_GSC_POLICY_BY_SESSION: dict[int, str] = {}


def _ensure_complete_maximum() -> None:
    if any(item.id == "complete-maximum" for item in profiles.PROFILES):
        return
    maximum = profiles.ExecutionProfile(
        "complete-maximum",
        "Completo máximo",
        (
            "Combina todos os módulos disponíveis: SEO, GEO, Performance, Acessibilidade, "
            "Web Quality, Search Intelligence, Experiência sintética e Análise profunda. "
            "Dependências de custo/carga permanecem obrigatoriamente explícitas."
        ),
        tuple(item.id for item in profiles.MODULES),
    )
    profiles.PROFILES = (*profiles.PROFILES, maximum)
    profiles._PROFILE_BY_ID = {item.id: item for item in profiles.PROFILES}


def _append_unique(items: list[str], value: str) -> None:
    if value not in items:
        items.append(value)


def gsc_profile_policy(session: profiles.SessionProfile | None) -> str:
    if session is None:
        return GSC_PROFILE_INHERIT
    return _GSC_POLICY_BY_SESSION.get(id(session), GSC_PROFILE_INHERIT)


def set_gsc_profile_policy(session: profiles.SessionProfile, policy: str) -> None:
    if policy not in _GSC_PROFILE_POLICIES:
        raise ValueError(f"política GSC de perfil inválida: {policy}")
    _GSC_POLICY_BY_SESSION[id(session)] = policy


def _scope_mode_for_policy(policy: str) -> str | None:
    if policy == GSC_PROFILE_IF_COMPATIBLE:
        return MODE_AUTO
    if policy == GSC_PROFILE_REQUIRED:
        return MODE_REQUIRED
    if policy == GSC_PROFILE_DISABLED:
        return MODE_DISABLED
    return None


def _gsc_dependency_status(state: Any, current: profiles.SessionProfile) -> tuple[tuple[str, ...], tuple[str, ...]]:
    target = str(getattr(state, "target", "") or "").strip()
    if not target:
        return (), ()
    policy = gsc_profile_policy(current)
    assessment = assess_gsc_target(
        target,
        os.environ,
        mode_override=_scope_mode_for_policy(policy),
    )
    blockers: list[str] = []
    advisories: list[str] = []
    if assessment.blocking:
        advisories.append(
            "Google Search Console: "
            + assessment.message
            + " A auditoria continuará; como GSC é requisito desta execução, o fechamento diagnóstico ficará pendente até reprocessamento."
        )
        return (), tuple(advisories)

    if assessment.state == STATE_PROPERTY_URL_MISMATCH:
        advisories.append(f"GSC: {assessment.message}")
    elif assessment.state == STATE_NOT_CONFIGURED:
        if policy == GSC_PROFILE_IF_COMPATIBLE:
            advisories.append("GSC se compatível: token/property incompletos; GSC não será requisito desta execução")
    elif assessment.state == STATE_DISABLED:
        if policy == GSC_PROFILE_DISABLED:
            advisories.append("GSC: desabilitado somente para esta execução do perfil")
    elif assessment.state == STATE_COMPATIBLE:
        if policy == GSC_PROFILE_REQUIRED or assessment.mode == MODE_REQUIRED:
            advisories.append(
                "GSC obrigatório: property cobre a URL. A validade do OAuth e a permissão da conta sobre a property "
                "só são confirmadas pelo Google; falha nessa etapa mantém o AUD parcial/não final."
            )
        elif policy == GSC_PROFILE_IF_COMPATIBLE:
            advisories.append(
                "GSC se compatível: property cobre a URL; a execução tentará GSC somente com a configuração atual, "
                "sem transformar incompatibilidade de domínio em requisito de conclusão."
            )
    return tuple(blockers), tuple(advisories)


def _enhanced_dependency_status(
    state: Any,
    session: profiles.SessionProfile | None = None,
) -> tuple[bool, tuple[str, ...], tuple[str, ...]]:
    assert _ORIGINAL_DEPENDENCY_STATUS is not None
    current = session or profiles.active_profile(state)
    ready, base_blockers, base_advisories = _ORIGINAL_DEPENDENCY_STATUS(state, current)
    if current is None:
        return ready, base_blockers, base_advisories

    blockers = list(base_blockers)
    advisories = list(base_advisories)

    # Terms alone are not enough for Search Intelligence. Surface provider/mode/key/limit
    # problems before profile selection instead of waiting for the final runtime preflight.
    if "search-intelligence" in current.modules and tuple(getattr(state, "search_queries", ()) or ()):
        try:
            _configured_search(state)
        except (TypeError, ValueError) as exc:
            _append_unique(blockers, f"Search Intelligence: {exc}")

    # Improvement Intelligence may be necessary for diagnostic closure, but provider
    # readiness is not a prerequisite to start/materialize the deterministic audit.
    if "deep-analysis" in current.modules and bool(getattr(state, "improvement_enabled", False)):
        deep_ready, reason = _single_url_ready(state)
        if not deep_ready:
            _append_unique(blockers, f"Análise profunda: {reason}")
        elif any(
            marker in str(reason or "").casefold()
            for marker in ("pendente", "indispon", "não configur")
        ):
            _append_unique(advisories, f"Análise profunda: {reason}")

    gsc_blockers, gsc_advisories = _gsc_dependency_status(state, current)
    for item in gsc_blockers:
        _append_unique(blockers, item)
    for item in gsc_advisories:
        _append_unique(advisories, item)

    return not blockers, tuple(blockers), tuple(advisories)


def _candidate(
    state: Any,
    definition: profiles.ExecutionProfile,
    *,
    ai_mode: str = profiles.AI_OFF,
) -> profiles.SessionProfile:
    candidate = profiles.SessionProfile(
        definition.id,
        definition.label,
        definition.modules,
        ai_mode,
        profiles._baseline(state),
    )
    # Presets are URL-scoped and therefore default to the safe GSC behavior requested
    # for the console: use GSC only when the configured property structurally covers
    # the audited URL. The operator can still make GSC mandatory explicitly.
    set_gsc_profile_policy(candidate, GSC_PROFILE_IF_COMPATIBLE)
    return candidate


def profile_status(state: Any, profile_id: str) -> tuple[bool, tuple[str, ...], tuple[str, ...]]:
    """Return catalog readiness for one named preset without selecting it."""
    _ensure_complete_maximum()
    definition = profiles._PROFILE_BY_ID.get(profile_id)
    if definition is None:
        raise ValueError(f"perfil desconhecido: {profile_id}")
    candidate = _candidate(state, definition)
    return profiles.dependency_status(state, candidate)


def _print_blocked(label: str, blockers: tuple[str, ...]) -> None:
    from rasai.console_ui import YELLOW, paint

    print(paint(f"\n{label} [CONFIGURAR]", YELLOW, bold=True))
    print("Este perfil permanece visível para orientar a parametrização, mas ainda não pode ser selecionado.")
    print("Pendências obrigatórias:")
    for blocker in blockers:
        print(paint(f"- {blocker}", YELLOW))
    print("Configure os itens indicados no menu principal e retorne a F. Perfil da execução.")


def _choose_gsc_policy(state: Any, candidate: profiles.SessionProfile) -> bool:
    from rasai.console_ui import CYAN, YELLOW, paint

    target = str(getattr(state, "target", "") or "").strip()
    print("\nGOOGLE SEARCH CONSOLE NESTA EXECUÇÃO")
    print("1. Usar somente se a property GSC cobrir a URL auditada (recomendado)")
    print("2. Exigir GSC para considerar a auditoria completa/final")
    print("3. Não usar GSC nesta execução")
    print("4. Herdar exatamente a política global RASAI_GSC_ENABLED")
    print("V. Voltar")
    print(paint("O OAuth token não pertence a um domínio; ele representa a conta Google autenticada.", CYAN))
    print(paint("A conta ainda precisa ter acesso à property configurada; isso só pode ser confirmado pela API do Google.", CYAN))
    if target:
        print(f"URL auditada: {target}")
    raw = input("Escolha: ").strip().upper()
    mapping = {
        "1": GSC_PROFILE_IF_COMPATIBLE,
        "2": GSC_PROFILE_REQUIRED,
        "3": GSC_PROFILE_DISABLED,
        "4": GSC_PROFILE_INHERIT,
    }
    if raw == "V":
        return False
    policy = mapping.get(raw)
    if policy is None:
        state.error = "política GSC do perfil inválida"
        return False
    set_gsc_profile_policy(candidate, policy)
    ready, blockers, advisories = profiles.dependency_status(state, candidate)
    for item in advisories:
        if item.startswith("GSC"):
            print(paint(f"INFO: {item}", CYAN))
    if not ready and any("Google Search Console" in item for item in blockers):
        print(paint("A política GSC escolhida cria um requisito impossível com a configuração atual.", YELLOW, bold=True))
    return True


def _gsc_policy_label(policy: str) -> str:
    return {
        GSC_PROFILE_IF_COMPATIBLE: "SOMENTE SE COMPATÍVEL",
        GSC_PROFILE_REQUIRED: "OBRIGATÓRIO",
        GSC_PROFILE_DISABLED: "DESABILITADO",
        GSC_PROFILE_INHERIT: "HERDAR GLOBAL",
    }.get(policy, policy.upper())


def _print_gsc_policy_detail(state: Any, candidate: profiles.SessionProfile) -> None:
    from rasai.console_ui import CYAN, paint

    policy = gsc_profile_policy(candidate)
    print("\nGOOGLE SEARCH CONSOLE")
    print(f"- Política da sessão: {_gsc_policy_label(policy)}")
    _, blockers, advisories = profiles.dependency_status(state, candidate)
    for item in blockers:
        if "Google Search Console" in item:
            print(f"- {item}")
    for item in advisories:
        if item.startswith("GSC"):
            print(paint(f"- {item}", CYAN))


def _configure_profile_guided(state: Any) -> None:
    from rasai.console_ui import GREEN, YELLOW, paint

    if str(getattr(state, "input_mode", "")).casefold() != "url" or not str(getattr(state, "target", "")).strip():
        state.error = "Perfis de execução ficam disponíveis somente após informar uma URL única no item 1"
        return

    while True:
        print("\nPERFIS DE EXECUÇÃO - SOMENTE ESTA SESSÃO / URL ÚNICA\n")
        print("Todos os perfis permanecem visíveis. [CONFIGURAR] indica dependência obrigatória ainda ausente.")
        print("Perfis [CONFIGURAR] não podem ser aplicados até que as pendências exibidas sejam resolvidas.")
        print("Por padrão, o perfil usa GSC somente quando a property configurada cobre a URL auditada.")
        print("O perfil não altera defaults, INI, Windows/User, Windows/Machine ou credenciais.\n")

        for index, definition in enumerate(profiles.PROFILES, 1):
            candidate = _candidate(state, definition)
            ready, blockers, _ = profiles.dependency_status(state, candidate)
            marker = paint("APTO", GREEN, bold=True) if ready else paint("CONFIGURAR", YELLOW, bold=True)
            module_costs = " | ".join(
                dict.fromkeys(profiles.MODULE_BY_ID[item].cost_note for item in definition.modules)
            )
            print(f" {index:2d}. [{marker}] {definition.label}")
            print(f"     Envolve: {definition.description}")
            print("     GSC   : somente se property cobrir a URL; pode ser alterado ao selecionar")
            print(f"     Custo : {module_costs}")
            for blocker in blockers:
                print(paint(f"     Falta : {blocker}", YELLOW))

        print("\n C. Compor perfil personalizado")
        print(" N. Remover perfil da sessão")
        print(" V. Voltar")
        raw = input("Escolha: ").strip().upper()

        if raw == "V":
            return
        if raw == "N":
            profiles.clear_profile(state)
            state.error = ""
            state.operation = "LOCAL:EXECUTION_PROFILE_NONE"
            return

        if raw == "C":
            modules = profiles._custom_modules(state)
            if modules is None:
                continue
            candidate = profiles.SessionProfile(
                "custom",
                "Personalizado",
                modules,
                profiles.AI_OFF,
                profiles._baseline(state),
            )
            set_gsc_profile_policy(candidate, GSC_PROFILE_IF_COMPATIBLE)
            ready, blockers, _ = profiles.dependency_status(state, candidate)
            if not ready:
                _print_blocked(candidate.label, blockers)
                state.error = "Perfil personalizado ainda requer configuração"
                continue
            ai_mode = profiles._choose_ai_mode(state)
            if ai_mode is None:
                continue
            candidate.ai_mode = ai_mode
        else:
            try:
                definition = profiles.PROFILES[int(raw) - 1]
            except (ValueError, IndexError):
                state.error = "perfil inválido"
                continue

            preview = _candidate(state, definition)
            ready, blockers, _ = profiles.dependency_status(state, preview)
            if not ready:
                _print_blocked(definition.label, blockers)
                state.error = f"{definition.label}: configure as dependências exibidas antes de selecionar"
                continue

            ai_mode = profiles._choose_ai_mode(state)
            if ai_mode is None:
                continue
            candidate = _candidate(state, definition, ai_mode=ai_mode)

        if not _choose_gsc_policy(state, candidate):
            continue

        # GSC=required can turn a previously safe candidate into a predictable partial
        # execution. Recheck before allowing the profile into the active session.
        ready, blockers, _ = profiles.dependency_status(state, candidate)
        if not ready:
            _print_blocked(candidate.label, blockers)
            state.error = f"{candidate.label}: configure as dependências exibidas antes de selecionar"
            continue

        profiles._render_profile_detail(state, candidate)
        _print_gsc_policy_detail(state, candidate)
        if not confirm_continue(
            "Confirmar e aplicar perfil à sessão",
            back_label="Voltar sem alterar",
        ):
            continue

        # Defensive recheck after all session policy choices.
        ready, blockers, _ = profiles.dependency_status(state, candidate)
        if not ready:
            _print_blocked(candidate.label, blockers)
            state.error = f"{candidate.label}: dependência alterada; perfil não aplicado"
            continue

        profiles._SESSIONS[id(state)] = candidate
        state.error = ""
        state.operation = "LOCAL:EXECUTION_PROFILE_SELECTED"
        return


def _install_profile_gsc_overlay() -> None:
    global _ORIGINAL_EFFECTIVE_PROFILE, _ORIGINAL_PROFILE_SUMMARY, _ORIGINAL_CLEAR_PROFILE
    if _ORIGINAL_EFFECTIVE_PROFILE is not None:
        return
    _ORIGINAL_EFFECTIVE_PROFILE = profiles.effective_profile
    _ORIGINAL_PROFILE_SUMMARY = profiles._profile_summary
    _ORIGINAL_CLEAR_PROFILE = profiles.clear_profile

    @contextmanager
    def effective_profile_with_gsc(
        state: Any,
        session: profiles.SessionProfile | None = None,
    ) -> Iterator[None]:
        current = session or profiles.active_profile(state)
        policy = gsc_profile_policy(current)
        existed = GSC_ENABLED_ENV in os.environ
        previous = os.environ.get(GSC_ENABLED_ENV)
        try:
            if policy == GSC_PROFILE_IF_COMPATIBLE:
                os.environ.pop(GSC_ENABLED_ENV, None)
            elif policy == GSC_PROFILE_REQUIRED:
                os.environ[GSC_ENABLED_ENV] = "true"
            elif policy == GSC_PROFILE_DISABLED:
                os.environ[GSC_ENABLED_ENV] = "false"
            with _ORIGINAL_EFFECTIVE_PROFILE(state, current):
                yield
        finally:
            if existed and previous is not None:
                os.environ[GSC_ENABLED_ENV] = previous
            elif not existed:
                os.environ.pop(GSC_ENABLED_ENV, None)

    def profile_summary_with_gsc(state: Any) -> None:
        _ORIGINAL_PROFILE_SUMMARY(state)
        current = profiles.active_profile(state)
        if current is None:
            return
        print(f"   Google Search Console  : {_gsc_policy_label(gsc_profile_policy(current))}")

    def clear_profile_with_gsc(state: Any) -> None:
        current = profiles.active_profile(state)
        if current is not None:
            _GSC_POLICY_BY_SESSION.pop(id(current), None)
        _ORIGINAL_CLEAR_PROFILE(state)

    profiles.effective_profile = effective_profile_with_gsc
    profiles._profile_summary = profile_summary_with_gsc
    profiles.clear_profile = clear_profile_with_gsc


def _install_gsc_environment_guidance() -> None:
    """Make domain/property consequences explicit in the existing configuration UI."""
    from rasai import console_environment as base
    from rasai import console_provider_environment as facade

    specs = list(base.SPECS)
    changed = False
    for index, spec in enumerate(specs):
        if spec.name == GSC_ENABLED_ENV:
            specs[index] = replace(
                spec,
                purpose=(
                    "Política do Google Search Console. Sem override = automático por requisitos; true = GSC obrigatório "
                    "para a conclusão; false = desabilitado."
                ),
                required_when=(
                    "Com true, exige OAuth token válido e property que cubra a URL auditada. Se a property não cobrir "
                    "o alvo, o AUD não poderá ficar completo/final."
                ),
                notes=(
                    "Em modo automático, uma property de outro domínio é tratada como não aplicável à URL e não vira "
                    "requisito de conclusão. Em true, o conflito PROPERTY_URL_MISMATCH é configuração bloqueante/reprocessável."
                ),
            )
            changed = True
        elif spec.name == GSC_SITE_URL_ENV:
            specs[index] = replace(
                spec,
                purpose=(
                    "Property real do Google Search Console usada por Search Analytics, Sitemaps e URL Inspection; "
                    "não é simplesmente o domínio que o RASAi está auditando."
                ),
                required_when=(
                    "Obrigatória quando GSC for usado. A conta representada pelo OAuth token precisa ter acesso a esta "
                    "property e a property precisa cobrir a URL auditada quando GSC for obrigatório."
                ),
                notes=(
                    "Aceita sc-domain:<domínio> ou URL-prefix HTTP(S). sc-domain cobre o domínio e subdomínios; URL-prefix "
                    "é específica de protocolo/host/path. Configurar property de outro site não concede acesso aos dados "
                    "do alvo auditado."
                ),
            )
            changed = True
        elif spec.name == GSC_TOKEN_ENV:
            specs[index] = replace(
                spec,
                purpose=(
                    "OAuth 2.0 access token temporário do Google Search Console. O token representa a conta Google "
                    "autenticada; não pertence a um domínio específico."
                ),
                required_when=(
                    "Necessário quando GSC for usado. A conta autenticada deve ter acesso à property configurada em "
                    "RASAI_GOOGLE_SEARCH_CONSOLE_SITE_URL."
                ),
                notes=(
                    "Access tokens expiram/podem ser revogados. Presença [SET] não comprova validade nem acesso à property; "
                    "a confirmação definitiva ocorre quando a API do Google aceita a chamada."
                ),
            )
            changed = True
    if not changed:
        return
    base.SPECS = tuple(specs)
    base.SPEC_BY_NAME = {spec.name: spec for spec in specs}
    facade.CATEGORIES = base.CATEGORIES
    facade.refresh_specs()


def install() -> None:
    """Install readiness-first catalog behavior before console_execution_profiles.install."""
    global _INSTALLED, _ORIGINAL_DEPENDENCY_STATUS
    if _INSTALLED:
        return

    _ensure_complete_maximum()
    _ORIGINAL_DEPENDENCY_STATUS = profiles.dependency_status
    profiles.dependency_status = _enhanced_dependency_status
    profiles.configure_profile = _configure_profile_guided
    _install_profile_gsc_overlay()
    _install_gsc_environment_guidance()
    _INSTALLED = True
