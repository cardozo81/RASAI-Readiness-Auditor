"""#129: provider cache provenance and explicit, bounded freshness override."""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest

from rasai.search_intelligence.config import SerpRuntimeConfig
from rasai.search_intelligence.evidence import FilesystemSerpEvidenceSink
from rasai.search_intelligence.persistence import SerpObservationRepository
from rasai.search_intelligence.providers.serpapi import SerpApiProvider
from rasai.search_intelligence.service import SearchIntelligenceService, analyze_observation
from tests.test_serp import FakeResponse, request


def _workspace(tmp_path: Path) -> tuple[Path, SerpObservationRepository]:
    root = tmp_path
    (root / "artifacts").mkdir()
    with sqlite3.connect(root / "audit.db") as db:
        db.execute("CREATE TABLE audits (audit_id TEXT PRIMARY KEY, created_at TEXT)")
        db.execute(
            "INSERT INTO audits VALUES (?,?)",
            ("AUD-CACHE", "2026-09-30T00:00:00+00:00"),
        )
    return root, SerpObservationRepository.from_workspace(root)


def _serp_response() -> bytes:
    return json.dumps(
        {
            "search_metadata": {
                "id": "same-provider-response",
                "created_at": "2026-09-30 14:48:24 UTC",
            },
            "organic_results": [
                {"position": index, "link": f"https://leader-{index}.example/"}
                for index in range(1, 10)
            ],
            "serpapi_pagination": {"current": 1},
        }
    ).encode()


def test_identical_live_responses_have_separate_ingest_and_probable_external_cache(tmp_path):
    root, repo = _workspace(tmp_path)
    calls: list[dict[str, list[str]]] = []
    def opener(req, timeout):
        calls.append(parse_qs(urlsplit(req.full_url).query))
        return FakeResponse(_serp_response())

    provider = SerpApiProvider(api_key="SECRET", retries=0, min_interval_seconds=0, opener=opener)
    service = SearchIntelligenceService(
        provider=provider, max_depth=20,
        evidence_sink=FilesystemSerpEvidenceSink(root, root / "artifacts"),
        repository=repo,
    )
    try:
        first = service.observe(request(depth=20))
        second = service.observe(request(depth=20))
        quality = second.observation.quality_metadata
        assert len(calls) == 2
        assert all("no_cache" not in call for call in calls)
        assert first.domain_status.value == "UNAVAILABLE"
        assert second.domain_status.value == "UNAVAILABLE"
        assert "encerrou a paginação" in first.error_message
        assert "nove" not in first.error_message  # exact observed numeric count, not inferred
        assert "9" in first.error_message and "20" in first.error_message
        assert second.observation.provider_request_id == first.observation.provider_request_id
        assert second.observation.raw_evidence_sha256 == first.observation.raw_evidence_sha256
        assert quality["provider_created_at"] == "2026-09-30T14:48:24+00:00"
        assert quality["rasai_response_received_at"]
        assert quality["rasai_persisted_at"]
        assert quality["provider_response_repeat_status"] == "SAME_PROVIDER_ID_AND_RAW_SHA"
        assert quality["provider_cache_assessment"] == "POSSIBLE_PROVIDER_CACHE"
        assert quality["previous_observation_id"] == first.observation.observation_id
        assert quality["pagination_ended_before_requested_depth"] is True
        assert quality["normalization_incomplete_for_requested_depth"] is False

        rows = repo.connection.execute(
            "SELECT o.observation_id,o.collected_at,o.quality_metadata,p.temporal_mode,"
            "p.captured_at,p.reuse_reason FROM serp_observations o "
            "JOIN serp_evidence_provenance p USING(observation_id) ORDER BY o.rowid"
        ).fetchall()
        assert len(rows) == 2
        assert all(row["collected_at"] == "2026-09-30T14:48:24+00:00" for row in rows)
        assert rows[0]["captured_at"] and rows[1]["captured_at"]
        assert all(row["temporal_mode"] == "LIVE_RECOLLECTION" for row in rows)
        assert all(row["reuse_reason"] is None for row in rows)
        assert json.loads(rows[1]["quality_metadata"])["provider_cache_assessment"] == "POSSIBLE_PROVIDER_CACHE"
    finally:
        repo.close()


