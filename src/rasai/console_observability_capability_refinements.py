"""Presentation-only readiness for external observability in the preparation console.

The canonical external-observability runtime owns three sources: CrUX History,
Microsoft Clarity and Common Crawl.  This module only aligns the preparation UI with
that contract; it does not enable collectors or change scoring/runtime behavior.
"""
from __future__ import annotations

import os
from types import ModuleType
from typing import Any

from rasai.console_ui import CYAN, DIM, RED, paint
from rasai.external_observability_policy import (
    CLARITY_DAYS_ENV,
    CLARITY_DIMENSIONS_ENV,
    COMMON_CRAWL_INDEX_COUNT_ENV,
    COMMON_CRAWL_MAX_URLS_ENV,
)

_SOURCE_IDS = ("crux-history", "microsoft-clarity", "common-crawl")
_SOURCE_EXTRA_NAMES = {
    "crux-history": (),
    "microsoft-clarity": (CLARITY_DAYS_ENV, CLARITY_DIMENSIONS_ENV),
    "common-crawl": (COMMON_CRAWL_MAX_URLS_ENV, COMMON_CRAWL_INDEX_COUNT_ENV),
}
_SOURCE_LABELS = {
    "crux-history": "CrUX History",
    "microsoft-clarity": "Microsoft Clarity",
    "common-crawl": "Common Crawl",
}


def _source_names() -> dict[str, tuple[str, ...]]:
    from rasai.standards_service_registry import service

    result: dict[str, tuple[str, ...]] = {}
    for service_id in _SOURCE_IDS:
        item = service(service_id)
        names = (
            item.enabled_env,
            *item.credential_envs,
            *item.config_envs,
            *((item.dataset_env,) if item.dataset_env else ()),
            *_SOURCE_EXTRA_NAMES[service_id],
        )
        result[service_id] = tuple(dict.fromkeys(name for name in names if name))
    return result


def _observability_specs() -> tuple[Any, ...]:
    from rasai import console_provider_environment as facade

    names = {name for values in _source_names().values() for name in values}
    return tuple(spec for spec in facade.refresh_specs() if spec.name in names)


def _service_component(service_id: str) -> tuple[str, str, str]:
    from rasai.standards_service_registry import service, service_state

    item = service(service_id)
    try:
        state = service_state(item, os.environ)
    except ValueError as exc:
        return _SOURCE_LABELS[service_id], "CONFIGURAR", str(exc)

    technical = str(state["state"])
    if technical == "READY":
        if service_id == "crux-history":
            detail = "série histórica por origem/form factor; credencial disponível"
        elif service_id == "microsoft-clarity":
            detail = "Data Export explicitamente habilitado; sujeito à quota diária do projeto"
        else:
            detail = "consulta bounded ao índice público; sem credencial"
        return _SOURCE_LABELS[service_id], "APTO", detail

    if technical == "NOT_CONFIGURED":
        missing = ", ".join(str(name) for name in state.get("missing_configuration", ()) or ())
        return (
            _SOURCE_LABELS[service_id],
            "CONFIGURAR",
            f"fonte solicitada, mas falta configuração: {missing or 'requisito obrigatório'}",
        )

    explicit = (os.environ.get(item.enabled_env) or "").strip()
    if explicit:
        detail = f"{item.enabled_env}=false; fonte desabilitada explicitamente"
    elif service_id == "microsoft-clarity":
        detail = "opt-in não solicitado; token sozinho não habilita o Clarity"
    elif service_id == "crux-history":
        detail = "sem credencial/override elegível; coleta histórica não solicitada"
    else:
        detail = "fonte não solicitada"
    return _SOURCE_LABELS[service_id], "DESABILITADO", detail


def _component_states() -> tuple[tuple[str, str, str], ...]:
    return tuple(_service_component(service_id) for service_id in _SOURCE_IDS)


def _overall_status() -> tuple[str, str]:
    components = _component_states()
    configuring = [item for item in components if item[1] == "CONFIGURAR"]
    ready = [item for item in components if item[1] == "APTO"]
    if configuring:
        return "CONFIGURAR", f"{len(configuring)} fonte(s) solicitada(s) com configuração pendente"
    if ready:
        disabled = sum(1 for item in components if item[1] == "DESABILITADO")
        suffix = f"; {disabled} desabilitada(s)/não solicitada(s)" if disabled else ""
        return "APTO", f"{len(ready)} fonte(s) observacional(is) apta(s){suffix}"
    return "NÃO SOLICITADO", "nenhuma fonte observacional externa está ativa para esta execução"


def _print_spec(catalog: ModuleType, state: Any, spec: Any) -> None:
    from rasai import console_configuration_presentation as presentation

    print(presentation.format_configuration_row(state, spec))


