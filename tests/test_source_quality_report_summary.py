from __future__ import annotations

import json
import sqlite3
from tempfile import TemporaryDirectory
import unittest

from rasai.persistence import AuditWorkspace
from rasai.source_quality import (
    RedirectDetail,
    SourceQualityAssessment,
    SourceQualityIssue,
    persist_assessment,
)
from rasai.source_quality_report_summary import enrich_source_quality_blocker_summary


class SourceQualityReportSummaryTests(unittest.TestCase):
    def test_blocked_source_is_explicit_on_every_report_and_log(self) -> None:
        with TemporaryDirectory() as temp_dir:
            workspace = AuditWorkspace.create(temp_dir, "AUD-SOURCE-REPORT")
            report_dir = workspace.root / "report"
            report_dir.mkdir()
            for name in ("index.html", "apdex.html"):
                (report_dir / name).write_text(
                    "<!doctype html><html><body><header><h1>RASAi</h1></header><main><p>conteúdo</p></main></body></html>",
                    encoding="utf-8",
                )

            assessment = SourceQualityAssessment(
                issues=(
                    SourceQualityIssue(
                        requested_url="https://mdsgroup.com/",
                        final_url="https://mds.pt/",
                        http_status=None,
                        network_error="TLS",
                        network_error_message="certificate hostname mismatch",
                        redirects=(
                            RedirectDetail(
                                status=301,
                                source_url="https://mdsgroup.com/",
                                location="http://www.mdsgroup.com/",
                                target_url="http://www.mdsgroup.com/",
                            ),
                            RedirectDetail(
                                status=301,
                                source_url="http://www.mdsgroup.com/",
                                location="https://mds.pt/",
                                target_url="https://mds.pt/",
                            ),
                        ),
                        hard_blocker=True,
                        severity="CRITICAL",
                        classification="TLS_CERTIFICATE_ERROR",
                        deterministic_summary="A URL final não pôde ser validada por TLS.",
                        recommended_actions=(
                            "Corrigir o certificado apresentado pelo hostname final.",
                            "Validar a cadeia de redirecionamento antes de reexecutar.",
                        ),
                        cross_host_redirect=True,
                        http_downgrade_hop=True,
                    ),
                ),
                pages_considered=1,
                hard_blocked_pages=1,
            )
            persist_assessment(workspace, assessment)

            (workspace.artifacts / "source-quality-preflight.json").write_text(
                json.dumps(assessment.as_dict(), ensure_ascii=False),
                encoding="utf-8",
            )
            (workspace.artifacts / "source-quality-ai.json").write_text(
                json.dumps(
                    {
                        "state": "SUCCESS",
                        "provider": "DEEPSEEK",
                        "model": "deepseek-v4-flash",
                        "explanation": {
                            "summary_pt": "A cadeia termina em hostname cujo certificado não corresponde ao destino.",
                            "likely_root_cause_pt": "Regra de redirect ou virtual host TLS inconsistente.",
                            "recommended_actions_pt": [
                                "Revisar redirects no CDN/proxy.",
                                "Emitir certificado válido para o hostname final esperado.",
                            ],
                            "human_validation_required": True,
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            with sqlite3.connect(workspace.database) as db:
                db.execute(
                    """CREATE TABLE web_performance_runs (
                    status TEXT, context_attempts INTEGER, reason TEXT
                    )"""
                )
                db.execute(
                    "INSERT INTO web_performance_runs VALUES (?,?,?)",
                    ("SKIPPED_SOURCE_BLOCKER", 0, "SOURCE_QUALITY_BLOCKED:TLS"),
                )
                db.execute(
                    """CREATE TABLE synthetic_apdex_runs (
                    status TEXT, attempted_samples INTEGER, valid_samples INTEGER,
                    invalid_samples INTEGER, reason TEXT
                    )"""
                )
                db.execute(
                    "INSERT INTO synthetic_apdex_runs VALUES (?,?,?,?,?)",
                    ("SKIPPED_SOURCE_BLOCKER", 0, 0, 0, "SOURCE_QUALITY_BLOCKED:TLS"),
                )
                db.execute(
                    """CREATE TABLE page_snapshots (
                    device TEXT, requested_url TEXT, final_url TEXT, http_status INTEGER,
                    browser_metadata TEXT, captured_at TEXT
                    )"""
                )
                db.execute(
                    "INSERT INTO page_snapshots VALUES (?,?,?,?,?,?)",
                    (
                        "DESKTOP",
                        "https://mdsgroup.com/",
                        "https://mds.pt/",
                        None,
                        json.dumps(
                            {
                                "browser_version": "151.0.7922.34",
                                "render_error": "NAVIGATION_ERROR",
                                "render_succeeded": False,
                                "browser_identity": {
                                    "channel": "chrome",
                                    "browser_version": "151.0.7922.34",
                                    "user_agent": "Chrome/151.0.7922.34",
                                },
                                "navigation_trace": [
                                    {"url": "https://mdsgroup.com/", "status": 301},
                                ],
                            }
                        ),
                        "2026-09-05T23:00:00+00:00",
                    ),
                )
                db.commit()

            result = enrich_source_quality_blocker_summary(
                audit_id="AUD-SOURCE-REPORT",
                workspace=workspace,
            )
            self.assertEqual(result, report_dir / "index.html")

            for name in ("index.html", "apdex.html"):
                html = (report_dir / name).read_text(encoding="utf-8")
                self.assertIn("Auditoria limitada por bloqueio técnico da origem", html)
                self.assertIn("As métricas dependentes do conteúdo não puderam ser coletadas", html)
                self.assertIn("0 tentativa(s) externa(s)", html)
                self.assertIn("0 navegação(ões) sintética(s)", html)
                self.assertIn("O que deve ser corrigido antes de reexecutar", html)
                self.assertIn("Interpretação complementar por IA", html)
                self.assertIn("DEEPSEEK", html)
                self.assertIn("logs/audit.log", html)
                self.assertIn("source-quality-preflight.json", html)
                self.assertIn("Observação do navegador utilizada na confirmação", html)

            # Idempotência: o bloco e o evento técnico não se multiplicam.
            enrich_source_quality_blocker_summary(
                audit_id="AUD-SOURCE-REPORT",
                workspace=workspace,
            )
            html = (report_dir / "index.html").read_text(encoding="utf-8")
            self.assertEqual(html.count("rasai-source-blocker-summary:start"), 1)

            log = (workspace.root / "logs" / "audit.log").read_text(encoding="utf-8")
            self.assertEqual(log.count("SOURCE_QUALITY_TECHNICAL_DIAGNOSTIC"), 1)
            self.assertIn("TLS_CERTIFICATE_ERROR", log)
            self.assertIn("SKIPPED_SOURCE_BLOCKER", log)


if __name__ == "__main__":
    unittest.main()
