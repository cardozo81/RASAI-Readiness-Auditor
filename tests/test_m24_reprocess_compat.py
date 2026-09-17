from __future__ import annotations

import json
import sqlite3
from types import SimpleNamespace

from rasai.m24_reprocess_compat import load_persisted_m24_diagnostics


def test_reprocess_loader_reopens_current_m24_diagnostic_contract(tmp_path) -> None:
    database = tmp_path / "audit.db"
    connection = sqlite3.connect(database)
    try:
        connection.execute(
            """CREATE TABLE m24_diagnostics(
                diagnostic_id TEXT PRIMARY KEY,
                audit_id TEXT NOT NULL,
                code TEXT NOT NULL,
                category TEXT NOT NULL,
                severity TEXT NOT NULL,
                title TEXT NOT NULL,
                scope_url TEXT,
                observed_value TEXT NOT NULL,
                evidence_ids TEXT NOT NULL,
                remediation TEXT NOT NULL,
                scoring_impact TEXT NOT NULL,
                created_at TEXT NOT NULL
            )"""
        )
        connection.execute(
            "INSERT INTO m24_diagnostics VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                "D1",
                "AUD-1",
                "M24-TEST",
                "ROBOTS",
                "INFO",
                "Teste",
                "https://example.test/robots.txt",
                json.dumps({"state": "OBSERVED"}),
                json.dumps(["E1"]),
                "Nenhuma ação.",
                "NONE",
                "2026-09-17T18:00:00+00:00",
            ),
        )
        connection.commit()
    finally:
        connection.close()

    workspace = SimpleNamespace(database=database)
    diagnostics = load_persisted_m24_diagnostics(workspace, "AUD-1")

    assert len(diagnostics) == 1
    diagnostic = diagnostics[0]
    assert diagnostic.code == "M24-TEST"
    assert diagnostic.category == "ROBOTS"
    assert diagnostic.observed == {"state": "OBSERVED"}
    assert diagnostic.evidence_ids == ("E1",)
    assert not hasattr(diagnostic, "scoring_impact")
