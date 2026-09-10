"""Risk-oriented tests for M3 Rendering Desktop/Mobile."""
from __future__ import annotations
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
from threading import Thread
import unittest
from unittest.mock import patch

from playwright.sync_api import sync_playwright

from rasai.acquisition import HttpClient
from rasai.device_context import DEVICE_CONTEXT_ENV
from rasai.discovery import DiscoveryEngine
from rasai.domain import Audit, AuditTarget, DeviceContext, TargetType, new_id
from rasai.m2 import execute_m2
from rasai.m3 import execute_m3
from rasai.persistence import AuditPersistence, AuditWorkspace
from rasai.rendering import (
    BrowserRenderResult,
    BrowserRenderer,
    DESKTOP_PROFILE,
    MOBILE_PROFILE,
    RenderErrorKind,
)


class _RenderingFixtureHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path in {"/robots.txt", "/sitemap.xml"}:
            self._respond(404, "text/plain", b"missing")
            return
        if self.path == "/":
            self._respond(
                200,
                "text/html; charset=utf-8",
                b"""<!doctype html><html><body data-profile=\"raw\"><div id=\"state\">raw</div>
<script>
document.getElementById('state').textContent = 'rendered';
document.body.dataset.profile = (/Mobile/.test(navigator.userAgent) && navigator.maxTouchPoints > 0) ? 'mobile' : 'desktop';
</script></body></html>""",
            )
            return
        self._respond(404, "text/plain", b"missing")

    def _respond(self, status: int, content_type: str, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return


@contextmanager
def _server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _RenderingFixtureHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def _build_m2(origin: str, temp_dir: str):
    audit = Audit(audit_id=new_id("AUD"), project_name="M3 rendering", max_pages=1)
    target = AuditTarget(
        target_id=new_id("TGT"),
        audit_id=audit.audit_id,
        input_url=f"{origin}/",
        normalized_origin=origin,
        target_type=TargetType.URL,
    )
    workspace = AuditWorkspace.create(Path(temp_dir), audit.audit_id)
    persistence = AuditPersistence(workspace)
    m2_result = execute_m2(
        audit,
        target,
        persistence,
        workspace,
        engine=DiscoveryEngine(HttpClient(timeout=1)),
    )
    return workspace, persistence, m2_result


class _LocalizedFailureRenderer:
    def render(self, url: str, device: DeviceContext) -> BrowserRenderResult:
        if device is DeviceContext.MOBILE:
            return BrowserRenderResult(
                requested_url=url,
                final_url=None,
                http_status=None,
                content_type=None,
                rendered_html=None,
                browser_metadata={
                    "engine": "fake",
                    "profile": {"device": device.value, "is_mobile": True, "has_touch": True},
                    "render_error": RenderErrorKind.NAVIGATION_TIMEOUT.value,
                },
                error_kind=RenderErrorKind.NAVIGATION_TIMEOUT,
            )
        return BrowserRenderResult(
            requested_url=url,
            final_url=url,
            http_status=200,
            content_type="text/html",
            rendered_html="<html><body>desktop-rendered</body></html>",
            browser_metadata={
                "engine": "fake",
                "profile": {"device": device.value, "is_mobile": False, "has_touch": False},
                "render_error": None,
            },
        )


class _ControlledHtmlPlaywrightRenderer:
    """Test adapter: execute the already captured fixture HTML in real Chromium without network navigation."""

    def __init__(self, raw_html: str, executable_path: str | None) -> None:
        self.raw_html = raw_html
        self.executable_path = executable_path

    def render(self, url: str, device: DeviceContext) -> BrowserRenderResult:
        profile = DESKTOP_PROFILE if device is DeviceContext.DESKTOP else MOBILE_PROFILE
        with sync_playwright() as playwright:
            options = {"headless": True}
            if self.executable_path:
                options["executable_path"] = self.executable_path
            browser = playwright.chromium.launch(**options)
            try:
                context = browser.new_context(**profile.context_options)
                try:
                    page = context.new_page()
                    page.set_content(self.raw_html, wait_until="domcontentloaded")
                    rendered = page.content()
                    return BrowserRenderResult(
                        requested_url=url,
                        final_url=url,
                        http_status=200,
                        content_type="text/html; charset=utf-8",
                        rendered_html=rendered,
                        browser_metadata={
                            "engine": "chromium-test-fixture",
                            "browser_version": browser.version,
                            "profile": {
                                "device": device.value,
                                "is_mobile": profile.is_mobile,
                                "has_touch": profile.has_touch,
                                "device_scale_factor": profile.device_scale_factor,
                            },
                            "render_error": None,
                        },
                    )
                finally:
                    context.close()
            finally:
                browser.close()


class M3RenderingTests(unittest.TestCase):
    def test_desktop_and_mobile_profiles_are_explicitly_distinct(self) -> None:
        self.assertEqual(DESKTOP_PROFILE.device, DeviceContext.DESKTOP)
        self.assertEqual(MOBILE_PROFILE.device, DeviceContext.MOBILE)
        self.assertFalse(DESKTOP_PROFILE.is_mobile)
        self.assertFalse(DESKTOP_PROFILE.has_touch)
        self.assertTrue(MOBILE_PROFILE.is_mobile)
        self.assertTrue(MOBILE_PROFILE.has_touch)
        self.assertNotEqual(DESKTOP_PROFILE.user_agent, MOBILE_PROFILE.user_agent)
        self.assertNotEqual(DESKTOP_PROFILE.device_scale_factor, MOBILE_PROFILE.device_scale_factor)
        self.assertNotEqual(
            (DESKTOP_PROFILE.viewport_width, DESKTOP_PROFILE.viewport_height),
            (MOBILE_PROFILE.viewport_width, MOBILE_PROFILE.viewport_height),
        )

    def test_snapshots_are_independent_reopenable_and_mobile_failure_is_localized(self) -> None:
        with _server() as origin, TemporaryDirectory() as temp_dir:
            workspace, persistence, m2_result = _build_m2(origin, temp_dir)
            page_id = next(iter(m2_result.page_ids.values()))
            with patch.dict(os.environ, {DEVICE_CONTEXT_ENV: "both"}):
                result = execute_m3(
                    m2_result,
                    persistence,
                    workspace,
                    renderer=_LocalizedFailureRenderer(),
                )
            desktop_id = result.snapshot_ids[page_id][DeviceContext.DESKTOP]
            mobile_id = result.snapshot_ids[page_id][DeviceContext.MOBILE]
            self.assertNotEqual(desktop_id, mobile_id)
            desktop = persistence.snapshots.get(desktop_id)
            mobile = persistence.snapshots.get(mobile_id)
            self.assertEqual(desktop.device, DeviceContext.DESKTOP)
            self.assertEqual(mobile.device, DeviceContext.MOBILE)
            self.assertIsNotNone(desktop.rendered_artifact_ref)
            self.assertIsNone(mobile.rendered_artifact_ref)
            self.assertEqual(desktop.raw_artifact_ref, mobile.raw_artifact_ref)
            self.assertTrue((workspace.root / desktop.rendered_artifact_ref).is_file())
            self.assertEqual(len(result.failures), 1)
            self.assertEqual(result.failures[0].device, DeviceContext.MOBILE)
            self.assertTrue(desktop.browser_metadata["render_succeeded"])
            self.assertFalse(mobile.browser_metadata["render_succeeded"])
            persistence.close()

            with AuditPersistence(AuditWorkspace.open(workspace.root)) as reopened:
                reopened_desktop = reopened.snapshots.get(desktop_id)
                reopened_mobile = reopened.snapshots.get(mobile_id)
                self.assertEqual(reopened_desktop.rendered_artifact_ref, desktop.rendered_artifact_ref)
                self.assertEqual(reopened_mobile.browser_metadata["render_error"], RenderErrorKind.NAVIGATION_TIMEOUT.value)

    def test_javascript_changes_rendered_dom_without_changing_m2_raw_artifact(self) -> None:
        with _server() as origin, TemporaryDirectory() as temp_dir:
            workspace, persistence, m2_result = _build_m2(origin, temp_dir)
            executable = (
                os.environ.get("RASAI_PLAYWRIGHT_CHROMIUM_EXECUTABLE")
                or shutil.which("chromium")
                or shutil.which("chromium-browser")
                or shutil.which("google-chrome")
                or shutil.which("google-chrome-stable")
            )
            page_id = next(iter(m2_result.page_ids.values()))
            raw_ref = m2_result.raw_artifact_refs[f"{origin}/"]
            raw = (workspace.root / raw_ref).read_text(encoding="utf-8")
            with patch.dict(os.environ, {DEVICE_CONTEXT_ENV: "both"}):
                result = execute_m3(
                    m2_result,
                    persistence,
                    workspace,
                    renderer=_ControlledHtmlPlaywrightRenderer(raw, executable),
                )
            self.assertEqual(result.failures, ())
            desktop = persistence.snapshots.get(result.snapshot_ids[page_id][DeviceContext.DESKTOP])
            mobile = persistence.snapshots.get(result.snapshot_ids[page_id][DeviceContext.MOBILE])
            desktop_rendered = (workspace.root / desktop.rendered_artifact_ref).read_text(encoding="utf-8")
            mobile_rendered = (workspace.root / mobile.rendered_artifact_ref).read_text(encoding="utf-8")
            self.assertIn('<div id="state">raw</div>', raw)
            self.assertNotIn('<div id="state">rendered</div>', raw)
            self.assertIn('<div id="state">rendered</div>', desktop_rendered)
            self.assertIn('<div id="state">rendered</div>', mobile_rendered)
            self.assertIn('data-profile="desktop"', desktop_rendered)
            self.assertIn('data-profile="mobile"', mobile_rendered)
            self.assertNotEqual(desktop.rendered_artifact_ref, mobile.rendered_artifact_ref)
            self.assertEqual(desktop.raw_artifact_ref, mobile.raw_artifact_ref)
            persistence.close()


if __name__ == "__main__":
    unittest.main()
