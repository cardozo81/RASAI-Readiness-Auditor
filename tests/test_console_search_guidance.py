from __future__ import annotations

from types import SimpleNamespace
import unittest

from rasai.console_search_guidance import _safe_google_depth, depth_guidance
from rasai.search_intelligence.config import SerpRuntimeConfig


class ConsoleSearchGuidanceTests(unittest.TestCase):
    def _config(self, **overrides) -> SerpRuntimeConfig:
        values = dict(
            mode="live",
            provider="serpapi",
            max_queries=10,
            max_requests=10,
            max_depth=20,
            max_competitors=10,
            timeout_seconds=20.0,
            retries=1,
            min_interval_seconds=1.0,
        )
        values.update(overrides)
        return SerpRuntimeConfig(**values).validate()

    def test_depth_guidance_explains_positions_and_google_pagination(self) -> None:
        state = SimpleNamespace(search_queries=("a",), search_depth=20)
        rendered = " ".join(depth_guidance(state, self._config()))
        self.assertIn("posição orgânica", rendered)
        self.assertIn("Top 10", rendered)
        self.assertIn("Top 20", rendered)
        self.assertIn("blocos de até 10 posições", rendered)

    def test_three_terms_at_depth_twenty_warn_about_twelve_request_ceiling(self) -> None:
        state = SimpleNamespace(
            search_queries=("seguro de vida", "seguro carro", "título de capitalização"),
            search_depth=20,
        )
        rendered = " ".join(depth_guidance(state, self._config()))
        self.assertIn("teto é 12 requests", rendered)
        self.assertIn("limite atual 10", rendered)
        self.assertIn("depth <= 10", rendered)

    def test_safe_depth_accounts_for_queries_and_retries(self) -> None:
        self.assertEqual(_safe_google_depth(self._config(), 3), 10)
        self.assertEqual(_safe_google_depth(self._config(), 1), 20)


if __name__ == "__main__":
    unittest.main()
