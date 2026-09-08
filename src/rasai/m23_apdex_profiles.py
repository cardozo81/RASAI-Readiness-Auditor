"""Deterministic browser/CPU/network profiles for M23 Synthetic Apdex."""
from __future__ import annotations

from dataclasses import dataclass
from importlib.metadata import version as package_version
import math
import os
import platform
import sys
import time
from typing import Any, Protocol

from playwright.sync_api import Error as PlaywrightError, TimeoutError as PlaywrightTimeoutError, sync_playwright

from rasai.browser_identity_renderer import realistic_context_options
from rasai.domain import DeviceContext
from rasai.rendering import DESKTOP_PROFILE, MOBILE_PROFILE, BrowserProfile

PROFILE_VERSION = "M23-PROFILE-001"


@dataclass(frozen=True, slots=True)
class SyntheticProfile:
    profile_id: str
    device: DeviceContext
    browser_profile: BrowserProfile
    cpu_slowdown: float
    rtt_ms: float
    download_kbps: float
    upload_kbps: float
    connection_type: str

    def validate(self) -> "SyntheticProfile":
        for name, value, minimum in (
            ("cpu_slowdown", self.cpu_slowdown, 1.0),
            ("rtt_ms", self.rtt_ms, 0.0),
            ("download_kbps", self.download_kbps, 0.000001),
            ("upload_kbps", self.upload_kbps, 0.000001),
        ):
            if not math.isfinite(value) or value < minimum:
                raise ValueError(f"{name} must be finite and >= {minimum:g}")
        return self

    def as_dict(self) -> dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "profile_version": PROFILE_VERSION,
            "device": self.device.value,
            "viewport": {
                "width": self.browser_profile.viewport_width,
                "height": self.browser_profile.viewport_height,
            },
            "user_agent": self.browser_profile.user_agent,
            "user_agent_role": "PROFILE_TEMPLATE_ONLY_NOT_EFFECTIVE_RUNTIME_VALUE",
            "effective_user_agent_source": "PLAYWRIGHT_DEVICE_DESCRIPTOR_ALIGNED_TO_RUNTIME_BROWSER",
            "effective_user_agent_persisted": False,
            "browser_identity_strategy": "PLAYWRIGHT_DEVICE_DESCRIPTOR_ALIGNED_TO_RUNTIME_BROWSER",
            "device_scale_factor": self.browser_profile.device_scale_factor,
            "is_mobile": self.browser_profile.is_mobile,
            "has_touch": self.browser_profile.has_touch,
            "cpu_slowdown": self.cpu_slowdown,
            "rtt_ms": self.rtt_ms,
            "download_kbps": self.download_kbps,
            "upload_kbps": self.upload_kbps,
            "connection_type": self.connection_type,
            "cache_policy": "COLD_CONTEXT",
            "randomization": "NONE",
        }


MOBILE_STANDARD_PROFILE = SyntheticProfile(
    profile_id="RASAI_MOBILE_SLOW4G_V1",
    device=DeviceContext.MOBILE,
    browser_profile=MOBILE_PROFILE,
    cpu_slowdown=4.0,
    rtt_ms=150.0,
    download_kbps=1638.4,
    upload_kbps=750.0,
    connection_type="cellular4g",
)

DESKTOP_STANDARD_PROFILE = SyntheticProfile(
    profile_id="RASAI_DESKTOP_DENSE4G_V1",
    device=DeviceContext.DESKTOP,
    browser_profile=DESKTOP_PROFILE,
    cpu_slowdown=1.0,
    rtt_ms=40.0,
    download_kbps=10240.0,
    upload_kbps=10240.0,
    connection_type="ethernet",
)


@dataclass(frozen=True, slots=True)
class NavigationMeasurement:
    status: str
    duration_ms: int | None
    http_status: int | None
    final_url: str | None
    error_code: str | None
    error_message: str | None
    profile_applied: bool
    cpu_method: str | None
    network_method: str | None
    browser_diagnostics: tuple[dict[str, str], ...] = ()


class SyntheticNavigationGateway(Protocol):
    def measure(self, *, url: str, profile: SyntheticProfile, timeout_seconds: float) -> NavigationMeasurement: ...
    def environment(self) -> dict[str, Any]: ...
    def close(self) -> None: ...


