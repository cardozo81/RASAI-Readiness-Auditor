"""Final operator-navigation refinements for the interactive console.

Presentation/navigation only:
- make capability context help actionable instead of a disposable pause screen;
- never swallow a configuration ID typed from contextual help;
- allow V to cancel manual AUD-ID entry without emitting an invalid-AUD error;
- repair closed boolean metadata for service toggles when a later catalog overlay has
  preserved runtime validation but accidentally degraded the UI type/domain.
"""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import ModuleType
from typing import Any

from rasai.console_ui import CYAN, DIM, RED, paint


def _repair_service_toggle_domains() -> None:
    """Keep UI metadata aligned with the canonical boolean runtime contract."""
    from rasai import console_environment as base
    from rasai import console_provider_environment as facade
    from rasai.standards_service_registry import services

    enabled_names = {item.enabled_env for item in services()}
    specs = list(base.SPECS)
    changed = False
    for index, spec in enumerate(specs):
        if spec.name not in enabled_names:
            continue
        accepted = tuple(getattr(spec, "accepted", ()) or ())
        if str(spec.value_type).casefold() == "booleano" and accepted == ("true", "false"):
            continue
        specs[index] = replace(
            spec,
            value_type="booleano",
            accepted=("true", "false"),
        )
        changed = True

    if not changed:
        return
    base.SPECS = tuple(specs)
    base.SPEC_BY_NAME = {spec.name: spec for spec in specs}
    facade.refresh_specs()


def _context_help(
    catalog: ModuleType,
    console_module: ModuleType,
    state: Any,
    capability: Any,
    status: str,
    detail: str,
    specs: tuple[Any, ...],
) -> None:
    """Render actionable help and accept a capability-local configuration ID."""
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
        print(capability.help_text)
        if capability.automatic:
            print(
                paint(
                    "Esta capacidade é automática/derivada; não existe seleção independente para habilitá-la.",
                    DIM,
                )
            )

        catalog.section("ESTADO ATUAL")
        catalog.info("Estado", catalog.badge(status))
        catalog.info("Interpretação", detail)

        catalog.section("COMO OPERAR")
        print('Para editar uma variável, digite diretamente seu ID no campo "Número/ID ou ação".')
        print("Não é necessário pressionar H antes do ID; H abre somente esta explicação contextual.")
        if capability.handler_choice is not None:
            print("A opção 1 abre os parâmetros próprios da análise quando existir configurador dedicado.")
        print("Somente configurações consumidas por esta capacidade aparecem aqui; o owner canônico continua único.")

        catalog.section("CONFIGURAÇÕES RELACIONADAS")
        if not specs:
            print(paint("Nenhuma configuração adicional é necessária neste contexto.", DIM))
        else:
            for spec in sorted(
                specs,
                key=lambda item: (catalog.owner_for(item).casefold(), item.name.casefold()),
            ):
                print(
                    f"{catalog.configuration_id(spec.name)}  {spec.name:<46} "
                    f"[{catalog.origin_for(state, spec)}]"
                )
                purpose = str(getattr(spec, "purpose", "") or "").strip()
                required = str(getattr(spec, "required_when", "") or "").strip()
                impact = str(getattr(spec, "impact", "") or "").strip()
                if purpose:
                    print(paint(f"        Finalidade : {purpose}", DIM))
                if required:
                    print(paint(f"        Necessário : {required}", DIM))
                if impact:
                    print(paint(f"        Impacto    : {impact}", DIM))

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


