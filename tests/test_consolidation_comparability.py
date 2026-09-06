from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from searchgeo.consolidation.index import ConsolidationIndex
from searchgeo.consolidation.service import build_data, normalize_filter
from tests.test_consolidation import _make_audit


class ConsolidationComparabilityTests(unittest.TestCase):
    def test_score_series_uses_latest_comparable_url_universe(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_audit(
                root,
                "AUD-001",
                when="2026-08-01T10:00:00-03:00",
                urls=("https://example.com/a",),
                score=50.0,
                scoring_version="1",
            )
            _make_audit(
                root,
                "AUD-002",
                when="2026-09-01T10:00:00-03:00",
                urls=("https://example.com/a", "https://example.com/b"),
                score=90.0,
                scoring_version="1",
            )
            index = ConsolidationIndex(root)
            index.refresh()
            data = build_data(index, normalize_filter(devices=("MOBILE",)))
            overall = next(item for item in data.scores if item.dimension == "OVERALL_READINESS")
            self.assertEqual(overall.url_universes, 2)
            self.assertEqual(overall.statistics.count, 1)
            self.assertEqual(overall.statistics.current, 90.0)
            self.assertIn("universos distintos", overall.limitation or "")

    def test_performance_current_is_mean_of_latest_value_per_url(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_audit(
                root,
                "AUD-001",
                when="2026-08-01T10:00:00-03:00",
                urls=("https://example.com/a", "https://example.com/b"),
            )
            _make_audit(
                root,
                "AUD-002",
                when="2026-09-01T10:00:00-03:00",
                urls=("https://example.com/a",),
            )
            index = ConsolidationIndex(root)
            index.refresh()
            data = build_data(index, normalize_filter(devices=("MOBILE",)))
            performance = next(item for item in data.performance if item.device == "MOBILE")
            metric = next(item for item in performance.metrics if item.name == "Performance Lighthouse")
            # URL A latest=0.901 (AUD-002), URL B latest=0.902 (AUD-001).
            self.assertAlmostEqual(metric.statistics.current or 0.0, (0.901 + 0.902) / 2.0)


if __name__ == "__main__":
    unittest.main()