def static_host_environment() -> dict[str, Any]:
    """Host data that does not start Chromium; safe for M23-disabled audits."""
    try:
        playwright_version = package_version("playwright")
    except Exception:
        playwright_version = None
    return {
        "system": platform.system(),
        "release": platform.release(),
        "machine": platform.machine(),
        "processor": platform.processor() or None,
        "logical_cpu_count": os.cpu_count(),
        "python_version": sys.version.split()[0],
        "playwright_version": playwright_version,
        "chromium_version": None,
        "browser_identity_strategy": "PLAYWRIGHT_DEVICE_DESCRIPTOR_ALIGNED_TO_RUNTIME_BROWSER",
        "startup_error": None,
    }


class PlaywrightSyntheticNavigationGateway:
    """One Chromium process; a fresh isolated BrowserContext for every sample."""

    def __init__(self, executable_path: str | None = None) -> None:
        self.executable_path = executable_path or os.environ.get("RASAI_PLAYWRIGHT_CHROMIUM_EXECUTABLE")
        self._playwright = None
        self._browser = None
        self._startup_error: str | None = None

    def _start(self) -> None:
        if self._browser is not None or self._startup_error is not None:
            return
        try:
            self._playwright = sync_playwright().start()
            options: dict[str, Any] = {"headless": True}
            if self.executable_path:
                options["executable_path"] = self.executable_path
            self._browser = self._playwright.chromium.launch(**options)
        except Exception as exc:
            self._startup_error = type(exc).__name__
            self.close()

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

    def environment(self) -> dict[str, Any]:
        self._start()
        value = static_host_environment()
        value["chromium_version"] = getattr(self._browser, "version", None) if self._browser is not None else None
        value["startup_error"] = self._startup_error
        return value

    def measure(self, *, url: str, profile: SyntheticProfile, timeout_seconds: float) -> NavigationMeasurement:
        self._start()
        if self._browser is None or self._playwright is None:
            return NavigationMeasurement(
                status="BROWSER_UNAVAILABLE",
                duration_ms=None,
                http_status=None,
                final_url=None,
                error_code=self._startup_error or "BROWSER_UNAVAILABLE",
                error_message=None,
                profile_applied=False,
                cpu_method=None,
                network_method=None,
                browser_diagnostics=(),
            )

        context = page = session = None
        cpu_method = network_method = None
        browser_diagnostics: list[dict[str, str]] = []
        try:
            # Every sample gets a new BrowserContext: no cookie, local/session storage,
            # service-worker storage, or browser-session reuse from another sample.
            context_options, _identity = realistic_context_options(
                self._playwright,
                browser_version=getattr(self._browser, "version", None),
                device=profile.device,
            )
            # Preserve the SyntheticProfile's explicitly versioned viewport semantics.
            context_options["viewport"] = {
                "width": profile.browser_profile.viewport_width,
                "height": profile.browser_profile.viewport_height,
            }
            context_options["device_scale_factor"] = profile.browser_profile.device_scale_factor
            context_options["is_mobile"] = profile.browser_profile.is_mobile
            context_options["has_touch"] = profile.browser_profile.has_touch
            context = self._browser.new_context(**context_options)
            page = context.new_page()

            def record(kind: str, message: str | None, url_value: str | None = None) -> None:
                if len(browser_diagnostics) >= 60:
                    return
                item = {"type": kind, "message": _bounded(message or "", 512) or "-"}
                if url_value:
                    item["url"] = _bounded(url_value, 512) or "-"
                browser_diagnostics.append(item)

            page.on("console", lambda message: record("CONSOLE_ERROR", message.text) if str(message.type).lower() == "error" else None)
            page.on("pageerror", lambda error: record("PAGE_ERROR", str(error)))
            page.on("requestfailed", lambda request: record("REQUEST_FAILED", str(request.failure or "request failed"), request.url))
            session = context.new_cdp_session(page)
            session.send("Network.enable")
            session.send("Network.setCacheDisabled", {"cacheDisabled": True})
            try:
                session.send("Emulation.setCPUThrottlingRate", {"rate": profile.cpu_slowdown})
                cpu_method = "CDP:Emulation.setCPUThrottlingRate"
            except PlaywrightError as exc:
                return _invalid_profile("CPU_PROFILE_ERROR", exc, cpu_method, network_method)

            network_method = _apply_network_profile(session, profile)
            started = time.monotonic()
            try:
                response = page.goto(url, wait_until="load", timeout=int(timeout_seconds * 1000.0))
                duration_ms = int((time.monotonic() - started) * 1000.0)
                http_status = response.status if response is not None else None
                status = "APPLICATION_ERROR" if http_status is not None and http_status >= 400 else "SUCCESS"
                return NavigationMeasurement(
                    status=status,
                    duration_ms=duration_ms,
                    http_status=http_status,
                    final_url=page.url,
                    error_code=None,
                    error_message=None,
                    profile_applied=True,
                    cpu_method=cpu_method,
                    network_method=network_method,
                    browser_diagnostics=tuple(browser_diagnostics),
                )
            except PlaywrightTimeoutError:
                duration_ms = int((time.monotonic() - started) * 1000.0)
                return NavigationMeasurement(
                    status="TIMEOUT",
                    duration_ms=duration_ms,
                    http_status=None,
                    final_url=page.url,
                    error_code="NAVIGATION_TIMEOUT",
                    error_message="navigation exceeded configured timeout",
                    profile_applied=True,
                    cpu_method=cpu_method,
                    network_method=network_method,
                    browser_diagnostics=tuple(browser_diagnostics),
                )
            except PlaywrightError as exc:
                duration_ms = int((time.monotonic() - started) * 1000.0)
                return NavigationMeasurement(
                    status="NAVIGATION_ERROR",
                    duration_ms=duration_ms,
                    http_status=None,
                    final_url=page.url,
                    error_code=type(exc).__name__.upper(),
                    error_message=_bounded(str(exc), 256),
                    profile_applied=True,
                    cpu_method=cpu_method,
                    network_method=network_method,
                    browser_diagnostics=tuple(browser_diagnostics),
                )
        except PlaywrightError as exc:
            return _invalid_profile("PROFILE_SETUP_ERROR", exc, cpu_method, network_method)
        except Exception as exc:
            return _invalid_profile("MEASUREMENT_SETUP_ERROR", exc, cpu_method, network_method)
        finally:
            if session is not None:
                try:
                    session.detach()
                except PlaywrightError:
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


