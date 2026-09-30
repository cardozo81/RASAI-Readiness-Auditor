"""Device-scoped browser capture enrichment for the core M3 renderer.

No extra network navigation is introduced. The existing Mobile/Desktop browser run is
used to persist bounded main-document fingerprints, runtime diagnostics and, only when
needed, a bounded lazy-loading interaction on the same live page. Main-source capture is
read from Chromium's already-buffered DevTools response only after the browser reports
that the request finished; RASAi never waits indefinitely for ``response.body()`` and
never re-fetches the page to obtain this evidence.
"""
from __future__ import annotations

import base64
import hashlib
import re
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from playwright.sync_api import Error as PlaywrightError, TimeoutError as PlaywrightTimeoutError

from rasai.context_scope import CONTEXT_SCOPE_CONTRACT_VERSION, ContextScope
from rasai.rendering import BrowserProfile, BrowserRenderResult, RenderErrorKind
from rasai.web_technology_signatures import analyze_script_source, detect_platforms


_MAX_DIAGNOSTICS = 60
_MAX_MESSAGE = 400
_MAX_DOCUMENT_SOURCE_BYTES = 5 * 1024 * 1024

_MAX_SCRIPT_BODY_BYTES = 512 * 1024
_MAX_SCRIPT_BODY_TOTAL_BYTES = 4 * 1024 * 1024
_MAX_SCRIPT_OBSERVATIONS = 80
_MAX_COOKIE_RUNTIME_EVENTS = 80

_COOKIE_RUNTIME_INIT_SCRIPT = r"""
(() => {
  const KEY = "__rasaiCookieRuntimeEvents";
  const LIMIT = 120;
  const events = globalThis[KEY] = Array.isArray(globalThis[KEY]) ? globalThis[KEY] : [];
  const record = (value, mechanism) => {
    try {
      const raw = String(value ?? "");
      const parts = raw.split(";").map(v => v.trim()).filter(Boolean);
      const pair = parts.shift() || "";
      const eq = pair.indexOf("=");
      const name = (eq >= 0 ? pair.slice(0, eq) : pair).trim();
      if (!name) return;
      const attributes = {};
      for (const part of parts) {
        const i = part.indexOf("=");
        const key = (i >= 0 ? part.slice(0, i) : part).trim().toLowerCase();
        const attrValue = (i >= 0 ? part.slice(i + 1) : "").trim();
        if (key === "domain") attributes.domain = attrValue;
        else if (key === "path") attributes.path = attrValue;
        else if (key === "samesite") attributes.samesite = attrValue;
        else if (key === "secure") attributes.secure = true;
      }
      if (events.length < LIMIT) {
        events.push({
          mechanism,
          name,
          attributes,
          at_ms: Number(performance.now() || 0),
          stack: String((new Error()).stack || "")
        });
      }
    } catch (_) {}
  };
  try {
    const descriptor = Object.getOwnPropertyDescriptor(Document.prototype, "cookie");
    if (descriptor && descriptor.get && descriptor.set && descriptor.configurable) {
      Object.defineProperty(Document.prototype, "cookie", {
        configurable: descriptor.configurable,
        enumerable: descriptor.enumerable,
        get() { return descriptor.get.call(this); },
        set(value) {
          record(value, "DOCUMENT_COOKIE");
          return descriptor.set.call(this, value);
        }
      });
    }
  } catch (_) {}
  try {
    const store = globalThis.cookieStore;
    if (store && typeof store.set === "function") {
      const original = store.set.bind(store);
      store.set = function(...args) {
        try {
          const first = args[0];
          if (typeof first === "string") {
            record(first + "=", "COOKIE_STORE");
          } else if (first && typeof first === "object" && first.name) {
            const attrs = [];
            if (first.domain) attrs.push("Domain=" + first.domain);
            if (first.path) attrs.push("Path=" + first.path);
            if (first.sameSite) attrs.push("SameSite=" + first.sameSite);
            if (first.secure) attrs.push("Secure");
            record(String(first.name) + "=;" + attrs.join(";"), "COOKIE_STORE");
          }
        } catch (_) {}
        return original(...args);
      };
    }
  } catch (_) {}
})();
"""
_LAZY_SCROLL_STEPS = 3
_LAZY_SETTLE_MS = 250


def _bounded(value: Any, limit: int = _MAX_MESSAGE) -> str:
    return str(value or "")[:limit]


def _safe_url(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = urlsplit(text)
    except ValueError:
        return None
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return None
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path or "/", "", ""))


