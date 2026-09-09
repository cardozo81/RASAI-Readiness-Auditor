from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import tempfile
from unittest.mock import patch

import pytest

from rasai import entrypoint
from rasai.m26_reporting import enrich_m26_report_site
from rasai.m26_visibility import FORMAT_VERSION, import_visibility_file, wilson_interval
from rasai.persistence import AuditWorkspace


def _workspace(root: Path) -> AuditWorkspace:
    workspace = AuditWorkspace.create(root, "AUD-M26")
    connection = sqlite3.connect(workspace.database)
    try:
        connection.executescript(
            """
            CREATE TABLE audits (audit_id TEXT PRIMARY KEY, project_name TEXT);
            INSERT INTO audits VALUES ('AUD-M26','Projeto M26');
            CREATE TABLE audit_targets (
                target_id TEXT PRIMARY KEY,
                audit_id TEXT,
                normalized_origin TEXT,
                target_type TEXT
            );
            INSERT INTO audit_targets VALUES ('T1','AUD-M26','https://example.test','DOMAIN');
            CREATE TABLE scores (
                score_id TEXT PRIMARY KEY,
                audit_id TEXT,
                dimension TEXT,
                device TEXT,
                value REAL,
                coverage REAL,
                confidence TEXT,
                consolidation_status TEXT,
                scoring_version TEXT
            );
            INSERT INTO scores VALUES ('S1','AUD-M26','OVERALL_READINESS','MOBILE',81,1,'HIGH','CONSOLIDATED','SCORE-GEO-004');
            """
        )
        connection.commit()
    finally:
        connection.close()
    report = workspace.root / "report"
    (report / "css").mkdir(parents=True)
    (report / "css" / "site.css").write_text("body{}", encoding="utf-8")
    (report / "index.html").write_text(
        "<!doctype html><html><body><aside class='app-nav'><nav><a href='index.html'>old</a></nav></aside><main class='app-main'><header class='hero'><h1>Index</h1></header></main></body></html>",
        encoding="utf-8",
    )
    return workspace


def _payload() -> dict:
    return {
        "format_version": FORMAT_VERSION,
        "source": {
            "type": "BING_WEBMASTER_TOOLS_AI_PERFORMANCE",
            "label": "Bing Webmaster Tools AI Performance",
            "capture_method": "NORMALIZED_EXPORT",
            "period_start": "2026-08-01",
            "period_end": "2026-08-31",
            "market": "BR",
            "language": "pt-BR",
            "reported_metrics": {"total_citations": 12, "average_cited_pages": 1.5},
            "metadata": {"capture": "normalized-manual-export"},
        },
        "page_citations": [
            {"url": "https://example.test/a", "citations": 8},
            {"url": "https://example.test/b", "citations": 4},
        ],
        "grounding_queries": [
            {"query": "seguro exemplo", "citations": 5, "url": "https://example.test/a"}
        ],
        "trend": [
            {"date": "2026-08-01", "citations": 3},
            {"date": "2026-08-31", "citations": 9},
        ],
        "query_runs": [
            {
                "engine": "BING_COPILOT",
                "surface": "AI answer",
                "query": "seguro exemplo",
                "observed_at": "2026-08-20T12:00:00-03:00",
                "status": "VALID",
                "cited": True,
                "cited_urls": ["https://example.test/a"],
            },
            {
                "engine": "BING_COPILOT",
                "surface": "AI answer",
                "query": "produto exemplo",
                "observed_at": "2026-08-20T12:05:00-03:00",
                "status": "VALID",
                "cited": False,
                "cited_urls": [],
            },
            {
                "engine": "BING_COPILOT",
                "query": "run inválido",
                "observed_at": "2026-08-20T12:10:00-03:00",
                "status": "INVALID",
                "cited": None,
                "cited_urls": [],
                "notes": "timeout externo",
            },
        ],
    }