def _apply_network_profile(session: Any, profile: SyntheticProfile) -> str:
    download_bps = profile.download_kbps * 1024.0 / 8.0
    upload_bps = profile.upload_kbps * 1024.0 / 8.0
    try:
        session.send(
            "Network.overrideNetworkState",
            {
                "offline": False,
                "latency": profile.rtt_ms,
                "downloadThroughput": download_bps,
                "uploadThroughput": upload_bps,
                "connectionType": profile.connection_type,
            },
        )
        session.send(
            "Network.emulateNetworkConditionsByRule",
            {
                "offline": False,
                "matchedNetworkConditions": [{
                    "urlPattern": "*",
                    "latency": profile.rtt_ms,
                    "downloadThroughput": download_bps,
                    "uploadThroughput": upload_bps,
                }],
            },
        )
        return "CDP:overrideNetworkState+emulateNetworkConditionsByRule"
    except PlaywrightError:
        session.send(
            "Network.emulateNetworkConditions",
            {
                "offline": False,
                "latency": profile.rtt_ms,
                "downloadThroughput": download_bps,
                "uploadThroughput": upload_bps,
                "connectionType": profile.connection_type,
            },
        )
        return "CDP:Network.emulateNetworkConditions(legacy-fallback)"


def _invalid_profile(
    code: str,
    exc: Exception,
    cpu_method: str | None,
    network_method: str | None,
) -> NavigationMeasurement:
    return NavigationMeasurement(
        status="INVALID_SAMPLE",
        duration_ms=None,
        http_status=None,
        final_url=None,
        error_code=code,
        error_message=_bounded(str(exc), 256),
        profile_applied=False,
        cpu_method=cpu_method,
        network_method=network_method,
    )


def _bounded(value: str | None, limit: int) -> str | None:
    return None if value is None else value[:limit]
