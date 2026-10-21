"""#330: no external calls, robots and consent enforced before public HTML."""
from __future__ import annotations

from io import BytesIO
import json

import pytest

from rasai.geo_competitor_fetch import (
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
             consent=("example.com",), role="COMPETITOR_CANDIDATE",
             purpose=None, operations=("GET_ROBOTS_TXT", "GET_STATIC_HTML")):
    if purpose is None:
        purpose = (
            "AUD_CUSTOMER_STATIC_CONTENT_REVIEW"
            if role == "CUSTOMER"
            else "GEO_COMPETITOR_STATIC_CONTENT_REVIEW"
        )
    return inspect_consented_public_html(
        url, query="seguro de vida", role=role,
        consented_hostnames=consent, fetcher=client,
        consent_purpose=purpose, consented_operations=operations,
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
    ids=("missing", "wrong-mime", "malformed", "unmatched-agent",
         "oversized", "invalid-encoding"),
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
        html=b"<html><title>Welcome</title><main id='app'></main></html>",
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


@pytest.mark.parametrize(
    "reason,changes",
    [
        ("no-purpose", {"purpose": "INVALID_PURPOSE"}),
        ("wrong-purpose", {"purpose": "AUD_CUSTOMER_STATIC_CONTENT_REVIEW"}),
        ("no-operations", {"operations": ()}),
        ("one-operation", {"operations": ("GET_ROBOTS_TXT",)}),
        ("duplicates", {"operations": ("GET_STATIC_HTML", "GET_STATIC_HTML")}),
        ("extra-operation", {"operations": ("GET_ROBOTS_TXT", "GET_STATIC_HTML", "POST")}),
    ],
)
def test_missing_role_purpose_or_operations_refuses_before_dns_and_http(
    reason, changes,
):
    dns, transport = [], _FakeTransport(b"User-agent: *\\nAllow: /\\n")
    client = _client(transport, resolved=lambda host, port: dns.append(host) or ("1.1.1.1",))
    result = _inspect(client, **changes)
    assert result["status"] == "EXPLICIT_PURPOSE_OPERATION_CONSENT_MISSING", reason
    assert result["provider_requests"] == 0
    assert dns == [] and transport.urls == []
    assert client.requests_used == 0


def test_cli_explicit_purpose_and_operation_required_before_network(capsys):
    arguments = [
        "--url", "https://example.com/seguro-de-vida",
        "--query", "seguro de vida",
        "--role", "COMPETITOR_CANDIDATE",
        "--consent-host", "example.com",
        "--allow-public-html-requests",
    ]
    with pytest.raises(SystemExit) as exc:
        main(arguments)
    assert exc.value.code == 2
    assert "explicit purpose and both GET operations" in capsys.readouterr().err


def test_native_competitor_html_entrypoint_routes_scope_without_audit_bootstrap(
    capsys, monkeypatch,
):
    from rasai import entrypoint
    from rasai import geo_competitor_fetch as module

    monkeypatch.setattr(
        entrypoint, "_install_audit_runtime",
        lambda: pytest.fail("consented COBS route must never install audit runtime"),
    )
    monkeypatch.setattr(
        entrypoint, "_activate_persisted_cli_secrets",
        lambda: pytest.fail("consented COBS route must not activate secrets"),
    )
    received = []

    def fake_consented_inspection(url, **kwargs):
        received.append((url, kwargs))
        return {
            "status": "EXACT_HOST_CONSENT_MISSING",
            "provider_requests": 0, "audit_writes": 0,
        }

    monkeypatch.setattr(
        module, "inspect_consented_public_html", fake_consented_inspection,
    )
    args = [
        "--url", "https://example.com/pagina",
        "--query", "seguro de vida",
        "--role", "COMPETITOR_CANDIDATE",
        "--consent-host", "example.com",
        "--allow-public-html-requests",
        "--consent-purpose", "GEO_COMPETITOR_STATIC_CONTENT_REVIEW",
        "--consent-operation", "GET_ROBOTS_TXT",
        "--consent-operation", "GET_STATIC_HTML",
    ]
    assert entrypoint.main(["competitor-html-review", *args]) == 0
    obj = json.loads(capsys.readouterr().out)
    assert obj["provider_requests"] == obj["audit_writes"] == 0
    assert received == [(
        "https://example.com/pagina", {
            "query": "seguro de vida",
            "role": "COMPETITOR_CANDIDATE",
            "consented_hostnames": ["example.com"],
            "consent_purpose": "GEO_COMPETITOR_STATIC_CONTENT_REVIEW",
            "consented_operations": ["GET_ROBOTS_TXT", "GET_STATIC_HTML"],
        },
    )]


def test_native_cobs_capture_requires_purpose_operations_before_source_or_network(
    tmp_path, capsys, monkeypatch,
):
    from rasai import entrypoint
    from rasai import geo_competitor_capture_bundle as module

    monkeypatch.setattr(
        entrypoint, "_install_audit_runtime",
        lambda: pytest.fail("COBS command must not install audit runtime"),
    )
    monkeypatch.setattr(
        entrypoint, "_activate_persisted_cli_secrets",
        lambda: pytest.fail("COBS command must not activate secrets"),
    )
    monkeypatch.setattr(
        module, "capture_competitor_sidecar",
        lambda *a, **k: pytest.fail("unconsented CLI must stop before capture"),
    )
    args = [
        "competitor-capture",
        "--audit-dir", str(tmp_path / "AUD-TEST"),
        "--serp-observation-id", "SERP-ONE",
        "--candidate-url", "https://example.com/pagina",
        "--output-root", str(tmp_path / "output"),
        "--consent-host", "example.com",
        "--allow-public-html-requests",
    ]
    with pytest.raises(SystemExit) as err:
        entrypoint.main(args)
    assert err.value.code == 2
    assert "explicit purpose and both GET operations" in capsys.readouterr().err
    assert not (tmp_path / "output").exists()


def test_opt_in_replay_uses_original_authorized_html_no_extra_requests(monkeypatch):
    from rasai import geo_competitor_inline_render as replay
    observed = []

    def fake_replay(url, html, *, device, response_headers):
        observed.append((url, html, device, response_headers["content-type"]))
        return {"status": "INLINE_DOM_STABLE_IN_OCI",
                "live_primary_content_proven": False,
                "additional_public_http_requests": 0}

    monkeypatch.setattr(replay, "inspect_inline_spa_replay", fake_replay)
    transport = _FakeTransport(b"User-agent: *\nAllow: /\n")
    client = _client(transport)
    result = inspect_consented_public_html(
        "https://example.com/seguro-de-vida",
        query="seguro de vida", role="CUSTOMER",
        consented_hostnames=["example.com"], fetcher=client,
        consent_purpose="AUD_CUSTOMER_STATIC_CONTENT_REVIEW",
        consented_operations=("GET_ROBOTS_TXT", "GET_STATIC_HTML"),
        offline_inline_js_replay=True, replay_device="mobile",
    )
    assert result["status"] == "STATIC_HTML_FEATURES_OBSERVED"
    assert result["html_rendering"] == "STATIC_HTTP_ONLY_NO_JS"
    assert result["primary_content_proven"] is False
    assert result["offline_js_advisory"]["status"] == "INLINE_DOM_STABLE_IN_OCI"
    assert result["provider_requests"] == 2
    assert len(transport.urls) == 2
    assert observed == [("https://example.com/seguro-de-vida", transport.html,
                         "mobile", "text/html")]


def test_no_replay_without_robots_or_explicit_device(monkeypatch):
    from rasai import geo_competitor_inline_render as replay
    monkeypatch.setattr(replay, "inspect_inline_spa_replay",
                        lambda *a, **kw: pytest.fail("no unauthorized replay"))
    transport = _FakeTransport(b"User-agent: *\nDisallow: /")
    client = _client(transport)
    kwargs = dict(
        url="https://example.com/seguro-de-vida", query="seguro de vida",
        role="CUSTOMER", consented_hostnames=["example.com"], fetcher=client,
        consent_purpose="AUD_CUSTOMER_STATIC_CONTENT_REVIEW",
        consented_operations=("GET_ROBOTS_TXT", "GET_STATIC_HTML"),
        offline_inline_js_replay=True,
    )
    with pytest.raises(ValueError, match="device"):
        inspect_consented_public_html(**kwargs)
    assert client.requests_used == 0
    assert inspect_consented_public_html(**kwargs, replay_device="desktop")["status"] == "ROBOTS_DISALLOWED"
    assert len(transport.urls) == 1


def test_cli_replay_requires_device_before_network(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--url", "https://example.com", "--query", "x",
              "--role", "CUSTOMER", "--consent-host", "example.com",
              "--offline-inline-js-replay", "--allow-public-html-requests"])
    assert exc.value.code == 2
    assert "--replay-device required" in capsys.readouterr().err
