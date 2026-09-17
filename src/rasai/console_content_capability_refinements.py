"""CAT-03 presentation for content, semantic context and structured data.

CAT-03 owns evidence and diagnosis. Remediation is deliberately excluded from this
surface and remains owned by CAT-09. Optional semantic AI uses the canonical global AI
orchestrator; this module never creates a CAT-specific provider path.
"""
from __future__ import annotations

from types import ModuleType
from typing import Any

from rasai.console_ui import CYAN, DIM, RED, paint
from rasai.property_semantic_profile import PROPERTY_SEMANTIC_PROFILE_ENV_NAMES

_PROPERTY_NAMES = frozenset(PROPERTY_SEMANTIC_PROFILE_ENV_NAMES)
_EDITORIAL_NAMES = frozenset(
    {
        "RASAI_CONTENT_ORIGIN",
        "RASAI_INTENDED_AUDIENCE",
        "RASAI_PAGE_PURPOSE",
    }
)
_TRUST_NAMES = frozenset(
    {
        "RASAI_CONTENT_RISK_PROFILE",
        "RASAI_YMYL_CATEGORY",
        "RASAI_EXPERIENCE_REQUIREMENT",
        "RASAI_FRESHNESS_SENSITIVITY",
    }
)
_SHARED_AI_NAMES = frozenset({"RASAI_AI_ANALYSIS_LANGUAGE"})
_CONTENT_NAMES = _PROPERTY_NAMES | _EDITORIAL_NAMES | _TRUST_NAMES | _SHARED_AI_NAMES


def _content_spec(spec: Any) -> bool:
    return str(getattr(spec, "name", "")).upper() in _CONTENT_NAMES


def _content_groups(
    specs: tuple[Any, ...],
) -> tuple[tuple[Any, ...], tuple[Any, ...], tuple[Any, ...], tuple[Any, ...]]:
    def group(names: frozenset[str]) -> tuple[Any, ...]:
        return tuple(
            sorted(
                (spec for spec in specs if str(spec.name).upper() in names),
                key=lambda item: item.name.casefold(),
            )
        )

    return group(_PROPERTY_NAMES), group(_EDITORIAL_NAMES), group(_TRUST_NAMES), group(_SHARED_AI_NAMES)


def _property_context_status() -> tuple[str, str]:
    from rasai.property_semantic_profile import configured_property_semantic_profile

    try:
        profile = configured_property_semantic_profile()
    except ValueError as exc:
        return "CONFIGURAR", str(exc)
    if profile.is_fully_auto:
        return "AUTOMÁTICO", "perfil da propriedade permanece em auto; a IA pode inferir apenas hipóteses transitórias"
    configured = ", ".join(profile.configured_fields)
    return "PERSONALIZADO", f"contexto explícito em: {configured}"


def _editorial_context_status() -> tuple[str, str]:
    from rasai.content_context import configured_content_analysis_context

    try:
        context = configured_content_analysis_context()
    except ValueError as exc:
        return "CONFIGURAR", str(exc)
    configured = [name for name in context.configured_fields if name in {"page_purpose", "intended_audience", "content_origin"}]
    if not configured:
        return "AUTOMÁTICO", "propósito, público categórico e origem permanecem em auto"
    return "PERSONALIZADO", "contexto explícito em: " + ", ".join(configured)


def _trust_context_status() -> tuple[str, str]:
    from rasai.content_context import configured_content_analysis_context

    try:
        context = configured_content_analysis_context()
    except ValueError as exc:
        return "CONFIGURAR", str(exc)
    configured = [
        name
        for name in context.configured_fields
        if name in {"risk_profile", "ymyl_category", "experience_requirement", "freshness_sensitivity"}
    ]
    if not configured:
        return "AUTOMÁTICO", "risco/YMYL, experiência e freshness permanecem em auto"
    return "PERSONALIZADO", "requisitos explícitos em: " + ", ".join(configured)


def _semantic_ai_status(state: Any) -> tuple[str, str]:
    try:
        from rasai.console_catalog_plan import ai_execution_enabled, ai_provider_readiness, is_selected

        if not is_selected(state, "CAT-03") or not ai_execution_enabled(state):
            return "NÃO SOLICITADA", "CAT-03 mantém baseline determinística; enriquecimento semântico por IA não foi solicitado"
        ready, detail = ai_provider_readiness(state)
        if not ready:
            return "CONFIGURAR", detail or "execução semântica por IA foi solicitada, mas a IA principal não está apta"
        return "APTO", detail or "IA principal apta para análise semântica evidence-bound"
    except (ImportError, AttributeError, TypeError, ValueError):
        provider = str(getattr(state, "ai_provider", "none") or "none").strip().casefold()
        if provider == "none":
            return "NÃO SOLICITADA", "baseline determinística disponível; IA semântica opcional"
        return "APTO", f"IA principal configurada: {provider}"


