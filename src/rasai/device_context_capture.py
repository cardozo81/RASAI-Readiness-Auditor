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
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from playwright.sync_api import Error as PlaywrightError, TimeoutError as PlaywrightTimeoutError

from rasai.context_scope import CONTEXT_SCOPE_CONTRACT_VERSION, ContextScope
from rasai.rendering import BrowserProfile, BrowserRenderResult, RenderErrorKind


_MAX_DIAGNOSTICS = 60
_MAX_MESSAGE = 400
_MAX_DOCUMENT_SOURCE_BYTES = 5 * 1024 * 1024
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
    }
    try:
        session = context.new_cdp_session(page)
        session.send("Network.enable")
        frame_tree = session.send("Page.getFrameTree")
        frame = frame_tree.get("frameTree", {}).get("frame", {}) if isinstance(frame_tree, dict) else {}
        if isinstance(frame, dict) and frame.get("id"):
            state["main_frame_id"] = str(frame["id"])

        def response_received(event: dict[str, Any]) -> None:
            if str(event.get("type") or "") != "Document":
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
            page = context.new_page()
            page.set_default_timeout(self.navigation_timeout_ms)
            page.set_default_navigation_timeout(self.navigation_timeout_ms)
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

            response = page.goto(url, wait_until="domcontentloaded", timeout=self.navigation_timeout_ms)
            try:
                page.wait_for_load_state("networkidle", timeout=self.settle_timeout_ms)
                settle_outcome = "NETWORKIDLE"
            except PlaywrightTimeoutError:
                settle_outcome = "BOUNDED_TIMEOUT"

            rendered_html = page.content()
            headers = response.headers if response is not None else {}
            document_source = _document_source_metadata(
                cdp_session,
                cdp_capture,
                content_type=headers.get("content-type") if response is not None else None,
            )
            rendered_dom = _rendered_dom_metadata(rendered_html)

            screenshot_png: bytes | None = None
            screenshot_state = "NOT_CAPTURED"
            try:
                screenshot_png = page.screenshot(
                    type="png",
                    full_page=False,
                    timeout=self.navigation_timeout_ms,
                )
                screenshot_state = "CAPTURED"
            except PlaywrightError:
                screenshot_state = "CAPTURE_FAILED"

            observations = ()
            observation_state = "NOT_CAPTURED"
            try:
                observations = self._capture_element_observations(page)
                observation_state = "CAPTURED"
            except (PlaywrightError, TypeError, ValueError):
                observation_state = "CAPTURE_FAILED"

            # Primary snapshot evidence above is frozen before any diagnostic interaction.
            # If lazy content needs bounded scrolling, reuse this same page/context instead
            # of closing it and later navigating the URL again in M6.
            lazy_probe = _same_session_lazy_probe(page, rendered_html)

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
        except PlaywrightTimeoutError:
            result = self._navigation_failure(
                url=url,
                profile=profile,
                page=page,
                error_kind=RenderErrorKind.NAVIGATION_TIMEOUT,
                identity=identity,
                navigation_trace=navigation_trace,
                request_headers=request_headers,
            )
        except PlaywrightError:
            result = self._navigation_failure(
                url=url,
                profile=profile,
                page=page,
                error_kind=RenderErrorKind.NAVIGATION_ERROR,
                identity=identity,
                navigation_trace=navigation_trace,
                request_headers=request_headers,
            )
        except Exception:
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
        metadata["context_scope_contract"] = CONTEXT_SCOPE_CONTRACT_VERSION
        metadata["capture_scope"] = ContextScope.DEVICE_SNAPSHOT.value
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
