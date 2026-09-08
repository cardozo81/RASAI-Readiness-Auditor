from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from rasai.report_semantics import enhance_report_html


class ReportSemanticTests(unittest.TestCase):
    def test_score_page_explains_low_confidence_and_structured_data_absence(self) -> None:
        html = (
            "<html><body><main><header><span>Confiança baixa</span></header>"
            "<section><h2>Dimensões Mobile</h2><table><tbody>"
            "<tr><td>Capacidade de indexação</td><td>75.0</td><td>67%</td><td>Baixa</td><td>Parcial</td></tr>"
            "<tr><td>Dados estruturados</td><td>-</td><td>0%</td><td>Indisponível</td><td>Não aplicável</td></tr>"
            "</tbody></table></section></main></body></html>"
        )
        with tempfile.TemporaryDirectory() as tmp:
            output = enhance_report_html(html, page_name="mobile.html", report_dir=Path(tmp))
        self.assertIn("Por que a confiança está baixa?", output)
        self.assertIn("Capacidade de indexação", output)
        self.assertIn("Opcional / não detectado", output)
        self.assertIn("não significa que a dimensão inteira saiu do SARI", output)
        self.assertIn("BR-GEO-034", output)
        self.assertIn("ausência é uma lacuna leve, não falha de coleta", output)

    def test_lighthouse_and_cwv_use_documented_threshold_states(self) -> None:
        html = (
            "<html><body><main><header></header>"
            "<h4>Core Web Vitals · dados reais CrUX</h4>"
            "<div class='metric'><small>Performance</small><strong>49/100</strong></div>"
            "<div class='metric'><small>CWV</small><strong>FAIL</strong></div>"
            "<div class='metric'><small>LCP p75</small><strong>3034 ms</strong></div>"
            "<div class='metric'><small>INP p75</small><strong>382 ms</strong></div>"
            "<div class='metric'><small>CLS p75</small><strong>0.900</strong></div>"
            "</main></body></html>"
        )
        with tempfile.TemporaryDirectory() as tmp:
            output = enhance_report_html(html, page_name="web-performance.html", report_dir=Path(tmp))
        self.assertIn("Ruim (0-49)", output)
        self.assertIn("Não aprovado no p75", output)
        self.assertEqual(output.count("Precisa melhorar</span>"), 2)
        self.assertIn("<span class='result-tag bad'>Ruim</span>", output)
        self.assertIn("Faixas Core Web Vitals", output)

    def test_accessibility_distinguishes_occurrences_from_audits_and_wcag(self) -> None:
        html = (
            "<html><body><main><header>"
            "<div class='metric'><small>Falhas automatizadas</small><strong>3</strong></div>"
            "<div class='metric'><small>Lighthouse médio</small><strong>78/100</strong></div>"
            "<div class='metric'><small>Conformidade WCAG</small><strong>NÃO DETERMINADA</strong></div>"
            "</header>"
            "<details><summary>a</summary><div><p><strong>Audit Lighthouse:</strong> <code>image-alt</code></p></div></details>"
            "<details><summary>b</summary><div><p><strong>Audit Lighthouse:</strong> <code>image-alt</code></p></div></details>"
            "<details><summary>c</summary><div><p><strong>Audit Lighthouse:</strong> <code>link-name</code></p></div></details>"
            "</main></body></html>"
        )
        with tempfile.TemporaryDirectory() as tmp:
            output = enhance_report_html(html, page_name="accessibility.html", report_dir=Path(tmp))
        self.assertIn("Ocorrências automatizadas", output)
        self.assertIn("3 ocorrência(s) em 2 audit(s)", output)
        self.assertIn("Requer avaliação humana", output)
        self.assertEqual(output.count("Prioridade alta"), 3)

    def test_apdex_profile_is_reconciled_from_persisted_device_configuration(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report_dir = root / "report"
            report_dir.mkdir()
            db = sqlite3.connect(root / "audit.db")
            db.execute("CREATE TABLE synthetic_apdex_runs(configuration TEXT)")
            db.execute("CREATE TABLE synthetic_apdex_summaries(url TEXT, device TEXT, profile_id TEXT)")
            configuration = {
                "mobile_profile": {
                    "profile_id": "RASAI_MOBILE_TEST",
                    "cpu_slowdown": 4.0,
                    "rtt_ms": 150.0,
                    "download_kbps": 1638.4,
                    "upload_kbps": 750.0,
                    "viewport": {"width": 412, "height": 915},
                },
                "desktop_profile": {
                    "profile_id": "RASAI_DESKTOP_TEST",
                    "cpu_slowdown": 1.0,
                    "rtt_ms": 40.0,
                    "download_kbps": 10240.0,
                    "upload_kbps": 10240.0,
                    "viewport": {"width": 1440, "height": 900},
                },
            }
            db.execute("INSERT INTO synthetic_apdex_runs VALUES (?)", (json.dumps(configuration),))
            db.execute(
                "INSERT INTO synthetic_apdex_summaries VALUES (?,?,?)",
                ("https://example.test/", "MOBILE", "RASAI_MOBILE_TEST"),
            )
            db.commit()
            db.close()
            html = (
                "<html><body><main><header></header>"
                "<article class='page-card apdex-card'>"
                "<span class='badge'>MOBILE</span><h3 class='page-url'>https://example.test/</h3>"
                "<div class='metric'><small>Apdex</small><strong>1.00 [8.0]*</strong></div>"
                "<p class='intro'><strong>Perfil sintético:</strong> RASAI_DESKTOP_TEST · CPU 1.0×</p>"
                "<div class='notice'><strong>Correlação com campo</strong><span>CrUX/Core Web Vitals também não aprovou neste contexto.</span></div>"
                "</article></main></body></html>"
            )
            output = enhance_report_html(html, page_name="apdex.html", report_dir=report_dir)
            second = enhance_report_html(output, page_name="apdex.html", report_dir=report_dir)
        self.assertIn("RASAI_MOBILE_TEST", output)
        self.assertNotIn("RASAI_DESKTOP_TEST", output)
        self.assertIn("T=8s", output)
        self.assertIn("notice warn", output)
        self.assertEqual(second.count("apdex-conflict"), 1)
        self.assertEqual(second.count("apdex-threshold-note"), 1)


if __name__ == "__main__":
    unittest.main()
