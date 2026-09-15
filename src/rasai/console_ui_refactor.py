"""Final information architecture for the local interactive console.

Only console presentation/configuration UX is changed. Audit execution, routing, scoring,
retries, quarantine, fulfillment and report generation remain owned by existing code.
"""
from __future__ import annotations

import builtins
from contextlib import redirect_stdout
import io
import sys
from types import ModuleType
from typing import Any, Callable

from rasai.console_ui import CYAN, DIM, RED, paint
from rasai.console_ui_catalog import (
    CAPABILITIES,
    CORE_IDS,
    badge,
    capability_menu,
    capability_specs,
    capability_status,
    catalog_menu,
    configuration_id,
    section,
    variable_editor,
)

# Console State classes are slot-based. Presentation metadata must therefore remain
# outside the canonical state object so the UI never changes the runtime state contract.
# Keep a strong identity reference with each bucket: Python may reuse id() after an
# object is released, and UI metadata must never leak to a later State instance.
_SESSION_META: dict[int, tuple[Any, dict[str, Any]]] = {}


def _bucket(state: Any, *, create: bool = False) -> dict[str, Any] | None:
    key = id(state)
    entry = _SESSION_META.get(key)
    if entry is not None and entry[0] is state:
        return entry[1]
    if entry is not None:
        _SESSION_META.pop(key, None)
    if not create:
        return None
    metadata: dict[str, Any] = {}
    _SESSION_META[key] = (state, metadata)
    return metadata


def _meta(state: Any) -> dict[str, Any]:
    bucket = _bucket(state, create=True)
    assert bucket is not None
    return bucket


def _get_meta(state: Any, key: str, default: Any = None) -> Any:
    bucket = _bucket(state)
    return default if bucket is None else bucket.get(key, default)


def _set_meta(state: Any, key: str, value: Any) -> None:
    _meta(state)[key] = value


def _drop_meta(state: Any, key: str) -> None:
    bucket = _bucket(state)
    if bucket is None:
        return
    bucket.pop(key, None)
    if not bucket:
        _SESSION_META.pop(id(state), None)


def _config_view(state: Any) -> str:
    return str(_get_meta(state, "config_view", "integrations") or "integrations")


def _set_config_view(state: Any, value: str) -> None:
    _set_meta(state, "config_view", value)


def _mix_inherited(state: Any) -> bool | None:
    value = _get_meta(state, "apdex_mix_inherited", None)
    return None if value is None else bool(value)


def _set_mix_inherited(state: Any, value: bool) -> None:
    _set_meta(state, "apdex_mix_inherited", bool(value))


def _fingerprint(state: Any):
    from rasai.console_settings import configuration_fingerprint

    return configuration_fingerprint(state)


def _derived_mix(device: str) -> str:
    value = str(device).casefold()
    if value == "desktop":
        return "mobile=0,desktop=100,tablet=0"
    if value == "both":
        return "mobile=60,desktop=40,tablet=0"
    return "mobile=100,desktop=0,tablet=0"


def _ensure_mix(state: Any) -> None:
    if not hasattr(state, "apdex_experience_device_mix"):
        return
    try:
        from rasai.m25_cli import DEFAULT_UX_DEVICE_MIX
    except ImportError:
        return
    current = str(getattr(state, "apdex_experience_device_mix", "") or "")
    inherited = _mix_inherited(state)
    if inherited is None:
        inherited = not current or current == DEFAULT_UX_DEVICE_MIX
        _set_mix_inherited(state, inherited)
    if inherited:
        state.apdex_experience_device_mix = _derived_mix(getattr(state, "device", "mobile"))


def _profile_text(state: Any) -> str:
    try:
        from rasai.console_execution_profiles import active_profile

        profile = active_profile(state)
        if profile is None:
            return "Personalizado / sem preset ativo"
        return str(getattr(profile, "label", None) or getattr(profile, "profile_id", None) or profile)
    except (ImportError, AttributeError, TypeError):
        return "Personalizado / sem preset ativo"


def _device_results(state: Any) -> tuple[str, str]:
    value = str(getattr(state, "device", "mobile")).casefold()
    mobile = "INCLUÍDO" if value in {"mobile", "both"} else "NÃO APLICÁVEL"
    desktop = "INCLUÍDO" if value in {"desktop", "both"} else "NÃO APLICÁVEL"
    return mobile, desktop


