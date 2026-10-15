from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit
import json
import threading
import time
import unittest

from rasai.m23_apdex_profiles import DESKTOP_STANDARD_PROFILE
from rasai.m25_apdex_experience import PlaywrightSyntheticUxGateway, UxMeasurement


class _ThreadingServer(ThreadingHTTPServer):
    daemon_threads = True


class _BoundaryHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        parsed = urlsplit(self.path)
        path = parsed.path
        if path.startswith("/delay/"):
            try:
                delay_ms = int(path.rsplit("/", 1)[-1])
            except ValueError:
                delay_ms = 100
            time.sleep(delay_ms / 1000.0)
            payload = b"ok"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            try:
                self.wfile.write(payload)
            except (BrokenPipeError, ConnectionResetError):
                pass
            return

        scenario = path.removeprefix("/scenario/") or "clean"
        script = {
            "preload-fetch": """
              fetch('/delay/350').catch(() => {});
            """,
            "postload-fetch": """
              window.addEventListener('load', () => setTimeout(() => {
                fetch('/delay/220').catch(() => {});
              }, 25));
            """,
            "dynamic-resource": """
              window.addEventListener('load', () => setTimeout(() => {
                const img = new Image();
                img.src = '/delay/220';
                document.body.appendChild(img);
              }, 25));
            """,
            "dom-mutation-script": """
              window.addEventListener('load', () => setTimeout(() => {
                const node = document.createElement('div');
                node.textContent = 'late-dom-content';
                document.body.appendChild(node);
                const s = document.createElement('script');
                s.textContent = 'window.__rasaiBoundaryProof = 1';
                document.body.appendChild(s);
              }, 25));
            """,
            "late-network-idle": """
              window.addEventListener('load', () => setTimeout(() => {
                fetch('/delay/1400').catch(() => {});
              }, 20));
            """,
            "javascript-error": """
              window.addEventListener('load', () => setTimeout(() => {
                throw new Error('controlled-boundary-proof');
              }, 25));
            """,
            "request-aborted": """
              window.addEventListener('load', () => setTimeout(() => {
                const controller = new AbortController();
                fetch('/delay/1000', {signal: controller.signal}).catch(() => {});
                setTimeout(() => controller.abort(), 50);
              }, 20));
            """,
            "clean": "",
        }.get(scenario, "")
        body = f"""<!doctype html><html><head><title>CAT07 boundary</title></head>
        <body><main><h1>{scenario}</h1><p>controlled fixture</p></main>
        <script>{script}</script></body></html>""".encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args) -> None:
        return


def _facts(value: UxMeasurement) -> dict[str, object]:
    return {
        "user_action_duration_ms": value.user_action_duration_ms,
        "navigation_duration_ms": value.navigation_duration_ms,
        "load_event_end_ms": value.load_event_end_ms,
        "lcp_ms": value.lcp_ms,
        "xhr_fetch_count": value.xhr_fetch_count,
        "dynamic_resource_count": value.dynamic_resource_count,
        "network_settled": value.network_settled,
        "javascript_error_count": value.javascript_error_count,
        "request_failed_count": value.request_failed_count,
    }


class M25UserActionBoundaryProof226Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = _ThreadingServer(("127.0.0.1", 0), _BoundaryHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.origin = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2.0)

    def _measure(self, scenario: str, *, settle: float = 1.2) -> UxMeasurement:
        gateway = PlaywrightSyntheticUxGateway(session_mode="cold")
        try:
            result = gateway.measure(
                url=f"{self.origin}/scenario/{scenario}",
                device="DESKTOP",
                profile=DESKTOP_STANDARD_PROFILE,
                timeout_seconds=10.0,
                settle_seconds=settle,
            )
            self.assertEqual(result.status, "SUCCESS", _facts(result))
            self.assertTrue(result.profile_applied, _facts(result))
            self.assertIsNotNone(result.user_action_duration_ms, _facts(result))
            self.assertIsNotNone(result.load_event_end_ms, _facts(result))
            print("CAT07_BOUNDARY_PROOF " + json.dumps({
                "scenario": scenario,
                **_facts(result),
            }, sort_keys=True))
            return result
        finally:
            gateway.close()

    def _assert_load_boundary(self, result: UxMeasurement, *, delta: float = 90.0) -> None:
        self.assertAlmostEqual(
            float(result.user_action_duration_ms),
            float(result.load_event_end_ms),
            delta=delta,
            msg=str(_facts(result)),
        )

    def test_preload_fetch_finishing_postload_extends_user_action(self) -> None:
        result = self._measure("preload-fetch")
        self.assertGreaterEqual(result.xhr_fetch_count, 1, _facts(result))
        self.assertGreater(
            float(result.user_action_duration_ms),
            float(result.load_event_end_ms) + 120.0,
            _facts(result),
        )
        self.assertTrue(result.network_settled, _facts(result))

    def test_fetch_started_postload_is_observed_but_does_not_extend_duration(self) -> None:
        result = self._measure("postload-fetch")
        self.assertGreaterEqual(result.xhr_fetch_count, 1, _facts(result))
        self.assertGreaterEqual(result.dynamic_resource_count, 1, _facts(result))
        self._assert_load_boundary(result)
        self.assertTrue(result.network_settled, _facts(result))

    def test_dynamic_resource_postload_is_observed_but_does_not_extend_duration(self) -> None:
        result = self._measure("dynamic-resource")
        self.assertGreaterEqual(result.dynamic_resource_count, 1, _facts(result))
        self._assert_load_boundary(result)
        self.assertTrue(result.network_settled, _facts(result))

    def test_dom_mutation_and_inline_script_do_not_extend_duration(self) -> None:
        result = self._measure("dom-mutation-script")
        self._assert_load_boundary(result)
        self.assertEqual(result.xhr_fetch_count, 0, _facts(result))
        self.assertEqual(result.request_failed_count, 0, _facts(result))

    def test_late_network_idle_timeout_is_diagnostic_not_duration_extension(self) -> None:
        result = self._measure("late-network-idle", settle=0.20)
        self.assertGreaterEqual(result.xhr_fetch_count, 1, _facts(result))
        self.assertGreaterEqual(result.dynamic_resource_count, 1, _facts(result))
        self.assertFalse(result.network_settled, _facts(result))
        self._assert_load_boundary(result)

    def test_javascript_error_is_observed_without_temporal_extension(self) -> None:
        result = self._measure("javascript-error")
        self.assertGreaterEqual(result.javascript_error_count, 1, _facts(result))
        self._assert_load_boundary(result)

    def test_aborted_postload_request_is_diagnostic_without_temporal_extension(self) -> None:
        result = self._measure("request-aborted")
        self.assertGreaterEqual(result.xhr_fetch_count, 1, _facts(result))
        self.assertGreaterEqual(result.request_failed_count, 1, _facts(result))
        self._assert_load_boundary(result)

    def test_clean_scenario_matches_load_boundary(self) -> None:
        result = self._measure("clean")
        self._assert_load_boundary(result)
        self.assertEqual(result.xhr_fetch_count, 0, _facts(result))
        self.assertEqual(result.dynamic_resource_count, 0, _facts(result))
        self.assertEqual(result.javascript_error_count, 0, _facts(result))
        self.assertEqual(result.request_failed_count, 0, _facts(result))
        self.assertTrue(result.network_settled, _facts(result))


if __name__ == "__main__":
    unittest.main()