def _render_source_groups(catalog: ModuleType, state: Any, specs: tuple[Any, ...]) -> None:
    by_name = {spec.name: spec for spec in specs}
    source_names = _source_names()
    for service_id in _SOURCE_IDS:
        catalog.section(_SOURCE_LABELS[service_id].upper())
        rows = [by_name[name] for name in source_names[service_id] if name in by_name]
        if not rows:
            print(paint("Nenhuma configuração adicional publicada para esta fonte.", DIM))
            continue
        for spec in rows:
            _print_spec(catalog, state, spec)
        if service_id == "microsoft-clarity":
            print(paint("Clarity é opt-in: credencial sem RASAI_CLARITY_ENABLED=true não solicita coleta.", DIM))
        elif service_id == "crux-history":
            print(paint("CrUX History pode ficar elegível por credencial, salvo hard-off explícito.", DIM))
        elif service_id == "common-crawl":
            print(paint("Common Crawl é público, bounded e sem credencial; o default vigente é habilitado.", DIM))


def _help(
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
            "Consolidar readiness das fontes observacionais externas realmente pertencentes a "
            "observability: CrUX History, Microsoft Clarity e Common Crawl."
        )
        print(
            paint(
                "Dynatrace não pertence a este grupo: ele é uma calibração opcional do Apdex de experiência.",
                DIM,
            )
        )
        catalog.section("CRITÉRIO DE ESTADO")
        print("APTO           : ao menos uma fonte está pronta e nenhuma fonte solicitada está incompleta.")
        print("CONFIGURAR     : uma fonte foi solicitada, mas falta credencial/configuração obrigatória.")
        print("NÃO SOLICITADO: nenhuma fonte está ativa/elegível.")
        print("DESABILITADO   : estado individual de uma fonte desligada ou sem opt-in.")
        catalog.section("FONTES")
        for label, status, detail in _component_states():
            print(f"{label:<20}: {catalog.badge(status)}")
            print(paint(f"  {detail}", DIM))
        _render_source_groups(catalog, state, specs)

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


def _menu(
    catalog: ModuleType,
    console_module: ModuleType,
    state: Any,
    capability: Any,
) -> str | None:
    from rasai import console_provider_environment as env

    while True:
        status, detail = _overall_status()
        specs = _observability_specs()
        env.base_environment.render_header(state)
        print(paint(f"INÍCIO > PREPARAR AUDITORIA > {capability.label.upper()}", CYAN, bold=True))

        catalog.section("ESTADO")
        catalog.info("Capacidade", capability.label)
        catalog.info("Estado geral", catalog.badge(status))
        catalog.info("Resumo", detail)

        catalog.section("FONTES OBSERVACIONAIS")
        for label, source_status, source_detail in _component_states():
            print(f"{label:<20}: {catalog.badge(source_status)}")
            print(paint(f"  {source_detail}", DIM))

        catalog.section("INFORMAÇÃO")
        print(
            "Fontes externas observacionais enriquecem o AUD sem substituir SARI/SCORE-GEO. "
            "Falha/ausência externa não vira finding do website."
        )
        print(
            paint(
                "SERP e Google Search Console possuem capacidades próprias; Dynatrace pertence à calibração do Apdex de experiência.",
                DIM,
            )
        )
        _render_source_groups(catalog, state, specs)

        catalog.section("AÇÕES")
        print("H. Ajuda de contexto")
        print("V. Voltar para Preparar auditoria")
        raw = input("Número/ID ou ação: ").strip().upper()
        if raw == "V":
            return None
        if raw == "H":
            _help(catalog, console_module, state, capability, specs)
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
    """Install the observability preparation view without changing collection runtime."""
    if getattr(console_module, "_rasai_observability_capability_refinements", False):
        return

    from rasai import console_ui_catalog as catalog
    from rasai import console_ui_refactor as refactor

    original_specs = catalog.capability_specs
    original_status = catalog.capability_status
    original_menu = catalog.capability_menu

    capabilities: list[Any] = []
    for item in catalog.CAPABILITIES:
        if item.key == "observability":
            item = catalog.CapabilityUI(
                "observability",
                "Observabilidade externa",
                "CrUX History, Microsoft Clarity e Common Crawl com readiness independente por fonte.",
                item.handler_choice,
                item.automatic,
                item.derived,
            )
        capabilities.append(item)
    catalog.CAPABILITIES = tuple(capabilities)

    def capability_specs(capability: str) -> tuple[Any, ...]:
        if capability == "observability":
            return _observability_specs()
        return original_specs(capability)

    def capability_status(state: Any, capability: Any) -> tuple[str, str]:
        if capability.key == "observability":
            return _overall_status()
        return original_status(state, capability)

    def capability_menu(console: ModuleType, state: Any, capability: Any) -> str | None:
        if capability.key == "observability":
            return _menu(catalog, console, state, capability)
        return original_menu(console, state, capability)

    catalog.capability_specs = capability_specs
    catalog.capability_status = capability_status
    catalog.capability_menu = capability_menu
    catalog._STATUS_COLORS["NÃO SOLICITADO"] = DIM

    refactor.CAPABILITIES = catalog.CAPABILITIES
    refactor.capability_specs = capability_specs
    refactor.capability_status = capability_status
    refactor.capability_menu = capability_menu

    console_module._rasai_observability_capability_refinements = True
