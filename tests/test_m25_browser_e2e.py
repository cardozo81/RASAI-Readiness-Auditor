from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading
import time
import unittest

from searchgeo.m23_apdex_profiles import DESKTOP_STANDARD_PROFILE
from searchgeo.m25_apdex_experience import PlaywrightSyntheticUxGateway


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path == "/late":
            time.sleep(0.08)
            payload = b"ok"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        body = b"""<!doctype html><html><head><title>M25 E2E</title></head><body>
        <main>controlled</main>
        <script>
        window.addEventListener('load', () => {
          fetch('/late').then(() => { setTimeout(() => { throw new Error('controlled-m25-error'); }, 15); });
        });
        </script></body></html>"""
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args) -> None:
        return


class M25BrowserE2ETests(unittest.TestCase):
    def test_real_chromium_collects_late_fetch_and_javascript_error(self) -> None:
        server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        gateway = PlaywrightSyntheticUxGateway(session_mode="cold")
        try:
            url = f"http://127.0.0.1:{server.server_port}/"
            result = gateway.measure(
                url=url,
                device="DESKTOP",
                profile=DESKTOP_STANDARD_PROFILE,
                timeout_seconds=12.0,
                settle_seconds=2.0,
            )
            self.assertTrue(result.profile_applied)
            self.assertEqual(result.status, "SUCCESS")
            self.assertIsNotNone(result.user_action_duration_ms)
            self.assertIsNotNone(result.navigation_duration_ms)
            self.assertIsNotNone(result.dom_interactive_ms)
            self.assertGreaterEqual(result.xhr_fetch_count, 1)
            self.assertGreaterEqual(result.dynamic_resource_count, 1)
            self.assertGreaterEqual(result.javascript_error_count, 1)
            self.assertTrue(result.network_settled)
        finally:
            gateway.close()
            server.shutdown()
            server.server_close()
            thread.join(timeout=2.0)


if __name__ == "__main__":
    unittest.main()
