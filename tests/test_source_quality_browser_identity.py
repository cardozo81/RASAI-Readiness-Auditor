from __future__ import annotations

import unittest

from searchgeo.browser_identity_renderer import realistic_context_options
from searchgeo.domain import DeviceContext


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


if __name__ == "__main__":
    unittest.main()
