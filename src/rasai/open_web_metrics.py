"""Zero-cost Open Web metrics collected from the existing device browser snapshot.

The collector intentionally creates no navigation and no external API call. It reads
W3C Web Performance API data already present in the live Playwright page before the
optional bounded lazy-loading interaction runs. The resulting evidence is advisory and
must not be presented as an official W3C/Lighthouse score or as RUM.
"""
from __future__ import annotations

from dataclasses import replace
from typing import Any

from playwright.sync_api import Error as PlaywrightError

from rasai.context_scope import ContextScope
from rasai.rendering import BrowserRenderResult


OPEN_WEB_METRICS_CONTRACT_VERSION = "OPEN-WEB-METRICS-001"
DEFAULT_OPEN_WEB_METRICS_ENABLED = True


_CAPTURE_SCRIPT = r"""
async () => {
  const round = value => Number.isFinite(value) ? Math.round(value * 1000) / 1000 : null;
  const positiveDelta = (end, start) => (
    Number.isFinite(end) && Number.isFinite(start) && end >= start ? round(end - start) : null
  );
  const supported = (
    typeof PerformanceObserver !== 'undefined' && Array.isArray(PerformanceObserver.supportedEntryTypes)
  ) ? Array.from(PerformanceObserver.supportedEntryTypes) : [];
  const buffered = {};
  const observers = [];
  const types = [
    'largest-contentful-paint', 'layout-shift', 'longtask', 'event',
    'first-input', 'long-animation-frame'
  ];
  for (const type of types) {
    if (!supported.includes(type)) continue;
    const bucket = [];
    buffered[type] = bucket;
    try {
      const observer = new PerformanceObserver(list => {
        for (const entry of list.getEntries()) {
          const item = {
            name: String(entry.name || ''),
            startTime: round(entry.startTime),
            duration: round(entry.duration)
          };
          if ('value' in entry) item.value = round(entry.value);
          if ('hadRecentInput' in entry) item.hadRecentInput = Boolean(entry.hadRecentInput);
          if ('interactionId' in entry) item.interactionId = Number(entry.interactionId || 0);
          if ('processingStart' in entry) item.processingStart = round(entry.processingStart);
          if ('processingEnd' in entry) item.processingEnd = round(entry.processingEnd);
          if ('renderTime' in entry) item.renderTime = round(entry.renderTime);
          if ('loadTime' in entry) item.loadTime = round(entry.loadTime);
          if ('size' in entry) item.size = round(entry.size);
          bucket.push(item);
        }
      });
      const options = {type, buffered: true};
      if (type === 'event') options.durationThreshold = 16;
      observer.observe(options);
      observers.push(observer);
    } catch (_) {
      buffered[type] = [];
    }
  }
  await new Promise(resolve => setTimeout(resolve, 25));
  for (const observer of observers) {
    try { observer.disconnect(); } catch (_) {}
  }

  const navigation = performance.getEntriesByType('navigation')[0] || null;
  const paints = performance.getEntriesByType('paint') || [];
  const resources = performance.getEntriesByType('resource') || [];
  const marks = performance.getEntriesByType('mark') || [];
  const measures = performance.getEntriesByType('measure') || [];
  const paintByName = {};
  for (const entry of paints) paintByName[String(entry.name || '')] = round(entry.startTime);

  let resourceTransfer = 0;
  let resourceEncoded = 0;
  let resourceDecoded = 0;
  let thirdParty = 0;
  let opaqueSizeEntries = 0;
  const initiators = {};
  const documentOrigin = location.origin;
  for (const entry of resources) {
    const initiator = String(entry.initiatorType || 'other');
    initiators[initiator] = (initiators[initiator] || 0) + 1;
    const transfer = Number(entry.transferSize || 0);
    const encoded = Number(entry.encodedBodySize || 0);
    const decoded = Number(entry.decodedBodySize || 0);
    resourceTransfer += transfer;
    resourceEncoded += encoded;
    resourceDecoded += decoded;
    if (transfer === 0 && encoded === 0 && decoded === 0) opaqueSizeEntries += 1;
    try {
      if (new URL(entry.name, location.href).origin !== documentOrigin) thirdParty += 1;
    } catch (_) {}
  }

  const lcpEntries = buffered['largest-contentful-paint'] || [];
  const lcp = lcpEntries.length ? lcpEntries[lcpEntries.length - 1] : null;
  const layoutEntries = buffered['layout-shift'] || [];
  let cls = 0;
  for (const entry of layoutEntries) {
    if (!entry.hadRecentInput && Number.isFinite(entry.value)) cls += entry.value;
  }
  const longTasks = buffered['longtask'] || [];
  const longFrames = buffered['long-animation-frame'] || [];
  const eventEntries = buffered['event'] || [];
  const interactions = eventEntries.filter(entry => Number(entry.interactionId || 0) > 0);
  const firstInputs = buffered['first-input'] || [];
  const firstInput = firstInputs.length ? firstInputs[0] : null;
  const serverTiming = navigation && Array.isArray(navigation.serverTiming)
    ? navigation.serverTiming : [];

  const durations = entries => entries
    .map(entry => Number(entry.duration || 0))
    .filter(value => Number.isFinite(value) && value >= 0);
  const longTaskDurations = durations(longTasks);
  const longFrameDurations = durations(longFrames);
  const interactionDurations = durations(interactions);

  return {
    capture_after_navigation_ms: round(performance.now()),
    supported_entry_types: supported.sort(),
    navigation: navigation ? {
      type: String(navigation.type || ''),
      redirect_count: Number(navigation.redirectCount || 0),
      next_hop_protocol: String(navigation.nextHopProtocol || ''),
      duration_ms: round(navigation.duration),
      response_start_ms: round(navigation.responseStart),
      response_end_ms: round(navigation.responseEnd),
      dom_interactive_ms: round(navigation.domInteractive),
      dom_content_loaded_end_ms: round(navigation.domContentLoadedEventEnd),
      dom_complete_ms: round(navigation.domComplete),
      load_event_end_ms: round(navigation.loadEventEnd),
      dns_ms: positiveDelta(navigation.domainLookupEnd, navigation.domainLookupStart),
      connect_ms: positiveDelta(navigation.connectEnd, navigation.connectStart),
      tls_ms: navigation.secureConnectionStart > 0
        ? positiveDelta(navigation.connectEnd, navigation.secureConnectionStart) : null,
      request_to_first_byte_ms: positiveDelta(navigation.responseStart, navigation.requestStart),
      ttfb_from_navigation_start_ms: positiveDelta(navigation.responseStart, navigation.startTime),
      response_download_ms: positiveDelta(navigation.responseEnd, navigation.responseStart),
      transfer_size_bytes: Number(navigation.transferSize || 0),
      encoded_body_size_bytes: Number(navigation.encodedBodySize || 0),
      decoded_body_size_bytes: Number(navigation.decodedBodySize || 0),
      server_timing_metric_count: serverTiming.length
    } : null,
    paint: {
      first_paint_ms: paintByName['first-paint'] ?? null,
      first_contentful_paint_ms: paintByName['first-contentful-paint'] ?? null,
      largest_contentful_paint_ms: lcp
        ? round(Math.max(Number(lcp.renderTime || 0), Number(lcp.loadTime || 0), Number(lcp.startTime || 0)))
        : null,
      largest_contentful_paint_size: lcp ? round(lcp.size) : null
    },
    layout: {
      cumulative_layout_shift: round(cls),
      observed_layout_shift_entries: layoutEntries.length
    },
    responsiveness: {
      first_input_delay_ms: firstInput && Number.isFinite(firstInput.processingStart)
        ? positiveDelta(firstInput.processingStart, firstInput.startTime) : null,
      observed_interaction_event_count: interactions.length,
      max_observed_interaction_event_duration_ms: interactionDurations.length
        ? round(Math.max(...interactionDurations)) : null,
      note: interactions.length
        ? 'Observed Event Timing only; not an official INP calculation.'
        : 'No qualifying interaction was observed in this synthetic snapshot; INP is not inferred.'
    },
    main_thread: {
      long_task_count: longTasks.length,
      long_task_total_duration_ms: round(longTaskDurations.reduce((a, b) => a + b, 0)),
      long_task_max_duration_ms: longTaskDurations.length ? round(Math.max(...longTaskDurations)) : null,
      long_animation_frame_count: longFrames.length,
      long_animation_frame_total_duration_ms: round(longFrameDurations.reduce((a, b) => a + b, 0)),
      long_animation_frame_max_duration_ms: longFrameDurations.length ? round(Math.max(...longFrameDurations)) : null
    },
    resources: {
      count: resources.length,
      third_party_count: thirdParty,
      transfer_size_bytes: Math.round(resourceTransfer),
      encoded_body_size_bytes: Math.round(resourceEncoded),
      decoded_body_size_bytes: Math.round(resourceDecoded),
      entries_without_size_visibility: opaqueSizeEntries,
      initiator_counts: initiators
    },
    user_timing: {
      mark_count: marks.length,
      measure_count: measures.length,
      measured_duration_total_ms: round(measures.reduce((sum, entry) => sum + Number(entry.duration || 0), 0))
    },
    document_platform: {
      standards_mode: document.compatMode === 'CSS1Compat',
      doctype_present: Boolean(document.doctype),
      document_language_present: Boolean((document.documentElement.lang || '').trim()),
      charset: String(document.characterSet || ''),
      viewport_meta_present: Boolean(document.querySelector('meta[name="viewport"]')),
      secure_context: Boolean(window.isSecureContext),
      cross_origin_isolated: Boolean(window.crossOriginIsolated)
    }
  };
}
"""


