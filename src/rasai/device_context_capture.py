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
import ipaddress
import re
import time
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from playwright.sync_api import Error as PlaywrightError, TimeoutError as PlaywrightTimeoutError

from rasai.cookie_path import _default_cookie_path
from rasai.context_scope import CONTEXT_SCOPE_CONTRACT_VERSION, ContextScope
from rasai.rendering import BrowserProfile, BrowserRenderResult, RenderErrorKind
from rasai.render_materiality import resolve_capture_quality, unavailable_capture_quality
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
_LAZY_CONTENT_OBSERVATIONS = 8  # only for a known-weak lazy shell after scroll


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


def _observed_resource_metadata(capture: dict[str, Any]) -> dict[str, Any]:
    """Bounded network responses already received in the same browser session."""
    entries = capture.get("resource_responses")
    entries = entries if isinstance(entries, dict) else {}
    items = list(entries.values())[:160]
    return {
        "state": "UNAVAILABLE" if not capture.get("available") else (
            "CAPTURED" if items else "NO_OBSERVATIONS"
        ),
        "capture_method": "SAME_NAVIGATION_CDP_RESPONSE_RECEIVED",
        "additional_network_requests": 0,
        "count": len(items),
        "truncated": capture.get("resource_response_truncated") is True,
        "max_items": 160,
        "items": items,
    }


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
        "resource_responses": {},
        "resource_response_truncated": False,
        "main_response_network": None,
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
            main_id = str(state.get("main_frame_id") or "")
            frame_id = str(event.get("frameId") or "")
            # Only a proven non-main Document qualifies as a subframe.
            if resource_type in {"Stylesheet", "XHR", "Fetch"} or (
                resource_type == "Document" and main_id and frame_id and frame_id != main_id
            ):
                request_id = str(event.get("requestId") or "")
                response = event.get("response")
                if request_id and isinstance(response, dict):
                    if len(state["resource_responses"]) < 160:
                        # Domain-only provenance. Never persist path/query,
                        # request/response headers, addresses or payloads.
                        from rasai.architecture_audit_facts import _public_host
                        raw_status = response.get("status")
                        state["resource_responses"][request_id] = {
                            "resource_type": (
                                resource_type if resource_type != "Document"
                                else "SubframeDocument"
                            ),
                            "host": _public_host(response.get("url")),
                            "status": (
                                int(raw_status)
                                if type(raw_status) in (int, float) and 100 <= raw_status <= 599
                                else None
                            ),
                            "protocol": str(response.get("protocol") or "")[:24],
                            "from_service_worker": bool(response.get("fromServiceWorker")),
                        }
                    else:
                        state["resource_response_truncated"] = True
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
                security = response.get("securityDetails")
                security = security if isinstance(security, dict) else {}
                raw_peer = response.get("remoteIPAddress")
                public_peer = None
                try:
                    peer = ipaddress.ip_address(str(raw_peer))
                    if peer.is_global:
                        public_peer = str(peer)
                except ValueError:
                    pass

                def tls_label(name: str) -> str | None:
                    value = security.get(name)
                    if (not isinstance(value, str) or len(value) > 100 or
                            any(ord(c) < 32 or ord(c) == 127 for c in value)):
                        return None
                    return value

                def tls_time(name: str) -> int | None:
                    value = security.get(name)
                    return int(value) if type(value) in (int, float) and 0 < value < 7258118400 else None

                state["main_response_network"] = {
                    "state": "OBSERVED_MAIN_DOCUMENT_RESPONSE",
                    "capture_method": "SAME_NAVIGATION_CDP_RESPONSE_RECEIVED",
                    "http_protocol": str(response.get("protocol") or "")[:24] or None,
                    "remote_public_peer_ip": public_peer,
                    "remote_public_peer_ip_source": (
                        "CDP_MAIN_DOCUMENT_RESPONSE" if public_peer else None
                    ),
                    "tls_protocol": tls_label("protocol"),
                    "tls_issuer": tls_label("issuer"),
                    "tls_subject": tls_label("subjectName"),
                    "tls_valid_from": tls_time("validFrom"),
                    "tls_valid_to": tls_time("validTo"),
                    "tls_security_details_observed": bool(security),
                    "from_service_worker": bool(response.get("fromServiceWorker")),
                    "from_disk_cache": bool(response.get("fromDiskCache")),
                    "additional_network_requests": 0,
                }
                if not main_frame_id or not frame_id:
                    # Main-frame provenance absent: cannot attribute certificate.
                    state["main_response_network"] = None

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


