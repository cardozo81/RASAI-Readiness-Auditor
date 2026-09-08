from __future__ import annotations

import unittest

from rasai.report_presentation import humanize_report_html, public_label


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
        self.assertIn("<td>Alta (P1)</td>", rendered)
        self.assertIn("<td>Estrutura semântica</td>", rendered)
        self.assertIn("<td>Confiança da evidência</td>", rendered)
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
        self.assertIn("<td>HTTP_429</td>", rendered)
        self.assertIn("<td>SCORE-GEO-004</td>", rendered)

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

    def test_public_label_is_conservative_for_unknown_values(self) -> None:
        self.assertEqual(public_label("NOT_CONFIGURED"), "Não configurado")
        self.assertEqual(public_label("LIGHTHOUSE_ARTIFACT"), "LIGHTHOUSE_ARTIFACT")
        self.assertEqual(public_label("BR-GEO-001"), "BR-GEO-001")


if __name__ == "__main__":
    unittest.main()
