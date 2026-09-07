"""Controlled Playwright/Chromium rendering for M3."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import os
from typing import Any

from playwright.sync_api import Browser, Error as PlaywrightError, TimeoutError as PlaywrightTimeoutError, sync_playwright

from rasai.domain import DeviceContext


class RenderErrorKind(StrEnum):
    BROWSER_UNAVAILABLE = "BROWSER_UNAVAILABLE"
    NAVIGATION_TIMEOUT = "NAVIGATION_TIMEOUT"
    NAVIGATION_ERROR = "NAVIGATION_ERROR"
    RENDERER_ERROR = "RENDERER_ERROR"


@dataclass(frozen=True, slots=True)
class BrowserProfile:
    device: DeviceContext
    viewport_width: int
    viewport_height: int
    user_agent: str
    device_scale_factor: float
    is_mobile: bool
    has_touch: bool

    @property
    def context_options(self) -> dict[str, Any]:
        return {
            "viewport": {"width": self.viewport_width, "height": self.viewport_height},
            "user_agent": self.user_agent,
            "device_scale_factor": self.device_scale_factor,
            "is_mobile": self.is_mobile,
            "has_touch": self.has_touch,
            "java_script_enabled": True,
        }


DESKTOP_PROFILE = BrowserProfile(
    device=DeviceContext.DESKTOP,
    viewport_width=1440,
    viewport_height=900,
    user_agent=(
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36"
    ),
    device_scale_factor=1.0,
    is_mobile=False,
    has_touch=False,
)

MOBILE_PROFILE = BrowserProfile(
    device=DeviceContext.MOBILE,
    viewport_width=412,
    viewport_height=915,
    user_agent=(
        "Mozilla/5.0 (Linux; Android 14; Pixel 7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Mobile Safari/537.36"
    ),
    device_scale_factor=2.625,
    is_mobile=True,
    has_touch=True,
)

_PROFILES = {
    DeviceContext.DESKTOP: DESKTOP_PROFILE,
    DeviceContext.MOBILE: MOBILE_PROFILE,
}


@dataclass(frozen=True, slots=True)
class RenderedElementObservation:
    """One concrete DOM node observed in the live Chromium document."""

    selector: str | None
    tag_name: str
    element_id: str | None
    classes: tuple[str, ...]
    outer_html: str | None
    text_excerpt: str | None
    bounding_box: dict[str, float] | None


@dataclass(frozen=True, slots=True)
class BrowserRenderResult:
    requested_url: str
    final_url: str | None
    http_status: int | None
    content_type: str | None
    rendered_html: str | None
    browser_metadata: dict[str, Any]
    error_kind: RenderErrorKind | None = None
    screenshot_png: bytes | None = None
    element_observations: tuple[RenderedElementObservation, ...] = ()

    @property
    def succeeded(self) -> bool:
        return self.error_kind is None and self.rendered_html is not None


class BrowserRenderer:
    """Bounded renderer that reuses one Chromium process and isolates each device in its own context."""

    def __init__(
        self,
        *,
        navigation_timeout_ms: int = 15_000,
        settle_timeout_ms: int = 2_000,
        executable_path: str | None = None,
    ) -> None:
        if navigation_timeout_ms <= 0:
            raise ValueError("navigation_timeout_ms must be greater than zero")
        if settle_timeout_ms <= 0:
            raise ValueError("settle_timeout_ms must be greater than zero")
        self.navigation_timeout_ms = navigation_timeout_ms
        self.settle_timeout_ms = settle_timeout_ms
        self.executable_path = executable_path or os.environ.get("RASAI_PLAYWRIGHT_CHROMIUM_EXECUTABLE")
        self._playwright = None
        self._browser: Browser | None = None
        self._startup_error: RenderErrorKind | None = None

    def __enter__(self) -> "BrowserRenderer":
        self.start()
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()

    def start(self) -> RenderErrorKind | None:
        if self._browser is not None or self._startup_error is not None:
            return self._startup_error
        try:
            self._playwright = sync_playwright().start()
            launch_options: dict[str, Any] = {"headless": True}
            if self.executable_path:
                launch_options["executable_path"] = self.executable_path
            self._browser = self._playwright.chromium.launch(**launch_options)
        except Exception:
            self._startup_error = RenderErrorKind.BROWSER_UNAVAILABLE
            self.close()
        return self._startup_error

    def close(self) -> None:
        browser, playwright = self._browser, self._playwright
        self._browser = None
        self._playwright = None
        if browser is not None:
            try:
                browser.close()
            except PlaywrightError:
                pass
        if playwright is not None:
            try:
                playwright.stop()
            except Exception:
                pass

    def render(self, url: str, device: DeviceContext) -> BrowserRenderResult:
        profile = _PROFILES[device]
        startup_error = self.start()
        if startup_error is not None or self._browser is None:
            return self._failure_result(url, profile, RenderErrorKind.BROWSER_UNAVAILABLE)

        context = None
        page = None
        settle_outcome = "NOT_ATTEMPTED"
        try:
            context = self._browser.new_context(**profile.context_options)
            page = context.new_page()
            response = page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=self.navigation_timeout_ms,
            )
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

            observations: tuple[RenderedElementObservation, ...] = ()
            observation_state = "NOT_CAPTURED"
            try:
                observations = self._capture_element_observations(page)
                observation_state = "CAPTURED"
            except (PlaywrightError, TypeError, ValueError):
                observation_state = "CAPTURE_FAILED"

            headers = response.headers if response is not None else {}
            metadata = self._metadata(profile, settle_outcome=settle_outcome)
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
            return self._failure_result(url, profile, RenderErrorKind.NAVIGATION_TIMEOUT)
        except PlaywrightError:
            return self._failure_result(url, profile, RenderErrorKind.NAVIGATION_ERROR)
        except Exception:
            return self._failure_result(url, profile, RenderErrorKind.RENDERER_ERROR)
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

    @staticmethod
    def _capture_element_observations(page: Any) -> tuple[RenderedElementObservation, ...]:
        raw = page.evaluate(
            r"""
            () => {
              const selectorFor = (el) => {
                if (!(el instanceof Element)) return null;
                if (el.id) {
                  const byId = `#${CSS.escape(el.id)}`;
                  try {
                    if (document.querySelectorAll(byId).length === 1) return byId;
                  } catch (_) {}
                }

                const parts = [];
                let node = el;
                while (node && node instanceof Element) {
                  let part = node.tagName.toLowerCase();
                  const classes = Array.from(node.classList || [])
                    .filter((item) => item && item.length <= 80)
                    .slice(0, 3);
                  if (classes.length) {
                    part += '.' + classes.map((item) => CSS.escape(item)).join('.');
                  }

                  const parent = node.parentElement;
                  if (parent) {
                    const sameTag = Array.from(parent.children)
                      .filter((item) => item.tagName === node.tagName);
                    if (sameTag.length > 1) {
                      part += `:nth-of-type(${sameTag.indexOf(node) + 1})`;
                    }
                  }
                  parts.unshift(part);
                  const candidate = parts.join(' > ');
                  try {
                    if (candidate && document.querySelectorAll(candidate).length === 1) {
                      return candidate;
                    }
                  } catch (_) {}
                  if (!parent || node === document.documentElement) break;
                  node = parent;
                }
                return null;
              };

              const candidates = new Set(document.querySelectorAll(
                'title,meta[name="robots" i],link[rel~="canonical" i],main,[role="main"],h1,h2,h3,h4,h5,h6,script[type="application/ld+json"]'
              ));

              return Array.from(candidates).slice(0, 250).map((el) => {
                const rect = el.getBoundingClientRect();
                const style = window.getComputedStyle(el);
                const visible = rect.width > 0 && rect.height > 0 &&
                  style.display !== 'none' && style.visibility !== 'hidden' &&
                  Number(style.opacity || 1) !== 0 &&
                  rect.bottom > 0 && rect.right > 0 &&
                  rect.top < window.innerHeight && rect.left < window.innerWidth;
                const html = typeof el.outerHTML === 'string' ? el.outerHTML : '';
                const text = (el.innerText || el.textContent || '').replace(/\s+/g, ' ').trim();
                return {
                  selector: selectorFor(el),
                  tag_name: el.tagName.toLowerCase(),
                  element_id: el.id || null,
                  classes: Array.from(el.classList || []).slice(0, 12),
                  outer_html: html ? html.slice(0, 4096) : null,
                  text_excerpt: text ? text.slice(0, 512) : null,
                  bounding_box: visible ? {
                    x: rect.x,
                    y: rect.y,
                    width: rect.width,
                    height: rect.height
                  } : null
                };
              });
            }
            """
        )
        if not isinstance(raw, list):
            return ()
        observations: list[RenderedElementObservation] = []
        for item in raw:
            if not isinstance(item, dict) or not isinstance(item.get("tag_name"), str):
                continue
            box_value = item.get("bounding_box")
            box: dict[str, float] | None = None
            if isinstance(box_value, dict):
                try:
                    box = {
                        key: float(box_value[key])
                        for key in ("x", "y", "width", "height")
                    }
                except (KeyError, TypeError, ValueError):
                    box = None
            observations.append(
                RenderedElementObservation(
                    selector=item.get("selector") if isinstance(item.get("selector"), str) else None,
                    tag_name=item["tag_name"],
                    element_id=item.get("element_id") if isinstance(item.get("element_id"), str) else None,
                    classes=tuple(str(value) for value in item.get("classes", ()) if isinstance(value, str)),
                    outer_html=item.get("outer_html") if isinstance(item.get("outer_html"), str) else None,
                    text_excerpt=item.get("text_excerpt") if isinstance(item.get("text_excerpt"), str) else None,
                    bounding_box=box,
                )
            )
        return tuple(observations)

    def _metadata(self, profile: BrowserProfile, *, settle_outcome: str, error_kind: RenderErrorKind | None = None) -> dict[str, Any]:
        return {
            "engine": "chromium",
            "browser_version": self._browser.version if self._browser is not None else None,
            "headless": True,
            "profile": {
                "device": profile.device.value,
                "viewport": {"width": profile.viewport_width, "height": profile.viewport_height},
                "user_agent": profile.user_agent,
                "device_scale_factor": profile.device_scale_factor,
                "is_mobile": profile.is_mobile,
                "has_touch": profile.has_touch,
                "javascript_enabled": True,
            },
            "navigation": {
                "wait_until": "domcontentloaded",
                "timeout_ms": self.navigation_timeout_ms,
                "settle_strategy": "networkidle-bounded",
                "settle_timeout_ms": self.settle_timeout_ms,
                "settle_outcome": settle_outcome,
            },
            "render_error": error_kind.value if error_kind is not None else None,
        }

    def _failure_result(
        self,
        url: str,
        profile: BrowserProfile,
        error_kind: RenderErrorKind,
    ) -> BrowserRenderResult:
        return BrowserRenderResult(
            requested_url=url,
            final_url=None,
            http_status=None,
            content_type=None,
            rendered_html=None,
            browser_metadata=self._metadata(
                profile,
                settle_outcome="NOT_AVAILABLE",
                error_kind=error_kind,
            ),
            error_kind=error_kind,
        )
