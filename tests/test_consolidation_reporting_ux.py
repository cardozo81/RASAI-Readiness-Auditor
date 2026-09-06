from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from searchgeo.consolidation.service import generate, normalize_filter
from tests.test_consolidation import _make_audit


class ConsolidationReportingUXTests(unittest.TestCase):
    def test_single_audit_is_rendered_as_snapshot_with_methodology(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_audit(
                root,
                "AUD-001",
                when="2026-09-05T10:00:00-03:00",
                score=97.22,
                scoring_version="SCORE-GEO-002",
            )
            result = generate(root, normalize_filter(domains=("example.com",), devices=("MOBILE",)))
            html = result.report_path.read_text(encoding="utf-8")
            self.assertIn("Snapshot", html)
            self.assertIn("Versão do método de pontuação", html)
            self.assertIn("SCORE-GEO-002", html)
            self.assertNotIn("SCORE-GEO-001", html)
            self.assertIn("Nenhuma observação é removida apenas", html)
            self.assertIn("Validação externa do SCORE-GEO", html)
            self.assertIn("Pesquisar", html)
            self.assertIn("Linhas por página", html)
            self.assertNotIn("—%", html)
            self.assertNotIn('{&quot;HIGH&quot;', html)

            manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["report_format_version"], "CONS-2")
            self.assertEqual(manifest["summary"]["historical_mode"], "Snapshot")
            self.assertEqual(manifest["aggregation_policy"]["outliers"], "no_automatic_removal")

    def test_three_comparable_audits_render_historical_chart(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for index, score in enumerate((70.0, 80.0, 90.0), 1):
                _make_audit(
                    root,
                    f"AUD-00{index}",
                    when=f"2026-0{6 + index}-01T10:00:00-03:00",
                    score=score,
                    scoring_version="SCORE-GEO-002",
                )
            result = generate(root, normalize_filter(domains=("example.com",), devices=("MOBILE",)))
            html = result.report_path.read_text(encoding="utf-8")
            self.assertIn("Série histórica descritiva", html)
            self.assertIn("Evolução da Compatibilidade GEO", html)
            self.assertIn("<svg", html)
            self.assertIn("Compatibilidade GEO", html)
            self.assertIn("Cobertura", html)
            self.assertIn("Matriz histórica das dimensões", html)

    def test_identical_request_still_reuses_cons2_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_audit(root, "AUD-001", when="2026-09-05T10:00:00-03:00", scoring_version="SCORE-GEO-002")
            filters = normalize_filter(domains=("example.com",))
            first = generate(root, filters)
            second = generate(root, filters)
            self.assertFalse(first.reused)
            self.assertTrue(second.reused)
            self.assertEqual(first.report_path, second.report_path)


if __name__ == "__main__":
    unittest.main()
