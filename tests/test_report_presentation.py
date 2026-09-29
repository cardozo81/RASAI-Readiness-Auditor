from __future__ import annotations

import unittest

from rasai.report_presentation import SCORING_CONCEPT_LABELS, humanize_report_html, public_label
from rasai.score_geo_004 import FEATURE_ORDER, GROUP_WEIGHTS


class ReportPresentationTests(unittest.TestCase):
    def test_humanizes_only_primary_visible_machine_values(self) -> None:
        html = (
            "<table><tr>"
            "<td>MOBILE</td><td>NOT_CONSOLIDATED</td><td>HIGH</td><td>P1</td>"
            "<td>SEMANTIC_STRUCTURE</td><td>EVIDENCE_TRUST</td>"
            "</tr></table>"
            "<div class='metric'><span>Status</span><strong>UNAVAILABLE</strong></div>"
            "<span class='badge'>SUCCESS</span>"
        )

        rendered = humanize_report_html(html, page_name="scoring.html")

        self.assertIn("<td>Mobile</td>", rendered)
        self.assertIn("<td>Não consolidado</td>", rendered)
        self.assertIn("<td>Alta</td>", rendered)
        self.assertIn("<td>Muito alta (P1)</td>", rendered)
        self.assertIn("<td>Estrutura semântica</td>", rendered)
        self.assertIn("<td>Evidências e confiabilidade</td>", rendered)
        self.assertIn("<strong>Indisponível</strong>", rendered)
        self.assertIn("<span class='badge'>Concluído</span>", rendered)

    def test_preserves_technical_identifiers_and_diagnostic_content(self) -> None:
        html = (
            "<p>Estado persistido: UNAVAILABLE.</p>"
            "<code>NOT_CONSOLIDATED</code>"
            "<pre>{\"status\": \"FAILED\", \"reason_code\": \"HTTP_429\"}</pre>"
            "<td>BR-GEO-054</td>"
            "<td>HTTP_429</td>"
            "<td>SCORE-GEO-004</td>"
        )

        rendered = humanize_report_html(html, page_name="references.html")

        self.assertIn("<p>Estado persistido: Indisponível.</p>", rendered)
        self.assertIn("<code>NOT_CONSOLIDATED</code>", rendered)
        self.assertIn('<pre>{"status": "FAILED", "reason_code": "HTTP_429"}</pre>', rendered)
        self.assertIn("<td>BR-GEO-054</td>", rendered)
        self.assertIn("<td>HTTP 429 - limite de requisições</td>", rendered)
        self.assertIn("<td>SCORE-GEO-004</td>", rendered)

    def test_preserves_canonical_hyphenated_contract_identifiers(self) -> None:
        html = (
            "<strong>CRAWLING-DISCOVERY-001</strong>"
            "<p>Contrato CRAWLING-DISCOVERY-001 permanece rastreável.</p>"
            "<td>SCORE-GEO-004</td>"
        )

        rendered = humanize_report_html(html)

        self.assertIn("<strong>CRAWLING-DISCOVERY-001</strong>", rendered)
        self.assertIn("Contrato CRAWLING-DISCOVERY-001 permanece rastreável.", rendered)
        self.assertIn("<td>SCORE-GEO-004</td>", rendered)
        self.assertNotIn("CRAWLING-DESCOBERTA-001", rendered)

    def test_humanizes_internal_execution_codes_and_visible_em_dash(self) -> None:
        html = (
            "<p>Motivo: AI_NOT_AUTHORIZED_FOR_EXECUTION — escopo TARGET_SITE.</p>"
            "<td>EXECUTION_POLICY</td><td>AUDIT</td>"
            "<code>AI_NOT_AUTHORIZED_FOR_EXECUTION — TARGET_SITE</code>"
            "<pre>EXECUTION_POLICY — AUDIT</pre>"
        )

        rendered = humanize_report_html(html)

        self.assertIn("Motivo: IA não autorizada para execução nesta auditoria - escopo Site / propriedade auditada.", rendered)
        self.assertIn("<td>Política de execução</td>", rendered)
        self.assertIn("<td>Auditoria</td>", rendered)
        self.assertIn("<code>AI_NOT_AUTHORIZED_FOR_EXECUTION — TARGET_SITE</code>", rendered)
        self.assertIn("<pre>EXECUTION_POLICY — AUDIT</pre>", rendered)
        self.assertNotIn("AI_NOT_AUTHORIZED_FOR_EXECUTION - escopo TARGET_SITE", rendered)

    def test_humanizes_monitoring_and_quality_states_without_losing_priority_code(self) -> None:
        html = (
            "<td>REGRESSED</td><td>DATA_UNAVAILABLE</td><td>PARTIAL_OVERLAP</td>"
            "<td>SUPPORTED_BY_PERSISTED_EVIDENCE</td><td>NOT_OBSERVED</td>"
            "<strong>P0</strong>"
        )

        rendered = humanize_report_html(html)

        self.assertIn("<td>Regrediu</td>", rendered)
        self.assertIn("<td>Dados indisponíveis</td>", rendered)
        self.assertIn("<td>Sobreposição parcial</td>", rendered)
        self.assertIn("<td>Suportada pela evidência persistida</td>", rendered)
        self.assertIn("<td>Não observado</td>", rendered)
        self.assertIn("<strong>Crítica (P0)</strong>", rendered)

    def test_localizes_visible_aware_timestamps_but_preserves_technical_blocks(self) -> None:
        html = (
            "<p>Gerado em 2026-09-10T22:02:15+00:00.</p>"
            "<td>2026-09-10T21:02:15Z</td>"
            "<code>2026-09-10T22:02:15+00:00</code>"
            "<pre>2026-09-10T22:02:15+00:00</pre>"
            "<span data-created='2026-09-10T22:02:15+00:00'>2026-09-10</span>"
        )

        rendered = humanize_report_html(html)

        self.assertIn("Gerado em 10/09/2026 19:02:15 (America/Sao_Paulo).", rendered)
        self.assertIn("<td>10/09/2026 18:02:15 (America/Sao_Paulo)</td>", rendered)
        self.assertIn("<code>2026-09-10T22:02:15+00:00</code>", rendered)
        self.assertIn("<pre>2026-09-10T22:02:15+00:00</pre>", rendered)
        self.assertIn("data-created='2026-09-10T22:02:15+00:00'", rendered)
        self.assertIn(">2026-09-10</span>", rendered)
        self.assertEqual(rendered, humanize_report_html(rendered))

    def test_public_label_is_conservative_for_unknown_values(self) -> None:
        self.assertEqual(public_label("NOT_CONFIGURED"), "Não configurado")
        self.assertEqual(public_label("LIGHTHOUSE_ARTIFACT"), "Artefato Lighthouse")
        self.assertEqual(public_label("BR-GEO-001"), "BR-GEO-001")

    def test_scoring_contract_has_human_labels_for_every_dimension_and_group(self) -> None:
        # The external SARI corroboration is an installed pre-publication scoring
        # extension, so its presentation vocabulary is registered by the same installer.
        from rasai.external_sari_reporting import install as install_external_sari_reporting

        install_external_sari_reporting()
        expected = set(FEATURE_ORDER)
        expected.update(group for groups in GROUP_WEIGHTS.values() for group in groups)
        missing = sorted(item for item in expected if item not in SCORING_CONCEPT_LABELS)
        self.assertEqual(missing, [])
        for item in expected:
            label = public_label(item)
            self.assertNotEqual(label, item)
            self.assertNotIn("_", label)

    def test_conceptual_scoring_terms_are_presented_in_pt_br(self) -> None:
        self.assertEqual(public_label("INDEXABILITY"), "Indexabilidade e canonicalização")
        self.assertEqual(public_label("STRUCTURED_DATA"), "Dados estruturados")
        self.assertEqual(public_label("CONTENT_VALUE"), "Valor do conteúdo")
        self.assertEqual(public_label("CITATION_READINESS"), "Preparação para citação")
        self.assertEqual(public_label("BLOCKED"), "Bloqueado")
        self.assertEqual(public_label("UNKNOWN"), "Não determinado")

    def test_legacy_standalone_dimension_labels_are_normalized_across_reports(self) -> None:
        html = (
            "<h4>Capacidade de indexação</h4>"
            "<td>Extração de conteúdo</td>"
            "<span>Estrutura semântica</span>"
            "<strong>Dados estruturados</strong>"
            "<p>Capacidade de indexação continua explicada nesta frase.</p>"
        )
        rendered = humanize_report_html(html, page_name="readiness.html")
        self.assertIn("<h4>Indexabilidade e canonicalização</h4>", rendered)
        self.assertIn("<td>Renderização e extração</td>", rendered)
        self.assertIn("<span>Estrutura semântica</span>", rendered)
        self.assertIn("<strong>Dados estruturados</strong>", rendered)
        self.assertIn("Capacidade de indexação continua explicada nesta frase.</p>", rendered)

    def test_humanization_remains_idempotent_after_concept_normalization(self) -> None:
        html = "<td>CONTENT_VALUE</td><td>Valor do conteúdo</td><td>BLOCKED</td>"
        once = humanize_report_html(html, page_name="scoring.html")
        twice = humanize_report_html(once, page_name="scoring.html")
        self.assertEqual(once, twice)
        self.assertIn("<td>Valor do conteúdo</td>", once)
        self.assertIn("<td>Bloqueado</td>", once)


if __name__ == "__main__":
    unittest.main()
