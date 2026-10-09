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
                            ("RUN-1", "AUD-1", '["seguro de vida"]', "web", "SUCCESS", "2026-10-07T10:00:00+00:00"))
                con.execute("INSERT INTO perplexity_search_sources VALUES (?,?,?,?,?,?,?)",
                            ("RUN-1", 1, "https://example.org/seguro", "Title", "", None, None))
                con.execute("INSERT INTO serp_observations VALUES (?,?,?,?,?,?)",
                            ("SERP-1","AUD-1","seguro de vida","2026-10-07T10:05:00+00:00","OBSERVED","OBSERVED_API"))
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
            self.assertEqual(exact["status"], "DOMAIN_ALTERNATIVE_OBSERVED")
            truly_exact = _target_observation(
                con, "AUD-1", run, ["seguro"],
                [{"url": "https://example.org/seguro", "position": 1}]
            )
            self.assertEqual(truly_exact["status"], "EXACT_URL_OBSERVED")

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


    def test_v3_projection_preserves_v1_snapshot_and_replays_idempotently(self):
        with tempfile.TemporaryDirectory() as root:
            db = Path(root) / "audit.db"
            old_projection = '{"legacy":true}'
            with closing(sqlite3.connect(db)) as con, con:
                con.execute("PRAGMA foreign_keys=ON")
                con.executescript("""
                    CREATE TABLE audits(audit_id TEXT PRIMARY KEY);
                    CREATE TABLE perplexity_search_runs(
                        run_id TEXT PRIMARY KEY, audit_id TEXT, query_json TEXT,
                        search_type TEXT, status TEXT, started_at TEXT
                    );
                    CREATE TABLE perplexity_search_sources(
                        run_id TEXT, position INTEGER, url TEXT, title TEXT,
                        snippet TEXT, source_date TEXT, last_updated TEXT
                    );
                    CREATE TABLE geo_observation_runs(
                        analysis_id TEXT PRIMARY KEY,
                        audit_id TEXT NOT NULL REFERENCES audits(audit_id) ON DELETE CASCADE,
                        perplexity_run_id TEXT NOT NULL REFERENCES perplexity_search_runs(run_id)
                            ON DELETE CASCADE,
                        serp_observation_id TEXT, contract_version TEXT NOT NULL,
                        input_sha256 TEXT NOT NULL, projection_json TEXT NOT NULL,
                        created_at TEXT NOT NULL
                    );
                """)
                con.execute("INSERT INTO audits VALUES ('AUD-1')")
                con.execute(
                    "INSERT INTO perplexity_search_runs VALUES (?,?,?,?,?,?)",
                    ("RUN-1", "AUD-1", '["seguro"]', "web", "SUCCESS", "2026-10-07"),
                )
                con.execute(
                    "INSERT INTO perplexity_search_sources VALUES (?,?,?,?,?,?,?)",
                    ("RUN-1", 1, "https://example.org/seguro", "Oferta", "", None, None),
                )
                con.execute(
                    "INSERT INTO geo_observation_runs VALUES (?,?,?,?,?,?,?,?)",
                    ("GEO-LEGACY", "AUD-1", "RUN-1", None,
                     "RASAI-GEO-OBSERVATION-1", "old-hash", old_projection, "2026-10-07"),
                )
                con.execute(
                    "INSERT INTO geo_observation_runs VALUES (?,?,?,?,?,?,?,?)",
                    ("GEO-V2", "AUD-1", "RUN-1", None,
                     "RASAI-GEO-OBSERVATION-2", "v2-hash",
                     '{"old_v2":true}', "2026-10-08"),
                )
                con.execute(
                    "INSERT INTO geo_observation_runs VALUES (?,?,?,?,?,?,?,?)",
                    ("GEO-V4", "AUD-1", "RUN-1", None,
                     "RASAI-GEO-OBSERVATION-4", "v4-hash",
                     '{"old_v4":true}', "2026-10-09"),
                )
            new_id = materialize_geo_observation(db, "AUD-1")
            self.assertIsNotNone(new_id)
            self.assertNotEqual(new_id, "GEO-LEGACY")
            self.assertEqual(new_id, materialize_geo_observation(db, "AUD-1"))
            with closing(sqlite3.connect(db)) as con:
                rows = con.execute(
                    "SELECT contract_version, projection_json FROM geo_observation_runs "
                    "ORDER BY contract_version"
                ).fetchall()
                self.assertEqual(len(rows), 4)
                self.assertEqual(rows[0], ("RASAI-GEO-OBSERVATION-1", old_projection))
                self.assertEqual(rows[1], ("RASAI-GEO-OBSERVATION-2", '{"old_v2":true}'))
                self.assertEqual(rows[2], ("RASAI-GEO-OBSERVATION-4", '{"old_v4":true}'))
                self.assertEqual(rows[3][0], "RASAI-GEO-OBSERVATION-8")
                self.assertIn("descriptive_overlap", json.loads(rows[3][1]))
                self.assertEqual(con.execute("PRAGMA foreign_key_check").fetchall(), [])
                self.assertEqual(con.execute("PRAGMA integrity_check").fetchone()[0], "ok")

    def test_exact_url_comparison_preserves_scheme_port_query_and_ipv6(self):
        from rasai.geo_observation import _canonical_url, _host
        self.assertNotEqual(
            _canonical_url("https://www.example.org:443/a/?x=1#part"),
            _canonical_url("https://example.org/a?x=1"),
        )
        self.assertEqual(
            _canonical_url("https://www.example.org:443/a/?x=1#part"),
            _canonical_url("https://www.example.org/a/?x=1"),
        )
        self.assertNotEqual(
            _canonical_url("https://www.example.org/a/?x=1"),
            _canonical_url("https://www.example.org/a?x=1"),
        )
        self.assertEqual(_canonical_url("https://user:secret@example.org/a"), "")
        self.assertEqual(_canonical_url("https://user@example.org/a"), "")
        self.assertEqual(_canonical_url("https://example.org:0/a"), "")
        self.assertEqual(_canonical_url("https://example.org/a\\\\b"), "")
        self.assertEqual(_canonical_url("https://example.org/a b"), "")
        self.assertEqual(_host("https://user:secret@example.org/a"), "")
        from rasai.geo_observation import _canonical_url_v7
        self.assertEqual(
            _canonical_url_v7("https://example.org/a/"),
            _canonical_url_v7("https://example.org/a"),
        )
        self.assertNotEqual(
            _canonical_url("https://example.org/a/"),
            _canonical_url("https://example.org/a"),
        )
        self.assertNotEqual(
            _canonical_url("http://example.org/a"),
            _canonical_url("https://example.org/a"),
        )
        self.assertNotEqual(
            _canonical_url("https://example.org:8443/a"),
            _canonical_url("https://example.org/a"),
        )
        self.assertNotEqual(
            _canonical_url("https://example.org/a?x=1"),
            _canonical_url("https://example.org/a?x=2"),
        )
        self.assertEqual(_canonical_url("https://[::1]:443/a"), "https://[::1]/a")
        self.assertEqual(_canonical_url("https://example.org:99999/a"), "")
        self.assertEqual(_host("ftp://example.org/a"), "")

    def test_comparability_records_serp_context_without_claiming_provider_equivalence(self):
        with tempfile.TemporaryDirectory() as temp:
            db = Path(temp) / "audit.db"
            with closing(sqlite3.connect(db)) as con, con:
                con.executescript("""
                    CREATE TABLE audits(audit_id TEXT PRIMARY KEY);
                    CREATE TABLE perplexity_search_runs(
                        run_id TEXT PRIMARY KEY, audit_id TEXT, query_json TEXT,
                        search_type TEXT, status TEXT, started_at TEXT
                    );
                    CREATE TABLE perplexity_search_sources(
                        run_id TEXT, position INTEGER, url TEXT, title TEXT,
                        snippet TEXT, source_date TEXT, last_updated TEXT
                    );
                    CREATE TABLE serp_observations(
                        observation_id TEXT, audit_id TEXT, query TEXT,
                        collected_at TEXT, observation_status TEXT, data_mode TEXT,
                        engine TEXT, country TEXT, region TEXT, language TEXT, device TEXT
                    );
                    CREATE TABLE serp_results(
                        observation_id TEXT, position INTEGER, url TEXT
                    );
                """)
                con.execute("INSERT INTO audits VALUES ('AUD-1')")
                con.execute("INSERT INTO perplexity_search_runs VALUES (?,?,?,?,?,?)",
                    ("PX-1", "AUD-1", '["Seguro de vida"]', "web", "SUCCESS", "2026-10-09T03:00:00Z"))
                con.execute("INSERT INTO perplexity_search_sources VALUES (?,?,?,?,?,?,?)",
                    ("PX-1", 1, "https://example.org/seguro", "Oferta", "", None, None))
                con.execute("INSERT INTO serp_observations VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    ("S-1", "AUD-1", " seguro de vida ", "2026-10-09T03:10:00Z",
                     "OBSERVED", "OBSERVED_API", "google", "BR", "São Paulo", "pt-BR", "mobile"))
                con.execute("INSERT INTO serp_results VALUES (?,?,?)",
                    ("S-1", 1, "http://example.org/seguro"))
            materialize_geo_observation(db, "AUD-1")
            with closing(sqlite3.connect(db)) as con:
                projection = json.loads(con.execute(
                    "SELECT projection_json FROM geo_observation_runs"
                ).fetchone()[0])
            self.assertEqual(projection["url_overlap_count"], 0)  # HTTPS != HTTP
            scope = projection["comparability"]
            self.assertTrue(scope["query_equivalent"])
            self.assertFalse(scope["geo_language_device_time_equivalence_proven"])
            self.assertEqual(scope["serp_context"]["country"], "BR")
            self.assertEqual(scope["serp_context"]["language"], "pt-BR")
            self.assertEqual(scope["serp_context"]["device"], "mobile")
            self.assertIsNone(scope["perplexity_context"]["geography_language_device"])
            self.assertTrue(scope["time_window_within_24h"])
            self.assertFalse(scope["intent_equivalence_proven"])
            self.assertEqual(scope["time_gap_seconds"], 600.0)

    def test_descriptive_metrics_are_directional_and_abstain_without_denominator(self):
        from rasai.geo_observation import _descriptive_overlap_metrics
        metrics = _descriptive_overlap_metrics(
            {"example.org/a", "example.org/b"},
            {"example.org/b", "example.org/c", "example.org/d"},
            serp_id="SERP-1", query_set=["insurance"], search_status="SUCCESS",
            time_gap_seconds=60,
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
            query_set=["insurance"], search_status="SUCCESS", time_gap_seconds=60,
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

    def test_temporal_scope_requires_timezone_and_bounded_gap(self):
        from rasai.geo_observation import _temporal_gap_seconds, _descriptive_overlap_metrics
        self.assertEqual(
            _temporal_gap_seconds("2026-10-09T12:00:00Z", "2026-10-09T09:00:00-03:00"),
            0.0,
        )
        self.assertIsNone(_temporal_gap_seconds("2026-10-09", "2026-10-09T12:00:00Z"))
        self.assertIsNone(_temporal_gap_seconds("not-a-date", "2026-10-09T12:00:00Z"))
        for gap, reason in ((None, "TIME_SCOPE_UNPROVEN"),
                            (86401, "TIME_SCOPE_OUTSIDE_WINDOW")):
            rates = _descriptive_overlap_metrics(
                {"https://example.org/a"}, {"https://example.org/a"},
                serp_id="SERP-1", query_set=["insurance"],
                search_status="SUCCESS", time_gap_seconds=gap,
            )
            self.assertEqual(rates["status"], "NOT_COMPARABLE")
            self.assertEqual(rates["reason"], reason)
            self.assertIsNone(rates["jaccard_url_rate"])
        boundary = _descriptive_overlap_metrics(
            {"https://example.org/a"}, {"https://example.org/a"},
            serp_id="SERP-1", query_set=["insurance"], search_status="SUCCESS",
            time_gap_seconds=86400,
        )
        self.assertEqual(boundary["status"], "DESCRIPTIVE_ONLY")


    def test_www_vs_apex_not_counted_as_exact_overlap_in_v6_snapshot(self):
        with tempfile.TemporaryDirectory() as root:
            db = Path(root) / "audit.db"
            with closing(sqlite3.connect(db)) as con, con:
                con.executescript("""
                    CREATE TABLE audits(audit_id TEXT PRIMARY KEY);
                    CREATE TABLE perplexity_search_runs(
                        run_id TEXT PRIMARY KEY, audit_id TEXT, query_json TEXT,
                        search_type TEXT, status TEXT, started_at TEXT
                    );
                    CREATE TABLE perplexity_search_sources(
                        run_id TEXT, position INTEGER, url TEXT, title TEXT,
                        snippet TEXT, source_date TEXT, last_updated TEXT
                    );
                    CREATE TABLE serp_observations(
                        observation_id TEXT, audit_id TEXT, query TEXT,
                        collected_at TEXT, observation_status TEXT, data_mode TEXT
                    );
                    CREATE TABLE serp_results(
                        observation_id TEXT, position INTEGER, url TEXT
                    );
                    CREATE TABLE audit_targets(
                        target_id TEXT, audit_id TEXT, input_url TEXT
                    );
                """)
                con.execute("INSERT INTO audits VALUES (?)", ("AUD-1",))
                con.execute("INSERT INTO audit_targets VALUES (?,?,?)",
                            ("T", "AUD-1", "https://www.example.org/a"))
                con.execute("INSERT INTO perplexity_search_runs VALUES (?,?,?,?,?,?)",
                            ("P-1", "AUD-1", '["insurance"]', "web", "SUCCESS",
                             "2026-10-09T10:00:00+00:00"))
                con.execute("INSERT INTO perplexity_search_sources VALUES (?,?,?,?,?,?,?)",
                            ("P-1", 1, "https://example.org/a", "Title", "", None, None))
                con.execute("INSERT INTO serp_observations VALUES (?,?,?,?,?,?)",
                            ("S-1", "AUD-1", "insurance", "2026-10-09T10:01:00+00:00",
                             "OBSERVED", "OBSERVED_API"))
                con.execute("INSERT INTO serp_results VALUES (?,?,?)",
                            ("S-1", 1, "https://www.example.org/a"))
            first = materialize_geo_observation(db, "AUD-1")
            assert first == materialize_geo_observation(db, "AUD-1")
            with closing(sqlite3.connect(db)) as con:
                value = json.loads(con.execute(
                    "SELECT projection_json FROM geo_observation_runs"
                ).fetchone()[0])
            self.assertEqual(value["contract_version"], "RASAI-GEO-OBSERVATION-8")
            self.assertEqual(value["descriptive_overlap"]["status"], "DESCRIPTIVE_ONLY")
            self.assertEqual(value["descriptive_overlap"]["common_urls"], 0)
            self.assertEqual(value["url_overlap_count"], 0)
            self.assertEqual(
                value["target_observation"]["status"],
                "DOMAIN_ALTERNATIVE_OBSERVED",
            )



if __name__ == "__main__":
    unittest.main()


def test_v6_prefers_nearest_trusted_serp_even_if_later_record_is_outside_window():
    """Original v5 selected the latest timestamp, losing a valid closer source."""
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
                    collected_at TEXT, observation_status TEXT, data_mode TEXT,
                    engine TEXT, country TEXT, region TEXT, language TEXT, device TEXT
                );
                CREATE TABLE serp_results (
                    observation_id TEXT, position INTEGER, url TEXT
                );
            """)
            con.execute("INSERT INTO audits VALUES ('AUD-ONE')")
            con.execute(
                "INSERT INTO perplexity_search_runs VALUES (?,?,?,?,?,?)",
                ("PX-1", "AUD-ONE", '["seguro vida"]', "web", "SUCCESS",
                 "2026-10-09T10:00:00+00:00"),
            )
            con.execute(
                "INSERT INTO perplexity_search_sources VALUES (?,?,?,?,?,?,?)",
                ("PX-1", 1, "https://example.org/a", "Title", "", None, None),
            )
            con.executemany(
                "INSERT INTO serp_observations VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                [
                    ("S-CLOSE", "AUD-ONE", "seguro vida", "2026-10-09T10:10:00+00:00",
                     "OBSERVED", "OBSERVED_API", "google", "BR", "São Paulo",
                     "pt-BR", "mobile"),
                    ("S-LATER-UNUSABLE", "AUD-ONE", "seguro vida",
                     "2026-10-11T10:00:00+00:00", "OBSERVED", "OBSERVED_API",
                     "google", "BR", "São Paulo", "pt-BR", "mobile"),
                ],
            )
            con.executemany(
                "INSERT INTO serp_results VALUES (?,?,?)",
                [
                    ("S-CLOSE", 1, "https://example.org/a"),
                    ("S-LATER-UNUSABLE", 1, "https://example.org/other"),
                ],
            )
        first = materialize_geo_observation(db, "AUD-ONE")
        assert first == materialize_geo_observation(db, "AUD-ONE")
        with closing(sqlite3.connect(db)) as con:
            raw = con.execute(
                "SELECT projection_json FROM geo_observation_runs WHERE analysis_id=?",
                (first,),
            ).fetchone()[0]
            assert con.execute("SELECT count(*) FROM geo_observation_runs").fetchone()[0] == 1
            assert con.execute("PRAGMA foreign_key_check").fetchall() == []
        snapshot = json.loads(raw)
        assert snapshot["contract_version"] == "RASAI-GEO-OBSERVATION-8"
        assert snapshot["serp_observation_id"] == "S-CLOSE"
        assert snapshot["descriptive_overlap"]["status"] == "DESCRIPTIVE_ONLY"
        assert snapshot["descriptive_overlap"]["common_urls"] == 1
        assert snapshot["comparability"]["time_gap_seconds"] == 600


def test_v6_abstains_if_all_serp_timestamps_are_untrusted_or_outside_window():
    from rasai.geo_observation import _temporal_gap_seconds
    assert _temporal_gap_seconds(
        "2026-10-09T10:00:00Z", "2026-10-11T10:00:00Z"
    ) > 86400
    assert _temporal_gap_seconds(
        "2026-10-09T10:00:00Z", "2026-10-09"
    ) is None


def _two_external_runs_for_v8(db: Path, *, ambiguous: bool = False) -> None:
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
        con.execute("INSERT INTO audits VALUES ('AUD-ONE')")
        con.executemany(
            "INSERT INTO perplexity_search_runs VALUES (?,?,?,?,?,?)",
            [
                ("PX-OLD", "AUD-ONE", '["seguro vida"]', "web", "SUCCESS",
                 "2026-10-09" if ambiguous else "2026-10-09T11:30:00+00:00"),
                ("PX-NEW", "AUD-ONE", '["seguro vida"]', "web", "AUTH_ERROR",
                 "2026-10-09" if ambiguous else "2026-10-09T09:00:00-03:00"),
                ("PX-FOREIGN", "AUD-FOREIGN", '["private"]', "web", "SUCCESS",
                 "2027-01-01T12:00:00+00:00"),
            ],
        )
        con.executemany(
            "INSERT INTO perplexity_search_sources VALUES (?,?,?,?,?,?,?)",
            [
                ("PX-OLD", 1, "https://example.org/old", "Old", "", None, None),
                ("PX-FOREIGN", 1, "https://other.org/secret", "Private", "", None, None),
            ],
        )


def test_v8_picks_actual_utc_latest_external_run_before_persisting_snapshot():
    with tempfile.TemporaryDirectory() as temp:
        db = Path(temp) / "audit.db"
        _two_external_runs_for_v8(db)
        result_id = materialize_geo_observation(db, "AUD-ONE")
        assert result_id is not None
        assert result_id == materialize_geo_observation(db, "AUD-ONE")
        with closing(sqlite3.connect(db)) as con:
            count = con.execute(
                "SELECT COUNT(*) FROM geo_observation_runs"
            ).fetchone()[0]
            payload = json.loads(con.execute(
                "SELECT projection_json FROM geo_observation_runs "
                "WHERE analysis_id=?", (result_id,),
            ).fetchone()[0])
            assert con.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert count == 1
        assert payload["contract_version"] == "RASAI-GEO-OBSERVATION-8"
        assert payload["perplexity_run_id"] == "PX-NEW"
        assert payload["search_status"] == "AUTH_ERROR"
        assert payload["source_count"] == 0
        assert payload["descriptive_overlap"]["status"] == "NOT_COMPARABLE"
        assert payload["descriptive_overlap"]["reason"] == "EXTERNAL_SEARCH_NOT_SUCCESSFUL"
        assert "PX-FOREIGN" not in str(payload)
        assert "PX-OLD" not in str(payload)


def test_v8_never_materializes_ambiguous_last_external_run_or_mutates_database():
    with tempfile.TemporaryDirectory() as temp:
        db = Path(temp) / "audit.db"
        _two_external_runs_for_v8(db, ambiguous=True)
        original = db.read_bytes()
        assert materialize_geo_observation(db, "AUD-ONE") is None
        assert materialize_geo_observation(db, "AUD-ONE") is None
        assert db.read_bytes() == original
        with closing(sqlite3.connect(db)) as con:
            assert con.execute(
                "SELECT 1 FROM sqlite_master WHERE name='geo_observation_runs'"
            ).fetchone() is None


def test_v8_snapshot_version_does_not_rewrite_older_geo_records():
    with tempfile.TemporaryDirectory() as temp:
        db = Path(temp) / "audit.db"
        _two_external_runs_for_v8(db)
        with closing(sqlite3.connect(db)) as con, con:
            con.execute("""
                CREATE TABLE geo_observation_runs (
                    analysis_id TEXT PRIMARY KEY,
                    audit_id TEXT NOT NULL REFERENCES audits(audit_id) ON DELETE CASCADE,
                    perplexity_run_id TEXT NOT NULL REFERENCES perplexity_search_runs(run_id)
                      ON DELETE CASCADE,
                    serp_observation_id TEXT, contract_version TEXT NOT NULL,
                    input_sha256 TEXT NOT NULL, projection_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)
            con.execute(
                "INSERT INTO geo_observation_runs VALUES (?,?,?,?,?,?,?,?)",
                ("GEO-HISTORICAL", "AUD-ONE", "PX-OLD", None,
                 "RASAI-GEO-OBSERVATION-7", "historical-fingerprint",
                 '{"historical":true}', "2026-10-09T10:00:00+00:00"),
            )
        result_id = materialize_geo_observation(db, "AUD-ONE")
        assert result_id and result_id != "GEO-HISTORICAL"
        with closing(sqlite3.connect(db)) as con:
            old = con.execute(
                "SELECT projection_json, contract_version FROM geo_observation_runs "
                "WHERE analysis_id='GEO-HISTORICAL'"
            ).fetchone()
            count = con.execute("SELECT COUNT(*) FROM geo_observation_runs").fetchone()[0]
        assert old == ('{"historical":true}', "RASAI-GEO-OBSERVATION-7")
        assert count == 2