def _setup_document_capture(context: Any, page: Any) -> tuple[Any | None, dict[str, Any]]:
    """Observe the existing Chromium navigation without creating another request."""
    state: dict[str, Any] = {
        "available": False,
        "request_id": None,
        "main_frame_id": None,
        "finished": {},
        "failed": set(),
        "response_url": None,
        "setup_error": None,
        "script_requests": {},
        "script_responses": {},
    }
    try:
        session = context.new_cdp_session(page)
        session.send("Network.enable")
        frame_tree = session.send("Page.getFrameTree")
        frame = frame_tree.get("frameTree", {}).get("frame", {}) if isinstance(frame_tree, dict) else {}
        if isinstance(frame, dict) and frame.get("id"):
            state["main_frame_id"] = str(frame["id"])

        def request_will_be_sent(event: dict[str, Any]) -> None:
            if str(event.get("type") or "") != "Script":
                return
            request_id = str(event.get("requestId") or "")
            request = event.get("request")
            if not request_id or not isinstance(request, dict):
                return
            raw_url = str(request.get("url") or "")
            initiator = event.get("initiator")
            initiator_type = str(initiator.get("type") or "") if isinstance(initiator, dict) else ""
            initiator_url = None
            stack = initiator.get("stack") if isinstance(initiator, dict) else None
            frames = stack.get("callFrames") if isinstance(stack, dict) else None
            if isinstance(frames, list):
                for frame in frames:
                    if isinstance(frame, dict) and frame.get("url"):
                        initiator_url = _safe_url(frame.get("url"))
                        if initiator_url:
                            break
            state["script_requests"][request_id] = {
                "raw_url": raw_url,
                "url": _safe_url(raw_url),
                "url_hash": hashlib.sha256(raw_url.encode("utf-8")).hexdigest()[:16] if raw_url else "",
                "initiator_type": initiator_type or None,
                "initiator_url": initiator_url,
            }

        def response_received(event: dict[str, Any]) -> None:
            resource_type = str(event.get("type") or "")
            if resource_type == "Script":
                request_id = str(event.get("requestId") or "")
                response = event.get("response")
                request_info = state["script_requests"].get(request_id, {})
                if request_id and isinstance(response, dict):
                    raw_url = str(response.get("url") or request_info.get("raw_url") or "")
                    state["script_responses"][request_id] = {
                        **request_info,
                        "raw_url": raw_url,
                        "url": _safe_url(raw_url),
                        "url_hash": hashlib.sha256(raw_url.encode("utf-8")).hexdigest()[:16] if raw_url else "",
                        "status": int(response.get("status") or 0),
                        "mime_type": str(response.get("mimeType") or "")[:160],
                        "protocol": str(response.get("protocol") or "")[:40],
                        "from_disk_cache": bool(response.get("fromDiskCache")),
                        "from_service_worker": bool(response.get("fromServiceWorker")),
                    }
                return
            if resource_type != "Document":
                return
            frame_id = str(event.get("frameId") or "")
            main_frame_id = str(state.get("main_frame_id") or "")
            if main_frame_id and frame_id and frame_id != main_frame_id:
                return
            request_id = str(event.get("requestId") or "")
            if not request_id:
                return
            response = event.get("response")
            state["request_id"] = request_id
            if isinstance(response, dict):
                state["response_url"] = _safe_url(response.get("url"))

        def loading_finished(event: dict[str, Any]) -> None:
            request_id = str(event.get("requestId") or "")
            if not request_id:
                return
            try:
                encoded = float(event.get("encodedDataLength") or 0.0)
            except (TypeError, ValueError):
                encoded = 0.0
            state["finished"][request_id] = max(encoded, 0.0)

        def loading_failed(event: dict[str, Any]) -> None:
            request_id = str(event.get("requestId") or "")
            if request_id:
                state["failed"].add(request_id)

        session.on("Network.requestWillBeSent", request_will_be_sent)
        session.on("Network.responseReceived", response_received)
        session.on("Network.loadingFinished", loading_finished)
        session.on("Network.loadingFailed", loading_failed)
        state["available"] = True
        return session, state
    except Exception as exc:
        state["setup_error"] = type(exc).__name__
        return None, state


