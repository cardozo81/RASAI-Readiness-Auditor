"""Process-isolated wall-clock deadline for the normal M3 browser session.

Playwright's synchronous API has operation-level timeouts, but a browser/driver defect can
still leave an individual call wedged.  A thread timeout is unsafe because Playwright is
thread-affine and the timed-out thread would keep running.  This adapter therefore owns
the normal BrowserIdentityRenderer in one persistent child process.  The process is reused
for healthy URL/device contexts and is terminated only when a context exceeds the complete
wall-clock budget.  The timed-out URL is not retried automatically; the next context starts
with a fresh browser worker.
"""
from __future__ import annotations

import multiprocessing as mp
import os
from multiprocessing.connection import Connection
from typing import Any

from rasai.domain import DeviceContext
from rasai.rendering import BrowserRenderResult, BrowserRenderer, RenderErrorKind

_ENV = "RASAI_M3_RENDER_WALLCLOCK_SECONDS"
_DEFAULT_SECONDS = 60.0
_MIN_SECONDS = 5.0
_MAX_SECONDS = 600.0
_INSTALLED = False


def configured_wallclock_seconds() -> float:
    raw = (os.environ.get(_ENV) or "").strip()
    if not raw:
        return _DEFAULT_SECONDS
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError(f"{_ENV} must be a number between {_MIN_SECONDS:g} and {_MAX_SECONDS:g}") from exc
    if not (_MIN_SECONDS <= value <= _MAX_SECONDS):
        raise ValueError(f"{_ENV} must be between {_MIN_SECONDS:g} and {_MAX_SECONDS:g} seconds")
    return value


def _failure(url: str, device: DeviceContext, reason: str, *, seconds: float) -> BrowserRenderResult:
    return BrowserRenderResult(
        requested_url=url,
        final_url=None,
        http_status=None,
        content_type=None,
        rendered_html=None,
        browser_metadata={
            "engine": "isolated-browser-identity-renderer",
            "profile": {"device": device.value},
            "render_error": RenderErrorKind.RENDERER_ERROR.value,
            "render_failure_reason": reason,
            "wallclock_deadline_seconds": seconds,
            "automatic_retry": False,
        },
        error_kind=RenderErrorKind.RENDERER_ERROR,
    )


def _worker(
    connection: Connection,
    navigation_timeout_ms: int,
    settle_timeout_ms: int,
    executable_path: str | None,
) -> None:
    # Windows uses spawn, so runtime monkeypatches from the parent are not inherited.
    # Install the bounded capture contract explicitly inside the browser owner process.
    from rasai.device_context_capture import install as install_device_context_capture
    from rasai.browser_identity_renderer import BrowserIdentityRenderer

    install_device_context_capture()
    renderer = BrowserIdentityRenderer(
        navigation_timeout_ms=navigation_timeout_ms,
        settle_timeout_ms=settle_timeout_ms,
        executable_path=executable_path,
    )
    try:
        with renderer:
            while True:
                try:
                    message = connection.recv()
                except EOFError:
                    return
                if not isinstance(message, dict):
                    continue
                command = message.get("command")
                if command == "stop":
                    return
                if command != "render":
                    continue
                try:
                    device = DeviceContext(str(message["device"]))
                    result = renderer.render(
                        str(message["url"]),
                        device,
                        preflight_navigation_trace=message.get("preflight_navigation_trace"),
                    )
                    connection.send({"ok": True, "result": result})
                except BaseException as exc:
                    try:
                        connection.send(
                            {
                                "ok": False,
                                "error_type": type(exc).__name__,
                                "error_message": str(exc)[:512],
                            }
                        )
                    except Exception:
                        return
    finally:
        try:
            connection.close()
        except Exception:
            pass


class IsolatedBrowserIdentityRenderer(BrowserRenderer):
    """Drop-in BrowserIdentityRenderer contract with a killable context deadline."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.wallclock_seconds = configured_wallclock_seconds()
        self._process: mp.Process | None = None
        self._connection: Connection | None = None
        self.browser_channel = "isolated-worker"

    def __enter__(self) -> "IsolatedBrowserIdentityRenderer":
        self._ensure_worker()
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()

    def start(self) -> RenderErrorKind | None:
        self._ensure_worker()
        return None if self._process is not None and self._process.is_alive() else RenderErrorKind.BROWSER_UNAVAILABLE

    def close(self) -> None:
        connection, process = self._connection, self._process
        self._connection = None
        self._process = None
        if connection is not None:
            try:
                if process is not None and process.is_alive():
                    connection.send({"command": "stop"})
            except Exception:
                pass
        if process is not None:
            process.join(timeout=2.0)
            if process.is_alive():
                process.terminate()
                process.join(timeout=2.0)
            if process.is_alive() and hasattr(process, "kill"):
                process.kill()
                process.join(timeout=1.0)
        if connection is not None:
            try:
                connection.close()
            except Exception:
                pass

    def _drop_worker(self) -> None:
        connection, process = self._connection, self._process
        self._connection = None
        self._process = None
        if connection is not None:
            try:
                connection.close()
            except Exception:
                pass
        if process is not None and process.is_alive():
            process.terminate()
            process.join(timeout=2.0)
            if process.is_alive() and hasattr(process, "kill"):
                process.kill()
                process.join(timeout=1.0)

    def _ensure_worker(self) -> None:
        if self._process is not None and self._process.is_alive() and self._connection is not None:
            return
        self._drop_worker()
        context = mp.get_context("spawn")
        parent, child = context.Pipe(duplex=True)
        process = context.Process(
            target=_worker,
            args=(child, self.navigation_timeout_ms, self.settle_timeout_ms, self.executable_path),
            name="rasai-m3-browser",
            daemon=False,
        )
        process.start()
        child.close()
        self._connection = parent
        self._process = process

    def render(
        self,
        url: str,
        device: DeviceContext,
        *,
        preflight_navigation_trace: Any = None,
    ) -> BrowserRenderResult:
        self._ensure_worker()
        connection, process = self._connection, self._process
        if connection is None or process is None or not process.is_alive():
            self._drop_worker()
            return _failure(url, device, "BROWSER_WORKER_UNAVAILABLE", seconds=self.wallclock_seconds)
        try:
            connection.send(
                {
                    "command": "render",
                    "url": url,
                    "device": device.value,
                    "preflight_navigation_trace": preflight_navigation_trace,
                }
            )
        except Exception:
            self._drop_worker()
            return _failure(url, device, "BROWSER_WORKER_SEND_FAILED", seconds=self.wallclock_seconds)

        if not connection.poll(self.wallclock_seconds):
            self._drop_worker()
            return _failure(url, device, "RENDER_WALLCLOCK_TIMEOUT", seconds=self.wallclock_seconds)
        try:
            response = connection.recv()
        except (EOFError, OSError):
            self._drop_worker()
            return _failure(url, device, "BROWSER_WORKER_EXITED", seconds=self.wallclock_seconds)
        if isinstance(response, dict) and response.get("ok") and isinstance(response.get("result"), BrowserRenderResult):
            return response["result"]
        reason = "BROWSER_WORKER_RENDER_EXCEPTION"
        if isinstance(response, dict) and response.get("error_type"):
            reason += ":" + str(response["error_type"])
        return _failure(url, device, reason, seconds=self.wallclock_seconds)


def install() -> None:
    """Replace only the default M3 renderer reference; injected test renderers stay direct."""
    global _INSTALLED
    if _INSTALLED:
        return
    from rasai import m3

    m3.BrowserIdentityRenderer = IsolatedBrowserIdentityRenderer
    _INSTALLED = True
