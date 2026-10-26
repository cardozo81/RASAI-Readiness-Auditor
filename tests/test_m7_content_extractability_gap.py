"""Focused regression tests for the BR-GEO-025..027 corrective."""

from __future__ import annotations

import unittest
from hashlib import sha256
from types import SimpleNamespace

from rasai.content_extractability import _evaluate, _material_qualifiers, _extract_for_comparison
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


    def test_attested_hidden_overlay_is_not_reported_as_lost_essential_content(self) -> None:
        """#665 WIKI-R02: only the same attested visible DOM is comparable."""
        from tempfile import TemporaryDirectory
        from pathlib import Path

        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            rel = "artifacts/rendered/example.html"
            artifact = root / rel
            artifact.parent.mkdir(parents=True)
            html = (
                "<html><head><title>Wikipedia</title></head><body><main>"
                "<p>Enciclopédia livre. Capacidade pública 20 GB.</p>"
                "<div class='overlay-banner-main'><p>$13 ocultos.</p>"
                "<p>Less than 2% invisível.</p></div>"
                "</main></body></html>"
            )
            artifact.write_text(html, encoding="utf-8")
            digest = sha256(artifact.read_bytes()).hexdigest()
            css_marker = sha256(b"overlay-banner-main").hexdigest()
            snapshot = SimpleNamespace(
                rendered_artifact_ref=rel,
                browser_metadata={
                    "architecture_artifact_binding": {"rendered_sha256": digest},
                    "dom_visibility": {
                        "version": "dom-visibility-v1",
                        "source": "CHROMIUM_COMPUTED_STYLE",
                        "status": "OBSERVED",
                        "rendered_sha256": digest,
                        "hidden_ids_sha256": [],
                        "hidden_classes_sha256": [css_marker],
                    },
                },
            )
            workspace = SimpleNamespace(root=root)
            extractor = ContentExtractor()
            # M4 and content-extractability must consume the same witness.
            filtered = _extract_for_comparison(extractor, html, snapshot, workspace)
            assert "$13" not in filtered.main_content
            assert "20 GB" in filtered.main_content
            persisted_main = filtered.main_content
            raw = extractor.extract(html)
            self.assertEqual(
                _evaluate(raw, persisted_main)["BR-GEO-027"][0], RuleResult.WARNING,
                "Regression fixture must recreate the old false-positive",
            )
            self.assertEqual(
                _evaluate(filtered, persisted_main)["BR-GEO-027"][0], RuleResult.PASS,
            )
            self.assertEqual(
                _evaluate(filtered, "Enciclopédia livre.")["BR-GEO-027"][0],
                RuleResult.WARNING,
                "Real loss of a visible material qualifier must stay detectable",
            )
            # Invalidating the stored rendered bytes must reject the witness.
            artifact.write_text(html + "<!-- changed -->", encoding="utf-8")
            unattested = _extract_for_comparison(extractor, html, snapshot, workspace)
            self.assertEqual(
                _evaluate(unattested, persisted_main)["BR-GEO-027"][0],
                RuleResult.WARNING,
            )

    def test_missing_rendered_document_stays_unknown(self) -> None:
        evaluations = _evaluate(None, None)
        self.assertEqual(evaluations["BR-GEO-025"][0], RuleResult.UNKNOWN)
        self.assertEqual(evaluations["BR-GEO-026"][0], RuleResult.UNKNOWN)
        self.assertEqual(evaluations["BR-GEO-027"][0], RuleResult.UNKNOWN)


if __name__ == "__main__":
    unittest.main()
