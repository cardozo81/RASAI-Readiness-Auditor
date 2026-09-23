from __future__ import annotations

from dataclasses import replace
import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace

from rasai.search_intelligence.competitive_persistence import analysis_payload
from rasai.search_intelligence import competitive_runtime
from rasai.search_intelligence.competitive_runtime import execute_competitive_intelligence
from rasai.search_intelligence.content import (
    ContentFetchStatus,
    PublicWebFetcher,
    _FetchedDocument,
)
from rasai.search_intelligence.models import (
    DomainMatchStatus,
    QueryOrigin,
    SerpDataMode,
    SerpObservation,
    SerpObservationStatus,
    SerpQueryRequest,
    SerpResult,
)
from rasai.search_intelligence.runtime import SearchExecution, SearchIntelligenceResult


def _search_execution() -> SearchExecution:
    observation = SerpObservation(
        observation_id="OBS-POLICY",
        run_id="RUN-POLICY",
        query="seguro de vida",
        query_origin=QueryOrigin.MANUAL,
        engine="google",
        country="BR",
        region=None,
        language="pt-BR",
        device="mobile",
        collected_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
        provider="fixture",
        provider_request_id=None,
        requested_depth=10,
        result_count=1,
        results=(SerpResult(1, "example.test", "https://example.test/"),),
        data_mode=SerpDataMode.FIXTURE,
        status=SerpObservationStatus.OBSERVED,
    )
    request = SerpQueryRequest(
        query="seguro de vida",
        domain_of_interest="example.test",
        depth=10,
    )
    result = SearchIntelligenceResult(
        request=request,
        observation=observation,
        domain_status=DomainMatchStatus.FOUND,
        customer_position=1,
    )
    return SearchExecution(
        mode="fixture",
        provider="fixture",
        results=(result,),
        projected_http_request_ceiling=0,
        actual_http_requests=0,
        persisted=False,
    )


def test_analysis_payload_accepts_additive_acquisition_policy() -> None:
    from rasai.search_intelligence.competitive import select_competitive_candidates
    from rasai.search_intelligence.content import CompetitiveContentAnalysis

    selection = select_competitive_candidates(
        _search_execution().results[0],
        max_pages=2,
    )
    analysis = CompetitiveContentAnalysis(
        selection=selection,
        customer_page=None,
        competitor_pages=(),
        gaps=(),
        comparison_status="CONTENT_COMPARISON_DISABLED",
    )
    payload = analysis_payload(
        analysis,
        acquisition_policy={
            "content_enabled": False,
            "max_competitor_pages": 2,
            "timeout_seconds": None,
            "max_bytes": None,
            "max_redirects": None,
        },
    )
    assert payload["acquisition_policy"]["max_competitor_pages"] == 2
    assert payload["acquisition_policy"]["content_enabled"] is False


def test_competitive_runtime_persists_effective_fetch_policy(tmp_path: Path) -> None:
    database = tmp_path / "audit.db"
    connection = sqlite3.connect(database)
    try:
        connection.executescript(
            """
            CREATE TABLE audits(audit_id TEXT PRIMARY KEY,created_at TEXT NOT NULL);
            CREATE TABLE serp_observations(
                observation_id TEXT PRIMARY KEY,audit_id TEXT
            );
            INSERT INTO audits VALUES ('AUD-POLICY','2026-09-18T00:00:00Z');
            INSERT INTO serp_observations VALUES ('OBS-POLICY','AUD-POLICY');
            """
        )
        connection.commit()
    finally:
        connection.close()

    fetcher = PublicWebFetcher(
        timeout_seconds=12.5,
        max_redirects=2,
        max_bytes=1_500_000,
        resolver=lambda host, port: ("93.184.216.34",),
        opener=lambda *args, **kwargs: (_ for _ in ()).throw(OSError("fixture no network")),
    )
    execute_competitive_intelligence(
        _search_execution(),
        content_enabled=True,
        max_competitor_pages=3,
        workspace_root=tmp_path,
        fetcher=fetcher,
    )
    artifact = tmp_path / "artifacts" / "search-intelligence" / "competitive" / "OBS-POLICY.json"
    payload = json.loads(artifact.read_text(encoding="utf-8"))
    assert payload["acquisition_policy"] == {
        "content_enabled": True,
        "max_competitor_pages": 3,
        "timeout_seconds": 12.5,
        "max_bytes": 1_500_000,
        "max_redirects": 2,
        "customer_source": "PUBLIC_WEB_HTTP",
    }

def test_multi_query_content_comparison_reuses_same_audited_customer_url(monkeypatch) -> None:
    base = _search_execution()
    first = base.results[0]
    second = replace(
        first,
        request=replace(first.request, query="cotacao seguro"),
        observation=replace(
            first.observation,
            observation_id="OBS-POLICY-2",
            query="cotacao seguro",
        ),
    )
    execution = replace(base, results=(first, second))
    seen: list[tuple[str, str | None]] = []

    def fake_analysis(search_result, *, customer_url, max_competitor_pages, fetcher, customer_page_override=None):
        from rasai.search_intelligence.competitive import select_competitive_candidates
        from rasai.search_intelligence.content import CompetitiveContentAnalysis

        seen.append((search_result.request.query, customer_url))
        return CompetitiveContentAnalysis(
            selection=select_competitive_candidates(
                search_result,
                max_pages=max_competitor_pages,
            ),
            customer_page=None,
            competitor_pages=(),
            gaps=(),
            comparison_status="NO_ELIGIBLE_COMPETITOR_CANDIDATES",
        )

    monkeypatch.setattr(competitive_runtime, "analyze_competitive_content", fake_analysis)
    result = execute_competitive_intelligence(
        execution,
        content_enabled=True,
        customer_url="https://example.test/customer",
        max_competitor_pages=3,
    )

    assert len(result.analyses) == 2
    assert seen == [
        ("seguro de vida", "https://example.test/customer"),
        ("cotacao seguro", "https://example.test/customer"),
    ]


