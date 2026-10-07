from __future__ import annotations

from contextlib import redirect_stdout
import io
from pathlib import Path
import sqlite3
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from rasai.audit_runner import AuditRunResult
from rasai.cli import main
from rasai.domain import CompletionStatus
from rasai.persistence import AuditWorkspace


class M21CliFailOpenTests(unittest.TestCase):
    def test_sqlite_error_in_m21_post_processing_does_not_invalidate_core_audit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = AuditWorkspace.create(Path(directory), "AUD-M21-FAILOPEN")
            workspace.database.touch()
            report_dir = workspace.root / "report"
            report_dir.mkdir()
            report_path = report_dir / "index.html"
            report_path.write_text("<html></html>", encoding="utf-8")
            result = AuditRunResult(
                audit_id="AUD-M21-FAILOPEN",
                audit_root=workspace.root,
                report_path=report_path,
                completion_status=CompletionStatus.COMPLETE_WITH_LIMITATIONS,
                audited_pages=1,
                finding_count=0,
                recommendation_count=0,
            )
            output = io.StringIO()

            final_summary = SimpleNamespace(
                processing_status="PARTIAL_RETRYABLE",
                report_status="PRELIMINARY",
            )
            with patch("rasai.cli.run_audit", return_value=result), patch(
                "rasai.cli.execute_m21", side_effect=sqlite3.OperationalError("simulated sqlite failure")
            ), patch(
                "rasai.audit_fulfillment.read_summary", return_value=final_summary
            ), redirect_stdout(output):
                exit_code = main([
                    "audit",
                    "https://example.test",
                    "--ai-provider",
                    "none",
                    "--web-performance",
                ])

            self.assertEqual(exit_code, 0)
            text = output.getvalue()
            self.assertIn("Auditoria concluída: AUD-M21-FAILOPEN", text)
            self.assertIn("Status: PARTIAL_RETRYABLE", text)
            self.assertIn("Relatório: PRELIMINARY", text)
            self.assertNotIn("Status: COMPLETE_WITH_LIMITATIONS", text)
            self.assertIn("INCOMPLETO por erro operacional", text)
            log_path = workspace.root / "logs" / "audit.log"
            self.assertTrue(log_path.is_file())
            log_text = log_path.read_text(encoding="utf-8")
            self.assertIn("M21_RUNTIME_FAILURE", log_text)
            self.assertIn("OperationalError", log_text)


    def test_final_cli_status_uses_complete_fulfillment_when_optional_web_performance_is_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = AuditWorkspace.create(Path(directory), "AUD-FINAL-COMPLETE")
            workspace.database.touch()
            report_dir = workspace.root / "report"
            report_dir.mkdir()
            report_path = report_dir / "index.html"
            report_path.write_text("<html></html>", encoding="utf-8")
            result = AuditRunResult(
                audit_id="AUD-FINAL-COMPLETE",
                audit_root=workspace.root,
                report_path=report_path,
                completion_status=CompletionStatus.COMPLETE_WITH_LIMITATIONS,
                audited_pages=1,
                finding_count=0,
                recommendation_count=0,
            )
            final_summary = SimpleNamespace(
                processing_status="COMPLETE",
                report_status="FINAL",
            )
            output = io.StringIO()

            with patch("rasai.cli.run_audit", return_value=result), patch(
                "rasai.cli.execute_m21", return_value=SimpleNamespace()
            ), patch(
                "rasai.audit_fulfillment.read_summary", return_value=final_summary
            ), redirect_stdout(output):
                exit_code = main([
                    "audit",
                    "https://example.test",
                    "--ai-provider",
                    "none",
                ])

            self.assertEqual(exit_code, 0)
            text = output.getvalue()
            self.assertIn("Status: COMPLETE", text)
            self.assertIn("Relatório: FINAL", text)
            self.assertIn("Web Performance externo: DESABILITADO", text)


    def test_cli_keeps_legacy_core_status_when_fulfillment_contract_is_absent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = AuditWorkspace.create(Path(directory), "AUD-LEGACY")
            workspace.database.touch()
            report_dir = workspace.root / "report"
            report_dir.mkdir()
            report_path = report_dir / "index.html"
            report_path.write_text("<html></html>", encoding="utf-8")
            result = AuditRunResult(
                audit_id="AUD-LEGACY",
                audit_root=workspace.root,
                report_path=report_path,
                completion_status=CompletionStatus.COMPLETE_WITH_LIMITATIONS,
                audited_pages=1,
                finding_count=0,
                recommendation_count=0,
            )
            output = io.StringIO()

            with patch("rasai.cli.run_audit", return_value=result), patch(
                "rasai.cli.execute_m21", return_value=SimpleNamespace()
            ), patch(
                "rasai.audit_fulfillment.read_summary", return_value=None
            ), redirect_stdout(output):
                exit_code = main([
                    "audit",
                    "https://example.test",
                    "--ai-provider",
                    "none",
                ])

            self.assertEqual(exit_code, 0)
            text = output.getvalue()
            self.assertIn("Status: COMPLETE_WITH_LIMITATIONS", text)
            self.assertNotIn("Relatório:", text)


if __name__ == "__main__":
    unittest.main()
