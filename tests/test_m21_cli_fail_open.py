from __future__ import annotations

from contextlib import redirect_stdout
import io
from pathlib import Path
import sqlite3
import tempfile
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

            with patch("rasai.cli.run_audit", return_value=result), patch(
                "rasai.cli.execute_m21", side_effect=sqlite3.OperationalError("simulated sqlite failure")
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
            self.assertIn("INCOMPLETO por erro operacional", text)
            log_path = workspace.root / "logs" / "audit.log"
            self.assertTrue(log_path.is_file())
            log_text = log_path.read_text(encoding="utf-8")
            self.assertIn("M21_RUNTIME_FAILURE", log_text)
            self.assertIn("OperationalError", log_text)


if __name__ == "__main__":
    unittest.main()
