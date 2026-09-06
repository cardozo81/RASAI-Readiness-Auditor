"""Minimal opt-in integration with the established interactive console.

The audit console is not reimplemented. Only its menu/configure hooks are wrapped
at the public entrypoint, preserving the existing audit/configuration engine.
"""
from __future__ import annotations

import builtins
from typing import Any, Callable

from .console import run as run_consolidation_console

CONSOLIDATION_CHOICE = "C"


def install(interactive_console: Any) -> None:
    if getattr(interactive_console, "_consolidation_installed", False):
        return
    original_menu: Callable[..., str] = interactive_console._menu
    original_configure: Callable[..., None] = interactive_console._configure

    def menu_with_consolidation(state: Any) -> str:
        had_module_input = hasattr(interactive_console, "input")
        original_input = getattr(interactive_console, "input", builtins.input)

        def input_with_option(prompt: str = "") -> str:
            if prompt == "Escolha: ":
                print("C. Histórico / relatórios consolidados [OFFLINE | sem APIs]")
            return original_input(prompt)

        interactive_console.input = input_with_option
        try:
            return original_menu(state)
        finally:
            if had_module_input:
                interactive_console.input = original_input
            else:
                delattr(interactive_console, "input")

    def configure_with_consolidation(state: Any, choice: str) -> None:
        if choice != CONSOLIDATION_CHOICE:
            original_configure(state, choice)
            return
        previous = (
            getattr(state, "status", "READY"),
            getattr(state, "operation", "LOCAL:MENU"),
            getattr(state, "error", ""),
        )
        state.status = "CONSOLIDATING"
        state.operation = "LOCAL:CONSOLIDATED_REPORT"
        state.error = ""
        try:
            run_consolidation_console(state.audits_root)
        except Exception as exc:  # fail-open boundary: never break the audit console
            state.error = f"consolidação indisponível: {type(exc).__name__}: {exc}"
        finally:
            if not state.error:
                state.status, state.operation, state.error = previous
            else:
                state.status = previous[0]
                state.operation = "LOCAL:CONSOLIDATION_ERROR"

    interactive_console._menu = menu_with_consolidation
    interactive_console._configure = configure_with_consolidation
    interactive_console._consolidation_installed = True
