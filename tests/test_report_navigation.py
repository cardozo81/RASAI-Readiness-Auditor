from __future__ import annotations

from datetime import datetime, timezone
from html import unescape
from pathlib import Path
import re
import tempfile
import unittest

from rasai.report_contract import CANONICAL_NAV_ITEMS
from rasai.report_navigation import normalize_report_navigation


_LINK_RE = re.compile(r"<a class='([^']*)' href='([^']+)'>([^<]+)</a>")
_NAV_RE = re.compile(r"<nav>(.*?)</nav>", re.DOTALL)


class ReportNavigationTests(unittest.TestCase):
    def test_all_generated_pages_share_canonical_order_current_item_and_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report_dir = Path(tmp)
            filenames = [filename for _, filename in CANONICAL_NAV_ITEMS]
            for index, filename in enumerate(filenames):
                old_links = "".join(f"<a href='{name}'>{name}</a>" for name in reversed(filenames[: index + 1]))
                (report_dir / filename).write_text(
                    f"<html><body><aside><nav>{old_links}</nav></aside><main>{filename}</main></body></html>",
                    encoding="utf-8",
                )

            normalize_report_navigation(
                report_dir,
                generated_at=datetime(2026, 9, 4, 1, 30, 45, tzinfo=timezone.utc),
                software_version="9.9.9",
            )

            expected = [(filename, label) for label, filename in CANONICAL_NAV_ITEMS]
            for filename in filenames:
                html = (report_dir / filename).read_text(encoding="utf-8")
                nav_match = _NAV_RE.search(html)
                self.assertIsNotNone(nav_match, filename)
                links = _LINK_RE.findall(nav_match.group(1))
                self.assertEqual([(href, unescape(label)) for _, href, label in links], expected, filename)
                active = [href for css_class, href, _ in links if css_class == "active"]
                self.assertEqual(active, [filename], filename)
                self.assertNotIn("Versão 9.9.9", html)
                self.assertIn("Gerado em 03/09/2026 22:30:45 - Horário de Brasília", html)

    def test_versioned_alias_is_not_treated_as_a_canonical_report_page(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report_dir = Path(tmp)
            (report_dir / "index.html").write_text(
                "<html><body><aside><nav></nav></aside><main>ok</main></body></html>",
                encoding="utf-8",
            )
            alias = report_dir / "score-geo-004.html"
            alias_html = "<html><head><meta http-equiv='refresh' content='0;url=scoring.html'></head></html>"
            alias.write_text(alias_html, encoding="utf-8")

            normalize_report_navigation(report_dir)

            self.assertEqual(alias.read_text(encoding="utf-8"), alias_html)
            self.assertIn("<aside class='app-nav'", (report_dir / "index.html").read_text(encoding="utf-8"))

    def test_optional_pages_are_omitted_until_their_files_exist(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report_dir = Path(tmp)
            for filename in ("index.html", "mobile.html", "remediation.html", "ai-usage.html", "references.html"):
                (report_dir / filename).write_text(
                    "<html><body><aside class='app-nav'><nav></nav></aside><main></main></body></html>",
                    encoding="utf-8",
                )

            normalize_report_navigation(report_dir)

            html = (report_dir / "index.html").read_text(encoding="utf-8")
            nav_match = _NAV_RE.search(html)
            self.assertIsNotNone(nav_match)
            hrefs = [href for _, href, _ in _LINK_RE.findall(nav_match.group(1))]
            self.assertEqual(
                hrefs,
                ["index.html", "mobile.html", "remediation.html", "ai-usage.html", "references.html"],
            )
            self.assertNotIn("desktop.html", hrefs)
            self.assertNotIn("content-suggestions.html", hrefs)
            self.assertNotIn("accessibility.html", hrefs)
            self.assertNotIn("web-performance.html", hrefs)

    def test_premium_css_and_br_geo_tooltips_are_shared_and_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report_dir = Path(tmp)
            (report_dir / "css").mkdir()
            (report_dir / "css" / "site.css").write_text("body{margin:0}\n", encoding="utf-8")
            (report_dir / "index.html").write_text(
                "<html><body><aside class='app-nav'><nav></nav></aside>"
                "<main><p>BR-GEO-005 · Página tecnicamente recuperável</p>"
                "<code>BR-GEO-006</code></main></body></html>",
                encoding="utf-8",
            )

            normalize_report_navigation(report_dir)
            normalize_report_navigation(report_dir)

            css = (report_dir / "css" / "site.css").read_text(encoding="utf-8")
            html = (report_dir / "index.html").read_text(encoding="utf-8")
            self.assertEqual(css.count("rasai-premium-report-v2"), 1)
            self.assertIn("grid-template-columns:minmax(0,1fr) minmax(320px,390px)", css)
            self.assertIn("@media(max-width:700px)", css)
            self.assertIn(".snapshot>figure{grid-column:2;grid-row:1", css)
            self.assertIn(".snapshot>figure{grid-column:1;grid-row:1", css)
            self.assertEqual(html.count("class='br-rule-tooltip'"), 1)
            self.assertIn("Severidade HIGH · Verifica se a página é tecnicamente recuperável.", html)
            self.assertIn("<code>BR-GEO-006</code>", html)

    def test_accessibility_keeps_canonical_position_when_materialized(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report_dir = Path(tmp)
            for filename in (
                "index.html",
                "content-suggestions.html",
                "accessibility.html",
                "web-performance.html",
                "ai-usage.html",
                "references.html",
            ):
                (report_dir / filename).write_text(
                    "<html><body><aside class='app-nav'><nav></nav></aside><main></main></body></html>",
                    encoding="utf-8",
                )
            normalize_report_navigation(report_dir)
            html = (report_dir / "index.html").read_text(encoding="utf-8")
            hrefs = [href for _, href, _ in _LINK_RE.findall(_NAV_RE.search(html).group(1))]
            self.assertLess(hrefs.index("accessibility.html"), hrefs.index("web-performance.html"))
            self.assertLess(hrefs.index("web-performance.html"), hrefs.index("content-suggestions.html"))

    def test_ai_cost_total_sums_m18_and_m20_without_double_counting(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report_dir = Path(tmp)
            (report_dir / "ai-usage.html").write_text(
                "<html><body><aside class='app-nav'><nav></nav></aside><main>"
                "<header class='hero'><div class='metric'><small>Custo estimado total</small>"
                "<strong>0.01000000 USD</strong></div></header>"
                "<section id='remediation-ai-telemetry' class='panel'><div class='metric'>"
                "<small>Custo estimado</small><strong>0.00250000 USD</strong></div></section>"
                "</main></body></html>",
                encoding="utf-8",
            )

            normalize_report_navigation(report_dir)
            normalize_report_navigation(report_dir)

            html = (report_dir / "ai-usage.html").read_text(encoding="utf-8")
            self.assertEqual(html.count("data-api-cost-total='true'"), 1)
            self.assertIn("Consumo projetado total de APIs com custo estimado: 0.01250000 USD", html)
            self.assertIn("Análise semântica por IA 0.01000000 USD + Remediação textual por IA 0.00250000 USD", html)
            self.assertIn("não inclui integrações sem estimated_cost persistido", html)


if __name__ == "__main__":
    unittest.main()
