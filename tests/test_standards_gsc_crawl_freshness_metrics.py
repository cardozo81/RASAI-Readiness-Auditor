from __future__ import annotations

import json
import sqlite3
from types import SimpleNamespace

from rasai.standards_gsc_crawl_freshness_metrics import reconcile_gsc_crawl_freshness_metrics


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
            """
        )
        connection.executemany(
            "INSERT INTO datasets VALUES (?,?,?)",
            (
                ("OLD-UI", "GOOGLE_SEARCH_CONSOLE_URL_INSPECTION", "2026-09-01T00:00:00+00:00"),
                ("NEW-UI", "GOOGLE_SEARCH_CONSOLE_URL_INSPECTION", "2026-09-11T00:00:00+00:00"),
            ),
        )
        rows = (
            (
                "OLD1", "OLD-UI", "GOOGLE_SEARCH_CONSOLE_URL_INSPECTION", "https://example.test/old",
                "PASS", None, None, None, None, None, None, "2020-01-01T00:00:00Z", None,
                "[]", "[]", "{}",
            ),
            (
                "N1", "NEW-UI", "GOOGLE_SEARCH_CONSOLE_URL_INSPECTION", "https://example.test/a",
                "PASS", None, None, None, None, None, None, "2026-09-10T00:00:00Z", None,
                "[]", "[]", "{}",
            ),
            (
                "N2", "NEW-UI", "GOOGLE_SEARCH_CONSOLE_URL_INSPECTION", "https://example.test/b",
                "PASS", None, None, None, None, None, None, "2026-09-07T00:00:00Z", None,
                "[]", "[]", "{}",
            ),
            (
                "N3", "NEW-UI", "GOOGLE_SEARCH_CONSOLE_URL_INSPECTION", "https://example.test/c",
                "PASS", None, None, None, None, None, None, None, None,
                "[]", "[]", "{}",
            ),
            (
                "N4", "NEW-UI", "GOOGLE_SEARCH_CONSOLE_URL_INSPECTION", "https://example.test/d",
                "ERROR", None, None, None, None, None, None, "2026-01-01T00:00:00Z", None,
                "[]", "[]", "{}",
            ),
        )
        connection.executemany("INSERT INTO index_observations VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
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


def test_crawl_freshness_uses_latest_dataset_and_persisted_collection_time(tmp_path) -> None:
    audit_db = tmp_path / "audit.db"
    _audit_database(audit_db)
    _observability_database(tmp_path / "observability.db")
    workspace = SimpleNamespace(root=tmp_path, database=audit_db)

    reconcile_gsc_crawl_freshness_metrics(audit_id="AUD-GSC-CRAWL", workspace=workspace)
    metrics = _metrics(audit_db)

    assert metrics["gsc_last_crawl_time_coverage"]["value"] == 66.667
    assert metrics["gsc_last_crawl_time_coverage"]["numerator"] == 2.0
    assert metrics["gsc_last_crawl_time_coverage"]["denominator"] == 3.0
    assert metrics["gsc_last_crawl_age_p50_days"]["value"] == 2.5
    assert metrics["gsc_last_crawl_age_p75_days"]["value"] == 3.25
    assert metrics["gsc_last_crawl_age_p95_days"]["value"] == 3.85
    assert all(row["scope"] == "URL_SET" for row in metrics.values())
    assert all(row["relation_degree"] == 5 for row in metrics.values())

    details = json.loads(metrics["gsc_last_crawl_age_p50_days"]["details_json"])
    assert details["dataset_id"] == "NEW-UI"
    assert details["dataset_collected_at"] == "2026-09-11T00:00:00+00:00"
    assert details["age_samples"] == 2


def test_crawl_freshness_keeps_percentiles_no_data_without_valid_last_crawl_times(tmp_path) -> None:
    audit_db = tmp_path / "audit.db"
    _audit_database(audit_db)
    obs_db = tmp_path / "observability.db"
    connection = sqlite3.connect(obs_db)
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
            """
        )
        connection.execute(
            "INSERT INTO datasets VALUES (?,?,?)",
            ("UI", "GOOGLE_SEARCH_CONSOLE_URL_INSPECTION", "2026-09-11T00:00:00+00:00"),
        )
        connection.execute(
            "INSERT INTO index_observations VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                "N1", "UI", "GOOGLE_SEARCH_CONSOLE_URL_INSPECTION", "https://example.test/a",
                "PASS", None, None, None, None, None, None, None, None, "[]", "[]", "{}",
            ),
        )
        connection.commit()
    finally:
        connection.close()

    workspace = SimpleNamespace(root=tmp_path, database=audit_db)
    reconcile_gsc_crawl_freshness_metrics(audit_id="AUD-GSC-CRAWL", workspace=workspace)
    metrics = _metrics(audit_db)

    assert metrics["gsc_last_crawl_time_coverage"]["state"] == "MEASURED"
    assert metrics["gsc_last_crawl_time_coverage"]["value"] == 0.0
    assert metrics["gsc_last_crawl_age_p50_days"]["state"] == "NO_DATA"
    assert metrics["gsc_last_crawl_age_p75_days"]["state"] == "NO_DATA"
    assert metrics["gsc_last_crawl_age_p95_days"]["state"] == "NO_DATA"
