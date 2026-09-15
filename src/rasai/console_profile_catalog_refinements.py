"""Final profile-catalog UX/readiness reconciliation.

Profiles remain session-only overlays.  The refinement aligns them with the current
single-primary-AI architecture, canonical preparation item numbers and the documented
meaning of Deep Analysis as a module that a profile may request directly.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import replace
from types import ModuleType
from typing import Any, Iterator

from rasai.console_ui import CYAN, DIM, GREEN, YELLOW, paint

_INSTALLED = False


def _replace_module_metadata() -> None:
    from rasai import console_execution_profiles as profiles

    updated = []
    for item in profiles.MODULES:
        if item.id == "search-intelligence":
            item = replace(
                item,
                dependency_note=(
                    "Exige Termos SERP no item 13, provider/mode SERP aptos e credencial quando o modo for live. "
                    "O perfil nunca inventa termos."
                ),
            )
        elif item.id == "experience":
            item = replace(
                item,
                dependency_note=(
                    "Exige Synthetic Apdex parametrizado no item 12; Experience Apdex, quando usado, "
                    "também precisa estar válido. O perfil não inventa threshold/amostras/carga."
                ),
            )
        elif item.id == "deep-analysis":
            item = replace(
                item,
                description=(
                    "Inclui Improvement Intelligence evidence-bound para a URL usando exclusivamente "
                    "a IA principal/orquestrador canônico."
                ),
                cost_note=(
                    "Gera chamadas adicionais de IA pelo mesmo orquestrador principal; custo depende "
                    "do provider efetivo, modelo, reasoning e volume de evidências."
                ),
                dependency_note=(
                    "Exige URL única e IA principal/AUTO apta no item 6. O próprio perfil solicita "
                    "Análise profunda; não existe IA especializada separada."
                ),
            )
        updated.append(item)
    profiles.MODULES = tuple(updated)
    profiles.MODULE_BY_ID = {item.id: item for item in profiles.MODULES}

    refined_profiles = []
    for definition in profiles.PROFILES:
        if definition.id == "complete-safe":
            definition = replace(
                definition,
                description=(
                    "Cobertura ampla de SEO, GEO, Performance, Acessibilidade e Web Quality sem ligar "
                    "SERP, carga sintética, Análise profunda ou integrações externas opt-in."
                ),
            )
        elif definition.id == "complete-maximum":
            definition = replace(
                definition,
                description=(
                    "Todos os módulos de workload do catálogo. Exige inputs não inventáveis (SERP/Apdex) "
                    "e IA principal apta; integrações externas opt-in continuam sob política própria."
                ),
            )
        refined_profiles.append(definition)
    profiles.PROFILES = tuple(refined_profiles)
    profiles._PROFILE_BY_ID = {item.id: item for item in profiles.PROFILES}


def _normalize_blocker(text: str) -> str:
    raw = str(text)
    lowered = raw.casefold()
    if "search intelligence selecionado" in lowered and "termos" in lowered:
        return "Search Intelligence / SERP: configure Termos SERP no item 13."
    if "experiência sintética selecionada" in lowered:
        return (
            "Experiência sintética: configure Synthetic Apdex no item 12 "
            "(e Experience Apdex, se fizer parte da medição desejada)."
        )
    if "análise profunda selecionada" in lowered and "item 8" in lowered:
        return ""
    return raw


def _project_deep_readiness(state: Any, current: Any) -> tuple[bool, str]:
    from rasai import console_execution_profiles as profiles
    from rasai import improvement_intelligence_console as improvement

    previous_enabled = bool(getattr(state, "improvement_enabled", False))
    previous_provider = str(getattr(state, "ai_provider", "none"))
    previous_model = getattr(state, "ai_model", None)
    previous_reasoning = getattr(state, "ai_reasoning", None)
    try:
        state.improvement_enabled = True
        if current.ai_mode == profiles.AI_IF_AVAILABLE and "ai" not in current.manual_overrides:
            provider = profiles._effective_ai_provider(state)
            state.ai_provider = provider
            if provider in {"none", "auto"}:
                state.ai_model = None
                state.ai_reasoning = None
        return improvement._single_url_ready(state)
    finally:
        state.improvement_enabled = previous_enabled
        state.ai_provider = previous_provider
        state.ai_model = previous_model
        state.ai_reasoning = previous_reasoning


def _impact_summary(definition: Any) -> str:
    modules = set(definition.modules)
    impacts: list[str] = []
    if modules & {"seo", "geo", "performance", "accessibility", "web-quality"}:
        impacts.append("PageSpeed/Lighthouse/CrUX conforme configuração")
    if "search-intelligence" in modules:
        impacts.append("SERP pode consumir quota/créditos")
    if "experience" in modules:
        impacts.append("gera navegações/carga sintética no alvo")
    if "deep-analysis" in modules:
        impacts.append("gera chamadas adicionais de IA")
    return "; ".join(impacts) or "sem workload externo adicional específico"


def _scope_summary(definition: Any) -> str:
    from rasai import console_execution_profiles as profiles

    labels = [profiles.MODULE_BY_ID[module_id].label for module_id in definition.modules]
    return ", ".join(labels)


def _choose_optional_ai(state: Any) -> str | None:
    from rasai import console_execution_profiles as profiles

    print("\nIA PRINCIPAL DO PERFIL")
    print("1. Não adicionar uso opcional de IA neste perfil")
    print("2. Usar a IA principal/AUTO se houver provider APTO")
    print("V. Voltar")
    print(
        paint(
            "Perfis com Análise profunda não exibem esta escolha: IA principal é requisito funcional desse módulo.",
            DIM,
        )
    )
    raw = input("Escolha: ").strip().upper()
    if raw == "1":
        return profiles.AI_OFF
    if raw == "2":
        return profiles.AI_IF_AVAILABLE
    if raw == "V":
        return None
    state.error = "opção de IA do perfil inválida"
    return None


def _configure_profile(state: Any) -> None:
    from rasai import console_execution_profile_readiness as readiness
    from rasai import console_execution_profiles as profiles

    if str(getattr(state, "input_mode", "")).casefold() != "url" or not str(getattr(state, "target", "")).strip():
        state.error = "Perfis de execução ficam disponíveis somente após informar uma URL única no item 1"
        return

    while True:
        print("\nPERFIS DE EXECUÇÃO - PRÓXIMA EXECUÇÃO / SOMENTE ESTA SESSÃO\n")
        print("Status considera dependências reais. O perfil não grava INI, SO ou credenciais.")
        print("GSC é escolhido depois do perfil e continua independente de SERP.")
        print(
            paint(
                "Referências da preparação: item 6=IA principal | 8=Análise profunda | "
                "12=Synthetic Apdex | 13=Termos SERP.",
                DIM,
            )
        )

        for index, definition in enumerate(profiles.PROFILES, 1):
            candidate = readiness._candidate(state, definition)
            ready, blockers, _ = profiles.dependency_status(state, candidate)
            marker = paint("APTO", GREEN, bold=True) if ready else paint("CONFIGURAR", YELLOW, bold=True)
            print(f"\n {index:2d}. [{marker}] {definition.label}")
            print(f"     Escopo : {_scope_summary(definition)}")
            print(f"     Impacto: {_impact_summary(definition)}")
            if "deep-analysis" in definition.modules:
                print("     IA     : obrigatória via IA principal/AUTO (item 6)")
            else:
                print("     IA     : opcional; definida após selecionar o perfil")
            for blocker in blockers:
                print(paint(f"     Falta  : {blocker}", YELLOW))

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
                profiles.AI_IF_AVAILABLE if "deep-analysis" in modules else profiles.AI_OFF,
                profiles._baseline(state),
            )
            readiness.set_gsc_profile_policy(candidate, readiness.GSC_PROFILE_IF_COMPATIBLE)
        else:
            try:
                definition = profiles.PROFILES[int(raw) - 1]
            except (ValueError, IndexError):
                state.error = "perfil inválido"
                continue
            candidate = readiness._candidate(state, definition)

        ready, blockers, _ = profiles.dependency_status(state, candidate)
        if not ready:
            readiness._print_blocked(candidate.label, blockers)
            state.error = f"{candidate.label}: configure as dependências exibidas antes de selecionar"
            continue

        if "deep-analysis" in candidate.modules:
            candidate.ai_mode = profiles.AI_IF_AVAILABLE
            print(
                paint(
                    "\nIA principal: OBRIGATÓRIA para Análise profunda; será usada a seleção atual/AUTO do item 6.",
                    CYAN,
                    bold=True,
                )
            )
        else:
            ai_mode = _choose_optional_ai(state)
            if ai_mode is None:
                continue
            candidate.ai_mode = ai_mode

        if not readiness._choose_gsc_policy(state, candidate):
            continue

        ready, blockers, _ = profiles.dependency_status(state, candidate)
        if not ready:
            readiness._print_blocked(candidate.label, blockers)
            state.error = f"{candidate.label}: configure as dependências exibidas antes de selecionar"
            continue

        profiles._render_profile_detail(state, candidate)
        readiness._print_gsc_policy_detail(state, candidate)
        print("\nA. Aplicar à sessão")
        print("V. Voltar sem alterar")
        if input("Escolha: ").strip().upper() != "A":
            continue

        ready, blockers, _ = profiles.dependency_status(state, candidate)
        if not ready:
            readiness._print_blocked(candidate.label, blockers)
            state.error = f"{candidate.label}: dependência alterada; perfil não aplicado"
            continue

        profiles._SESSIONS[id(state)] = candidate
        state.error = ""
        state.operation = "LOCAL:EXECUTION_PROFILE_SELECTED"
        return


def install(console_module: ModuleType) -> None:
    """Install after preparation numbering and readiness overlays are already composed."""
    global _INSTALLED
    if _INSTALLED or getattr(console_module, "_rasai_profile_catalog_refined", False):
        return

    from rasai import console_execution_profile_readiness as readiness
    from rasai import console_execution_profiles as profiles

    _replace_module_metadata()

    original_candidate = readiness._candidate
    original_dependency_status = profiles.dependency_status
    original_effective_profile = profiles.effective_profile
    original_cost_lines = profiles._cost_lines

    def candidate(
        state: Any,
        definition: Any,
        *,
        ai_mode: str = profiles.AI_OFF,
    ) -> Any:
        if "deep-analysis" in definition.modules and ai_mode == profiles.AI_OFF:
            ai_mode = profiles.AI_IF_AVAILABLE
        return original_candidate(state, definition, ai_mode=ai_mode)

    def dependency_status(state: Any, session: Any = None):
        current = session or profiles.active_profile(state)
        ready, blockers, advisories = original_dependency_status(state, current)
        normalized = [value for value in (_normalize_blocker(item) for item in blockers) if value]
        if current is not None and "deep-analysis" in current.modules:
            normalized = [
                item for item in normalized
                if not str(item).casefold().startswith("análise profunda:")
            ]
            deep_ready, reason = _project_deep_readiness(state, current)
            if not deep_ready and reason not in normalized:
                normalized.append(reason)
            elif deep_ready:
                advisories = (*advisories, "Análise profunda será habilitada pelo perfil usando a IA principal.")
        return not normalized, tuple(normalized), tuple(dict.fromkeys(advisories))

    @contextmanager
    def effective_profile(state: Any, session: Any = None) -> Iterator[None]:
        current = session or profiles.active_profile(state)
        with original_effective_profile(state, current):
            if current is not None and "deep-analysis" in current.modules and "deep" not in current.manual_overrides:
                state.improvement_enabled = True
            yield

    def cost_lines(state: Any, session: Any) -> tuple[str, ...]:
        lines = list(original_cost_lines(state, session))
        repaired = []
        for line in lines:
            if line.startswith("Análise profunda:"):
                repaired.append(
                    "Análise profunda: chamadas adicionais de IA pelo orquestrador principal; "
                    "custo depende da IA principal/AUTO, modelo e reasoning efetivos do item 6"
                )
            else:
                repaired.append(line)
        return tuple(repaired)

    readiness._candidate = candidate
    profiles.dependency_status = dependency_status
    profiles.effective_profile = effective_profile
    profiles._cost_lines = cost_lines
    profiles._choose_ai_mode = _choose_optional_ai
    profiles.configure_profile = _configure_profile

    console_module._rasai_profile_catalog_refined = True
    _INSTALLED = True
