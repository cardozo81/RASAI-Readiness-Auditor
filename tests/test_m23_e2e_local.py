from __future__ import annotations

from contextlib import redirect_stdout, redirect_stderr
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest

from rasai.cli_extensions import main

_HTML = b"""<!doctype html><html lang='pt-BR'><head><title>M23 local</title><meta name='description' content='fixture local'><link rel='canonical' href='/'></head><body><header><nav><a href='/'>Inicio</a></nav></header><main><h1>Fixture M23</h1><p>Conteudo controlado para validar Synthetic Navigation Apdex sem trafego externo de API.</p></main></body></html>"""

class _Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        if self.path in {"/", "/robots.txt"}:
            body = _HTML if self.path == "/" else b"User-agent: *\nAllow: /\n"
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8" if self.path == "/" else "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_response(404)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, format: str, *args: object) -> None:
        return

class M23LocalE2ETests(unittest.TestCase):
    def test_cli_materializes_apdex_report_and_keeps_external_apis_off(self) -> None:
        server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as directory:
                target = f"http://127.0.0.1:{server.server_port}/"
                stdout = io.StringIO()
                stderr = io.StringIO()
                with redirect_stdout(stdout), redirect_stderr(stderr):
                    code = main(["audit", target, "--audits-root", directory, "--project", "M23 Local E2E", "--max-pages", "1", "--device-context", "mobile", "--ai-provider", "none", "--no-ai-content-remediation", "--no-web-performance", "--synthetic-apdex", "--apdex-threshold-seconds", "2", "--apdex-samples-per-context", "3", "--apdex-max-attempts-per-context", "3", "--apdex-max-pages", "1", "--apdex-timeout-seconds", "10", "--apdex-delay-seconds", "0", "--apdex-concurrency", "1"])
                self.assertEqual(code, 0, stderr.getvalue())
                roots = [path for path in Path(directory).iterdir() if path.is_dir() and path.name.startswith("AUD-")]
                self.assertEqual(len(roots), 1)
                workspace = roots[0]
                report = workspace / "report" / "apdex.html"
                self.assertTrue(report.is_file())
                html = report.read_text(encoding="utf-8")
                self.assertIn("Synthetic Navigation Apdex", html)
                self.assertIn("grupo pequeno", html)
                index = (workspace / "report" / "index.html").read_text(encoding="utf-8")
                self.assertIn("apdex.html", index)
                connection = sqlite3.connect(workspace / "audit.db")
                try:
                    run = connection.execute("SELECT status,attempted_samples,valid_samples,invalid_samples FROM synthetic_apdex_runs").fetchone()
                    summary = connection.execute("SELECT valid_samples,small_group,final_group,apdex_score FROM synthetic_apdex_summaries").fetchone()
                    ai_attempts = connection.execute("SELECT COUNT(*) FROM ai_provider_attempts").fetchone()[0]
                    web_attempts = connection.execute("SELECT COUNT(*) FROM web_performance_attempts").fetchone()[0]
                finally:
                    connection.close()
                self.assertEqual(run[1:], (3, 3, 0))
                self.assertEqual(summary[0:3], (3, 1, 0))
                self.assertIsNotNone(summary[3])
                self.assertEqual(ai_attempts, 0)
                self.assertEqual(web_attempts, 0)
                self.assertIn("Synthetic Apdex: HABILITADO", stdout.getvalue())
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

if __name__ == "__main__":
    unittest.main()
