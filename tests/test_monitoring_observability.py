from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import tempfile

from rasai.monitoring.compare import compare_audits, evaluate_release_gate
from rasai.monitoring.impact import analyze_change_impact
from rasai.monitoring.reporting import write_monitoring_report
from rasai.observability.diagnostics import analyze_workspace
from rasai.observability.reporting import enrich_observability_report
from rasai.observability.store import ObservabilityStore, new_dataset


def _workspace(
    root: Path,
    audit_id: str,
    *,
    rule_result: str = "PASS",
    canonical: str = "https://example.test/a",
    score: float = 90.0,
    with_artifacts: bool = False,
) -> Path:
    workspace = root / audit_id
    workspace.mkdir(parents=True)
    database = workspace / "audit.db"
    connection = sqlite3.connect(database)
    try:
        connection.executescript(
            f"""
            CREATE TABLE audits (
                audit_id TEXT PRIMARY KEY, project_name TEXT, created_at TEXT, started_at TEXT,
                completed_at TEXT, status TEXT, completion_status TEXT, auditor_version TEXT, ruleset_version TEXT
            );
            INSERT INTO audits VALUES ('{audit_id}','Projeto','2026-09-01T10:00:00Z','2026-09-01T10:00:00Z','2026-09-01T10:05:00Z','COMPLETED','COMPLETE','1.0','RULESET-1');
            CREATE TABLE audit_targets (target_id TEXT PRIMARY KEY,audit_id TEXT,normalized_origin TEXT,target_type TEXT);
            INSERT INTO audit_targets VALUES ('T1','{audit_id}','https://example.test','DOMAIN');
            CREATE TABLE pages (page_id TEXT PRIMARY KEY,audit_id TEXT,normalized_url TEXT);
            INSERT INTO pages VALUES ('P1','{audit_id}','https://example.test/a');
            INSERT INTO pages VALUES ('P2','{audit_id}','https://example.test/b');
            CREATE TABLE page_snapshots (
                snapshot_id TEXT PRIMARY KEY,page_id TEXT,device TEXT,captured_at TEXT,http_status INTEGER,
                final_url TEXT,canonical TEXT,meta_robots TEXT,title TEXT,structured_data_ref TEXT,
                rendered_artifact_ref TEXT,raw_artifact_ref TEXT,main_content_ref TEXT
            );
            INSERT INTO page_snapshots VALUES ('S1','P1','MOBILE','2026-09-01T10:01:00Z',200,'https://example.test/a','{canonical}','index,follow','Produto A',NULL,NULL,NULL,NULL);
            INSERT INTO page_snapshots VALUES ('S2','P2','MOBILE','2026-09-01T10:01:00Z',200,'https://example.test/b','https://example.test/b','index,follow','Produto B',NULL,NULL,NULL,NULL);
            CREATE TABLE rule_executions (
                audit_id TEXT,rule_id TEXT,page_id TEXT,device TEXT,result TEXT,observed_value TEXT,error TEXT,executed_at TEXT
            );
            INSERT INTO rule_executions VALUES ('{audit_id}','BR-GEO-011','P1','MOBILE','{rule_result}','{{}}',NULL,'2026-09-01T10:02:00Z');
            INSERT INTO rule_executions VALUES ('{audit_id}','BR-GEO-038','P1','MOBILE','PASS','{{"primary_intent":"seguro viagem"}}',NULL,'2026-09-01T10:02:00Z');
            CREATE TABLE findings (
                audit_id TEXT,severity TEXT,rule_id TEXT,page_id TEXT,device TEXT,status TEXT,title TEXT,observed_value TEXT
            );
            INSERT INTO findings VALUES ('{audit_id}','HIGH','BR-GEO-011','P1','MOBILE','OPEN','Indexabilidade','{{"selector":".shared-component"}}');
            INSERT INTO findings VALUES ('{audit_id}','HIGH','BR-GEO-011','P2','MOBILE','OPEN','Indexabilidade','{{"selector":".shared-component"}}');
            CREATE TABLE scores (
                score_id TEXT PRIMARY KEY,audit_id TEXT,dimension TEXT,device TEXT,value REAL,coverage REAL,
                confidence TEXT,consolidation_status TEXT,scoring_version TEXT,calculated_at TEXT
            );
            INSERT INTO scores VALUES ('SC1','{audit_id}','INDEXABILITY','MOBILE',{score},1.0,'HIGH','CONSOLIDATED','SCORE-GEO-003','2026-09-01T10:03:00Z');
            """
        )
        connection.commit()
    finally:
        connection.close()

    report = workspace / "report"
    (report / "css").mkdir(parents=True)
    (report / "css" / "site.css").write_text("body{}", encoding="utf-8")
    (report / "index.html").write_text(
        "<!doctype html><html><body><aside class='app-nav'><nav><a href='index.html'>old</a></nav></aside><main class='app-main'><h1>Index</h1></main></body></html>",
        encoding="utf-8",
    )
    if with_artifacts:
        _add_artifacts(workspace)
    return workspace


