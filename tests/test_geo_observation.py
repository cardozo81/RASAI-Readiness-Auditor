"""Focused deterministic and replay-safe GEO snapshot contract tests."""
from __future__ import annotations

from contextlib import closing

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
            with closing(sqlite3.connect(db)) as con, con:
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
            with closing(sqlite3.connect(db)) as con, con:
                self.assertEqual(con.execute("PRAGMA integrity_check").fetchone()[0], "ok")
                self.assertEqual(con.execute("SELECT count(*) FROM geo_observation_runs").fetchone()[0], 1)
                data = json.loads(con.execute(
                    "SELECT projection_json FROM geo_observation_runs"
                ).fetchone()[0])
            self.assertEqual(data["perplexity_run_id"], "RUN-1")
            self.assertEqual(data["serp_observation_id"], "SERP-1")
            self.assertEqual(data["url_overlap_count"], 1)
            descriptive = data["descriptive_overlap"]
            self.assertEqual(descriptive["status"], "DESCRIPTIVE_ONLY")
            self.assertEqual(descriptive["serp_denominator"], 1)
            self.assertEqual(descriptive["perplexity_denominator"], 1)
            self.assertEqual(descriptive["common_urls"], 1)
            self.assertEqual(descriptive["serp_overlap_rate"], 1.0)
            self.assertEqual(descriptive["perplexity_overlap_rate"], 1.0)
            self.assertEqual(descriptive["jaccard_url_rate"], 1.0)

    def test_target_observation_explains_alternative_and_absence_without_causality(self):
        from rasai.geo_observation import _target_observation
        with closing(sqlite3.connect(":memory:")) as con, con:
            con.row_factory = sqlite3.Row
            con.execute("CREATE TABLE audit_targets (target_id TEXT, audit_id TEXT, input_url TEXT)")
            con.execute("INSERT INTO audit_targets VALUES (?,?,?)",
                        ("target", "AUD-1", "https://example.org/seguro"))
            run = {"run_id": "RUN-1", "status": "SUCCESS"}
            alt = _target_observation(
                con, "AUD-1", run, ["seguro"],
                [{"url": "https://example.org/other", "position": 1}]
            )
            self.assertEqual(alt["status"], "DOMAIN_ALTERNATIVE_OBSERVED")
            missing = _target_observation(
                con, "AUD-1", run, ["seguro"],
                [{"url": "https://competitor.org/policy", "position": 1}]
            )
            self.assertEqual(missing["status"], "TARGET_NOT_IN_RETURNED_SOURCES")
            self.assertIn("nao prova", missing["causality"])
            exact = _target_observation(
                con, "AUD-1", run, ["seguro"],
                [{"url": "https://www.example.org/seguro/", "position": 1}]
            )
            self.assertEqual(exact["status"], "EXACT_URL_OBSERVED")

    def test_multi_query_abstains_from_serp_attribution(self):
        with tempfile.TemporaryDirectory() as temp:
            db = Path(temp) / "audit.db"
            with closing(sqlite3.connect(db)) as con, con:
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
            with closing(sqlite3.connect(db)) as con, con:
                data = json.loads(con.execute(
                    "SELECT projection_json FROM geo_observation_runs"
                ).fetchone()[0])
            self.assertIsNone(data["serp_observation_id"])
            self.assertIsNone(data["url_overlap_count"])
            self.assertEqual(data["descriptive_overlap"]["status"], "NOT_COMPARABLE")
            self.assertEqual(data["descriptive_overlap"]["reason"], "UNATTRIBUTABLE_QUERY_SET")
            self.assertIsNone(data["descriptive_overlap"]["serp_overlap_rate"])


    def test_report_reprocessing_reuses_persisted_external_evidence(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        from rasai.report_completion import materialize_catalog_report_projection
        with tempfile.TemporaryDirectory() as temp:
            db = Path(temp) / "audit.db"
            with closing(sqlite3.connect(db)) as con, con:
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
                con.execute(
                    "INSERT INTO perplexity_search_runs VALUES (?,?,?,?,?,?)",
                    ("RUN-1", "AUD-1", '["insurance"]', "web", "SUCCESS", "2026-10-07")
                )
            workspace = SimpleNamespace(root=Path(temp), database=db)
            with patch("rasai.catalog_report_site.materialize_catalog_report_site") as html, patch(
                "rasai.catalog_report_site.catalog_report_is_fresh", return_value=True
            ):
                for _ in range(2):
                    completion = materialize_catalog_report_projection(
                        audit_id="AUD-1", workspace=workspace
                    )
                    self.assertFalse(completion.renderer_errors)
                self.assertEqual(html.call_count, 2)
            with closing(sqlite3.connect(db)) as con, con:
                self.assertEqual(
                    con.execute("SELECT count(*) FROM geo_observation_runs").fetchone()[0], 1
                )
                self.assertEqual(con.execute("PRAGMA integrity_check").fetchone()[0], "ok")


    def test_descriptive_metrics_are_directional_and_abstain_without_denominator(self):
        from rasai.geo_observation import _descriptive_overlap_metrics
        metrics = _descriptive_overlap_metrics(
            {"example.org/a", "example.org/b"},
            {"example.org/b", "example.org/c", "example.org/d"},
            serp_id="SERP-1", query_set=["insurance"], search_status="SUCCESS",
        )
        self.assertEqual(metrics["status"], "DESCRIPTIVE_ONLY")
        self.assertEqual(metrics["serp_denominator"], 3)
        self.assertEqual(metrics["perplexity_denominator"], 2)
        self.assertEqual(metrics["common_urls"], 1)
        self.assertEqual(metrics["serp_overlap_rate"], 0.3333)
        self.assertEqual(metrics["perplexity_overlap_rate"], 0.5)
        self.assertEqual(metrics["jaccard_url_rate"], 0.25)
        self.assertEqual(metrics["serp_only_count"], 2)
        self.assertEqual(metrics["perplexity_only_count"], 1)
        empty = _descriptive_overlap_metrics(
            set(), {"example.org/c"}, serp_id="SERP-1",
            query_set=["insurance"], search_status="SUCCESS",
        )
        self.assertEqual(empty["reason"], "NO_VALID_URL_DENOMINATOR")
        self.assertIsNone(empty["jaccard_url_rate"])
        missing = _descriptive_overlap_metrics(
            {"example.org/a"}, {"example.org/a"}, serp_id=None,
            query_set=["insurance"], search_status="SUCCESS",
        )
        self.assertEqual(missing["reason"], "NO_EQUIVALENT_OBSERVED_SERP_QUERY")
        self.assertIsNone(missing["serp_denominator"])
        failed = _descriptive_overlap_metrics(
            {"example.org/a"}, {"example.org/a"}, serp_id="SERP-1",
            query_set=["insurance"], search_status="TIMEOUT_ERROR",
        )
        self.assertEqual(failed["reason"], "EXTERNAL_SEARCH_NOT_SUCCESSFUL")
        self.assertIsNone(failed["common_urls"])



if __name__ == "__main__":
    unittest.main()
