from __future__ import annotations

import json
import sqlite3
from types import SimpleNamespace

from rasai.standards_operational_reconciliation import reconcile_operational_http_metrics


def _workspace(tmp_path):
    database = tmp_path / "audit.db"
    connection = sqlite3.connect(database)
    try:
        connection.executescript(
            """
            CREATE TABLE pages (
                page_id TEXT PRIMARY KEY,
                audit_id TEXT NOT NULL,
                normalized_url TEXT NOT NULL
            );
            CREATE TABLE page_snapshots (
                snapshot_id TEXT PRIMARY KEY,
                page_id TEXT NOT NULL,
                device TEXT NOT NULL,
                browser_metadata TEXT NOT NULL
            );
            CREATE TABLE standards_service_runs (
                audit_id TEXT NOT NULL,
                service_id TEXT NOT NULL,
                requested INTEGER NOT NULL DEFAULT 1,
                configured INTEGER NOT NULL DEFAULT 1,
                effective_enabled INTEGER NOT NULL,
                state TEXT NOT NULL DEFAULT 'SUCCESS',
                targets_attempted INTEGER NOT NULL DEFAULT 0,
                targets_succeeded INTEGER NOT NULL DEFAULT 0,
                details_json TEXT NOT NULL DEFAULT '{}',
                updated_at TEXT NOT NULL DEFAULT '',
                PRIMARY KEY (audit_id, service_id)
            );
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
        connection.execute(
            "INSERT INTO standards_service_runs (audit_id,service_id,effective_enabled) VALUES (?,?,?)",
            ("AUD-OPS", "derived-readiness", 1),
        )
        connection.executemany(
            "INSERT INTO pages VALUES (?,?,?)",
            (
                ("P1", "AUD-OPS", "https://example.test/a"),
                ("P2", "AUD-OPS", "https://example.test/b"),
            ),
        )
        redirected = json.dumps(
            {
                "raw_http": {
                    "requested_url": "https://example.test/a",
                    "final_url": "https://www.example.test/a",
                    "status": 200,
                    "redirect_count": 1,
                    "network_error": None,
                }
            }
        )
        timed_out = json.dumps(
            {
                "raw_http": {
                    "requested_url": "https://example.test/b",
                    "final_url": "",
                    "status": None,
                    "redirect_count": 0,
                    "network_error": "TIMEOUT",
                }
            }
        )
        connection.executemany(
            "INSERT INTO page_snapshots VALUES (?,?,?,?)",
            (
                ("S1M", "P1", "MOBILE", redirected),
                ("S1D", "P1", "DESKTOP", redirected),
                ("S2M", "P2", "MOBILE", timed_out),
            ),
        )
        connection.commit()
    finally:
        connection.close()
    return SimpleNamespace(database=database)


def _metrics(database):
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    try:
        return {
            row["metric_id"]: dict(row)
            for row in connection.execute(
                "SELECT metric_id,value,numerator,denominator,scope,details_json FROM standards_metric_observations"
            ).fetchall()
        }
    finally:
        connection.close()


def test_operational_metrics_deduplicate_device_snapshots(tmp_path) -> None:
    workspace = _workspace(tmp_path)
    reconcile_operational_http_metrics(audit_id="AUD-OPS", workspace=workspace)
    metrics = _metrics(workspace.database)

    assert metrics["http_physical_observation_coverage"]["value"] == 100.0
    assert metrics["http_2xx_success_rate"]["value"] == 50.0
    assert metrics["transport_error_rate"]["value"] == 50.0
    assert metrics["transport_timeout_rate"]["value"] == 50.0
    assert metrics["redirect_rate"]["value"] == 50.0
    assert metrics["redirect_completion_rate"]["value"] == 100.0
    assert metrics["cross_host_redirect_rate"]["value"] == 100.0
    assert metrics["http_2xx_success_rate"]["denominator"] == 2.0
    assert metrics["http_2xx_success_rate"]["scope"] == "URL_SET"
    details = json.loads(metrics["http_2xx_success_rate"]["details_json"])
    assert details["physical_observations"] == 2
    assert details["deduplicated_by"] == "page_id"


def test_operational_metrics_respect_derived_readiness_disable(tmp_path) -> None:
    workspace = _workspace(tmp_path)
    connection = sqlite3.connect(workspace.database)
    try:
        connection.execute(
            "UPDATE standards_service_runs SET effective_enabled=0 WHERE audit_id=? AND service_id=?",
            ("AUD-OPS", "derived-readiness"),
        )
        connection.commit()
    finally:
        connection.close()

    reconcile_operational_http_metrics(audit_id="AUD-OPS", workspace=workspace)
    assert _metrics(workspace.database) == {}