def _backfill_main_public_peer_from_navigation(response: Any, capture: dict[str, Any]) -> None:
    """Fallback from the same Playwright navigation; never resolve or reconnect.

    A missing CDP remoteIPAddress is not proof of a network block. Attribute
    the peer only when the CDP main-frame response URL matches the navigation.
    """
    observed = capture.get("main_response_network")
    if not isinstance(observed, dict) or observed.get("state") != "OBSERVED_MAIN_DOCUMENT_RESPONSE":
        return
    if (observed.get("remote_public_peer_ip") or observed.get("from_service_worker")
            or observed.get("from_disk_cache")):
        return
    captured_url = capture.get("response_url")
    if not captured_url:
        return
    try:
        if _safe_url(response.url) != captured_url:
            return
        server = response.server_addr()
    except Exception:
        # Optional browser diagnostic: do not fail or retry a successful AUD.
        return
    if not isinstance(server, dict):
        return
    try:
        peer = ipaddress.ip_address(str(server.get("ipAddress") or ""))
    except ValueError:
        return
    if not peer.is_global:
        return
    observed["remote_public_peer_ip"] = str(peer)
    observed["remote_public_peer_ip_source"] = "PLAYWRIGHT_MAIN_NAVIGATION_RESPONSE_SERVER_ADDR"


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



def _safe_cookie_runtime_metadata(page: Any, context: Any) -> dict[str, Any]:
    """Cookie instrumentation is supplementary; never discard captured HTML on failure."""
    try:
        return _cookie_runtime_metadata(page, context)
    except Exception as exc:
        # Exception messages may contain cookie values, URLs or browser secrets.
        return {
            "state": "UNAVAILABLE_CAPTURE_ERROR",
            "capture_method": "EARLY_DOCUMENT_COOKIE+COOKIE_STORE_WRAPPER",
            "additional_network_requests": 0,
            "items": [],
            "limitations": ["COOKIE_RUNTIME_CAPTURE_ERROR"],
            "error_class": type(exc).__name__,
        }

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


def _observe_post_screenshot_dom(
    page: Any, rendered_html: str | None,
    capture_quality: dict[str, Any], screenshot_png: bytes | None,
) -> tuple[dict[str, Any], str | None]:
    """Read one optional late DOM; return only its metadata for persistence."""
    result = {
        "state": "NOT_APPLICABLE",
        "contract_version": "SCREENSHOT-DOM-CORRELATION-001",
    }
    if screenshot_png is None or capture_quality.get("state") != "INCOMPLETE":
        return result, None
    try:
        from rasai.render_materiality import observe_materiality
        baseline = observe_materiality(rendered_html)
        current_html = page.content()
        if not isinstance(current_html, str):
            return {**result, "state": "UNAVAILABLE"}, None
        screenshot_time = observe_materiality(current_html)
        return {
            **result,
            "state": "OBSERVED",
            "captured_dom_sha256": hashlib.sha256(
                (rendered_html or "").encode("utf-8")
            ).hexdigest(),
            "screenshot_time_dom_sha256": hashlib.sha256(
                current_html.encode("utf-8")
            ).hexdigest(),
            "captured_main_text_length": baseline.main_text_length,
            "screenshot_time_main_text_length": screenshot_time.main_text_length,
            "main_text_delta": (
                screenshot_time.main_text_length - baseline.main_text_length
            ),
            "limitation": (
                "Same-session post-screenshot DOM observation; no proof of "
                "image content, indexing or hydration cause."
            ),
        }, current_html
    except (PlaywrightError, TypeError, ValueError, RuntimeError):
        return {**result, "state": "UNAVAILABLE"}, None


