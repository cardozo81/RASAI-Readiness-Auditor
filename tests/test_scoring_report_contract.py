from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile

from rasai.persistence import AuditWorkspace
from rasai.report_manifest import write_report_manifest
from rasai.report_registry import install
from rasai.score_geo_004_reporting import REPORT_FILE, write_score_geo_004_report


CURRENT_SCORING_VERSION = "SCORE-GEO-004"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _workspace(root: Path, scoring_version: str) -> AuditWorkspace:
    root.mkdir(parents=True)
    (root / "artifacts").mkdir()
    report = root / "report"
    (report / "css").mkdir(parents=True)
    (report / "css" / "site.css").write_text("body{}\n", encoding="utf-8")
    connection = sqlite3.connect(root / "audit.db")
    try:
        connection.executescript(
            """
            CREATE TABLE audits(
                audit_id TEXT PRIMARY KEY,
                auditor_version TEXT,
                ruleset_version TEXT
            );
            CREATE TABLE scores(
                score_id TEXT PRIMARY KEY,
                audit_id TEXT NOT NULL,
                device TEXT NOT NULL,
                dimension TEXT NOT NULL,
                value REAL,
                coverage REAL NOT NULL,
                confidence TEXT NOT NULL,
                consolidation_status TEXT NOT NULL,
                scoring_version TEXT NOT NULL,
                calculated_at TEXT NOT NULL,
                limitations TEXT NOT NULL
            );
            CREATE TABLE score_contributions(
                contribution_id TEXT PRIMARY KEY,
                score_id TEXT NOT NULL,
                dimension TEXT NOT NULL,
                rule_id TEXT NOT NULL,
                weight REAL NOT NULL
            );
            """
        )
        connection.execute(
            "INSERT INTO audits VALUES (?,?,?)",
            ("AUD-CURRENT", "0.1.0", "BR-GEO-001-056-V1"),
        )
        connection.execute(
            "INSERT INTO scores VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (
                "SCORE-1",
                "AUD-CURRENT",
                "DESKTOP",
                "OVERALL_READINESS",
                77.5,
                0.90,
                "MEDIUM",
                "CONSOLIDATED",
                scoring_version,
                "2026-09-08T00:00:00+00:00",
                "[]",
            ),
        )
        if scoring_version == CURRENT_SCORING_VERSION:
            connection.execute(
                "INSERT INTO score_contributions VALUES (?,?,?,?,?)",
                ("C-1", "SCORE-1", "TECHNICAL_ACCESSIBILITY", "BR-GEO-005", 1.0),
            )
        connection.commit()
    finally:
        connection.close()
    return AuditWorkspace(root)


def test_scoring_report_projects_only_current_prepublication_contract() -> None:
    install()
    with tempfile.TemporaryDirectory() as directory:
        workspace = _workspace(Path(directory) / "AUD-CURRENT", CURRENT_SCORING_VERSION)
        before = _sha256(workspace.database)
        path = write_score_geo_004_report(audit_id="AUD-CURRENT", workspace=workspace)
        after = _sha256(workspace.database)
        html = path.read_text(encoding="utf-8")
        assert path.name == REPORT_FILE == "scoring.html"
        assert CURRENT_SCORING_VERSION in html
        assert "VIGENTE" in html
        assert "O que entra no score" in html
        assert "O que não entra automaticamente no score" in html
        assert not list(path.parent.glob("score-geo-*.html"))
        assert before == after


def test_report_manifest_exposes_current_version_axes_without_score_or_evidence_payloads() -> None:
    install()
    with tempfile.TemporaryDirectory() as directory:
        workspace = _workspace(Path(directory) / "AUD-CURRENT", CURRENT_SCORING_VERSION)
        write_score_geo_004_report(audit_id="AUD-CURRENT", workspace=workspace)
        (workspace.root / "report" / "index.html").write_text("<!doctype html>", encoding="utf-8")
        manifest_path = write_report_manifest(workspace.root / "report")
        assert manifest_path is not None
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert payload["audit_id"] == "AUD-CURRENT"
        assert payload["auditor_version"] == "0.1.0"
        assert payload["ruleset_version"] == "BR-GEO-001-056-V1"
        assert payload["sari_version"] == "SARI-001"
        assert payload["scoring_version"] == CURRENT_SCORING_VERSION
        assert payload["report_contract_version"].startswith("REPORT-CONTRACT-")
        assert payload["source_db"] == "audit.db"
        assert "scoring.html" in payload["generated_pages"]
        assert "aliases" not in payload
        assert "score" not in payload
        assert "evidence" not in payload
