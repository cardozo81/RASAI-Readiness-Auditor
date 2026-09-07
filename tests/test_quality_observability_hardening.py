from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import tempfile

from rasai.monitoring.compare import compare_audits, evaluate_release_gate
from rasai.monitoring.impact import _observed_snapshot, analyze_change_impact
from rasai.monitoring.models import AuditSnapshot, ChangeEvent, ComparisonResult, GatePolicy
from rasai.observability.diagnostics import analyze_workspace
from rasai.observability.google_genai import (
    import_google_genai_performance_csv,
    persist_google_genai_control,
)
from rasai.observability.google_search_console import collect_search_analytics
from rasai.observability.gsc_resources import collect_sites, collect_sitemaps
from rasai.observability.store import Dataset, ObservabilityStore, new_dataset
from rasai.quality.analysis import analyze_quality
from rasai.quality.content_controls import analyze_content_controls
from rasai.quality.reporting import write_quality_report
from rasai.quality.verification import verify_fixes


class _Response:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


def _audit_workspace(
    root: Path,
    audit_id: str,
    *,
    rule_result: str = "FAIL",
    completed_at: str = "2026-09-01T10:05:00Z",
    structured_future_date: bool = False,
) -> Path:
    workspace = root / audit_id
    workspace.mkdir()
    rendered = workspace / "artifacts" / "rendered" / "page.html"
    rendered.parent.mkdir(parents=True)
    rendered.write_text(
        "<html><body><main><p data-nosnippet>private excerpt</p><h1>Produto</h1></main></body></html>",
        encoding="utf-8",
    )
    structured = workspace / "artifacts" / "extraction" / "structured.json"
    structured.parent.mkdir(parents=True)
    published = "2026-09-02" if structured_future_date else "2026-08-01"
    structured.write_text(
        json.dumps(
            {
                "blocks": [
                    {
                        "parse_error": None,
                        "parsed": [
                            {
                                "@context": "https://schema.org",
                                "@type": "Article",
                                "datePublished": published,
                                "dateModified": published,
                            }
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    report = workspace / "report"
    report.mkdir()
    (report / "index.html").write_text(
        "<!doctype html><html><body><aside class='app-nav'><nav><a href='index.html'>Index</a></nav></aside><main class='app-main'>Index</main></body></html>",
        encoding="utf-8",
    )

    connection = sqlite3.connect(workspace / "audit.db")
    try:
        connection.executescript(
            f"""
            CREATE TABLE audits (
                audit_id TEXT PRIMARY KEY, project_name TEXT, created_at TEXT, started_at TEXT,
                completed_at TEXT, status TEXT, completion_status TEXT, auditor_version TEXT, ruleset_version TEXT
            );
            INSERT INTO audits VALUES (
                '{audit_id}','Projeto','2026-09-01T10:00:00Z','2026-09-01T10:00:00Z',
                '{completed_at}','COMPLETED','COMPLETE','1.0','RULESET-1'
            );
            CREATE TABLE audit_targets (target_id TEXT PRIMARY KEY,audit_id TEXT,normalized_origin TEXT,target_type TEXT);
            INSERT INTO audit_targets VALUES ('T1','{audit_id}','https://example.test','DOMAIN');
            CREATE TABLE pages (page_id TEXT PRIMARY KEY,audit_id TEXT,normalized_url TEXT);
            INSERT INTO pages VALUES ('P1','{audit_id}','https://example.test/a');
            CREATE TABLE page_snapshots (
                snapshot_id TEXT PRIMARY KEY,page_id TEXT,device TEXT,captured_at TEXT,http_status INTEGER,
                final_url TEXT,canonical TEXT,meta_robots TEXT,title TEXT,structured_data_ref TEXT,
                rendered_artifact_ref TEXT,raw_artifact_ref TEXT,main_content_ref TEXT,browser_metadata TEXT
            );
            INSERT INTO page_snapshots VALUES (
                'S1','P1','MOBILE','2026-09-01T10:01:00Z',200,
                'https://example.test/a','https://example.test/a','index,follow,max-snippet:50','Produto',
                'artifacts/extraction/structured.json','artifacts/rendered/page.html',NULL,NULL,
                '{{"raw_http":{{"x_robots_tag":["nosnippet"]}},"render_succeeded":true}}'
            );
            CREATE TABLE rule_executions (
                rule_execution_id TEXT PRIMARY KEY,audit_id TEXT,rule_id TEXT,page_id TEXT,snapshot_id TEXT,
                device TEXT,result TEXT,observed_value TEXT,expected_condition TEXT,evidence_ids TEXT,error TEXT,executed_at TEXT
            );
            INSERT INTO rule_executions VALUES (
                'R1','{audit_id}','BR-GEO-011','P1','S1','MOBILE','{rule_result}',
                '{{"selector":"main"}}','indexable','["EV1"]',NULL,'2026-09-01T10:02:00Z'
            );
            CREATE TABLE evidence (
                evidence_id TEXT PRIMARY KEY,audit_id TEXT,page_id TEXT,snapshot_id TEXT,device TEXT,
                evidence_type TEXT,source TEXT,observed_value TEXT,artifact_reference TEXT,captured_at TEXT
            );
            INSERT INTO evidence VALUES ('EV1','{audit_id}','P1','S1','MOBILE','HTTP','fixture','{{}}',NULL,'2026-09-01T10:01:00Z');
            CREATE TABLE findings (
                finding_id TEXT PRIMARY KEY,audit_id TEXT,severity TEXT,rule_id TEXT,page_id TEXT,device TEXT,
                status TEXT,title TEXT,observed_value TEXT,evidence_ids TEXT,source TEXT,category TEXT
            );
            INSERT INTO findings VALUES (
                'F1','{audit_id}','HIGH','BR-GEO-011','P1','MOBILE','OPEN','Indexabilidade',
                '{{"selector":"main"}}','["EV1"]','deterministic','INDEXABILITY'
            );
            CREATE TABLE scores (
                score_id TEXT PRIMARY KEY,audit_id TEXT,dimension TEXT,device TEXT,value REAL,coverage REAL,
                confidence TEXT,consolidation_status TEXT,scoring_version TEXT,calculated_at TEXT
            );
            INSERT INTO scores VALUES (
                'SC1','{audit_id}','INDEXABILITY','MOBILE',90,1.0,'HIGH','CONSOLIDATED','SCORE-GEO-003','2026-09-01T10:03:00Z'
            );
            """
        )
        connection.commit()
    finally:
        connection.close()
    return workspace


def _sidecar_dataset(
    workspace: Path,
    *,
    dataset_id: str,
    source: str,
    period_start: str,
    period_end: str,
    impressions: float,
    collected_at: str,
) -> None:
    artifact = workspace / "artifacts" / "observability" / f"{dataset_id}.json"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text("{}", encoding="utf-8")
    dataset = Dataset(
        dataset_id=dataset_id,
        source_type=source,
        capture_method="TEST",
        period_start=period_start,
        period_end=period_end,
        artifact_path=artifact.relative_to(workspace).as_posix(),
        artifact_sha256="0" * 64,
        metadata={},
        collected_at=collected_at,
    )
    with ObservabilityStore(workspace) as store:
        store.replace_dataset_rows(
            dataset,
            search_rows=(
                {
                    "record_id": "R1",
                    "source": source,
                    "observed_date": period_end,
                    "query_text": "seguro",
                    "url": "https://example.test/a",
                    "device": "MOBILE",
                    "country": "BRA",
                    "surface": "web",
                    "clicks": impressions / 10,
                    "impressions": impressions,
                    "ctr": 0.1,
                    "position": 3,
                    "metadata": {},
                },
            ),
        )


def test_obs001_migration_preserves_rows_and_allows_reused_local_record_id() -> None:
    with tempfile.TemporaryDirectory() as directory:
        workspace = Path(directory) / "AUD-LEGACY"
        workspace.mkdir()
        (workspace / "audit.db").write_bytes(b"")
        connection = sqlite3.connect(workspace / "observability.db")
        try:
            connection.executescript(
                """
                CREATE TABLE datasets (
                    dataset_id TEXT PRIMARY KEY,format_version TEXT NOT NULL,source_type TEXT NOT NULL,
                    capture_method TEXT NOT NULL,period_start TEXT,period_end TEXT,artifact_path TEXT NOT NULL,
                    artifact_sha256 TEXT NOT NULL,metadata TEXT NOT NULL,collected_at TEXT NOT NULL
                );
                INSERT INTO datasets VALUES ('D1','RASAI-OBS-001','SRC','TEST','2026-08-01','2026-08-31','a.json','x','{}','2026-09-01T00:00:00Z');
                CREATE TABLE search_performance (
                    record_id TEXT PRIMARY KEY,dataset_id TEXT NOT NULL,source TEXT NOT NULL,observed_date TEXT,
                    query_text TEXT,url TEXT,device TEXT,country TEXT,surface TEXT,clicks REAL,impressions REAL,
                    ctr REAL,position REAL,metadata TEXT NOT NULL
                );
                INSERT INTO search_performance VALUES ('R1','D1','SRC','2026-08-31','q','https://example.test/a','MOBILE','BRA','web',1,10,.1,2,'{}');
                """
            )
            connection.commit()
        finally:
            connection.close()
        with ObservabilityStore(workspace) as store:
            pk = [
                str(row[1])
                for row in sorted(store.connection.execute("PRAGMA table_info(search_performance)"), key=lambda item: int(item[5]))
                if int(row[5]) > 0
            ]
            assert pk == ["dataset_id", "record_id"]
            assert len(store.search_rows()) == 1
            second = new_dataset(
                dataset_id="D2", source_type="SRC", capture_method="TEST",
                artifact_path="b.json", artifact_sha256="y", period_start="2026-09-01", period_end="2026-09-30",
            )
            store.replace_dataset_rows(second, search_rows=(
                {"record_id":"R1","source":"SRC","observed_date":"2026-09-30","query_text":"q","url":"https://example.test/a","device":"MOBILE","country":"BRA","surface":"web","clicks":2,"impressions":20,"ctr":.1,"position":2,"metadata":{}},
            ))
            assert len(store.search_rows()) == 2


def test_gsc_max_rows_is_true_cap_and_search_appearance_is_distinct_source() -> None:
    with tempfile.TemporaryDirectory() as directory:
        workspace = _audit_workspace(Path(directory), "AUD-GSC")
        requested_limits: list[int] = []

        def opener(request, timeout=0):
            payload = json.loads(request.data.decode("utf-8"))
            requested_limits.append(int(payload["rowLimit"]))
            dimensions = payload["dimensions"]
            rows = []
            for index in range(int(payload["rowLimit"])):
                mapping = {
                    "date": "2026-08-31", "query": f"q{index}", "page": "https://example.test/a",
                    "device": "mobile", "country": "bra", "searchAppearance": "AMP_ARTICLE",
                }
                rows.append({
                    "keys": [mapping[name] for name in dimensions],
                    "clicks": 1, "impressions": 10, "ctr": .1, "position": 2,
                })
            return _Response({"rows": rows})

        collect_search_analytics(
            audit_workspace=workspace, site_url="sc-domain:example.test", access_token="secret",
            start_date="2026-08-01", end_date="2026-08-31", max_rows=2, opener=opener,
        )
        collect_search_analytics(
            audit_workspace=workspace, site_url="sc-domain:example.test", access_token="secret",
            start_date="2026-08-01", end_date="2026-08-31",
            dimensions=("searchAppearance", "date", "page", "device", "country"),
            surface_dimension="searchAppearance", max_rows=1, opener=opener,
        )
        assert requested_limits[:2] == [2, 1]
        with ObservabilityStore(workspace) as store:
            rows = store.search_rows()
            assert len(rows) == 3
            assert {row["source"] for row in rows} == {
                "GOOGLE_SEARCH_CONSOLE_SEARCH_ANALYTICS",
                "GOOGLE_SEARCH_CONSOLE_SEARCH_APPEARANCE",
            }
            appearance = next(row for row in rows if row["source"] == "GOOGLE_SEARCH_CONSOLE_SEARCH_APPEARANCE")
            assert appearance["surface"] == "AMP_ARTICLE"


def test_gsc_sites_and_sitemaps_are_read_only_and_do_not_persist_token() -> None:
    with tempfile.TemporaryDirectory() as directory:
        workspace = _audit_workspace(Path(directory), "AUD-GSC-RES")
        responses = iter([
            {"siteEntry": [{"siteUrl": "sc-domain:example.test", "permissionLevel": "siteOwner"}]},
            {"sitemap": [{
                "path": "https://example.test/sitemap.xml", "lastSubmitted": "2026-08-30T00:00:00Z",
                "lastDownloaded": "2026-08-31T00:00:00Z", "isPending": False, "warnings": "0", "errors": "0",
                "contents": [{"type": "web", "submitted": "10", "indexed": "9"}],
            }]},
        ])

        def opener(request, timeout=0):
            return _Response(next(responses))

        collect_sites(audit_workspace=workspace, access_token="never-store-me", opener=opener)
        collect_sitemaps(
            audit_workspace=workspace, site_url="sc-domain:example.test",
            access_token="never-store-me", opener=opener,
        )
        with ObservabilityStore(workspace) as store:
            datasets = store.datasets()
            assert {row["source_type"] for row in datasets} >= {
                "GOOGLE_SEARCH_CONSOLE_PROPERTIES", "GOOGLE_SEARCH_CONSOLE_SITEMAPS"
            }
            for row in datasets:
                artifact = workspace / row["artifact_path"]
                assert "never-store-me" not in artifact.read_text(encoding="utf-8")
            sitemap_meta = next(
                json.loads(row["metadata"])
                for row in datasets if row["source_type"] == "GOOGLE_SEARCH_CONSOLE_SITEMAPS"
            )
            assert sitemap_meta["indexed_field_policy"] == "DEPRECATED_FIELD_NOT_USED"
            assert sitemap_meta["sitemaps"][0]["submitted"] == [{"submitted": "10", "type": "web"}]


def test_google_genai_import_keeps_missing_metrics_unavailable_and_surfaces_separate() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        workspace = _audit_workspace(root, "AUD-GENAI")
        source = root / "genai.csv"
        source.write_text(
            "Date,Page,Device,Country,Impressions\n"
            "2026-08-30,https://example.test/a,mobile,BRA,100\n"
            "2026-08-31,https://example.test/a,mobile,BRA,~\n",
            encoding="utf-8",
        )
        search_id = import_google_genai_performance_csv(audit_workspace=workspace, path=source, surface="search")
        discover_id = import_google_genai_performance_csv(audit_workspace=workspace, path=source, surface="discover")
        control_id = persist_google_genai_control(
            audit_workspace=workspace, state="EXCLUDE", observed_at="2026-09-01T10:00:00Z"
        )
        assert len({search_id, discover_id, control_id}) == 3
        with ObservabilityStore(workspace) as store:
            rows = store.search_rows()
            assert {row["source"] for row in rows} == {
                "GOOGLE_SEARCH_CONSOLE_GENERATIVE_AI_PERFORMANCE_EXPORT_SEARCH",
                "GOOGLE_SEARCH_CONSOLE_GENERATIVE_AI_PERFORMANCE_EXPORT_DISCOVER",
            }
            assert all(row["clicks"] is None and row["ctr"] is None and row["position"] is None for row in rows)
            suppressed = [json.loads(row["metadata"])["suppressed_or_rounded_token"] for row in rows]
            assert suppressed.count(True) == 2
        signals, _datasets = _observed_snapshot(workspace)
        genai_keys = [key for key in signals if "GENERATIVE_AI" in key]
        assert any(key.endswith("|impressions") for key in genai_keys)
        assert not any(key.endswith("|clicks") or key.endswith("|ctr") for key in genai_keys)


def test_change_impact_uses_latest_dataset_without_double_sum_and_requires_temporal_overlap() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        baseline = _audit_workspace(root, "AUD-BASE", rule_result="PASS")
        current = _audit_workspace(root, "AUD-CURRENT", rule_result="FAIL")
        source = "GOOGLE_SEARCH_CONSOLE_SEARCH_ANALYTICS"
        _sidecar_dataset(
            baseline, dataset_id="OLD", source=source, period_start="2026-07-01", period_end="2026-07-31",
            impressions=900, collected_at="2026-08-01T00:00:00Z",
        )
        _sidecar_dataset(
            baseline, dataset_id="LATEST", source=source, period_start="2026-08-01", period_end="2026-08-31",
            impressions=1000, collected_at="2026-09-01T00:00:00Z",
        )
        _sidecar_dataset(
            current, dataset_id="CURRENT", source=source, period_start="2026-09-01", period_end="2026-09-30",
            impressions=500, collected_at="2026-10-01T00:00:00Z",
        )
        signals, selected = _observed_snapshot(baseline)
        impression = next(value for key, value in signals.items() if key.endswith("|impressions"))
        assert impression["value"] == 1000
        assert selected[source]["dataset_id"] == "LATEST"
        result = compare_audits(baseline, current)
        impact = analyze_change_impact(result)
        window = next(item for item in impact.window_comparability if item["source"] == source)
        assert window["status"] == "NON_OVERLAPPING"
        assert impact.associations == ()


def test_release_gate_excludes_non_deterministic_families_until_opt_in() -> None:
    snapshot = AuditSnapshot(
        audit_id="AUD", workspace=Path("."), project_name="P", event_time="2026-09-01", status="COMPLETED",
        completion_status="COMPLETE", auditor_version="1", ruleset_version="1", scoring_versions=("SCORE-GEO-003",),
        domains=("example.test",), devices=("MOBILE",), urls=("https://example.test/a",), signals={},
    )
    perf = ChangeEvent(
        key="PERF", domain="PERFORMANCE", label="Performance", status="REGRESSED", before=.9, after=.7,
        severity="HIGH", material=True, delta=-.2,
    )
    aggregate = ChangeEvent(
        key="FIND", domain="FINDINGS", label="HIGH findings", status="REGRESSED", before=1, after=2,
        severity="HIGH", material=True, delta=1,
    )
    result = ComparisonResult(snapshot, snapshot, True, (), (perf, aggregate), {"REGRESSED": 2}, {"REGRESSED": 2})
    assert evaluate_release_gate(result).passed is True
    enabled = evaluate_release_gate(result, GatePolicy(include_performance=True, include_finding_aggregates=True))
    assert enabled.passed is False
    assert {item.domain for item in enabled.blocking_events} == {"PERFORMANCE", "FINDINGS"}


def test_quality_report_content_controls_and_freshness_use_persisted_audit_date() -> None:
    with tempfile.TemporaryDirectory() as directory:
        workspace = _audit_workspace(
            Path(directory), "AUD-QUALITY", rule_result="FAIL", structured_future_date=True,
        )
        controls = analyze_content_controls(workspace)
        assert len(controls) == 1
        assert controls[0].nosnippet is True
        assert controls[0].max_snippet == 50
        assert controls[0].data_nosnippet_count == 1
        assert controls[0].interpretation == "DIRECT_SNIPPET_USE_RESTRICTED"
        diagnostics = analyze_workspace(workspace)
        future = next(item for item in diagnostics.diagnostics if item.code == "FRESHNESS-FUTURE-DATE")
        assert future.evidence and future.evidence["analysis_date"] == "2026-09-01"
        quality = analyze_quality(workspace)
        assert quality.finding_assessments
        assert quality.coverage_map
        assert any(item.code == "AUDIT-DB-INTEGRITY" and item.status == "PASS" for item in quality.health_checks)
        path = write_quality_report(workspace)
        html = path.read_text(encoding="utf-8")
        assert "Audit Health" in html
        assert "Evidence Confidence" in html
        assert "Coverage Map" in html
        assert "Search & AI content controls" in html
        assert "quality.html" in (workspace / "report" / "index.html").read_text(encoding="utf-8")


def test_fix_verification_requires_persisted_rule_transition() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        baseline = _audit_workspace(root, "AUD-FIX-BASE", rule_result="FAIL")
        current = _audit_workspace(root, "AUD-FIX-CURRENT", rule_result="PASS")
        bundle = verify_fixes(baseline, current, rule_id="BR-GEO-011")
        assert bundle.counts == {"FIXED": 1}
        assert bundle.items[0].status == "FIXED"
