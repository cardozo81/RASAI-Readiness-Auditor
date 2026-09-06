from __future__ import annotations

import inspect
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest

from searchgeo.acquisition import (
    HttpAcquisitionResult,
    NetworkError,
    NetworkErrorKind,
    RedirectHop,
)
from searchgeo.audit_runner import run_audit
from searchgeo import console_runtime
from searchgeo.discovery import (
    DEFAULT_CRAWLERS,
    DiscoveredPage,
    DiscoveryProvenance,
    DiscoveryResult,
    RobotsResult,
    RobotsState,
)
from searchgeo.domain import CompletionStatus, DiscoverySource, DeviceContext
from searchgeo.m21_web_performance import WebPerformanceConfig
from searchgeo.m23_apdex import SyntheticApdexConfig
from searchgeo.persistence import AuditWorkspace
from searchgeo.rendering import BrowserRenderResult, RenderErrorKind
from searchgeo.semantic import NoneProvider
from searchgeo.source_quality import (
    PreflightBlockedRenderer,
    assess_acquisitions,
    enrich_source_quality_report_site,
    load_assessment,
    persist_m21_source_skip,
    persist_m23_source_skip,
)


_SOURCE = "https://mdsgroup.com/"
_FINAL = "https://mds.pt/"
_BROWSER_FINAL = "https://www.mdsgroup.com/pt/"
_TLS_MESSAGE = "certificate verify failed: hostname mismatch for mds.pt"


def _tls_acquisition() -> HttpAcquisitionResult:
    return HttpAcquisitionResult(
        requested_url=_SOURCE,
        final_url=_FINAL,
        status=None,
        headers=(),
        body=b"",
        redirects=(
            RedirectHop(
                status=301,
                source_url=_SOURCE,
                location="http://www.mdsgroup.com/",
                target_url="http://www.mdsgroup.com/",
            ),
            RedirectHop(
                status=301,
                source_url="http://www.mdsgroup.com/",
                location=_FINAL,
                target_url=_FINAL,
            ),
        ),
        network_error=NetworkError(NetworkErrorKind.TLS, _TLS_MESSAGE),
        elapsed_ms=37,
    )


class _BlockedDiscovery:
    def discover(self, seed_url: str, *, max_pages: int) -> DiscoveryResult:
        self.seed_url = seed_url
        self.max_pages = max_pages
        acquisition = _tls_acquisition()
        crawler_access = {
            _SOURCE: {crawler: None for crawler in DEFAULT_CRAWLERS}
        }
        return DiscoveryResult(
            origin="https://mdsgroup.com",
            pages=(
                DiscoveredPage(
                    normalized_url=_SOURCE,
                    discovered_url=_SOURCE,
                    discovery_sources=(DiscoverySource.SEED,),
                    depth=0,
                    internal_references=0,
                ),
            ),
            page_acquisitions={_SOURCE: acquisition},
            provenance=(
                DiscoveryProvenance(
                    target_url=_SOURCE,
                    source=DiscoverySource.SEED,
                    source_url=None,
                    discovered_url=_SOURCE,
                ),
            ),
            robots=RobotsResult(
                url="https://mdsgroup.com/robots.txt",
                state=RobotsState.NETWORK_ERROR,
                acquisition=acquisition,
                sitemap_urls=(),
                crawler_access=crawler_access,
            ),
            sitemaps=(),
            total_discovered=1,
            total_audited=1,
            max_pages=max_pages,
            limit_reached=False,
        )


class _BrowserSuccessRenderer:
    def render(self, url: str, device: DeviceContext) -> BrowserRenderResult:
        return BrowserRenderResult(
            requested_url=url,
            final_url=_BROWSER_FINAL,
            http_status=200,
            content_type="text/html; charset=utf-8",
            rendered_html=(
                "<!doctype html><html lang='pt'><head><title>MDS</title>"
                "<meta name='description' content='MDS Group'>"
                f"<link rel='canonical' href='{_BROWSER_FINAL}'>"
                "</head><body><main><h1>MDS Group</h1><p>Conteúdo válido.</p></main></body></html>"
            ),
            browser_metadata={
                "engine": "fake-chromium",
                "profile": {"device": device.value},
                "navigation": {"settle_outcome": "NETWORKIDLE"},
            },
        )


