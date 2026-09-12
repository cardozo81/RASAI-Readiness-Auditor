from __future__ import annotations

import json
import sqlite3
from types import SimpleNamespace

from rasai.standards_gsc_metrics import reconcile_gsc_observational_metrics


def _audit_database(path):
    connection = sqlite3.connect(path)
    try:
        connection.execute(
            """CREATE TABLE standards_metric_observations (
                observation_id TEXT PRIMARY KEY,
                audit_id TEXT NOT NULL,
                metric_id TEXT NOT NULL,
                label TEXT NOT NULL,
                scope TEXT NOT NULL,
                target TEXT,
                device TEXT,
                state TEXT NOT NULL,
                value REAL,
                numerator REAL,
                denominator REAL,
                unit TEXT,
                source TEXT NOT NULL,
                methodology TEXT NOT NULL,
                relation_degree INTEGER NOT NULL,
                details_json TEXT NOT NULL,
                observed_at TEXT NOT NULL
            )"""
        )
        connection.commit()
    finally:
        connection.close()


def _observability_database(path):
    connection = sqlite3.connect(path)
    try:
        connection.executescript(
            """
            CREATE TABLE datasets (
                dataset_id TEXT PRIMARY KEY,
                source_type TEXT NOT NULL,
                collected_at TEXT NOT NULL
            );
            CREATE TABLE index_observations (
                record_id TEXT NOT NULL,
                dataset_id TEXT NOT NULL,
                source TEXT NOT NULL,
                url TEXT NOT NULL,
                verdict TEXT,
                coverage_state TEXT,
                indexing_state TEXT,
                robots_txt_state TEXT,
                page_fetch_state TEXT,
                user_canonical TEXT,
                selected_canonical TEXT,
                last_crawl_time TEXT,
                crawled_as TEXT,
                referring_urls TEXT NOT NULL,
                sitemap_urls TEXT NOT NULL,
                metadata TEXT NOT NULL
            );
            CREATE TABLE search_performance (
                record_id TEXT NOT NULL,
                dataset_id TEXT NOT NULL,
                source TEXT NOT NULL,
                observed_date TEXT,
                query_text TEXT,
                url TEXT,
                device TEXT,
                country TEXT,
                surface TEXT,
                clicks REAL,
                impressions REAL,
                ctr REAL,
                position REAL,
                metadata TEXT NOT NULL
            );
            """
        )
        connection.executemany(
            "INSERT INTO datasets VALUES (?,?,?)",
            (
                ("OLD-UI", "GOOGLE_SEARCH_CONSOLE_URL_INSPECTION", "2026-09-01T00:00:00+00:00"),
                ("NEW-UI", "GOOGLE_SEARCH_CONSOLE_URL_INSPECTION", "2026-09-11T00:00:00+00:00"),
                ("OLD-SA", "GOOGLE_SEARCH_CONSOLE_SEARCH_ANALYTICS", "2026-09-01T00:00:00+00:00"),
                ("NEW-SA", "GOOGLE_SEARCH_CONSOLE_SEARCH_ANALYTICS", "2026-09-11T00:00:00+00:00"),
            ),
        )
        connection.execute(
            "INSERT INTO index_observations VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                "OLD1", "OLD-UI", "GOOGLE_SEARCH_CONSOLE_URL_INSPECTION", "https://example.test/old",
                "PASS", "Indexed", "INDEXING_ALLOWED", "ALLOWED", "SUCCESSFUL",
                "https://example.test/old", "https://example.test/old", None, None,
                "[]", "[\"https://example.test/sitemap.xml\"]", "{}",
            ),
        )
        connection.executemany(
            "INSERT INTO index_observations VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                (
                    "N1", "NEW-UI", "GOOGLE_SEARCH_CONSOLE_URL_INSPECTION", "https://example.test/a",
                    "PASS", "Indexed", "INDEXING_ALLOWED", "ALLOWED", "SUCCESSFUL",
                    "https://example.test/a", "https://example.test/a", None, None,
                    "[]", "[\"https://example.test/sitemap.xml\"]", "{}",
                ),
                (
                    "N2", "NEW-UI", "GOOGLE_SEARCH_CONSOLE_URL_INSPECTION", "https://example.test/b",
                    "FAIL", "Excluded", "INDEXING_NOT_ALLOWED", "DISALLOWED", "SOFT_404",
                    "https://example.test/b", "https://example.test/c", None, None,
                    "[]", "[]", "{}",
                ),
                (
                    "N3", "NEW-UI", "GOOGLE_SEARCH_CONSOLE_URL_INSPECTION", "https://example.test/c",
                    "ERROR", None, None, None, None, None, None, None, None,
                    "[]", "[]", "{\"error\":\"fixture\"}",
                ),
            ),
        )
        connection.execute(
            "INSERT INTO search_performance VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                "OLD1", "OLD-SA", "GOOGLE_SEARCH_CONSOLE_SEARCH_ANALYTICS", "2026-09-01", "old",
                "https://example.test/old", "DESKTOP", "bra", "web", 1000, 1000, 1.0, 1.0, "{}",
            ),
        )
        connection.executemany(
            "INSERT INTO search_performance VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                (
                    "S1", "NEW-SA", "GOOGLE_SEARCH_CONSOLE_SEARCH_ANALYTICS", "2026-09-11", "query a",
                    "https://example.test/a", "MOBILE", "bra", "web", 10, 100, 0.10, 2.0, "{}",
                ),
                (
                    "S2", "NEW-SA", "GOOGLE_SEARCH_CONSOLE_SEARCH_ANALYTICS", "2026-09-11", "query b",
                    "https://example.test/b", "DESKTOP", "bra", "web", 5, 50, 0.10, 4.0, "{}",
                ),
            ),
        )
        connection.commit()
    finally:
        connection.close()


