import unittest

from rasai.m15_style_overrides import SCORE_LAYOUT_CSS


class M15ScoreLayoutTests(unittest.TestCase):
    def test_score_grid_models_all_six_legacy_cells_and_responsive_fallbacks(self) -> None:
        self.assertIn("minmax(210px,1.45fr)", SCORE_LAYOUT_CSS)
        self.assertIn("minmax(145px,.78fr)", SCORE_LAYOUT_CSS)
        self.assertIn(".score-number", SCORE_LAYOUT_CSS)
        self.assertIn("white-space:nowrap", SCORE_LAYOUT_CSS)
        self.assertIn("max-width:1200px", SCORE_LAYOUT_CSS)
        self.assertIn("max-width:820px", SCORE_LAYOUT_CSS)
        self.assertIn("grid-template-columns:1fr!important", SCORE_LAYOUT_CSS)


if __name__ == "__main__":
    unittest.main()
