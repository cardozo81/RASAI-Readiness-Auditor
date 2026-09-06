from __future__ import annotations

import unittest

from searchgeo.browser_identity_renderer import (
    BrowserIdentityRenderer,
    realistic_context_options,
    secure_upgrade_candidate,
)
from searchgeo.domain import DeviceContext
from searchgeo.rendering import BrowserRenderResult, RenderErrorKind


class _FakePlaywright:
    devices = {
        "Desktop Chrome": {
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36",
            "viewport": {"width": 1280, "height": 720},
            "device_scale_factor": 1,
            "is_mobile": False,
            "has_touch": False,
            "default_browser_type": "chromium",
        },
        "Pixel 7": {
            "user_agent": "Mozilla/5.0 (Linux; Android 14; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Mobile Safari/537.36",
            "viewport": {"width": 412, "height": 839},
            "device_scale_factor": 2.625,
            "is_mobile": True,
            "has_touch": True,
            "default_browser_type": "chromium",
        },
    }


class _FakeBrowser:
    version = "151.0.7922.34"


class _RecoveryRenderer(BrowserIdentityRenderer):
    def __init__(self, *, recovery_succeeds: bool = True) -> None:
        super().__init__()
        self._browser = _FakeBrowser()
        self._playwright = _FakePlaywright()
        self.browser_channel = "chrome"
        self.calls: list[str] = []
        self.recovery_succeeds = recovery_succeeds

    def start(self):
        return None

    def _render_once(self, *, url, profile, options, identity):
        self.calls.append(url)
        if len(self.calls) == 1:
            return BrowserRenderResult(
                requested_url=url,
                final_url=None,
                http_status=None,
                content_type=None,
                rendered_html=None,
                browser_metadata={
                    "navigation_trace": [
                        {
                            "url": "https://mdsgroup.com/",
                            "status": 301,
                            "location": "http://www.mdsgroup.com/",
                        },
                        {
                            "url": "http://www.mdsgroup.com/",
                            "status": 301,
                            "location": "https://mds.pt/",
                        },
                    ]
                },
                error_kind=RenderErrorKind.NAVIGATION_ERROR,
            )
        if self.recovery_succeeds:
            return BrowserRenderResult(
                requested_url=url,
                final_url="https://www.mdsgroup.com/pt/",
                http_status=200,
                content_type="text/html",
                rendered_html="<html><body>MDS</body></html>",
                browser_metadata={
                    "navigation_trace": [
                        {
                            "url": "https://www.mdsgroup.com/",
                            "status": 301,
                            "location": "/pt/",
                        },
                        {
                            "url": "https://www.mdsgroup.com/pt/",
                            "status": 200,
                            "location": None,
                        },
                    ]
                },
            )
        return BrowserRenderResult(
            requested_url=url,
            final_url=None,
            http_status=None,
            content_type=None,
            rendered_html=None,
            browser_metadata={"navigation_trace": []},
            error_kind=RenderErrorKind.NAVIGATION_ERROR,
        )


