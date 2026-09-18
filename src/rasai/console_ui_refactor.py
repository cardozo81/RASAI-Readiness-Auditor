"""Final information architecture helpers for the local interactive console.

The public preparation surface is catalog-driven. This module owns shared console-only
presentation/configuration behavior (navigation, persistence and canonical editors) and
intentionally contains no legacy execution-profile or ``ANÁLISES / RESULTADOS`` screen.
Audit execution, routing, scoring, retries, quarantine, fulfillment and report generation
remain owned by existing runtime code.
"""
from __future__ import annotations

import builtins
from contextlib import redirect_stdout
import io
import math
import sys
from types import ModuleType
from typing import Any

from rasai.console_ui import CYAN, DIM, RED, paint
from rasai.console_ui_catalog import (
    CAPABILITIES,
    capability_specs,
    capability_status,
    catalog_menu,
    configuration_id,
    variable_editor,
)

# Console State classes are slot-based. Presentation metadata must therefore remain
# outside the canonical state object so the UI never changes the runtime state contract.
_SESSION_META: dict[int, tuple[Any, dict[str, Any]]] = {}

_SEARCH_OLD_NOTICE = (
    "Termos são dados desta sessão de execução; não são variáveis de ambiente "
    "e não são gravados no rasai-console.ini."
)
_SEARCH_NOTICE = (
    "Termos são inputs da próxima execução e não são variáveis de ambiente. "
    "Permanecem na sessão; ao usar Salvar configuração, os inputs não sensíveis "
    "de Search também são gravados no rasai-console.ini."
)


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


def _device_results(state: Any) -> tuple[str, str]:
    """Compatibility helper for the Device-derived report projection/tests."""
    value = str(getattr(state, "device", "mobile")).casefold()
    mobile = "INCLUÍDO" if value in {"mobile", "both"} else "NÃO APLICÁVEL"
    desktop = "INCLUÍDO" if value in {"desktop", "both"} else "NÃO APLICÁVEL"
    return mobile, desktop


def preparation_menu(console: ModuleType, state: Any, detailed: Any = None) -> str:
    """Delegate to the canonical catalog workflow; no legacy preparation UI remains."""
    from rasai.console_catalog_workflow import preparation_menu as catalog_preparation_menu

    _ensure_mix(state)
    return catalog_preparation_menu(console, state, detailed)


def _install_search_persistence() -> None:
    from rasai import console_settings as settings

    if getattr(settings, "_rasai_search_console_persistence", False):
        return
    old_values, old_assign = settings._state_values, settings._assign

    def values(state: Any):
        result = old_values(state)
        if _mix_inherited(state):
            result.get("synthetic_apdex_experience", {}).pop("device_mix", None)
        if hasattr(state, "search_queries"):
            result["search_intelligence"] = {
                "queries": "; ".join(tuple(getattr(state, "search_queries", ()) or ())),
                "depth": str(int(getattr(state, "search_depth", 20))),
                "region": str(getattr(state, "search_region", "") or ""),
                "device": str(getattr(state, "search_device", "mobile") or "mobile"),
                "competitive": "true" if bool(getattr(state, "search_competitive", True)) else "false",
                "compare_content": "true" if bool(getattr(state, "search_compare_content", False)) else "false",
                "max_content_pages": str(int(getattr(state, "search_max_content_pages", 3))),
                "content_timeout_seconds": str(float(getattr(state, "search_content_timeout_seconds", 10.0))),
                "content_max_bytes": str(int(getattr(state, "search_content_max_bytes", 2_000_000))),
                "content_max_redirects": str(int(getattr(state, "search_content_max_redirects", 5))),
                "ai_competitive": "true" if bool(getattr(state, "search_ai_competitive", False)) else "false",
                "ymyl_mode": str(getattr(state, "search_ymyl_mode", "AUTO") or "AUTO").upper(),
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
        elif option == "compare_content":
            state.search_compare_content = settings._parse_bool(raw)
        elif option == "max_content_pages":
            value = int(raw)
            if value < 0:
                raise ValueError("search_intelligence.max_content_pages: use inteiro >= 0")
            state.search_max_content_pages = value
        elif option == "content_timeout_seconds":
            value = float(raw)
            if not math.isfinite(value) or value <= 0:
                raise ValueError("search_intelligence.content_timeout_seconds: use número finito > 0")
            state.search_content_timeout_seconds = value
        elif option == "content_max_bytes":
            value = int(raw)
            if value <= 0:
                raise ValueError("search_intelligence.content_max_bytes: use inteiro > 0")
            state.search_content_max_bytes = value
        elif option == "content_max_redirects":
            value = int(raw)
            if value < 0:
                raise ValueError("search_intelligence.content_max_redirects: use inteiro >= 0")
            state.search_content_max_redirects = value
        elif option == "ai_competitive":
            state.search_ai_competitive = settings._parse_bool(raw)
        elif option == "ymyl_mode":
            value = raw.strip().upper()
            if value not in {"AUTO", "ON", "OFF"}:
                raise ValueError("search_intelligence.ymyl_mode: use AUTO, ON ou OFF")
            state.search_ymyl_mode = value
        return None

    settings._state_values = values
    settings._assign = assign
    settings._rasai_search_console_persistence = True


def _rewrite_search_copy(text: str) -> str:
    return text.replace(_SEARCH_OLD_NOTICE, _SEARCH_NOTICE)


def _install_search_copy() -> None:
    from rasai import console_search_intelligence as search

    if getattr(search, "_rasai_final_console_copy", False):
        return
    original = search.configure_search_intelligence

    class Writer:
        def __init__(self, target: Any):
            self.target = target

        def write(self, text: str):
            return self.target.write(_rewrite_search_copy(text))

        def __getattr__(self, name: str):
            return getattr(self.target, name)

    def configure_search_intelligence(state: Any):
        with redirect_stdout(Writer(sys.stdout)):
            return original(state)

    search.configure_search_intelligence = configure_search_intelligence
    search._rasai_final_console_copy = True


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
        def __init__(self, target: Any):
            super().__init__()
            self._target = target

        def isatty(self):
            probe = getattr(self._target, "isatty", None)
            return bool(probe()) if callable(probe) else False

    def menu(state: Any) -> str:
        original_input, real_stdout, rendered = builtins.input, sys.stdout, False
        buffer = Capture(real_stdout)

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
    _install_search_copy()
    _install_variable_editor(console)
    _install_environment_router(console)
    from rasai import console_navigation as navigation

    navigation._preparation_menu = preparation_menu
    _install_configure_persistence(console)
    _install_top_level(console)
    console._rasai_ui_refactor_installed = True


# Testable aliases retained for the current console contracts.
_capability_specs = capability_specs
_derived_apdex_mix = _derived_mix
_device_result_states = _device_results
_preparation_menu = preparation_menu
_install_top_level_menu = _install_top_level