def _document_source_metadata(
    session: Any | None,
    capture: dict[str, Any],
    *,
    content_type: str | None,
) -> dict[str, Any]:
    """Return a bounded source fingerprint from the already-finished navigation."""
    result: dict[str, Any] = {
        "capture_state": "NOT_AVAILABLE",
        "sha256": None,
        "bytes": None,
        "content_type": content_type,
        "scope": ContextScope.DEVICE_SNAPSHOT.value,
        "additional_network_requests": 0,
        "capture_method": "CDP_BUFFERED_RESPONSE_BODY",
        "max_capture_bytes": _MAX_DOCUMENT_SOURCE_BYTES,
    }
    if session is None or not capture.get("available"):
        result["reason"] = "CDP_SESSION_UNAVAILABLE"
        if capture.get("setup_error"):
            result["error"] = str(capture["setup_error"])
        return result

    request_id = str(capture.get("request_id") or "")
    if not request_id:
        result["reason"] = "MAIN_DOCUMENT_REQUEST_NOT_OBSERVED"
        return result
    result["response_url"] = capture.get("response_url")

    failed = capture.get("failed")
    if isinstance(failed, set) and request_id in failed:
        result.update(capture_state="CAPTURE_FAILED", reason="MAIN_DOCUMENT_LOADING_FAILED")
        return result

    finished = capture.get("finished")
    if not isinstance(finished, dict) or request_id not in finished:
        result.update(
            capture_state="SKIPPED_NOT_FINISHED",
            reason="MAIN_DOCUMENT_NOT_CONFIRMED_FINISHED",
        )
        return result

    encoded_data_length = float(finished.get(request_id) or 0.0)
    result["encoded_data_length"] = encoded_data_length
    if encoded_data_length > _MAX_DOCUMENT_SOURCE_BYTES:
        result.update(
            capture_state="SKIPPED_SIZE_LIMIT",
            reason="MAIN_DOCUMENT_EXCEEDS_CAPTURE_LIMIT",
        )
        return result

    try:
        payload = session.send("Network.getResponseBody", {"requestId": request_id})
        body_value = payload.get("body", "") if isinstance(payload, dict) else ""
        if bool(payload.get("base64Encoded")) if isinstance(payload, dict) else False:
            source_body = base64.b64decode(str(body_value), validate=False)
        else:
            source_body = str(body_value).encode("utf-8")
        if len(source_body) > _MAX_DOCUMENT_SOURCE_BYTES:
            result.update(
                capture_state="SKIPPED_SIZE_LIMIT",
                reason="DECODED_DOCUMENT_EXCEEDS_CAPTURE_LIMIT",
            )
            return result
        result.update(
            capture_state="CAPTURED",
            sha256=hashlib.sha256(source_body).hexdigest(),
            bytes=len(source_body),
        )
    except Exception as exc:
        result.update(
            capture_state="CAPTURE_FAILED",
            reason="CDP_RESPONSE_BODY_UNAVAILABLE",
            error=type(exc).__name__,
        )
    return result



def _party_for_url(resource_url: str | None, page_url: str | None) -> str:
    try:
        resource = urlsplit(str(resource_url or ""))
        page = urlsplit(str(page_url or ""))
    except ValueError:
        return "UNKNOWN"
    if not resource.hostname or not page.hostname:
        return "UNKNOWN"
    return "FIRST_PARTY" if resource.hostname.casefold() == page.hostname.casefold() else "THIRD_PARTY"


