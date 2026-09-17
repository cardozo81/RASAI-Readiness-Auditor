from __future__ import annotations

from pathlib import Path
import sqlite3

import pytest

from rasai.search_intelligence.freshness import (
    require_valid_serp_freshness,
    validate_serp_freshness,
)


def _database(path: Path) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.executescript(
            """
            PRAGMA foreign_keys=ON;
            CREATE TABLE audits(
                audit_id TEXT PRIMARY KEY,
                started_at TEXT,
                created_at TEXT
            );
            INSERT INTO audits VALUES(
                'AUD-1','2026-09-17T10:00:00+00:00','2026-09-17T09:59:00+00:00'
            );
            CREATE TABLE serp_observations(
                observation_id TEXT PRIMARY KEY,
                audit_id TEXT NOT NULL REFERENCES audits(audit_id),
                collected_at TEXT NOT NULL,
                data_mode TEXT NOT NULL
            );
            """
        )
        connection.commit()
    finally:
        connection.close()


def test_live_recollection_cannot_predate_audit_start(tmp_path: Path) -> None:
    database = tmp_path / "audit.db"
    _database(database)
    connection = sqlite3.connect(database)
    try:
        connection.execute(
            "INSERT INTO serp_observations VALUES (?,?,?,?)",
            ("SERP-1", "AUD-1", "2026-09-17T09:30:00+00:00", "OBSERVED_API"),
        )
        connection.commit()
    finally:
        connection.close()

    # Legacy rows that predate the AUD fail closed until explicit reuse provenance exists.
    issues = validate_serp_freshness(database, "AUD-1")
    assert [item.code for item in issues] == ["MISSING_REUSE_PROVENANCE"]
    with pytest.raises(RuntimeError, match="SERP freshness/provenance invariant failed"):
        require_valid_serp_freshness(database, "AUD-1")


def test_explicit_reused_evidence_is_valid_with_source_and_reason(tmp_path: Path) -> None:
    database = tmp_path / "audit.db"
    _database(database)
    connection = sqlite3.connect(database)
    try:
        connection.executescript(
            """
            INSERT INTO serp_observations VALUES(
                'SERP-REUSED','AUD-1','2026-09-17T09:30:00+00:00','IMPORTED'
            );
            CREATE TABLE serp_evidence_provenance(
                observation_id TEXT PRIMARY KEY REFERENCES serp_observations(observation_id),
                audit_id TEXT NOT NULL REFERENCES audits(audit_id),
                temporal_mode TEXT NOT NULL,
                captured_at TEXT NOT NULL,
                source_audit_id TEXT,
                source_observation_id TEXT,
                reused_at TEXT,
                reuse_reason TEXT,
                created_at TEXT NOT NULL
            );
            INSERT INTO serp_evidence_provenance VALUES(
                'SERP-REUSED','AUD-1','REUSED_EVIDENCE','2026-09-17T09:30:00+00:00',
                'AUD-SOURCE','SERP-SOURCE','2026-09-17T10:05:00+00:00',
                'reuso explícito para comparação histórica','2026-09-17T10:05:00+00:00'
            );
            """
        )
        connection.commit()
    finally:
        connection.close()

    assert validate_serp_freshness(database, "AUD-1") == ()
    require_valid_serp_freshness(database, "AUD-1")


def test_invalid_live_provenance_is_rejected(tmp_path: Path) -> None:
    database = tmp_path / "audit.db"
    _database(database)
    connection = sqlite3.connect(database)
    try:
        connection.executescript(
            """
            INSERT INTO serp_observations VALUES(
                'SERP-LIVE','AUD-1','2026-09-17T09:30:00+00:00','OBSERVED_API'
            );
            CREATE TABLE serp_evidence_provenance(
                observation_id TEXT PRIMARY KEY REFERENCES serp_observations(observation_id),
                audit_id TEXT NOT NULL REFERENCES audits(audit_id),
                temporal_mode TEXT NOT NULL,
                captured_at TEXT NOT NULL,
                source_audit_id TEXT,
                source_observation_id TEXT,
                reused_at TEXT,
                reuse_reason TEXT,
                created_at TEXT NOT NULL
            );
            INSERT INTO serp_evidence_provenance VALUES(
                'SERP-LIVE','AUD-1','LIVE_RECOLLECTION','2026-09-17T09:30:00+00:00',
                'AUD-1','SERP-LIVE',NULL,NULL,'2026-09-17T10:05:00+00:00'
            );
            """
        )
        connection.commit()
    finally:
        connection.close()

    issues = validate_serp_freshness(database, "AUD-1")
    assert any(item.code == "LIVE_RECOLLECTION_BEFORE_AUDIT" for item in issues)
