from __future__ import annotations

import json
import sqlite3
from types import SimpleNamespace

from rasai.standards_gsc_visibility_metrics import reconcile_gsc_visibility_counts


def _audit_database(path) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.executescript(
            """
            CREATE TABLE standards_metric_observations (
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
            );
            """
        )
        connection.commit()
    finally:
        connection.close()


def _observability_database(path) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.executescript(
            """
            CREATE TABLE datasets (
                dataset_id TEXT PRIMARY KEY,
                source_type TEXT NOT NULL,
                collected_at TEXT NOT NULL
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
                ("OLD-SA", "GOOGLE_SEARCH_CONSOLE_SEARCH_ANALYTICS", "2026-09-01T00:00:00+00:00"),
                ("NEW-SA", "GOOGLE_SEARCH_CONSOLE_SEARCH_ANALYTICS", "2026-09-11T00:00:00+00:00"),
            ),
        )
        connection.execute(
            "INSERT INTO search_performance VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                "OLD-1", "OLD-SA", "GOOGLE_SEARCH_CONSOLE_SEARCH_ANALYTICS", "2026-09-01",
                "old query", "https://example.test/old", "DESKTOP", "bra", "web",
                999, 999, 1.0, 1.0, "{}",
            ),
        )
        connection.executemany(
            "INSERT INTO search_performance VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                (
                    "N1", "NEW-SA", "GOOGLE_SEARCH_CONSOLE_SEARCH_ANALYTICS", "2026-09-11",
                    "query a", "https://example.test/a", "MOBILE", "bra", "web",
                    10, 100, 0.1, 2.0, "{}",
                ),
                (
                    "N2", "NEW-SA", "GOOGLE_SEARCH_CONSOLE_SEARCH_ANALYTICS", "2026-09-11",
                    "query a", "https://example.test/a", "DESKTOP", "bra", "web",
                    5, 50, 0.1, 3.0, "{}",
                ),
                (
                    "N3", "NEW-SA", "GOOGLE_SEARCH_CONSOLE_SEARCH_ANALYTICS", "2026-09-11",
                    "query a", "https://example.test/b", "DESKTOP", "bra", "web",
                    2, 20, 0.1, 4.0, "{}",
                ),
                (
                    "N4", "NEW-SA", "GOOGLE_SEARCH_CONSOLE_SEARCH_ANALYTICS", "2026-09-11",
                    "query b", "https://example.test/b", "DESKTOP", "bra", "web",
                    1, 10, 0.1, 5.0, "{}",
                ),
                (
                    "N5", "NEW-SA", "GOOGLE_SEARCH_CONSOLE_SEARCH_ANALYTICS", "2026-09-11",
                    "", "https://example.test/c", "DESKTOP", "bra", "web",
                    0, 1, 0.0, 8.0, "{}",
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


def test_visibility_counts_use_latest_dataset_and_deduplicate_dimensions(tmp_path) -> None:
    audit_db = tmp_path / "audit.db"
    _audit_database(audit_db)
    _observability_database(tmp_path / "observability.db")
    workspace = SimpleNamespace(root=tmp_path, database=audit_db)

    reconcile_gsc_visibility_counts(audit_id="AUD-GSC-VIS", workspace=workspace)
    metrics = _metrics(audit_db)

    assert metrics["gsc_returned_distinct_queries"]["value"] == 2.0
    assert metrics["gsc_returned_distinct_urls"]["value"] == 3.0
    assert metrics["gsc_returned_distinct_query_url_pairs"]["value"] == 3.0
    assert all(row["scope"] == "ORIGIN" for row in metrics.values())
    assert all(row["state"] == "MEASURED" for row in metrics.values())
    assert all(row["relation_degree"] == 5 for row in metrics.values())

    details = json.loads(metrics["gsc_returned_distinct_queries"]["details_json"])
    assert details["dataset_id"] == "NEW-SA"
    assert details["returned_rows"] == 5
    assert "not complete" in details["boundary"]


def test_visibility_counts_materialize_zero_for_valid_empty_latest_dataset(tmp_path) -> None:
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
    reconcile_gsc_visibility_counts(audit_id="AUD-GSC-VIS", workspace=workspace)
    metrics = _metrics(audit_db)

    assert metrics["gsc_returned_distinct_queries"]["value"] == 0.0
    assert metrics["gsc_returned_distinct_urls"]["value"] == 0.0
    assert metrics["gsc_returned_distinct_query_url_pairs"]["value"] == 0.0
    assert all(row["state"] == "MEASURED" for row in metrics.values())


def test_visibility_counts_are_idempotent(tmp_path) -> None:
    audit_db = tmp_path / "audit.db"
    _audit_database(audit_db)
    _observability_database(tmp_path / "observability.db")
    workspace = SimpleNamespace(root=tmp_path, database=audit_db)

    reconcile_gsc_visibility_counts(audit_id="AUD-GSC-VIS", workspace=workspace)
    reconcile_gsc_visibility_counts(audit_id="AUD-GSC-VIS", workspace=workspace)

    connection = sqlite3.connect(audit_db)
    try:
        count = connection.execute("SELECT COUNT(*) FROM standards_metric_observations").fetchone()[0]
    finally:
        connection.close()
    assert count == 3
