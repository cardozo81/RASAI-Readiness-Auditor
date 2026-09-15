"""Canonical capability-driven execution profiles for the interactive console."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import os
from typing import Any, Iterator

from rasai.execution_capabilities import (
    CAPABILITIES as AUDIT_CAPABILITIES,
    CAPABILITY_BY_ID,
    NON_BLOCKING_PROFILE_CAPABILITIES,
    PROFILE_SELECTABLE,
)

_INSTALLED = False
_CATEGORY_ORDER = ("performance", "accessibility", "best-practices", "seo", "agentic-browsing")


@dataclass(frozen=True, slots=True)
class ProfileUX:
    purpose: str
    result: str
    categories: tuple[str, ...] = ()


UX = {
    "seo": ProfileUX(
        "Diagnosticar descoberta, indexabilidade e sinais técnicos de busca orgânica.",
        "Search Readiness técnico com descoberta/conteúdo e Lighthouse SEO/boas práticas.",
        ("seo", "best-practices"),
    ),
    "geo": ProfileUX(
        "Diagnosticar preparo técnico para descoberta e consumo por agentes/IA.",
        "AI Readiness com conteúdo, sinais agentic e evidências disponíveis de visibilidade.",
        ("seo", "best-practices", "agentic-browsing"),
    ),
    "performance": ProfileUX(
        "Medir desempenho sem ampliar para SERP, Apdex ou análise profunda.",
        "PageSpeed/Lighthouse/CrUX disponíveis com foco em Performance e boas práticas.",
        ("performance", "best-practices"),
    ),
    "accessibility": ProfileUX(
        "Aprofundar acessibilidade com enriquecimento Lighthouse.",
        "Evidências do core mais Lighthouse Accessibility/boas práticas.",
        ("accessibility", "best-practices"),
    ),
    "web-quality": ProfileUX(
        "Obter leitura ampla de qualidade Web sem SERP, carga sintética ou IA obrigatória.",
        "Descoberta, acessibilidade, padrões, conteúdo e Lighthouse de qualidade Web.",
        ("best-practices", "seo", "accessibility"),
    ),
    "seo-geo": ProfileUX(
        "Combinar Search Readiness e AI Readiness.",
        "Visão conjunta de descoberta, conteúdo e sinais para busca/agentes.",
        ("seo", "best-practices", "agentic-browsing"),
    ),
    "seo-geo-performance": ProfileUX(
        "Combinar Search/AI Readiness com performance.",
        "Descoberta, conteúdo, sinais agentic e performance de laboratório/campo.",
        ("performance", "seo", "best-practices", "agentic-browsing"),
    ),
    "search-intelligence": ProfileUX(
        "Observar resultados de busca para termos definidos pelo operador.",
        "SERP/concorrência restrita a termos, região, device e depth configurados.",
    ),
    "apdex-navigation": ProfileUX(
        "Medir navegação real repetida sob perfil sintético controlado.",
        "Amostras e Apdex conforme thresholds, amostras e perfil configurados.",
    ),
    "apdex-experience": ProfileUX(
        "Medir experiência sintética por distribuição de dispositivos.",
        "Navigation + Experience Apdex com distribuição/calibração vigentes.",
    ),
    "deep-analysis": ProfileUX(
        "Obter análise evidence-bound adicional com priorização corretiva.",
        "Recomendações adicionais ligadas às evidências usando a IA principal.",
    ),
    "complete-safe": ProfileUX(
        "Executar cobertura ampla sem workloads que exigem termos, carga sintética ou IA obrigatória.",
        "Descoberta, acessibilidade, performance, padrões, conteúdo e resultados sistêmicos disponíveis.",
        ("performance", "accessibility", "best-practices", "seo", "agentic-browsing"),
    ),
    "complete-maximum": ProfileUX(
        "Executar todas as capacidades selecionáveis corretamente parametrizadas.",
        "Cobertura máxima, incluindo SERP, Apdex e análise profunda.",
        ("performance", "accessibility", "best-practices", "seo", "agentic-browsing"),
    ),
}

CAPS = {
    "seo": ("domain-discovery", "web-performance", "content-suggestions"),
    "geo": ("domain-discovery", "web-performance", "content-suggestions", "ai-visibility"),
    "performance": ("web-performance",),
    "accessibility": ("accessibility", "web-performance"),
    "web-quality": (
        "domain-discovery",
        "accessibility",
        "web-performance",
        "standards",
        "content-suggestions",
        "quality",
    ),
    "seo-geo": ("domain-discovery", "web-performance", "content-suggestions", "ai-visibility"),
    "seo-geo-performance": (
        "domain-discovery",
        "web-performance",
        "content-suggestions",
        "ai-visibility",
    ),
    "search-intelligence": ("search-intelligence",),
    "apdex-navigation": ("apdex-navigation",),
    "apdex-experience": ("apdex-navigation", "apdex-experience"),
    "deep-analysis": ("deep-analysis",),
    "complete-safe": (
        "domain-discovery",
        "accessibility",
        "web-performance",
        "standards",
        "content-suggestions",
        "ai-visibility",
        "observability",
        "quality",
    ),
    "complete-maximum": tuple(item.id for item in AUDIT_CAPABILITIES),
}

LABELS = {
    "seo": "SEO / Search Readiness",
    "geo": "GEO / AI Readiness",
    "performance": "Performance",
    "accessibility": "Acessibilidade",
    "web-quality": "Web Quality",
    "seo-geo": "SEO + GEO",
    "seo-geo-performance": "SEO + GEO + Performance",
    "search-intelligence": "Search Intelligence / SERP",
    "apdex-navigation": "Apdex de navegação",
    "apdex-experience": "Apdex de experiência",
    "deep-analysis": "Análise profunda URL",
    "complete-safe": "Completo seguro",
    "complete-maximum": "Completo máximo",
}


def _categories(session: Any) -> tuple[str, ...]:
    meta = UX.get(str(getattr(session, "profile_id", "")))
    wanted = set(meta.categories if meta else ())
    return tuple(item for item in _CATEGORY_ORDER if item in wanted)


def _manual(session: Any, state: Any, domain: str) -> bool:
    if domain in getattr(session, "manual_overrides", set()):
        return True
    baseline = getattr(session, "baseline", {}) or {}
    if domain == "web":
        return bool(getattr(state, "web_performance", False)) != bool(
            baseline.get("web_performance", False)
        )
    if domain == "categories":
        return str(getattr(state, "lighthouse_categories", "")) != str(
            baseline.get("lighthouse_categories", "")
        )
    return False


@contextmanager
def effective_profile(state: Any, session: Any | None = None) -> Iterator[None]:
    """Project the selected profile as the authoritative execution scope.

    Session values remain available as parameters for capabilities included by the
    profile, but they cannot silently re-enable workloads that the profile explicitly
    excluded. Explicit adjustments made after profile selection still win through
    ``manual_overrides``. The parent console state is restored exactly afterwards.
    """
    from rasai import console_execution_profile_readiness as readiness
    from rasai import console_execution_profiles as profiles

    current = session or profiles.active_profile(state)
    if current is None:
        yield
        return

    fields = (
        "web_performance",
        "lighthouse_categories",
        "ai_provider",
        "ai_model",
        "ai_reasoning",
        "content_remediation",
        "technical_remediation",
        "synthetic_apdex",
        "apdex_experience",
        "search_queries",
        "improvement_enabled",
    )
    saved = {name: getattr(state, name) for name in fields if hasattr(state, name)}
    capabilities = set(tuple(getattr(current, "modules", ()) or ()))
    overrides = set(getattr(current, "manual_overrides", set()) or set())

    policy = readiness.gsc_profile_policy(current)
    gsc_env = readiness.GSC_ENABLED_ENV
    gsc_existed = gsc_env in os.environ
    gsc_previous = os.environ.get(gsc_env)

    try:
        if policy == readiness.GSC_PROFILE_IF_COMPATIBLE:
            os.environ.pop(gsc_env, None)
        elif policy == readiness.GSC_PROFILE_REQUIRED:
            os.environ[gsc_env] = "true"
        elif policy == readiness.GSC_PROFILE_DISABLED:
            os.environ[gsc_env] = "false"

        if not _manual(current, state, "web"):
            state.web_performance = "web-performance" in capabilities

        categories = _categories(current)
        if categories and not _manual(current, state, "categories"):
            state.lighthouse_categories = ",".join(categories)

        if "ai" not in overrides:
            if getattr(current, "ai_mode", profiles.AI_OFF) == profiles.AI_OFF:
                state.ai_provider = "none"
                state.ai_model = None
                state.ai_reasoning = None
            else:
                provider = profiles._effective_ai_provider(state)
                state.ai_provider = provider
                if provider in {"none", "auto"}:
                    state.ai_model = None
                    state.ai_reasoning = None

        if "remediation" not in overrides:
            if "remediation" not in capabilities or str(
                getattr(state, "ai_provider", "none") or "none"
            ).casefold() == "none":
                state.content_remediation = False
                state.technical_remediation = False

        if "search" not in overrides and "search-intelligence" not in capabilities:
            if hasattr(state, "search_queries"):
                state.search_queries = ()

        if "experience" not in overrides:
            if "apdex-navigation" not in capabilities and hasattr(state, "synthetic_apdex"):
                state.synthetic_apdex = False
            if "apdex-experience" not in capabilities and hasattr(state, "apdex_experience"):
                state.apdex_experience = False

        if "deep" not in overrides and hasattr(state, "improvement_enabled"):
            state.improvement_enabled = "deep-analysis" in capabilities

        yield
    finally:
        for name, value in saved.items():
            setattr(state, name, value)
        if gsc_existed and gsc_previous is not None:
            os.environ[gsc_env] = gsc_previous
        elif not gsc_existed:
            os.environ.pop(gsc_env, None)


def _ui_capability(capability_id: str):
    from rasai import console_ui_catalog as ui

    return next((item for item in ui.CAPABILITIES if item.key == capability_id), None)


def dependency_status(state: Any, session: Any | None = None):
    from rasai import console_execution_profile_readiness as readiness
    from rasai import console_execution_profiles as profiles
    from rasai import console_ui_catalog as ui
    from rasai.content_context import configured_content_analysis_context

    current = session or profiles.active_profile(state)
    if current is None:
        return True, (), ()

    blockers: list[str] = []
    advisories: list[str] = []
    if str(getattr(state, "input_mode", "")).casefold() != "url" or not str(
        getattr(state, "target", "")
    ).strip():
        blockers.append("Perfil exige uma URL única explícita.")

    with effective_profile(state, current):
        for capability_id in tuple(getattr(current, "modules", ()) or ()):
            capability = _ui_capability(capability_id)
            if capability is None:
                blockers.append(f"Capacidade desconhecida: {capability_id}")
                continue
            status, detail = ui.capability_status(state, capability)
            if capability_id in NON_BLOCKING_PROFILE_CAPABILITIES:
                if status == "CONFIGURAR":
                    advisories.append(f"{capability.label}: {detail}")
            elif status == "APTO COM LIMITAÇÕES":
                advisories.append(f"{capability.label}: {detail}")
            elif status not in {
                "APTO",
                "INCLUÍDO",
                "AUTOMÁTICO",
                "DERIVADO",
                "PERSONALIZADO",
                "HABILITADO",
            }:
                blockers.append(f"{capability.label}: {detail}")

    if str(getattr(current, "profile_id", "")) in {
        "geo",
        "seo-geo",
        "seo-geo-performance",
        "complete-safe",
        "complete-maximum",
    }:
        try:
            context = configured_content_analysis_context()
        except ValueError as exc:
            blockers.append(f"Contexto editorial: {exc}")
        else:
            advisories.append(
                "Contexto editorial/YMYL permanece AUTO; nenhum valor é inventado."
                if context.is_fully_auto
                else "Contexto editorial explícito da sessão será preservado."
            )

    try:
        gsc_blockers, gsc_advisories = readiness._gsc_dependency_status(state, current)
    except (AttributeError, TypeError, ValueError):
        gsc_blockers, gsc_advisories = (), ()

    blockers.extend(item for item in gsc_blockers if item not in blockers)
    advisories.extend(item for item in gsc_advisories if item not in advisories)
    return not blockers, tuple(dict.fromkeys(blockers)), tuple(dict.fromkeys(advisories))


def cost_lines(state: Any, session: Any) -> tuple[str, ...]:
    from rasai.console_cost import estimate_exposure
    from rasai.console_m23 import synthetic_load_summary

    lines: list[str] = []
    with effective_profile(state, session):
        estimate = estimate_exposure(state)
        lines.append(f"Exposição estimada do core/IA/Web Performance: {estimate.level}")
        if "apdex-navigation" in session.modules or "apdex-experience" in session.modules:
            attempts, load = synthetic_load_summary(state)
            lines.append(
                "Carga sintética: "
                + (
                    load
                    if attempts
                    else "depende da parametrização vigente; o perfil não inventa carga"
                )
            )

    for capability_id in session.modules:
        note = CAPABILITY_BY_ID[capability_id].cost_note
        if note and note not in lines:
            lines.append(note)

    lines.append(
        "Integrações opt-in não são ativadas pelo perfil; credenciais e políticas próprias são preservadas."
    )
    return tuple(lines)


def _scope_state(session: Any) -> tuple[str, ...]:
    capabilities = set(tuple(getattr(session, "modules", ()) or ()))
    from rasai import console_execution_profiles as profiles

    return (
        f"IA principal: {'DESABILITADA' if session.ai_mode == profiles.AI_OFF else 'HABILITADA SE APTA'}",
        f"Search Intelligence: {'SOLICITADA' if 'search-intelligence' in capabilities else 'NÃO SOLICITADA'}",
        f"Apdex navegação: {'SOLICITADO' if 'apdex-navigation' in capabilities else 'NÃO SOLICITADO'}",
        f"Apdex experiência: {'SOLICITADO' if 'apdex-experience' in capabilities else 'NÃO SOLICITADO'}",
        f"Análise profunda: {'SOLICITADA' if 'deep-analysis' in capabilities else 'NÃO SOLICITADA'}",
        f"Remediação por IA: {'POSSÍVEL SE CONFIGURADA' if 'remediation' in capabilities and session.ai_mode != profiles.AI_OFF else 'DESABILITADA'}",
    )


def render_detail(state: Any, session: Any) -> None:
    from rasai import console_ui_catalog as ui
    from rasai.console_ui import CYAN, GREEN, YELLOW, paint

    meta = UX.get(str(session.profile_id))
    print(f"\n{session.label}\n" + "-" * min(max(len(session.label), 24), 80))
    print(
        f"Uso esperado      : {meta.purpose if meta else 'Composição personalizada de capacidades.'}"
    )
    print(
        f"Resultado esperado: {meta.result if meta else 'Somente workloads selecionados, além do core automático.'}"
    )

    print("\nESCOPO EFETIVO DO PERFIL")
    for line in _scope_state(session):
        print(f"- {line}")

    print("\nCAPACIDADES")
    with effective_profile(state, session):
        for capability_id in session.modules:
            capability = _ui_capability(capability_id)
            if capability:
                status, detail = ui.capability_status(state, capability)
                print(f"- {capability.label}: {status} — {detail}")

    ready, blockers, advisories = dependency_status(state, session)
    for item in blockers:
        print(paint(f"CONFIGURAR: {item}", YELLOW, bold=True))
    for item in advisories:
        print(paint(f"INFO: {item}", CYAN))

    print("\nIMPACTO / CUSTO")
    for line in cost_lines(state, session):
        print(f"- {line}")

    print(
        paint(
            "\nO perfil define o escopo da execução. Variáveis da sessão parametrizam apenas capacidades incluídas; não reativam workloads excluídos.",
            GREEN,
            bold=True,
        )
    )
    print(
        "Ajustes explícitos feitos depois da seleção do perfil continuam com precedência e o estado pai é restaurado após a execução."
    )
    if not ready:
        print(paint("Resolva as pendências antes de aplicar/executar este perfil.", YELLOW))


def choose_ai_mode(state: Any) -> str | None:
    from rasai import console_execution_profiles as profiles

    print("\nIA PRINCIPAL NESTE PERFIL")
    print("1. Não usar IA nesta execução do perfil")
    print("   A IA configurada na sessão permanece salva, mas fica desabilitada durante esta execução.")
    print("2. Usar IA principal/AUTO se houver provider APTO")
    print("   A seleção atual da sessão é usada quando estiver apta; caso contrário, vale o orquestrador AUTO.")
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


def custom_capabilities(state: Any) -> tuple[str, ...] | None:
    selected: set[str] = set()
    while True:
        print("\nPERFIL PERSONALIZADO — CAPACIDADES SELECIONÁVEIS")
        print(
            "Automáticas/derivadas continuam incluídas pelo core e não recebem checkbox.\n"
        )
        for index, item in enumerate(PROFILE_SELECTABLE, 1):
            marker = "*" if item.id in selected else " "
            print(
                f" {index:2d}. [{marker}] {item.label}\n"
                f"     Resultado: {item.expected_result}"
            )
        print("\nNúmero=marcar/desmarcar | A=aplicar | V=voltar")
        raw = input("Escolha: ").strip().upper()
        if raw == "V":
            return None
        if raw == "A":
            if not selected:
                state.error = "selecione ao menos uma capacidade"
                continue
            return tuple(item.id for item in PROFILE_SELECTABLE if item.id in selected)
        try:
            item = PROFILE_SELECTABLE[int(raw) - 1]
        except (ValueError, IndexError):
            state.error = "capacidade inválida"
            continue
        if (
            item.id == "apdex-navigation"
            and item.id in selected
            and "apdex-experience" in selected
        ):
            state.error = "Apdex de navegação é dependência do Apdex de experiência"
            continue
        if item.id in selected:
            selected.remove(item.id)
        else:
            selected.add(item.id)
            if item.id == "apdex-experience":
                selected.add("apdex-navigation")
        state.error = ""


def configure_profile(state: Any) -> None:
    from rasai import console_execution_profile_readiness as readiness
    from rasai import console_execution_profiles as profiles
    from rasai.console_ui import CYAN, DIM, GREEN, YELLOW, paint

    if str(getattr(state, "input_mode", "")).casefold() != "url" or not str(
        getattr(state, "target", "")
    ).strip():
        state.error = "Perfis ficam disponíveis somente após informar uma URL única"
        return

    while True:
        print("\nPERFIS DA PRÓXIMA AUDITORIA — CATÁLOGO ÚNICO\n")
        print(
            paint(
                "O perfil define o escopo efetivo da próxima execução; configurações da sessão não reativam capacidades excluídas.",
                CYAN,
                bold=True,
            )
        )
        print(
            paint(
                "Ajustes explícitos realizados depois da escolha do perfil continuam com precedência.",
                DIM,
            )
        )
        print(paint("[CONFIGURAR] = falta dependência para o resultado prometido.\n", DIM))

        for index, definition in enumerate(profiles.PROFILES, 1):
            candidate = readiness._candidate(state, definition)
            ready, blockers, _ = profiles.dependency_status(state, candidate)
            meta = UX[definition.id]
            marker = (
                paint("APTO", GREEN, bold=True)
                if ready
                else paint("CONFIGURAR", YELLOW, bold=True)
            )
            print(
                f" {index:2d}. [{marker}] {definition.label}\n"
                f"     Uso   : {meta.purpose}\n"
                f"     Espera: {meta.result}"
            )
            for blocker in blockers:
                print(paint(f"     Falta : {blocker}", YELLOW))

        print("\n C. Personalizado por capacidades")
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
            capabilities = custom_capabilities(state)
            if capabilities is None:
                continue
            candidate = profiles.SessionProfile(
                "custom",
                "Personalizado",
                capabilities,
                profiles.AI_OFF,
                profiles._baseline(state),
            )
            readiness.set_gsc_profile_policy(
                candidate, readiness.GSC_PROFILE_IF_COMPATIBLE
            )
        else:
            try:
                definition = profiles.PROFILES[int(raw) - 1]
            except (ValueError, IndexError):
                state.error = "perfil inválido"
                continue
            candidate = readiness._candidate(state, definition)

        if "deep-analysis" in candidate.modules:
            candidate.ai_mode = profiles.AI_IF_AVAILABLE
            print(
                paint(
                    "\nIA principal é obrigatória para Análise profunda e será resolvida pela seleção atual/AUTO.",
                    CYAN,
                )
            )
        else:
            mode = choose_ai_mode(state)
            if mode is None:
                continue
            candidate.ai_mode = mode

        ready, blockers, _ = profiles.dependency_status(state, candidate)
        if not ready:
            state.error = "; ".join(blockers)
            continue

        if not readiness._choose_gsc_policy(state, candidate):
            continue

        ready, blockers, _ = profiles.dependency_status(state, candidate)
        if not ready:
            state.error = "; ".join(blockers)
            continue

        render_detail(state, candidate)
        readiness._print_gsc_policy_detail(state, candidate)
        print("\nA. Aplicar à sessão")
        print("V. Voltar sem alterar")
        if input("Escolha: ").strip().upper() != "A":
            continue

        profiles._SESSIONS[id(state)] = candidate
        state.error = ""
        state.operation = "LOCAL:EXECUTION_PROFILE_SELECTED"
        return


def profile_summary(state: Any) -> None:
    from rasai import console_execution_profile_readiness as readiness
    from rasai import console_execution_profiles as profiles
    from rasai.console_cost import estimate_exposure
    from rasai.console_ui import CYAN, DIM, GREEN, RED, YELLOW, paint

    current = profiles.active_profile(state)
    allowed = str(getattr(state, "input_mode", "")).casefold() == "url" and bool(
        str(getattr(state, "target", "")).strip()
    )

    print("\nPERFIL DA PRÓXIMA EXECUÇÃO")
    if current is None:
        if allowed:
            print(
                f"F. Perfil da execução     : {paint('NENHUM', DIM)} | sessão preservada"
            )
        else:
            print(
                f"F. Perfil da execução     : {paint('INDISPONÍVEL', RED, bold=True)} | informe URL única"
            )
        return

    ready, blockers, advisories = profiles.dependency_status(state, current)
    marker = (
        paint("APTO", GREEN, bold=True)
        if ready
        else paint("CONFIGURAR", YELLOW, bold=True)
    )
    labels = ", ".join(CAPABILITY_BY_ID[item].label for item in current.modules)
    ai_label = "SEM IA" if current.ai_mode == profiles.AI_OFF else "IA SE APTA"

    print(
        f"F. Perfil da execução     : {marker} | {current.label} | {ai_label} | SESSÃO"
    )
    print(f"   Capacidades            : {labels}")
    print(
        paint(
            "   Precedência            : perfil define o escopo; ajustes explícitos posteriores vencem",
            DIM,
        )
    )
    print(
        f"   Google Search Console  : {readiness._gsc_policy_label(readiness.gsc_profile_policy(current))}"
    )
    with effective_profile(state, current):
        estimate = estimate_exposure(state)
    print(
        f"   Exposição estimada     : {estimate.level} | Web API até {estimate.max_web_calls} | "
        f"IA até {estimate.max_ai_attempts} tentativa(s)"
    )
    for item in blockers:
        print(paint(f"   CONFIGURAR             : {item}", YELLOW))
    for item in advisories:
        print(paint(f"   INFO                   : {item}", CYAN))


def metadata(session: Any) -> dict[str, Any]:
    capabilities = list(tuple(getattr(session, "modules", ()) or ()))
    return {
        "profile_id": str(getattr(session, "profile_id", "") or ""),
        "label": str(getattr(session, "label", "") or ""),
        "capabilities": capabilities,
        "ai_mode": str(getattr(session, "ai_mode", "") or ""),
        "manual_overrides": sorted(
            str(item)
            for item in (getattr(session, "manual_overrides", set()) or set())
        ),
    }


def _install_catalog() -> None:
    from rasai import console_execution_profiles as profiles
    from rasai import console_ui_catalog as ui

    handlers = {
        "web-performance": "6",
        "search-intelligence": "T",
        "apdex-navigation": "11",
        "apdex-experience": "11",
        "deep-analysis": "13",
        "remediation": "5",
    }
    ui.CAPABILITIES = tuple(
        ui.CapabilityUI(
            item.id,
            item.label,
            f"{item.purpose} Resultado esperado: {item.expected_result}",
            handlers.get(item.id),
            item.automatic,
            item.derived,
        )
        for item in AUDIT_CAPABILITIES
    )
    profiles.MODULES = tuple(
        profiles.ExecutionModule(
            item.id,
            item.label,
            item.purpose,
            (),
            item.cost_note,
            "Usa o contrato canônico desta capacidade; o perfil não inventa credenciais/inputs.",
        )
        for item in AUDIT_CAPABILITIES
    )
    profiles.MODULE_BY_ID = {item.id: item for item in profiles.MODULES}
    profiles.PROFILES = tuple(
        profiles.ExecutionProfile(pid, LABELS[pid], UX[pid].purpose, capability_ids)
        for pid, capability_ids in CAPS.items()
    )
    profiles._PROFILE_BY_ID = {item.id: item for item in profiles.PROFILES}


def install(console_module: Any) -> None:
    global _INSTALLED
    if _INSTALLED or getattr(
        console_module, "_rasai_profile_capability_architecture", False
    ):
        return

    _install_catalog()
    from rasai import audit_configuration_reuse_console as reuse
    from rasai import console_execution_profiles as profiles

    profiles.effective_profile = effective_profile
    profiles.dependency_status = dependency_status
    profiles._profile_categories = _categories
    profiles._cost_lines = cost_lines
    profiles._render_profile_detail = render_detail
    profiles._choose_ai_mode = choose_ai_mode
    profiles._custom_modules = custom_capabilities
    profiles.configure_profile = configure_profile
    profiles._profile_summary = profile_summary
    reuse._execution_profile_metadata = metadata

    console_module._rasai_profile_capability_architecture = True
    _INSTALLED = True
