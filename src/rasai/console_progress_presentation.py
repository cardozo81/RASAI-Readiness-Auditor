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
    from rasai.audit_progress_runtime import install as install_audit_progress_runtime
    from rasai.console_progress_model import install as install_workload_progress_model
    from rasai.external_observability_progress_runtime import install as install_external_progress_runtime
    from rasai.console_ui import CYAN, GREEN, paint

    # Install after the specialized collectors/runtime adapters have been composed.
    # This layer only observes their real units/events and recalculates presentation.
    install_audit_progress_runtime()
    install_external_progress_runtime()
    install_workload_progress_model()

    original = console_runtime.render_header
    if bool(getattr(original, "_rasai_progress_bar", False)):
        _INSTALLED = True
        return

    def render_header(state: Any) -> None:
        original(state)
        progress = console_runtime.runtime_progress_summary(state)
        if progress is None:
            return

        if progress.stage_percent is not None:
            stage_exact = bool(progress.stage_exact)
            stage_prefix = "" if stage_exact else "~"
            stage_color = GREEN if stage_exact else CYAN
            stage_qualifier = "medido na etapa" if stage_exact else "estimado dentro da etapa"
            print(
                "Barra etapa : "
                + paint(_bar(progress.stage_percent), stage_color, bold=True)
                + " "
                + paint(f"{stage_prefix}{progress.stage_percent:.0f}%", stage_color, bold=True)
                + f" [{stage_qualifier}]"
            )

        if progress.overall_percent is None:
            print("=" * 100)
            return

        exact = bool(progress.overall_exact)
        prefix = "" if exact else "~"
        color = GREEN if exact else CYAN
        qualifier = "medido" if exact else "projeção ponderada pela carga configurada/observada"
        print(
            "Pipeline    : "
            + paint(_bar(progress.overall_percent), color, bold=True)
            + " "
            + paint(f"{prefix}{progress.overall_percent:.0f}%", color, bold=True)
            + f" [{qualifier}]"
        )
        if not exact:
            print(
                "             O percentual geral estima a posição no trabalho planejado; "
                "não é previsão de tempo restante e se ajusta quando a carga real é conhecida."
            )
        print("=" * 100)

    render_header._rasai_progress_bar = True  # type: ignore[attr-defined]
    console_runtime.render_header = render_header
    # These modules import render_header by value, so rebind their presentation surface.
    interactive_console.render_header = render_header
    console_environment.render_header = render_header
    _INSTALLED = True