def _metrics(path):
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    try:
        return {
            str(row["metric_id"]): dict(row)
            for row in connection.execute("SELECT * FROM standards_metric_observations")
        }
    finally:
        connection.close()


def test_gsc_metrics_use_only_latest_persisted_datasets(tmp_path) -> None:
    audit_db = tmp_path / "audit.db"
    obs_db = tmp_path / "observability.db"
    _audit_database(audit_db)
    _observability_database(obs_db)
    workspace = SimpleNamespace(root=tmp_path, database=audit_db)

    reconcile_gsc_observational_metrics(audit_id="AUD-GSC-METRICS", workspace=workspace)
    metrics = _metrics(audit_db)

    assert metrics["gsc_url_inspection_verdict_pass_rate"]["value"] == 50.0
    assert metrics["gsc_url_inspection_verdict_pass_rate"]["denominator"] == 2.0
    assert metrics["gsc_indexing_allowed_rate"]["value"] == 50.0
    assert metrics["gsc_robots_allowed_rate"]["value"] == 50.0
    assert metrics["gsc_page_fetch_success_rate"]["value"] == 50.0
    assert metrics["gsc_exact_canonical_agreement_rate"]["value"] == 50.0
    assert metrics["gsc_sitemap_association_rate"]["value"] == 50.0

    assert metrics["gsc_returned_search_rows"]["value"] == 2.0
    assert metrics["gsc_returned_row_clicks"]["value"] == 15.0
    assert metrics["gsc_returned_row_impressions"]["value"] == 150.0
    assert metrics["gsc_returned_row_ctr"]["value"] == 10.0
    assert metrics["gsc_returned_row_impression_weighted_position"]["value"] == 2.667
    assert metrics["gsc_returned_row_impressions"]["scope"] == "ORIGIN"
    assert metrics["gsc_url_inspection_verdict_pass_rate"]["scope"] == "URL_SET"
    assert all(row["relation_degree"] == 5 for row in metrics.values())

    inspection_details = json.loads(metrics["gsc_url_inspection_verdict_pass_rate"]["details_json"])
    assert inspection_details["dataset_id"] == "NEW-UI"
    search_details = json.loads(metrics["gsc_returned_row_impressions"]["details_json"])
    assert search_details["dataset_id"] == "NEW-SA"
    assert "top rows" in search_details["boundary"]


def test_gsc_metrics_are_idempotent_for_same_latest_datasets(tmp_path) -> None:
    audit_db = tmp_path / "audit.db"
    _audit_database(audit_db)
    _observability_database(tmp_path / "observability.db")
    workspace = SimpleNamespace(root=tmp_path, database=audit_db)

    reconcile_gsc_observational_metrics(audit_id="AUD-GSC-METRICS", workspace=workspace)
    reconcile_gsc_observational_metrics(audit_id="AUD-GSC-METRICS", workspace=workspace)

    connection = sqlite3.connect(audit_db)
    try:
        count = connection.execute("SELECT COUNT(*) FROM standards_metric_observations").fetchone()[0]
    finally:
        connection.close()
    assert count == 11


def test_gsc_metrics_do_nothing_without_observability_sidecar(tmp_path) -> None:
    audit_db = tmp_path / "audit.db"
    _audit_database(audit_db)
    workspace = SimpleNamespace(root=tmp_path, database=audit_db)

    reconcile_gsc_observational_metrics(audit_id="AUD-GSC-METRICS", workspace=workspace)
    assert _metrics(audit_db) == {}


def test_empty_search_analytics_dataset_is_measured_as_zero_rows_not_missing_dataset(tmp_path) -> None:
    audit_db = tmp_path / "audit.db"
    obs_db = tmp_path / "observability.db"
    _audit_database(audit_db)
    _observability_database(obs_db)

    connection = sqlite3.connect(obs_db)
    try:
        connection.execute("DELETE FROM search_performance WHERE dataset_id='NEW-SA'")
        connection.commit()
    finally:
        connection.close()

    workspace = SimpleNamespace(root=tmp_path, database=audit_db)
    reconcile_gsc_observational_metrics(audit_id="AUD-GSC-METRICS", workspace=workspace)
    metrics = _metrics(audit_db)

    assert metrics["gsc_returned_search_rows"]["state"] == "MEASURED"
    assert metrics["gsc_returned_search_rows"]["value"] == 0.0
    assert metrics["gsc_returned_row_clicks"]["state"] == "MEASURED"
    assert metrics["gsc_returned_row_clicks"]["value"] == 0.0
    assert metrics["gsc_returned_row_impressions"]["state"] == "MEASURED"
    assert metrics["gsc_returned_row_impressions"]["value"] == 0.0
    assert metrics["gsc_returned_row_ctr"]["state"] == "NO_DATA"
    assert metrics["gsc_returned_row_ctr"]["value"] is None
    assert metrics["gsc_returned_row_impression_weighted_position"]["state"] == "NO_DATA"
    assert metrics["gsc_returned_row_impression_weighted_position"]["value"] is None
