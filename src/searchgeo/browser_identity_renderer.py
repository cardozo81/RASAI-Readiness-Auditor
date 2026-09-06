"""Browser renderer with a coherent, browser-like HTTP identity.

The stable M3 renderer historically used a fixed Chrome/127 User-Agent even when
Playwright executed a much newer Chromium. Some CDN/WAF/redirect policies inspect
User-Agent and User-Agent Client Hints together; a version mismatch can therefore
produce a route that a normal browser would not receive.

This renderer keeps SearchGEO stateless (no user cookies/profile reuse), preserves TLS
validation, prefers the locally installed Google Chrome when Playwright can launch it,
and otherwise falls back to bundled Chromium. Desktop and mobile keep SearchGEO's
versioned viewport semantics while borrowing Playwright's current browser descriptors.

When a strict browser navigation fails after an HTTPS -> HTTP redirect on the same
host/www alias, SearchGEO may perform one bounded recovery probe against the HTTPS
version of that insecure hop. This does not ignore TLS and does not rewrite the original
redirect evidence: the original chain and the recovery chain are both persisted.
"""
from __future__ import annotations

from dataclasses import replace
import os
import re
from typing import Any
from urllib.parse import urljoin, urlsplit, urlunsplit

from playwright.sync_api import Error as PlaywrightError, TimeoutError as PlaywrightTimeoutError, sync_playwright

from searchgeo.domain import DeviceContext
from searchgeo.rendering import (
    BrowserProfile,
    BrowserRenderResult,
    BrowserRenderer,
    DESKTOP_PROFILE,
    MOBILE_PROFILE,
    RenderErrorKind,
)

_DEFAULT_LOCALE = "pt-BR"
_SAFE_HEADER_NAMES = (
    "accept-language",
    "sec-ch-ua",
    "sec-ch-ua-mobile",
    "sec-ch-ua-platform",
    "upgrade-insecure-requests",
    "user-agent",
)


