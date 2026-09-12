from __future__ import annotations

import sqlite3
from types import SimpleNamespace

from rasai.standards_gsc_observability_runtime import _clear_metrics_without_current_success


def _database(path) -> None:
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
        rows = (
            ("1", "AUD-1", "gsc_url_inspection_verdict_pass_rate"),
            ("2", "AUD-1", "gsc_last_crawl_age_p50_days"),
            ("3", "AUD-1", "gsc_sitemap_count"),
            ("4", "AUD-1", "gsc_returned_row_impressions"),
            ("5", "AUD-1", "gsc_returned_distinct_queries"),
            ("6", "AUD-1", "crawlability_coverage"),
            ("7", "AUD-OTHER", "gsc_url_inspection_verdict_pass_rate"),
        )
        connection.executemany(
            """INSERT INTO standards_metric_observations(
                observation_id,audit_id,metric_id,label,scope,state,value,unit,source,methodology,
                relation_degree,details_json,observed_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            [
                (observation_id, audit_id, metric_id, metric_id, "URL_SET", "MEASURED", 1.0, "percent", "fixture", "fixture", 5, "{}", "2026-09-11T00:00:00+00:00")
                for observation_id, audit_id, metric_id in rows
            ],
        )
        connection.commit()
    finally:
        connection.close()


def _metric_ids(path, audit_id: str) -> set[str]:
    connection = sqlite3.connect(path)
    try:
        return {
            str(row[0])
            for row in connection.execute(
                "SELECT metric_id FROM standards_metric_observations WHERE audit_id=?",
                (audit_id,),
            )
        }
    finally:
        connection.close()


def test_only_currently_successful_gsc_operation_families_remain_projected(tmp_path) -> None:
    database = tmp_path / "audit.db"
    _database(database)
    workspace = SimpleNamespace(database=database)

    _clear_metrics_without_current_success(
        audit_id="AUD-1",
        workspace=workspace,
        result={
            "operations": [
                {"name": "SITEMAPS", "status": "SUCCESS", "dataset_id": "OBS-SITEMAPS"},
                {"name": "URL_INSPECTION", "status": "ERROR"},
            ]
        },
    )

    remaining = _metric_ids(database, "AUD-1")
    assert "gsc_sitemap_count" in remaining
    assert "gsc_url_inspection_verdict_pass_rate" not in remaining
    assert "gsc_last_crawl_age_p50_days" not in remaining
    assert "gsc_returned_row_impressions" not in remaining
    assert "gsc_returned_distinct_queries" not in remaining
    assert "crawlability_coverage" in remaining
    assert "gsc_url_inspection_verdict_pass_rate" in _metric_ids(database, "AUD-OTHER")


def test_disabled_or_unconfigured_current_run_clears_all_gsc_projections_only(tmp_path) -> None:
    database = tmp_path / "audit.db"
    _database(database)
    workspace = SimpleNamespace(database=database)

    _clear_metrics_without_current_success(
        audit_id="AUD-1",
        workspace=workspace,
        result={"effective_enabled": False, "operations": []},
    )

    remaining = _metric_ids(database, "AUD-1")
    assert remaining == {"crawlability_coverage"}


def test_success_requires_dataset_id_before_projection_is_considered_current(tmp_path) -> None:
    database = tmp_path / "audit.db"
    _database(database)
    workspace = SimpleNamespace(database=database)

    _clear_metrics_without_current_success(
        audit_id="AUD-1",
        workspace=workspace,
        result={
            "operations": [
                {"name": "URL_INSPECTION", "status": "SUCCESS", "dataset_id": ""},
                {"name": "SITEMAPS", "status": "SUCCESS", "dataset_id": "OBS-SITEMAPS"},
                {"name": "SEARCH_ANALYTICS", "status": "SUCCESS", "dataset_id": "OBS-SA"},
            ]
        },
    )

    remaining = _metric_ids(database, "AUD-1")
    assert "gsc_url_inspection_verdict_pass_rate" not in remaining
    assert "gsc_last_crawl_age_p50_days" not in remaining
    assert "gsc_sitemap_count" in remaining
    assert "gsc_returned_row_impressions" in remaining
    assert "gsc_returned_distinct_queries" in remaining
