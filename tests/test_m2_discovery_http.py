"""Risk-oriented tests for M2 Discovery + HTTP."""

from __future__ import annotations

from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import socket
from tempfile import TemporaryDirectory
from threading import Thread
import unittest

from rasai.acquisition import HttpClient, NetworkErrorKind
from rasai.discovery import DiscoveryEngine, RobotsState, SitemapState
from rasai.domain import Audit, AuditTarget, EvidenceType, RuleResult, TargetType, new_id
from rasai.m2 import execute_m2
from rasai.persistence import AuditPersistence, AuditWorkspace
from rasai.url_utils import InvalidUrl, normalize_url, resolve_http_url


class _FixtureHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        port = self.server.server_port
        origin = f"http://127.0.0.1:{port}"
        if self.path == "/robots.txt":
            self._respond(
                200,
                "text/plain",
                (
                    "User-agent: GPTBot\n"
                    "Disallow: /private\n"
                    "User-agent: *\n"
                    "Allow: /\n"
                    f"Sitemap: {origin}/sitemap.xml\n"
                ).encode(),
            )
        elif self.path == "/sitemap.xml":
            self._respond(
                200,
                "application/xml",
                (
                    '<?xml version="1.0"?>'
                    '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
                    f"<url><loc>{origin}/b#fragment</loc></url>"
                    f"<url><loc>{origin}/a</loc></url>"
                    "</urlset>"
                ).encode(),
            )
        elif self.path == "/":
            self._respond(
                200,
                "text/html; charset=utf-8",
                b'<a href="/c">c1</a><a href="/c#fragment">c2</a><a href="/d">d</a>'
                b'<a href="/private">private</a><a href="mailto:test@example.com">mail</a>',
                {"X-Fixture": "seed"},
            )
        elif self.path == "/a":
            self._respond(200, "text/html", b'<a href="/d">d</a>')
        elif self.path == "/b":
            self._respond(200, "text/html", b'<a href="/c">c</a>')
        elif self.path in {"/c", "/d", "/private", "/final"}:
            self._respond(200, "text/html", self.path.encode())
        elif self.path == "/redirect":
            self._respond(302, "text/plain", b"", {"Location": "/final"})
        elif self.path == "/loop-a":
            self._respond(302, "text/plain", b"", {"Location": "/loop-b"})
        elif self.path == "/loop-b":
            self._respond(302, "text/plain", b"", {"Location": "/loop-a"})
        elif self.path == "/cycle-a":
            self._respond(200, "text/html", b'<a href="/cycle-b">b</a>')
        elif self.path == "/cycle-b":
            self._respond(200, "text/html", b'<a href="/cycle-a">a</a>')
        elif self.path == "/drop":
            self.connection.shutdown(socket.SHUT_RDWR)
            self.connection.close()
        else:
            self._respond(404, "text/plain", b"not found")

    def _respond(
        self,
        status: int,
        content_type: str,
        body: bytes,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return


class _MalformedHandler(_FixtureHandler):
    def do_GET(self) -> None:
        if self.path == "/robots.txt":
            self._respond(404, "text/plain", b"missing")
        elif self.path == "/sitemap.xml":
            self._respond(200, "application/xml", b"<urlset><url>")
        elif self.path == "/":
            self._respond(200, "text/html", b"ok")
        else:
            self._respond(404, "text/plain", b"missing")


@contextmanager
def _server(handler: type[BaseHTTPRequestHandler] = _FixtureHandler):
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


class M2DiscoveryHttpTests(unittest.TestCase):
    def test_url_normalization_is_conservative_and_rejects_unsupported_urls(self) -> None:
        self.assertEqual(
            normalize_url("HTTPS://Example.COM:443/a/../b/?x=2&x=1#fragment"),
            "https://example.com/b/?x=2&x=1",
        )
        self.assertEqual(
            resolve_http_url("https://example.com/a/index.html", "../b#x"),
            "https://example.com/b",
        )
        with self.assertRaises(InvalidUrl):
            normalize_url("javascript:alert(1)")
        with self.assertRaises(InvalidUrl):
            normalize_url("https://user:pass@example.com/")

    def test_http_captures_redirects_headers_http_errors_and_network_errors(self) -> None:
        with _server() as origin:
            client = HttpClient(timeout=1)
            result = client.acquire(f"{origin}/redirect")
            self.assertEqual(result.status, 200)
            self.assertEqual(result.final_url, f"{origin}/final")
            self.assertEqual(len(result.redirects), 1)
            self.assertEqual(result.redirects[0].status, 302)

            missing = client.acquire(f"{origin}/missing")
            self.assertEqual(missing.status, 404)
            self.assertIsNone(missing.network_error)

            loop = client.acquire(f"{origin}/loop-a")
            self.assertEqual(loop.network_error.kind, NetworkErrorKind.REDIRECT_LOOP)

        probe = socket.socket()
        probe.bind(("127.0.0.1", 0))
        unused_port = probe.getsockname()[1]
        probe.close()
        refused = HttpClient(timeout=0.5).acquire(f"http://127.0.0.1:{unused_port}/")
        self.assertIsNotNone(refused.network_error)
        # A closed localhost port is normally CONNECTION/PROTOCOL, but some
        # Windows firewall/network stacks silently drop the SYN and surface a
        # timeout instead. All three are valid localized network failures; the
        # contract under test is that acquisition records the failure without
        # converting it into an HTTP response.
        self.assertIn(
            refused.network_error.kind,
            {
                NetworkErrorKind.CONNECTION,
                NetworkErrorKind.PROTOCOL,
                NetworkErrorKind.TIMEOUT,
            },
        )

    def test_discovery_is_deterministic_and_m2_persists_provenance_http_and_rules(self) -> None:
        with _server() as origin, TemporaryDirectory() as temp_dir:
            audit = Audit(
                audit_id=new_id("AUD"),
                project_name="M2 integration",
                max_pages=4,
                auditor_version="0.1.0",
                ruleset_version="M2",
            )
            target = AuditTarget(
                target_id=new_id("TGT"),
                audit_id=audit.audit_id,
                input_url=f"{origin}/",
                normalized_origin=origin,
                target_type=TargetType.URL,
            )
            workspace = AuditWorkspace.create(Path(temp_dir), audit.audit_id)
            with AuditPersistence(workspace) as persistence:
                execution = execute_m2(
                    audit,
                    target,
                    persistence,
                    workspace,
                    engine=DiscoveryEngine(HttpClient(timeout=1)),
                )

                selected = [page.normalized_url for page in execution.discovery.pages]
                self.assertEqual(
                    selected,
                    [f"{origin}/", f"{origin}/a", f"{origin}/b", f"{origin}/c"],
                )
                self.assertTrue(execution.discovery.limit_reached)
                self.assertGreater(execution.discovery.total_discovered, audit.max_pages)
                self.assertEqual(execution.discovery.robots.sitemap_urls, (f"{origin}/sitemap.xml",))

                stored_audit = persistence.audits.get(audit.audit_id)
                self.assertTrue(any(value.startswith("MAX_PAGES_REACHED:") for value in stored_audit.limitations))
                for url, page_id in execution.page_ids.items():
                    page = persistence.pages.get(page_id)
                    self.assertEqual(page.normalized_url, url)
                    self.assertTrue(page.discovery_sources)

                evidence = [persistence.evidence.get(evidence_id) for evidence_id in execution.evidence_ids]
                self.assertTrue(any(item.evidence_type is EvidenceType.ROBOTS_RULE for item in evidence))
                http_evidence = [item for item in evidence if item.evidence_type is EvidenceType.HTTP_RESPONSE]
                self.assertEqual(len(http_evidence), audit.max_pages)
                self.assertTrue(any(item.artifact_reference for item in http_evidence))
                for item in http_evidence:
                    if item.artifact_reference:
                        self.assertTrue((workspace.root / item.artifact_reference).is_file())
                    self.assertIsNone(item.snapshot_id)
                    self.assertIsNone(item.device)

                rule_executions = [
                    persistence.rule_executions.get(execution_id)
                    for execution_id in execution.rule_execution_ids
                ]
                self.assertEqual(len(rule_executions), audit.max_pages * 4)
                self.assertTrue(all(item.device is None and item.snapshot_id is None for item in rule_executions))

            with AuditPersistence(AuditWorkspace.open(workspace.root)) as reopened:
                for page_id in execution.page_ids.values():
                    self.assertIsNotNone(reopened.pages.get(page_id))
                for evidence_id in execution.evidence_ids:
                    self.assertIsNotNone(reopened.evidence.get(evidence_id))

    def test_page_network_failure_is_persisted_without_aborting_the_audit(self) -> None:
        with _server() as origin, TemporaryDirectory() as temp_dir:
            audit = Audit(audit_id=new_id("AUD"), project_name="M2 network failure", max_pages=1)
            target = AuditTarget(
                target_id=new_id("TGT"),
                audit_id=audit.audit_id,
                input_url=f"{origin}/drop",
                normalized_origin=origin,
                target_type=TargetType.URL,
            )
            workspace = AuditWorkspace.create(Path(temp_dir), audit.audit_id)
            with AuditPersistence(workspace) as persistence:
                execution = execute_m2(
                    audit,
                    target,
                    persistence,
                    workspace,
                    engine=DiscoveryEngine(HttpClient(timeout=1)),
                )
                acquisition = execution.discovery.page_acquisitions[f"{origin}/drop"]
                self.assertIsNotNone(acquisition.network_error)
                rules = [
                    persistence.rule_executions.get(execution_id)
                    for execution_id in execution.rule_execution_ids
                ]
                retrievability = next(item for item in rules if item.rule_id == "BR-GEO-005")
                redirect = next(item for item in rules if item.rule_id == "BR-GEO-007")
                self.assertEqual(retrievability.result, RuleResult.FAIL)
                self.assertEqual(redirect.result, RuleResult.NOT_APPLICABLE)
                self.assertIsNotNone(persistence.audits.get(audit.audit_id))

    def test_robots_access_is_resolved_independently_per_configured_crawler(self) -> None:
        with _server() as origin:
            result = DiscoveryEngine(HttpClient(timeout=1)).discover(f"{origin}/", max_pages=6)
            self.assertIn(f"{origin}/private", result.robots.crawler_access)
            access = result.robots.crawler_access[f"{origin}/private"]
            self.assertFalse(access["GPTBot"])
            self.assertTrue(access["OAI-SearchBot"])
            self.assertTrue(access["Googlebot"])

    def test_robots_absence_and_malformed_sitemap_do_not_abort_discovery(self) -> None:
        with _server(_MalformedHandler) as origin:
            result = DiscoveryEngine(HttpClient(timeout=1)).discover(f"{origin}/", max_pages=1)
            self.assertEqual(result.robots.state, RobotsState.ABSENT)
            self.assertEqual(result.sitemaps[0].state, SitemapState.INVALID)
            self.assertEqual(result.total_audited, 1)
            self.assertEqual(result.pages[0].normalized_url, f"{origin}/")

    def test_internal_link_cycles_are_deduplicated(self) -> None:
        with _server() as origin:
            result = DiscoveryEngine(HttpClient(timeout=1)).discover(f"{origin}/cycle-a", max_pages=10)
            urls = [page.normalized_url for page in result.pages]
            self.assertEqual(urls.count(f"{origin}/cycle-a"), 1)
            self.assertEqual(urls.count(f"{origin}/cycle-b"), 1)


if __name__ == "__main__":
    unittest.main()
