from __future__ import annotations

from datetime import datetime, timezone
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from rasai.cli import _configured_web_performance, build_parser
from rasai.domain import Audit, AuditTarget, DeviceContext, DiscoverySource, Page, PageSnapshot, TargetType
from rasai.m21_reporting import enrich_m21_report_site
from rasai.m21_web_performance import ExternalServiceError, HttpJsonResult, WebPerformanceConfig, execute_m21
from rasai.persistence import AuditPersistence, AuditWorkspace

_NOW = datetime(2026, 9, 3, 15, 0, tzinfo=timezone.utc)


class _PageSpeed:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def run(self, *, url, strategy, categories, timeout_seconds):
        self.calls.append((url, strategy, categories, timeout_seconds))
        return HttpJsonResult(self.payload, 200, 12)


class _FailingPageSpeed:
    def __init__(self):
        self.calls = []

    def run(self, *, url, strategy, categories, timeout_seconds):
        self.calls.append((url, strategy, categories, timeout_seconds))
        raise ExternalServiceError(
            "PAGESPEED_INSIGHTS",
            "TimeoutError",
            error_code="TIMEOUTERROR",
            duration_ms=60000,
        )


class _Crux:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def query(self, *, url, form_factor, timeout_seconds):
        self.calls.append((url, form_factor, timeout_seconds))
        return HttpJsonResult(self.payload, 200, 8)