def _overall(console: ModuleType, state: Any) -> tuple[str, str]:
    try:
        ready, reason = console._execution_readiness(state)
    except (OSError, ValueError, UnicodeError) as exc:
        return "CONFIGURAR", str(exc)
    return ("APTO" if ready else "CONFIGURAR"), reason


def preparation_menu(console: ModuleType, state: Any, detailed: Callable[[Any], str]) -> str:
    del detailed
    _set_meta(state, "preparation_active", True)
    _ensure_mix(state)
    try:
        while True:
            console.render_header(state)
            print(paint("INÍCIO > PREPARAR AUDITORIA", CYAN, bold=True))
            print(paint("Números abrem parâmetros/resultados; letras executam ações ou navegam.", DIM))

            section("PERFIL DA PRÓXIMA AUDITORIA")
            print(f"1. {CORE_IDS['profile']}  Perfil base              : {_profile_text(state)}")

            section("ESCOPO")
            print(f"2. {CORE_IDS['input']}  Entrada                  : {getattr(state, 'target', '') or '<não informada>'}")
            print(f"3. {CORE_IDS['project']}  Projeto                  : {getattr(state, 'project', '') or '<auto>'}")
            print(f"4. {CORE_IDS['device']}  Device                   : {getattr(state, 'device', 'mobile')}")
            print(f"5. {CORE_IDS['language_market']}  Idioma / mercado         : {getattr(state, 'language', '-')} / {getattr(state, 'market', '-')}")
            try:
                from rasai.time_contract import configured_presentation_timezone

                timezone = configured_presentation_timezone()
            except (ImportError, ValueError):
                timezone = "<inválido>"
            print(f"6. {CORE_IDS['timezone']}  Timezone apresentação    : {timezone}")

            section("ANÁLISES / RESULTADOS")
            mobile_result, desktop_result = _device_results(state)
            print(f"  — {'Relatório Mobile':<31} {badge(mobile_result)}")
            print(f"  — {'Relatório Desktop':<31} {badge(desktop_result)}")
            print(paint("    Derivados do Device; não possuem seleção independente.", DIM))
            number, mapping = 7, {}
            for capability in CAPABILITIES:
                status, detail = capability_status(state, capability)
                editable = bool(capability_specs(capability.key))
                prefix = "—" if capability.automatic and capability.handler_choice is None and not editable else f"{number}."
                if prefix != "—":
                    mapping[str(number)] = capability
                    number += 1
                print(f"{prefix:>3} {capability.label:<31} {badge(status)}")
                if status in {"CONFIGURAR", "APTO COM LIMITAÇÕES"}:
                    print(paint(f"    {detail}", RED if status == "CONFIGURAR" else CYAN))

            section("RESULTADOS SISTÊMICOS")
            print(paint("Visão geral · Readiness SARI · Metodologia de scoring · Contexto de captura · Uso de IA · Referências/metodologia", DIM))
            print(paint("Gerados pelo contrato do relatório; não possuem seleção independente.", DIM))

            section("EXECUÇÃO / ARMAZENAMENTO")
            storage = number
            print(f"{storage}. {CORE_IDS['audits_root']}  Raiz das auditorias        : {getattr(state, 'audits_root', 'audits')}")

            status, reason = _overall(console, state)
            section("AÇÕES")
            print(f"R. Executar auditoria        [{badge(status)}] {reason}")
            print(
                "S. Salvar configuração no arquivo [SEM SECRETS]\n"
                "L. Carregar configuração de AUD [NOVA EXECUÇÃO]\n"
                "E. Integrações e serviços\n"
                "A. Todas as configurações\n"
                "H. Ajuda / custos\n"
                "C. Histórico / relatórios consolidados [OFFLINE]\n"
                "V. Voltar ao início\n"
                "Q. Sair"
            )
            raw = input("Escolha: ").strip().upper()
            if raw == "V":
                return "V"
            if raw in {"E", "A"}:
                _set_config_view(state, "integrations" if raw == "E" else "all")
                return "E"
            if raw in {"R", "S", "L", "H", "C", "Q"}:
                return raw
            core = {
                "1": "F",
                "2": "1",
                "3": "2",
                "4": "3",
                "5": "9",
                "6": "12",
                str(storage): "10",
            }
            if raw in core:
                return core[raw]
            capability = mapping.get(raw)
            if capability is not None:
                choice = capability_menu(console, state, capability)
                if choice is not None:
                    return choice
                continue
            state.error = "opção inválida em Preparar auditoria"
    finally:
        _drop_meta(state, "preparation_active")


