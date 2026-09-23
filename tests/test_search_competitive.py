from __future__ import annotations

from datetime import datetime, timezone
import io
import json
from pathlib import Path
import sqlite3

from rasai.search_intelligence.competitive import (
    SearchResultClass,
    select_competitive_candidates,
)
from rasai.search_intelligence.competitive_persistence import (
    CompetitiveIntelligenceRepository,
    FilesystemCompetitiveEvidenceSink,
)
from rasai.search_intelligence.content import (
    ContentFetchStatus,
    PublicWebFetcher,
    _FetchedDocument,
    analyze_competitive_content,
    extract_page_features,
    query_terms,
)
from rasai.search_intelligence.models import (
    DomainMatchStatus,
    QueryOrigin,
    SearchIntelligenceResult,
    SerpDataMode,
    SerpObservation,
    SerpObservationStatus,
    SerpQueryRequest,
    SerpResult,
)


def _search_result(*, found: bool = True) -> SearchIntelligenceResult:
    results = (
        SerpResult(1, "www.gov.br", "https://www.gov.br/tema", title="Governo"),
        SerpResult(2, "youtube.com", "https://youtube.com/watch?v=1", title="Video"),
        SerpResult(3, "leader.example", "https://leader.example/seguro", title="Leader"),
        SerpResult(4, "amazon.com.br", "https://amazon.com.br/item", title="Marketplace"),
        SerpResult(5, "customer.example", "https://customer.example/seguro", title="Customer"),
        SerpResult(6, "later.example", "https://later.example/seguro", title="Later"),
    )
    request = SerpQueryRequest(
        query="seguro auto online",
        depth=10,
        domain_of_interest="customer.example",
        run_id="SERP-RUN-TEST",
    )
    observed = results if found else results[:4]
    observation = SerpObservation(
        observation_id="SERP-OBS-TEST",
        run_id=request.run_id,
        query=request.query,
        query_origin=QueryOrigin.MANUAL,
        engine="google",
        country="BR",
        region=None,
        language="pt-BR",
        device="desktop",
        collected_at=datetime(2026, 9, 9, tzinfo=timezone.utc),
        provider="fixture",
        provider_request_id=None,
        requested_depth=10,
        result_count=len(observed),
        results=observed,
        data_mode=SerpDataMode.FIXTURE,
        status=SerpObservationStatus.OBSERVED,
    )
    return SearchIntelligenceResult(
        request=request,
        observation=observation,
        domain_status=(
            DomainMatchStatus.FOUND
            if found
            else DomainMatchStatus.NOT_FOUND_WITHIN_DEPTH
        ),
        customer_position=5 if found else None,
        results_ahead=results[:4] if found else (),
        competitor_domains_ahead=("www.gov.br", "youtube.com", "leader.example", "amazon.com.br"),
    )


def test_competitive_selection_classifies_and_bounds_candidates() -> None:
    selection = select_competitive_candidates(_search_result(), max_pages=2)

    assert selection.customer_result is not None
    assert selection.customer_result.position == 5
    assert [item.classification for item in selection.classified_results] == [
        SearchResultClass.PUBLIC_AUTHORITY,
        SearchResultClass.VIDEO_PLATFORM,
        SearchResultClass.ORGANIC_CANDIDATE,
        SearchResultClass.MARKETPLACE,
    ]
    assert [item.result.domain for item in selection.selected_candidates] == [
        "leader.example",
        "amazon.com.br",
    ]
    assert all(item.result.position < 5 for item in selection.classified_results)


def test_not_found_classifies_observed_results_without_claiming_customer_absence() -> None:
    selection = select_competitive_candidates(_search_result(found=False), max_pages=1)

    assert selection.customer_result is None
    assert len(selection.classified_results) == 4
    assert selection.selected_candidates[0].result.domain == "leader.example"


def test_query_terms_normalize_accents_and_stopwords() -> None:
    assert query_terms("Seguro de Automóvel para São Paulo") == (
        "seguro",
        "automovel",
        "sao",
        "paulo",
    )


