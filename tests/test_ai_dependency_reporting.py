from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
import sqlite3
import tempfile

from rasai.ai_dependency_reporting import dependency_html


def _database(root: Path) -> Path:
    database = root / "audit.db"
    connection = sqlite3.connect(database)
    try:
        connection.executescript(
            """
            CREATE TABLE audits(audit_id TEXT PRIMARY KEY);
            INSERT INTO audits VALUES ('AUD-1');
            CREATE TABLE ai_dependency_snapshots(
                dependency_snapshot_id TEXT PRIMARY KEY,
                audit_id TEXT NOT NULL,
                purpose TEXT NOT NULL,
                scope_key TEXT NOT NULL,
                expected_json TEXT NOT NULL,
                present_json TEXT NOT NULL,
                missing_json TEXT NOT NULL,
                evidence_ids_json TEXT NOT NULL,
                context_fingerprint TEXT NOT NULL,
                ready INTEGER NOT NULL,
                contract_version TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            """
        )
        connection.commit()
    finally:
        connection.close()
    return database


def test_blocked_dependency_snapshot_is_visible_before_provider_execution() -> None:
    with tempfile.TemporaryDirectory() as directory:
        database = _database(Path(directory))
        connection = sqlite3.connect(database)
        try:
            connection.execute(
                "INSERT INTO ai_dependency_snapshots VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    "AID-1", "AUD-1", "DEEP_ANALYSIS", "AUDIT",
                    json.dumps(["SEARCH_INTELLIGENCE", "IMPROVEMENT_EVIDENCE_CONTEXT"]),
                    json.dumps({"SEARCH_INTELLIGENCE": "FAILED_RETRYABLE", "IMPROVEMENT_EVIDENCE_CONTEXT": True}),
                    json.dumps(["SEARCH_INTELLIGENCE"]),
                    json.dumps(["EV-1"]),
                    "abc123", 0, "AI-DEPENDENCY-001", "2026-09-17T12:00:00Z",
                ),
            )
            connection.commit()
        finally:
            connection.close()

        html = dependency_html(database, SimpleNamespace(audit_id="AUD-1"))
        assert "Dependências antes da IA" in html
        assert "Bloqueado" in html
        assert "SEARCH_INTELLIGENCE" in html
        assert "Provider não elegível neste ponto" in html
        assert "AI-DEPENDENCY-001" in html


def test_ready_dependency_snapshot_is_projected_without_missing_dependencies() -> None:
    with tempfile.TemporaryDirectory() as directory:
        database = _database(Path(directory))
        connection = sqlite3.connect(database)
        try:
            connection.execute(
                "INSERT INTO ai_dependency_snapshots VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    "AID-2", "AUD-1", "TECHNICAL_AI", "AUDIT",
                    json.dumps(["TECHNICAL_RESOURCE_EVIDENCE"]),
                    json.dumps({"TECHNICAL_RESOURCE_EVIDENCE": True}),
                    "[]", json.dumps(["EV-ROBOTS"]), "fingerprint", 1,
                    "AI-DEPENDENCY-001", "2026-09-17T12:00:00Z",
                ),
            )
            connection.commit()
        finally:
            connection.close()

        html = dependency_html(database, SimpleNamespace(audit_id="AUD-1"))
        assert "IA técnica" in html
        assert "Pronto" in html
        assert "EV-ROBOTS" in html
        assert "Provider não elegível neste ponto" not in html