def test_different_provider_payload_does_not_flag_probable_cache(tmp_path):
    root, repo = _workspace(tmp_path)
    responses = [_serp_response(), json.dumps({
        "search_metadata": {"id": "fresh-id", "created_at": "2026-09-30 15:01:00 UTC"},
        "organic_results": [{"position": 1, "link": "https://different.example/"}],
    }).encode()]
    def opener(_req, timeout):
        return FakeResponse(responses.pop(0))
    provider = SerpApiProvider(api_key="KEY", retries=0, min_interval_seconds=0, opener=opener)
    service = SearchIntelligenceService(
        provider=provider, max_depth=20,
        evidence_sink=FilesystemSerpEvidenceSink(root, root / "artifacts"),
        repository=repo,
    )
    try:
        service.observe(request(depth=20))
        later = service.observe(request(depth=20))
        assert "provider_response_repeat_status" not in later.observation.quality_metadata
    finally:
        repo.close()


def test_force_refresh_requires_explicit_opt_in_and_stays_bounded():
    from rasai.search_intelligence.budget import RequestBudget
    calls = []
    budget = RequestBudget(1)
    def opener(req, timeout):
        calls.append(parse_qs(urlsplit(req.full_url).query))
        return FakeResponse(_serp_response())

    provider = SerpApiProvider(
        api_key="KEY", no_cache=True, budget=budget, retries=0,
        min_interval_seconds=0, opener=opener,
    )
    observed = provider.observe(request(depth=20))
    assert observed.observation.quality_metadata["provider_cache_policy"] == "FORCE_REFRESH"
    assert observed.observation.quality_metadata["pages_collected"] == 1
    assert observed.observation.quality_metadata["requested_depth_complete"] is False
    assert budget.used == 1
    assert calls[0]["no_cache"] == ["true"]
    with pytest.raises(ValueError, match="force_refresh"):
        SerpRuntimeConfig(mode="disabled", force_refresh=True).validate()
    with pytest.raises(ValueError, match="force_refresh"):
        SerpRuntimeConfig(mode="live", provider="zenserp", force_refresh=True).validate()
    assert SerpRuntimeConfig(mode="live", provider="serpapi", force_refresh=True).validate().force_refresh


def test_rpr_freshness_override_only_from_explicit_current_session(monkeypatch):
    from rasai.selective_optional_reprocess import _search_runtime_config
    item = SimpleNamespace(configuration={"mode": "live", "provider": "serpapi"})
    monkeypatch.delenv("RASAI_SERP_NO_CACHE_RPR", raising=False)
    assert _search_runtime_config(item).force_refresh is False
    monkeypatch.setenv("RASAI_SERP_NO_CACHE_RPR", "true")
    assert _search_runtime_config(item).force_refresh is True
    monkeypatch.setenv("RASAI_SERP_NO_CACHE_RPR", "sometimes")
    with pytest.raises(ValueError, match="RASAI_SERP_NO_CACHE_RPR"):
        _search_runtime_config(item)


def test_provider_completeness_does_not_confuse_normalization_with_early_pagination():
    raw = json.dumps({
        "search_metadata": {"id": "only-page"},
        "organic_results": [
            {"position": 1, "link": "https://valid.example/"},
            {"position": 2, "link": "javascript:invalid"},
        ],
        "serpapi_pagination": {"next": "provider-next"},
    }).encode()
    responses = [raw, json.dumps({
        "organic_results": [{"position": 1, "link": "https://another.example/"}],
    }).encode()]
    provider = SerpApiProvider(
        api_key="KEY", retries=0, min_interval_seconds=0,
        opener=lambda req, timeout: FakeResponse(responses.pop(0)),
    )
    result = provider.observe(request(depth=20)).observation
    quality = result.quality_metadata
    assert quality["dropped_results"] == 1
    assert quality["pagination_ended_before_requested_depth"] is False
    assert quality["normalization_incomplete_for_requested_depth"] is True
