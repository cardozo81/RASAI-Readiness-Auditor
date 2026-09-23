"""Focused regression tests for the BR-GEO-025..027 corrective."""

from __future__ import annotations

import unittest

from rasai.content_extractability import _evaluate, _material_qualifiers
from rasai.domain import RuleResult
from rasai.extraction import ContentExtractor


class ContentExtractabilityGapTests(unittest.TestCase):
    def test_main_content_and_meaningful_non_boilerplate_do_not_use_word_thresholds(self) -> None:
        extracted = ContentExtractor().extract(
            "<html><body><nav>Menu</nav><main><p>OK.</p></main><footer>Rodapé</footer></body></html>"
        )
        evaluations = _evaluate(extracted, extracted.main_content)

        self.assertEqual(evaluations["BR-GEO-025"][0], RuleResult.PASS)
        self.assertEqual(evaluations["BR-GEO-026"][0], RuleResult.PASS)
        self.assertEqual(evaluations["BR-GEO-027"][0], RuleResult.PASS)

    def test_material_qualifier_loss_is_warning_not_semantic_fail(self) -> None:
        extracted = ContentExtractor().extract(
            "<html><body><main><p>Plano custa R$ 199,90 e inclui 20 GB por 30 dias.</p></main></body></html>"
        )
        qualifiers = _material_qualifiers(extracted.main_content)
        self.assertIn("r$ 199,90", qualifiers)
        self.assertIn("20 gb", qualifiers)
        self.assertIn("30 dias", qualifiers)

        evaluations = _evaluate(extracted, "Plano inclui 20 GB por 30 dias.")
        self.assertEqual(evaluations["BR-GEO-027"][0], RuleResult.WARNING)
        self.assertEqual(
            evaluations["BR-GEO-027"][3],
            "MATERIAL_QUALIFIERS_LOST_DURING_EXTRACTION",
        )

    def test_missing_rendered_document_stays_unknown(self) -> None:
        evaluations = _evaluate(None, None)
        self.assertEqual(evaluations["BR-GEO-025"][0], RuleResult.UNKNOWN)
        self.assertEqual(evaluations["BR-GEO-026"][0], RuleResult.UNKNOWN)
        self.assertEqual(evaluations["BR-GEO-027"][0], RuleResult.UNKNOWN)


if __name__ == "__main__":
    unittest.main()