def _content_component_states(state: Any) -> tuple[tuple[str, str, str], ...]:
    property_status, property_detail = _property_context_status()
    editorial_status, editorial_detail = _editorial_context_status()
    trust_status, trust_detail = _trust_context_status()
    ai_status, ai_detail = _semantic_ai_status(state)
    return (
        (
            "Conteúdo / estrutura",
            "INCLUÍDO",
            "coleta e avaliações determinísticas permanecem no contrato da auditoria",
        ),
        (
            "JSON-LD",
            "INCLUÍDO",
            "estrutura e consistência determinística permanecem independentes da IA",
        ),
        ("Contexto da propriedade", property_status, property_detail),
        ("Contexto editorial", editorial_status, editorial_detail),
        ("Risco / confiança", trust_status, trust_detail),
        ("Coerência semântica IA", ai_status, ai_detail),
    )


def _content_overall_status(state: Any) -> tuple[str, str]:
    property_status, _ = _property_context_status()
    editorial_status, _ = _editorial_context_status()
    trust_status, _ = _trust_context_status()
    ai_status, _ = _semantic_ai_status(state)
    if "CONFIGURAR" in {property_status, editorial_status, trust_status}:
        return "CONFIGURAR", "há contexto CAT-03 inválido; corrija antes da execução"
    return (
        "INCLUÍDO",
        "conteúdo/estrutura e JSON-LD determinísticos incluídos; "
        f"propriedade={property_status}; editorial={editorial_status}; risco={trust_status}; IA semântica={ai_status}",
    )


def _print_spec_row(catalog: ModuleType, state: Any, spec: Any, *, shared: bool = False) -> None:
    suffix = " · compartilhada/global" if shared else ""
    print(
        f"{catalog.configuration_id(spec.name)}  {spec.name:<46} "
        f"[{catalog.origin_for(state, spec)}]{suffix}"
    )


def _render_group(catalog: ModuleType, state: Any, title: str, specs: tuple[Any, ...], *, shared: bool = False) -> None:
    catalog.section(title)
    if specs:
        for spec in specs:
            _print_spec_row(catalog, state, spec, shared=shared)
    else:
        print(paint("Nenhuma configuração adicional neste contexto.", DIM))


def _render_content_groups(catalog: ModuleType, state: Any, specs: tuple[Any, ...]) -> None:
    property_specs, editorial, trust, shared_ai = _content_groups(specs)
    _render_group(catalog, state, "CONTEXTO DA PROPRIEDADE", property_specs)
    print(paint("Campos em auto são válidos; inferências da IA não sobrescrevem esses valores.", DIM))
    _render_group(catalog, state, "CONTEXTO EDITORIAL DA PÁGINA", editorial)
    _render_group(catalog, state, "RISCO E REQUISITOS DE CONFIANÇA", trust)
    _render_group(catalog, state, "IA SEMÂNTICA · CONFIGURAÇÃO COMPARTILHADA", shared_ai, shared=True)
    print(
        paint(
            "Provider/modelo/reasoning pertencem à IA principal. Remediação não pertence ao CAT-03; consulte CAT-09.",
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
            "CAT-03 evidencia o que foi coletado, derivado deterministicamente e interpretado semanticamente. "
            "O perfil da propriedade e o contexto editorial condicionam a análise; CAT-09 continua sendo o owner das remediações."
        )

        catalog.section("COMPONENTES")
        for label, status, detail in _content_component_states(state):
            print(f"{label:<24}: {catalog.badge(status)}")
            print(paint(f"  {detail}", DIM))

        catalog.section("COMO OPERAR")
        print('Digite diretamente o ID da variável no campo "Número/ID ou ação" para editá-la.')
        print("AUTO é válido e significa hipótese transitória quando a IA estiver habilitada; nunca vira configuração automaticamente.")
        print("A IA semântica usa a IA principal global e mantém routing, fallback, custo e rastreabilidade canônicos.")
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
            print(f"{label:<24}: {catalog.badge(component_status)}")
            print(paint(f"  {component_detail}", DIM))

        catalog.section("INFORMAÇÃO")
        print(
            "Conteúdo/estrutura e JSON-LD permanecem disponíveis sem IA. Quando solicitada, a IA avalia coerência "
            "somente após o contexto/evidências necessários estarem coletados; ações corretivas pertencem ao CAT-09."
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
    """Install CAT-03 presentation without altering runtime routing or scoring."""
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

    refactor.capability_specs = capability_specs
    refactor.capability_status = capability_status
    refactor.capability_menu = capability_menu

    console_module._rasai_content_capability_refinements = True
