from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from rasai.search_intelligence.competitive_persistence import analysis_payload
from rasai.search_intelligence.competitive_runtime import execute_competitive_intelligence
from rasai.search_intelligence.content import PublicWebFetcher
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
    }