def realistic_context_options(
    playwright: Any,
    *,
    browser_version: str | None,
    device: DeviceContext,
    locale: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return coherent context options plus auditable identity metadata.

    Playwright's maintained device descriptors provide a current desktop/mobile browser
    identity. SearchGEO preserves its own viewport and device-scale baseline, while the
    Chrome version token is aligned to the browser binary actually launched.
    """

    profile = DESKTOP_PROFILE if device is DeviceContext.DESKTOP else MOBILE_PROFILE
    descriptor_name = "Desktop Chrome" if device is DeviceContext.DESKTOP else "Pixel 7"
    descriptor = dict(playwright.devices.get(descriptor_name) or {})
    descriptor.pop("default_browser_type", None)

    ua = str(descriptor.get("user_agent") or profile.user_agent)
    ua = _align_chrome_version(ua, browser_version)
    effective_locale = (locale or os.environ.get("SEARCHGEO_BROWSER_LOCALE") or _DEFAULT_LOCALE).strip() or _DEFAULT_LOCALE

    options: dict[str, Any] = {
        "viewport": {"width": profile.viewport_width, "height": profile.viewport_height},
        "user_agent": ua,
        "device_scale_factor": profile.device_scale_factor,
        "is_mobile": profile.is_mobile,
        "has_touch": profile.has_touch,
        "java_script_enabled": True,
        "locale": effective_locale,
        "color_scheme": "light",
    }
    identity = {
        "strategy": "PLAYWRIGHT_DEVICE_DESCRIPTOR_ALIGNED_TO_RUNTIME_BROWSER",
        "descriptor": descriptor_name,
        "locale": effective_locale,
        "user_agent": ua,
        "browser_version": browser_version,
        "stateless_context": True,
        "tls_validation": "ENABLED",
    }
    return options, identity


def secure_upgrade_candidate(
    requested_url: str,
    navigation_trace: Any,
) -> str | None:
    """Return one safe HTTPS recovery candidate from a failed redirect trace.

    The recovery is intentionally narrow:
    - the configured/requested URL must already be HTTPS;
    - the observed redirect must downgrade HTTPS -> HTTP;
    - source and target hosts must differ only by an optional leading ``www.``;
    - credentials and non-standard ports are rejected;
    - only the insecure hop itself is upgraded to HTTPS.

    A returned candidate is merely eligible for one strict-TLS browser probe. It is not
    treated as evidence until that probe produces a valid rendered document.
    """

    try:
        requested = urlsplit(str(requested_url))
    except ValueError:
        return None
    if requested.scheme.casefold() != "https":
        return None
    if not isinstance(navigation_trace, list):
        return None

    for item in navigation_trace:
        if not isinstance(item, dict):
            continue
        source_url = str(item.get("url") or "").strip()
        location = str(item.get("location") or "").strip()
        if not source_url or not location:
            continue
        try:
            source = urlsplit(source_url)
            target = urlsplit(urljoin(source_url, location))
            port = target.port
        except ValueError:
            continue
        if source.scheme.casefold() != "https" or target.scheme.casefold() != "http":
            continue
        if not _same_www_site(source.hostname, target.hostname):
            continue
        if target.username is not None or target.password is not None:
            continue
        if port not in (None, 80):
            continue
        hostname = target.hostname or ""
        if not hostname:
            continue
        if ":" in hostname and not hostname.startswith("["):
            hostname = f"[{hostname}]"
        return urlunsplit(("https", hostname, target.path or "/", target.query, target.fragment))
    return None


class BrowserIdentityRenderer(BrowserRenderer):
    """M3 renderer that uses a coherent Chrome identity and records browser routing."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.browser_channel: str | None = None

    def start(self) -> RenderErrorKind | None:
        if self._browser is not None or self._startup_error is not None:
            return self._startup_error
        try:
            self._playwright = sync_playwright().start()
            launch_options: dict[str, Any] = {"headless": True}
            if self.executable_path:
                launch_options["executable_path"] = self.executable_path
                self._browser = self._playwright.chromium.launch(**launch_options)
                self.browser_channel = "explicit-executable"
            else:
                try:
                    self._browser = self._playwright.chromium.launch(channel="chrome", **launch_options)
                    self.browser_channel = "chrome"
                except PlaywrightError:
                    self._browser = self._playwright.chromium.launch(**launch_options)
                    self.browser_channel = "chromium"
        except Exception:
            self._startup_error = RenderErrorKind.BROWSER_UNAVAILABLE
            self.close()
        return self._startup_error

    def render(self, url: str, device: DeviceContext) -> BrowserRenderResult:
        profile = DESKTOP_PROFILE if device is DeviceContext.DESKTOP else MOBILE_PROFILE
        startup_error = self.start()
        if startup_error is not None or self._browser is None or self._playwright is None:
            return self._failure_result(url, profile, RenderErrorKind.BROWSER_UNAVAILABLE)

        options, identity = realistic_context_options(
            self._playwright,
            browser_version=self._browser.version,
            device=device,
        )
        first = self._render_once(
            url=url,
            profile=profile,
            options=options,
            identity=identity,
        )
        if first.succeeded:
            return first

        original_trace = first.browser_metadata.get("navigation_trace")
        candidate = secure_upgrade_candidate(url, original_trace)
        if candidate is None:
            return first

        recovered = self._render_once(
            url=candidate,
            profile=profile,
            options=options,
            identity=identity,
        )
        recovery_trace = recovered.browser_metadata.get("navigation_trace")
        recovery_metadata = {
            "policy": "STRICT_TLS_SAME_SITE_HTTPS_UPGRADE_V1",
            "trigger": "HTTPS_TO_HTTP_DOWNGRADE_AFTER_NAVIGATION_FAILURE",
            "attempted": True,
            "candidate_url": candidate,
            "succeeded": recovered.succeeded,
            "original_requested_url": url,
            "original_error_kind": first.error_kind.value if first.error_kind is not None else None,
            "original_navigation_trace": original_trace if isinstance(original_trace, list) else [],
            "recovery_navigation_trace": recovery_trace if isinstance(recovery_trace, list) else [],
            "recovery_final_url": recovered.final_url,
            "recovery_http_status": recovered.http_status,
            "tls_validation": "ENABLED",
        }

        if recovered.succeeded:
            metadata = dict(recovered.browser_metadata)
            metadata["secure_redirect_recovery"] = recovery_metadata
            return replace(
                recovered,
                requested_url=url,
                browser_metadata=metadata,
            )

        metadata = dict(first.browser_metadata)
        metadata["secure_redirect_recovery"] = recovery_metadata
        return replace(first, browser_metadata=metadata)

    def _render_once(
        self,
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

        try:
            assert self._browser is not None
            context = self._browser.new_context(**options)
            page = context.new_page()

            def _on_response(response: Any) -> None:
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
                        for name in _SAFE_HEADER_NAMES:
                            value = all_headers.get(name)
                            if value:
                                request_headers[name] = str(value)
                except Exception:
                    return

            page.on("response", _on_response)
            response = page.goto(url, wait_until="domcontentloaded", timeout=self.navigation_timeout_ms)
            try:
                page.wait_for_load_state("networkidle", timeout=self.settle_timeout_ms)
                settle_outcome = "NETWORKIDLE"
            except PlaywrightTimeoutError:
                settle_outcome = "BOUNDED_TIMEOUT"

            rendered_html = page.content()
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
            metadata["visual_snapshot"] = {
                "state": screenshot_state,
                "viewport_width": profile.viewport_width,
                "viewport_height": profile.viewport_height,
            }
            metadata["dom_observations"] = {
                "state": observation_state,
                "count": len(observations),
            }
            headers = response.headers if response is not None else {}
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
            return self._navigation_failure(
                url=url,
                profile=profile,
                page=page,
                error_kind=RenderErrorKind.NAVIGATION_TIMEOUT,
                identity=identity,
                navigation_trace=navigation_trace,
                request_headers=request_headers,
            )
        except PlaywrightError:
            return self._navigation_failure(
                url=url,
                profile=profile,
                page=page,
                error_kind=RenderErrorKind.NAVIGATION_ERROR,
                identity=identity,
                navigation_trace=navigation_trace,
                request_headers=request_headers,
            )
        except Exception:
            return self._navigation_failure(
                url=url,
                profile=profile,
                page=page,
                error_kind=RenderErrorKind.RENDERER_ERROR,
                identity=identity,
                navigation_trace=navigation_trace,
                request_headers=request_headers,
            )
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

    def _navigation_failure(
        self,
        *,
        url: str,
        profile: BrowserProfile,
        page: Any,
        error_kind: RenderErrorKind,
        identity: dict[str, Any],
        navigation_trace: list[dict[str, Any]],
        request_headers: dict[str, str],
    ) -> BrowserRenderResult:
        metadata = self._metadata(profile, settle_outcome="NOT_AVAILABLE", error_kind=error_kind)
        metadata["profile"]["user_agent"] = identity.get("user_agent") or profile.user_agent
        metadata["profile"]["locale"] = identity.get("locale")
        metadata["browser_identity"] = {**identity, "channel": self.browser_channel}
        metadata["navigation_trace"] = navigation_trace
        metadata["navigation_request_headers"] = request_headers
        final_url = None
        if page is not None:
            try:
                observed = str(page.url or "").strip()
                if observed and observed != "about:blank":
                    final_url = observed
            except Exception:
                pass
        return BrowserRenderResult(
            requested_url=url,
            final_url=final_url,
            http_status=None,
            content_type=None,
            rendered_html=None,
            browser_metadata=metadata,
            error_kind=error_kind,
        )


def _align_chrome_version(user_agent: str, browser_version: str | None) -> str:
    if not browser_version:
        return user_agent
    match = re.match(r"\s*(\d+(?:\.\d+){0,3})", str(browser_version))
    if not match:
        return user_agent
    version = match.group(1)
    parts = version.split(".")
    while len(parts) < 4:
        parts.append("0")
    normalized = ".".join(parts[:4])
    return re.sub(r"Chrome/\d+(?:\.\d+){0,3}", f"Chrome/{normalized}", user_agent, count=1)


def _same_www_site(left: str | None, right: str | None) -> bool:
    if not left or not right:
        return False

    def normalize(value: str) -> str:
        host = value.rstrip(".").casefold()
        return host[4:] if host.startswith("www.") else host

    return normalize(left) == normalize(right)
