from __future__ import annotations

import os
from pathlib import Path
import sqlite3
import tempfile
import unittest

from searchgeo.consolidation.index import ConsolidationIndex
from searchgeo.platform import default_platform_database
from searchgeo.report_registry import install
from searchgeo.runtime_paths import runtime_directory
from searchgeo.score_geo_003 import resolve_model_path
from searchgeo.score_geo_003_reporting import _score_reason


class RasaiRuntimeBrandingTests(unittest.TestCase):
    def test_legacy_runtime_directory_moves_to_rasai_without_data_loss(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            legacy = root / ".searchgeo"
            legacy.mkdir()
            (legacy / "consolidated-index.db").write_text("legacy", encoding="utf-8")

            effective = runtime_directory(root)

            self.assertEqual(effective, root / ".rasai")
            self.assertEqual((effective / "consolidated-index.db").read_text(encoding="utf-8"), "legacy")
            self.assertFalse(legacy.exists())

    def test_conflicting_legacy_runtime_entry_is_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            canonical = root / ".rasai"
            legacy = root / ".searchgeo"
            canonical.mkdir()
            legacy.mkdir()
            (canonical / "platform.db").write_text("canonical", encoding="utf-8")
            (legacy / "platform.db").write_text("legacy", encoding="utf-8")

            effective = runtime_directory(root)

            self.assertEqual(effective, canonical)
            self.assertEqual((canonical / "platform.db").read_text(encoding="utf-8"), "canonical")
            self.assertEqual((legacy / "platform.db").read_text(encoding="utf-8"), "legacy")

    def test_platform_and_consolidation_use_rasai_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "audits"
            self.assertEqual(default_platform_database(root), root / ".rasai" / "platform.db")
            index = ConsolidationIndex(root)
            self.assertEqual(index.path, root / ".rasai" / "consolidated-index.db")

    def test_score_model_path_migrates_project_runtime_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            audit = project / "audits" / "AUD-TEST"
            audit.mkdir(parents=True)
            legacy_model = project / ".searchgeo" / "scoring" / "score-geo-003-model.json"
            legacy_model.parent.mkdir(parents=True)
            legacy_model.write_text("{}", encoding="utf-8")

            resolved = resolve_model_path(audit)

            self.assertEqual(resolved, project / ".rasai" / "scoring" / "score-geo-003-model.json")
            self.assertTrue(resolved.is_file())
            self.assertFalse((project / ".searchgeo").exists())


class RasaiReportConsistencyTests(unittest.TestCase):
    def test_apdex_navigation_has_one_item_per_html(self) -> None:
        from searchgeo import m23_reporting, m25_reporting, report_navigation

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
            row = connection.execute(
                "SELECT NULL AS value, '[\"CALIBRATION_MODEL_UNAVAILABLE:SCORE-GEO-003\"]' AS limitations"
            ).fetchone()
            self.assertIn("VALIDATED", _score_reason(row))
            self.assertIn("não pode ser consolidado", _score_reason(row))
        finally:
            connection.close()


if __name__ == "__main__":
    unittest.main()
