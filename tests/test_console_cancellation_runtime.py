from __future__ import annotations

import json
from pathlib import Path
import sqlite3

from rasai.console_cancellation_runtime import _mark_cancelled


def test_mark_cancelled_updates_nonterminal_audit_and_logs_event(tmp_path: Path) -> None:
    workspace = tmp_path / "AUD-TEST"
    (workspace / "logs").mkdir(parents=True)
    database = workspace / "audit.db"
    connection = sqlite3.connect(database)
    try:
        connection.execute(
            "CREATE TABLE audits(audit_id TEXT PRIMARY KEY,status TEXT,created_at TEXT)"
        )
        connection.execute(
            "INSERT INTO audits(audit_id,status,created_at) VALUES(?,?,?)",
            ("AUD-TEST", "ACQUIRING", "2026-09-11T00:00:00+00:00"),
        )
        connection.commit()
    finally:
        connection.close()

    assert _mark_cancelled(workspace) == "AUD-TEST"

    connection = sqlite3.connect(database)
    try:
        status = connection.execute(
            "SELECT status FROM audits WHERE audit_id='AUD-TEST'"
        ).fetchone()[0]
    finally:
        connection.close()
    assert status == "CANCELLED"

    payload = json.loads((workspace / "logs" / "audit.log").read_text(encoding="utf-8").splitlines()[-1])
    assert payload["event"] == "AUDIT_CANCELLED_BY_OPERATOR"
    assert payload["process_tree_terminated"] is True


def test_mark_cancelled_does_not_rewrite_completed_audit(tmp_path: Path) -> None:
    workspace = tmp_path / "AUD-DONE"
    (workspace / "logs").mkdir(parents=True)
    database = workspace / "audit.db"
    connection = sqlite3.connect(database)
    try:
        connection.execute(
            "CREATE TABLE audits(audit_id TEXT PRIMARY KEY,status TEXT,created_at TEXT)"
        )
        connection.execute(
            "INSERT INTO audits(audit_id,status,created_at) VALUES(?,?,?)",
            ("AUD-DONE", "COMPLETED", "2026-09-11T00:00:00+00:00"),
        )
        connection.commit()
    finally:
        connection.close()

    _mark_cancelled(workspace)
    connection = sqlite3.connect(database)
    try:
        status = connection.execute(
            "SELECT status FROM audits WHERE audit_id='AUD-DONE'"
        ).fetchone()[0]
    finally:
        connection.close()
    assert status == "COMPLETED"
