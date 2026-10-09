"""Experimental advisory contract #322: primary-content readiness, NOT an Apdex task.

No browser hooks, network calls, SQLite writes or changes to M23/M25 are made here.
A producer may feed checkpoints only from ONE explicitly identified browser/sample
context. This classifier cannot infer timestamps from M3 capture or past M23/M25.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

METHOD_VERSION = "APP_PRIMARY_CONTENT_READINESS-EXPERIMENTAL-001"
STRICT_PROVENANCE_VERSION = "APP_PRIMARY_CONTENT_READINESS-EXPERIMENTAL-002-STRICT-PROVENANCE"
_ELIGIBLE = frozenset({"CSR_SPA", "HYDRATED", "MIXED"})
_MIN_MAIN_CHARACTERS = 200
_MIN_HEADING_CHARACTERS = 5
_MIN_STABILITY_MS = 100
_MAX_WINDOW_MS = 3000


@dataclass(frozen=True, slots=True)
class PrimaryContentCheckpoint:
    sample_id: str
    context_id: str
    since_navigation_ms: float
    main_text_characters: int
    heading_text_characters: int
    skeleton_present: bool
    page_id: str = ""
    device: str = ""


@dataclass(frozen=True, slots=True)
class PrimaryContentReadiness:
    sample_id: str
    context_id: str
    architecture: str
    method_version: str
    status: str
    load_ms: float | None
    primary_content_ms: float | None
    post_load_delta_ms: float | None
    observation_window_ms: int
    reason: str
    page_id: str = ""
    device: str = ""


def classify_primary_content_readiness(
    *,
    sample_id: str,
    context_id: str,
    architecture: str,
    load_ms: float | None,
    checkpoints: Sequence[PrimaryContentCheckpoint] = (),
    enabled: bool = False,
    window_ms: int = 1500,
    window_expired: bool = False,
    page_id: str = "",
    device: str = "",
    strict_provenance: bool = False,
) -> PrimaryContentReadiness:
    """Classify only pre-collected same-sample monotonic checkpoints.

    This does NOT sample browser content itself. Timestamps are relative to the
    navigation start in the same context, never wall-clock or M3 capture times.
    All outputs are advisory, independent of legacy Apdex and scoring.
    """
    name = str(architecture or "UNKNOWN").strip().upper()
    def result(status: str, reason: str, ready: float | None = None):
        return PrimaryContentReadiness(
            sample_id=sample_id,
            context_id=context_id,
            architecture=name,
            method_version=(
                STRICT_PROVENANCE_VERSION if strict_provenance else METHOD_VERSION
            ),
            status=status,
            load_ms=load_ms,
            primary_content_ms=ready,
            post_load_delta_ms=(max(ready - load_ms, 0.0) if ready is not None and load_ms is not None else None),
            observation_window_ms=window_ms,
            reason=reason,
            page_id=page_id if strict_provenance else "",
            device=device if strict_provenance else "",
        )

    if not enabled:
        return result("NOT_APPLICABLE", "opt_in_disabled")
    if name not in _ELIGIBLE:
        return result("NOT_APPLICABLE", "architecture_not_selected")
    if not sample_id or not context_id:
        return result("ERROR", "missing_sample_or_context_identity")
    if strict_provenance and (
        not str(page_id).strip() or not str(device).strip()
    ):
        return result("ERROR", "missing_page_or_device_identity")
    if not isinstance(window_ms, int) or not 100 <= window_ms <= _MAX_WINDOW_MS:
        return result("ERROR", "invalid_observation_window")
    if load_ms is None or not 0 <= load_ms < float("inf"):
        return result("ERROR", "no_same_context_load_boundary")
    if any(
        sample.sample_id != sample_id
        or sample.context_id != context_id
        or (
            strict_provenance
            and (sample.page_id != page_id or sample.device != device)
        )
        or not 0 <= sample.since_navigation_ms < float("inf")
        or sample.since_navigation_ms > load_ms + window_ms
        or sample.main_text_characters < 0
        or sample.heading_text_characters < 0
        for sample in checkpoints
    ):
        return result("ERROR", "mixed_context_or_invalid_checkpoint")
    times = [sample.since_navigation_ms for sample in checkpoints]
    if times != sorted(times):
        return result("ERROR", "out_of_order_checkpoints")
    if not checkpoints:
        return result("TIMEOUT" if window_expired else "NOT_OBSERVED", "no_checkpoints")
    def material(sample: PrimaryContentCheckpoint) -> bool:
        return (
            sample.main_text_characters >= _MIN_MAIN_CHARACTERS
            and sample.heading_text_characters >= _MIN_HEADING_CHARACTERS
            and not sample.skeleton_present
        )
    for i, first in enumerate(checkpoints):
        if not material(first):
            continue
        # A skeleton or an empty/intermediate checkpoint breaks continuity.
        # Two distant positive probes cannot establish stability if a negative
        # probe was recorded between them in this SAME browser context.
        for next_sample in checkpoints[i + 1:]:
            if not material(next_sample):
                break
            if next_sample.since_navigation_ms - first.since_navigation_ms >= _MIN_STABILITY_MS:
                return result("OBSERVED", "stable_primary_dom_text", first.since_navigation_ms)
    return result(
        "TIMEOUT" if window_expired else "NOT_OBSERVED",
        "window_censored" if window_expired else "content_not_yet_stable",
    )
