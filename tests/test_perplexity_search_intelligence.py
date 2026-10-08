from __future__ import annotations

import json
import sqlite3

import pytest

from rasai.ai_native_usage import PERPLEXITY_SEARCH_REQUEST
from rasai.catalog_report_integrations import _AI_USAGE_DETAILS
from rasai.catalog_report_model import _AI_PURPOSE_LABELS
from rasai.persistence import AuditWorkspace
from rasai.provider_registry import provider_registrations
from rasai.search_intelligence.perplexity import (
    API_KEY_ENV,
    ENDPOINT,
    PerplexityHttpResponse,
    PerplexityTimeoutError,
    execute_perplexity_search,
    humanized_perplexity_summary,
    perplexity_configuration_status,
)


AUDIT_ID = "AUD-PERPLEXITY-1"


def _workspace(tmp_path) -> AuditWorkspace:
    root = tmp_path / AUDIT_ID
    root.mkdir()
    (root / "artifacts").mkdir()
    database = root / "audit.db"
    connection = sqlite3.connect(database)
    try:
        connection.executescript(
            """
            PRAGMA foreign_keys=ON;
            CREATE TABLE audits(audit_id TEXT PRIMARY KEY);
            CREATE TABLE pages(
                page_id TEXT PRIMARY KEY,
                audit_id TEXT
            );
            CREATE TABLE page_snapshots(
                snapshot_id TEXT PRIMARY KEY,
                page_id TEXT
            );
            CREATE TABLE scores(
                score_id TEXT PRIMARY KEY,
                audit_id TEXT,
                score REAL
            );
            INSERT INTO audits(audit_id) VALUES ('AUD-PERPLEXITY-1');
            INSERT INTO scores(score_id,audit_id,score)
            VALUES ('SCORE-1','AUD-PERPLEXITY-1',87.5);
            """
        )
        connection.commit()
    finally:
        connection.close()
    return AuditWorkspace.open(root)


def _success_transport(expected_search_type: str = "web"):
    def transport(endpoint, headers, body, timeout):
        assert endpoint == ENDPOINT
        assert headers["Authorization"] == "Bearer TEST_ONLY_PERPLEXITY_KEY"
        assert "TEST_ONLY_PERPLEXITY_KEY" not in body.decode("utf-8")
        payload = json.loads(body)
        assert payload["search_type"] == expected_search_type
        assert timeout > 0
        return PerplexityHttpResponse(
            status=200,
            headers={"x-request-id": "REQ-PX-1"},
            body=json.dumps(
                {
                    "id": "PX-RESPONSE-1",
                    "results": [
                        {
                            "title": "Fonte A",
                            "url": "https://example.com/a",
                            "snippet": "Trecho A",
                            "date": "2026-10-01",
                            "last_updated": "2026-10-03",
                            "extra": "kept-as-metadata",
                        },
                        {
                            "title": "Fonte B",
                            "url": "https://example.org/b",
                            "snippet": "",
                            "date": None,
                            "last_updated": "2026-10-02",
                        },
                    ],
                    "server_time": None,
                }
            ).encode("utf-8"),
        )

    return transport


def _db_rows(workspace: AuditWorkspace, sql: str):
    connection = sqlite3.connect(workspace.database)
    connection.row_factory = sqlite3.Row
    try:
        return connection.execute(sql).fetchall()
    finally:
        connection.close()


def test_perplexity_configuration_status_never_returns_secret() -> None:
    status = perplexity_configuration_status(
        {API_KEY_ENV: "TEST_ONLY_PERPLEXITY_KEY"}
    )
    assert status["configured"] is True
    assert status["secret_env"] == API_KEY_ENV
    assert "TEST_ONLY_PERPLEXITY_KEY" not in repr(status)


