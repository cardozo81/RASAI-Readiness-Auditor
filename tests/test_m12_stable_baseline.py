"""M12 critical end-to-end tests for the stable local baseline."""

from __future__ import annotations

from contextlib import contextmanager, redirect_stdout
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import StringIO
import os
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
from threading import Thread
import unittest
from unittest.mock import patch

from rasai.acquisition import HttpClient
from rasai.audit_runner import AuditRunResult, run_audit
from rasai.cli import main
from rasai.device_context import DEVICE_CONTEXT_ENV
from rasai.discovery import DiscoveryEngine
from rasai.domain import AuditMode, AuditStatus, CompletionStatus, DeviceContext
from rasai.persistence import AuditPersistence, AuditWorkspace
from rasai.rendering import BrowserRenderResult
from rasai.semantic import NoneProvider


class _BaselineHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        origin = f"http://127.0.0.1:{self.server.server_port}"
        if self.path == "/robots.txt":
            self._respond(200, "text/plain; charset=utf-8", f"User-agent: *\nAllow: /\nSitemap: {origin}/sitemap.xml\n".encode())
            return
        if self.path == "/sitemap.xml":
            body = f"<?xml version='1.0'?><urlset xmlns='http://www.sitemaps.org/schemas/sitemap/0.9'><url><loc>{origin}/</loc></url><url><loc>{origin}/extra</loc></url></urlset>"
            self._respond(200, "application/xml", body.encode())
            return
        if self.path == "/":
            html = f"""<!doctype html><html lang='pt-BR'><head>
<title>Guia RASAi</title><meta name='description' content='Guia técnico.'>
<link rel='canonical' href='{origin}/'><script type='application/ld+json'>{{"@context":"https://schema.org","@type":"Article","headline":"Guia RASAi"}}</script>
</head><body><header><nav><a href='/extra'>Conteúdo adicional</a></nav></header>
<main><h1>Guia RASAi</h1><h2>Visão geral</h2><p>Este guia apresenta uma explicação técnica verificável sobre readiness para busca e sistemas generativos.</p><p>Publicado em 2026-09-02 pela Equipe Exemplo.</p></main></body></html>"""
            self._respond(200, "text/html; charset=utf-8", html.encode())
            return
        if self.path == "/extra":
            self._respond(200, "text/html; charset=utf-8", b"<html><head><title>Extra</title></head><body><main><h1>Extra</h1><p>Conteudo secundario.</p></main></body></html>")
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
    server = ThreadingHTTPServer(("127.0.0.1", 0), _BaselineHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


class _FixtureRenderer:
    def __init__(self, html: str) -> None:
        self.html = html

    def render(self, url: str, device: DeviceContext) -> BrowserRenderResult:
        return BrowserRenderResult(
            requested_url=url,
            final_url=url,
            http_status=200,
            content_type="text/html; charset=utf-8",
            rendered_html=self.html,
            browser_metadata={
                "engine": "m12-fixture",
                "profile": {
                    "device": device.value,
                    "is_mobile": device is DeviceContext.MOBILE,
                    "has_touch": device is DeviceContext.MOBILE,
                },
                "render_error": None,
            },
        )


class M12StableBaselineTests(unittest.TestCase):
    def test_end_to_end_pipeline_materializes_all_rules_devices_scores_and_report_site(self) -> None:
        with _server() as origin, TemporaryDirectory() as directory:
            html = f"""<!doctype html><html lang='pt-BR'><head><title>Guia RASAi</title>
<meta name='description' content='Guia técnico.'><link rel='canonical' href='{origin}/'>
<script type='application/ld+json'>{{"@context":"https://schema.org","@type":"Article","headline":"Guia RASAi"}}</script>
</head><body><nav><a href='{origin}/extra'>Extra</a></nav><main><h1>Guia RASAi</h1><h2>Visão geral</h2><p>Conteúdo principal técnico e verificável para a auditoria.</p><p>Publicado em 2026-09-02 pela Equipe Exemplo.</p></main></body></html>"""
            result = run_audit(
                f"{origin}/",
                audits_root=Path(directory),
                project_name="Baseline M12",
                language="pt-BR",
                market="BR",
                max_pages=1,
                semantic_provider=NoneProvider(),
                discovery_engine=DiscoveryEngine(HttpClient(timeout=1)),
                renderer=_FixtureRenderer(html),
                lazy_probe=lambda url, device: None,
            )

            self.assertTrue(result.report_path.is_file())
            self.assertEqual(result.report_path, result.audit_root / "report" / "index.html")
            self.assertTrue((result.audit_root / "audit.db").is_file())
            self.assertTrue((result.audit_root / "artifacts").is_dir())
            self.assertTrue((result.audit_root / "report" / "css" / "site.css").is_file())
            for filename in (
                "mobile.html", "desktop.html", "remediation.html",
                "content-suggestions.html", "ai-usage.html", "references.html",
            ):
                self.assertTrue((result.audit_root / "report" / filename).is_file(), filename)
            self.assertFalse((result.audit_root / "report.html").exists())
            self.assertFalse((result.audit_root / "remediation.html").exists())
            self.assertEqual(result.audited_pages, 1)
            self.assertEqual(result.completion_status, CompletionStatus.COMPLETE_WITH_LIMITATIONS)

            workspace = AuditWorkspace.open(result.audit_root)
            with AuditPersistence(workspace) as persistence:
                audit = persistence.audits.get(result.audit_id)
                self.assertIsNotNone(audit)
                assert audit is not None
                self.assertEqual(audit.status, AuditStatus.COMPLETED)
                self.assertEqual(audit.completion_status, CompletionStatus.COMPLETE_WITH_LIMITATIONS)
                self.assertEqual(audit.audit_mode, AuditMode.NO_AI)
                self.assertTrue(any(limitation.startswith("MAX_PAGES_REACHED:") for limitation in audit.limitations))

            connection = sqlite3.connect(result.audit_root / "audit.db")
            connection.row_factory = sqlite3.Row
            try:
                rule_ids = {
                    row[0]
                    for row in connection.execute(
                        "SELECT DISTINCT rule_id FROM rule_executions WHERE audit_id = ?",
                        (result.audit_id,),
                    )
                }
                expected_rules = {f"BR-GEO-{number:03d}" for number in range(1, 55)}
                self.assertTrue(expected_rules.issubset(rule_ids), sorted(expected_rules - rule_ids))

                snapshots = connection.execute(
                    "SELECT device, COUNT(*) FROM page_snapshots GROUP BY device ORDER BY device"
                ).fetchall()
                self.assertEqual({row[0]: row[1] for row in snapshots}, {"DESKTOP": 1, "MOBILE": 1})

                score_devices = {row[0] for row in connection.execute("SELECT DISTINCT device FROM scores")}
                self.assertEqual(score_devices, {"DESKTOP", "MOBILE"})
                report_rows = connection.execute("SELECT file_path FROM reports").fetchall()
                self.assertEqual(len(report_rows), 1)
                self.assertEqual(report_rows[0][0], "report/index.html")

                invalid_findings = connection.execute(
                    """
                    SELECT COUNT(*) FROM findings
                    WHERE rule_execution_id IS NULL OR evidence_ids IS NULL OR evidence_ids = '[]'
                    """
                ).fetchone()[0]
                self.assertEqual(invalid_findings, 0)

                m20_run = connection.execute(
                    "SELECT * FROM content_remediation_runs WHERE audit_id=?", (result.audit_id,)
                ).fetchone()
                self.assertIsNotNone(m20_run)
                self.assertEqual(m20_run["status"], "DISABLED")
                self.assertEqual(m20_run["generated_suggestions"], 0)
                jsonld_rows = connection.execute(
                    "SELECT device,status FROM jsonld_remediation_suggestions WHERE audit_id=? ORDER BY device",
                    (result.audit_id,),
                ).fetchall()
                self.assertEqual(len(jsonld_rows), 2)
                self.assertEqual({row["device"] for row in jsonld_rows}, {"DESKTOP", "MOBILE"})
            finally:
                connection.close()

            report = result.report_path.read_text(encoding="utf-8")
            content_report = (result.audit_root / "report" / "content-suggestions.html").read_text(encoding="utf-8")
            ai_report = (result.audit_root / "report" / "ai-usage.html").read_text(encoding="utf-8")
            css = (result.audit_root / "report" / "css" / "site.css").read_text(encoding="utf-8")
            self.assertIn('lang="pt-BR"', report)
            self.assertIn("Visão geral da auditoria", report)
            self.assertIn("Cobertura e confiabilidade", report)
            self.assertIn("Confiabilidade baixa não significa", report)
            self.assertIn("Relatório Mobile", report)
            self.assertIn("Relatório Desktop", report)
            self.assertIn("Referências e metodologia", report)
            self.assertIn("Conteúdo e JSON-LD", report)
            self.assertIn('<link rel="stylesheet" href="css/site.css">', report)
            self.assertNotIn("<style", report.casefold())
            self.assertIn("Conteúdo e JSON-LD", content_report)
            self.assertIn("Structured Data", content_report)
            self.assertIn("css/site.css", content_report)
            self.assertNotIn("<style", content_report.casefold())
            self.assertIn("remediation-ai-telemetry", ai_report)
            self.assertIn("--nav:", css)

    def test_cli_audit_command_defaults_to_mobile_and_restores_environment(self) -> None:
        with TemporaryDirectory() as directory:
            expected = AuditRunResult(
                audit_id="AUD-TEST",
                audit_root=Path(directory) / "AUD-TEST",
                report_path=Path(directory) / "AUD-TEST" / "report" / "index.html",
                completion_status=CompletionStatus.COMPLETE_WITH_LIMITATIONS,
                audited_pages=2,
                finding_count=3,
                recommendation_count=2,
            )
            output = StringIO()

            def fake_run(*args, **kwargs):
                self.assertEqual(os.environ.get(DEVICE_CONTEXT_ENV), "mobile")
                return expected

            with patch.dict(os.environ, {}, clear=True):
                with patch("rasai.cli.run_audit", side_effect=fake_run) as mocked, redirect_stdout(output):
                    exit_code = main([
                        "audit",
                        "example.com",
                        "--project",
                        "Projeto CLI",
                        "--max-pages",
                        "2",
                        "--audits-root",
                        directory,
                    ])
                self.assertNotIn(DEVICE_CONTEXT_ENV, os.environ)

            self.assertEqual(exit_code, 0)
            mocked.assert_called_once()
            _, kwargs = mocked.call_args
            self.assertEqual(kwargs["project_name"], "Projeto CLI")
            self.assertEqual(kwargs["max_pages"], 2)
            self.assertIsInstance(kwargs["semantic_provider"], NoneProvider)
            self.assertFalse(kwargs["content_remediation"])
            rendered = output.getvalue()
            self.assertIn("Auditoria concluída: AUD-TEST", rendered)
            self.assertIn("Contexto de dispositivo: MOBILE", rendered)
            self.assertIn("Sugestões de conteúdo por IA: DESABILITADAS", rendered)
            self.assertIn("report", rendered)
            self.assertIn("index.html", rendered)


if __name__ == "__main__":
    unittest.main()
