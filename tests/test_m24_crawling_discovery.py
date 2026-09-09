"""Risk-oriented tests for Crawling, Discovery & AI Access."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import re
import sqlite3
from tempfile import TemporaryDirectory
from threading import Thread
import unittest

from rasai.acquisition import HttpClient
from rasai.discovery import DiscoveryEngine, SitemapState
from rasai.domain import Audit, AuditTarget, TargetType, new_id
from rasai.m2 import execute_m2
from rasai.m24_cli import TECHNICAL_AI_ENV, configured_m24
from rasai.m24_crawling_discovery import execute_m24
from rasai.m24_discovery_extensions import install_discovery_extensions
from rasai.m24_reporting import enrich_m24_report_site
from rasai.persistence import AuditPersistence, AuditWorkspace


_MILESTONE_PUBLIC_RE = re.compile(r"(?i)(?<![A-Za-z0-9])m\d{1,3}")


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        origin = f"http://127.0.0.1:{self.server.server_port}"
        if self.path == "/robots.txt":
            self._respond(
                200,
                "text/plain",
                (
                    "User-agent: OAI-SearchBot\n"
                    "Allow: /\n"
                    "User-agent: GPTBot\n"
                    "Disallow: /\n"
                    "User-agent: Google-Extended\n"
                    "Disallow: /private\n"
                    "User-agent: *\n"
                    "Allow: /\n"
                    "Disallow: /assets/\n"
                    f"Sitemap: {origin}/sitemap.xml\n"
                    "Sitemap: https://cdn.example.invalid/sitemap.xml\n"
                ).encode(),
            )
        elif self.path == "/sitemap.xml":
            self._respond(
                200,
                "text/plain",
                (
                    '<?xml version="1.0"?>'
                    '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
                    f"<url><loc>{origin}/</loc><lastmod>2999-01-01</lastmod><priority>1.0</priority></url>"
                    f"<url><loc>{origin}/page</loc><changefreq>daily</changefreq></url>"
                    f"<url><loc>{origin}/</loc></url>"
                    "</urlset>"
                ).encode(),
            )
        elif self.path == "/sitemap.txt":
            self._respond(
                200,
                "text/plain",
                f"{origin}/\n{origin}/page\nhttps://other.invalid/out\n".encode(),
            )
        elif self.path == "/feed.xml":
            self._respond(
                200,
                "application/rss+xml",
                (
                    "<rss version='2.0'><channel>"
                    f"<item><link>{origin}/page</link></item>"
                    "</channel></rss>"
                ).encode(),
            )
        elif self.path == "/atom.xml":
            self._respond(
                200,
                "application/atom+xml",
                (
                    "<feed xmlns='http://www.w3.org/2005/Atom'>"
                    f"<entry><link rel='alternate' href='{origin}/page'/></entry>"
                    "</feed>"
                ).encode(),
            )
        elif self.path == "/llms.txt":
            self._respond(
                200,
                "text/plain",
                f"Descrição sem H1\n\n## Links\n- [Página]({origin}/page)\n".encode(),
            )
        elif self.path in {"/", "/page"}:
            self._respond(
                200,
                "text/html; charset=utf-8",
                b"<html><head><title>Fixture</title></head><body><main><h1>Fixture</h1></main></body></html>",
            )
        else:
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
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def _fixture(origin: str, root: str):
    audit = Audit(
        audit_id=new_id("AUD"),
        project_name="Crawling discovery fixture",
        max_pages=2,
        auditor_version="0.1.0",
        ruleset_version="TEST",
    )
    target = AuditTarget(
        target_id=new_id("TGT"),
        audit_id=audit.audit_id,
        input_url=f"{origin}/",
        normalized_origin=origin,
        target_type=TargetType.URL,
    )
    workspace = AuditWorkspace.create(Path(root), audit.audit_id)
    with AuditPersistence(workspace) as persistence:
        m2 = execute_m2(
            audit,
            target,
            persistence,
            workspace,
            engine=DiscoveryEngine(HttpClient(timeout=1)),
        )
    return audit, target, workspace, m2


class M24Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        install_discovery_extensions()

    def test_discovery_supports_xml_text_rss_atom_and_preserves_external_declaration(self) -> None:
        with _server() as origin:
            engine = DiscoveryEngine(HttpClient(timeout=1))
            result = engine.discover(f"{origin}/", max_pages=2)
            self.assertIn("https://cdn.example.invalid/sitemap.xml", result.robots.sitemap_urls)
            self.assertTrue(all(item.url.startswith(origin) for item in result.sitemaps))
            xml = next(item for item in result.sitemaps if item.url == f"{origin}/sitemap.xml")
            self.assertEqual(xml.state, SitemapState.OBTAINED)
            self.assertEqual(xml.page_urls, (f"{origin}/", f"{origin}/page"))

            text = engine._acquire_sitemap(f"{origin}/sitemap.txt", origin)
            rss = engine._acquire_sitemap(f"{origin}/feed.xml", origin)
            atom = engine._acquire_sitemap(f"{origin}/atom.xml", origin)
            self.assertEqual(text.page_urls, (f"{origin}/", f"{origin}/page"))
            self.assertEqual(rss.page_urls, (f"{origin}/page",))
            self.assertEqual(atom.page_urls, (f"{origin}/page",))

    def test_m24_persists_non_scoring_diagnostics_and_report_idempotently(self) -> None:
        with _server() as origin, TemporaryDirectory() as directory:
            audit, _, workspace, _ = _fixture(origin, directory)
            connection = sqlite3.connect(workspace.database)
            before_rules = connection.execute(
                "SELECT COUNT(*) FROM rule_executions WHERE audit_id=?",
                (audit.audit_id,),
            ).fetchone()[0]
            connection.close()

            result = execute_m24(
                audit_id=audit.audit_id,
                workspace=workspace,
                technical_ai=False,
                http_client=HttpClient(timeout=1),
            )
            self.assertEqual(result.scoring_impact, "NONE")
            self.assertEqual(result.llms_state, "PRESENT")
            self.assertIn("https://cdn.example.invalid/sitemap.xml", result.external_sitemaps)

            connection = sqlite3.connect(workspace.database)
            rows = connection.execute(
                "SELECT code,scoring_impact FROM m24_diagnostics WHERE audit_id=?",
                (audit.audit_id,),
            ).fetchall()
            after_rules = connection.execute(
                "SELECT COUNT(*) FROM rule_executions WHERE audit_id=?",
                (audit.audit_id,),
            ).fetchone()[0]
            connection.close()
            self.assertEqual(before_rules, after_rules)
            self.assertTrue(rows)
            self.assertTrue(all(row[1] == "NONE" for row in rows))
            codes = {row[0] for row in rows}
            self.assertIn("M24-ROBOTS-EXTERNAL-SITEMAP", codes)
            self.assertIn("M24-ROBOTS-GPTBOT-BLOCKED", codes)
            self.assertIn("M24-LLMS-PRESENT", codes)
            self.assertIn("M24-LLMS-H1-MISSING", codes)
            self.assertIn("M24-SITEMAP-DUPLICATE-URL", codes)
            self.assertIn("M24-SITEMAP-LASTMOD-FUTURE", codes)
            self.assertIn("M24-SITEMAP-IGNORED-HINTS", codes)

            report = workspace.root / "report"
            (report / "css").mkdir(parents=True)
            (report / "css" / "site.css").write_text("body{}\n", encoding="utf-8")
            shell = (
                "<!doctype html><html><body>"
                "<aside><nav><a href='index.html'>Visão geral</a></nav></aside>"
                "<main></main><footer class='footer'>x</footer></body></html>"
            )
            for name in ("index.html", "ai-usage.html", "references.html"):
                (report / name).write_text(shell, encoding="utf-8")
            page = enrich_m24_report_site(audit_id=audit.audit_id, workspace=workspace)
            enrich_m24_report_site(audit_id=audit.audit_id, workspace=workspace)
            html = page.read_text(encoding="utf-8")
            self.assertIn("css/site.css", html)
            self.assertNotIn("<style", html.casefold())
            self.assertIn("NENHUM", html)
            self.assertIn("Rastreamento, descoberta e acesso por IA", html)
            self.assertIn("CRAWLING-DISCOVERY-001", html)
            self.assertIn("ROBOTS-EXTERNAL-SITEMAP", html)
            self.assertNotIn("M24-ROBOTS-EXTERNAL-SITEMAP", html)
            self.assertIsNone(_MILESTONE_PUBLIC_RE.search(html))

            ai_html = (report / "ai-usage.html").read_text(encoding="utf-8")
            refs_html = (report / "references.html").read_text(encoding="utf-8")
            self.assertEqual(ai_html.count("<!-- crawling-discovery-ai-usage:start -->"), 1)
            self.assertEqual(refs_html.count("<!-- crawling-discovery-references:start -->"), 1)
            self.assertNotIn("<!-- m24-ai-usage:start -->", ai_html)
            self.assertNotIn("<!-- m24-references:start -->", refs_html)
            self.assertIsNone(_MILESTONE_PUBLIC_RE.search(ai_html))
            self.assertIsNone(_MILESTONE_PUBLIC_RE.search(refs_html))

    def test_m24_ai_enabled_without_provider_is_not_configured_not_site_failure(self) -> None:
        with _server() as origin, TemporaryDirectory() as directory:
            audit, _, workspace, _ = _fixture(origin, directory)
            result = execute_m24(
                audit_id=audit.audit_id,
                workspace=workspace,
                technical_ai=True,
                semantic_provider=None,
                http_client=HttpClient(timeout=1),
            )
            self.assertEqual(result.ai_state, "NOT_CONFIGURED")
            connection = sqlite3.connect(workspace.database)
            row = connection.execute(
                "SELECT state,reason FROM m24_ai_results WHERE audit_id=?",
                (audit.audit_id,),
            ).fetchone()
            connection.close()
            self.assertEqual(row[0], "NOT_CONFIGURED")
            self.assertIn("NOT_CONFIGURED", row[1])

    def test_source_blocker_disables_additional_llms_network_probe(self) -> None:
        class ExplodingClient:
            def acquire(self, url: str):
                raise AssertionError(f"network must not be called: {url}")

        with _server() as origin, TemporaryDirectory() as directory:
            audit, _, workspace, _ = _fixture(origin, directory)
            result = execute_m24(
                audit_id=audit.audit_id,
                workspace=workspace,
                allow_network=False,
                http_client=ExplodingClient(),
            )
            self.assertEqual(result.llms_state, "SKIPPED_SOURCE_BLOCKER")
            connection = sqlite3.connect(workspace.database)
            codes = {
                row[0]
                for row in connection.execute(
                    "SELECT code FROM m24_diagnostics WHERE audit_id=?",
                    (audit.audit_id,),
                )
            }
            connection.close()
            self.assertIn("M24-LLMS-SKIPPED-SOURCE-BLOCKER", codes)

    def test_cli_config_defaults_off_and_accepts_env(self) -> None:
        args = argparse.Namespace(ai_technical_remediation=None)
        old = __import__("os").environ.pop(TECHNICAL_AI_ENV, None)
        try:
            self.assertFalse(configured_m24(args).technical_ai)
            __import__("os").environ[TECHNICAL_AI_ENV] = "true"
            self.assertTrue(configured_m24(args).technical_ai)
            args.ai_technical_remediation = False
            self.assertFalse(configured_m24(args).technical_ai)
        finally:
            if old is None:
                __import__("os").environ.pop(TECHNICAL_AI_ENV, None)
            else:
                __import__("os").environ[TECHNICAL_AI_ENV] = old


if __name__ == "__main__":
    unittest.main()
