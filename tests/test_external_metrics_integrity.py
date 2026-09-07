from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from rasai.domain import Audit, AuditTarget, DeviceContext, DiscoverySource, Page, PageSnapshot, TargetType
from rasai.external_metrics_integrity import (
    ARTIFACT,
    enrich_external_metrics_integrity_report_site,
    reconcile_external_metrics_integrity,
)
from rasai.m21_reporting import enrich_m21_report_site
from rasai.m21_web_performance import HttpJsonResult, WebPerformanceConfig, execute_m21
from rasai.persistence import AuditPersistence, AuditWorkspace


_NOW = datetime(2026, 9, 5, 20, 0, tzinfo=timezone.utc)


class _PageSpeed:
    def __init__(self, payload):
        self.payload = payload

    def run(self, *, url, strategy, categories, timeout_seconds):
        return HttpJsonResult(self.payload, 200, 10)


class ExternalMetricsIntegrityTests(unittest.TestCase):
    def test_lighthouse_runtime_error_discards_scores_even_when_pagespeed_http_200(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = self._fixture(Path(directory))
            payload = self._payload()
            payload["lighthouseResult"]["runtimeError"] = {
                "code": "INSECURE_DOCUMENT_REQUEST",
                "message": "The page could not be securely loaded",
            }
            result = execute_m21(
                audit_id="AUD-INTEGRITY",
                workspace=workspace,
                config=WebPerformanceConfig(enabled=True, field_source="none"),
                pagespeed_client=_PageSpeed(payload),
            )
            # M21 transport succeeded. The integrity gate must independently reject LHR.
            self.assertEqual(result.pagespeed_successes, 1)
            reconciled = reconcile_external_metrics_integrity(
                audit_id="AUD-INTEGRITY",
                workspace=workspace,
                result=result,
            )
            self.assertEqual(reconciled.status, "UNAVAILABLE")
            self.assertEqual(reconciled.successful_contexts, 0)

            with sqlite3.connect(workspace.database) as db:
                row = db.execute(
                    "SELECT status,performance_score,accessibility_score,error_summary FROM web_performance_observations"
                ).fetchone()
                self.assertEqual(row[0], "UNAVAILABLE")
                self.assertIsNone(row[1])
                self.assertIsNone(row[2])
                self.assertIn("LIGHTHOUSE_RUNTIME_ERROR:INSECURE_DOCUMENT_REQUEST", row[3])
                run = db.execute(
                    "SELECT status,pagespeed_successes,successful_contexts FROM web_performance_runs"
                ).fetchone()
                self.assertEqual(run, ("UNAVAILABLE", 1, 0))

            integrity = json.loads((workspace.root / ARTIFACT).read_text(encoding="utf-8"))
            self.assertEqual(integrity["contexts"][0]["lighthouse_status"], "RUNTIME_ERROR")
            self.assertFalse(integrity["contexts"][0]["accessibility_valid"])

    def test_runtime_error_with_valid_crux_is_partial_not_lighthouse_success(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = self._fixture(Path(directory))
            payload = self._payload(with_field=True)
            payload["lighthouseResult"]["runtimeError"] = {
                "code": "PROTOCOL_TIMEOUT",
                "message": "Lighthouse timed out",
            }
            result = execute_m21(
                audit_id="AUD-INTEGRITY",
                workspace=workspace,
                config=WebPerformanceConfig(enabled=True, field_source="pagespeed"),
                pagespeed_client=_PageSpeed(payload),
            )
            reconciled = reconcile_external_metrics_integrity(
                audit_id="AUD-INTEGRITY",
                workspace=workspace,
                result=result,
            )
            self.assertEqual(reconciled.status, "PARTIAL")
            self.assertEqual(reconciled.successful_contexts, 1)
            self.assertEqual(reconciled.partial_contexts, 1)
            with sqlite3.connect(workspace.database) as db:
                row = db.execute(
                    "SELECT status,performance_score,accessibility_score,cwv_assessment FROM web_performance_observations"
                ).fetchone()
                self.assertEqual(row, ("PARTIAL", None, None, "PASS"))

    def test_missing_accessibility_category_does_not_become_no_failures(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = self._fixture(Path(directory))
            payload = self._payload()
            del payload["lighthouseResult"]["categories"]["accessibility"]
            result = execute_m21(
                audit_id="AUD-INTEGRITY",
                workspace=workspace,
                config=WebPerformanceConfig(enabled=True, field_source="none"),
                pagespeed_client=_PageSpeed(payload),
            )
            reconciled = reconcile_external_metrics_integrity(
                audit_id="AUD-INTEGRITY",
                workspace=workspace,
                result=result,
            )
            self.assertEqual(reconciled.status, "PARTIAL")
            with sqlite3.connect(workspace.database) as db:
                row = db.execute(
                    "SELECT performance_score,accessibility_score,status,error_summary FROM web_performance_observations"
                ).fetchone()
                self.assertAlmostEqual(row[0], 91.0)
                self.assertIsNone(row[1])
                self.assertEqual(row[2], "PARTIAL")
                self.assertIn("LIGHTHOUSE_CATEGORY_INVALID:accessibility", row[3])

            report = workspace.root / "report"
            report.mkdir()
            shell = "<html><body><aside><nav></nav></aside><main><header>H</header></main></body></html>"
            for name in ("index.html", "references.html", "remediation.html", "ai-usage.html"):
                (report / name).write_text(shell, encoding="utf-8")
            enrich_m21_report_site(audit_id="AUD-INTEGRITY", workspace=workspace)
            enrich_external_metrics_integrity_report_site(audit_id="AUD-INTEGRITY", workspace=workspace)
            html = (report / "accessibility.html").read_text(encoding="utf-8")
            self.assertIn("Acessibilidade válida", html)
            self.assertIn("0/1", html)
            self.assertIn("LIGHTHOUSE", html)
            self.assertIn("Esta observação só deve ser interpretada", html)
            self.assertNotIn(
                "<strong>Nenhuma falha automatizada persistida.</strong> Isso não elimina",
                html,
            )

    def test_fully_valid_lighthouse_preserves_scores_and_success(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = self._fixture(Path(directory))
            result = execute_m21(
                audit_id="AUD-INTEGRITY",
                workspace=workspace,
                config=WebPerformanceConfig(enabled=True, field_source="none"),
                pagespeed_client=_PageSpeed(self._payload()),
            )
            reconciled = reconcile_external_metrics_integrity(
                audit_id="AUD-INTEGRITY",
                workspace=workspace,
                result=result,
            )
            self.assertEqual(reconciled.status, "SUCCESS")
            with sqlite3.connect(workspace.database) as db:
                row = db.execute(
                    "SELECT performance_score,accessibility_score,status,error_summary FROM web_performance_observations"
                ).fetchone()
                self.assertEqual(row, (91.0, 88.0, "SUCCESS", None))

    @staticmethod
    def _fixture(root: Path) -> AuditWorkspace:
        workspace = AuditWorkspace.create(root, "AUD-INTEGRITY")
        with AuditPersistence(workspace) as persistence:
            persistence.audits.add(Audit(
                audit_id="AUD-INTEGRITY",
                project_name="Integrity",
                primary_language="pt-BR",
                auditor_version="test",
                ruleset_version="test",
            ))
            persistence.targets.add(AuditTarget(
                "TGT-INTEGRITY", "AUD-INTEGRITY", "https://example.test/", "https://example.test", TargetType.URL,
            ))
            persistence.pages.add(Page(
                "PGE-INTEGRITY", "AUD-INTEGRITY", "https://example.test/", "https://example.test/", (DiscoverySource.SEED,), 0,
            ))
            persistence.snapshots.add(PageSnapshot(
                snapshot_id="SNP-INTEGRITY",
                page_id="PGE-INTEGRITY",
                device=DeviceContext.MOBILE,
                requested_url="https://example.test/",
                final_url="https://example.test/",
                captured_at=_NOW,
                http_status=200,
            ))
        return workspace

    @staticmethod
    def _payload(*, with_field: bool = False) -> dict:
        payload = {
            "lighthouseResult": {
                "lighthouseVersion": "13.0.0",
                "fetchTime": "2026-09-05T20:00:00.000Z",
                "categories": {
                    "performance": {"score": 0.91, "auditRefs": []},
                    "accessibility": {"score": 0.88, "auditRefs": []},
                    "best-practices": {"score": 0.95, "auditRefs": []},
                    "seo": {"score": 1.0, "auditRefs": []},
                },
                "audits": {
                    "first-contentful-paint": {"numericValue": 900},
                    "speed-index": {"numericValue": 1200},
                    "largest-contentful-paint": {"numericValue": 2100},
                    "total-blocking-time": {"numericValue": 180},
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
                "origin_fallback": False,
            }
        return payload


if __name__ == "__main__":
    unittest.main()
