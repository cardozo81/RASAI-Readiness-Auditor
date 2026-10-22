"""Bounded same-sample DOM-stability gate for the isolated architecture renderer.

Navigation/load/networkidle are not proof of content materialization. The
function below operates on observations from one Playwright page in ONE
already network-isolated browser. It never authorizes further navigation,
browser egress, interaction, or indefinite waiting.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import time
from typing import Any

MAX_SETTLE_MS = 2800
# Standalone, networkless menu-8 preview ONLY. Not used by canonical AUD captures.
ISOLATED_PREVIEW_SETTLE_MS = 5200
MIN_OBSERVE_MS = 850
SAMPLE_INTERVAL_MS = 200
STABLE_SAMPLES = 3

# Assessed on the existing document only: no network or event injection.
DOM_SAMPLE_JS = """() => {
  const visible = el => {
    if (!el || !el.isConnected || el.hidden) return false;
    const style = window.getComputedStyle(el);
    return style.display !== 'none' && style.visibility !== 'hidden'
      && el.getClientRects().length > 0;
  };
  const el = Array.from(document.querySelectorAll(
    'main,article,[role="main"]')).find(visible);
  const loading = Array.from(document.querySelectorAll(
    '[aria-busy="true"],.skeleton,.loading-state,[data-loading="true"]'
  )).some(visible);
  const text = el ? (el.innerText || '').trim().slice(0, 3000) : '';
  return {text, loading, hasMain: !!el};
}"""


@dataclass(frozen=True, slots=True)
class DomSettleResult:
    stable: bool
    reason: str | None
    samples: int
    material_text_observed: bool
    loading_marker_observed: bool
    bounded_ms: int = MAX_SETTLE_MS
    content_transitions: int = 0
    observed_ms: int = 0


def _sample_fields(raw: Any) -> tuple[str, bool, bool] | None:
    if not isinstance(raw, dict) or set(raw) != {"text", "loading", "hasMain"}:
        return None
    text, loading, main = raw["text"], raw["loading"], raw["hasMain"]
    if not isinstance(text, str) or len(text) > 3000:
        return None
    if type(loading) is not bool or type(main) is not bool:
        return None
    return " ".join(text.split()), loading, main


def wait_for_material_dom(
    page: Any, *, time_source=time.monotonic, isolated_preview: bool = False,
) -> DomSettleResult:
    """Use the entire bounded same-page window, including late SPA mutations.

    A stable SSR-looking first paint may be replaced by client rendering after
    the 850ms checkpoint. Accepting at that checkpoint would falsely certify
    STATIC_OR_SSR. We therefore make the decision from the *final* consecutive
    material samples, and never grant an early pass. All samples are from one
    already-isolated page and no new network is initiated by this function.
    The 2.8s default is unchanged; the menu-8 OCI preview explicitly uses
    a 5.2s bound to observe late client-side replacement even if first paint
    looked stable. No network/RTT/load metric is sampled by this function.
    """
    if type(isolated_preview) is not bool:
        raise ValueError("isolated_preview must be boolean")
    budget_ms = ISOLATED_PREVIEW_SETTLE_MS if isolated_preview else MAX_SETTLE_MS
    begin = time_source()
    previous: str | None = None
    stable = 0
    count = 0
    observed = False
    saw_loading = False
    transitions = 0
    elapsed = 0.0
    while (time_source() - begin) * 1000 <= budget_ms:
        try:
            parsed = _sample_fields(page.evaluate(DOM_SAMPLE_JS))
        except (OSError, ValueError, TypeError, RuntimeError):
            return DomSettleResult(
                False, "ISOLATED_CONTENT_NOT_ATTESTED", count, observed,
                saw_loading, bounded_ms=budget_ms,
                content_transitions=transitions, observed_ms=int(elapsed),
            )
        if parsed is None:
            return DomSettleResult(
                False, "ISOLATED_CONTENT_NOT_ATTESTED", count, observed,
                saw_loading, bounded_ms=budget_ms,
                content_transitions=transitions, observed_ms=int(elapsed),
            )
        text, loading, has_main = parsed
        count += 1
        saw_loading |= loading
        material = bool(has_main and len(text) >= 16)
        observed |= material
        if material and not loading:
            fingerprint = sha256(text.encode("utf-8")).hexdigest()
            if previous is not None and previous != fingerprint:
                transitions += 1
            stable = stable + 1 if fingerprint == previous else 1
            previous = fingerprint
        else:
            stable, previous = 0, None
        elapsed = (time_source() - begin) * 1000
        if elapsed + SAMPLE_INTERVAL_MS > budget_ms:
            break
        page.wait_for_timeout(SAMPLE_INTERVAL_MS)
    successful = elapsed >= MIN_OBSERVE_MS and stable >= STABLE_SAMPLES
    return DomSettleResult(
        successful, None if successful else "ISOLATED_CONTENT_NOT_STABLE",
        count, observed, saw_loading,
        bounded_ms=budget_ms, content_transitions=transitions,
        observed_ms=int(elapsed),
    )


__all__ = ["wait_for_material_dom", "DomSettleResult", "DOM_SAMPLE_JS"]