def _add_artifacts(workspace: Path) -> None:
    extraction = workspace / "artifacts" / "extraction"
    extraction.mkdir(parents=True)
    structured_a = extraction / "structured-a.json"
    structured_a.write_text(json.dumps({
        "blocks": [{"parse_error": None, "parsed": [
            {"@context":"https://schema.org","@type":"Product","name":"Produto A"},
            {"@context":"https://schema.org","@type":"Organization","@id":"https://example.test/#org","name":"Example A","url":"https://example.test"},
            {"@context":"https://schema.org","@type":"Article","datePublished":"2026-09-03","dateModified":"2026-09-02"},
        ]}]
    }), encoding="utf-8")
    structured_b = extraction / "structured-b.json"
    structured_b.write_text(json.dumps({
        "blocks": [{"parse_error": None, "parsed": [
            {"@context":"https://schema.org","@type":"Organization","@id":"https://example.test/#org","name":"Example B","url":"https://example.test"}
        ]}]
    }), encoding="utf-8")
    html_a = extraction / "a.html"
    html_a.write_text("<html><head><link rel='alternate' hreflang='pt-BR' href='/a'></head><body><h1>Seguro viagem?</h1><table><tr><td>sem header</td></tr></table></body></html>", encoding="utf-8")
    html_b = extraction / "b.html"
    html_b.write_text("<html><head></head><body><h1>Outro</h1></body></html>", encoding="utf-8")
    main_a = extraction / "a.txt"
    main_a.write_text("Seguro viagem com cobertura internacional.", encoding="utf-8")
    main_b = extraction / "b.txt"
    main_b.write_text("Outro conteúdo.", encoding="utf-8")

    connection = sqlite3.connect(workspace / "audit.db")
    try:
        connection.execute("UPDATE page_snapshots SET structured_data_ref=?,rendered_artifact_ref=?,main_content_ref=? WHERE page_id='P1'", (
            structured_a.relative_to(workspace).as_posix(), html_a.relative_to(workspace).as_posix(), main_a.relative_to(workspace).as_posix(),
        ))
        connection.execute("UPDATE page_snapshots SET structured_data_ref=?,rendered_artifact_ref=?,main_content_ref=? WHERE page_id='P2'", (
            structured_b.relative_to(workspace).as_posix(), html_b.relative_to(workspace).as_posix(), main_b.relative_to(workspace).as_posix(),
        ))
        connection.commit()
    finally:
        connection.close()


