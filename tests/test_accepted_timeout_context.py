from __future__ import annotations

from contextvars import ContextVar
import time

from rasai.accepted_timeout_context import _deadline_candidate_call
from rasai.m18_ai import AttemptStatus


def test_deadline_worker_preserves_contextvars() -> None:
    marker: ContextVar[str] = ContextVar("marker", default="missing")
    token = marker.set("improvement-capture")

    class Provider:
        name = "TEST"

    def candidate(provider, *, body, timeout):
        return marker.get(), None, None, AttemptStatus.SUCCESS, 1

    try:
        raw, _usage, _diagnostic, status, _duration = _deadline_candidate_call(
            Provider(), body=b"{}", timeout=0.2, candidate_call=candidate
        )
    finally:
        marker.reset(token)

    assert raw == "improvement-capture"
    assert status is AttemptStatus.SUCCESS


def test_deadline_remains_wall_clock_bounded() -> None:
    class Provider:
        name = "TEST"

    def candidate(provider, *, body, timeout):
        time.sleep(0.20)
        return "late", None, None, AttemptStatus.SUCCESS, 200

    started = time.perf_counter()
    _raw, _usage, diagnostic, status, _duration = _deadline_candidate_call(
        Provider(), body=b"{}", timeout=0.04, candidate_call=candidate
    )

    assert time.perf_counter() - started < 0.15
    assert status is AttemptStatus.TECHNICAL_ERROR
    assert getattr(diagnostic, "error_code", None) == "IMPROVEMENT_WALL_CLOCK_TIMEOUT"
