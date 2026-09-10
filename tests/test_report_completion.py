from __future__ import annotations

from pathlib import Path
import sqlite3
from types import SimpleNamespace

from rasai.report_completion import (
    AUDIT_ALWAYS_PAGES,
    expected_audit_report_pages,
    inspect_audit_report_site,
)


def _workspace(tmp_path: Path):
    root = tmp_path / "AUD-REPORT-COMPLETE"
    report = root / "report"
    report.mkdir(parents=True)
    database = root / "audit.db"
    connection = sqlite3.connect(database)
    try:
        connection.executescript(
            """
            CREATE TABLE pages (
                page_id TEXT PRIMARY KEY,
                audit_id TEXT NOT NULL
            );
            CREATE TABLE page_snapshots (
                snapshot_id TEXT PRIMARY KEY,
                page_id TEXT NOT NULL,
                device TEXT
            );
            CREATE TABLE synthetic_apdex_runs (
                audit_id TEXT,
                enabled INTEGER
            );
            CREATE TABLE synthetic_ux_apdex_runs (
                audit_id TEXT,
                enabled INTEGER
            );
            INSERT INTO pages(page_id,audit_id) VALUES('P-1','AUD-REPORT-COMPLETE');
            INSERT INTO page_snapshots(snapshot_id,page_id,device) VALUES('S-1','P-1','MOBILE');
            INSERT INTO synthetic_apdex_runs(audit_id,enabled) VALUES('AUD-REPORT-COMPLETE',1);
            INSERT INTO synthetic_ux_apdex_runs(audit_id,enabled) VALUES('AUD-REPORT-COMPLETE',0);
            """
        )
    finally:
        connection.close()
    return SimpleNamespace(root=root, database=database), report


def test_expected_pages_are_execution_specific(tmp_path: Path) -> None:
    workspace, _report = _workspace(tmp_path)
    expected = expected_audit_report_pages(
        audit_id="AUD-REPORT-COMPLETE",
        workspace=workspace,
    )
    assert set(AUDIT_ALWAYS_PAGES).issubset(set(expected))
    assert "mobile.html" in expected
    assert "desktop.html" not in expected
    assert "apdex.html" in expected
    assert "apdex-experience.html" not in expected
    assert "search-intelligence.html" not in expected
    assert "ai-visibility.html" not in expected
    assert "observability.html" not in expected
    assert "quality.html" not in expected


def test_completeness_detects_only_missing_audit_owned_pages(tmp_path: Path) -> None:
    workspace, report = _workspace(tmp_path)
    expected = expected_audit_report_pages(
        audit_id="AUD-REPORT-COMPLETE",
        workspace=workspace,
    )
    for name in expected:
        (report / name).write_text("<!doctype html><title>test</title>", encoding="utf-8")

    complete = inspect_audit_report_site(
        audit_id="AUD-REPORT-COMPLETE",
        workspace=workspace,
    )
    assert complete.complete is True
    assert complete.missing_pages == ()

    (report / "readiness.html").unlink()
    incomplete = inspect_audit_report_site(
        audit_id="AUD-REPORT-COMPLETE",
        workspace=workspace,
    )
    assert incomplete.complete is False
    assert incomplete.missing_pages == ("readiness.html",)
