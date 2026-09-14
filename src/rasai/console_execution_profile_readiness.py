"""Readiness-first UX for interactive-console execution profiles.

This extension keeps every profile visible, but prevents applying a profile whose mandatory
operational dependencies are still missing. It also adds a Completo máximo preset that
combines every execution module without weakening the underlying runtime/preflight gates.
"""
from __future__ import annotations

from typing import Any

from rasai import console_execution_profiles as profiles
from rasai.console_search_intelligence import _configured_search
from rasai.improvement_intelligence_console import _single_url_ready

_INSTALLED = False
_ORIGINAL_DEPENDENCY_STATUS = None


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


def _enhanced_dependency_status(
    state: Any,
    session: profiles.SessionProfile | None = None,
) -> tuple[bool, tuple[str, ...], tuple[str, ...]]:
    assert _ORIGINAL_DEPENDENCY_STATUS is not None
    current = session or profiles.active_profile(state)
    ready, base_blockers, advisories = _ORIGINAL_DEPENDENCY_STATUS(state, current)
    if current is None:
        return ready, base_blockers, advisories

    blockers = list(base_blockers)

    # Terms alone are not enough for Search Intelligence. Surface provider/mode/key/limit
    # problems before profile selection instead of waiting for the final runtime preflight.
    if "search-intelligence" in current.modules and tuple(getattr(state, "search_queries", ()) or ()):
        try:
            _configured_search(state)
        except (TypeError, ValueError) as exc:
            _append_unique(blockers, f"Search Intelligence: {exc}")

    # Improvement Intelligence owns an independent provider/model/reasoning contract.
    # When the operator already enabled item 13, expose any remaining provider/key/model
    # problem directly in the profile catalog.
    if "deep-analysis" in current.modules and bool(getattr(state, "improvement_enabled", False)):
        deep_ready, reason = _single_url_ready(state)
        if not deep_ready:
            _append_unique(blockers, f"Análise profunda: {reason}")

    return not blockers, tuple(blockers), advisories


def _candidate(
    state: Any,
    definition: profiles.ExecutionProfile,
    *,
    ai_mode: str = profiles.AI_OFF,
) -> profiles.SessionProfile:
    return profiles.SessionProfile(
        definition.id,
        definition.label,
        definition.modules,
        ai_mode,
        profiles._baseline(state),
    )


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


def _configure_profile_guided(state: Any) -> None:
    from rasai.console_ui import GREEN, YELLOW, paint

    if str(getattr(state, "input_mode", "")).casefold() != "url" or not str(getattr(state, "target", "")).strip():
        state.error = "Perfis de execução ficam disponíveis somente após informar uma URL única no item 1"
        return

    while True:
        print("\nPERFIS DE EXECUÇÃO - SOMENTE ESTA SESSÃO / URL ÚNICA\n")
        print("Todos os perfis permanecem visíveis. [CONFIGURAR] indica dependência obrigatória ainda ausente.")
        print("Perfis [CONFIGURAR] não podem ser aplicados até que as pendências exibidas sejam resolvidas.")
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

        profiles._render_profile_detail(state, candidate)
        print("\nA. Aplicar à sessão")
        print("V. Voltar sem alterar")
        confirm = input("Escolha: ").strip().upper()
        if confirm != "A":
            continue

        # Defensive recheck after the AI-mode step; dependencies can be externally changed
        # while the menu is open, and a blocked profile must never become silently active.
        ready, blockers, _ = profiles.dependency_status(state, candidate)
        if not ready:
            _print_blocked(candidate.label, blockers)
            state.error = f"{candidate.label}: dependência alterada; perfil não aplicado"
            continue

        profiles._SESSIONS[id(state)] = candidate
        state.error = ""
        state.operation = "LOCAL:EXECUTION_PROFILE_SELECTED"
        return


def install() -> None:
    """Install readiness-first catalog behavior before console_execution_profiles.install."""
    global _INSTALLED, _ORIGINAL_DEPENDENCY_STATUS
    if _INSTALLED:
        return

    _ensure_complete_maximum()
    _ORIGINAL_DEPENDENCY_STATUS = profiles.dependency_status
    profiles.dependency_status = _enhanced_dependency_status
    profiles.configure_profile = _configure_profile_guided
    _INSTALLED = True
