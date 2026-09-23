"""Focused tests for BR-GEO-050, BR-GEO-051 and BR-GEO-053 helpers."""

from __future__ import annotations

import unittest

from rasai.pre_scoring_rules import _duplicate_pairs


class PreScoringRuleTests(unittest.TestCase):
    def test_exact_and_near_duplicates_are_limited_to_supplied_audited_universe(self) -> None:
        pairs = _duplicate_pairs({
            "P1": "Produto premium com garantia de dois anos e suporte especializado",
            "P2": "Produto premium com garantia de dois anos e suporte especializado",
            "P3": "Conteúdo completamente diferente sobre outro assunto",
        })
        self.assertEqual(len(pairs), 1)
        self.assertEqual(pairs[0][:2], ("P1", "P2"))
        self.assertEqual(pairs[0][2], 1.0)

    def test_short_distinct_content_is_not_forced_into_duplicate(self) -> None:
        self.assertEqual(_duplicate_pairs({"P1": "Comprar", "P2": "Vender"}), ())


if __name__ == "__main__":
    unittest.main()
