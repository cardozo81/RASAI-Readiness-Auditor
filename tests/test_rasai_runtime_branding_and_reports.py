from __future__ import annotations

from pathlib import Path
import sqlite3
import tempfile
import unittest

from rasai.consolidation.index import ConsolidationIndex
from rasai.platform import default_platform_database
from rasai.report_navigation import render_report_navigation
from rasai.report_registry import install
from rasai.runtime_paths import runtime_directory
from rasai.score_geo_003 import resolve_model_path
from rasai.score_geo_003_reporting import _score_reason


class RasaiRuntimeBrandingTests(unittest.TestCase):
    def test_runtime_directory_is_rasai(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.assertEqual(runtime_directory(root), root / ".rasai")

    def test_platform_and_consolidation_use_rasai_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "audits"
            self.assertEqual(default_platform_database(root), root / ".rasai" / "platform.db")
            index = ConsolidationIndex(root)
            self.assertEqual(index.path, root / ".rasai" / "consolidated-index.db")

    def test_score_model_path_uses_rasai_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            audit = project / "audits" / "AUD-TEST"
            audit.mkdir(parents=True)
            resolved = resolve_model_path(audit)
            self.assertEqual(resolved, project / ".rasai" / "scoring" / "score-geo-003-model.json")


class RasaiReportConsistencyTests(unittest.TestCase):
    def test_apdex_navigation_has_one_item_per_html(self) -> None:
        from rasai import m23_reporting, m25_reporting, report_navigation
        install()
        m23_reporting._register_apdex_navigation()
        m23_reporting._register_apdex_navigation()
        m25_reporting._register_navigation()
        m25_reporting._register_navigation()
        apdex = [item for item in report_navigation.NAV_ITEMS if item[1] == "apdex.html"]
        experience = [item for item in report_navigation.NAV_ITEMS if item[1] == "apdex-experience.html"]
        self.assertEqual(apdex, [("Apdex de navegação", "apdex.html")])
        self.assertEqual(experience, [("Apdex de experiência", "apdex-experience.html")])

    def test_score_reason_explains_missing_validated_model(self) -> None:
        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        try:
            row = connection.execute("SELECT NULL AS value, '[\"CALIBRATION_MODEL_UNAVAILABLE:SCORE-GEO-003\"]' AS limitations").fetchone()
            self.assertIn("VALIDATED", _score_reason(row))
            self.assertIn("não pode ser consolidado", _score_reason(row))
        finally:
            connection.close()

    def test_public_navigation_uses_hyphen_not_long_dash(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            report_dir = Path(directory)
            (report_dir / "index.html").write_text("x", encoding="utf-8")
            html = render_report_navigation(report_dir, "index.html")
            self.assertNotIn("—", html)
            self.assertNotIn("–", html)


if __name__ == "__main__":
    unittest.main()
