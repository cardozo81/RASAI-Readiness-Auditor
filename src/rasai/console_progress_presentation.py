"""Consistent, truthful visual progress presentation for the interactive console."""
from __future__ import annotations

from typing import Any


_INSTALLED = False
_BAR_WIDTH = 42


def _bar(percent: float) -> str:
    bounded = min(max(float(percent), 0.0), 100.0)
    filled = int(round((_BAR_WIDTH * bounded) / 100.0))
    return "[" + ("#" * filled) + ("-" * (_BAR_WIDTH - filled)) + "]"


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    from rasai import console_environment, console_runtime, interactive_console
    from rasai.console_ui import CYAN, GREEN, paint

    original = console_runtime.render_header
    if bool(getattr(original, "_rasai_progress_bar", False)):
        _INSTALLED = True
        return

    def render_header(state: Any) -> None:
        original(state)
        progress = console_runtime.runtime_progress_summary(state)
        if progress is None or progress.overall_percent is None:
            return
        exact = bool(progress.overall_exact)
        prefix = "" if exact else "~"
        color = GREEN if exact else CYAN
        qualifier = "medido" if exact else "projeção por marcos/unidades observáveis"
        print(
            "Pipeline    : "
            + paint(_bar(progress.overall_percent), color, bold=True)
            + " "
            + paint(f"{prefix}{progress.overall_percent:.0f}%", color, bold=True)
            + f" [{qualifier}]"
        )
        if not exact:
            print("             O percentual geral não representa tempo restante; etapas externas podem ter duração variável.")
        print("=" * 100)

    render_header._rasai_progress_bar = True  # type: ignore[attr-defined]
    console_runtime.render_header = render_header
    # These modules import render_header by value, so rebind their presentation surface.
    interactive_console.render_header = render_header
    console_environment.render_header = render_header
    _INSTALLED = True
