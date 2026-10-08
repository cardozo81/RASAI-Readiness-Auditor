"""Focused read-only GEO projection and source-isolation contract tests."""
from __future__ import annotations

from contextlib import closing
import sqlite3
import tempfile
import unittest
from pathlib import Path

from rasai.geo_report import geo_body


class GeoReportTests(unittest.TestCase):
    def test_no_optional_tables_is_explicitly_inconclusive(self):
        with tempfile.TemporaryDirectory() as temp:
            db = Path(temp) / "audit.db"
            with closing(sqlite3.connect(db)) as con, con:
                con.execute("CREATE TABLE marker (id INTEGER)")
            before = db.read_bytes()
            html = geo_body(db, "AUD-TEST")
            self.assertIn("Não há execução", html)
            self.assertIn("não é possível concluir", html)
            self.assertEqual(before, db.read_bytes())

    def test_sources_are_audit_scoped_and_html_escaped(self):
        with tempfile.TemporaryDirectory() as temp:
            db = Path(temp) / "audit.db"
            with closing(sqlite3.connect(db)) as con, con:
                con.executescript("""
                    CREATE TABLE perplexity_search_runs (
                        run_id TEXT PRIMARY KEY, audit_id TEXT, query_json TEXT,
                        search_type TEXT, status TEXT, started_at TEXT, error_class TEXT
                    );
                    CREATE TABLE perplexity_search_sources (
                        run_id TEXT, position INTEGER, url TEXT, title TEXT, snippet TEXT
                    );
                """)
                con.execute("INSERT INTO perplexity_search_runs VALUES (?,?,?,?,?,?,?)",
                            ("r1","AUD-ONE",'["question <script>"]',"web","SUCCESS","2026-10-07",None))
                con.execute("INSERT INTO perplexity_search_runs VALUES (?,?,?,?,?,?,?)",
                            ("r2","AUD-TWO",'["private"]',"web","SUCCESS","2026-10-07",None))
                con.execute("INSERT INTO perplexity_search_sources VALUES (?,?,?,?,?)",
                            ("r1",1,"https://www.example.org/path","<bad>","snippet"))
                con.execute("INSERT INTO perplexity_search_sources VALUES (?,?,?,?,?)",
                            ("r2",1,"https://different.org","other","other"))
            html = geo_body(db, "AUD-ONE")
            self.assertIn("example.org", html)
            self.assertNotIn("different.org", html)
            self.assertIn("&lt;script&gt;", html)
            self.assertNotIn("<script>", html)


    def test_cross_source_comparison_requires_single_query_and_observed_api(self):
        with tempfile.TemporaryDirectory() as temp:
            db = Path(temp) / "audit.db"
            with closing(sqlite3.connect(db)) as con, con:
                con.executescript("""
                    CREATE TABLE perplexity_search_runs (
                        run_id TEXT PRIMARY KEY, audit_id TEXT, query_json TEXT,
                        search_type TEXT, status TEXT, started_at TEXT, error_class TEXT
                    );
                    CREATE TABLE perplexity_search_sources (
                        run_id TEXT, position INTEGER, url TEXT, title TEXT, snippet TEXT
                    );
                    CREATE TABLE serp_observations (
                        observation_id TEXT, audit_id TEXT, query TEXT,
                        collected_at TEXT, observation_status TEXT, data_mode TEXT
                    );
                    CREATE TABLE serp_results (
                        observation_id TEXT, url TEXT
                    );
                    CREATE TABLE geo_observation_runs (
                        analysis_id TEXT, audit_id TEXT, projection_json TEXT,
                        created_at TEXT
                    );
                """)
                con.execute("INSERT INTO perplexity_search_runs VALUES (?,?,?,?,?,?,?)",
                            ("r1","AUD-ONE",'["insurance premium"]',"web","SUCCESS","2026-10-07",None))
                con.execute("INSERT INTO perplexity_search_sources VALUES (?,?,?,?,?)",
                            ("r1",1,"https://example.org/policy","Policy","snippet"))
                con.execute("INSERT INTO serp_observations VALUES (?,?,?,?,?,?)",
                            ("s1","AUD-ONE","insurance premium","2026-10-07","OBSERVED","OBSERVED_API"))
                con.execute("INSERT INTO serp_results VALUES (?,?)",
                            ("s1","https://example.org/policy"))
                con.execute(
                    "INSERT INTO geo_observation_runs VALUES (?,?,?,?)",
                    ("g1", "AUD-ONE",
                     '{"perplexity_run_id":"r1","serp_observation_id":"s1","serp_url_count":1,'
                     '"perplexity_url_count":1,"url_overlap_count":1}',
                     "2026-10-07")
                )
            self.assertIn("Sobreposição observacional", geo_body(db, "AUD-ONE"))
            self.assertIn("1 em ambas", geo_body(db, "AUD-ONE"))
            self.assertIn("não comprova escopo de país, idioma, dispositivo", geo_body(db, "AUD-ONE"))


    def test_extraction_warning_visible_without_perplexity_run(self):
        from rasai.geo_report import geo_body
        with tempfile.TemporaryDirectory() as root:
            folder = Path(root)
            db = folder / "audit.db"
            with closing(sqlite3.connect(db)) as con, con:
                con.execute("CREATE TABLE placeholder (id TEXT)")
            quality_path = folder / "artifacts" / "geo-extraction-quality.json"
            quality_path.parent.mkdir(parents=True)
            quality_path.write_text(
                '{"observations":[{"state":"NAVIGATION_DOMINATED_SUSPECTED",'
                '"artifact_ref":"artifacts/extraction/SNP-1/main_content.txt",'
                '"word_count":11}]}', encoding="utf-8"
            )
            page = geo_body(db, "AUD-ONE")
            self.assertIn("Confiabilidade da extração principal", page)
            self.assertIn("Não há execução Perplexity Search", page)

    def test_optional_recommendations_with_partial_schema_do_not_break_geo(self):
        from rasai.geo_report import _geo_relevant_findings
        with tempfile.TemporaryDirectory() as temp:
            db = Path(temp) / "audit.db"
            with closing(sqlite3.connect(db)) as con, con:
                con.execute(
                    "CREATE TABLE findings (finding_id TEXT, audit_id TEXT, "
                    "rule_id TEXT, category TEXT, severity TEXT, title TEXT, "
                    "evidence_ids TEXT, observed_value TEXT, expected_condition TEXT)"
                )
                con.execute("CREATE TABLE recommendations (finding_id TEXT, title TEXT)")
                con.execute(
                    "INSERT INTO findings VALUES (?,?,?,?,?,?,?,?,?)",
                    ("F1", "AUD-1", "HTML-1", "HTML", "HIGH", "HTML main empty",
                     "[]", "empty", "content"),
                )
            findings = _geo_relevant_findings(db, "AUD-1")
            self.assertEqual(len(findings), 1)
            self.assertEqual(findings[0]["finding_id"], "F1")

    def test_geo_section_visual_separation_and_foreign_tld_hint(self):
        from rasai.geo_report import geo_body
        with tempfile.TemporaryDirectory() as temp:
            db = Path(temp) / "audit.db"
            with closing(sqlite3.connect(db)) as con, con:
                con.executescript("""
                    CREATE TABLE perplexity_search_runs (
                        run_id TEXT PRIMARY KEY, audit_id TEXT, query_json TEXT,
                        search_type TEXT, status TEXT, started_at TEXT
                    );
                    CREATE TABLE perplexity_search_sources (
                        run_id TEXT, position INTEGER, url TEXT, title TEXT, snippet TEXT
                    );
                """)
                con.execute(
                    "INSERT INTO perplexity_search_runs VALUES (?,?,?,?,?,?)",
                    ("PX-1", "AUD-1", '["seguro de vida"]', "web", "SUCCESS", "2026-10-08")
                )
                con.execute(
                    "INSERT INTO perplexity_search_sources VALUES (?,?,?,?,?)",
                    ("PX-1", 1, "https://ejemplo.es/seguros", "Seguro", "Fragmento")
                )
            html = geo_body(db, "AUD-1")
            self.assertIn('class="geo-view"', html)
            self.assertIn(".geo-view > section", html)
            self.assertIn("overflow-x:auto", html)
            self.assertLess(html.index("Domínios das fontes observadas"), html.index("Evidências externas para análise competitiva"))
            self.assertIn("TLD estrangeiro", html)
            self.assertIn("ejemplo.es", html)
            self.assertIn("não prova que a fonte seja irrelevante", html)

    def test_existing_competitive_ai_is_reused_only_with_evidence_ids(self):
        from rasai.geo_report import _prior_competitive_ai
        with tempfile.TemporaryDirectory() as temp:
            db = Path(temp) / "audit.db"
            with closing(sqlite3.connect(db)) as con, con:
                con.execute("""
                    CREATE TABLE serp_competitive_ai_analyses (
                        observation_id TEXT, audit_id TEXT, state TEXT,
                        provider TEXT, model TEXT, contract_version TEXT,
                        prompt_id TEXT, prompt_version TEXT, summary TEXT,
                        opportunities_json TEXT, evidence_ref TEXT, evidence_sha256 TEXT
                    )
                """)
                con.execute(
                    "INSERT INTO serp_competitive_ai_analyses VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    ("SERP-1", "AUD-ONE", "AVAILABLE", "TEST", "m1",
                     "COMPETITIVE-AI-001", "p1", "v1", "Hypothesis",
                     '[{"title":"Check clarity","recommendation":"Review headline",'
                     '"evidence_ids":["E1"]},'
                     '{"title":"Uncited guess","recommendation":"Unverifiable",'
                     '"evidence_ids":[]}]',
                     "artifacts/source.json", "deadbeef"),
                )
            matching = _prior_competitive_ai(db, "AUD-ONE", "SERP-1")
            self.assertIsNotNone(matching)
            self.assertEqual(len(matching["opportunities"]), 1)
            self.assertIsNone(_prior_competitive_ai(db, "AUD-TWO", "SERP-1"))
            self.assertIsNone(_prior_competitive_ai(db, "AUD-ONE", "SERP-UNKNOWN"))


if __name__ == "__main__":
    unittest.main()
