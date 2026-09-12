from __future__ import annotations

import json
import sqlite3
from types import SimpleNamespace

from rasai.standards_structured_data_reconciliation import reconcile_structured_data_metrics


def _workspace(tmp_path):
    database = tmp_path / "audit.db"
    connection = sqlite3.connect(database)
    try:
        connection.executescript(
            """
            CREATE TABLE standards_service_runs (
                audit_id TEXT NOT NULL,
                service_id TEXT NOT NULL,
                effective_enabled INTEGER NOT NULL,
                PRIMARY KEY (audit_id, service_id)
            );
            CREATE TABLE rule_executions (
                execution_id TEXT PRIMARY KEY,
                audit_id TEXT NOT NULL,
                rule_id TEXT NOT NULL,
                result TEXT NOT NULL
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
            "INSERT INTO standards_service_runs VALUES (?,?,?)",
            ("AUD-SD", "derived-readiness", 1),
        )
        connection.executemany(
            "INSERT INTO rule_executions VALUES (?,?,?,?)",
            (
                ("E1", "AUD-SD", "BR-GEO-035", "PASS"),
                ("E2", "AUD-SD", "BR-GEO-035", "FAIL"),
                ("E3", "AUD-SD", "BR-GEO-035", "WARNING"),
                ("E4", "AUD-SD", "BR-GEO-035", "NOT_APPLICABLE"),
                ("E5", "AUD-SD", "BR-GEO-034", "PASS"),
            ),
        )
        connection.commit()
    finally:
        connection.close()
    return SimpleNamespace(database=database)


def _metric(database):
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    try:
        row = connection.execute(
            "SELECT * FROM standards_metric_observations WHERE metric_id=?",
            ("structured_data_type_property_identifiability_rate",),
        ).fetchone()
        return None if row is None else dict(row)
    finally:
        connection.close()


def test_structured_data_identifiability_uses_only_determinate_rule_executions(tmp_path) -> None:
    workspace = _workspace(tmp_path)
    reconcile_structured_data_metrics(audit_id="AUD-SD", workspace=workspace)
    metric = _metric(workspace.database)

    assert metric is not None
    assert metric["value"] == 33.333
    assert metric["numerator"] == 1.0
    assert metric["denominator"] == 3.0
    assert metric["scope"] == "DEVICE_SNAPSHOT"
    assert metric["relation_degree"] == 5
    assert "BR-GEO-035" in metric["methodology"]
    details = json.loads(metric["details_json"])
    assert details["rule_id"] == "BR-GEO-035"
    assert "does not claim" in details["boundary"]


def test_structured_data_identifiability_respects_derived_readiness_disable(tmp_path) -> None:
    workspace = _workspace(tmp_path)
    connection = sqlite3.connect(workspace.database)
    try:
        connection.execute(
            "UPDATE standards_service_runs SET effective_enabled=0 WHERE audit_id=? AND service_id=?",
            ("AUD-SD", "derived-readiness"),
        )
        connection.commit()
    finally:
        connection.close()

    reconcile_structured_data_metrics(audit_id="AUD-SD", workspace=workspace)
    assert _metric(workspace.database) is None


def test_structured_data_identifiability_is_no_data_without_applicable_execution(tmp_path) -> None:
    workspace = _workspace(tmp_path)
    connection = sqlite3.connect(workspace.database)
    try:
        connection.execute("DELETE FROM rule_executions WHERE rule_id='BR-GEO-035'")
        connection.execute(
            "INSERT INTO rule_executions VALUES (?,?,?,?)",
            ("E6", "AUD-SD", "BR-GEO-035", "NOT_APPLICABLE"),
        )
        connection.commit()
    finally:
        connection.close()

    reconcile_structured_data_metrics(audit_id="AUD-SD", workspace=workspace)
    metric = _metric(workspace.database)
    assert metric is not None
    assert metric["state"] == "NO_DATA"
    assert metric["value"] is None
    assert metric["denominator"] == 0.0
