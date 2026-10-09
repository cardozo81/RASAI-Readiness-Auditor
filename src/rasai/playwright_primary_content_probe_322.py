"""#322: opt-in Playwright *page-bound* content probe; not an Apdex gateway hook.

The caller must own the existing Playwright page AND provide the navigation
monotonic origin and load boundary captured by that same sample. This helper
never opens a browser, navigates, makes requests, writes SQLite, or modifies
M23/M25. It is not enabled by RASAi production collectors.
"""
from __future__ import annotations

from dataclasses import replace
import math
import time
from typing import Any, Callable

from rasai.apdex_content_readiness_observation import (
    PrimaryContentCheckpoint,
    PrimaryContentReadiness,
    classify_primary_content_readiness,
)


# Small fixed DOM read: avoid innerText layout thrashing, external fetches,
# screenshot/OCR, document-wide text extraction and unbounded polling.
_DOM_SNAPSHOT = """() => {
    const root = document.querySelector('main, article, [role="main"]');
    // textContent includes hidden hydration/bootstrap placeholders. Bound
    // visible text-node traversal to avoid treating offscreen hidden content
    // as materialized; never serialize text, HTML, links or secrets to Python.
    // getClientRects/getComputedStyle introduce a bounded layout read whose
    // cost is separately measured by the experimental overhead pilot.
    const visible = el => {
      if (!el || el.closest('[hidden], [aria-hidden="true"]')) return false;
      const css = window.getComputedStyle(el);
      return css.display !== 'none' && css.visibility !== 'hidden'
        && css.visibility !== 'collapse' && el.getClientRects().length > 0;
    };
    const mainVisible = visible(root);
    const heading = mainVisible
      ? root.querySelector('h1, h2, [role="heading"]') : null;
    const headingChars = visible(heading)
      ? (heading.textContent || '').trim().length : 0;
    let characters = 0;
    let inspected = 0;
    if (mainVisible) {
      const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
      let item;
      while (inspected < 128 && characters < 10000 && (item = walker.nextNode())) {
        inspected++;
        if (visible(item.parentElement)) {
          characters += (item.textContent || '').trim().length;
        }
      }
    }
    const skeleton = !!(root && root.querySelector(
      '[aria-busy="true"], [data-loading="true"], .skeleton, [class*="skeleton"]'
    ));
    return {
      main_text_characters: characters,
      heading_text_characters: headingChars,
      skeleton_present: !mainVisible || skeleton
        || !!(root && root.matches('[aria-busy="true"]'))
    };
}"""


def observe_existing_playwright_page(
    *,
    page: Any,
    sample_id: str,
    context_id: str,
    page_id: str,
    device: str,
    architecture: str,
    navigation_started_monotonic_ns: int | None,
    load_ms: float | None,
    enabled: bool = False,
    window_ms: int = 1200,
    poll_ms: int = 125,
    monotonic_ns: Callable[[], int] = time.monotonic_ns,
    sleep: Callable[[float], None] = time.sleep,
) -> PrimaryContentReadiness:
    """Probe a supplied *existing* browser page; return advisory-only evidence.

    This is deliberately a noninstalled adapter. A future M23/M25 integration
    needs explicit methodology/overhead acceptance, guaranteed same-sample
    identity, and separate persistence. In particular callers must never
    invoke this after the gateway has closed the page or on an M3 page.
    """
    base = dict(
        sample_id=sample_id, context_id=context_id, page_id=page_id,
        device=device, architecture=architecture, load_ms=load_ms,
        enabled=enabled, window_ms=window_ms, strict_provenance=True,
    )
    initial = classify_primary_content_readiness(**base)
    if initial.status in {"NOT_APPLICABLE", "ERROR"}:
        return initial  # Absolutely no browser interaction on opt-out/SSR/UNKNOWN.
    if (
        not isinstance(navigation_started_monotonic_ns, int)
        or isinstance(navigation_started_monotonic_ns, bool)
        or navigation_started_monotonic_ns <= 0
        or not isinstance(poll_ms, int) or isinstance(poll_ms, bool)
        or poll_ms < 100 or poll_ms > 500
    ):
        return replace(initial, status="ERROR", reason="invalid_same_sample_clock_or_poll")
    if load_ms is None or not math.isfinite(float(load_ms)):
        return replace(initial, status="ERROR", reason="invalid_same_sample_load")
    if page is None or not callable(getattr(page, "evaluate", None)):
        return replace(initial, status="ERROR", reason="missing_live_browser_page")

    checkpoints: list[PrimaryContentCheckpoint] = []
    deadline_ns = navigation_started_monotonic_ns + int((load_ms + window_ms) * 1_000_000)
    for _ in range((window_ms // poll_ms) + 2):
        before = monotonic_ns()
        if not isinstance(before, int) or before < navigation_started_monotonic_ns:
            return replace(initial, status="ERROR", reason="inconsistent_monotonic_origin")
        if before >= deadline_ns:
            break
        try:
            dom = page.evaluate(_DOM_SNAPSHOT)
        except Exception:
            # Do not expose an exception potentially containing URL/HTML/secrets.
            return replace(initial, status="ERROR", reason="same_sample_dom_probe_failed")
        after = monotonic_ns()
        if not isinstance(after, int) or after < before:
            return replace(initial, status="ERROR", reason="nonmonotonic_probe_timing")
        elapsed_ms = (after - navigation_started_monotonic_ns) / 1_000_000
        if after > deadline_ns:
            break  # censored; an over-budget evaluation is not proof of readiness
        if not isinstance(dom, dict):
            return replace(initial, status="ERROR", reason="invalid_dom_probe_response")
        main = dom.get("main_text_characters")
        heading = dom.get("heading_text_characters")
        skeleton = dom.get("skeleton_present")
        if (
            type(main) is not int or type(heading) is not int or
            main < 0 or heading < 0 or type(skeleton) is not bool
        ):
            return replace(initial, status="ERROR", reason="invalid_dom_probe_response")
        checkpoints.append(PrimaryContentCheckpoint(
            sample_id, context_id, elapsed_ms, main, heading, skeleton,
            page_id, device,
        ))
        current = classify_primary_content_readiness(**base, checkpoints=checkpoints)
        if current.status in {"OBSERVED", "ERROR"}:
            return current
        remaining_ms = (deadline_ns - after) / 1_000_000
        if remaining_ms < poll_ms:
            break
        sleep(min(poll_ms, remaining_ms) / 1000)
    return classify_primary_content_readiness(
        **base, checkpoints=checkpoints, window_expired=True,
    )
