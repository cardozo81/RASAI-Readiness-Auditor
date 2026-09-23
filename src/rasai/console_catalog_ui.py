"""Rendering/navigation for the interactive audit catalog."""
from __future__ import annotations

from types import ModuleType
import os
from typing import Any

from rasai.audit_catalog import AI_NONE, AI_OPTIONAL, AI_REQUIRED, CATALOGS, AuditCatalog
from rasai.configuration_value_labels import configuration_csv_info, configuration_value_info
from rasai.console_ui import CYAN, DIM, RED, YELLOW, paint
from rasai.console_ui_catalog import CORE_IDS, badge, capability_specs, configuration_id, info, origin_for, section, variable_editor
from rasai.console_catalog_plan import (
    _ai_provider,
    ai_execution_enabled,
    ai_optional,
    ai_provider_readiness,
    ai_required,
    catalog_status,
    deselect_catalog,
    execution_ready,
    is_selected,
    raw_capability_status,
    select_catalog,
    set_ai_execution_enabled,
)

_HANDLER_CHOICES = {
    "CAT-04": "6", "CAT-05": "T", "CAT-06": "11", "CAT-07": "11",
    "CAT-08": "13", "CAT-09": "5",
}


def _capability_by_key(key: str) -> Any:
    from rasai.console_ui_catalog import CAPABILITIES
    return next((item for item in CAPABILITIES if item.key == key), None)


def _related_specs(catalog: AuditCatalog) -> tuple[Any, ...]:
    by_name: dict[str, Any] = {}
    for key in catalog.capability_ids:
        for spec in capability_specs(key):
            by_name[str(spec.name)] = spec
    return tuple(sorted(by_name.values(), key=lambda spec: str(spec.name).casefold()))


def _ai_summary(state: Any, selected: tuple[AuditCatalog, ...]) -> tuple[str, tuple[str, ...]]:
    optional = tuple(item for item in selected if item.ai_mode == AI_OPTIONAL)
    required = tuple(item for item in selected if item.ai_mode == AI_REQUIRED)
    lines: list[str] = []
    if required:
        lines.append("Obrigatória: " + ", ".join(item.id for item in required))
    if optional:
        lines.append("Opcional: " + ", ".join(item.id for item in optional))
    if not required and not optional:
        return "SEM IA", ()
    provider = _ai_provider(state)
    ready, _ = ai_provider_readiness(state)
    if required:
        return (
            f"OBRIGATÓRIA ({provider})" if ready else "PENDÊNCIA DE FECHAMENTO",
            tuple(lines),
        )
    if not ai_execution_enabled(state):
        return "SEM IA (RECOMENDADO)", tuple(lines)
    if not ready:
        return "CONFIGURAR", tuple(lines)
    return f"COM IA ({provider})", tuple(lines)


