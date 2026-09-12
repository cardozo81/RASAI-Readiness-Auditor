from __future__ import annotations

from pathlib import Path
import sqlite3
from types import SimpleNamespace

from rasai.report_completion import (
    AUDIT_ALWAYS_PAGES,
    expected_audit_report_pages,
    inspect_audit_report_site,
)
from rasai.report_contract import CANONICAL_FILENAMES
from rasai.report_scope_clarity import materialize_missing_canonical_surfaces


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


def test_expected_pages_are_static_canonical_surfaces(tmp_path: Path) -> None:
    workspace, _report = _workspace(tmp_path)
    expected = expected_audit_report_pages(
        audit_id="AUD-REPORT-COMPLETE",
        workspace=workspace,
    )
    assert AUDIT_ALWAYS_PAGES == CANONICAL_FILENAMES
    assert expected == CANONICAL_FILENAMES
    assert "mobile.html" in expected
    assert "desktop.html" in expected
    assert "standards.html" in expected
    assert "apdex.html" in expected
    assert "apdex-experience.html" in expected
    assert "search-intelligence.html" in expected
    assert "ai-visibility.html" in expected
    assert "observability.html" in expected
    assert "quality.html" in expected


def test_completeness_detects_missing_canonical_page(tmp_path: Path) -> None:
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

    (report / "standards.html").unlink()
    incomplete = inspect_audit_report_site(
        audit_id="AUD-REPORT-COMPLETE",
        workspace=workspace,
    )
    assert incomplete.complete is False
    assert incomplete.missing_pages == ("standards.html",)


def test_missing_surfaces_get_neutral_html_without_overwriting_real_page(tmp_path: Path) -> None:
    _workspace_obj, report = _workspace(tmp_path)
    css = report / "css"
    css.mkdir(parents=True)
    (css / "site.css").write_text("body{}", encoding="utf-8")
    real_index = "<!doctype html><html><body><main>REAL INDEX</main></body></html>"
    (report / "index.html").write_text(real_index, encoding="utf-8")

    created = materialize_missing_canonical_surfaces(report)

    assert "index.html" not in created
    assert (report / "index.html").read_text(encoding="utf-8") == real_index
    assert set(created) == set(CANONICAL_FILENAMES) - {"index.html"}
    for filename in created:
        html = (report / filename).read_text(encoding="utf-8")
        assert "data-rasai-empty-surface='true'" in html
        assert "SEM DADOS" in html
        assert "não é convertida em falha do website" in html
