"""Presentation-only segmentation for the Conteúdo e JSON-LD capability.

The runtime contract remains unchanged: deterministic content/structure and JSON-LD
analysis stay included, editorial context remains optional/AUTO, and AI remediation is
an optional enrichment using the canonical primary-AI orchestration.
"""
from __future__ import annotations

from types import ModuleType
from typing import Any

from rasai.console_ui import CYAN, DIM, RED, paint

_CONTENT_EDITORIAL_NAMES = frozenset(
    {
        "RASAI_CONTENT_ORIGIN",
        "RASAI_CONTENT_RISK_PROFILE",
        "RASAI_EXPERIENCE_REQUIREMENT",
        "RASAI_FRESHNESS_SENSITIVITY",
        "RASAI_INTENDED_AUDIENCE",
        "RASAI_PAGE_PURPOSE",
        "RASAI_YMYL_CATEGORY",
    }
)
_CONTENT_AI_NAMES = frozenset(
    {
        "RASAI_AI_CONTENT_REMEDIATION",
        "RASAI_AI_ANALYSIS_LANGUAGE",
    }
)
_CONTENT_NAMES = _CONTENT_EDITORIAL_NAMES | _CONTENT_AI_NAMES


def _content_spec(spec: Any) -> bool:
    return str(getattr(spec, "name", "")).upper() in _CONTENT_NAMES


def _content_groups(specs: tuple[Any, ...]) -> tuple[tuple[Any, ...], tuple[Any, ...]]:
    editorial = tuple(
        sorted(
            (spec for spec in specs if str(spec.name).upper() in _CONTENT_EDITORIAL_NAMES),
            key=lambda item: item.name.casefold(),
        )
    )
    ai = tuple(
        sorted(
            (spec for spec in specs if str(spec.name).upper() in _CONTENT_AI_NAMES),
            key=lambda item: item.name.casefold(),
        )
    )
    return editorial, ai


def _editorial_context_status() -> tuple[str, str]:
    from rasai.content_context import configured_content_analysis_context

    try:
        context = configured_content_analysis_context()
    except ValueError as exc:
        return "CONFIGURAR", str(exc)
    if context.is_fully_auto:
        return "AUTOMÁTICO", "todos os campos editoriais permanecem em auto"
    configured = ", ".join(context.configured_fields)
    return "PERSONALIZADO", f"contexto explícito em: {configured}"


def _content_ai_status(state: Any) -> tuple[str, str]:
    if not bool(getattr(state, "content_remediation", False)):
        return "NÃO SOLICITADA", "remediação textual por IA não foi solicitada; análise determinística permanece incluída"

    try:
        from rasai.console_execution_profiles import _effective_ai_provider

        provider = _effective_ai_provider(state)
    except (ImportError, AttributeError, TypeError, ValueError):
        provider = str(getattr(state, "ai_provider", "none") or "none").strip().casefold()

    if provider == "none":
        return "CONFIGURAR", "remediação por IA foi solicitada, mas nenhuma IA principal está apta"
    return "APTO", f"remediação por IA solicitada; provider efetivo={provider}"


def _content_component_states(state: Any) -> tuple[tuple[str, str, str], ...]:
    editorial_status, editorial_detail = _editorial_context_status()
    ai_status, ai_detail = _content_ai_status(state)
    return (
        (
            "Conteúdo / estrutura",
            "INCLUÍDO",
            "análise determinística do conteúdo e da estrutura permanece no contrato da auditoria",
        ),
        (
            "JSON-LD",
            "INCLUÍDO",
            "orientação e validação determinísticas permanecem independentes da IA",
        ),
        ("Contexto editorial", editorial_status, editorial_detail),
        ("Remediação por IA", ai_status, ai_detail),
    )


def _content_overall_status(state: Any) -> tuple[str, str]:
    editorial_status, _ = _editorial_context_status()
    ai_status, _ = _content_ai_status(state)
    return (
        "INCLUÍDO",
        "conteúdo/estrutura e JSON-LD determinísticos incluídos; "
        f"contexto editorial={editorial_status}; remediação por IA={ai_status}",
    )


def _print_spec_row(catalog: ModuleType, state: Any, spec: Any, *, shared: bool = False) -> None:
    suffix = " · compartilhada/global" if shared else ""
    print(
        f"{catalog.configuration_id(spec.name)}  {spec.name:<46} "
        f"[{catalog.origin_for(state, spec)}]{suffix}"
    )


def _render_content_groups(catalog: ModuleType, state: Any, specs: tuple[Any, ...]) -> None:
    editorial, ai = _content_groups(specs)

    catalog.section("CONTEXTO EDITORIAL")
    if editorial:
        for spec in editorial:
            _print_spec_row(catalog, state, spec)
    else:
        print(paint("Nenhuma configuração editorial adicional neste contexto.", DIM))
    print(paint("Campos em auto são válidos e não representam pendência de configuração.", DIM))

    catalog.section("ENRIQUECIMENTO POR IA")
    if ai:
        for spec in ai:
            _print_spec_row(
                catalog,
                state,
                spec,
                shared=str(spec.name).upper() == "RASAI_AI_ANALYSIS_LANGUAGE",
            )
    else:
        print(paint("Nenhuma configuração adicional de IA neste contexto.", DIM))
    print(
        paint(
            "A remediação por IA é opcional; JSON-LD e análise determinística de conteúdo não dependem dela.",
            DIM,
        )
    )


