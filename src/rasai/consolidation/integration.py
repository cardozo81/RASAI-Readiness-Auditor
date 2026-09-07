"""Minimal opt-in integration with the established interactive console.

The audit console is not reimplemented. Only its menu/configure hooks are wrapped
at the public entrypoint, preserving the existing audit/configuration engine.
"""
from __future__ import annotations

from typing import Any, Callable

from .console import run as run_consolidation_console

CONSOLIDATION_CHOICE = "C"


def install(interactive_console: Any) -> None:
    if getattr(interactive_console, "_consolidation_installed", False):
        return
    original_menu: Callable[..., str] = interactive_console._menu
    original_configure: Callable[..., None] = interactive_console._configure

    def menu_with_consolidation(state: Any) -> str:
        # The core menu renders option C so all actions share one vertical layout.
        # This wrapper remains only to preserve the integration boundary.
        return original_menu(state)

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
