from __future__ import annotations

import json
from pathlib import Path
import sqlite3

from rasai.request_remediation_intelligence import (
    _validate_solutions,
    collect_request_error_evidence,
    group_request_error_evidence,
    persist_request_remediation_groups,
)


def _database(path: Path) -> Path:
    connection = sqlite3.connect(path)
    try:
        connection.executescript(
            """
            CREATE TABLE audits(audit_id TEXT PRIMARY KEY);
            INSERT INTO audits VALUES ('AUD-1');

            CREATE TABLE synthetic_ux_apdex_samples (
                sample_id TEXT PRIMARY KEY,
                audit_id TEXT NOT NULL,
                page_id TEXT,
                url TEXT NOT NULL,
                device TEXT NOT NULL,
                run_index INTEGER NOT NULL,
                error_forced_frustrated INTEGER NOT NULL,
                captured_at TEXT
            );
            CREATE TABLE synthetic_ux_apdex_error_details (
                sample_id TEXT NOT NULL,
                sequence_no INTEGER NOT NULL,
                audit_id TEXT NOT NULL,
                error_type TEXT NOT NULL,
                source_url TEXT,
                first_party INTEGER,
                resource_type TEXT,
                http_status INTEGER,
                message TEXT,
                captured_at TEXT,
                PRIMARY KEY(sample_id,sequence_no)
            );
            INSERT INTO synthetic_ux_apdex_samples VALUES
                ('UX-1','AUD-1','P-1','https://example.com/','MOBILE',1,1,'2026-09-17T10:00:00Z'),
                ('UX-2','AUD-1','P-1','https://example.com/','MOBILE',2,1,'2026-09-17T10:01:00Z'),
                ('UX-3','AUD-1','P-1','https://example.com/','MOBILE',3,0,'2026-09-17T10:02:00Z');
            INSERT INTO synthetic_ux_apdex_error_details VALUES
                ('UX-1',1,'AUD-1','HTTP_ERROR','https://example.com/assets/a.js?v=1',1,'script',404,NULL,'2026-09-17T10:00:00Z'),
                ('UX-1',2,'AUD-1','HTTP_ERROR','https://example.com/assets/b.js?v=9',1,'script',404,NULL,'2026-09-17T10:00:00Z'),
                ('UX-2',1,'AUD-1','HTTP_ERROR','https://example.com/assets/a.js?v=2',1,'script',404,NULL,'2026-09-17T10:01:00Z'),
                ('UX-2',2,'AUD-1','JAVASCRIPT_ERROR',NULL,NULL,NULL,NULL,'TypeError: widget is undefined','2026-09-17T10:01:00Z');

            CREATE TABLE synthetic_apdex_samples (
                sample_id TEXT PRIMARY KEY,
                audit_id TEXT NOT NULL,
                url TEXT NOT NULL,
                device TEXT NOT NULL,
                run_index INTEGER NOT NULL,
                browser_diagnostics TEXT,
                captured_at TEXT
            );
            """
        )
        browser = json.dumps(
            {
                "events": [
                    {"type": "PAGE_ERROR", "message": "TypeError: widget is undefined", "url": ""}
                ]
            }
        )
        connection.execute(
            "INSERT INTO synthetic_apdex_samples VALUES (?,?,?,?,?,?,?)",
            ('NAV-1','AUD-1','https://example.com/','DESKTOP',1,browser,'2026-09-17T09:59:00Z'),
        )
        connection.commit()
    finally:
        connection.close()
    return path


def test_groups_requests_by_solution_family_and_preserves_sources(tmp_path: Path) -> None:
    database = _database(tmp_path / "audit.db")
    events, universe = collect_request_error_evidence(database, "AUD-1")
    groups = group_request_error_evidence(events, universe, audit_id="AUD-1")

    not_found = next(group for group in groups if group["family"] == "RESOURCE_NOT_FOUND")
    assert not_found["problem_count"] == 2
    assert not_found["occurrence_count"] == 3
    assert not_found["affected_sample_count"] == 2
    assert not_found["source_catalogs"] == ["CAT-07"]
    assert not_found["observed_impacts"] == ["Apdex de experiência", "Experiência sintética"]
    assert not_found["resource_urls"] == [
        "https://example.com/assets/a.js",
        "https://example.com/assets/b.js",
    ]

    javascript = next(group for group in groups if group["family"] == "JAVASCRIPT_RUNTIME")
    assert javascript["occurrence_count"] == 2
    assert javascript["source_catalogs"] == ["CAT-06", "CAT-07"]


def test_persists_grouped_evidence_without_duplicating_ai_facts(tmp_path: Path) -> None:
    database = _database(tmp_path / "audit.db")
    events, universe = collect_request_error_evidence(database, "AUD-1")
    groups = group_request_error_evidence(events, universe, audit_id="AUD-1")
    persist_request_remediation_groups(database, "AUD-1", groups)

    connection = sqlite3.connect(database)
    try:
        group_count = connection.execute(
            "SELECT COUNT(*) FROM request_remediation_groups WHERE audit_id='AUD-1'"
        ).fetchone()[0]
        evidence_count = connection.execute(
            "SELECT COUNT(*) FROM request_remediation_evidence WHERE audit_id='AUD-1'"
        ).fetchone()[0]
    finally:
        connection.close()
    assert group_count == len(groups)
    assert evidence_count == len(events)


def test_ai_solution_validation_is_bound_to_known_group_ids() -> None:
    groups = [
        {
            "group_id": "REQG-1",
            "title": "Corrigir recursos ausentes",
        }
    ]
    accepted, missing = _validate_solutions(
        {
            "solutions": [
                {
                    "group_id": "REQG-1",
                    "title": "Publicar assets",
                    "solution": "Corrigir a publicação dos arquivos e as referências geradas pelo build.",
                    "technical_detail": "Validar o manifesto e o caminho público.",
                    "example": "GET /assets/app.js -> 200",
                    "verification": "Reexecutar as amostras e confirmar ausência de 404.",
                    "confidence": 0.91,
                    "effort": "MEDIUM",
                },
                {
                    "group_id": "REQG-UNKNOWN",
                    "title": "Não permitido",
                    "solution": "x",
                    "technical_detail": "x",
                    "example": "x",
                    "verification": "x",
                    "confidence": 1,
                    "effort": "LOW",
                },
            ]
        },
        groups,
    )
    assert list(accepted) == ["REQG-1"]
    assert missing == []