def _optional_screenshot_dom_correlation(
    page: Any, rendered_html: str | None,
    capture_quality: dict[str, Any], screenshot_png: bytes | None,
) -> dict[str, Any]:
    """Backward-compatible metadata-only probe for existing callers and tests."""
    return _observe_post_screenshot_dom(
        page, rendered_html, capture_quality, screenshot_png
    )[0]


def _promote_late_materialized_dom(
    rendered_html: str | None,
    capture_quality: dict[str, Any],
    correlation: dict[str, Any],
    observed_html: str | None,
) -> tuple[str | None, dict[str, Any]]:
    """Accept late DOM only while M3 is live and only under the *existing* gate.

    This is not SPA identification. The M6 raw/rendered classifier remains unchanged.
    A successful existing observation is reused (no further page reads or waits).
    """
    if (
        capture_quality.get("state") != "INCOMPLETE"
        or correlation.get("state") != "OBSERVED"
        or not isinstance(observed_html, str)
        or not observed_html
    ):
        return rendered_html, capture_quality

    from rasai.render_materiality import _strong_primary_content, observe_materiality

    observed = observe_materiality(observed_html)
    if not _strong_primary_content(observed):
        return rendered_html, capture_quality

    initial = capture_quality.get("initial")
    if not isinstance(initial, dict):
        initial = observe_materiality(rendered_html).to_dict()
    final = observed.to_dict()
    growth_fields = {
        "text_delta": "text_length",
        "main_text_delta": "main_text_length",
        "primary_text_delta": "primary_text_length",
        "dom_nodes_delta": "dom_nodes",
        "heading_nodes_delta": "heading_nodes",
        "content_nodes_delta": "content_nodes",
        "transient_markers_delta": "transient_markers",
        "lazy_markers_delta": "lazy_markers",
    }
    growth = {
        output: final[key] - int(initial.get(key, 0))
        for output, key in growth_fields.items()
    }
    growth["materialized"] = True
    late_observation = {
        "state": "MATERIALIZED",
        "capture_method": "REUSE_POST_SCREENSHOT_PAGE_CONTENT",
        "additional_navigation_requests": 0,
        "additional_page_content_reads": 0,
        "previous_rendered_sha256": correlation.get("captured_dom_sha256"),
        "accepted_rendered_sha256": correlation.get("screenshot_time_dom_sha256"),
    }
    # Preserve the bounded recovery's original result: it genuinely exhausted.
    # The *later* successful observation is an independently documented phase.
    return observed_html, {
        **capture_quality,
        "state": "RECOVERED",
        "reason": "POST_SCREENSHOT_DOM_MATERIALIZED",
        "materiality_reason": "LATE_SAME_SESSION_PRIMARY_CONTENT",
        "final": final,
        "growth": growth,
        "post_screenshot_recovery": late_observation,
    }


