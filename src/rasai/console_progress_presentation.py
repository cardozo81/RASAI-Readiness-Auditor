"""Consistent, truthful visual progress presentation for the interactive console."""
from __future__ import annotations

from typing import Any


_INSTALLED = False


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    from rasai import console_environment, console_runtime, interactive_console
    from rasai.audit_progress_runtime import install as install_audit_progress_runtime
    from rasai.console_progress_model import install as install_workload_progress_model
    from rasai.execution_progress_presentation import render_canonical_progress
    from rasai.external_observability_progress_runtime import install as install_external_progress_runtime
    from rasai.progress_completion_refinement import install as install_progress_completion_refinement

    # Install after the specialized collectors/runtime adapters have been composed.
    # This layer only observes their real units/events and recalculates presentation.
    install_audit_progress_runtime()
    install_external_progress_runtime()
    # Improvement Intelligence is installed later by console_entrypoint. Prepare its
    # workload phase and post-analysis local-only report refresh before that wrapper is
    # composed, while the external finalizer chain is already complete.
    install_progress_completion_refinement()
    install_workload_progress_model()

    original = console_runtime.render_header
    if bool(getattr(original, "_rasai_progress_bar", False)):
        _INSTALLED = True
        return

    # The base header keeps status/url/timing/error. Progress is rendered once, below,
    # through the canonical single-screen block.
    console_runtime._CANONICAL_PROGRESS_PRESENTATION = True

    def render_header(state: Any) -> None:
        original(state)
        progress = console_runtime.runtime_progress_summary(state)
        if progress is None:
            return

        details = list(getattr(progress, "detail_rows", ()) or ())
        operation = str(getattr(state, "operation", "") or "").strip()
        if operation and not any(str(label).casefold() == "operação" for label, _value in details):
            details.insert(0, ("Operação", operation))

        render_canonical_progress(
            current_label=str(progress.label or "Execução"),
            current_status=str(getattr(progress, "current_status", "") or "EM EXECUÇÃO"),
            stage_index=getattr(progress, "stage_index", None),
            stage_count=getattr(progress, "stage_count", None),
            stage_count_planned=bool(getattr(progress, "stage_count_planned", True)),
            previous_label=str(getattr(progress, "previous_label", "") or "") or None,
            next_label=str(getattr(progress, "next_label", "") or "") or None,
            next_status=str(getattr(progress, "next_status", "") or "AGUARDANDO"),
            stage_percent=progress.stage_percent,
            stage_exact=bool(progress.stage_exact),
            overall_percent=progress.overall_percent,
            overall_exact=bool(progress.overall_exact),
            message=str(progress.detail or ""),
            detail_rows=details,
        )
        if progress.overall_percent is not None and not bool(progress.overall_exact):
            print(
                "O percentual total representa posição projetada no trabalho planejado; "
                "não é previsão de tempo restante."
            )
            print("=" * 100)

    render_header._rasai_progress_bar = True  # type: ignore[attr-defined]
    console_runtime.render_header = render_header
    # These modules import render_header by value, so rebind their presentation surface.
    interactive_console.render_header = render_header
    console_environment.render_header = render_header
    _INSTALLED = True