def _render_context(state: Any, catalog: AuditCatalog) -> None:
    section("CONFIGURAÇÃO EFETIVA")
    info("URL / entrada", getattr(state, "target", "") or "<não informada>")
    info(
        "Device",
        configuration_value_info("RASAI_DEVICE_CONTEXT", getattr(state, "device", "mobile")),
    )
    info("Idioma / mercado", f"{getattr(state, 'language', '-')} / {getattr(state, 'market', '-')}")
    if catalog.id == "CAT-04":
        info(
            "Web Performance",
            configuration_value_info(
                "",
                "ON" if bool(getattr(state, "web_performance", False)) else "OFF",
            ),
        )
        info(
            "Field source",
            configuration_value_info(
                "RASAI_WEB_PERFORMANCE_FIELD_SOURCE",
                getattr(state, "field_source", "auto"),
            ),
        )
        info(
            "Lighthouse",
            configuration_csv_info(
                "RASAI_LIGHTHOUSE_CATEGORIES",
                getattr(state, "lighthouse_categories", "-"),
            ),
        )
    elif catalog.id == "CAT-05":
        queries = tuple(getattr(state, "search_queries", ()) or ())
        info("Termos SERP", "; ".join(queries) if queries else "<não configurados>")
        info("Região", getattr(state, "search_region", "") or "<não configurada>")
        info("Profundidade", getattr(state, "search_depth", 20))
        info(
            "Device SERP",
            configuration_value_info(
                "RASAI_DEVICE_CONTEXT",
                getattr(state, "search_device", "mobile"),
            ),
        )
        info(
            "Contexto YMYL IA",
            configuration_value_info(
                "SEARCH_YMYL_MODE",
                str(getattr(state, "search_ymyl_mode", "AUTO") or "AUTO").upper(),
            ),
        )
        status, detail = raw_capability_status(state, "google-search-console")
        info("GSC", status)
        if detail:
            print(paint(f"  {detail}", DIM))
    elif catalog.id == "CAT-06":
        info("Habilitado", "SIM" if bool(getattr(state, "synthetic_apdex", False)) else "NÃO")
        info("Threshold", getattr(state, "apdex_threshold", None) or "default")
        info("Amostras", getattr(state, "apdex_samples", "default"))
    elif catalog.id == "CAT-07":
        info("Habilitado", "SIM" if bool(getattr(state, "apdex_experience", False)) else "NÃO")
        info("Mix", getattr(state, "apdex_experience_device_mix", "default"))
        info(
            "Sessão",
            configuration_value_info(
                "RASAI_APDEX_EXPERIENCE_SESSION_MODE",
                getattr(state, "apdex_experience_session_mode", "cold"),
            ),
        )
        info(
            "KPM",
            configuration_value_info(
                "RASAI_APDEX_EXPERIENCE_KPM",
                getattr(state, "apdex_experience_kpm", "USER_ACTION_DURATION"),
            ),
        )
        info(
            "Escopo de erros",
            configuration_value_info(
                "RASAI_APDEX_EXPERIENCE_ERROR_SCOPE",
                getattr(state, "apdex_experience_error_scope", "first-party"),
            ),
        )
    elif catalog.id == "CAT-08":
        info("Habilitado", "SIM" if bool(getattr(state, "improvement_enabled", False)) else "NÃO")
    elif catalog.id == "CAT-09":
        info("Remediação conteúdo IA", "SIM" if bool(getattr(state, "content_remediation", False)) else "NÃO")
        info("Remediação técnica IA", "SIM" if bool(getattr(state, "technical_remediation", False)) else "NÃO")
    elif catalog.id == "CAT-10":
        truthy = {"1","true","yes","on","sim","s"}
        flag = lambda name, default="true": "SIM" if str(os.environ.get(name, default)).strip().casefold() in truthy else "NÃO"
        info("Modo", "PASSIVO")
        info("Headers / CSP / CORS", flag("RASAI_SECURITY_HEADERS"))
        info("Cookies", flag("RASAI_SECURITY_COOKIES"))
        info("Scripts / recursos", flag("RASAI_SECURITY_RESOURCES"))
        info("Third-party", flag("RASAI_SECURITY_THIRD_PARTY"))
        info("Runtime", flag("RASAI_SECURITY_RUNTIME_CORRELATION"))
        info("OSV", flag("RASAI_SECURITY_OSV"))
        info("CISA KEV", flag("RASAI_SECURITY_CISA_KEV"))
        info("MDN Observatory", "REUTILIZADO quando habilitado no catálogo canônico de padrões")


def _render_capabilities(state: Any, catalog: AuditCatalog) -> None:
    from rasai.console_ui_catalog import capability_status
    section("CAPACIDADES / FONTES")
    for key in catalog.capability_ids:
        capability = _capability_by_key(key)
        if capability is None:
            print(f"- {key}")
            continue
        status, detail = capability_status(state, capability)
        print(f"- {capability.label:<31} {badge(status)}")
        if detail:
            print(paint(f"  {detail}", DIM))