def _script_runtime_metadata(session: Any | None, capture: dict[str, Any], page: Any) -> dict[str, Any]:
    result: dict[str, Any] = {
        "state": "NOT_AVAILABLE",
        "capture_method": "CDP_BUFFERED_SCRIPT_BODY+PERFORMANCE_RESOURCE_TIMING",
        "additional_network_requests": 0,
        "max_scripts": _MAX_SCRIPT_OBSERVATIONS,
        "max_script_body_bytes": _MAX_SCRIPT_BODY_BYTES,
        "max_total_body_bytes": _MAX_SCRIPT_BODY_TOTAL_BYTES,
        "items": [],
        "limitations": [],
        "cpu_attribution_state": "NOT_COLLECTED_TO_AVOID_PROFILER_OVERHEAD",
    }
    try:
        timing_rows = page.evaluate(r"""() => performance.getEntriesByType('resource')
          .filter(entry => String(entry.initiatorType || '').toLowerCase() === 'script')
          .slice(0, 120)
          .map(entry => ({
            name: String(entry.name || ''),
            start_time_ms: Number(entry.startTime || 0),
            duration_ms: Number(entry.duration || 0),
            transfer_size_bytes: Number(entry.transferSize || 0),
            encoded_body_size_bytes: Number(entry.encodedBodySize || 0),
            decoded_body_size_bytes: Number(entry.decodedBodySize || 0),
            next_hop_protocol: String(entry.nextHopProtocol || '')
          }))""")
    except Exception:
        timing_rows = []
        result["limitations"].append("RESOURCE_TIMING_UNAVAILABLE")
    timings: dict[str, dict[str, Any]] = {}
    for row in timing_rows if isinstance(timing_rows, list) else []:
        if not isinstance(row, dict):
            continue
        raw_url = str(row.get("name") or "")
        key = hashlib.sha256(raw_url.encode("utf-8")).hexdigest()[:16] if raw_url else ""
        if key:
            timings[key] = {
                "start_time_ms": row.get("start_time_ms"),
                "duration_ms": row.get("duration_ms"),
                "transfer_size_bytes": row.get("transfer_size_bytes"),
                "encoded_body_size_bytes": row.get("encoded_body_size_bytes"),
                "decoded_body_size_bytes": row.get("decoded_body_size_bytes"),
                "next_hop_protocol": str(row.get("next_hop_protocol") or "")[:40],
            }

    if session is None or not capture.get("available"):
        result["limitations"].append("CDP_SESSION_UNAVAILABLE")
        return result
    responses = capture.get("script_responses")
    finished = capture.get("finished")
    if not isinstance(responses, dict):
        responses = {}
    if not isinstance(finished, dict):
        finished = {}
    page_url = str(getattr(page, "url", "") or "")
    total_body_bytes = 0
    truncated = False
    for request_id, raw_item in list(responses.items())[:_MAX_SCRIPT_OBSERVATIONS]:
        if not isinstance(raw_item, dict):
            continue
        item = {key: value for key, value in raw_item.items() if key != "raw_url"}
        url_hash = str(item.get("url_hash") or "")
        item.update(timings.get(url_hash, {}))
        item["party"] = _party_for_url(item.get("url"), page_url)
        item["encoded_data_length"] = float(finished.get(request_id) or 0.0)
        item["body_analysis_state"] = "NOT_AVAILABLE"
        item["content_sha256"] = None
        item["content_bytes"] = None
        item["risk_signals"] = []
        detection_url = str(raw_item.get("raw_url") or item.get("url") or "")
        item["platforms"] = detect_platforms(detection_url, None)
        encoded_length = float(finished.get(request_id) or 0.0)
        if request_id not in finished:
            item["body_analysis_state"] = "NOT_FINISHED"
        elif encoded_length > _MAX_SCRIPT_BODY_BYTES:
            item["body_analysis_state"] = "SKIPPED_SIZE_LIMIT"
        elif total_body_bytes >= _MAX_SCRIPT_BODY_TOTAL_BYTES:
            item["body_analysis_state"] = "SKIPPED_TOTAL_BUDGET"
            truncated = True
        else:
            try:
                payload = session.send("Network.getResponseBody", {"requestId": request_id})
                body_value = payload.get("body", "") if isinstance(payload, dict) else ""
                if bool(payload.get("base64Encoded")) if isinstance(payload, dict) else False:
                    source_body = base64.b64decode(str(body_value), validate=False)
                else:
                    source_body = str(body_value).encode("utf-8")
                if len(source_body) > _MAX_SCRIPT_BODY_BYTES:
                    item["body_analysis_state"] = "SKIPPED_SIZE_LIMIT"
                elif total_body_bytes + len(source_body) > _MAX_SCRIPT_BODY_TOTAL_BYTES:
                    item["body_analysis_state"] = "SKIPPED_TOTAL_BUDGET"
                    truncated = True
                else:
                    total_body_bytes += len(source_body)
                    item["body_analysis_state"] = "ANALYZED"
                    item["content_sha256"] = hashlib.sha256(source_body).hexdigest()
                    item["content_bytes"] = len(source_body)
                    item["risk_signals"] = analyze_script_source(source_body)
                    source_text = source_body.decode("utf-8", errors="ignore")
                    item["platforms"] = detect_platforms(detection_url, source_text)
            except Exception as exc:
                item["body_analysis_state"] = "BODY_UNAVAILABLE"
                item["body_error"] = type(exc).__name__
        result["items"].append(item)
    if len(responses) > _MAX_SCRIPT_OBSERVATIONS:
        result["limitations"].append("SCRIPT_COUNT_LIMIT")
        truncated = True
    if truncated:
        result["limitations"].append("SCRIPT_BODY_BUDGET_LIMIT")
    result["state"] = "CAPTURED" if result["items"] else "NO_SCRIPT_DATA"
    result["count"] = len(result["items"])
    result["total_analyzed_body_bytes"] = total_body_bytes
    return result


_COOKIE_NAME_RE = re.compile(r"^[!#$%&'*+\-.^_\x60|~0-9A-Za-z]{1,128}$")


def _cookie_stack_source(stack: Any) -> str | None:
    text = str(stack or "")
    for candidate in re.findall(r"https?://[^\s)]+", text):
        safe = _safe_url(candidate)
        if safe:
            return safe
    return None