def _install_search_persistence() -> None:
    from rasai import console_settings as settings

    if getattr(settings, "_rasai_search_console_persistence", False):
        return
    old_values, old_assign = settings._state_values, settings._assign

    def values(state: Any):
        result = old_values(state)
        if _mix_inherited(state):
            result.get("synthetic_apdex_experience", {}).pop("device_mix", None)
        # The settings helper is shared by narrower State variants in tests and tools.
        # Only states that actually expose Search Intelligence receive this section.
        if hasattr(state, "search_queries"):
            result["search_intelligence"] = {
                "queries": "; ".join(tuple(getattr(state, "search_queries", ()) or ())),
                "depth": str(int(getattr(state, "search_depth", 20))),
                "region": str(getattr(state, "search_region", "") or ""),
                "device": str(getattr(state, "search_device", "mobile") or "mobile"),
                "competitive": "true" if bool(getattr(state, "search_competitive", True)) else "false",
            }
        return result

    def assign(state: Any, section_name: str, option: str, raw: str):
        if section_name != "search_intelligence":
            return old_assign(state, section_name, option, raw)
        if not hasattr(state, "search_queries"):
            return None
        from rasai.console_search_intelligence import parse_search_terms

        if option == "queries":
            state.search_queries = parse_search_terms(raw)
        elif option == "depth":
            value = int(raw)
            if value <= 0:
                raise ValueError("search_intelligence.depth: use inteiro > 0")
            state.search_depth = value
        elif option == "region":
            state.search_region = raw.strip()
        elif option == "device":
            value = raw.strip().casefold()
            if value not in {"mobile", "desktop"}:
                raise ValueError("search_intelligence.device: use mobile ou desktop")
            state.search_device = value
        elif option == "competitive":
            state.search_competitive = settings._parse_bool(raw)
        return None

    settings._state_values = values
    settings._assign = assign
    settings._rasai_search_console_persistence = True


def _install_variable_editor(console: ModuleType) -> None:
    from rasai import console_provider_environment as env

    if getattr(env, "_rasai_canonical_variable_editor", False):
        return
    env._variable_menu = lambda state, spec: variable_editor(console, state, spec)
    env._rasai_canonical_variable_editor = True


def _install_environment_router(console: ModuleType) -> None:
    def menu(state: Any):
        view = _config_view(state)
        _set_config_view(state, "integrations")
        if view == "ai":
            catalog_menu(console, state, view="ai", title="INTELIGÊNCIA ARTIFICIAL")
        elif view == "all":
            catalog_menu(console, state, view="all", title="TODAS AS CONFIGURAÇÕES")
        else:
            catalog_menu(console, state, view="integrations", title="INTEGRAÇÕES E SERVIÇOS")

    console._environment_menu = menu
    console._rasai_configuration_router = True


