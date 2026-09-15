from __future__ import annotations

import sqlite3
from pathlib import Path

from rasai.console_history_presentation import domain_context, process_finished_at


def _database(root: Path) -> sqlite3.Connection:
    root.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(root / "audit.db")
    connection.executescript(
        """
        CREATE TABLE audits (
            audit_id TEXT PRIMARY KEY,
            completed_at TEXT
        );
        CREATE TABLE console_execution_projections (
            audit_id TEXT PRIMARY KEY,
            finished_at TEXT NOT NULL
        );
        CREATE TABLE audit_reprocess_runs (
            reprocess_id TEXT PRIMARY KEY,
            audit_id TEXT NOT NULL,
            completed_at TEXT
        );
        CREATE TABLE audit_targets (
            target_id TEXT PRIMARY KEY,
            audit_id TEXT,
            input_url TEXT,
            normalized_origin TEXT,
            target_type TEXT
        );
        CREATE TABLE pages (
            page_id TEXT PRIMARY KEY,
            audit_id TEXT,
            normalized_url TEXT
        );
        """
    )
    return connection


def test_process_completion_is_independent_from_logical_final_status(tmp_path: Path) -> None:
    audit_root = tmp_path / "AUD-PARTIAL"
    connection = _database(audit_root)
    try:
        connection.execute("INSERT INTO audits VALUES (?,?)", ("AUD-PARTIAL", None))
        connection.execute(
            "INSERT INTO console_execution_projections VALUES (?,?)",
            ("AUD-PARTIAL", "2026-09-15T10:05:00+00:00"),
        )
        connection.commit()
    finally:
        connection.close()

    assert process_finished_at(audit_root, "AUD-PARTIAL") == "2026-09-15T10:05:00+00:00"


def test_latest_completed_reprocess_becomes_latest_process_completion(tmp_path: Path) -> None:
    audit_root = tmp_path / "AUD-RPR"
    connection = _database(audit_root)
    try:
        connection.execute("INSERT INTO audits VALUES (?,?)", ("AUD-RPR", None))
        connection.execute(
            "INSERT INTO console_execution_projections VALUES (?,?)",
            ("AUD-RPR", "2026-09-15T10:05:00+00:00"),
        )
        connection.execute(
            "INSERT INTO audit_reprocess_runs VALUES (?,?,?)",
            ("RPR-1", "AUD-RPR", "2026-09-15T12:30:00+00:00"),
        )
        connection.commit()
    finally:
        connection.close()

    assert process_finished_at(audit_root, "AUD-RPR") == "2026-09-15T12:30:00+00:00"


def test_domain_context_shows_only_domain_for_single_audited_url(tmp_path: Path) -> None:
    audit_root = tmp_path / "AUD-ONE"
    connection = _database(audit_root)
    try:
        connection.execute("INSERT INTO audits VALUES (?,?)", ("AUD-ONE", None))
        connection.execute(
            "INSERT INTO audit_targets VALUES (?,?,?,?,?)",
            ("T1", "AUD-ONE", "https://www.example.com/a", "https://www.example.com", "URL"),
        )
        connection.execute(
            "INSERT INTO pages VALUES (?,?,?)",
            ("P1", "AUD-ONE", "https://www.example.com/a"),
        )
        connection.commit()
    finally:
        connection.close()

    assert domain_context(audit_root, "AUD-ONE") == "www.example.com"


def test_domain_context_shows_primary_domain_and_total_urls(tmp_path: Path) -> None:
    audit_root = tmp_path / "AUD-MANY"
    connection = _database(audit_root)
    try:
        connection.execute("INSERT INTO audits VALUES (?,?)", ("AUD-MANY", None))
        connection.execute(
            "INSERT INTO audit_targets VALUES (?,?,?,?,?)",
            ("T1", "AUD-MANY", "https://example.com/a", "https://example.com", "DOMAIN"),
        )
        connection.executemany(
            "INSERT INTO pages VALUES (?,?,?)",
            (
                ("P1", "AUD-MANY", "https://example.com/a"),
                ("P2", "AUD-MANY", "https://example.com/b"),
                ("P3", "AUD-MANY", "https://example.com/c"),
            ),
        )
        connection.commit()
    finally:
        connection.close()

    assert domain_context(audit_root, "AUD-MANY") == "example.com (3 URLs)"
