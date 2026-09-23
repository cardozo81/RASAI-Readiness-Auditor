from __future__ import annotations

import sqlite3

from rasai import catalog_projection_consistency as projection
from rasai import catalog_report_metrics as metrics
from rasai import catalog_state_trust as state_trust
from rasai import execution_consistency_runtime as consistency


def test_browser_metric_wrapper_accepts_and_reuses_shared_connection(monkeypatch, tmp_path):
    database = tmp_path / "audit.db"
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    received: dict[str, object] = {}

    def base(database_arg, audit_id, *, connection=None):
        received["base_database"] = database_arg
        received["base_audit_id"] = audit_id
        received["base_connection"] = connection
        return [("Base", "1", "Persistida")]

    def browser(database_arg, audit_id, *, connection=None):
        received["browser_database"] = database_arg
        received["browser_audit_id"] = audit_id
        received["browser_connection"] = connection
        return [("Navegador · FCP same-session", "100 ms", "Medição da sessão capturada")]

    monkeypatch.setattr(consistency, "_consistent_web_metric_rows", base)
    monkeypatch.setattr(metrics, "_web_metric_rows", base)
    monkeypatch.setattr(state_trust, "_browser_performance_count", lambda database_arg, audit_id: 0)
    monkeypatch.setattr(projection, "_browser_snapshot_metrics", browser)

    projection._install_browser_metrics()

    rows = metrics._web_metric_rows(database, "AUD-TEST", connection=connection)

    assert received["base_connection"] is connection
    assert received["browser_connection"] is connection
    assert rows == [
        ("Base", "1", "Persistida"),
        ("Navegador · FCP same-session", "100 ms", "Medição da sessão capturada"),
    ]
    assert connection.execute("SELECT 1").fetchone()[0] == 1
    connection.close()


def test_consistent_web_metric_rows_keeps_supplied_connection_open(monkeypatch, tmp_path):
    database = tmp_path / "audit.db"
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    received: dict[str, object] = {}

    def base(database_arg, audit_id, *, connection=None):
        received["connection"] = connection
        return []

    monkeypatch.setattr(consistency._consistent_web_metric_rows, "_base", base, raising=False)

    rows = consistency._consistent_web_metric_rows(
        database,
        "AUD-TEST",
        connection=connection,
    )

    assert rows == []
    assert received["connection"] is connection
    assert connection.execute("SELECT 1").fetchone()[0] == 1
    connection.close()


def test_observability_sidecar_keeps_timestamp_and_human_source_name(monkeypatch, tmp_path):
    from rasai import catalog_report_integrations as integrations

    connection = sqlite3.connect(":memory:")
    datasets = [
        {
            "dataset_id": "OBS-GSC-1",
            "source_type": "GOOGLE_SEARCH_CONSOLE_SEARCH_ANALYTICS",
            "collected_at": "2026-09-21T14:05:00+00:00",
            "capture_method": "DIRECT_OFFICIAL_API",
            "period_start": "2026-09-01",
            "period_end": "2026-09-21",
            "artifact_path": "artifacts/gsc.json",
            "metadata": "{}",
        }
    ]

    monkeypatch.setattr(integrations, "_external_integrations", lambda database, audit_id: [])
    monkeypatch.setattr(projection, "_observability", lambda database: (datasets, connection))
    monkeypatch.setattr(projection, "_dataset_count", lambda *args, **kwargs: 12)

    projection._install_external_integrations()
    rows = integrations._external_integrations(tmp_path / "audit.db", "AUD")

    assert len(rows) == 1
    assert rows[0]["name"] == "Google Search Console - Análise de pesquisa"
    assert rows[0]["occurred_at"] == "2026-09-21T14:05:00+00:00"
    assert rows[0]["raw"]["details_json"]
