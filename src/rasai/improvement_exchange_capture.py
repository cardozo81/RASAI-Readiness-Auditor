"""Persist sanitized Improvement Intelligence request/response envelopes.

The canonical AI exchange recorder already captures semantic, content-remediation and
technical-remediation traffic. Improvement Intelligence uses the same provider adapters
through the orchestration unification layer, but its deep-analysis transport historically
persisted only attempt telemetry. This additive wrapper closes that observability gap
without changing provider selection, retry/fallback policy, prompts, scoring or payloads.
"""
from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from functools import wraps
from typing import Any

from rasai.ai_exchange_log import AiExchangeRecorder, persist_ai_exchange_log


_INSTALLED = False


@dataclass(slots=True)
class _CaptureState:
    audit_id: str
    workspace: Any
    recorder: AiExchangeRecorder
    external_recorders: list[AiExchangeRecorder]


_STATE: ContextVar[_CaptureState | None] = ContextVar(
    "rasai_improvement_exchange_capture", default=None
)


def _remember_external(state: _CaptureState, recorder: Any) -> None:
    if not isinstance(recorder, AiExchangeRecorder):
        return
    if recorder is state.recorder:
        return
    if all(item is not recorder for item in state.external_recorders):
        state.external_recorders.append(recorder)


def _persist_state(state: _CaptureState) -> None:
    recorders = [state.recorder, *state.external_recorders]
    seen: set[int] = set()
    for recorder in recorders:
        marker = id(recorder)
        if marker in seen:
            continue
        seen.add(marker)
        persist_ai_exchange_log(
            audit_id=state.audit_id,
            workspace=state.workspace,
            recorder=recorder,
        )


def _mark_latest_as_improvement(recorder: AiExchangeRecorder) -> None:
    """Give the generic transport envelope its stable deep-analysis purpose label."""
    if not recorder.exchanges:
        return
    latest = recorder.exchanges[-1]
    if latest.purpose == "IMPROVEMENT_INTELLIGENCE":
        return
    # AiExchange is immutable by design; the recorder owns this private append-only list
    # until persistence, so replacing only the purpose label leaves the captured payload,
    # hashes, timestamps and sanitization untouched.
    recorder._exchanges[-1] = replace(latest, purpose="IMPROVEMENT_INTELLIGENCE")


def install() -> None:
    """Install deep-analysis exchange capture after canonical orchestration is composed."""
    global _INSTALLED
    if _INSTALLED:
        return

    from rasai import ai_orchestration_unification as orchestration
    from rasai import improvement_intelligence as improvement

    original_candidate = orchestration._candidate_call
    if not getattr(original_candidate, "_rasai_improvement_exchange_capture", False):
        @wraps(original_candidate)
        def candidate_call(provider: Any, *, body: bytes, timeout: float):
            state = _STATE.get()
            if state is None:
                return original_candidate(provider, body=body, timeout=timeout)

            # If another canonical recorder already owns this provider transport, do not
            # duplicate the exchange. Persist that recorder at the end of the deep call.
            existing = getattr(provider, "_rasai_exchange_recorder", None)
            if isinstance(existing, AiExchangeRecorder) and bool(
                getattr(provider, "_rasai_exchange_instrumented", False)
            ):
                _remember_external(state, existing)
                return original_candidate(provider, body=body, timeout=timeout)

            started_at = datetime.now(timezone.utc)
            raw, usage, diagnostic, status, duration_ms = original_candidate(
                provider, body=body, timeout=timeout
            )
            state.recorder.append_exchange(
                provider=str(getattr(provider, "name", "UNKNOWN")),
                model=getattr(provider, "model", None),
                endpoint=str(getattr(provider, "endpoint", "")),
                body=body,
                started_at=started_at,
                duration_ms=duration_ms,
                outcome="RESPONSE" if raw is not None else "PROVIDER_ERROR",
                response=raw,
                http_status=getattr(diagnostic, "http_status", None),
                exception_type=getattr(diagnostic, "error_type", None),
            )
            _mark_latest_as_improvement(state.recorder)
            return raw, usage, diagnostic, status, duration_ms

        candidate_call._rasai_improvement_exchange_capture = True  # type: ignore[attr-defined]
        candidate_call._rasai_original = original_candidate  # type: ignore[attr-defined]
        orchestration._candidate_call = candidate_call

    original_analyze = improvement._ai_analyze
    if not getattr(original_analyze, "_rasai_improvement_exchange_capture", False):
        @wraps(original_analyze)
        def ai_analyze(*args: Any, **kwargs: Any):
            current = _STATE.get()
            if current is not None:
                return original_analyze(*args, **kwargs)
            audit_id = str(kwargs.get("audit_id") or "")
            workspace = kwargs.get("workspace")
            if not audit_id or workspace is None:
                return original_analyze(*args, **kwargs)
            state = _CaptureState(
                audit_id=audit_id,
                workspace=workspace,
                recorder=AiExchangeRecorder(),
                external_recorders=[],
            )
            token = _STATE.set(state)
            try:
                return original_analyze(*args, **kwargs)
            finally:
                try:
                    _persist_state(state)
                finally:
                    _STATE.reset(token)

        ai_analyze._rasai_improvement_exchange_capture = True  # type: ignore[attr-defined]
        ai_analyze._rasai_original = original_analyze  # type: ignore[attr-defined]
        improvement._ai_analyze = ai_analyze

    _INSTALLED = True


__all__ = ["install"]