def catalog_menu(console_module: ModuleType, state: Any, catalog: AuditCatalog) -> None:
    while True:
        console_module.render_header(state)
        print(paint(f"INÍCIO > PREPARAR AUDITORIA > {catalog.id} {catalog.label.upper()}", CYAN, bold=True))
        status, detail = catalog_status(state, catalog)
        section("ESTADO")
        info("Catálogo", f"{catalog.id} · {catalog.label}")
        info("Readiness", badge(status))
        print(paint(detail, RED if status == "BLOQUEADO" else DIM))
        _render_capabilities(state, catalog)
        _render_context(state, catalog)
        section("USO DE IA")
        if not catalog.ai_uses:
            print("Este catálogo não ativa IA principal por si só.")
        else:
            for use in catalog.ai_uses:
                print(f"- {use.mode:<9} {use.label}: {use.purpose}")
            info("IA principal", _ai_provider(state))
            info("Uso nesta auditoria", "COM IA" if ai_execution_enabled(state) else "SEM IA")
            if catalog.ai_mode == AI_REQUIRED:
                info("Necessária para fechamento", "SIM")
                if not ai_execution_enabled(state):
                    print(
                        paint(
                            "  A auditoria pode executar sem IA; este catálogo permanecerá pendente para fechamento integral.",
                            DIM,
                        )
                    )
            elif not ai_execution_enabled(state):
                print(paint("  Execução sem IA é o default recomendado quando o catálogo tem apenas enriquecimento opcional.", DIM))
            if not ai_provider_readiness(state)[0]:
                print(
                    paint(
                        "  Provider/modelo podem ser ajustados no fluxo de Inteligência Artificial ou pelo atalho A da estimativa financeira.",
                        DIM,
                    )
                )
        section("RESULTADO ESPERADO")
        print(catalog.expected_result)
        specs = _related_specs(catalog)
        section("CONFIGURAÇÕES RELACIONADAS")
        if specs:
            from rasai import console_configuration_presentation as presentation
            for spec in specs:
                print(presentation.format_configuration_row(state, spec))
        else:
            print(paint("Nenhuma variável adicional obrigatória neste catálogo.", DIM))
        section("PERSISTÊNCIA")
        print("Variáveis editáveis usam sessão ou arquivo; secrets usam Windows/User e nunca entram no INI.")
        print("A seleção CAT-* pertence somente ao plano da próxima execução e ao snapshot do AUD.")
        section("AÇÕES")
        if _HANDLER_CHOICES.get(catalog.id):
            print("1. Configurar parâmetros próprios deste catálogo")
        if catalog.ai_mode == AI_OPTIONAL and ai_provider_readiness(state)[0] and not ai_required(state):
            toggle = "Executar sem IA (recomendado)" if ai_execution_enabled(state) else "Executar com IA"
            print(f"U. {toggle}")
        print("D. Remover este catálogo do plano")
        print("V. Voltar para o catálogo da auditoria")
        raw = input("Número/ID ou ação: ").strip().upper()
        if raw == "V":
            return
        if raw == "D":
            if deselect_catalog(state, catalog):
                state.error = ""
                return
            continue
        if raw == "U" and catalog.ai_mode == AI_OPTIONAL and ai_provider_readiness(state)[0] and not ai_required(state):
            set_ai_execution_enabled(state, not ai_execution_enabled(state))
            state.error = ""
            continue
        if raw == "1" and _HANDLER_CHOICES.get(catalog.id):
            console_module._configure(state, _HANDLER_CHOICES[catalog.id])
            continue
        spec = next((item for item in specs if configuration_id(item.name) == raw), None)
        if spec is not None:
            variable_editor(console_module, state, spec)
            continue
        state.error = "opção inválida neste catálogo"


