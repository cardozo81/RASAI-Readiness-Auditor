from __future__ import annotations

from pathlib import Path
import sqlite3
from types import SimpleNamespace

from rasai.m25_overview_reporting import enrich_m25_overview_summary


def _workspace(tmp_path: Path):
    root = tmp_path / "AUD-M25-OVERVIEW"
    report = root / "report"
    report.mkdir(parents=True)
    database = root / "audit.db"
    connection = sqlite3.connect(database)
    try:
        connection.executescript(
            """
            CREATE TABLE synthetic_ux_apdex_runs (
                audit_id TEXT PRIMARY KEY,
                enabled INTEGER NOT NULL,
                status TEXT NOT NULL,
                target_samples_per_page INTEGER NOT NULL,
                valid_samples INTEGER NOT NULL,
                kpm TEXT NOT NULL,
                calibration_source TEXT NOT NULL
            );
            CREATE TABLE synthetic_ux_apdex_summaries (
                summary_id TEXT PRIMARY KEY,
                audit_id TEXT NOT NULL,
                url TEXT NOT NULL,
                device TEXT NOT NULL,
                final_group INTEGER NOT NULL
            );
            INSERT INTO synthetic_ux_apdex_runs VALUES (
                'AUD-M25-OVERVIEW',1,'SUCCESS',100,100,
                'USER_ACTION_DURATION','DYNATRACE_CONFIG_JSON'
            );
            INSERT INTO synthetic_ux_apdex_summaries VALUES (
                'SUM-1','AUD-M25-OVERVIEW','https://example.com/','POPULATION',1
            );
            INSERT INTO synthetic_ux_apdex_summaries VALUES (
                'SUM-2','AUD-M25-OVERVIEW','https://example.com/','MOBILE',1
            );
            """
        )
    finally:
        connection.close()

    (report / "index.html").write_text(
        "<!doctype html><main>"
        "<!-- rasai-apdex-index-start -->"
        "<section id='m23-apdex-summary'>Navigation</section>"
        "<!-- rasai-apdex-index-end -->"
        "</main>",
        encoding="utf-8",
    )
    return SimpleNamespace(root=root, database=database), report


def test_experience_apdex_is_added_after_navigation_apdex_on_overview(tmp_path: Path) -> None:
    workspace, report = _workspace(tmp_path)

    result = enrich_m25_overview_summary(audit_id="AUD-M25-OVERVIEW", workspace=workspace)

    assert result == report / "index.html"
    html = result.read_text(encoding="utf-8")
    assert html.index("m23-apdex-summary") < html.index("m25-apdex-experience-summary")
    assert "Synthetic User Experience Apdex" in html
    assert "Apdex calibrado" in html
    assert "USER_ACTION_DURATION" in html
    assert "DYNATRACE_CONFIG_JSON" in html
    assert "Populações finais" in html
    assert "apdex-experience.html" in html
    assert "Não é RUM" in html


def test_experience_apdex_overview_enrichment_is_idempotent(tmp_path: Path) -> None:
    workspace, _report = _workspace(tmp_path)

    enrich_m25_overview_summary(audit_id="AUD-M25-OVERVIEW", workspace=workspace)
    result = enrich_m25_overview_summary(audit_id="AUD-M25-OVERVIEW", workspace=workspace)

    assert result is not None
    html = result.read_text(encoding="utf-8")
    assert html.count("rasai-apdex-experience-index-start") == 1
    assert html.count("m25-apdex-experience-summary") == 1
