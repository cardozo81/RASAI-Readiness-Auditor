"""Preserve execution context while enforcing Improvement Intelligence wall-clock deadlines."""
from __future__ import annotations

from contextvars import copy_context
from datetime import datetime, timezone
import queue
import threading
import time
from typing import Any


def _record_timeout_exchange(provider: Any, body: bytes, started_at: datetime, duration_ms: int) -> None:
    """Persist the timeout envelope even when the abandoned transport finishes later."""
    try:
        from rasai import improvement_exchange_capture as capture
        from rasai.ai_exchange_log import AiExchangeRecorder

        state = capture._STATE.get()
        if state is None:
            return
        recorder = state.recorder
        existing = getattr(provider, "_rasai_exchange_recorder", None)
        if isinstance(existing, AiExchangeRecorder) and bool(
            getattr(provider, "_rasai_exchange_instrumented", False)
        ):
            capture._remember_external(state, existing)
            recorder = existing
        recorder.append_exchange(
            provider=str(getattr(provider, "name", "UNKNOWN")),
            model=getattr(provider, "model", None),
            endpoint=str(getattr(provider, "endpoint", "")),
            body=body,
            started_at=started_at,
            duration_ms=duration_ms,
            outcome="PROVIDER_ERROR",
            response=None,
            exception_type="WallClockDeadlineExceeded",
        )
        capture._mark_latest_as_improvement(recorder)
    except Exception:
        # Telemetry must never convert a bounded provider timeout into a pipeline failure.
        return


def _deadline_candidate_call(
    provider: Any,
    *,
    body: bytes,
    timeout: float,
    candidate_call: Any,
) -> tuple[Any, Any, Any, Any, int]:
    from rasai.m18_ai import AttemptStatus, ProviderDiagnostic, ProviderErrorClass

    limit = max(0.001, float(timeout))
    output: queue.Queue[tuple[str, Any]] = queue.Queue(maxsize=1)
    started_perf = time.perf_counter()
    started_at = datetime.now(timezone.utc)
    execution_context = copy_context()

    def invoke() -> None:
        try:
            output.put(("result", candidate_call(provider, body=body, timeout=limit)))
        except BaseException as exc:
            output.put(("error", exc))

    worker = threading.Thread(
        target=lambda: execution_context.run(invoke),
        name=f"rasai-improvement-{getattr(provider, 'name', 'provider')}",
        daemon=True,
    )
    worker.start()
    try:
        kind, value = output.get(timeout=limit)
    except queue.Empty:
        # Resolve the boundary race if the worker completed between timeout and handling.
        try:
            kind, value = output.get_nowait()
        except queue.Empty:
            elapsed = max(0, int((time.perf_counter() - started_perf) * 1000))
            _record_timeout_exchange(provider, body, started_at, elapsed)
            return (
                None,
                None,
                ProviderDiagnostic(
                    ProviderErrorClass.TIMEOUT_ERROR,
                    error_type="WallClockDeadlineExceeded",
                    error_code="IMPROVEMENT_WALL_CLOCK_TIMEOUT",
                ),
                AttemptStatus.TECHNICAL_ERROR,
                elapsed,
            )
    if kind == "error":
        elapsed = max(0, int((time.perf_counter() - started_perf) * 1000))
        return (
            None,
            None,
            ProviderDiagnostic(
                ProviderErrorClass.UNKNOWN_PROVIDER_ERROR,
                error_type=type(value).__name__,
                error_code="IMPROVEMENT_CALL_WRAPPER_ERROR",
            ),
            AttemptStatus.TECHNICAL_ERROR,
            elapsed,
        )
    return value


def install() -> None:
    from rasai import accepted_audit_refinements as accepted

    if getattr(accepted._deadline_candidate_call, "_rasai_context_preserving_deadline", False):
        return
    _deadline_candidate_call._rasai_context_preserving_deadline = True
    _deadline_candidate_call._rasai_original = accepted._deadline_candidate_call
    accepted._deadline_candidate_call = _deadline_candidate_call


__all__ = ["_deadline_candidate_call", "install"]
