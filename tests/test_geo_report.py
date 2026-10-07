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


if __name__ == "__main__":
    unittest.main()
