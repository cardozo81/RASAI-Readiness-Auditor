"""#309: AUD/RPR/report replays consume persisted evidence only, without providers."""
from __future__ import annotations

from contextlib import closing
import json
from pathlib import Path
import sqlite3
from types import SimpleNamespace
from unittest.mock import patch

from rasai.geo_observation import materialize_geo_observation
from rasai.report_completion import materialize_catalog_report_projection


def _legacy_db(path: Path) -> None:
    with closing(sqlite3.connect(path)) as con, con:
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
            CREATE TABLE serp_results(observation_id TEXT, position INTEGER, url TEXT);
        """)
        con.executemany("INSERT INTO audits VALUES (?)", [("AUD-1",), ("AUD-2",)])
        con.executemany("INSERT INTO perplexity_search_runs VALUES (?,?,?,?,?,?)", [
            ("RUN-1", "AUD-1", '["seguro de vida"]', "web", "SUCCESS", "2026-10-09"),
            ("RUN-2", "AUD-2", '["outro mercado"]', "web", "SUCCESS", "2026-10-09"),
        ])
        con.executemany("INSERT INTO perplexity_search_sources VALUES (?,?,?,?,?,?,?)", [
            ("RUN-1", 1, "https://example.com/a", "Fonte A", "", None, None),
            ("RUN-2", 1, "https://private.example/x", "Privado", "", None, None),
        ])
        con.executemany("INSERT INTO serp_observations VALUES (?,?,?,?,?,?)", [
            ("SERP-1", "AUD-1", "seguro de vida", "2026-10-09", "OBSERVED", "OBSERVED_API"),
            ("SERP-2", "AUD-2", "outro mercado", "2026-10-09", "OBSERVED", "OBSERVED_API"),
        ])
        con.executemany("INSERT INTO serp_results VALUES (?,?,?)", [
            ("SERP-1", 1, "https://example.com/a"),
            ("SERP-2", 1, "https://private.example/x"),
        ])


def test_report_projection_replay_never_calls_provider_and_reuses_snapshot(tmp_path):
    db = tmp_path / "audit.db"
    _legacy_db(db)
    workspace = SimpleNamespace(root=tmp_path, database=db)
    # Mock only the HTML writer and its freshness check. GEO materialization is real.
    with patch("rasai.catalog_report_site.materialize_catalog_report_site") as writer, patch(
        "rasai.catalog_report_site.catalog_report_is_fresh", return_value=True
    ), patch(
        "rasai.search_intelligence.perplexity.execute_perplexity_search",
        side_effect=AssertionError("RPR/report must not call paid Search API"),
    ), patch(
        "rasai.geo_ai.execute_geo_ai",
        side_effect=AssertionError("RPR/report must not run AI"),
    ):
        for _ in range(3):  # initial report, RPR replay, catalog complement replay
            result = materialize_catalog_report_projection(audit_id="AUD-1", workspace=workspace)
            assert not result.renderer_errors
        assert writer.call_count == 3
    with closing(sqlite3.connect(db)) as con:
        con.row_factory = sqlite3.Row
        rows = con.execute("SELECT * FROM geo_observation_runs").fetchall()
        assert len(rows) == 1
        projection = json.loads(rows[0]["projection_json"])
        assert projection["audit_id"] == "AUD-1"
        assert projection["perplexity_run_id"] == "RUN-1"
        assert projection["serp_observation_id"] == "SERP-1"
        # Legacy date-only clocks do not prove a 24h comparable observation window.
        # Preserve sources/replay, but abstain from v4 overlap rates.
        assert projection["descriptive_overlap"]["common_urls"] is None
        assert projection["descriptive_overlap"]["reason"] == "TIME_SCOPE_UNPROVEN"
        assert "private.example" not in rows[0]["projection_json"]
        assert con.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert con.execute("PRAGMA foreign_key_check").fetchone() is None


def test_legacy_aud_without_external_request_abstains_without_schema_changes(tmp_path):
    path = tmp_path / "audit.db"
    with closing(sqlite3.connect(path)) as con, con:
        con.execute("CREATE TABLE audits(audit_id TEXT PRIMARY KEY)")
        con.execute("INSERT INTO audits VALUES ('AUD-LEGACY')")
    before = path.read_bytes()
    assert materialize_geo_observation(path, "AUD-LEGACY") is None
    assert path.read_bytes() == before
    with closing(sqlite3.connect(path)) as con:
        assert con.execute(
            "SELECT name FROM sqlite_master WHERE name='geo_observation_runs'"
        ).fetchone() is None


def test_replay_uses_audit_persisted_query_not_environment_or_new_defaults(tmp_path, monkeypatch):
    db = tmp_path / "audit.db"
    _legacy_db(db)
    first = materialize_geo_observation(db, "AUD-1")
    monkeypatch.setenv("RASAI_PERPLEXITY_ENABLED", "false")
    monkeypatch.setenv("RASAI_SERP_MAX_DEPTH", "2")
    again = materialize_geo_observation(db, "AUD-1")
    assert again == first
    with closing(sqlite3.connect(db)) as con:
        assert con.execute("SELECT count(*) FROM geo_observation_runs").fetchone()[0] == 1
        assert con.execute("PRAGMA foreign_key_check").fetchone() is None
