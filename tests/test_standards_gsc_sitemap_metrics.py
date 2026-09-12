from __future__ import annotations

import json
import sqlite3
from types import SimpleNamespace

from rasai.standards_gsc_sitemap_metrics import reconcile_gsc_sitemap_metrics


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
    old_metadata = {
        "sitemaps": [
            {
                "path": "https://example.test/old.xml",
                "is_pending": False,
                "warnings": 0,
                "errors": 0,
                "submitted": [{"type": "web", "submitted": 999}],
            }
        ]
    }
    new_metadata = {
        "site_url": "sc-domain:example.test",
        "sitemaps": [
            {
                "path": "https://example.test/a.xml",
                "is_pending": False,
                "warnings": 0,
                "errors": 0,
                "submitted": [{"type": "web", "submitted": "100"}],
            },
            {
                "path": "https://example.test/b.xml",
                "is_pending": True,
                "warnings": "1",
                "errors": "2",
                "submitted": [{"type": "web", "submitted": 50}],
            },
        ],
        "indexed_field_policy": "DEPRECATED_FIELD_NOT_USED",
    }
    connection = sqlite3.connect(path)
    try:
        connection.execute(
            """CREATE TABLE datasets (
                dataset_id TEXT PRIMARY KEY,
                source_type TEXT NOT NULL,
                metadata TEXT NOT NULL,
                collected_at TEXT NOT NULL
            )"""
        )
        connection.executemany(
            "INSERT INTO datasets VALUES (?,?,?,?)",
            (
                (
                    "OLD-SITEMAPS",
                    "GOOGLE_SEARCH_CONSOLE_SITEMAPS",
                    json.dumps(old_metadata),
                    "2026-09-01T00:00:00+00:00",
                ),
                (
                    "NEW-SITEMAPS",
                    "GOOGLE_SEARCH_CONSOLE_SITEMAPS",
                    json.dumps(new_metadata),
                    "2026-09-11T00:00:00+00:00",
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


def test_sitemap_metrics_use_latest_persisted_dataset(tmp_path) -> None:
    audit_db = tmp_path / "audit.db"
    _audit_database(audit_db)
    _observability_database(tmp_path / "observability.db")
    workspace = SimpleNamespace(root=tmp_path, database=audit_db)

    reconcile_gsc_sitemap_metrics(audit_id="AUD-GSC-SITEMAP", workspace=workspace)
    metrics = _metrics(audit_db)

    assert metrics["gsc_sitemap_count"]["value"] == 2.0
    assert metrics["gsc_sitemap_error_free_rate"]["value"] == 50.0
    assert metrics["gsc_sitemap_warning_free_rate"]["value"] == 50.0
    assert metrics["gsc_sitemap_pending_rate"]["value"] == 50.0
    assert metrics["gsc_sitemap_reported_submitted_urls"]["value"] == 150.0
    assert all(row["scope"] == "ORIGIN" for row in metrics.values())
    assert all(row["relation_degree"] == 5 for row in metrics.values())

    details = json.loads(metrics["gsc_sitemap_reported_submitted_urls"]["details_json"])
    assert details["dataset_id"] == "NEW-SITEMAPS"
    assert "not an indexed-URL count" in details["boundary"]


def test_sitemap_metrics_are_idempotent(tmp_path) -> None:
    audit_db = tmp_path / "audit.db"
    _audit_database(audit_db)
    _observability_database(tmp_path / "observability.db")
    workspace = SimpleNamespace(root=tmp_path, database=audit_db)

    reconcile_gsc_sitemap_metrics(audit_id="AUD-GSC-SITEMAP", workspace=workspace)
    reconcile_gsc_sitemap_metrics(audit_id="AUD-GSC-SITEMAP", workspace=workspace)

    connection = sqlite3.connect(audit_db)
    try:
        count = connection.execute("SELECT COUNT(*) FROM standards_metric_observations").fetchone()[0]
    finally:
        connection.close()
    assert count == 5


def test_empty_sitemap_dataset_keeps_count_and_submitted_zero_without_fake_rates(tmp_path) -> None:
    audit_db = tmp_path / "audit.db"
    _audit_database(audit_db)
    obs_db = tmp_path / "observability.db"
    connection = sqlite3.connect(obs_db)
    try:
        connection.execute(
            """CREATE TABLE datasets (
                dataset_id TEXT PRIMARY KEY,
                source_type TEXT NOT NULL,
                metadata TEXT NOT NULL,
                collected_at TEXT NOT NULL
            )"""
        )
        connection.execute(
            "INSERT INTO datasets VALUES (?,?,?,?)",
            (
                "EMPTY-SITEMAPS",
                "GOOGLE_SEARCH_CONSOLE_SITEMAPS",
                json.dumps({"sitemaps": []}),
                "2026-09-11T00:00:00+00:00",
            ),
        )
        connection.commit()
    finally:
        connection.close()

    workspace = SimpleNamespace(root=tmp_path, database=audit_db)
    reconcile_gsc_sitemap_metrics(audit_id="AUD-GSC-SITEMAP", workspace=workspace)
    metrics = _metrics(audit_db)

    assert metrics["gsc_sitemap_count"]["value"] == 0.0
    assert metrics["gsc_sitemap_reported_submitted_urls"]["value"] == 0.0
    assert metrics["gsc_sitemap_error_free_rate"]["state"] == "NO_DATA"
    assert metrics["gsc_sitemap_warning_free_rate"]["state"] == "NO_DATA"
    assert metrics["gsc_sitemap_pending_rate"]["state"] == "NO_DATA"