def _capability_menu_factory(catalog: ModuleType):
    def capability_menu(console_module: ModuleType, state: Any, capability: Any) -> str | None:
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
            catalog.info("Estado", catalog.badge(status))
            catalog.info("Detalhe", detail)
            catalog.section("INFORMAÇÃO")
            print(capability.help_text)
            if capability.automatic:
                print(
                    paint(
                        "Resultado automático/derivado; não há checkbox independente.",
                        DIM,
                    )
                )
            if capability.handler_choice is not None:
                catalog.section("CONFIGURAÇÃO DA ANÁLISE")
                print("1. Alterar parâmetros próprios desta análise")

            catalog.section("DEPENDÊNCIAS / CONFIGURAÇÕES RELACIONADAS")
            if specs:
                for spec in sorted(
                    specs,
                    key=lambda item: (catalog.owner_for(item).casefold(), item.name.casefold()),
                ):
                    print(
                        f"{catalog.configuration_id(spec.name)}  {spec.name:<46} "
                        f"[{catalog.origin_for(state, spec)}]"
                    )
            else:
                print(paint("Nenhuma variável adicional é necessária neste contexto.", DIM))

            catalog.section("AÇÕES")
            print("H. Ajuda de contexto")
            print("V. Voltar para Preparar auditoria")
            raw = input("Número/ID ou ação: ").strip().upper()
            if raw == "V":
                return None
            if raw == "H":
                _context_help(
                    catalog,
                    console_module,
                    state,
                    capability,
                    status,
                    detail,
                    specs,
                )
                continue
            if raw == "1" and capability.handler_choice is not None:
                return capability.handler_choice
            selected = next(
                (spec for spec in specs if catalog.configuration_id(spec.name) == raw),
                None,
            )
            if selected is not None:
                catalog.variable_editor(console_module, state, selected)
                continue
            state.error = "opção inválida neste relatório/capacidade"

    return capability_menu


def _choose_audit_factory(console_module: ModuleType):
    def choose_audit(state: Any) -> str | None:
        from rasai import audit_management_console as management
        from rasai import console_navigation as navigation
        from rasai import console_usability_refinements as usability

        while True:
            audits = navigation._audit_directories(state.audits_root)
            print("\nAUDITORIAS / HISTÓRICO")
            print(f"Raiz: {state.audits_root}")
            if audits:
                recent = audits[:20]
                audit_width = max(36, min(44, max(len(item.name) for item in recent)))
                print("\nRecentes:")
                print(
                    f"{'Nº':>3} {'AUDITORIA':<{audit_width}}  {'CONCLUSÃO LOCAL':<16}  "
                    f"{'SITUAÇÃO':<29}  REPROCESSAMENTO"
                )
                print(
                    f"{'---':>3} {'-' * audit_width}  {'-' * 16}  "
                    f"{'-' * 29}  {'-' * 16}"
                )
                for index, audit_root in enumerate(recent, 1):
                    usability._history_row(index, audit_root, audit_width)
            else:
                print("\nNenhum AUD com audit.db encontrado nesta raiz.")

            print("\nI. Informar Audit ID")
            print("G. Gerenciar / excluir auditorias")
            print("V. Voltar")
            raw = input("Escolha: ").strip().upper()
            if raw == "V":
                return None
            if raw == "G":
                management._management_menu(console_module, state)
                console_module.render_header(state)
                continue
            if raw == "I":
                audit_id = input("Audit ID (AUD-*) ou V para cancelar: ").strip().upper()
                if audit_id == "V":
                    state.error = ""
                    continue
                candidate = Path(state.audits_root) / audit_id
                if audit_id.startswith("AUD-") and (candidate / "audit.db").is_file():
                    state.error = ""
                    return audit_id
                state.error = f"AUD não encontrado em {state.audits_root}: {audit_id or '<vazio>'}"
                continue
            try:
                selected = int(raw) - 1
            except ValueError:
                state.error = "opção de auditoria inválida"
                continue
            if 0 <= selected < min(len(audits), 20):
                state.error = ""
                return audits[selected].name
            state.error = "opção de auditoria inválida"

    return choose_audit


def install(console_module: ModuleType) -> None:
    """Install after the existing UI/usability layers."""
    if getattr(console_module, "_rasai_operator_navigation_refinements", False):
        return

    _repair_service_toggle_domains()

    from rasai import console_navigation as navigation
    from rasai import console_ui_catalog as catalog
    from rasai import console_ui_refactor as refactor

    capability_menu = _capability_menu_factory(catalog)
    catalog.capability_menu = capability_menu
    # console_ui_refactor imports capability_menu by value.
    refactor.capability_menu = capability_menu
    navigation._choose_audit = _choose_audit_factory(console_module)

    console_module._rasai_operator_navigation_refinements = True
