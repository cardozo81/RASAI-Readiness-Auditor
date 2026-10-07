"""Focused deterministic and replay-safe GEO snapshot contract tests."""
from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from rasai.geo_observation import materialize_geo_observation


class GeoObservationTests(unittest.TestCase):
    def test_idempotent_snapshot_and_per_query_provenance(self):
        with tempfile.TemporaryDirectory() as temp:
            db = Path(temp) / "audit.db"
            with sqlite3.connect(db) as con:
                con.executescript("""
                    CREATE TABLE audits (audit_id TEXT PRIMARY KEY);
                    CREATE TABLE perplexity_search_runs (
                        run_id TEXT PRIMARY KEY, audit_id TEXT, query_json TEXT,
                        search_type TEXT, status TEXT, started_at TEXT
                    );
                    CREATE TABLE perplexity_search_sources (
                        run_id TEXT, position INTEGER, url TEXT, title TEXT,
                        snippet TEXT, source_date TEXT, last_updated TEXT
                    );
                    CREATE TABLE serp_observations (
                        observation_id TEXT, audit_id TEXT, query TEXT,
                        collected_at TEXT, observation_status TEXT, data_mode TEXT
                    );
                    CREATE TABLE serp_results (
                        observation_id TEXT, position INTEGER, url TEXT
                    );
                """)
                con.execute("INSERT INTO audits VALUES ('AUD-1')")
                con.execute("INSERT INTO perplexity_search_runs VALUES (?,?,?,?,?,?)",
                            ("RUN-1", "AUD-1", '["seguro de vida"]', "web", "SUCCESS", "2026-10-07"))
                con.execute("INSERT INTO perplexity_search_sources VALUES (?,?,?,?,?,?,?)",
                            ("RUN-1", 1, "https://example.org/seguro", "Title", "", None, None))
                con.execute("INSERT INTO serp_observations VALUES (?,?,?,?,?,?)",
                            ("SERP-1","AUD-1","seguro de vida","2026-10-07","OBSERVED","OBSERVED_API"))
                con.execute("INSERT INTO serp_results VALUES (?,?,?)",
                            ("SERP-1",1,"https://example.org/seguro"))
            first = materialize_geo_observation(db, "AUD-1")
            self.assertEqual(first, materialize_geo_observation(db, "AUD-1"))
            with sqlite3.connect(db) as con:
                self.assertEqual(con.execute("PRAGMA integrity_check").fetchone()[0], "ok")
                self.assertEqual(con.execute("SELECT count(*) FROM geo_observation_runs").fetchone()[0], 1)
                data = json.loads(con.execute(
                    "SELECT projection_json FROM geo_observation_runs"
                ).fetchone()[0])
            self.assertEqual(data["perplexity_run_id"], "RUN-1")
            self.assertEqual(data["serp_observation_id"], "SERP-1")
            self.assertEqual(data["url_overlap_count"], 1)

    def test_multi_query_abstains_from_serp_attribution(self):
        with tempfile.TemporaryDirectory() as temp:
            db = Path(temp) / "audit.db"
            with sqlite3.connect(db) as con:
                con.executescript("""
                    CREATE TABLE audits (audit_id TEXT PRIMARY KEY);
                    CREATE TABLE perplexity_search_runs (
                        run_id TEXT PRIMARY KEY, audit_id TEXT, query_json TEXT,
                        search_type TEXT, status TEXT, started_at TEXT
                    );
                    CREATE TABLE perplexity_search_sources (
                        run_id TEXT, position INTEGER, url TEXT, title TEXT,
                        snippet TEXT, source_date TEXT, last_updated TEXT
                    );
                """)
                con.execute("INSERT INTO audits VALUES ('AUD-1')")
                con.execute("INSERT INTO perplexity_search_runs VALUES (?,?,?,?,?,?)",
                            ("RUN-1", "AUD-1", '["one","two"]', "web", "SUCCESS", "2026-10-07"))
            materialize_geo_observation(db, "AUD-1")
            with sqlite3.connect(db) as con:
                data = json.loads(con.execute(
                    "SELECT projection_json FROM geo_observation_runs"
                ).fetchone()[0])
            self.assertIsNone(data["serp_observation_id"])
            self.assertIsNone(data["url_overlap_count"])


if __name__ == "__main__":
    unittest.main()