def _same_session_lazy_probe(page: Any, rendered_html: str) -> tuple[dict[str, Any], str | None]:
    """Observe bounded same-page lazy content; return a candidate, not an automatic fact."""
    from rasai.javascript_spa import JavascriptSpaAnalyzer

    analyzer = JavascriptSpaAnalyzer()
    preliminary = analyzer.lazy_loading(rendered_html, after_probe_html=None)
    # The BR-GEO-024 extractor can recover navigation text from a blank
    # product skeleton. M3 uses its stronger, independent materiality gate.
    from rasai.render_materiality import _strong_primary_content, observe_materiality
    materiality = observe_materiality(rendered_html)
    material_at_entry = _strong_primary_content(materiality)
    # DOM class/attribute lazy markers also matter when the legacy GEO rule
    # specifically tests loading=data-src. The M3 recovery gate is wider but
    # only permitted on demonstrably weak primary content.
    has_actionable_lazy = preliminary.has_lazy_signals or materiality.lazy_markers > 0
    result: dict[str, Any] = {
        "scope": ContextScope.DEVICE_SNAPSHOT.value,
        "capture_method": "SAME_PAGE_BOUNDED_SCROLL",
        "additional_navigation_requests": 0,
        "scroll_steps": _LAZY_SCROLL_STEPS,
        "settle_ms": _LAZY_SETTLE_MS,
        "post_scroll_observation_limit": _LAZY_CONTENT_OBSERVATIONS,
        "max_additional_wait_ms": (
            (_LAZY_SCROLL_STEPS + _LAZY_CONTENT_OBSERVATIONS - 1) * _LAZY_SETTLE_MS
        ),
        "viewport_restored_before_screenshot": False,
        "has_lazy_signals": has_actionable_lazy,
        "legacy_rule_lazy_signals": preliminary.has_lazy_signals,
        "initial_content_recoverable": material_at_entry,
        "legacy_extractor_content_recoverable": preliminary.initial_content_recoverable,
        "materiality_gate": "PRIMARY_CONTENT",
        "attempted": False,
        "after_probe_content_recoverable": preliminary.after_probe_content_recoverable,
        "state": "NOT_REQUIRED",
    }
    if not has_actionable_lazy or material_at_entry:
        return result, None

    result["attempted"] = True
    try:
        for _ in range(_LAZY_SCROLL_STEPS):
            page.evaluate("window.scrollBy(0, Math.max(window.innerHeight * 0.8, 1))")
            page.wait_for_timeout(_LAZY_SETTLE_MS)
        # The subsequent M3 screenshot must still represent the initial viewport;
        # the bounded scroll is a materialization gesture, not a screenshot target.
        page.evaluate("window.scrollTo(0, 0)")
        result["viewport_restored_before_screenshot"] = True
        after_html = rendered_html
        after_material = False
        polls = 0
        for index in range(_LAZY_CONTENT_OBSERVATIONS):
            polls += 1
            after_html = page.content()
            after_material = _strong_primary_content(observe_materiality(after_html))
            if after_material:
                break
            if index + 1 < _LAZY_CONTENT_OBSERVATIONS:
                page.wait_for_timeout(_LAZY_SETTLE_MS)
        assessed = analyzer.lazy_loading(rendered_html, after_probe_html=after_html)
        result.update(
            state="CAPTURED",
            post_scroll_observations=polls,
            actual_additional_wait_ms=(
                (_LAZY_SCROLL_STEPS + polls - 1) * _LAZY_SETTLE_MS
            ),
            after_probe_content_recoverable=after_material,
            result=("PASS" if after_material else "FAIL"),
            reason=("CONTENT_RECOVERED_BY_BOUNDED_SCROLL"
                    if after_material else "ESSENTIAL_CONTENT_NOT_RECOVERED_BY_BOUNDED_SCROLL"),
            legacy_extractor_after_recoverable=assessed.after_probe_content_recoverable,
        )
        return result, after_html
    except PlaywrightTimeoutError:
        result.update(state="TIMEOUT", reason="SAME_SESSION_LAZY_PROBE_TIMEOUT")
    except PlaywrightError as exc:
        result.update(state="FAILED", reason="SAME_SESSION_LAZY_PROBE_FAILED", error=type(exc).__name__)
    except Exception as exc:
        result.update(state="FAILED", reason="SAME_SESSION_LAZY_PROBE_FAILED", error=type(exc).__name__)
    return result, None


