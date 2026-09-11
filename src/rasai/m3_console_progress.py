"""Interactive-console projection for core M3 browser rendering.

M3 persists a snapshot only after a browser render returns, so showing the most recent
snapshot can make a stalled render look like it is still processing the previous URL.
This adapter projects the operational M3 events emitted before/after each render so the
console shows the URL/device that is actually in flight and warns when no new render
milestone has appeared for an unusual amount of time.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


_INSTALLED = False
_STALL_WARNING_SECONDS = 30.0


def _event_age_seconds(event: dict[str, object]) -> float | None:
    raw = str(event.get("timestamp") or "").strip()
    if not raw:
        return None
    try:
        observed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if observed.tzinfo is None:
        observed = observed.replace(tzinfo=timezone.utc)
    return max((datetime.now(timezone.utc) - observed.astimezone(timezone.utc)).total_seconds(), 0.0)


def install_m3_render_progress() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    from rasai import console_runtime

    original_observe = console_runtime.observe_workspace
    if bool(getattr(original_observe, "_rasai_m3_render_progress", False)):
        _INSTALLED = True
        return

    def observe_workspace(workspace: Any, state: Any) -> None:
        original_observe(workspace, state)
        if str(getattr(state, "status", "")).upper() != "ACQUIRING":
            return
        event = console_runtime._last_log_event(workspace)
        if not isinstance(event, dict):
            return
        name = str(event.get("event") or "")
        if name not in {"M3_RENDER_STARTED", "M3_RENDER_COMPLETED", "M3_SNAPSHOT_PERSISTED"}:
            return

        state.current_url = str(event.get("url") or state.current_url)
        state.current_device = str(event.get("device") or state.current_device).upper()
        context_index = max(int(event.get("context_index") or 1), 1)
        context_total = max(int(event.get("context_total") or 1), 1)

        if name == "M3_RENDER_STARTED":
            completed_contexts = min(context_index - 1, context_total)
            state.operation = "BROWSER:CHROMIUM_RENDER"
            detail = f"renderizando snapshot {context_index}/{context_total}; {state.current_device}; {state.current_url}"
            age = _event_age_seconds(event)
            if age is not None and age >= _STALL_WARNING_SECONDS:
                detail += f"; sem novo marco de renderização há {int(age)}s"
        elif name == "M3_RENDER_COMPLETED":
            completed_contexts = min(context_index, context_total)
            state.operation = "LOCAL:SNAPSHOT_PERSIST"
            status = str(event.get("render_status") or "-")
            duration_ms = int(event.get("duration_ms") or 0)
            detail = (
                f"renderização {context_index}/{context_total} concluída ({status}, {duration_ms}ms); "
                "persistindo snapshot"
            )
        else:
            completed_contexts = min(context_index, context_total)
            state.operation = "LOCAL:SNAPSHOT_PERSIST"
            detail = f"snapshot {context_index}/{context_total} persistido; preparando próximo contexto"

        stage_percent = (completed_contexts / context_total) * 100.0
        overall_percent = 22.0 + (20.0 * stage_percent / 100.0)
        progress_type = getattr(console_runtime, "_RunProgress", None)
        progress_store = getattr(console_runtime, "_RUN_PROGRESS", None)
        if progress_type is not None and isinstance(progress_store, dict):
            progress_store[id(state)] = progress_type(
                label="Aquisição HTTP e renderização",
                percent=stage_percent,
                detail=detail,
                exact=True,
                stage_percent=stage_percent,
                stage_exact=True,
                overall_percent=overall_percent,
                overall_exact=False,
            )

    setattr(observe_workspace, "_rasai_m3_render_progress", True)
    setattr(observe_workspace, "_rasai_original", original_observe)
    console_runtime.observe_workspace = observe_workspace
    _INSTALLED = True