def test_web_search_persists_external_provenance_and_native_request_pricing(tmp_path) -> None:
    workspace = _workspace(tmp_path)
    run = execute_perplexity_search(
        workspace,
        audit_id=AUDIT_ID,
        query="RASAi search readiness",
        search_type="web",
        env={API_KEY_ENV: "TEST_ONLY_PERPLEXITY_KEY"},
        transport=_success_transport("web"),
    )

    assert run.status == "SUCCESS"
    assert run.provider_response_id == "PX-RESPONSE-1"
    assert len(run.sources) == 2
    assert run.native_usage[0].unit == PERPLEXITY_SEARCH_REQUEST
    assert run.native_usage[0].quantity == pytest.approx(1.0)
    assert run.native_usage[0].billable is True
    assert run.pricing.pricing_model == "PER_REQUEST"
    assert run.pricing.estimated_cost == pytest.approx(0.005)
    assert run.pricing.currency == "USD"

    attempts = _db_rows(
        workspace,
        "SELECT * FROM ai_provider_attempts WHERE provider='PERPLEXITY'",
    )
    assert len(attempts) == 1
    attempt = attempts[0]
    assert attempt["surface"] == "SEARCH_API"
    assert attempt["input_tokens"] is None
    assert attempt["output_tokens"] is None
    assert attempt["total_tokens"] is None
    assert attempt["operation"] == "SEARCH_INTELLIGENCE"

    native = _db_rows(
        workspace,
        "SELECT * FROM ai_provider_native_usage WHERE provider='PERPLEXITY'",
    )
    assert len(native) == 1
    assert native[0]["native_usage_unit"] == PERPLEXITY_SEARCH_REQUEST
    assert native[0]["native_usage_quantity"] == pytest.approx(1.0)
    assert native[0]["estimated_cost"] == pytest.approx(0.005)
    assert native[0]["pricing_model"] == "PER_REQUEST"
    assert native[0]["pricing_rule_id"] == "perplexity-search-web-realtime"

    provenance = _db_rows(workspace, "SELECT * FROM perplexity_search_runs")
    sources = _db_rows(
        workspace,
        "SELECT * FROM perplexity_search_sources ORDER BY position",
    )
    assert len(provenance) == 1
    assert provenance[0]["provenance_kind"] == "EXTERNAL_SEARCH_INTELLIGENCE"
    assert provenance[0]["citation_urls_json"] == json.dumps(
        ["https://example.com/a", "https://example.org/b"],
        ensure_ascii=False,
    )
    assert len(sources) == 2
    assert json.loads(sources[0]["source_metadata_json"])["extra"] == "kept-as-metadata"

    score = _db_rows(workspace, "SELECT score FROM scores WHERE score_id='SCORE-1'")
    assert score[0]["score"] == pytest.approx(87.5)

    raw_db = workspace.database.read_bytes()
    assert b"TEST_ONLY_PERPLEXITY_KEY" not in raw_db


def test_fast_search_uses_fast_price(tmp_path) -> None:
    workspace = _workspace(tmp_path)
    run = execute_perplexity_search(
        workspace,
        audit_id=AUDIT_ID,
        query="fast query",
        search_type="fast",
        env={API_KEY_ENV: "TEST_ONLY_PERPLEXITY_KEY"},
        transport=_success_transport("fast"),
    )
    assert run.pricing.estimated_cost == pytest.approx(0.001)
    assert run.pricing.pricing_rule_id == "perplexity-search-fast-realtime"


def test_multi_query_counts_one_billable_request_not_query_count(tmp_path) -> None:
    workspace = _workspace(tmp_path)
    seen = {}

    def transport(endpoint, headers, body, timeout):
        payload = json.loads(body)
        seen["query"] = payload["query"]
        return PerplexityHttpResponse(
            200,
            {},
            b'{"id":"PX-MULTI","results":[]}',
        )

    run = execute_perplexity_search(
        workspace,
        audit_id=AUDIT_ID,
        query=("q1", "q2", "q3"),
        env={API_KEY_ENV: "TEST_ONLY_PERPLEXITY_KEY"},
        transport=transport,
    )

    assert seen["query"] == ["q1", "q2", "q3"]
    assert len(run.queries) == 3
    assert run.native_usage[0].quantity == pytest.approx(1.0)
    assert run.pricing.estimated_cost == pytest.approx(0.005)


