"""#330: no external calls, robots and consent enforced before public HTML."""
from __future__ import annotations

from io import BytesIO
import json

import pytest

from rasai.geo_competitor_fetch_330 import (
    inspect_consented_public_html, main,
)
from rasai.search_intelligence.content import PublicWebFetcher


class _Response:
    def __init__(self, status: int, content_type: str, body: bytes,
                 location: str | None = None) -> None:
        self.code = status
        self.headers = {"Content-Type": content_type}
        if location is not None:
            self.headers["Location"] = location
        self._data = BytesIO(body)

    def getcode(self) -> int:
        return self.code

    def read(self, n: int) -> bytes:
        return self._data.read(n)

    def close(self) -> None:
        self._data.close()


class _FakeTransport:
    def __init__(self, robots: bytes, *, html: bytes | None = None,
                 robots_code: int = 200, html_code: int = 200,
                 robots_type: str = "text/plain", html_type: str = "text/html",
                 html_location: str | None = None) -> None:
        self.robots = robots
        self.html = html if html is not None else (
            b"<html><title>Seguro de vida</title>"
            b"<main><h1>Seguro de vida</h1><p>Seguro de vida total</p></main></html>"
        )
        self.robots_code = robots_code
        self.html_code = html_code
        self.robots_type = robots_type
        self.html_type = html_type
        self.html_location = html_location
        self.urls: list[str] = []

    def __call__(self, request, *, timeout: float):
        assert 0 < timeout <= 10
        self.urls.append(request.full_url)
        if request.full_url.endswith("/robots.txt"):
            return _Response(self.robots_code, self.robots_type, self.robots)
        return _Response(
            self.html_code, self.html_type, self.html, self.html_location
        )


def _client(transport, resolved=None):
    resolver = resolved or (lambda host, port: ("1.1.1.1",))
    return PublicWebFetcher(
        max_redirects=0, timeout_seconds=2, max_bytes=2_000_000,
        resolver=resolver, opener=transport,
    )


def _inspect(client, *, url="https://example.com/seguro-de-vida",
             consent=("example.com",), role="COMPETITOR_CANDIDATE"):
    return inspect_consented_public_html(
        url, query="seguro de vida", role=role,
        consented_hostnames=consent, fetcher=client,
    )


def test_explicit_robots_allow_returns_transient_html_features_no_aud_write():
    t = _FakeTransport(b"User-agent: *\nAllow: /\n")
    result = _inspect(_client(t))
    assert result["status"] == "STATIC_HTML_FEATURES_OBSERVED"
    assert result["robots_fetch_status"] == "ALLOWED"
    assert result["content_evidence_status"] == "TRANSIENT_STATIC_HTML_FEATURES"
    assert result["provider_requests"] == 2
    assert result["content_sha256"] is not None
    assert result["query_body_terms"] == ["seguro", "vida"]
    assert result["html_fetch_timestamp"].endswith("+00:00")
    assert result["html_rendering"] == "STATIC_HTTP_ONLY_NO_JS"
    assert result["primary_content_proven"] is False
    assert result["score_changed"] is False
    assert result["audit_writes"] == 0
    assert t.urls == [
        "https://example.com/robots.txt", "https://example.com/seguro-de-vida"
    ]


def test_robots_disallow_stops_before_html_get():
    t = _FakeTransport(b"User-agent: *\nDisallow: /seguro-de-vida\n")
    result = _inspect(_client(t))
    assert result["status"] == "ROBOTS_DISALLOWED"
    assert result["provider_requests"] == 1
    assert t.urls == ["https://example.com/robots.txt"]


def test_consent_does_not_trigger_dns_or_http():
    calls = []
    t = _FakeTransport(b"User-agent: *\nAllow: /\n")
    client = _client(t, resolved=lambda host, port: calls.append(host) or ("1.1.1.1",))
    assert _inspect(client, consent=("other.com",))["status"] == (
        "EXACT_HOST_CONSENT_MISSING"
    )
    assert not calls and not t.urls and client.requests_used == 0


@pytest.mark.parametrize(
    "robots,code,media,expected",
    [
        (b"User-agent: *\nAllow: /\n", 404, "text/plain",
         "ROBOTS_UNAVAILABLE_OR_NOT_VERIFIED"),
        (b"User-agent: *\nAllow: /\n", 200, "text/html",
         "ROBOTS_NOT_PLAIN_TEXT"),
        (b"broken", 200, "text/plain", "ROBOTS_NO_APPLICABLE_USER_AGENT"),
        (b"User-agent: OtherBot\nAllow: /", 200, "text/plain",
         "ROBOTS_NO_APPLICABLE_USER_AGENT"),
        (b"User-agent: *\nAllow: /\n" + b"x" * 65_000,
         200, "text/plain", "ROBOTS_UNAVAILABLE_OR_NOT_VERIFIED"),
        (b"User-agent: *\nAllow: /\n\xff", 200, "text/plain",
         "ROBOTS_INVALID_ENCODING"),
    ],
)
def test_robots_absent_or_invalid_abstains_without_html(
    robots, code, media, expected,
):
    t = _FakeTransport(robots, robots_code=code, robots_type=media)
    result = _inspect(_client(t))
    assert result["status"] == expected
    assert result["provider_requests"] == 1
    assert len(t.urls) == 1
    assert result["content_sha256"] is None


def test_redirected_html_is_not_followed_even_if_destination_public():
    t = _FakeTransport(b"User-agent: *\nAllow: /", html_code=302,
                       html_location="https://other.com/secret")
    result = _inspect(_client(t))
    assert result["status"] == "HTML_NOT_OBSERVED"
    assert result["content_sha256"] is None
    assert result["provider_requests"] == 2
    assert "other.com" not in json.dumps(t.urls)


def test_spa_shell_without_lexical_body_does_not_prove_primary_content():
    t = _FakeTransport(
        b"User-agent: *\nAllow: /",
        html=b"<html><title>Seguro de vida</title><main id='app'></main></html>",
    )
    result = _inspect(_client(t), role="CUSTOMER")
    assert result["status"] == "STATIC_HTML_WITHOUT_QUERY_BODY_EVIDENCE"
    assert result["content_evidence_status"] == "NOT_COMPARABLE"
    assert result["primary_content_proven"] is False


def test_rejects_unsafe_host_transport_and_missing_consent():
    t = _FakeTransport(b"User-agent: *\nAllow: /")
    client = _client(t)
    assert _inspect(client, url="http://localhost/private",
                    consent=("localhost",))["status"] == "UNSAFE_PUBLIC_URL"
    assert client.requests_used == 0
    with pytest.raises(ValueError, match="no-redirect"):
        _inspect(PublicWebFetcher(opener=t, resolver=lambda host, port: ("1.1.1.1",)))
    with pytest.raises(ValueError, match="exact-host"):
        _inspect(client, consent=("*.example.com",))


def test_cli_requires_explicit_http_authorization(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--url", "https://example.com", "--query", "seguro",
              "--role", "CUSTOMER", "--consent-host", "example.com"])
    assert exc.value.code == 2
    assert "explicit --allow-public-html-requests is required" in capsys.readouterr().err
