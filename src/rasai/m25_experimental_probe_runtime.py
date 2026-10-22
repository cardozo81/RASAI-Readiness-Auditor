"""Explicit opt-in M25 same-navigation readiness, flushed only after AUD seal.

No baseline collector changes, no scores, no provider or new navigation. The
producer retains only a bounded series of derived numeric observations in
process memory until the catalog report is finalized.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
import sqlite3
from threading import Lock
from typing import Any

from rasai.apdex_content_readiness_observation import (
    PrimaryContentReadiness, STRICT_PROVENANCE_VERSION,
)

_ALLOWED = frozenset({"CSR_SPA", "HYDRATED", "MIXED", "UNKNOWN", "STATIC_OR_SSR"})
_LOCK = Lock()
_pending: tuple[str, int] | None = None
_observations: dict[str, list[PrimaryContentReadiness]] = defaultdict(list)
_costs: dict[str, dict[str, Any]] = defaultdict(dict)
_MAX_OBSERVATIONS = 128


def configure_one_shot_readiness(
    *, architecture: str, window_ms: int = 1200,
    operator_opt_in: bool = False,
) -> None:
    """One-shot intent, never default; explicit architecture cannot be inferred."""
    global _pending
    if (operator_opt_in is not True or architecture not in _ALLOWED
            or type(window_ms) is not int or not 100 <= window_ms <= 3000):
        raise ValueError("explicit bounded readiness opt-in is required")
    with _LOCK:
        if _pending is not None:
            raise ValueError("readiness opt-in already awaiting audit")
        _pending = (architecture, window_ms)


def consume_one_shot_readiness() -> tuple[str, int] | None:
    global _pending
    with _LOCK:
        value, _pending = _pending, None
        return value


def clear_pending_readiness() -> None:
    global _pending
    with _LOCK:
        _pending = None


def experimental_gateway_factory(*, session_mode: str, policy: tuple[str, int]):
    from rasai.m25_apdex_experience import PlaywrightSyntheticUxGateway
    from rasai.readiness_probe_cost_pilot import measure_existing_playwright_probe_cost

    architecture, window_ms = policy
    def record_on_live_page(
        *, page: Any, live_context: Any, requested_url: str,
        final_url: str, device: str, navigation_started_monotonic_ns: int,
        load_ms: float, audit_id: str, page_id: str, sample_id: str,
        context_id: str,
    ) -> PrimaryContentReadiness | dict[str, object]:
        # Only the existing M25 page/context. Never write at this stage.
        try:
            if (page is None or page.context is not live_context
                    or page.url != final_url or len(live_context.pages) != 1):
                return {"status": "EXPERIMENTAL_SAME_PAGE_SCOPE_NOT_VERIFIED"}
            timed = measure_existing_playwright_probe_cost(
                page=page, sample_id=sample_id, context_id=context_id,
                page_id=page_id, device=device, architecture=architecture,
                navigation_started_monotonic_ns=navigation_started_monotonic_ns,
                load_ms=load_ms, enabled=True, window_ms=window_ms,
            )
            observed = timed.observation
            if observed.method_version != STRICT_PROVENANCE_VERSION:
                return {"status": "EXPERIMENTAL_PROVENANCE_NOT_VERIFIED"}
            with _LOCK:
                rows = _observations[audit_id]
                if len(rows) < _MAX_OBSERVATIONS:
                    rows.append(observed)
                    _costs[audit_id][sample_id] = timed
            return observed
        except Exception:
            return {"status": "EXPERIMENTAL_PROBE_UNAVAILABLE"}
    return PlaywrightSyntheticUxGateway(
        session_mode=session_mode,
        advisory_same_page_observer=record_on_live_page,
    )


def forget_experimental_readiness(audit_id: str | None = None) -> None:
    with _LOCK:
        if audit_id is None:
            _observations.clear()
            _costs.clear()
        else:
            _observations.pop(audit_id, None)
            _costs.pop(audit_id, None)


def _drain(audit_id: str) -> tuple[tuple[PrimaryContentReadiness, ...], dict[str, Any]]:
    with _LOCK:
        return tuple(_observations.pop(audit_id, ())), _costs.pop(audit_id, {})


def publish_after_seal(*, audit_id: str, aud_dir: Path) -> dict[str, int]:
    """Validate row identity against immutable AUD before each sidecar write.

    A missing table/sample never becomes proof. Every failure is isolated;
    caller must not treat a sidecar error as permission to edit the AUD.
    """
    observations, costs = _drain(audit_id)
    result = {"eligible": len(observations), "published": 0, "rejected": 0}
    if not observations:
        return result
    from rasai.apdex_readiness_sidecar import write_readiness_sidecar
    from rasai.apdex_readiness_sidecar import _original
    root = Path(aud_dir)
    try:
        verified_audit_id, _, _ = _original(root)
        if verified_audit_id != audit_id:
            raise ValueError("AUD identity changed")
        db = root / "audit.db"
        with sqlite3.connect(db.resolve().as_uri() + "?mode=ro&immutable=1", uri=True, timeout=1) as con:
            con.execute("PRAGMA query_only=ON")
            for row in observations:
                try:
                    count = con.execute(
                        "SELECT COUNT(*) FROM synthetic_ux_apdex_samples "
                        "WHERE audit_id=? AND sample_id=? AND page_id=? AND device=?",
                        (audit_id, row.sample_id, row.page_id, row.device),
                    ).fetchone()[0]
                    if count != 1 or row.method_version != STRICT_PROVENANCE_VERSION:
                        result["rejected"] += 1
                        continue
                    if row.sample_id in costs:
                        write_readiness_sidecar(root, row, probe_cost=costs[row.sample_id])
                    else:
                        write_readiness_sidecar(root, row)
                    result["published"] += 1
                except (ValueError, OSError, sqlite3.Error):
                    result["rejected"] += 1
    except (ValueError, OSError, sqlite3.Error):
        result["rejected"] = len(observations)
    return result


__all__ = [
    "configure_one_shot_readiness", "consume_one_shot_readiness",
    "clear_pending_readiness", "experimental_gateway_factory",
    "publish_after_seal", "forget_experimental_readiness",
]