def test_rate_limit_is_contained_and_known_non_billable(tmp_path) -> None:
    workspace = _workspace(tmp_path)

    def transport(endpoint, headers, body, timeout):
        return PerplexityHttpResponse(
            429,
            {"Retry-After": "2"},
            b'{"error":{"type":"rate_limit","code":"too_many_requests"}}',
        )

    run = execute_perplexity_search(
        workspace,
        audit_id=AUDIT_ID,
        query="limited query",
        env={API_KEY_ENV: "TEST_ONLY_PERPLEXITY_KEY"},
        transport=transport,
    )

    assert run.status == "RATE_LIMIT_ERROR"
    assert run.diagnostic is not None
    assert run.diagnostic.retry_after_seconds == pytest.approx(2.0)
    assert run.native_usage[0].billable is False
    assert run.pricing.estimated_cost == pytest.approx(0.0)


def test_timeout_preserves_request_with_unknown_billability_and_unpriced_cost(tmp_path) -> None:
    workspace = _workspace(tmp_path)

    def transport(endpoint, headers, body, timeout):
        raise PerplexityTimeoutError("timeout")

    run = execute_perplexity_search(
        workspace,
        audit_id=AUDIT_ID,
        query="timeout query",
        env={API_KEY_ENV: "TEST_ONLY_PERPLEXITY_KEY"},
        transport=transport,
    )

    assert run.status == "TIMEOUT_ERROR"
    assert run.native_usage[0].billable is None
    assert run.pricing.estimated_cost is None
    native = _db_rows(
        workspace,
        "SELECT billable,estimated_cost FROM ai_provider_native_usage",
    )
    assert native[0]["billable"] is None
    assert native[0]["estimated_cost"] is None


def test_malformed_success_is_billed_but_classified_as_invalid_response(tmp_path) -> None:
    workspace = _workspace(tmp_path)

    def transport(endpoint, headers, body, timeout):
        return PerplexityHttpResponse(200, {}, b'{"id":"PX-BAD","unexpected":true}')

    run = execute_perplexity_search(
        workspace,
        audit_id=AUDIT_ID,
        query="malformed response",
        env={API_KEY_ENV: "TEST_ONLY_PERPLEXITY_KEY"},
        transport=transport,
    )

    assert run.status == "INVALID_RESPONSE"
    assert run.native_usage[0].billable is True
    assert run.pricing.estimated_cost == pytest.approx(0.005)
    assert run.sources == ()


def test_missing_key_is_persisted_as_not_configured_without_fake_request(tmp_path) -> None:
    workspace = _workspace(tmp_path)
    run = execute_perplexity_search(
        workspace,
        audit_id=AUDIT_ID,
        query="no key",
        env={},
    )

    assert run.status == "NOT_CONFIGURED"
    assert run.native_usage == ()
    assert run.attempt_id is None
    tables = _db_rows(
        workspace,
        "SELECT name FROM sqlite_master WHERE type='table' AND name='ai_provider_attempts'",
    )
    assert tables == []
    rows = _db_rows(workspace, "SELECT * FROM perplexity_search_runs")
    assert rows[0]["status"] == "NOT_CONFIGURED"
    assert rows[0]["native_usage_quantity"] is None


def test_summary_is_humanized_and_perplexity_does_not_enter_canonical_ai_auto_registry(tmp_path) -> None:
    workspace = _workspace(tmp_path)
    run = execute_perplexity_search(
        workspace,
        audit_id=AUDIT_ID,
        query="summary",
        env={API_KEY_ENV: "TEST_ONLY_PERPLEXITY_KEY"},
        transport=_success_transport("web"),
    )
    summary = humanized_perplexity_summary(run)
    assert summary["origem"] == "Perplexity Search API - pesquisa externa"
    assert "não é evidência determinística" in summary["provenance"]
    assert summary["modo"] == "Busca web"
    assert summary["requests"] == pytest.approx(1.0)

    canonical = {item.provider_name for item in provider_registrations()}
    assert "PERPLEXITY" not in canonical



def test_report_contract_labels_external_research_without_deterministic_claims() -> None:
    purpose, catalog = _AI_PURPOSE_LABELS["RASAI-PERPLEXITY-SEARCH-1"]
    assert purpose == "Pesquisa externa Perplexity"
    assert catalog == "CAT-05"
    detail = _AI_USAGE_DETAILS["RASAI-PERPLEXITY-SEARCH-1"]
    assert "Pesquisa externa" in detail[0]
    assert "não substitui SERP" in detail[2]
    assert "não altera scoring" in detail[2]