def capture_open_web_metrics(page: Any) -> dict[str, Any]:
    """Read W3C/browser-native metrics from the already loaded page."""
    base: dict[str, Any] = {
        "contract_version": OPEN_WEB_METRICS_CONTRACT_VERSION,
        "state": "UNAVAILABLE",
        "enabled_by_default": True,
        "scope": ContextScope.DEVICE_SNAPSHOT.value,
        "additional_navigation_requests": 0,
        "additional_external_api_calls": 0,
        "score_impact": "NONE",
        "methodology": "W3C Web Performance APIs; same-session browser observation",
        "collector": "Playwright page.evaluate on the existing device snapshot",
    }
    try:
        observed = page.evaluate(_CAPTURE_SCRIPT)
        if not isinstance(observed, dict):
            return {**base, "reason": "UNEXPECTED_BROWSER_RESULT"}
        return {**base, "state": "CAPTURED", **observed}
    except PlaywrightError as exc:
        return {**base, "reason": "PLAYWRIGHT_METRICS_UNAVAILABLE", "error": type(exc).__name__}
    except Exception as exc:
        return {**base, "reason": "METRICS_CAPTURE_FAILED", "error": type(exc).__name__}


def install() -> None:
    """Attach metrics capture to the live device snapshot without replacing navigation."""
    from rasai import device_context_capture as capture_runtime
    from rasai.browser_identity_renderer import BrowserIdentityRenderer

    if getattr(BrowserIdentityRenderer, "_rasai_open_web_metrics", False):
        return

    original_lazy_probe = capture_runtime._same_session_lazy_probe
    original_render_once = BrowserIdentityRenderer._render_once

    def lazy_probe_with_open_metrics(page: Any, rendered_html: str) -> dict[str, Any]:
        metrics = capture_open_web_metrics(page)
        result = original_lazy_probe(page, rendered_html)
        if isinstance(result, dict):
            result = dict(result)
            result["_open_web_metrics"] = metrics
        return result

    def render_once_with_open_metrics(self: Any, **kwargs: Any) -> BrowserRenderResult:
        result = original_render_once(self, **kwargs)
        metadata = dict(result.browser_metadata or {})
        lazy_probe = metadata.get("bounded_lazy_probe")
        metrics = None
        if isinstance(lazy_probe, dict):
            lazy_probe = dict(lazy_probe)
            metrics = lazy_probe.pop("_open_web_metrics", None)
            metadata["bounded_lazy_probe"] = lazy_probe
        if metrics is None and result.succeeded:
            metrics = {
                "contract_version": OPEN_WEB_METRICS_CONTRACT_VERSION,
                "state": "UNAVAILABLE",
                "enabled_by_default": True,
                "scope": ContextScope.DEVICE_SNAPSHOT.value,
                "additional_navigation_requests": 0,
                "additional_external_api_calls": 0,
                "score_impact": "NONE",
                "methodology": "W3C Web Performance APIs; same-session browser observation",
                "reason": "LIVE_PAGE_CAPTURE_HOOK_NOT_REACHED",
            }
        if metrics is not None:
            metadata["open_web_metrics"] = metrics
        return replace(result, browser_metadata=metadata)

    capture_runtime._same_session_lazy_probe = lazy_probe_with_open_metrics
    BrowserIdentityRenderer._render_once = render_once_with_open_metrics
    BrowserIdentityRenderer._rasai_open_web_metrics = True