def _cookie_runtime_metadata(page: Any, context: Any | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {
        "state": "NOT_INSTRUMENTED",
        "capture_method": "EARLY_DOCUMENT_COOKIE+COOKIE_STORE_WRAPPER",
        "additional_network_requests": 0,
        "items": [],
        "limitations": [],
        "browser_store_state": "NOT_QUERIED",
    }

    # Cookie values are deliberately discarded. The browser store is consulted only
    # to distinguish an observed setter call from a cookie that is actually present
    # after navigation. Presence after the call corroborates storage; it does not
    # prove that the observed call created a previously absent cookie.
    store_items: list[dict[str, Any]] = []
    if context is not None:
        try:
            raw_store = context.cookies()
        except Exception:
            result["browser_store_state"] = "UNAVAILABLE"
            result["limitations"].append("COOKIE_STORE_QUERY_UNAVAILABLE")
        else:
            result["browser_store_state"] = "CAPTURED"
            for raw_cookie in raw_store if isinstance(raw_store, list) else []:
                if not isinstance(raw_cookie, dict):
                    continue
                raw_name = str(raw_cookie.get("name") or "").strip()
                if not raw_name:
                    continue
                raw_domain = str(raw_cookie.get("domain") or "").strip().casefold()
                domain = raw_domain.lstrip(".")
                path = str(raw_cookie.get("path") or "/")
                store_items.append({
                    "name": raw_name,
                    "name_hash": hashlib.sha256(raw_name.encode("utf-8")).hexdigest()[:12],
                    "domain": domain or None,
                    "path": path if path.startswith("/") else "/",
                    "host_only": bool(raw_domain and not raw_domain.startswith(".")),
                    "secure": bool(raw_cookie.get("secure")),
                    "httponly": bool(raw_cookie.get("httpOnly")),
                    "samesite": str(raw_cookie.get("sameSite") or "")[:40] or None,
                })

    def confirmed_store_item(
        *,
        name: str,
        frame_url: str,
        domain_attribute: str | None,
        path_attribute: str | None,
    ) -> dict[str, Any] | None:
        try:
            frame_host = (urlsplit(frame_url).hostname or "").casefold()
        except ValueError:
            frame_host = ""
        declared_domain = str(domain_attribute or "").strip().casefold().lstrip(".")
        declared_path = str(path_attribute or "")
        effective_path = declared_path if declared_path.startswith("/") else _default_cookie_path(frame_url)
        wanted_domain = declared_domain or frame_host
        matches = [
            item
            for item in store_items
            if item.get("name") == name
            and str(item.get("domain") or "").casefold() == wanted_domain
            and str(item.get("path") or "/") == effective_path
        ]
        return matches[0] if len(matches) == 1 else None
    frames = list(getattr(page, "frames", ()) or ())
    for frame in frames:
        if len(result["items"]) >= _MAX_COOKIE_RUNTIME_EVENTS:
            result["limitations"].append("COOKIE_EVENT_LIMIT")
            break
        try:
            events = frame.evaluate(
                "() => Array.isArray(globalThis.__rasaiCookieRuntimeEvents) ? "
                "globalThis.__rasaiCookieRuntimeEvents : []"
            )
        except Exception:
            continue
        if not isinstance(events, list):
            continue
        for event in events:
            if len(result["items"]) >= _MAX_COOKIE_RUNTIME_EVENTS:
                break
            if not isinstance(event, dict):
                continue
            raw_name = str(event.get("name") or "").strip()
            name_hash = hashlib.sha256(raw_name.encode("utf-8")).hexdigest()[:12] if raw_name else ""
            display_name = raw_name if _COOKIE_NAME_RE.fullmatch(raw_name) else None
            attrs = event.get("attributes") if isinstance(event.get("attributes"), dict) else {}
            setter_script_url = _cookie_stack_source(event.get("stack"))
            frame_url = _safe_url(getattr(frame, "url", None))
            declared_domain = str(attrs.get("domain") or "")[:255] or None
            declared_path = str(attrs.get("path") or "")[:255] or None
            confirmed = confirmed_store_item(
                name=raw_name,
                frame_url=str(frame_url or ""),
                domain_attribute=declared_domain,
                path_attribute=declared_path,
            )
            result["items"].append({
                "mechanism": str(event.get("mechanism") or "UNKNOWN")[:40],
                "cookie_name": display_name,
                "name_hash": name_hash,
                "domain_attribute": declared_domain,
                "path_attribute": declared_path,
                "samesite": str(attrs.get("samesite") or "")[:40] or None,
                "secure": bool(attrs.get("secure")),
                "at_ms": float(event.get("at_ms") or 0.0),
                "frame_url": frame_url,
                "setter_script_url": setter_script_url,
                "attribution_confidence": "MEDIUM" if setter_script_url else "LOW",
                "consent_state_at_creation": "NOT_OBSERVED",
                "created_before_consent": None,
                "store_state": (
                    "CONFIRMED_IN_BROWSER_STORE"
                    if confirmed is not None
                    else "WRITE_ATTEMPT_NOT_CONFIRMED"
                ),
                "confirmed_domain": confirmed.get("domain") if confirmed else None,
                "confirmed_path": confirmed.get("path") if confirmed else None,
                "confirmed_host_only": confirmed.get("host_only") if confirmed else None,
                "confirmed_secure": confirmed.get("secure") if confirmed else None,
                "confirmed_httponly": confirmed.get("httponly") if confirmed else None,
                "confirmed_samesite": confirmed.get("samesite") if confirmed else None,
            })
    result["state"] = "CAPTURED" if result["items"] else "CAPTURED_NO_WRITES"
    result["count"] = len(result["items"])
    return result


def _rendered_dom_metadata(rendered_html: str) -> dict[str, Any]:
    payload = rendered_html.encode("utf-8")
    return {
        "capture_state": "CAPTURED",
        "sha256": hashlib.sha256(payload).hexdigest(),
        "bytes": len(payload),
        "scope": ContextScope.DEVICE_SNAPSHOT.value,
        "additional_network_requests": 0,
        "capture_method": "PLAYWRIGHT_PAGE_CONTENT",
    }


def _same_session_lazy_probe(page: Any, rendered_html: str) -> dict[str, Any]:
    """Run BR-GEO-024's bounded interaction without another page navigation."""
    from rasai.javascript_spa import JavascriptSpaAnalyzer

    analyzer = JavascriptSpaAnalyzer()
    preliminary = analyzer.lazy_loading(rendered_html, after_probe_html=None)
    result: dict[str, Any] = {
        "scope": ContextScope.DEVICE_SNAPSHOT.value,
        "capture_method": "SAME_PAGE_BOUNDED_SCROLL",
        "additional_navigation_requests": 0,
        "scroll_steps": _LAZY_SCROLL_STEPS,
        "settle_ms": _LAZY_SETTLE_MS,
        "has_lazy_signals": preliminary.has_lazy_signals,
        "initial_content_recoverable": preliminary.initial_content_recoverable,
        "attempted": False,
        "after_probe_content_recoverable": preliminary.after_probe_content_recoverable,
        "state": "NOT_REQUIRED",
    }
    if not preliminary.has_lazy_signals or preliminary.initial_content_recoverable:
        return result

    result["attempted"] = True
    try:
        for _ in range(_LAZY_SCROLL_STEPS):
            page.evaluate("window.scrollBy(0, Math.max(window.innerHeight * 0.8, 1))")
            page.wait_for_timeout(_LAZY_SETTLE_MS)
        after_html = page.content()
        assessed = analyzer.lazy_loading(rendered_html, after_probe_html=after_html)
        result.update(
            state="CAPTURED",
            after_probe_content_recoverable=assessed.after_probe_content_recoverable,
            result=assessed.result.value,
            reason=assessed.reason,
        )
    except PlaywrightTimeoutError:
        result.update(state="TIMEOUT", reason="SAME_SESSION_LAZY_PROBE_TIMEOUT")
    except PlaywrightError as exc:
        result.update(state="FAILED", reason="SAME_SESSION_LAZY_PROBE_FAILED", error=type(exc).__name__)
    except Exception as exc:
        result.update(state="FAILED", reason="SAME_SESSION_LAZY_PROBE_FAILED", error=type(exc).__name__)
    return result


def _install_browser_capture() -> None:
    from rasai.browser_identity_renderer import BrowserIdentityRenderer
    from rasai.browser_render_failure import render_failure_context

    if getattr(BrowserIdentityRenderer, "_rasai_context_scope_capture", False):
        return

    def render_once(
        self: Any,
        *,
        url: str,
        profile: BrowserProfile,
        options: dict[str, Any],
        identity: dict[str, Any],
    ) -> BrowserRenderResult:
        context = None
        page = None
        cdp_session = None
        cdp_capture: dict[str, Any] = {}
        settle_outcome = "NOT_ATTEMPTED"
        navigation_trace: list[dict[str, Any]] = []
        request_headers: dict[str, str] = {}
        runtime_diagnostics: list[dict[str, Any]] = []
        stage = "CONTEXT_CREATE"
        failure_context: dict[str, str] | None = None

        def record(kind: str, message: Any, observed_url: Any = None) -> None:
            if len(runtime_diagnostics) >= _MAX_DIAGNOSTICS:
                return
            item: dict[str, Any] = {"type": kind, "message": _bounded(message)}
            safe = _safe_url(observed_url)
            if safe:
                item["url"] = safe
            runtime_diagnostics.append(item)

        try:
            assert self._browser is not None
            context = self._browser.new_context(**options)
            stage = "INIT_SCRIPT"
            try:
                context.add_init_script(_COOKIE_RUNTIME_INIT_SCRIPT)
            except Exception:
                pass
            stage = "NEW_PAGE"
            page = context.new_page()
            page.set_default_timeout(self.navigation_timeout_ms)
            page.set_default_navigation_timeout(self.navigation_timeout_ms)
            stage = "CDP_SETUP"
            cdp_session, cdp_capture = _setup_document_capture(context, page)

            def on_response(response: Any) -> None:
                try:
                    request = response.request
                    if not request.is_navigation_request() or request.frame != page.main_frame:
                        return
                    headers = response.headers
                    navigation_trace.append(
                        {
                            "url": response.url,
                            "status": int(response.status),
                            "location": headers.get("location"),
                        }
                    )
                    if not request_headers:
                        try:
                            all_headers = request.all_headers()
                        except Exception:
                            all_headers = request.headers
                        for name in (
                            "accept-language",
                            "sec-ch-ua",
                            "sec-ch-ua-mobile",
                            "sec-ch-ua-platform",
                            "upgrade-insecure-requests",
                            "user-agent",
                        ):
                            value = all_headers.get(name)
                            if value:
                                request_headers[name] = str(value)
                except Exception:
                    return

            stage = "EVENT_HANDLERS"
            page.on("response", on_response)
            page.on(
                "console",
                lambda message: record("CONSOLE_ERROR", getattr(message, "text", ""))
                if str(getattr(message, "type", "")).casefold() == "error"
                else None,
            )
            page.on("pageerror", lambda error: record("PAGE_ERROR", error))
            page.on(
                "requestfailed",
                lambda request: record(
                    "REQUEST_FAILED",
                    getattr(request, "failure", None) or "request failed",
                    getattr(request, "url", None),
                ),
            )

            stage = "NAVIGATION"
            response = page.goto(url, wait_until="domcontentloaded", timeout=self.navigation_timeout_ms)
            stage = "SETTLE"
            try:
                page.wait_for_load_state("networkidle", timeout=self.settle_timeout_ms)
                settle_outcome = "NETWORKIDLE"
            except PlaywrightTimeoutError:
                # Bounded settle timeout is an expected diagnostic, not a
                # fatal browser failure. Rendering continues from the DOM.
                settle_outcome = "BOUNDED_TIMEOUT"

            stage = "DOM_CAPTURE"
            rendered_html = page.content()
            headers = response.headers if response is not None else {}
            stage = "DOCUMENT_SOURCE"
            document_source = _document_source_metadata(
                cdp_session,
                cdp_capture,
                content_type=headers.get("content-type") if response is not None else None,
            )
            stage = "RENDERED_DOM"
            rendered_dom = _rendered_dom_metadata(rendered_html)
            stage = "SCRIPT_RUNTIME"
            script_runtime = _script_runtime_metadata(cdp_session, cdp_capture, page)
            stage = "COOKIE_RUNTIME"
            cookie_runtime = _cookie_runtime_metadata(page, context)

            screenshot_png: bytes | None = None
            screenshot_state = "NOT_CAPTURED"
            stage = "SCREENSHOT"
            try:
                screenshot_png = page.screenshot(
                    type="png",
                    full_page=False,
                    timeout=self.navigation_timeout_ms,
                )
                screenshot_state = "CAPTURED"
            except PlaywrightError:
                # Screenshot is optional: a visual failure must not invalidate
                # otherwise captured/rendered HTML.
                screenshot_state = "CAPTURE_FAILED"

            observations = ()
            observation_state = "NOT_CAPTURED"
            stage = "DOM_OBSERVATIONS"
            try:
                observations = self._capture_element_observations(page)
                observation_state = "CAPTURED"
            except (PlaywrightError, TypeError, ValueError):
                observation_state = "CAPTURE_FAILED"

            # Primary snapshot evidence above is frozen before any diagnostic interaction.
            # If lazy content needs bounded scrolling, reuse this same page/context instead
            # of closing it and later navigating the URL again in M6.
            stage = "LAZY_PROBE"
            lazy_probe = _same_session_lazy_probe(page, rendered_html)

            stage = "METADATA"
            metadata = self._metadata(profile, settle_outcome=settle_outcome)
            metadata["profile"]["user_agent"] = identity.get("user_agent")
            metadata["profile"]["locale"] = identity.get("locale")
            metadata["browser_identity"] = {**identity, "channel": self.browser_channel}
            metadata["navigation_trace"] = navigation_trace
            metadata["navigation_request_headers"] = request_headers
            metadata["context_scope_contract"] = CONTEXT_SCOPE_CONTRACT_VERSION
            metadata["capture_scope"] = ContextScope.DEVICE_SNAPSHOT.value
            metadata["document_source"] = document_source
            metadata["rendered_dom"] = rendered_dom
            metadata["script_runtime"] = script_runtime
            metadata["cookie_runtime"] = cookie_runtime
            metadata["bounded_lazy_probe"] = lazy_probe
            metadata["runtime_diagnostics"] = {
                "scope": ContextScope.DEVICE_SNAPSHOT.value,
                "count": len(runtime_diagnostics),
                "truncated": len(runtime_diagnostics) >= _MAX_DIAGNOSTICS,
                "items": runtime_diagnostics,
            }
            metadata["visual_snapshot"] = {
                "state": screenshot_state,
                "viewport_width": profile.viewport_width,
                "viewport_height": profile.viewport_height,
            }
            metadata["dom_observations"] = {
                "state": observation_state,
                "count": len(observations),
            }
            return BrowserRenderResult(
                requested_url=url,
                final_url=page.url,
                http_status=response.status if response is not None else None,
                content_type=headers.get("content-type"),
                rendered_html=rendered_html,
                browser_metadata=metadata,
                screenshot_png=screenshot_png,
                element_observations=observations,
            )
        except PlaywrightTimeoutError as exc:
            failure_context = render_failure_context(stage, exc)
            result = self._navigation_failure(
                url=url,
                profile=profile,
                page=page,
                error_kind=RenderErrorKind.NAVIGATION_TIMEOUT,
                identity=identity,
                navigation_trace=navigation_trace,
                request_headers=request_headers,
            )
        except PlaywrightError as exc:
            failure_context = render_failure_context(stage, exc)
            result = self._navigation_failure(
                url=url,
                profile=profile,
                page=page,
                error_kind=RenderErrorKind.NAVIGATION_ERROR,
                identity=identity,
                navigation_trace=navigation_trace,
                request_headers=request_headers,
            )
        except Exception as exc:
            failure_context = render_failure_context(stage, exc)
            result = self._navigation_failure(
                url=url,
                profile=profile,
                page=page,
                error_kind=RenderErrorKind.RENDERER_ERROR,
                identity=identity,
                navigation_trace=navigation_trace,
                request_headers=request_headers,
            )
        else:
            result = None
        finally:
            if cdp_session is not None:
                try:
                    cdp_session.detach()
                except Exception:
                    pass
            if page is not None:
                try:
                    page.close()
                except PlaywrightError:
                    pass
            if context is not None:
                try:
                    context.close()
                except PlaywrightError:
                    pass

        assert result is not None
        metadata = dict(result.browser_metadata)
        if failure_context is not None:
            metadata["render_failure_context"] = failure_context
        metadata["context_scope_contract"] = CONTEXT_SCOPE_CONTRACT_VERSION
        metadata["capture_scope"] = ContextScope.DEVICE_SNAPSHOT.value
        metadata["script_runtime"] = {
            "state": "UNAVAILABLE_RENDER_FAILURE",
            "capture_method": "CDP_BUFFERED_SCRIPT_BODY+PERFORMANCE_RESOURCE_TIMING",
            "additional_network_requests": 0,
            "items": [],
            "limitations": ["RENDER_FAILURE"],
            "cpu_attribution_state": "NOT_COLLECTED_TO_AVOID_PROFILER_OVERHEAD",
        }
        metadata["cookie_runtime"] = {
            "state": "UNAVAILABLE_RENDER_FAILURE",
            "capture_method": "EARLY_DOCUMENT_COOKIE+COOKIE_STORE_WRAPPER",
            "additional_network_requests": 0,
            "items": [],
            "limitations": ["RENDER_FAILURE"],
        }
        metadata["bounded_lazy_probe"] = {
            "scope": ContextScope.DEVICE_SNAPSHOT.value,
            "capture_method": "SAME_PAGE_BOUNDED_SCROLL",
            "additional_navigation_requests": 0,
            "attempted": False,
            "state": "UNAVAILABLE_RENDER_FAILURE",
        }
        metadata["runtime_diagnostics"] = {
            "scope": ContextScope.DEVICE_SNAPSHOT.value,
            "count": len(runtime_diagnostics),
            "truncated": len(runtime_diagnostics) >= _MAX_DIAGNOSTICS,
            "items": runtime_diagnostics,
        }
        return BrowserRenderResult(
            requested_url=result.requested_url,
            final_url=result.final_url,
            http_status=result.http_status,
            content_type=result.content_type,
            rendered_html=result.rendered_html,
            browser_metadata=metadata,
            error_kind=result.error_kind,
            screenshot_png=result.screenshot_png,
            element_observations=result.element_observations,
        )

    BrowserIdentityRenderer._render_once = render_once
    BrowserIdentityRenderer._rasai_context_scope_capture = True


def install() -> None:
    """Install device-scoped capture enrichment idempotently."""
    _install_browser_capture()
