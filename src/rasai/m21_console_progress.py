"""Interactive-console progress for external Web Performance measurements.

The base console historically held the overall display at ~88% for the complete M21
phase. PageSpeed can legitimately take tens of seconds per URL, so this looked like a
hang even when the provider was still processing. The external-measurement runtime now
emits a start event before every provider call; this adapter projects that event as
measured context progress and shows the active wall-clock deadline.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


_INSTALLED = False


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


def install_m21_external_progress() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    from rasai import console_runtime

    original_observe = console_runtime.observe_workspace
    if bool(getattr(original_observe, "_rasai_m21_external_progress", False)):
        _INSTALLED = True
        return

    def observe_workspace(workspace: Any, state: Any) -> None:
        original_observe(workspace, state)
        event = console_runtime._last_log_event(workspace)
        if not isinstance(event, dict):
            return
        if str(event.get("event") or "") != "M21_EXTERNAL_REQUEST_STARTED":
            return

        state.status = "WEB_PERFORMANCE"
        service = str(event.get("service") or "EXTERNAL")
        state.operation = f"API:{service}"
        state.current_url = str(event.get("url") or state.current_url)
        state.current_device = str(event.get("device") or state.current_device).upper()

        context_index = max(int(event.get("context_index") or 1), 1)
        context_total = max(int(event.get("context_total") or 1), 1)
        completed_contexts = min(context_index - 1, context_total)
        stage_percent = (completed_contexts / context_total) * 100.0

        timeout_seconds = max(float(event.get("timeout_seconds") or 0.0), 0.0)
        age = _event_age_seconds(event)
        elapsed = int(age or 0.0)
        timeout_label = f"/{int(timeout_seconds)}s" if timeout_seconds else ""
        target_navigation = bool(event.get("target_navigation"))
        request_kind = (
            "Lighthouse remoto independente"
            if target_navigation
            else "consulta de dados externa sem nova navegação no alvo"
        )
        detail = (
            f"contexto {context_index}/{context_total}; aguardando {service}; "
            f"{elapsed}s{timeout_label}; {request_kind}; sem retry automático; {state.current_url}"
        )
        if timeout_seconds and age is not None and age >= timeout_seconds:
            detail += "; deadline atingido, aguardando propagação fail-open"

        # Web Performance occupies 88→92 when Synthetic Apdex follows it, otherwise
        # it can use the whole 88→97 enrichment window. The completed-context ratio is
        # measured; the overall projection remains an estimate because the active
        # provider request has unknown remaining duration.
        overall_end = 92.0 if bool(getattr(state, "synthetic_apdex", False)) else 97.0
        overall_percent = 88.0 + ((overall_end - 88.0) * stage_percent / 100.0)
        progress_type = getattr(console_runtime, "_RunProgress", None)
        progress_store = getattr(console_runtime, "_RUN_PROGRESS", None)
        if progress_type is not None and isinstance(progress_store, dict):
            progress_store[id(state)] = progress_type(
                label="Web Performance externo",
                percent=stage_percent,
                detail=detail,
                exact=True,
                stage_percent=stage_percent,
                stage_exact=True,
                overall_percent=overall_percent,
                overall_exact=False,
            )

    setattr(observe_workspace, "_rasai_m21_external_progress", True)
    setattr(observe_workspace, "_rasai_original", original_observe)
    console_runtime.observe_workspace = observe_workspace
    _INSTALLED = True