def test_extract_features_is_deterministic_and_does_not_persist_raw_html() -> None:
    html = b"""
    <html><head>
      <title>Seguro Auto Online</title>
      <meta name="description" content="Cotacao de seguro auto">
      <script type="application/ld+json">{"@type":"Product"}</script>
      <script>seguro fake script</script>
    </head><body>
      <h1>Seguro auto</h1><h2>Contrate online</h2>
      <p>Seguro para seu carro com cotacao online.</p>
    </body></html>
    """
    fetched = _FetchedDocument(
        requested_url="https://customer.example/seguro",
        final_url="https://customer.example/seguro",
        http_status=200,
        headers={"content-type": "text/html; charset=utf-8"},
        body=html,
        redirects=(),
        status=ContentFetchStatus.OBSERVED,
    )

    page = extract_page_features(
        fetched,
        role="CUSTOMER",
        domain="customer.example",
        query="seguro auto online",
    )

    assert page.status is ContentFetchStatus.OBSERVED
    assert page.title == "Seguro Auto Online"
    assert page.headings == ("Seguro auto", "Contrate online")
    assert page.query_terms_in_title == ("seguro", "auto", "online")
    assert page.query_terms_in_headings == ("seguro", "auto", "online")
    assert page.query_body_coverage == 1.0
    assert page.jsonld_types == ("Product",)
    assert page.content_sha256 is not None
    assert page.bytes_read == len(html)