class BrowserIdentityTests(unittest.TestCase):
    def test_desktop_identity_tracks_runtime_chrome_version_without_changing_searchgeo_viewport(self) -> None:
        options, identity = realistic_context_options(
            _FakePlaywright(),
            browser_version="151.0.7922.34",
            device=DeviceContext.DESKTOP,
        )
        self.assertIn("Chrome/151.0.7922.34", options["user_agent"])
        self.assertEqual(options["viewport"], {"width": 1440, "height": 900})
        self.assertFalse(options["is_mobile"])
        self.assertFalse(options["has_touch"])
        self.assertEqual(options["locale"], "pt-BR")
        self.assertEqual(identity["descriptor"], "Desktop Chrome")
        self.assertEqual(identity["tls_validation"], "ENABLED")
        self.assertTrue(identity["stateless_context"])

    def test_mobile_identity_tracks_runtime_chrome_version_and_keeps_mobile_semantics(self) -> None:
        options, identity = realistic_context_options(
            _FakePlaywright(),
            browser_version="151.0.7922.34",
            device=DeviceContext.MOBILE,
        )
        self.assertIn("Chrome/151.0.7922.34", options["user_agent"])
        self.assertIn("Mobile Safari", options["user_agent"])
        self.assertEqual(options["viewport"], {"width": 412, "height": 915})
        self.assertTrue(options["is_mobile"])
        self.assertTrue(options["has_touch"])
        self.assertEqual(identity["descriptor"], "Pixel 7")

    def test_secure_upgrade_candidate_matches_mdsgroup_downgrade_hop(self) -> None:
        trace = [
            {"url": "https://mdsgroup.com/", "status": 301, "location": "http://www.mdsgroup.com/"},
            {"url": "http://www.mdsgroup.com/", "status": 301, "location": "https://mds.pt/"},
        ]
        self.assertEqual(
            secure_upgrade_candidate("https://mdsgroup.com/", trace),
            "https://www.mdsgroup.com/",
        )

    def test_secure_upgrade_candidate_does_not_cross_to_unrelated_host(self) -> None:
        trace = [
            {"url": "https://example.com/", "status": 301, "location": "http://other.example.net/"},
        ]
        self.assertIsNone(secure_upgrade_candidate("https://example.com/", trace))

    def test_secure_upgrade_candidate_does_not_activate_after_redirect_to_third_party(self) -> None:
        trace = [
            {"url": "https://example.com/", "status": 302, "location": "https://third.example.net/"},
            {"url": "https://third.example.net/", "status": 301, "location": "http://www.third.example.net/"},
        ]
        self.assertIsNone(secure_upgrade_candidate("https://example.com/", trace))

    def test_secure_upgrade_candidate_requires_https_requested_url(self) -> None:
        trace = [
            {"url": "http://example.com/", "status": 301, "location": "http://www.example.com/"},
        ]
        self.assertIsNone(secure_upgrade_candidate("http://example.com/", trace))

    def test_renderer_recovers_mdsgroup_via_single_strict_https_probe(self) -> None:
        renderer = _RecoveryRenderer(recovery_succeeds=True)
        result = renderer.render("https://mdsgroup.com/", DeviceContext.DESKTOP)
        self.assertTrue(result.succeeded)
        self.assertEqual(
            renderer.calls,
            ["https://mdsgroup.com/", "https://www.mdsgroup.com/"],
        )
        self.assertEqual(result.requested_url, "https://mdsgroup.com/")
        self.assertEqual(result.final_url, "https://www.mdsgroup.com/pt/")
        recovery = result.browser_metadata["secure_redirect_recovery"]
        self.assertTrue(recovery["attempted"])
        self.assertTrue(recovery["succeeded"])
        self.assertEqual(recovery["candidate_url"], "https://www.mdsgroup.com/")
        self.assertEqual(recovery["tls_validation"], "ENABLED")
        self.assertEqual(len(recovery["original_navigation_trace"]), 2)
        self.assertEqual(len(recovery["recovery_navigation_trace"]), 2)

    def test_renderer_preserves_original_failure_when_secure_probe_also_fails(self) -> None:
        renderer = _RecoveryRenderer(recovery_succeeds=False)
        result = renderer.render("https://mdsgroup.com/", DeviceContext.DESKTOP)
        self.assertFalse(result.succeeded)
        self.assertEqual(result.error_kind, RenderErrorKind.NAVIGATION_ERROR)
        self.assertEqual(
            renderer.calls,
            ["https://mdsgroup.com/", "https://www.mdsgroup.com/"],
        )
        recovery = result.browser_metadata["secure_redirect_recovery"]
        self.assertTrue(recovery["attempted"])
        self.assertFalse(recovery["succeeded"])


if __name__ == "__main__":
    unittest.main()
