from __future__ import annotations

from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import tempfile
import unittest

from rasai.domain import (
    Audit,
    AuditTarget,
    DeviceContext,
    DiscoverySource,
    Page,
    PageSnapshot,
    TargetType,
)
from rasai.m21_reporting import enrich_m21_report_site
from rasai.m21_web_performance import HttpJsonResult, WebPerformanceConfig, execute_m21
from rasai.persistence import AuditPersistence, AuditWorkspace


_NOW = datetime(2026, 9, 9, 3, 30, tzinfo=timezone.utc)


class _PageSpeed:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def run(self, *, url, strategy, categories, timeout_seconds):
        return HttpJsonResult(self.payload, 200, 11)


class LighthouseWebQualityReportingTests(unittest.TestCase):
    def test_web_performance_exposes_four_lighthouse_categories_with_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = self._fixture(Path(directory))
            execute_m21(
                audit_id="AUD-WEB-QUALITY",
                workspace=workspace,
                config=WebPerformanceConfig(enabled=True, field_source="none"),
                pagespeed_client=_PageSpeed(self._payload()),
            )

            report = workspace.root / "report"
            report.mkdir()
            shell = (
                "<html><body><aside><nav><a href='index.html'>Visão</a></nav></aside>"
                "<main><header>H</header></main></body></html>"
            )
            for name in ("index.html", "references.html", "remediation.html", "ai-usage.html"):
                (report / name).write_text(shell, encoding="utf-8")

            path = enrich_m21_report_site(audit_id="AUD-WEB-QUALITY", workspace=workspace)
            html = path.read_text(encoding="utf-8")
            index = (report / "index.html").read_text(encoding="utf-8")
            references = (report / "references.html").read_text(encoding="utf-8")

            # sqlite3.Connection.__exit__ commits/rolls back but does not close the
            # handle. Explicit closing keeps the test portable to Windows, where an
            # open audit.db handle prevents TemporaryDirectory cleanup.
            with closing(sqlite3.connect(workspace.database)) as db:
                row = db.execute(
                    """
                    SELECT performance_score,accessibility_score,best_practices_score,seo_score
                    FROM web_performance_observations
                    """
                ).fetchone()
            self.assertEqual(row, (91.0, 88.0, 95.0, 90.0))

            self.assertIn("Performance · Lighthouse", html)
            self.assertIn("Accessibility · Lighthouse", html)
            self.assertIn("Best Practices · Lighthouse", html)
            self.assertIn("SEO técnico · Lighthouse", html)
            self.assertIn("Google Chrome Lighthouse", html)
            self.assertIn("lighthouseResult.categories.performance.score", html)
            self.assertIn("lighthouseResult.categories.accessibility.score", html)
            self.assertIn("lighthouseResult.categories.best-practices.score", html)
            self.assertIn("lighthouseResult.categories.seo.score", html)
            self.assertIn("errors-in-console", html)
            self.assertIn("meta-description", html)
            self.assertIn("Não mede ranking", html)
            self.assertIn("não repondera, não combina e não recalcula", html)
            self.assertIn("Search Intelligence/SERP", html)
            self.assertIn("SCORE-GEO-004", html)
            self.assertIn("accessibility.html", html)

            self.assertIn("Performance Lighthouse · média", index)
            self.assertIn("Accessibility Lighthouse · média", index)
            self.assertIn("Best Practices Lighthouse · média", index)
            self.assertIn("SEO técnico Lighthouse · média", index)

            self.assertIn("Lighthouse Best Practices", references)
            self.assertIn("Lighthouse SEO", references)
            self.assertIn("quatro categorias Lighthouse", references)

    @staticmethod
    def _fixture(root: Path) -> AuditWorkspace:
        workspace = AuditWorkspace.create(root, "AUD-WEB-QUALITY")
        with AuditPersistence(workspace) as persistence:
            persistence.audits.add(
                Audit(
                    audit_id="AUD-WEB-QUALITY",
                    project_name="Web Quality",
                    primary_language="pt-BR",
                    auditor_version="test",
                    ruleset_version="test",
                )
            )
            persistence.targets.add(
                AuditTarget(
                    "TGT-WEB-QUALITY",
                    "AUD-WEB-QUALITY",
                    "https://example.test/",
                    "https://example.test",
                    TargetType.URL,
                )
            )
            persistence.pages.add(
                Page(
                    "PGE-WEB-QUALITY",
                    "AUD-WEB-QUALITY",
                    "https://example.test/",
                    "https://example.test/",
                    (DiscoverySource.SEED,),
                    0,
                )
            )
            persistence.snapshots.add(
                PageSnapshot(
                    snapshot_id="SNP-WEB-QUALITY",
                    page_id="PGE-WEB-QUALITY",
                    device=DeviceContext.MOBILE,
                    requested_url="https://example.test/",
                    final_url="https://example.test/",
                    captured_at=_NOW,
                    http_status=200,
                )
            )
        return workspace

    @staticmethod
    def _payload() -> dict:
        return {
            "lighthouseResult": {
                "lighthouseVersion": "13.0.0",
                "fetchTime": "2026-09-09T03:30:00.000Z",
                "categories": {
                    "performance": {
                        "score": 0.91,
                        "auditRefs": [
                            {"id": "first-contentful-paint", "weight": 10},
                        ],
                    },
                    "accessibility": {
                        "score": 0.88,
                        "auditRefs": [
                            {"id": "color-contrast", "weight": 7},
                        ],
                    },
                    "best-practices": {
                        "score": 0.95,
                        "auditRefs": [
                            {"id": "is-on-https", "weight": 1},
                            {"id": "errors-in-console", "weight": 1},
                        ],
                    },
                    "seo": {
                        "score": 0.90,
                        "auditRefs": [
                            {"id": "document-title", "weight": 1},
                            {"id": "meta-description", "weight": 1},
                        ],
                    },
                },
                "audits": {
                    "first-contentful-paint": {
                        "score": 1,
                        "scoreDisplayMode": "numeric",
                        "numericValue": 900,
                        "title": "First Contentful Paint",
                    },
                    "largest-contentful-paint": {"numericValue": 2100},
                    "speed-index": {"numericValue": 1200},
                    "total-blocking-time": {"numericValue": 180},
                    "cumulative-layout-shift": {"numericValue": 0.04},
                    "color-contrast": {
                        "score": 0,
                        "scoreDisplayMode": "binary",
                        "title": "Background and foreground colors do not have a sufficient contrast ratio.",
                    },
                    "is-on-https": {
                        "score": 1,
                        "scoreDisplayMode": "binary",
                        "title": "Uses HTTPS",
                    },
                    "errors-in-console": {
                        "score": 0,
                        "scoreDisplayMode": "binary",
                        "title": "Browser errors were logged to the console",
                        "description": "Errors logged to the console indicate unresolved problems.",
                        "displayValue": "1 error",
                    },
                    "document-title": {
                        "score": 1,
                        "scoreDisplayMode": "binary",
                        "title": "Document has a title element",
                    },
                    "meta-description": {
                        "score": 0,
                        "scoreDisplayMode": "binary",
                        "title": "Document does not have a meta description",
                        "description": "Meta descriptions may be included in search results.",
                    },
                },
            }
        }


if __name__ == "__main__":
    unittest.main()