def test_public_web_fetcher_blocks_private_literal_before_opener() -> None:
    calls = []

    def opener(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("opener must not be called")

    fetcher = PublicWebFetcher(
        resolver=lambda host, port: ("127.0.0.1",),
        opener=opener,
    )
    result = fetcher.fetch("http://127.0.0.1/private")

    assert result.status is ContentFetchStatus.BLOCKED
    assert result.error_code == "PUBLIC_WEB_DESTINATION_BLOCKED"
    assert calls == []
    assert fetcher.requests_used == 0


def test_public_web_fetcher_blocks_hostname_resolving_private_before_opener() -> None:
    calls = []

    def opener(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("opener must not be called")

    fetcher = PublicWebFetcher(
        resolver=lambda host, port: ("10.0.0.8",),
        opener=opener,
    )
    result = fetcher.fetch("https://example.invalid/page")

    assert result.status is ContentFetchStatus.BLOCKED
    assert "non-public address" in (result.error_message or "")
    assert calls == []


class _FakeHeaders(dict):
    def items(self):
        return super().items()

    def get(self, key, default=None):
        for current, value in self.items():
            if current.casefold() == str(key).casefold():
                return value
        return default


class _FakeResponse:
    def __init__(self, status: int, body: bytes = b"", headers=None):
        self._status = status
        self._body = io.BytesIO(body)
        self.headers = _FakeHeaders(headers or {})

    def getcode(self):
        return self._status

    def read(self, size=-1):
        return self._body.read(size)

    def close(self):
        pass


def test_public_web_fetcher_validates_redirect_target_before_second_request() -> None:
    calls = []

    def resolver(host, port):
        if host == "public.example":
            return ("93.184.216.34",)
        if host == "localhost":
            return ("127.0.0.1",)
        raise AssertionError(host)

    def opener(request, timeout):
        calls.append(request.full_url)
        return _FakeResponse(
            302,
            headers={"Location": "http://localhost/admin"},
        )

    fetcher = PublicWebFetcher(resolver=resolver, opener=opener)
    result = fetcher.fetch("https://public.example/start")

    assert result.status is ContentFetchStatus.BLOCKED
    assert calls == ["https://public.example/start"]
    assert fetcher.requests_used == 1


def test_content_analysis_reports_correlational_gaps() -> None:
    result = _search_result()
    pages = {
        "https://customer.example/seguro": b"""
            <html><head><title>Seguro</title></head>
            <body><h1>Seguro</h1><p>Seguro simples.</p></body></html>
        """,
        "https://leader.example/seguro": b"""
            <html><head><title>Seguro Auto Online</title>
            <script type="application/ld+json">{"@type":"Product"}</script></head>
            <body><h1>Seguro Auto Online</h1><p>
            Seguro auto online cotacao protecao cobertura carro veiculo assistencia.
            </p></body></html>
        """,
        "https://amazon.com.br/item": b"""
            <html><head><title>Seguro Auto Online</title></head>
            <body><h1>Seguro Auto Online</h1><p>
            Seguro auto online com informacoes adicionais e comparacao.
            </p></body></html>
        """,
    }

    class FakeFetcher:
        requests_used = 0

        def fetch(self, url):
            self.requests_used += 1
            body = pages[url]
            return _FetchedDocument(
                requested_url=url,
                final_url=url,
                http_status=200,
                headers={"content-type": "text/html; charset=utf-8"},
                body=body,
                redirects=(),
                status=ContentFetchStatus.OBSERVED,
            )

    analysis = analyze_competitive_content(
        result,
        max_competitor_pages=2,
        fetcher=FakeFetcher(),
    )

    assert analysis.comparison_status == "CONSOLIDATED"
    codes = {item.code for item in analysis.gaps}
    assert "TITLE_QUERY_ALIGNMENT_LOWER_THAN_OBSERVED_LEADERS" in codes
    assert "HEADING_QUERY_ALIGNMENT_LOWER_THAN_OBSERVED_LEADERS" in codes
    assert "STRUCTURED_DATA_TYPES_DIFFER_FROM_OBSERVED_LEADERS" in codes
    assert all(item.severity == "INFO" for item in analysis.gaps)


def test_content_analysis_requires_customer_url_when_not_found_without_fetching() -> None:
    class NoFetch:
        requests_used = 0

        def fetch(self, url):
            raise AssertionError("must not fetch without customer URL")

    analysis = analyze_competitive_content(
        _search_result(found=False),
        max_competitor_pages=2,
        fetcher=NoFetch(),
    )
    assert analysis.comparison_status == "CUSTOMER_URL_REQUIRED"
    assert analysis.customer_page is None
    assert analysis.competitor_pages == ()


def test_competitive_persistence_is_additive_and_artifact_contains_no_raw_html(tmp_path: Path) -> None:
    database = tmp_path / "audit.db"
    connection = sqlite3.connect(database)
    try:
        connection.executescript(
            """
            CREATE TABLE audits (
                audit_id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL
            );
            CREATE TABLE serp_observations (
                observation_id TEXT PRIMARY KEY,
                audit_id TEXT NOT NULL REFERENCES audits(audit_id)
            );
            INSERT INTO audits(audit_id, created_at) VALUES ('AUDIT-1', '2026-09-09T00:00:00Z');
            INSERT INTO serp_observations(observation_id, audit_id) VALUES ('SERP-OBS-TEST', 'AUDIT-1');
            """
        )
        connection.commit()
    finally:
        connection.close()

    result = _search_result()

    class FakeFetcher:
        requests_used = 0

        def fetch(self, url):
            self.requests_used += 1
            html = (
                "<html><head><title>Seguro Auto Online</title></head>"
                "<body><h1>Seguro Auto Online</h1><p>seguro auto online</p></body></html>"
            ).encode()
            return _FetchedDocument(
                requested_url=url,
                final_url=url,
                http_status=200,
                headers={"content-type": "text/html"},
                body=html,
                redirects=(),
                status=ContentFetchStatus.OBSERVED,
            )

    analysis = analyze_competitive_content(
        result,
        max_competitor_pages=1,
        fetcher=FakeFetcher(),
    )
    sink = FilesystemCompetitiveEvidenceSink(tmp_path)
    ref, digest = sink.write("SERP-OBS-TEST", analysis)
    with CompetitiveIntelligenceRepository.from_workspace(tmp_path) as repository:
        repository.save(
            "SERP-OBS-TEST",
            analysis,
            evidence_ref=ref,
            evidence_sha256=digest,
        )

    payload = json.loads((tmp_path / ref).read_text(encoding="utf-8"))
    assert payload["raw_html_persisted"] is False
    assert payload["customer_page"]["content_sha256"]
    assert "<html" not in (tmp_path / ref).read_text(encoding="utf-8").casefold()

    connection = sqlite3.connect(database)
    try:
        analysis_row = connection.execute(
            "SELECT comparison_status, gap_count, evidence_sha256 "
            "FROM serp_competitive_analyses WHERE observation_id='SERP-OBS-TEST'"
        ).fetchone()
        pages = connection.execute(
            "SELECT role, content_sha256 FROM serp_competitive_pages "
            "WHERE observation_id='SERP-OBS-TEST' ORDER BY role"
        ).fetchall()
    finally:
        connection.close()

    assert analysis_row is not None
    assert analysis_row[0] == "CONSOLIDATED"
    assert analysis_row[2] == digest
    assert pages
    assert all(item[1] for item in pages)