def _promote_bounded_lazy_dom(
    captured_html: str | None,
    quality: dict[str, Any],
    probe: dict[str, Any],
    candidate_html: str | None,
) -> tuple[str | None, dict[str, Any]]:
    """Only a materialized same-session DOM may replace the unsaved M3 artifact."""
    if (
        quality.get("state") != "INCOMPLETE"
        or probe.get("state") != "CAPTURED"
        or probe.get("after_probe_content_recoverable") is not True
        or not isinstance(candidate_html, str)
    ):
        return captured_html, quality
    from rasai.render_materiality import _strong_primary_content, observe_materiality
    observation = observe_materiality(candidate_html)
    if not _strong_primary_content(observation):
        return captured_html, quality
    initial = quality.get("initial")
    if not isinstance(initial, dict):
        initial = observe_materiality(captured_html).to_dict()
    final = observation.to_dict()
    fields = {
        "text_delta": "text_length",
        "main_text_delta": "main_text_length",
        "primary_text_delta": "primary_text_length",
        "dom_nodes_delta": "dom_nodes",
        "heading_nodes_delta": "heading_nodes",
        "content_nodes_delta": "content_nodes",
        "transient_markers_delta": "transient_markers",
        "lazy_markers_delta": "lazy_markers",
    }
    growth = {label: final[key] - int(initial.get(key, 0)) for label, key in fields.items()}
    growth["materialized"] = True
    return candidate_html, {
        **quality,
        "state": "RECOVERED",
        "reason": "BOUNDED_LAZY_CONTENT_MATERIALIZED",
        "materiality_reason": "SAME_SESSION_LAZY_CONTENT_RECOVERED",
        "final": final,
        "growth": growth,
        "bounded_lazy_recovery": {
            "state": "MATERIALIZED",
            "capture_method": "SAME_PAGE_BOUNDED_SCROLL",
            "additional_navigation_requests": 0,
            "previous_rendered_sha256": hashlib.sha256((captured_html or "").encode("utf-8")).hexdigest(),
            "accepted_rendered_sha256": hashlib.sha256(candidate_html.encode("utf-8")).hexdigest(),
            "scroll_steps": probe.get("scroll_steps"),
            "settle_ms": probe.get("settle_ms"),
        },
    }