class M21WebPerformanceTests(unittest.TestCase):
    def test_disabled_is_no_network_and_persists_run(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = self._fixture(Path(directory))
            psi = _PageSpeed({})
            result = execute_m21(
                audit_id="AUD-M21",
                workspace=workspace,
                config=WebPerformanceConfig(enabled=False),
                pagespeed_client=psi,
            )
            self.assertEqual(result.status, "DISABLED")
            self.assertEqual(psi.calls, [])
            connection = sqlite3.connect(workspace.database)
            try:
                row = connection.execute("SELECT enabled,status FROM web_performance_runs").fetchone()
                self.assertEqual(row, (0, "DISABLED"))
            finally:
                connection.close()
            self.assertTrue((workspace.root / "logs" / "audit.log").is_file())

    def test_cli_disabled_ignores_inactive_m21_tuning_environment(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["audit", "https://example.test", "--no-web-performance"])
        noisy_env = {
            "RASAI_WEB_PERFORMANCE_MAX_PAGES": "-999",
            "RASAI_WEB_PERFORMANCE_TIMEOUT_SECONDS": "not-a-number",
            "RASAI_WEB_PERFORMANCE_FIELD_SOURCE": "crux",
            "RASAI_LIGHTHOUSE_CATEGORIES": "not-a-category",
        }
        with patch.dict(os.environ, noisy_env, clear=False):
            config = _configured_web_performance(args)
        self.assertFalse(config.enabled)
        self.assertEqual(config.max_pages, 10)
        self.assertEqual(config.field_source, "auto")
        self.assertEqual(
            config.categories,
            ("performance", "accessibility", "best-practices", "seo", "agentic-browsing"),
        )

    def test_pagespeed_persists_lighthouse_and_cwv_without_touching_score(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = self._fixture(Path(directory))
            psi = _PageSpeed(self._pagespeed_payload(with_field=True))
            result = execute_m21(
                audit_id="AUD-M21",
                workspace=workspace,
                config=WebPerformanceConfig(enabled=True, max_pages=10, field_source="pagespeed"),
                pagespeed_client=psi,
            )
            self.assertEqual(result.status, "SUCCESS")
            self.assertEqual(result.pagespeed_attempts, 1)
            self.assertEqual(result.pagespeed_successes, 1)
            self.assertEqual(result.partial_contexts, 0)
            self.assertEqual(len(psi.calls), 1)
            self.assertEqual(psi.calls[0][1], "mobile")
            self.assertEqual(
                psi.calls[0][2],
                ("performance", "accessibility", "best-practices", "seo", "agentic-browsing"),
            )

            connection = sqlite3.connect(workspace.database)
            connection.row_factory = sqlite3.Row
            try:
                row = connection.execute("SELECT * FROM web_performance_observations").fetchone()
                self.assertAlmostEqual(row["performance_score"], 91.0)
                self.assertAlmostEqual(row["accessibility_score"], 88.0)
                self.assertAlmostEqual(row["agentic_browsing_score"], 84.0)
                self.assertAlmostEqual(row["lcp_p75_ms"], 2400.0)
                self.assertAlmostEqual(row["inp_p75_ms"], 180.0)
                self.assertAlmostEqual(row["cls_p75"], 0.08)
                self.assertEqual(row["cwv_assessment"], "PASS")
                self.assertEqual(row["field_source"], "PAGESPEED_CRUX")
                # This fixture intentionally has no M9 score tables. M21 must
                # remain additive and must not create or mutate scoring storage.
                self.assertIsNone(
                    connection.execute(
                        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='scores'"
                    ).fetchone()
                )
                artifact = row["pagespeed_artifact_reference"]
            finally:
                connection.close()
            self.assertTrue((workspace.root / artifact).is_file())

    def test_auto_uses_direct_crux_when_pagespeed_field_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = self._fixture(Path(directory))
            psi = _PageSpeed(self._pagespeed_payload(with_field=False))
            crux = _Crux({
                "record": {
                    "key": {"url": "https://example.test/"},
                    "metrics": {
                        "largest_contentful_paint": {"percentiles": {"p75": 2600}},
                        "interaction_to_next_paint": {"percentiles": {"p75": 150}},
                        "cumulative_layout_shift": {"percentiles": {"p75": 0.05}},
                    },
                }
            })
            result = execute_m21(
                audit_id="AUD-M21",
                workspace=workspace,
                config=WebPerformanceConfig(enabled=True, field_source="auto", crux_api_key="test-key"),
                pagespeed_client=psi,
                crux_client=crux,
            )
            self.assertEqual(result.status, "SUCCESS")
            self.assertEqual(result.pagespeed_attempts, 1)
            self.assertEqual(result.pagespeed_successes, 1)
            self.assertEqual(result.crux_attempts, 1)
            self.assertEqual(result.crux_successes, 1)
            self.assertEqual(len(crux.calls), 1)
            self.assertEqual(crux.calls[0][1], "PHONE")
            connection = sqlite3.connect(workspace.database)
            connection.row_factory = sqlite3.Row
            try:
                row = connection.execute("SELECT field_source,field_scope,cwv_assessment FROM web_performance_observations").fetchone()
                self.assertEqual(row["field_source"], "CRUX_API")
                self.assertEqual(row["field_scope"], "URL")
                self.assertEqual(row["cwv_assessment"], "FAIL")
                services = [item[0] for item in connection.execute("SELECT service FROM web_performance_attempts ORDER BY created_at,service")]
                self.assertEqual(set(services), {"PAGESPEED_INSIGHTS", "CRUX_API"})
            finally:
                connection.close()

    def test_pagespeed_timeout_with_crux_success_is_partial_and_logged(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = self._fixture(Path(directory))
            psi_secret = "psi-secret-must-not-appear"
            crux_secret = "crux-secret-must-not-appear"
            psi = _FailingPageSpeed()
            crux = _Crux({
                "record": {
                    "key": {"url": "https://example.test/"},
                    "metrics": {
                        "largest_contentful_paint": {"percentiles": {"p75": 2997}},
                        "interaction_to_next_paint": {"percentiles": {"p75": 382}},
                        "cumulative_layout_shift": {"percentiles": {"p75": 0.9}},
                    },
                }
            })
            result = execute_m21(
                audit_id="AUD-M21",
                workspace=workspace,
                config=WebPerformanceConfig(
                    enabled=True,
                    field_source="crux",
                    timeout_seconds=60,
                    pagespeed_api_key=psi_secret,
                    crux_api_key=crux_secret,
                ),
                pagespeed_client=psi,
                crux_client=crux,
            )

            self.assertEqual(result.status, "PARTIAL")
            self.assertEqual(result.context_attempts, 1)
            self.assertEqual(result.successful_contexts, 1)
            self.assertEqual(result.partial_contexts, 1)
            self.assertEqual(result.pagespeed_attempts, 1)
            self.assertEqual(result.pagespeed_successes, 0)
            self.assertEqual(result.crux_attempts, 1)
            self.assertEqual(result.crux_successes, 1)

            connection = sqlite3.connect(workspace.database)
            try:
                run = connection.execute(
                    "SELECT status,reason,pagespeed_successes,crux_successes FROM web_performance_runs"
                ).fetchone()
                self.assertEqual(
                    run,
                    ("PARTIAL", "ONE_OR_MORE_EXTERNAL_COMPONENTS_UNAVAILABLE", 0, 1),
                )
                observation = connection.execute(
                    "SELECT status,cwv_assessment,error_summary FROM web_performance_observations"
                ).fetchone()
                self.assertEqual(observation, ("PARTIAL", "FAIL", "PAGESPEED:TIMEOUTERROR"))
                attempts = connection.execute(
                    "SELECT service,status,error_code FROM web_performance_attempts ORDER BY created_at,service"
                ).fetchall()
                self.assertEqual(
                    set(attempts),
                    {
                        ("PAGESPEED_INSIGHTS", "ERROR", "TIMEOUTERROR"),
                        ("CRUX_API", "SUCCESS", None),
                    },
                )
            finally:
                connection.close()

            log_path = workspace.root / "logs" / "audit.log"
            self.assertTrue(log_path.is_file())
            log_text = log_path.read_text(encoding="utf-8")
            self.assertIn('"event":"M21_STARTED"', log_text)
            self.assertIn('"event":"M21_EXTERNAL_ATTEMPT"', log_text)
            self.assertIn('"event":"M21_COMPLETED"', log_text)
            self.assertIn('"status":"PARTIAL"', log_text)
            self.assertIn("TIMEOUTERROR", log_text)
            self.assertNotIn(psi_secret, log_text)
            self.assertNotIn(crux_secret, log_text)

    def test_missing_cwv_metric_is_incomplete_not_fail(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = self._fixture(Path(directory))
            payload = self._pagespeed_payload(with_field=True)
            del payload["loadingExperience"]["metrics"]["INTERACTION_TO_NEXT_PAINT"]
            result = execute_m21(
                audit_id="AUD-M21",
                workspace=workspace,
                config=WebPerformanceConfig(enabled=True, field_source="pagespeed"),
                pagespeed_client=_PageSpeed(payload),
            )
            self.assertEqual(result.status, "SUCCESS")
            connection = sqlite3.connect(workspace.database)
            try:
                assessment = connection.execute("SELECT cwv_assessment FROM web_performance_observations").fetchone()[0]
                self.assertEqual(assessment, "INCOMPLETE")
            finally:
                connection.close()

    def test_report_keeps_external_metrics_separate_from_score_geo_004(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = self._fixture(Path(directory))
            execute_m21(
                audit_id="AUD-M21",
                workspace=workspace,
                config=WebPerformanceConfig(enabled=True, field_source="pagespeed"),
                pagespeed_client=_PageSpeed(self._pagespeed_payload(with_field=True)),
            )
            report = workspace.root / "report"
            report.mkdir()
            shell = "<html><body><aside><nav><a href='index.html'>Visão</a></nav></aside><main><header>H</header></main></body></html>"
            (report / "index.html").write_text(shell, encoding="utf-8")
            (report / "references.html").write_text(shell, encoding="utf-8")
            (report / "remediation.html").write_text(shell, encoding="utf-8")
            (report / "ai-usage.html").write_text(shell, encoding="utf-8")
            path = enrich_m21_report_site(audit_id="AUD-M21", workspace=workspace)
            html = path.read_text(encoding="utf-8")
            self.assertIn("SCORE-GEO-004", html)
            self.assertIn("Core Web Vitals", html)
            self.assertIn("Lighthouse", html)
            self.assertIn("Nenhum desses scores é convertido automaticamente", html)
            self.assertIn("Agentic Browsing", html)
            self.assertIn("web-performance.html", (report / "index.html").read_text(encoding="utf-8"))
            self.assertIn("PageSpeed Insights API v5", (report / "references.html").read_text(encoding="utf-8"))

    @staticmethod
    def _fixture(root: Path) -> AuditWorkspace:
        workspace = AuditWorkspace.create(root, "AUD-M21")
        with AuditPersistence(workspace) as persistence:
            persistence.audits.add(Audit(
                audit_id="AUD-M21",
                project_name="M21",
                primary_language="pt-BR",
                auditor_version="test",
                ruleset_version="test",
            ))
            persistence.targets.add(AuditTarget(
                "TGT-M21", "AUD-M21", "https://example.test/", "https://example.test", TargetType.URL,
            ))
            persistence.pages.add(Page(
                "PGE-M21", "AUD-M21", "https://example.test/", "https://example.test/", (DiscoverySource.SEED,), 0,
            ))
            persistence.snapshots.add(PageSnapshot(
                snapshot_id="SNP-M21", page_id="PGE-M21", device=DeviceContext.MOBILE,
                requested_url="https://example.test/", final_url="https://example.test/",
                captured_at=_NOW, http_status=200,
            ))
        return workspace

    @staticmethod
    def _pagespeed_payload(*, with_field: bool):
        payload = {
            "lighthouseResult": {
                "lighthouseVersion": "13.0.0",
                "fetchTime": "2026-09-03T15:00:00.000Z",
                "categories": {
                    "performance": {"score": 0.91}, "accessibility": {"score": 0.88},
                    "best-practices": {"score": 0.95}, "seo": {"score": 1.0},
                    "agentic-browsing": {"score": 0.84},
                },
                "audits": {
                    "first-contentful-paint": {"numericValue": 900}, "speed-index": {"numericValue": 1200},
                    "largest-contentful-paint": {"numericValue": 2100}, "total-blocking-time": {"numericValue": 180},
                    "cumulative-layout-shift": {"numericValue": 0.04},
                },
            }
        }
        if with_field:
            payload["loadingExperience"] = {
                "metrics": {
                    "LARGEST_CONTENTFUL_PAINT_MS": {"percentile": 2400},
                    "INTERACTION_TO_NEXT_PAINT": {"percentile": 180},
                    "CUMULATIVE_LAYOUT_SHIFT_SCORE": {"percentile": 8},
                },
                "overall_category": "FAST", "origin_fallback": False,
            }
        return payload


if __name__ == "__main__":
    unittest.main()
