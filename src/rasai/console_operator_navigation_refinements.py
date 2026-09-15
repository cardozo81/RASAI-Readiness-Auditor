"""Final operator-navigation refinements for the interactive console.

Presentation/navigation only:
- make capability context help actionable instead of a disposable pause screen;
- never swallow a configuration ID typed from contextual help;
- allow V to cancel manual AUD-ID entry without emitting an invalid-AUD error;
- repair closed boolean metadata for service toggles when a later catalog overlay has
  preserved runtime validation but accidentally degraded the UI type/domain;
- keep Search Intelligence/SERP and Google Search Console as independent capabilities,
  with independent readiness states and dependency lists.
"""
from __future__ import annotations

from dataclasses import replace
import os
from pathlib import Path
from types import ModuleType
from typing import Any

from rasai.console_ui import CYAN, DIM, RED, YELLOW, paint


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


def _serp_spec(spec: Any) -> bool:
    name = str(spec.name).upper()
    if name.startswith("RASAI_SERP"):
        return True
    try:
        from rasai.search_intelligence.provider_catalog import serp_provider_key_envs

        return name in set(serp_provider_key_envs())
    except ImportError:
        return name in {
            "RASAI_SERPAPI_API_KEY",
            "RASAI_ZENSERP_API_KEY",
            "RASAI_SCRAPINGDOG_API_KEY",
        }


def _gsc_spec(spec: Any) -> bool:
    name = str(spec.name).upper()
    return name.startswith("RASAI_GSC_") or name.startswith("RASAI_GOOGLE_SEARCH_CONSOLE_")


def _search_intelligence_status(state: Any) -> tuple[str, str]:
    """Represent request intent separately from provider configuration readiness."""
    from rasai.console_search_intelligence import validate_search_readiness
    from rasai.search_intelligence.config import SerpRuntimeConfig
    from rasai.search_intelligence.provider_catalog import serp_provider_registration

    try:
        config = SerpRuntimeConfig.from_environment()
    except ValueError as exc:
        return "CONFIGURAR", f"configuração SERP inválida: {exc}"

    queries = tuple(getattr(state, "search_queries", ()) or ())
    if not queries:
        if config.mode == "disabled":
            return "DESABILITADO", "RASAI_SERP_MODE=disabled; observação SERP está desabilitada"

        registration = serp_provider_registration(config.provider)
        if config.mode == "live" and registration is not None:
            key_present = bool((os.environ.get(registration.key_env) or "").strip())
            provider_detail = (
                f"provider {registration.id} configurado"
                if key_present
                else f"provider {registration.id} selecionado; credencial ainda não configurada"
            )
        elif config.mode == "fixture":
            provider_detail = "modo fixture configurado"
        else:
            provider_detail = f"modo {config.mode}; provider {config.provider}"
        return "NÃO SOLICITADO", f"{provider_detail}; nenhum termo SERP definido nesta execução"

    ready, detail = validate_search_readiness(state)
    return ("APTO" if ready else "CONFIGURAR"), detail


def _gsc_status(state: Any) -> tuple[str, str]:
    """Resolve local GSC readiness without conflating it with SERP readiness."""
    from rasai.gsc_oauth import (
        MODE_INCOMPLETE,
        MODE_INVALID as OAUTH_INVALID,
        credential_state,
    )
    from rasai.gsc_scope import (
        GSC_SITE_URL_ENV,
        MODE_AUTO,
        MODE_DISABLED,
        MODE_INVALID,
        MODE_REQUIRED,
        gsc_property_covers_url,
        gsc_request_mode,
    )

    mode = gsc_request_mode(os.environ)
    if mode == MODE_INVALID:
        return "CONFIGURAR", "RASAI_GSC_ENABLED possui valor inválido"
    if mode == MODE_DISABLED:
        return "DESABILITADO", "Google Search Console foi desabilitado explicitamente"

    oauth = credential_state(os.environ)
    site_url = (os.environ.get(GSC_SITE_URL_ENV) or "").strip()
    required = mode == MODE_REQUIRED

    if oauth.mode == OAUTH_INVALID:
        return "CONFIGURAR", oauth.detail or "credencial OAuth do Google Search Console é inválida"
    if oauth.mode == MODE_INCOMPLETE:
        return "CONFIGURAR", oauth.detail or "credenciais OAuth do Google Search Console estão incompletas"

    missing: list[str] = []
    if not oauth.configured:
        missing.append("OAuth")
    if not site_url:
        missing.append("property")
    if missing:
        state_label = "CONFIGURAR" if required else "NÃO CONFIGURADO"
        mode_detail = "obrigatório" if required else "automático/opcional"
        return state_label, f"GSC {mode_detail}: falta " + " + ".join(missing)

    target = str(getattr(state, "target", "") or "").strip()
    if not target:
        return (
            "AUTOMÁTICO" if mode == MODE_AUTO else "APTO",
            "OAuth e property configurados; informe a URL para validar se a property cobre o alvo",
        )

    try:
        covers = gsc_property_covers_url(site_url, target)
    except ValueError as exc:
        return "CONFIGURAR", f"property GSC inválida: {exc}"

    if not covers:
        if required:
            return "CONFIGURAR", "GSC obrigatório, mas a property configurada não cobre a URL auditada"
        return "NÃO APLICÁVEL", "property GSC não cobre esta URL; em modo automático o GSC não será exigido"

    return (
        "APTO",
        "OAuth e property configurados; o escopo cobre a URL. Validade/permissão são confirmadas pela API do Google",
    )


