"""Focused read-only GEO projection and source-isolation contract tests."""
from __future__ import annotations
import sqlite3
import tempfile
import unittest
from pathlib import Path

from rasai.geo_report import geo_body


class GeoReportTests(unittest.TestCase):
    def test_no_optional_tables_is_explicitly_inconclusive(self):
        with tempfile.TemporaryDirectory() as temp:
            db = Path(temp) / "audit.db"
            with sqlite3.connect(db) as con:
                con.execute("CREATE TABLE marker (id INTEGER)")
            before = db.read_bytes()
            html = geo_body(db, "AUD-TEST")
            self.assertIn("Não há execução", html)
            self.assertIn("não é possível concluir", html)
            self.assertEqual(before, db.read_bytes())

    def test_sources_are_audit_scoped_and_html_escaped(self):
        with tempfile.TemporaryDirectory() as temp:
            db = Path(temp) / "audit.db"
            with sqlite3.connect(db) as con:
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
            with sqlite3.connect(db) as con:
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


    def test_existing_competitive_ai_is_reused_only_with_evidence_ids(self):
        from rasai.geo_report import _prior_competitive_ai
        with tempfile.TemporaryDirectory() as temp:
            db = Path(temp) / "audit.db"
            with sqlite3.connect(db) as con:
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
