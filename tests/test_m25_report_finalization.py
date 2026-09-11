from __future__ import annotations

from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from rasai import m23_reporting, m25_reporting, report_navigation
from rasai.m25_runtime import refresh_m25_report_after_m23
from rasai.persistence import AuditWorkspace


class M25ReportFinalizationTests(unittest.TestCase):
    def _workspace(self, directory: str, *, with_run: bool) -> AuditWorkspace:
        workspace = AuditWorkspace.create(Path(directory), "AUD-M25-FINAL")
        connection = sqlite3.connect(workspace.database)
        try:
            with connection:
                connection.execute(
                    "CREATE TABLE synthetic_ux_apdex_runs(audit_id TEXT PRIMARY KEY)"
                )
                if with_run:
                    connection.execute(
                        "INSERT INTO synthetic_ux_apdex_runs(audit_id) VALUES (?)",
                        ("AUD-M25-FINAL",),
                    )
        finally:
            connection.close()
        (workspace.root / "report").mkdir(exist_ok=True)
        return workspace

    def test_m23_reporting_is_wrapped_with_m25_finalizer(self) -> None:
        self.assertTrue(
            getattr(m23_reporting.enrich_m23_report_site, "_rasai_m25_finalizer", False)
        )

    def test_m25_navigation_registration_is_idempotent_by_filename(self) -> None:
        original = report_navigation.NAV_ITEMS
        try:
            m25_reporting._register_navigation()
            matching = [
                item for item in report_navigation.NAV_ITEMS
                if item[1] == "apdex-experience.html"
            ]
            self.assertEqual(matching, [("Apdex de experiência", "apdex-experience.html")])
            self.assertEqual(report_navigation.NAV_ITEMS, original)
        finally:
            report_navigation.NAV_ITEMS = original

    def test_refresh_runs_only_for_persisted_m25_audit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = self._workspace(directory, with_run=True)
            expected = workspace.root / "report" / "apdex-experience.html"
            with patch(
                "rasai.m25_reporting.enrich_m25_report_site",
                return_value=expected,
            ) as enrich:
                refresh_m25_report_after_m23(
                    audit_id="AUD-M25-FINAL", workspace=workspace
                )
            enrich.assert_called_once_with(
                audit_id="AUD-M25-FINAL", workspace=workspace
            )

    def test_refresh_does_not_materialize_m25_when_run_is_absent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = self._workspace(directory, with_run=False)
            with patch("rasai.m25_reporting.enrich_m25_report_site") as enrich:
                refresh_m25_report_after_m23(
                    audit_id="AUD-M25-FINAL", workspace=workspace
                )
            enrich.assert_not_called()


if __name__ == "__main__":
    unittest.main()
