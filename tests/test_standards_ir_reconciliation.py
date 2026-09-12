from __future__ import annotations

import json
from pathlib import Path
import sqlite3
from types import SimpleNamespace

from rasai.standards_ir_reconciliation import reconcile_information_retrieval_metrics


def _schema(database: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(database)
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
        CREATE TABLE serp_observations (
            observation_id TEXT PRIMARY KEY,
            audit_id TEXT NOT NULL,
            domain_of_interest TEXT,
            quality_metadata TEXT NOT NULL,
            collected_at TEXT NOT NULL
        );
        CREATE TABLE serp_results (
            observation_id TEXT NOT NULL,
            position INTEGER NOT NULL,
            metadata TEXT NOT NULL
        );
        """
    )
    return connection


def _insert_query(
    connection: sqlite3.Connection,
    *,
    observation_id: str,
    grades: list[float | None],
    quality: dict[str, object] | None = None,
) -> None:
    connection.execute(
        "INSERT INTO serp_observations VALUES (?,?,?,?,?)",
        (observation_id, "AUD-IR", "example.com", json.dumps(quality or {}), "2026-09-11T12:00:00Z"),
    )
    for position, grade in enumerate(grades, start=1):
        metadata = {} if grade is None else {"relevance_grade": grade}
        connection.execute(
            "INSERT INTO serp_results VALUES (?,?,?)",
            (observation_id, position, json.dumps(metadata)),
        )


def _metrics(database: Path) -> dict[str, sqlite3.Row]:
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
            "SELECT * FROM standards_metric_observations WHERE audit_id='AUD-IR'"
        ).fetchall()
        return {str(row["metric_id"]): row for row in rows}
    finally:
        connection.close()


def test_partial_judgments_are_unknown_not_irrelevant(tmp_path: Path) -> None:
    database = tmp_path / "audit.db"
    connection = _schema(database)
    try:
        _insert_query(
            connection,
            observation_id="OBS-PARTIAL",
            grades=[3, 2, 1, 0, 0, 0, 0, 0, 0, None],
        )
        connection.commit()
    finally:
        connection.close()

    reconcile_information_retrieval_metrics(
        audit_id="AUD-IR",
        workspace=SimpleNamespace(database=database),
    )
    metrics = _metrics(database)
    assert metrics["relevance_judgment_coverage_at_10"]["value"] == 0.0
    assert metrics["precision_at_10"]["state"] == "NO_DATA"
    assert metrics["judged_mrr_at_10"]["state"] == "NO_DATA"
    assert metrics["ndcg_at_10"]["state"] == "NO_DATA"
    assert metrics["recall_at_10"]["state"] == "NO_DATA"


def test_fully_judged_query_publishes_only_supported_ir_metrics(tmp_path: Path) -> None:
    database = tmp_path / "audit.db"
    connection = _schema(database)
    try:
        _insert_query(
            connection,
            observation_id="OBS-FULL",
            grades=[3, 2, 1, 0, 0, 0, 0, 0, 0, 0],
            quality={
                "ideal_relevance_grades": [3, 2, 1, 0, 0, 0, 0, 0, 0, 0],
                "total_relevant_documents": 3,
            },
        )
        connection.commit()
    finally:
        connection.close()

    reconcile_information_retrieval_metrics(
        audit_id="AUD-IR",
        workspace=SimpleNamespace(database=database),
    )
    metrics = _metrics(database)
    assert metrics["relevance_judgment_coverage_at_10"]["value"] == 100.0
    assert metrics["precision_at_10"]["value"] == 0.3
    assert metrics["judged_mrr_at_10"]["value"] == 1.0
    assert metrics["ndcg_at_10"]["value"] == 1.0
    assert metrics["recall_at_10"]["value"] == 1.0
    details = json.loads(metrics["recall_at_10"]["details_json"])
    assert details["boundary"] == "No missing relevance judgment or denominator is inferred."


def test_ndcg_and_recall_stay_no_data_without_explicit_denominators(tmp_path: Path) -> None:
    database = tmp_path / "audit.db"
    connection = _schema(database)
    try:
        _insert_query(
            connection,
            observation_id="OBS-NO-QRELS",
            grades=[1, 0, 1, 0, 0, 0, 0, 0, 0, 0],
        )
        connection.commit()
    finally:
        connection.close()

    reconcile_information_retrieval_metrics(
        audit_id="AUD-IR",
        workspace=SimpleNamespace(database=database),
    )
    metrics = _metrics(database)
    assert metrics["precision_at_10"]["state"] == "MEASURED"
    assert metrics["judged_mrr_at_10"]["state"] == "MEASURED"
    assert metrics["ndcg_at_10"]["state"] == "NO_DATA"
    assert metrics["recall_at_10"]["state"] == "NO_DATA"