def _content_help(
    catalog: ModuleType,
    console_module: ModuleType,
    state: Any,
    capability: Any,
    specs: tuple[Any, ...],
) -> None:
    from rasai import console_provider_environment as env

    while True:
        env.base_environment.render_header(state)
        print(
            paint(
                f"INÍCIO > PREPARAR AUDITORIA > {capability.label.upper()} > AJUDA DE CONTEXTO",
                CYAN,
                bold=True,
            )
        )
        catalog.section("OBJETIVO")
        print(
            "Conteúdo/estrutura e JSON-LD são análises determinísticas incluídas. "
            "O contexto editorial pode permanecer em auto ou receber overrides explícitos; "
            "a remediação textual por IA é apenas um enriquecimento opcional."
        )

        catalog.section("COMPONENTES")
        for label, status, detail in _content_component_states(state):
            print(f"{label:<20}: {catalog.badge(status)}")
            print(paint(f"  {detail}", DIM))

        catalog.section("COMO OPERAR")
        print('Digite diretamente o ID da variável no campo "Número/ID ou ação" para editá-la.')
        print("Valores editoriais em auto são válidos; configure apenas quando houver contexto humano conhecido.")
        print("RASAI_AI_ANALYSIS_LANGUAGE é compartilhada com outras análises de IA e mantém owner canônico único.")
        _render_content_groups(catalog, state, specs)

        print("\nDigite um ID acima para abrir a configuração, ou ENTER/V para voltar.")
        raw = input("ID ou ação: ").strip().upper()
        if not raw or raw == "V":
            return
        selected = next(
            (spec for spec in specs if catalog.configuration_id(spec.name) == raw),
            None,
        )
        if selected is not None:
            catalog.variable_editor(console_module, state, selected)
            return
        print(paint("ID inválido neste contexto.", RED, bold=True))
        input("ENTER para tentar novamente...")


def _content_menu(
    catalog: ModuleType,
    console_module: ModuleType,
    state: Any,
    capability: Any,
) -> str | None:
    from rasai import console_provider_environment as env

    while True:
        status, detail = catalog.capability_status(state, capability)
        specs = catalog.capability_specs(capability.key)
        env.base_environment.render_header(state)
        print(
            paint(
                f"INÍCIO > PREPARAR AUDITORIA > {capability.label.upper()}",
                CYAN,
                bold=True,
            )
        )

        catalog.section("ESTADO")
        catalog.info("Capacidade", capability.label)
        catalog.info("Estado geral", catalog.badge(status))
        catalog.info("Resumo", detail)

        catalog.section("COMPONENTES")
        for label, component_status, component_detail in _content_component_states(state):
            print(f"{label:<20}: {catalog.badge(component_status)}")
            print(paint(f"  {component_detail}", DIM))

        catalog.section("INFORMAÇÃO")
        print(
            "Análise de conteúdo e orientação JSON-LD determinísticas incluídas. "
            "Contexto editorial pode permanecer automático ou ser informado explicitamente. "
            "Remediação por IA é opcional."
        )

        _render_content_groups(catalog, state, specs)

        catalog.section("AÇÕES")
        print("H. Ajuda de contexto")
        print("V. Voltar para Preparar auditoria")
        raw = input("Número/ID ou ação: ").strip().upper()
        if raw == "V":
            return None
        if raw == "H":
            _content_help(catalog, console_module, state, capability, specs)
            continue
        selected = next(
            (spec for spec in specs if catalog.configuration_id(spec.name) == raw),
            None,
        )
        if selected is not None:
            catalog.variable_editor(console_module, state, selected)
            continue
        state.error = "opção inválida neste relatório/capacidade"


def install(console_module: ModuleType) -> None:
    """Install after the operator-navigation layer without altering runtime semantics."""
    if getattr(console_module, "_rasai_content_capability_refinements", False):
        return

    from rasai import console_provider_environment as facade
    from rasai import console_ui_catalog as catalog
    from rasai import console_ui_refactor as refactor

    original_specs = catalog.capability_specs
    original_status = catalog.capability_status
    original_menu = catalog.capability_menu

    def capability_specs(capability: str) -> tuple[Any, ...]:
        if capability == "content-suggestions":
            return tuple(spec for spec in facade.refresh_specs() if _content_spec(spec))
        return original_specs(capability)

    def capability_status(state: Any, capability: Any) -> tuple[str, str]:
        if capability.key == "content-suggestions":
            return _content_overall_status(state)
        return original_status(state, capability)

    def capability_menu(console: ModuleType, state: Any, capability: Any) -> str | None:
        if capability.key == "content-suggestions":
            return _content_menu(catalog, console, state, capability)
        return original_menu(console, state, capability)

    catalog.capability_specs = capability_specs
    catalog.capability_status = capability_status
    catalog.capability_menu = capability_menu
    catalog._STATUS_COLORS["NÃO SOLICITADA"] = DIM

    # console_ui_refactor imported these callables by value, so refresh its bindings too.
    refactor.capability_specs = capability_specs
    refactor.capability_status = capability_status
    refactor.capability_menu = capability_menu

    console_module._rasai_content_capability_refinements = True