def test_v8_materialized_overlap_refuses_unproved_slash_alias_and_userinfo():
    with tempfile.TemporaryDirectory() as temp:
        db = Path(temp) / "audit.db"
        with closing(sqlite3.connect(db)) as con, con:
            con.executescript("""
                CREATE TABLE audits(audit_id TEXT PRIMARY KEY);
                CREATE TABLE audit_targets(
                    target_id TEXT PRIMARY KEY, audit_id TEXT, input_url TEXT
                );
                CREATE TABLE perplexity_search_runs(
                    run_id TEXT PRIMARY KEY, audit_id TEXT, query_json TEXT,
                    search_type TEXT, status TEXT, started_at TEXT
                );
                CREATE TABLE perplexity_search_sources(
                    run_id TEXT, position INTEGER, url TEXT, title TEXT,
                    snippet TEXT, source_date TEXT, last_updated TEXT
                );
                CREATE TABLE serp_observations(
                    observation_id TEXT PRIMARY KEY, audit_id TEXT, query TEXT,
                    collected_at TEXT, observation_status TEXT, data_mode TEXT
                );
                CREATE TABLE serp_results(
                    observation_id TEXT, position INTEGER, url TEXT
                );
            """)
            con.execute("INSERT INTO audits VALUES (?)", ("AUD-URL-V8",))
            con.execute(
                "INSERT INTO audit_targets VALUES (?,?,?)",
                ("T1", "AUD-URL-V8", "https://example.org/produto"),
            )
            con.execute(
                "INSERT INTO perplexity_search_runs VALUES (?,?,?,?,?,?)",
                ("P1", "AUD-URL-V8", '["produto seguro"]',
                 "web", "SUCCESS", "2026-10-09T10:00:00+00:00"),
            )
            con.executemany(
                "INSERT INTO perplexity_search_sources VALUES (?,?,?,?,?,?,?)",
                [
                    ("P1", 1, "https://example.org/produto/", "Alternative", "", None, None),
                    ("P1", 2, "https://user:secret@example.org/produto", "Invalid", "", None, None),
                ],
            )
            con.execute(
                "INSERT INTO serp_observations VALUES (?,?,?,?,?,?)",
                ("S1", "AUD-URL-V8", "produto seguro",
                 "2026-10-09T10:05:00+00:00", "OBSERVED", "OBSERVED_API"),
            )
            con.execute(
                "INSERT INTO serp_results VALUES (?,?,?)",
                ("S1", 1, "https://example.org/produto"),
            )
        first = materialize_geo_observation(db, "AUD-URL-V8")
        assert first and first == materialize_geo_observation(db, "AUD-URL-V8")
        with closing(sqlite3.connect(db)) as con:
            rows = con.execute(
                "SELECT projection_json FROM geo_observation_runs"
            ).fetchall()
            assert len(rows) == 1
            value = json.loads(rows[0][0])
            assert con.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert value["contract_version"] == "RASAI-GEO-OBSERVATION-8"
        assert value["source_count"] == 2  # raw evidence is preserved
        assert value["perplexity_url_count"] == 1  # bad userinfo excluded
        assert value["serp_url_count"] == 1
        assert value["descriptive_overlap"]["status"] == "DESCRIPTIVE_ONLY"
        assert value["descriptive_overlap"]["common_urls"] == 0
        assert value["descriptive_overlap"]["serp_denominator"] == 1
        assert value["descriptive_overlap"]["perplexity_denominator"] == 1
        assert value["descriptive_overlap"]["jaccard_url_rate"] == 0
        assert value["target_observation"]["status"] == "DOMAIN_ALTERNATIVE_OBSERVED"
        assert value["target_observation"]["exact_sources"] == []
        assert value["target_observation"]["domain_alternatives"] == [
            "https://example.org/produto/",
        ]