def _preparation_menu_impl(console_module: ModuleType, state: Any, detailed: Any = None) -> str:
    del detailed
    while True:
        console_module.render_header(state)
        print(paint("INÍCIO > PREPARAR AUDITORIA", CYAN, bold=True))
        print(paint("Selecione um catálogo para incluí-lo no plano; suas opções abrem imediatamente.", DIM))
        section("ESCOPO")
        print(f"1. {CORE_IDS['input']}  Entrada                  : {getattr(state, 'target', '') or '<não informada>'}")
        print(f"2. {CORE_IDS['project']}  Projeto                  : {getattr(state, 'project', '') or '<auto>'}")
        print(f"3. {CORE_IDS['device']}  Device                   : {getattr(state, 'device', 'mobile')}")
        print(f"4. {CORE_IDS['language_market']}  Idioma / mercado         : {getattr(state, 'language', '-')} / {getattr(state, 'market', '-')}")
        try:
            from rasai.time_contract import configured_presentation_timezone
            timezone = configured_presentation_timezone()
        except (ImportError, ValueError):
            timezone = "<inválido>"
        print(f"5. {CORE_IDS['timezone']}  Timezone apresentação    : {timezone}")
        section("CATÁLOGO DA AUDITORIA")
        mapping: dict[str, AuditCatalog] = {}
        for index, catalog in enumerate(CATALOGS, 6):
            mapping[str(index)] = catalog
            status, detail = catalog_status(state, catalog)
            marker = "X" if is_selected(state, catalog.id) else " "
            print(f"{index:2d}. [{marker}] {catalog.id} {catalog.label:<43} {badge(status)}")
            if marker == "X" and status in {"BLOQUEADO", "APTO COM LIMITAÇÕES"}:
                print(paint(f"     {detail}", RED if status == "BLOQUEADO" else YELLOW))
        selected = tuple(item for item in CATALOGS if is_selected(state, item.id))
        plan_state, plan_detail = execution_ready(console_module, state)
        ai_state, ai_lines = _ai_summary(state, selected)
        section("PLANO DA PRÓXIMA AUDITORIA")
        print(f"Catálogos selecionados     : {len(selected)}")
        print(f"Estado                     : {badge(plan_state)} | {plan_detail}")
        print(f"IA                         : {ai_state}")
        for line in ai_lines:
            print(paint(f"  {line}", DIM))
        if (ai_required(state) or ai_optional(state)) and ai_provider_readiness(state)[0]:
            print(
                paint(
                    "  Antes da execução, a tela financeira permitirá C=usar IA, N=não usar IA, A=ajustar IA ou V=voltar.",
                    DIM,
                )
            )
        section("EXECUÇÃO / ARMAZENAMENTO")
        print(f"16. {CORE_IDS['audits_root']}  Raiz das auditorias        : {getattr(state, 'audits_root', 'audits')}")
        section("AÇÕES")
        print(f"R. Executar auditoria        [{badge(plan_state)}]")
        if ai_optional(state) and not ai_required(state) and ai_provider_readiness(state)[0]:
            toggle = "Executar sem IA (recomendado)" if ai_execution_enabled(state) else "Executar com IA"
            print(f"U. {toggle}")
        print("M. Ver linha de comando")
        print("S. Salvar configuração no arquivo [SEM SECRETS]\nL. Carregar configuração de AUD [NOVA EXECUÇÃO]\nV. Voltar ao início")
        raw = input("Escolha: ").strip().upper()
        if raw == "V":
            return "V"
        if raw == "R":
            if plan_state == "BLOQUEADO":
                state.error = plan_detail
                continue
            return "R"
        if raw == "U" and ai_optional(state) and not ai_required(state) and ai_provider_readiness(state)[0]:
            set_ai_execution_enabled(state, not ai_execution_enabled(state))
            state.error = ""
            continue
        if raw == "M":
            from rasai.execution_commands import audit_plan, show

            show(
                audit_plan(state),
                state.audits_root,
                artifact_root=state.audits_root,
            )
            state.error = ""
            continue
        if raw in {"S", "L"}:
            return raw
        core = {"1": "1", "2": "2", "3": "3", "4": "9", "5": "12", "16": "10"}
        if raw in core:
            console_module._configure(state, core[raw])
            continue
        catalog = mapping.get(raw)
        if catalog is not None:
            if not is_selected(state, catalog.id):
                select_catalog(state, catalog)
            catalog_menu(console_module, state, catalog)
            continue
        state.error = "opção inválida em Preparar auditoria"


def preparation_menu(console_module: ModuleType, state: Any, detailed: Any = None) -> str:
    """Render preparation without allowing the top-level input capture to hijack nested prompts."""
    from rasai import console_ui_refactor as refactor

    refactor._set_meta(state, "preparation_active", True)
    try:
        return _preparation_menu_impl(console_module, state, detailed)
    finally:
        refactor._drop_meta(state, "preparation_active")