def _install_search_capability_split() -> None:
    """Split SERP and GSC in the preparation UI without changing either runtime."""
    from rasai import console_provider_environment as facade
    from rasai import console_ui_catalog as catalog
    from rasai import console_ui_refactor as refactor

    if getattr(catalog, "_rasai_search_gsc_capability_split", False):
        return

    original_specs = catalog.capability_specs
    original_status = catalog.capability_status

    def capability_specs(capability: str) -> tuple[Any, ...]:
        if capability == "search-intelligence":
            return tuple(spec for spec in facade.refresh_specs() if _serp_spec(spec))
        if capability == "google-search-console":
            return tuple(spec for spec in facade.refresh_specs() if _gsc_spec(spec))
        if capability == "observability":
            return tuple(spec for spec in original_specs(capability) if not _gsc_spec(spec))
        return original_specs(capability)

    def capability_status(state: Any, capability: Any) -> tuple[str, str]:
        if capability.key == "search-intelligence":
            return _search_intelligence_status(state)
        if capability.key == "google-search-console":
            return _gsc_status(state)
        return original_status(state, capability)

    capabilities: list[Any] = []
    gsc_added = False
    for item in catalog.CAPABILITIES:
        if item.key == "search-intelligence":
            item = catalog.CapabilityUI(
                "search-intelligence",
                "Search Intelligence / SERP",
                "Observação SERP por termos desta execução, com provider, limites e compatibilidade validados antes da chamada.",
                item.handler_choice,
                item.automatic,
                item.derived,
            )
            capabilities.append(item)
            capabilities.append(
                catalog.CapabilityUI(
                    "google-search-console",
                    "Google Search Console",
                    "Search Analytics, sitemaps e URL Inspection para property autenticada que cubra a URL auditada.",
                )
            )
            gsc_added = True
            continue
        capabilities.append(item)
    if not gsc_added:
        capabilities.append(
            catalog.CapabilityUI(
                "google-search-console",
                "Google Search Console",
                "Search Analytics, sitemaps e URL Inspection para property autenticada que cubra a URL auditada.",
            )
        )

    catalog.CAPABILITIES = tuple(capabilities)
    catalog.capability_specs = capability_specs
    catalog.capability_status = capability_status
    catalog._STATUS_COLORS["NÃO SOLICITADO"] = DIM
    catalog._STATUS_COLORS["NÃO CONFIGURADO"] = YELLOW

    # console_ui_refactor imports these names by value; rebind the already imported
    # references so the preparation screen sees the split immediately in this process.
    refactor.CAPABILITIES = catalog.CAPABILITIES
    refactor.capability_specs = capability_specs
    refactor.capability_status = capability_status

    catalog._rasai_search_gsc_capability_split = True


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

    _install_search_capability_split()

    capability_menu = _capability_menu_factory(catalog)
    catalog.capability_menu = capability_menu
    # console_ui_refactor imports capability_menu by value.
    refactor.capability_menu = capability_menu
    navigation._choose_audit = _choose_audit_factory(console_module)

    console_module._rasai_operator_navigation_refinements = True