def test_competitive_comparison_summary_marks_incomplete_requested_query(tmp_path: Path) -> None:
    from rasai.search_audit_runtime import _competitive_comparison_summary

    database = tmp_path / "audit.db"
    connection = sqlite3.connect(database)
    try:
        connection.execute(
            "CREATE TABLE serp_competitive_analyses(audit_id TEXT, comparison_status TEXT)"
        )
        connection.executemany(
            "INSERT INTO serp_competitive_analyses VALUES (?,?)",
            [
                ("AUD", "CONSOLIDATED"),
                ("AUD", "NO_ELIGIBLE_COMPETITOR_CANDIDATES"),
                ("AUD", "CUSTOMER_CONTENT_UNAVAILABLE"),
            ],
        )
        connection.commit()
    finally:
        connection.close()

    summary = _competitive_comparison_summary(
        SimpleNamespace(database=database),
        "AUD",
        expected_observations=3,
    )
    assert summary["complete"] is False
    assert summary["incomplete_statuses"] == ["CUSTOMER_CONTENT_UNAVAILABLE"]

def test_competitive_customer_reuses_rendered_audit_html_without_refetching_customer(tmp_path: Path) -> None:
    base = _search_execution()
    original = base.results[0]
    observation = replace(
        original.observation,
        result_count=2,
        results=(
            SerpResult(1, "leader.example", "https://leader.example/seguro"),
            SerpResult(2, "example.test", "https://example.test/"),
        ),
    )
    result = replace(
        original,
        observation=observation,
        customer_position=2,
    )
    execution = replace(base, results=(result,))

    class Fetcher:
        timeout_seconds = 10.0
        max_redirects = 2
        max_bytes = 500000

        def __init__(self):
            self.urls = []

        def fetch(self, url):
            self.urls.append(url)
            html = b"<html><title>Seguro de vida lider</title><h1>Seguro de vida</h1><p>cobertura ampla</p></html>"
            return _FetchedDocument(
                requested_url=url,
                final_url=url,
                http_status=200,
                headers={"content-type": "text/html; charset=utf-8"},
                body=html,
                redirects=(),
                status=ContentFetchStatus.OBSERVED,
            )

        @property
        def requests_used(self):
            return len(self.urls)

    fetcher = Fetcher()
    rendered = (
        b"<html><head><title>Seguro de vida Bradesco</title></head><body>"
        b"<h1>Seguro de vida</h1><h2>Coberturas</h2>"
        b"<p>Seguro de vida com coberturas, assistencias e protecao para sua familia.</p>"
        b"</body></html>"
    )
    out = execute_competitive_intelligence(
        execution,
        content_enabled=True,
        customer_url="https://example.test/",
        max_competitor_pages=1,
        workspace_root=None,
        fetcher=fetcher,
        customer_rendered_html=rendered,
        customer_rendered_final_url="https://example.test/",
    )

    analysis = out.analyses[0]
    assert analysis.customer_page is not None
    assert analysis.customer_page.status is ContentFetchStatus.OBSERVED
    assert analysis.customer_page.word_count > 2
    assert analysis.customer_page.headings == ("Seguro de vida", "Coberturas")
    assert fetcher.urls == ["https://leader.example/seguro"]


def test_search_audit_selects_matching_rendered_customer_artifact(tmp_path: Path) -> None:
    from rasai.search_audit_runtime import _rendered_customer_artifact

    database = tmp_path / "audit.db"
    rendered = tmp_path / "artifacts" / "rendered.html"
    rendered.parent.mkdir(parents=True)
    rendered.write_text("<html><h1>Cliente</h1></html>", encoding="utf-8")
    connection = sqlite3.connect(database)
    try:
        connection.executescript(
            """
            CREATE TABLE pages(page_id TEXT PRIMARY KEY,audit_id TEXT,normalized_url TEXT);
            CREATE TABLE page_snapshots(
                snapshot_id TEXT PRIMARY KEY,page_id TEXT,device TEXT,captured_at TEXT,
                rendered_artifact_ref TEXT
            );
            """
        )
        connection.execute(
            "INSERT INTO pages VALUES (?,?,?)",
            ("P1", "AUD", "https://example.test/"),
        )
        connection.execute(
            "INSERT INTO page_snapshots VALUES (?,?,?,?,?)",
            ("S1", "P1", "MOBILE", "2026-09-18T20:00:00+00:00", "artifacts/rendered.html"),
        )
        connection.commit()
    finally:
        connection.close()

    workspace = SimpleNamespace(root=tmp_path, database=database)
    assert _rendered_customer_artifact(
        workspace,
        "AUD",
        "https://example.test/",
        "mobile",
    ) == rendered.resolve()