def _install_top_level(console: ModuleType) -> None:
    if getattr(console, "_rasai_top_level_information_architecture", False):
        return
    original = console._menu

    class Capture(io.StringIO):
        def isatty(self):
            probe = getattr(sys.stdout, "isatty", None)
            return bool(probe()) if callable(probe) else False

    def menu(state: Any) -> str:
        original_input, real_stdout, buffer, rendered = builtins.input, sys.stdout, Capture(), False

        def flush():
            text = buffer.getvalue()
            if text:
                real_stdout.write(text)
                real_stdout.flush()
                buffer.seek(0)
                buffer.truncate(0)
            return text

        def read(prompt=""):
            nonlocal rendered
            captured = buffer.getvalue()
            if bool(_get_meta(state, "preparation_active", False)):
                flush()
                return original_input(prompt)
            if (
                not rendered
                and prompt.strip().casefold().startswith("escolha")
                and "INÍCIO\n" in captured
                and "PREPARAR AUDITORIA" not in captured
            ):
                prefix = captured.split("INÍCIO\n", 1)[0]
                buffer.seek(0)
                buffer.truncate(0)
                real_stdout.write(
                    prefix
                    + "INÍCIO\n\n"
                    + f"Projeto atual : {getattr(state, 'project', '') or '<auto>'}\n"
                    + f"Alvo          : {getattr(state, 'target', '') or '<não informado>'}\n"
                )
                if getattr(state, "audit_id", ""):
                    real_stdout.write(f"Último AUD    : {state.audit_id}\n")
                real_stdout.write(
                    "\n1. Preparar auditoria\n"
                    "2. Auditorias / histórico\n"
                    "3. Relatórios consolidados\n"
                    "4. Inteligência Artificial\n"
                    "5. Integrações e serviços\n"
                    "6. Todas as configurações\n"
                    "7. Sistema / restaurar padrões\n"
                    "\nH. Ajuda\n"
                    "Q. Sair\n"
                    + prompt
                )
                real_stdout.flush()
                rendered = True
                raw = original_input("").strip().upper()
                mapping = {"1": "1", "2": "2", "3": "3", "4": "4", "5": "4", "6": "4", "7": "5", "H": "?", "Q": "Q"}
                if raw in {"4", "5", "6"}:
                    _set_config_view(state, {"4": "ai", "5": "integrations", "6": "all"}[raw])
                return mapping.get(raw, raw)
            flush()
            return original_input(prompt)

        builtins.input = read
        try:
            with redirect_stdout(buffer):
                result = original(state)
            flush()
            return result
        finally:
            builtins.input = original_input

    console._menu = menu
    console._rasai_top_level_information_architecture = True


def _install_configure_persistence(console: ModuleType) -> None:
    if getattr(console, "_rasai_configure_persistence_prompt", False):
        return
    original, old_mark = console._configure, console.mark_dirty

    def configure(state: Any, choice: str):
        before = _fingerprint(state)
        _ensure_mix(state)
        before_mix = str(getattr(state, "apdex_experience_device_mix", "") or "")
        mix_was_inherited = _mix_inherited(state)
        original(state, choice)
        if choice == "3" and _mix_inherited(state) and hasattr(state, "apdex_experience_device_mix"):
            state.apdex_experience_device_mix = _derived_mix(getattr(state, "device", "mobile"))
        if choice == "11" and mix_was_inherited and hasattr(state, "apdex_experience_device_mix"):
            after_mix = str(getattr(state, "apdex_experience_device_mix", "") or "")
            _set_mix_inherited(state, after_mix == before_mix)
        if choice == "F" or _fingerprint(state) == before:
            return
        print("\nDESTINO DA ALTERAÇÃO")
        print("1. Manter somente nesta sessão")
        print("2. Manter na sessão e salvar no arquivo de configuração")
        while True:
            destination = input("Escolha: ").strip().upper()
            if destination in {"1", "2"}:
                break
            print(paint("Opção inválida.", RED, bold=True))
        if destination == "2" and console._save_configuration(state):
            _set_meta(state, "saved_fingerprint", _fingerprint(state))

    def mark_dirty(state: Any, value: bool = True):
        saved = _get_meta(state, "saved_fingerprint", None)
        if value and saved == _fingerprint(state):
            _drop_meta(state, "saved_fingerprint")
            return old_mark(state, False)
        return old_mark(state, value)

    console._configure = configure
    console.mark_dirty = mark_dirty
    console._rasai_configure_persistence_prompt = True


def install() -> None:
    from rasai import interactive_console as console

    if getattr(console, "_rasai_ui_refactor_installed", False):
        return
    _install_search_persistence()
    _install_variable_editor(console)
    _install_environment_router(console)
    from rasai import console_navigation as navigation

    navigation._preparation_menu = lambda module, state, detailed: preparation_menu(module, state, detailed)
    _install_configure_persistence(console)
    _install_top_level(console)
    console._rasai_ui_refactor_installed = True


# Testable aliases for the presentation contract.
_capability_specs = capability_specs
_derived_apdex_mix = _derived_mix
_device_result_states = _device_results
_preparation_menu = preparation_menu
_install_top_level_menu = _install_top_level