def _observed(workspace: Path, *, impressions: float, canonical: str) -> None:
    dataset = new_dataset(
        dataset_id="OBS-TEST", source_type="GOOGLE_SEARCH_CONSOLE", capture_method="TEST",
        artifact_path="artifacts/observability/test.json", artifact_sha256="0" * 64,
        period_start="2026-08-01", period_end="2026-08-31",
    )
    with ObservabilityStore(workspace) as store:
        (store.artifacts / "test.json").write_text("{}", encoding="utf-8")
        store.replace_dataset_rows(
            dataset,
            search_rows=(
                {"record_id":"R1","source":"GOOGLE_SEARCH_CONSOLE","observed_date":"2026-08-31","query_text":"seguro viagem","url":"https://example.test/a","device":"MOBILE","country":"BRA","surface":"web","clicks":10,"impressions":impressions,"ctr":10/impressions,"position":3,"metadata":{}},
                {"record_id":"R2","source":"GOOGLE_SEARCH_CONSOLE","observed_date":"2026-08-31","query_text":"seguro viagem","url":"https://example.test/b","device":"MOBILE","country":"BRA","surface":"web","clicks":5,"impressions":impressions/2,"ctr":10/impressions,"position":4,"metadata":{}},
            ),
            index_rows=(
                {"record_id":"I1","source":"GOOGLE_SEARCH_CONSOLE_URL_INSPECTION","url":"https://example.test/a","verdict":"PASS","coverage_state":"Submitted and indexed","indexing_state":"INDEXING_ALLOWED","robots_txt_state":"ALLOWED","page_fetch_state":"SUCCESSFUL","user_canonical":"https://example.test/a","selected_canonical":canonical,"last_crawl_time":"2026-08-31T10:00:00Z","crawled_as":"MOBILE","referring_urls":(),"sitemap_urls":(),"metadata":{}},
            ),
        )


def test_monitor_detects_regression_and_release_gate() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        baseline = _workspace(root, "AUD-BASE", rule_result="PASS", score=92)
        current = _workspace(root, "AUD-CURRENT", rule_result="FAIL", canonical="https://example.test/b", score=80)
        result = compare_audits(baseline, current)
        assert any(event.rule_id == "BR-GEO-011" and event.status == "REGRESSED" for event in result.events)
        assert any(event.label == "Canonical" and event.status == "CHANGED" for event in result.events)
        gate = evaluate_release_gate(result)
        assert gate.passed is False
        assert any(event.rule_id == "BR-GEO-011" for event in gate.blocking_events)
        report = write_monitoring_report(root, result)
        assert report.report_path.is_file()
        assert "Release gate" in report.report_path.read_text(encoding="utf-8")


def test_unknown_does_not_become_regression() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        baseline = _workspace(root, "AUD-BASE", rule_result="PASS")
        current = _workspace(root, "AUD-CURRENT", rule_result="UNKNOWN")
        result = compare_audits(baseline, current)
        event = next(event for event in result.events if event.rule_id == "BR-GEO-011")
        assert event.status == "DATA_UNAVAILABLE"
        assert event.material is False


def test_observability_diagnostics_matrix_intent_clusters_and_report() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        workspace = _workspace(root, "AUD-OBS", with_artifacts=True)
        _observed(workspace, impressions=1000, canonical="https://example.test/b")
        bundle = analyze_workspace(workspace)
        codes = {item.code for item in bundle.diagnostics}
        assert "SD-PRODUCT-DOC" in codes
        assert "HREFLANG-ABSOLUTE-URL" in codes
        assert "ENTITY-NAME-CONFLICT" in codes
        assert "FRESHNESS-DATE-CONFLICT" in codes
        assert "RETRIEVAL-TABLE-HEADERS" in codes
        assert bundle.template_clusters
        assert any(row["canonical_alignment"] == "DIFFERENT" for row in bundle.indexability_matrix)
        assert any(row["status"] == "ALIGNED" for row in bundle.query_intent_alignment)
        assert bundle.cannibalization_candidates
        report = enrich_observability_report(audit_workspace=workspace)
        html = report.read_text(encoding="utf-8")
        assert "Indexability Reality Matrix" in html
        assert "Potential Search Cannibalization" in html
        assert "não altera SARI-001" in html
        assert "observability.html" in (workspace / "report" / "index.html").read_text(encoding="utf-8")


def test_change_impact_reports_association_without_causality() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        baseline = _workspace(root, "AUD-BASE", rule_result="PASS")
        current = _workspace(root, "AUD-CURRENT", rule_result="FAIL")
        _observed(baseline, impressions=1000, canonical="https://example.test/a")
        _observed(current, impressions=500, canonical="https://example.test/b")
        result = compare_audits(baseline, current)
        impact = analyze_change_impact(result)
        assert any(item.status == "REGRESSED" and "impressions" in item.metric for item in impact.outcome_changes)
        assert impact.associations
        assert all(item["status"] == "TEMPORAL_ASSOCIATION_ONLY" for item in impact.associations)