class _BrowserFailureRenderer:
    def render(self, url: str, device: DeviceContext) -> BrowserRenderResult:
        return BrowserRenderResult(
            requested_url=url,
            final_url=_FINAL,
            http_status=None,
            content_type=None,
            rendered_html=None,
            browser_metadata={
                "engine": "fake-chromium",
                "profile": {"device": device.value},
                "navigation": {"settle_outcome": "NAVIGATION_ERROR"},
                "render_error": RenderErrorKind.NAVIGATION_ERROR.value,
            },
            error_kind=RenderErrorKind.NAVIGATION_ERROR,
        )


class SourceQualityFailFastTests(unittest.TestCase):
    def test_mdsgroup_redirect_tls_is_hard_blocker_with_full_chain(self) -> None:
        assessment = assess_acquisitions((_tls_acquisition(),))
        self.assertTrue(assessment.all_pages_hard_blocked)
        self.assertEqual(assessment.hard_blocker_kinds, ("TLS",))
        issue = assessment.issues[0]
        self.assertEqual(issue.requested_url, _SOURCE)
        self.assertEqual(issue.final_url, _FINAL)
        self.assertTrue(issue.cross_host_redirect)
        self.assertTrue(issue.http_downgrade_hop)
        self.assertEqual([item.status for item in issue.redirects], [301, 301])
        self.assertEqual(issue.classification, "TLS_CERTIFICATE_ERROR")
        self.assertIn("Não desabilitar", " ".join(issue.recommended_actions))

    def test_preflight_blocked_renderer_remains_available_as_diagnostic_stub(self) -> None:
        assessment = assess_acquisitions((_tls_acquisition(),))
        result = PreflightBlockedRenderer(assessment).render(_SOURCE, DeviceContext.DESKTOP)
        self.assertFalse(result.succeeded)
        self.assertEqual(result.final_url, _FINAL)
        self.assertEqual(result.browser_metadata["engine"], "not_started")
        self.assertIn("SOURCE_QUALITY_BLOCKED:TLS", result.browser_metadata["render_skipped_reason"])

    def test_core_audit_confirms_blocker_only_after_browser_failure(self) -> None:
        with TemporaryDirectory() as directory:
            result = run_audit(
                _SOURCE,
                audits_root=directory,
                project_name="MDS source quality",
                max_pages=1,
                semantic_provider=NoneProvider(),
                discovery_engine=_BlockedDiscovery(),
                renderer=_BrowserFailureRenderer(),
            )
            self.assertEqual(result.completion_status, CompletionStatus.COMPLETE_WITH_LIMITATIONS)
            workspace = AuditWorkspace.open(result.audit_root)
            assessment = load_assessment(workspace)
            self.assertIsNotNone(assessment)
            assert assessment is not None
            self.assertTrue(assessment.all_pages_hard_blocked)

            connection = sqlite3.connect(workspace.database)
            connection.row_factory = sqlite3.Row
            try:
                audit = connection.execute(
                    "SELECT completion_status,limitations FROM audits WHERE audit_id=?",
                    (result.audit_id,),
                ).fetchone()
                self.assertEqual(audit["completion_status"], "COMPLETE_WITH_LIMITATIONS")
                limitations = json.loads(audit["limitations"])
                self.assertTrue(any("TLS" in item for item in limitations))

                snapshots = connection.execute(
                    "SELECT browser_metadata FROM page_snapshots"
                ).fetchall()
                self.assertGreaterEqual(len(snapshots), 1)
                metadata = json.loads(snapshots[0]["browser_metadata"])
                self.assertEqual(metadata["engine"], "fake-chromium")
                self.assertFalse(metadata["render_succeeded"])

                attempts = connection.execute(
                    "SELECT COUNT(*) FROM ai_provider_attempts"
                ).fetchone()[0]
                self.assertEqual(attempts, 0)
            finally:
                connection.close()

            log = (workspace.root / "logs" / "audit.log").read_text(encoding="utf-8")
            self.assertIn("SOURCE_QUALITY_PREFLIGHT_BLOCKER", log)
            self.assertIn("SOURCE_QUALITY_BLOCKED", log)
            self.assertNotIn("SOURCE_QUALITY_BROWSER_RECOVERED", log)

    def test_core_audit_continues_when_chromium_reaches_valid_browser_route(self) -> None:
        with TemporaryDirectory() as directory:
            result = run_audit(
                _SOURCE,
                audits_root=directory,
                project_name="MDS browser reconciliation",
                max_pages=1,
                semantic_provider=NoneProvider(),
                discovery_engine=_BlockedDiscovery(),
                renderer=_BrowserSuccessRenderer(),
            )
            self.assertEqual(result.completion_status, CompletionStatus.COMPLETE_WITH_LIMITATIONS)
            workspace = AuditWorkspace.open(result.audit_root)
            assessment = load_assessment(workspace)
            self.assertIsNotNone(assessment)
            assert assessment is not None
            self.assertFalse(assessment.all_pages_hard_blocked)
            self.assertEqual(assessment.hard_blocker_kinds, ())
            issue = assessment.issues[0]
            self.assertFalse(issue.hard_blocker)
            self.assertEqual(issue.classification, "HTTP_BROWSER_ROUTE_DIVERGENCE")
            self.assertEqual(issue.final_url, _BROWSER_FINAL)
            self.assertIsNone(issue.network_error)
            self.assertIn(_FINAL, issue.deterministic_summary)
            self.assertIn(_BROWSER_FINAL, issue.deterministic_summary)

            connection = sqlite3.connect(workspace.database)
            connection.row_factory = sqlite3.Row
            try:
                audit = connection.execute(
                    "SELECT completion_status,limitations FROM audits WHERE audit_id=?",
                    (result.audit_id,),
                ).fetchone()
                limitations = json.loads(audit["limitations"])
                self.assertTrue(any("HTTP e Chromium" in item for item in limitations))

                snapshot = connection.execute(
                    "SELECT final_url,rendered_artifact_ref,browser_metadata FROM page_snapshots LIMIT 1"
                ).fetchone()
                self.assertEqual(snapshot["final_url"], _BROWSER_FINAL)
                self.assertTrue(snapshot["rendered_artifact_ref"])
                metadata = json.loads(snapshot["browser_metadata"])
                self.assertTrue(metadata["render_succeeded"])

                extraction = connection.execute(
                    "SELECT title,canonical,main_content_ref FROM page_snapshots LIMIT 1"
                ).fetchone()
                self.assertEqual(extraction["title"], "MDS")
                self.assertEqual(extraction["canonical"], _BROWSER_FINAL)
                self.assertTrue(extraction["main_content_ref"])
            finally:
                connection.close()

            log = (workspace.root / "logs" / "audit.log").read_text(encoding="utf-8")
            self.assertIn("SOURCE_QUALITY_PREFLIGHT_BLOCKER", log)
            self.assertIn("SOURCE_QUALITY_BROWSER_RECOVERED", log)
            self.assertNotIn('"event":"SOURCE_QUALITY_BLOCKED"', log)

    def test_m21_and_m23_persist_zero_attempt_source_skip_after_browser_confirmation(self) -> None:
        with TemporaryDirectory() as directory:
            result = run_audit(
                _SOURCE,
                audits_root=directory,
                project_name="MDS skip downstream",
                max_pages=1,
                semantic_provider=NoneProvider(),
                discovery_engine=_BlockedDiscovery(),
                renderer=_BrowserFailureRenderer(),
            )
            workspace = AuditWorkspace.open(result.audit_root)
            assessment = load_assessment(workspace)
            assert assessment is not None
            self.assertTrue(assessment.all_pages_hard_blocked)

            m21 = persist_m21_source_skip(
                audit_id=result.audit_id,
                workspace=workspace,
                config=WebPerformanceConfig(enabled=True),
                assessment=assessment,
            )
            self.assertEqual(m21.status, "SKIPPED_SOURCE_BLOCKER")
            self.assertEqual(m21.context_attempts, 0)
            self.assertEqual(m21.pagespeed_attempts, 0)
            self.assertEqual(m21.crux_attempts, 0)

            m23 = persist_m23_source_skip(
                audit_id=result.audit_id,
                workspace=workspace,
                config=SyntheticApdexConfig(
                    enabled=True,
                    threshold_seconds=8.0,
                    target_valid_samples=100,
                    max_attempts_per_context=125,
                    timeout_seconds=45.0,
                ).validate(),
                assessment=assessment,
            )
            self.assertEqual(m23.status, "SKIPPED_SOURCE_BLOCKER")
            self.assertEqual(m23.attempted_samples, 0)
            self.assertEqual(m23.valid_samples, 0)

            connection = sqlite3.connect(workspace.database)
            try:
                web = connection.execute(
                    "SELECT status,context_attempts FROM web_performance_runs WHERE audit_id=?",
                    (result.audit_id,),
                ).fetchone()
                apdex = connection.execute(
                    "SELECT status,attempted_samples,valid_samples FROM synthetic_apdex_runs WHERE audit_id=?",
                    (result.audit_id,),
                ).fetchone()
            finally:
                connection.close()
            self.assertEqual(web, ("SKIPPED_SOURCE_BLOCKER", 0))
            self.assertEqual(apdex, ("SKIPPED_SOURCE_BLOCKER", 0, 0))

    def test_source_quality_panel_is_added_to_all_reports_idempotently(self) -> None:
        with TemporaryDirectory() as directory:
            result = run_audit(
                _SOURCE,
                audits_root=directory,
                project_name="MDS report diagnostics",
                max_pages=1,
                semantic_provider=NoneProvider(),
                discovery_engine=_BlockedDiscovery(),
                renderer=_BrowserFailureRenderer(),
            )
            workspace = AuditWorkspace.open(result.audit_root)
            report_dir = workspace.root / "report"
            extra = report_dir / "extra-test.html"
            extra.write_text("<html><body><main><header><h1>Teste</h1></header></main></body></html>", encoding="utf-8")

            enrich_source_quality_report_site(audit_id=result.audit_id, workspace=workspace)
            enrich_source_quality_report_site(audit_id=result.audit_id, workspace=workspace)

            for path in (result.report_path, extra):
                html = path.read_text(encoding="utf-8")
                self.assertEqual(html.count("searchgeo-source-quality:start"), 1)
                self.assertIn("Origem, redirecionamentos e integridade de transporte", html)
                self.assertIn("https://mdsgroup.com/", html)
                self.assertIn("https://mds.pt/", html)
                self.assertIn("TLS_CERTIFICATE_ERROR", html)
                self.assertGreaterEqual(html.count("301"), 2)

    def test_recovered_route_report_exposes_browser_final_and_http_chain(self) -> None:
        with TemporaryDirectory() as directory:
            result = run_audit(
                _SOURCE,
                audits_root=directory,
                project_name="MDS recovered report",
                max_pages=1,
                semantic_provider=NoneProvider(),
                discovery_engine=_BlockedDiscovery(),
                renderer=_BrowserSuccessRenderer(),
            )
            workspace = AuditWorkspace.open(result.audit_root)
            enrich_source_quality_report_site(audit_id=result.audit_id, workspace=workspace)
            html = result.report_path.read_text(encoding="utf-8")
            self.assertIn("HTTP_BROWSER_ROUTE_DIVERGENCE", html)
            self.assertIn(_BROWSER_FINAL, html)
            self.assertIn(_FINAL, html)
            self.assertIn("Chromium", html)
            self.assertGreaterEqual(html.count("301"), 2)

    def test_console_runtime_does_not_dump_raw_recent_or_final_stdout(self) -> None:
        source = inspect.getsource(console_runtime.run_audit_from_console)
        self.assertNotIn("Saída recente", source)
        self.assertNotIn("Saída final", source)
        self.assertIn("Log técnico", source)


if __name__ == "__main__":
    unittest.main()