def _write(root: Path, payload: dict) -> Path:
    path = root / "visibility.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def test_import_is_same_origin_idempotent_and_non_scoring() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        workspace = _workspace(root)
        source = _write(root, _payload())

        first = import_visibility_file(audit_id="AUD-M26", workspace=workspace, path=source)
        second = import_visibility_file(audit_id="AUD-M26", workspace=workspace, path=source)

        assert first.import_id == second.import_id
        assert first.capture_method == "NORMALIZED_EXPORT"
        assert first.valid_query_runs == 2
        assert first.cited_query_runs == 1
        assert first.citation_presence_rate == 0.5
        assert first.citation_presence_ci95_low is not None
        assert first.citation_presence_ci95_high is not None
        assert first.artifact_path.is_file()

        connection = sqlite3.connect(workspace.database)
        try:
            assert connection.execute("SELECT COUNT(*) FROM generative_visibility_imports").fetchone()[0] == 1
            assert connection.execute("SELECT capture_method FROM generative_visibility_imports").fetchone()[0] == "NORMALIZED_EXPORT"
            assert connection.execute("SELECT COUNT(*) FROM generative_visibility_page_citations").fetchone()[0] == 2
            assert connection.execute("SELECT COUNT(*) FROM generative_visibility_query_runs").fetchone()[0] == 3
            score = connection.execute("SELECT value,scoring_version FROM scores WHERE score_id='S1'").fetchone()
        finally:
            connection.close()
        assert score == (81.0, "SCORE-GEO-004")


def test_report_keeps_source_metrics_and_computed_presence_separate() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        workspace = _workspace(root)
        source = _write(root, _payload())
        import_visibility_file(audit_id="AUD-M26", workspace=workspace, path=source)
        report = enrich_m26_report_site(audit_id="AUD-M26", workspace=workspace)
        html = report.read_text(encoding="utf-8")
        index = (workspace.root / "report" / "index.html").read_text(encoding="utf-8")

        assert "Observed Generative Visibility" in html
        assert "Total Citations · fonte" in html
        assert ">12<" in html
        assert "Average Cited Pages · fonte" in html
        assert "Citation Presence Rate" in html
        assert "50.0%" in html
        assert "NORMALIZED_EXPORT" in html
        assert "não autentica o portal externo" in html
        assert "runs válidos que citaram" in html
        assert "não compõem SARI-001/SCORE-GEO-004" in html
        assert "SCORE-GEO-001" not in html
        assert "SCORE-GEO-002" not in html
        assert "SCORE-GEO-003" not in html
        assert "contratos históricos" not in html
        assert "não faz scraping" in html
        assert "ai-visibility.html" in index


def test_capture_method_is_required_and_bounded() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        workspace = _workspace(root)
        payload = _payload()
        payload["source"].pop("capture_method")
        with pytest.raises(ValueError, match="source.capture_method"):
            import_visibility_file(audit_id="AUD-M26", workspace=workspace, path=_write(root, payload))

        payload = _payload()
        payload["source"]["capture_method"] = "DIRECT_API_VERIFIED"
        with pytest.raises(ValueError, match="source.capture_method deve ser um de"):
            import_visibility_file(audit_id="AUD-M26", workspace=workspace, path=_write(root, payload))


def test_import_rejects_observations_from_another_origin() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        workspace = _workspace(root)
        payload = _payload()
        payload["page_citations"][0]["url"] = "https://other.test/a"
        source = _write(root, payload)
        with pytest.raises(ValueError, match="origin diferente"):
            import_visibility_file(audit_id="AUD-M26", workspace=workspace, path=source)


def test_rank_requires_explicit_ranking_semantics() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        workspace = _workspace(root)
        payload = _payload()
        payload["query_runs"][0]["rank"] = 1
        source = _write(root, payload)
        with pytest.raises(ValueError, match="ranking_semantics"):
            import_visibility_file(audit_id="AUD-M26", workspace=workspace, path=source)


def test_source_reported_bing_metrics_are_not_allowed_for_controlled_source() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        workspace = _workspace(root)
        payload = _payload()
        payload["source"]["type"] = "CONTROLLED_QUERY_RUNS"
        payload["source"]["capture_method"] = "CONTROLLED_PROTOCOL"
        source = _write(root, payload)
        with pytest.raises(ValueError, match="reported_metrics do Bing"):
            import_visibility_file(audit_id="AUD-M26", workspace=workspace, path=source)


def test_wilson_interval_uses_only_explicit_binomial_sample() -> None:
    low, high = wilson_interval(50, 100)
    assert 0.40 < low < 0.41
    assert 0.59 < high < 0.60
    assert wilson_interval(0, 0) is None


def test_top_level_entrypoint_delegates_existing_commands_and_intercepts_visibility() -> None:
    with patch("rasai.entrypoint.cli_extensions.main", return_value=17) as existing:
        assert entrypoint.main(["audit", "example.test"]) == 17
        existing.assert_called_once_with(["audit", "example.test"])

    with patch("rasai.m26_cli.main", return_value=23) as visibility:
        assert entrypoint.main(["visibility", "report", "--audit-id", "AUD-X"]) == 23
        visibility.assert_called_once_with(["report", "--audit-id", "AUD-X"])
