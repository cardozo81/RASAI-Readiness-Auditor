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
MIN_OBSERVE_MS = 850
SAMPLE_INTERVAL_MS = 200
STABLE_SAMPLES = 3

# Assessed on the existing document only: no network or event injection.
DOM_SAMPLE_JS = """() => {
  const el = document.querySelector('main,article,[role="main"]');
  const loading = !!document.querySelector(
    '[aria-busy="true"],.skeleton,.loading-state,[data-loading="true"]'
  );
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


def _sample_fields(raw: Any) -> tuple[str, bool, bool] | None:
    if not isinstance(raw, dict) or set(raw) != {"text", "loading", "hasMain"}:
        return None
    text, loading, main = raw["text"], raw["loading"], raw["hasMain"]
    if not isinstance(text, str) or len(text) > 3000:
        return None
    if type(loading) is not bool or type(main) is not bool:
        return None
    return " ".join(text.split()), loading, main


def wait_for_material_dom(page: Any, *, time_source=time.monotonic) -> DomSettleResult:
    """Observe up to 2.8s after DOMContentLoaded; a short initial flash is N/D.

    The HTML is returned only after stable, material content from the same
    page/snapshot and at least 850ms of observation. A late SPA update
    invalidates earlier stability. A page with no main or unresolved loading
    is censored rather than categorized as static/SSR.
    """
    begin = time_source()
    previous: str | None = None
    stable = 0
    count = 0
    observed = False
    saw_loading = False
    while (time_source() - begin) * 1000 <= MAX_SETTLE_MS:
        try:
            parsed = _sample_fields(page.evaluate(DOM_SAMPLE_JS))
        except (OSError, ValueError, TypeError, RuntimeError):
            return DomSettleResult(False, "ISOLATED_CONTENT_NOT_ATTESTED", count, observed, saw_loading)
        if parsed is None:
            return DomSettleResult(False, "ISOLATED_CONTENT_NOT_ATTESTED", count, observed, saw_loading)
        text, loading, has_main = parsed
        count += 1
        saw_loading |= loading
        material = bool(has_main and len(text) >= 16)
        observed |= material
        if material and not loading:
            fingerprint = sha256(text.encode("utf-8")).hexdigest()
            stable = stable + 1 if fingerprint == previous else 1
            previous = fingerprint
        else:
            stable, previous = 0, None
        elapsed = (time_source() - begin) * 1000
        if elapsed >= MIN_OBSERVE_MS and stable >= STABLE_SAMPLES:
            return DomSettleResult(True, None, count, observed, saw_loading)
        if elapsed + SAMPLE_INTERVAL_MS > MAX_SETTLE_MS:
            break
        page.wait_for_timeout(SAMPLE_INTERVAL_MS)
    return DomSettleResult(
        False, "ISOLATED_CONTENT_NOT_STABLE", count, observed, saw_loading
    )


__all__ = ["wait_for_material_dom", "DomSettleResult", "DOM_SAMPLE_JS"]
