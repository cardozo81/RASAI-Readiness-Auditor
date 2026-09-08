from __future__ import annotations

from pathlib import Path
import re
import tempfile
import unittest

from rasai.report_navigation import _PREMIUM_CSS, normalize_report_navigation


class ReportVisualContractTests(unittest.TestCase):
    def test_shared_card_and_table_radius_contract(self) -> None:
        self.assertIn("--radius:5px", _PREMIUM_CSS)
        self.assertNotIn("border-left:3px solid rgba(101,127,198,.18)", _PREMIUM_CSS)
        self.assertIn(".metric,.score-meta div,.page-summary div,.remediation-grid>div,.confidence-explain>div{border:0;background:#f7f8fb;border-radius:5px}", _PREMIUM_CSS)
        self.assertIn(".score-card{border:1px solid var(--line);border-left-width:4px;border-radius:5px", _PREMIUM_CSS)
        self.assertIn(".table-wrap{border-color:var(--line);border-radius:0", _PREMIUM_CSS)
        self.assertIn("table{border-radius:0}", _PREMIUM_CSS)
        self.assertIn("@media(max-width:700px)", _PREMIUM_CSS)
        self.assertIn(".table-wrap{border-radius:0}", _PREMIUM_CSS)

    def test_m20_table_has_visual_breathing_room(self) -> None:
        self.assertIn("#remediation-ai-telemetry .table-wrap{margin-top:14px}", _PREMIUM_CSS)

    def test_footer_is_last_element_inside_main_after_enrichment(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report_dir = Path(tmp)
            (report_dir / "ai-usage.html").write_text(
                "<html><body><aside class='app-nav'><nav></nav></aside><main>"
                "<header class='hero'>Topo</header>"
                "<footer class='footer'>Rodapé</footer>"
                "<section id='remediation-ai-telemetry' class='panel'>M20</section>"
                "</main></body></html>",
                encoding="utf-8",
            )

            normalize_report_navigation(report_dir)
            normalize_report_navigation(report_dir)

            html = (report_dir / "ai-usage.html").read_text(encoding="utf-8")
            main_match = re.search(r"<main>(.*?)</main>", html, re.DOTALL)
            self.assertIsNotNone(main_match)
            main = main_match.group(1)
            self.assertEqual(main.count("<footer class='footer'>"), 1)
            self.assertTrue(main.rstrip().endswith("</footer>"))
            self.assertLess(main.index("remediation-ai-telemetry"), main.index("<footer"))


if __name__ == "__main__":
    unittest.main()