def _capture_bound_dom_visibility(renderer: Any, page: Any, rendered_html: str) -> dict[str, Any]:
    """Capture CSS-hidden selectors for the exact frozen M3 rendered DOM only.

    The device-scoped installer overrides BrowserIdentityRenderer._render_once,
    so the canonical computed-style observation must be forwarded here.
    Abstain if the accepted DOM changes before or during this observation.
    """
    unavailable = {
        "version": "dom-visibility-v1",
        "source": "CHROMIUM_COMPUTED_STYLE",
        "status": "UNAVAILABLE",
        "hidden_ids_sha256": [],
        "hidden_classes_sha256": [],
        "inspected": 0,
        "reason": "FROZEN_DOM_MISMATCH_OR_UNAVAILABLE",
    }
    frozen_digest = hashlib.sha256(rendered_html.encode("utf-8")).hexdigest()
    try:
        if hashlib.sha256(page.content().encode("utf-8")).hexdigest() != frozen_digest:
            return unavailable
        observed = renderer._capture_dom_visibility(page)
        if hashlib.sha256(page.content().encode("utf-8")).hexdigest() != frozen_digest:
            return unavailable
        return observed if isinstance(observed, dict) else unavailable
    except (PlaywrightError, TypeError, ValueError, AttributeError):
        return unavailable


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
            if callable(getattr(self, "_rasai_optin_faq_observer", None)):
                context.add_init_script(_FAQ_EGRESS_INIT_SCRIPT)
            try:
                context.add_init_script(_COOKIE_RUNTIME_INIT_SCRIPT)
            except Exception:
                pass
            stage = "NEW_PAGE"
            page = context.new_page()
            # M3 owns this capture nonce; the website and FAQ observer cannot
            # provide or override worker-origin physical page identity.
            from secrets import token_hex
            m3_faq_capture_nonce = (
                token_hex(16) if callable(getattr(self, "_rasai_optin_faq_observer", None))
                else None
            )
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
            navigation_started_ns = time.monotonic_ns()
            response = page.goto(url, wait_until="domcontentloaded", timeout=self.navigation_timeout_ms)
            _backfill_main_public_peer_from_navigation(response, cdp_capture)
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
            stage = "MATERIALITY_GATE"
            rendered_html, capture_quality = resolve_capture_quality(
                page,
                rendered_html,
                settle_outcome=settle_outcome,
            )
            # Before screenshot/artifact identity is frozen, perform the
            # existing bounded lazy probe on this SAME browser page. A nav-heavy
            # skeleton cannot bypass it through a false positive extractor.
            stage = "LAZY_PROBE"
            lazy_probe, lazy_candidate = _same_session_lazy_probe(page, rendered_html)
            rendered_html, capture_quality = _promote_bounded_lazy_dom(
                rendered_html, capture_quality, lazy_probe, lazy_candidate,
            )
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
            cookie_runtime = _safe_cookie_runtime_metadata(page, context)

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

            screenshot_dom_correlation, late_dom = _observe_post_screenshot_dom(
                page, rendered_html, capture_quality, screenshot_png
            )
            rendered_html, capture_quality = _promote_late_materialized_dom(
                rendered_html, capture_quality, screenshot_dom_correlation, late_dom
            )
            if capture_quality.get("post_screenshot_recovery", {}).get("state") == "MATERIALIZED":
                # The authoritative M3 artifact and its metadata MUST hash the same
                # accepted HTML. The early and later hashes remain in correlation.
                rendered_dom = _rendered_dom_metadata(rendered_html)

            # The diagnostic interaction was completed before the authoritative
            # screenshot and DOM artifact were frozen; no second navigation.
            # Noninstalled physical M3 handoff. Opt-in only by the trusted
            # caller owning THIS renderer instance. The snapshot's accepted
            # rendered HTML is already frozen; the callback must refuse
            # a changed DOM rather than replacing the canonical source.
            # Do not persist HTML or secrets in the regular browser metadata.
            experimental_receipt = None
            m3_worker_provenance = None
            observer = getattr(self, "_rasai_optin_faq_observer", None)
            if callable(observer):
                try:
                    # The M3 renderer independently freezes its own pre-action
                    # page/context identity, not a value supplied by the observer.
                    m3_before_html = page.content()
                    m3_before_hash = hashlib.sha256(m3_before_html.encode("utf-8")).hexdigest()
                    m3_page_identity = (
                        len(context.pages) == 1 and context.pages[0] is page
                        and not bool(context.service_workers) and page.url != "about:blank"
                    )
                    m3_before_url = page.url
                    observed = observer(
                        page=page, captured_html_sha256=hashlib.sha256(
                            rendered_html.encode("utf-8")
                        ).hexdigest(),
                        requested_url=url, final_url=page.url,
                        device=profile.device.value,
                        navigation_started_monotonic_ns=navigation_started_ns,
                        load_ms=0.0,
                    )
                    if isinstance(observed, dict):
                        if observed.get("_private_witness") is not None:
                            self._rasai_private_faq_witness = observed["_private_witness"]
                        if (
                            observed.get("status") == "LOCAL_FAQ_ACTION_OBSERVED_NOT_ATTESTED"
                            and self._rasai_private_faq_witness is not None
                            and m3_before_hash == hashlib.sha256(rendered_html.encode("utf-8")).hexdigest()
                            and observed.get("before_sha256") == m3_before_hash
                            and m3_page_identity
                            and len(context.pages) == 1 and context.pages[0] is page
                            and not bool(context.service_workers) and page.url == m3_before_url
                            and m3_faq_capture_nonce is not None
                        ):
                            # Re-read after the gesture from THIS M3 Playwright page.
                            # A collector's self-declared hash is not an attestation.
                            m3_after_hash = hashlib.sha256(page.content().encode("utf-8")).hexdigest()
                            if m3_after_hash == observed.get("after_sha256"):
                                private_scope = getattr(self, "_rasai_m3_capture_scope", None)
                                if (
                                    isinstance(private_scope, dict)
                                    and private_scope.get("requested_url") == url
                                    and private_scope.get("allowed_final_url") == page.url
                                    and private_scope.get("device") == profile.device.value
                                ):
                                    from rasai.m3_faq_capture_provenance import sign_worker_capture
                                    m3_worker_provenance = sign_worker_capture(
                                        scope={
                                            "audit_id": private_scope["audit_id"],
                                            "page_id": private_scope["page_id"],
                                            "snapshot_id": private_scope["snapshot_id"],
                                            "requested_url": url,
                                            "final_url": page.url,
                                            "device": profile.device.value,
                                        },
                                        nonce=m3_faq_capture_nonce,
                                        before_sha256=m3_before_hash,
                                        after_sha256=m3_after_hash,
                                        navigation_started_ns=navigation_started_ns,
                                        observed_ns=time.monotonic_ns(),
                                        same_page_context=True,
                                    )
                        # Strict fixed projection: never accept raw user HTML.
                        experimental_receipt = {
                            "status": str(observed.get("status", "UNVERIFIED"))[:80],
                            "before_sha256": str(observed.get("before_sha256", ""))[:64],
                            "after_sha256": str(observed.get("after_sha256", ""))[:64],
                            "same_aud_sample_verified": False,
                            "score_change_authorized": False,
                        }
                except Exception:
                    experimental_receipt = {
                        "status": "EXPERIMENTAL_OBSERVER_ERROR",
                        "same_aud_sample_verified": False,
                        "score_change_authorized": False,
                    }
            stage = "METADATA"
            metadata = self._metadata(profile, settle_outcome=settle_outcome)
            if experimental_receipt is not None:
                metadata["experimental_faq_same_page_receipt"] = experimental_receipt
            if m3_worker_provenance is not None:
                # Signed by the trusted worker, persisted in canonical M3
                # metadata; no signing key, HTML or private FAQ sidecar here.
                metadata["experimental_faq_m3_worker_provenance"] = m3_worker_provenance
            metadata["profile"]["user_agent"] = identity.get("user_agent")
            metadata["profile"]["locale"] = identity.get("locale")
            metadata["browser_identity"] = {**identity, "channel": self.browser_channel}
            metadata["navigation_trace"] = navigation_trace
            metadata["navigation_request_headers"] = request_headers
            metadata["context_scope_contract"] = CONTEXT_SCOPE_CONTRACT_VERSION
            metadata["capture_scope"] = ContextScope.DEVICE_SNAPSHOT.value
            metadata["document_source"] = document_source
            metadata["rendered_dom"] = rendered_dom
            # #665 R02: the device-scoped _render_once overrides the base
            # renderer's visibility capture. Restore it for the frozen DOM,
            # then M3 binds it to the persisted rendered-artifact SHA-256.
            metadata["dom_visibility"] = _capture_bound_dom_visibility(
                self, page, rendered_html,
            )
            metadata["script_runtime"] = script_runtime
            metadata["network_resource_observations"] = _observed_resource_metadata(cdp_capture)
            metadata["main_response_network"] = cdp_capture.get("main_response_network")
            metadata["cookie_runtime"] = cookie_runtime
            metadata["bounded_lazy_probe"] = lazy_probe
            metadata["capture_quality"] = capture_quality
            metadata["screenshot_dom_correlation"] = screenshot_dom_correlation
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
        metadata["main_response_network"] = {
            "state": "UNAVAILABLE_RENDER_FAILURE",
            "additional_network_requests": 0,
        }
        metadata["network_resource_observations"] = {
            "state": "UNAVAILABLE_RENDER_FAILURE",
            "capture_method": "SAME_NAVIGATION_CDP_RESPONSE_RECEIVED",
            "additional_network_requests": 0,
            "count": 0,
            "truncated": False,
            "items": [],
        }
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
        metadata["capture_quality"] = unavailable_capture_quality(
            settle_outcome="NOT_AVAILABLE",
            reason=(result.error_kind.value if result.error_kind is not None else "RENDER_FAILURE"),
        )
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


_FAQ_EGRESS_INIT_SCRIPT = "\n// Opt-in-only pre-navigation restriction: JS cannot create native\n// WebRTC data channels, WebSockets or EventSource during FAQ capture.\n// This is defense in depth, not a substitute for OS network isolation.\n(() => {\n  for (const name of ['RTCPeerConnection', 'webkitRTCPeerConnection',\n                      'WebSocket', 'EventSource']) {\n    try { Object.defineProperty(globalThis, name,\n      {value: undefined, writable: false, configurable: false}); }\n    catch (_) { /* fail-closed: runtime validates absence below */ }\n  }\n})();\n"

def install() -> None:
    """Install device-scoped capture enrichment idempotently."""
    _install_browser_capture()
