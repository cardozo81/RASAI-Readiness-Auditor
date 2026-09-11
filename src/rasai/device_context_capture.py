"""Device-scoped browser capture enrichment for the core M3 renderer.

No extra network navigation is introduced. The existing Mobile/Desktop browser run is
used to persist a hash of the main-document response and bounded runtime diagnostics.
This makes device variance observable without re-fetching origin-scoped resources.
"""
from __future__ import annotations

import hashlib
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from playwright.sync_api import Error as PlaywrightError, TimeoutError as PlaywrightTimeoutError

from rasai.context_scope import CONTEXT_SCOPE_CONTRACT_VERSION, ContextScope
from rasai.rendering import BrowserProfile, BrowserRenderResult, RenderErrorKind


_MAX_DIAGNOSTICS = 60
_MAX_MESSAGE = 400


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
            document_source: dict[str, Any] = {
                "capture_state": "NOT_AVAILABLE",
                "sha256": None,
                "bytes": None,
                "content_type": headers.get("content-type") if response is not None else None,
                "scope": ContextScope.DEVICE_SNAPSHOT.value,
                "additional_network_requests": 0,
            }
            if response is not None:
                try:
                    source_body = response.body()
                    document_source.update(
                        capture_state="CAPTURED",
                        sha256=hashlib.sha256(source_body).hexdigest(),
                        bytes=len(source_body),
                    )
                except Exception as exc:
                    document_source.update(
                        capture_state="CAPTURE_FAILED",
                        error=type(exc).__name__,
                    )

            screenshot_png: bytes | None = None
            screenshot_state = "NOT_CAPTURED"
            try:
                screenshot_png = page.screenshot(type="png", full_page=False)
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

            metadata = self._metadata(profile, settle_outcome=settle_outcome)
            metadata["profile"]["user_agent"] = identity.get("user_agent")
            metadata["profile"]["locale"] = identity.get("locale")
            metadata["browser_identity"] = {**identity, "channel": self.browser_channel}
            metadata["navigation_trace"] = navigation_trace
            metadata["navigation_request_headers"] = request_headers
            metadata["context_scope_contract"] = CONTEXT_SCOPE_CONTRACT_VERSION
            metadata["capture_scope"] = ContextScope.DEVICE_SNAPSHOT.value
            metadata["document_source"] = document_source
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