@pytest.mark.parametrize("status", [401, 402, 403, 429, 500])
def test_http_errors_are_contained_and_not_billed(tmp_path, status: int) -> None:
    workspace = _workspace(tmp_path)

    def transport(endpoint, headers, body, timeout):
        return PerplexityHttpResponse(
            status,
            {},
            b'{"error":{"type":"provider_error","code":"blocked"}}',
        )

    run = execute_perplexity_search(
        workspace,
        audit_id=AUDIT_ID,
        query=f"http {status}",
        env={API_KEY_ENV: "TEST_ONLY_PERPLEXITY_KEY"},
        transport=transport,
    )
    assert run.status != "SUCCESS"
    assert run.native_usage[0].billable is False
    assert run.pricing.estimated_cost == pytest.approx(0.0)
    if status == 402:
        assert run.status == "CREDIT_ERROR"
        assert run.diagnostic.error_class.value == "CREDIT_ERROR"
        with sqlite3.connect(workspace.database) as conn:
            assert conn.execute("SELECT COUNT(*) FROM perplexity_search_runs").fetchone()[0] == 1
            assert conn.execute("SELECT score FROM scores").fetchone()[0] == 87.5


def test_scoped_search_payload_persists_exact_payload_fingerprint(tmp_path) -> None:
    """Provider receives only policy-approved options, not PlayGround settings."""
    import hashlib
    from rasai.search_intelligence.perplexity_request_policy import resolve_request_options

    workspace = _workspace(tmp_path)
    payloads: list[dict] = []

    def transport(endpoint, headers, body, timeout):
        payloads.append(json.loads(body))
        return _success_transport("web")(endpoint, headers, body, timeout)

    scope = resolve_request_options({
        "RASAI_PERPLEXITY_MAX_RESULTS": "7",
        "RASAI_PERPLEXITY_SEARCH_LANGUAGE_FILTER": "pt",
        "RASAI_PERPLEXITY_SEARCH_DOMAIN_FILTER": "example.com",
        "RASAI_PERPLEXITY_SEARCH_RECENCY_FILTER": "month",
        "RASAI_PERPLEXITY_MAX_TOKENS": "4000",
        "RASAI_PERPLEXITY_MAX_TOKENS_PER_PAGE": "2000",
    }, explicit_brazil=True)
    run = execute_perplexity_search(
        workspace,
        audit_id=AUDIT_ID,
        query="seguro de vida",
        search_type="web",
        search_options=scope,
        env={API_KEY_ENV: "TEST_ONLY_PERPLEXITY_KEY"},
        transport=transport,
    )
    assert run.status == "SUCCESS"
    assert len(payloads) == 1
    outgoing = payloads[0]
    assert outgoing == {
        "query": "seguro de vida",
        "search_type": "web",
        "max_results": 7,
        "country": "BR",
        "search_language_filter": ["pt"],
        "search_domain_filter": ["example.com"],
        "search_recency_filter": "month",
        "max_tokens": 4000,
        "max_tokens_per_page": 2000,
    }
    expected = json.dumps(outgoing, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    assert run.request_payload_hash == hashlib.sha256(expected).hexdigest()
    row = _db_rows(
        workspace,
        "SELECT request_payload_hash FROM perplexity_search_runs WHERE run_id='" + run.run_id + "'",
    )
    assert len(row) == 1
    assert row[0]["request_payload_hash"] == run.request_payload_hash
    assert "TEST_ONLY_PERPLEXITY_KEY" not in repr(outgoing)


def test_scoped_search_rejects_invalid_options_without_transport(tmp_path) -> None:
    workspace = _workspace(tmp_path)

    def forbidden(*args):
        raise AssertionError("invalid request should never reach HTTP transport")

    with pytest.raises(ValueError, match="max_results"):
        execute_perplexity_search(
            workspace,
            audit_id=AUDIT_ID,
            query="seguro de vida",
            search_options={"max_results": 21},
            env={API_KEY_ENV: "TEST_ONLY_PERPLEXITY_KEY"},
            transport=forbidden,
        )

