from __future__ import annotations

import unittest

from rasai.m3 import _align_title_observation_to_rendered_artifact
from rasai.remediation import RemediationRecipe, recipe_for
from rasai.rendering import BrowserRenderResult, RenderedElementObservation


class HotfixSmokeReportIntegrityTests(unittest.TestCase):
    def test_one_item_recipe_steps_are_normalized_as_tuples(self) -> None:
        recipe = RemediationRecipe(
            rule_id="BR-TEST",
            title="Teste",
            target="Documento",
            element=None,
            location=None,
            action="REVIEW",
            description="Teste de normalização.",
            example=None,
            acceptance="Critério único.",  # type: ignore[arg-type]
            validation="Revalidar uma vez.",  # type: ignore[arg-type]
        )

        self.assertEqual(recipe.acceptance, ("Critério único.",))
        self.assertEqual(recipe.validation, ("Revalidar uma vez.",))

    def test_all_current_recipes_expose_step_collections_not_strings(self) -> None:
        rule_ids = (
            "BR-GEO-005",
            "BR-GEO-011",
            "BR-GEO-012",
            "BR-GEO-013",
            "BR-GEO-014",
            "BR-GEO-017",
            "BR-GEO-018",
            *(f"BR-GEO-{number:03d}" for number in range(28, 50)),
            "BR-GEO-999",
        )

        for rule_id in rule_ids:
            with self.subTest(rule_id=rule_id):
                recipe = recipe_for(rule_id)
                self.assertIsInstance(recipe.acceptance, tuple)
                self.assertIsInstance(recipe.validation, tuple)
                self.assertTrue(all(isinstance(item, str) for item in recipe.acceptance))
                self.assertTrue(all(isinstance(item, str) for item in recipe.validation))

        br_040 = recipe_for("BR-GEO-040")
        self.assertEqual(br_040.acceptance, ("A resposta é compreensível no contexto da página.",))
        self.assertEqual(br_040.validation, ("Reexecutar BR-GEO-040.",))

    def test_title_observation_uses_same_serialized_dom_consumed_by_semantic_analysis(self) -> None:
        result = BrowserRenderResult(
            requested_url="https://example.com/viagem",
            final_url="https://example.com/viagem",
            http_status=200,
            content_type="text/html",
            rendered_html=(
                "<!doctype html><html><head>"
                "<title>Seguro Viagem | Exemplo</title>"
                "</head><body><h1>Seguro Viagem</h1></body></html>"
            ),
            browser_metadata={},
            element_observations=(
                RenderedElementObservation(
                    selector="title",
                    tag_name="title",
                    element_id=None,
                    classes=(),
                    outer_html="<title>Marca genérica alterada depois</title>",
                    text_excerpt="Marca genérica alterada depois",
                    bounding_box=None,
                ),
                RenderedElementObservation(
                    selector="h1",
                    tag_name="h1",
                    element_id=None,
                    classes=(),
                    outer_html="<h1>Seguro Viagem</h1>",
                    text_excerpt="Seguro Viagem",
                    bounding_box={"x": 1.0, "y": 2.0, "width": 100.0, "height": 20.0},
                ),
            ),
        )

        observations = _align_title_observation_to_rendered_artifact(result)
        titles = [item for item in observations if item.tag_name == "title"]
        headings = [item for item in observations if item.tag_name == "h1"]

        self.assertEqual(len(titles), 1)
        self.assertEqual(titles[0].selector, "title")
        self.assertEqual(titles[0].outer_html, "<title>Seguro Viagem | Exemplo</title>")
        self.assertNotIn("Marca genérica alterada depois", titles[0].outer_html or "")
        self.assertEqual(len(headings), 1)
        self.assertEqual(headings[0].outer_html, "<h1>Seguro Viagem</h1>")

    def test_late_live_title_is_not_persisted_when_serialized_dom_has_no_title(self) -> None:
        result = BrowserRenderResult(
            requested_url="https://example.com/sem-title",
            final_url="https://example.com/sem-title",
            http_status=200,
            content_type="text/html",
            rendered_html="<html><head></head><body><main>Conteúdo</main></body></html>",
            browser_metadata={},
            element_observations=(
                RenderedElementObservation(
                    selector="title",
                    tag_name="title",
                    element_id=None,
                    classes=(),
                    outer_html="<title>Adicionado depois</title>",
                    text_excerpt="Adicionado depois",
                    bounding_box=None,
                ),
            ),
        )

        observations = _align_title_observation_to_rendered_artifact(result)

        self.assertFalse(any(item.tag_name == "title" for item in observations))


if __name__ == "__main__":
    unittest.main()
