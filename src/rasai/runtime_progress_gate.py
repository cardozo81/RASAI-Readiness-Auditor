"""Interactive-console progress gate for post-audit Search Intelligence.

The core audit runner historically reaches its terminal screen before the optional
Search Intelligence extension starts. When SERP terms are pending, keep the execution
clock open and project the hand-off as a real final pipeline stage instead of briefly
showing 100%/finished and then going backwards.
"""
from __future__ import annotations

from typing import Any


_INSTALLED = False


def install_search_progress_gate() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    from rasai import console_runtime

    original_render = console_runtime.render_header
    if bool(getattr(original_render, "_rasai_search_progress_gate", False)):
        _INSTALLED = True
        return

    def render_header(state: Any) -> None:
        queries = tuple(getattr(state, "search_queries", ()) or ())
        pending = bool(queries) and str(getattr(state, "search_last_status", "")).upper() == "PENDING"
        status = str(getattr(state, "status", "")).upper()
        timing = console_runtime._RUN_TIMINGS.get(id(state))
        terminal_core_screen = (
            pending
            and status in {"COMPLETE", "COMPLETE_WITH_LIMITATIONS"}
            and timing is not None
            and timing.finished_at is not None
        )
        if not terminal_core_screen:
            original_render(state)
            return

        # The core projection has already been persisted at this point. Re-open the
        # same clock before drawing the terminal screen so elapsed time remains a
        # single end-to-end duration that will be overwritten after SERP finalization.
        timing.finished_at = None
        timing.duration_seconds = None
        progress_type = getattr(console_runtime, "_RunProgress", None)
        progress_store = getattr(console_runtime, "_RUN_PROGRESS", None)
        if progress_type is not None and isinstance(progress_store, dict):
            progress_store[id(state)] = progress_type(
                label="Search Intelligence / SERP",
                percent=0.0,
                detail=(
                    f"auditoria principal concluída; iniciando {len(queries)} termo(s) SERP "
                    "antes da liberação final dos relatórios"
                ),
                exact=True,
                stage_percent=0.0,
                stage_exact=True,
                overall_percent=97.0,
                overall_exact=False,
            )

        previous_status = state.status
        previous_operation = state.operation
        try:
            state.status = "SEARCH_INTELLIGENCE"
            state.operation = "API:SERP"
            original_render(state)
        finally:
            state.status = previous_status
            state.operation = previous_operation

    setattr(render_header, "_rasai_search_progress_gate", True)
    setattr(render_header, "_rasai_original", original_render)
    console_runtime.render_header = render_header
    _INSTALLED = True
