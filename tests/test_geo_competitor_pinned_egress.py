"""#330: pinned egress tests use memory TCP/TLS only; no public requests."""
from __future__ import annotations

from io import BytesIO
import socket
import ssl
from urllib.request import Request

import pytest

from rasai.geo_competitor_fetch_330 import inspect_consented_public_html
from rasai.geo_competitor_pinned_egress import PublicWebPinnedOpener
from rasai.search_intelligence.content import (
    ContentFetchStatus, PublicWebFetcher,
)


class _MemorySocket:
    def __init__(self) -> None:
        self.sent = bytearray()
        self.closed = False

    def sendall(self, data: bytes) -> None:
        self.sent.extend(data)

    def makefile(self, mode: str):
        assert mode == "rb"
        path = bytes(self.sent).split(b" ", 2)[1]
        if path == b"/robots.txt":
            body, media = b"User-agent: *\nAllow: /\n", b"text/plain"
        else:
            body = (
                b"<html><title>Seguro de vida</title>"
                b"<main><h1>Seguro de vida</h1><p>Seguro de vida</p></main></html>"
            )
            media = b"text/html"
        return BytesIO(
            b"HTTP/1.1 200 OK\r\nContent-Type: " + media +
            b"\r\nContent-Length: " + str(len(body)).encode("ascii") +
            b"\r\nConnection: close\r\n\r\n" + body
        )

    def close(self) -> None:
        self.closed = True


def test_pinned_http_uses_only_public_numeric_ip_and_original_host(monkeypatch):
    connections = []

    def fake_connect(destination, timeout):
        assert destination == ("1.1.1.1", 80)
        connections.append(_MemorySocket())
        return connections[-1]

    monkeypatch.setattr(socket, "create_connection", fake_connect)
    opener = PublicWebPinnedOpener(lambda host, port: ("1.1.1.1",))
    response = opener(Request("http://example.org/a?q=1"), timeout=2)
    try:
        assert response.getcode() == 200
        assert response.headers["Content-Type"] == "text/html"
        assert b"Seguro de vida" in response.read(2_000_001)
    finally:
        response.close()
    assert len(connections) == 1 and connections[0].closed
    written = bytes(connections[0].sent)
    assert b"GET /a?q=1 HTTP/1.1" in written
    assert b"Host: example.org" in written
    assert b"1.1.1.1" not in written


def test_https_pins_tcp_ip_but_preserves_tls_sni_hostname(monkeypatch):
    observed = {"tcp": [], "sni": [], "contexts": 0}
    sockets = []

    def fake_connect(dest, timeout):
        observed["tcp"].append((dest, timeout))
        sock = _MemorySocket()
        sockets.append(sock)
        return sock

    class FakeTLSContext:
        def wrap_socket(self, sock, *, server_hostname):
            observed["sni"].append(server_hostname)
            return sock

    def context_factory():
        observed["contexts"] += 1
        return FakeTLSContext()

    monkeypatch.setattr(socket, "create_connection", fake_connect)
    monkeypatch.setattr(ssl, "create_default_context", context_factory)
    opener = PublicWebPinnedOpener(lambda host, port: ("8.8.8.8",))
    response = opener(Request("https://example.org/robots.txt"), timeout=4)
    try:
        assert response.getcode() == 200
        assert b"User-agent" in response.read(64001)
    finally:
        response.close()
    assert observed == {
        "tcp": [(("8.8.8.8", 443), 4)],
        "sni": ["example.org"], "contexts": 1,
    }
    assert sockets[0].closed
    assert b"Host: example.org" in bytes(sockets[0].sent)


def test_dns_rebinding_to_private_ip_is_blocked_before_any_tcp(monkeypatch):
    calls = {"dns": 0, "tcp": 0}

    def flipping_resolver(host, port):
        calls["dns"] += 1
        return ("1.1.1.1",) if calls["dns"] < 4 else ("127.0.0.1",)

    def unexpected_tcp(*args, **kwargs):
        calls["tcp"] += 1
        pytest.fail("rebinding may not reach the socket")

    monkeypatch.setattr(socket, "create_connection", unexpected_tcp)
    client = PublicWebFetcher(
        max_redirects=0, resolver=flipping_resolver,
        opener=PublicWebPinnedOpener(flipping_resolver),
    )
    result = client.fetch("http://example.org/robots.txt")
    assert result.status is ContentFetchStatus.UNAVAILABLE
    assert result.error_code == "CONTENT_NETWORK_ERROR"
    assert calls == {"dns": 4, "tcp": 0}
    assert client.requests_used == 1


def test_mixed_public_private_dns_answers_are_rejected_by_pinned_gate(monkeypatch):
    calls = {"dns": 0}
    def resolver(host, port):
        calls["dns"] += 1
        return ("1.1.1.1",) if calls["dns"] == 1 else ("1.1.1.1", "10.0.0.7")
    monkeypatch.setattr(socket, "create_connection", lambda *a, **k: pytest.fail(
        "mixed DNS cannot connect"
    ))
    with pytest.raises(Exception, match="pinned public egress denied"):
        PublicWebPinnedOpener(resolver)(
            Request("https://example.org/robots.txt"), timeout=2,
        )
    assert calls["dns"] == 2


def test_consented_robots_and_html_use_pinned_transport_no_external_io(monkeypatch):
    destinations = []

    def fake_connect(dest, timeout):
        destinations.append(dest)
        return _MemorySocket()

    monkeypatch.setattr(socket, "create_connection", fake_connect)
    monkeypatch.setattr(ssl, "create_default_context", lambda: type(
        "FakeTLS", (), {"wrap_socket": lambda self, sock, server_hostname: sock},
    )())
    resolver = lambda host, port: ("8.8.8.8",)
    client = PublicWebFetcher(
        max_redirects=0, max_bytes=2_000_000, timeout_seconds=2,
        resolver=resolver, opener=PublicWebPinnedOpener(resolver),
    )
    result = inspect_consented_public_html(
        "https://example.org/seguro",
        query="seguro de vida", role="COMPETITOR_CANDIDATE",
        consented_hostnames=("example.org",), fetcher=client,
        consent_purpose="GEO_COMPETITOR_STATIC_CONTENT_REVIEW",
        consented_operations=("GET_ROBOTS_TXT", "GET_STATIC_HTML"),
    )
    assert result["status"] == "STATIC_HTML_FEATURES_OBSERVED"
    assert result["provider_requests"] == 2
    assert result["egress_transport_status"] == "PINNED_PUBLIC_IP_TLS_HOSTNAME_CHECK"
    assert destinations == [("8.8.8.8", 443), ("8.8.8.8", 443)]
    assert result["audit_writes"] == 0 and result["primary_content_proven"] is False
