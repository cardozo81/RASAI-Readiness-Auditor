"""#355: authenticated Dynatrace GET egress tests; all TCP/TLS are memory fakes."""
from __future__ import annotations

from io import BytesIO
import json
import socket
import ssl
from urllib.error import URLError
from urllib.request import Request

import pytest

from rasai import dynatrace_rum_population_355 as rum
from rasai import dynatrace_settings_live_355 as settings
from rasai.dynatrace_settings_live_355 import DynatracePinnedOpener


_TENANT = "tenant-abc123.live.dynatrace.com"
_BASE = "https://" + _TENANT
_APP = "APPLICATION-1234567890ABCDEF"


class _Socket:
    def __init__(self, status: int = 200):
        self.sent = bytearray()
        self.closed = False
        self.status = status

    def sendall(self, data: bytes) -> None:
        self.sent.extend(data)

    def makefile(self, mode: str):
        assert mode == "rb"
        path = bytes(self.sent).split(b" ", 2)[1]
        if b"/api/v2/settings/effectiveValues?" in path:
            data = {"items": [], "totalCount": 0}
        elif b"/api/v1/userSessionQueryLanguage/table?" in path:
            data = {
                "columnNames": ["type", "COUNT(*)"],
                "values": [["Load", 2], ["Xhr", 3]],
                "extrapolationLevel": 4,
            }
        else:
            pytest.fail("unapproved Dynatrace endpoint requested")
        body = json.dumps(data).encode("utf-8")
        return BytesIO(
            b"HTTP/1.1 " + str(self.status).encode() + b" "
            + (b"Found" if self.status == 302 else b"OK")
            + b"\r\nContent-Type: application/json\r\n"
            + b"Content-Length: " + str(len(body)).encode()
            + b"\r\nConnection: close\r\n"
            + (b"Location: https://evil.example/steal\r\n"
               if self.status == 302 else b"")
            + b"\r\n" + body
        )

    def close(self) -> None:
        self.closed = True


def _network(monkeypatch, status=200):
    sockets, sni, destinations = [], [], []

    def connect(addr, timeout):
        destinations.append((addr, timeout))
        sock = _Socket(status=status)
        sockets.append(sock)
        return sock

    class TLS:
        def wrap_socket(self, sock, *, server_hostname):
            sni.append(server_hostname)
            return sock

    monkeypatch.setattr(socket, "create_connection", connect)
    monkeypatch.setattr(ssl, "create_default_context", TLS)
    return sockets, sni, destinations


def _request(path="/api/v2/settings/effectiveValues?scope=APP"):
    return Request(
        _BASE + path,
        headers={"Authorization": "Api-Token READ-ONLY-SECRET"},
        method="GET",
    )


def test_auth_token_goes_only_to_verified_numeric_ip_with_original_tls_host(monkeypatch):
    sockets, sni, destinations = _network(monkeypatch)
    dns = []
    def resolver(host, port):
        dns.append((host, port))
        return ("8.8.8.8",)

    client = DynatracePinnedOpener(resolver)
    with client.open(_request(), timeout=3.5) as response:
        assert response.getcode() == 200
        assert json.loads(response.read(1024)) == {"items": [], "totalCount": 0}
    assert destinations == [(("8.8.8.8", 443), 3.5)]
    assert sni == [_TENANT]
    assert dns and all(d == (_TENANT, 443) for d in dns)
    assert len(sockets) == 1 and sockets[0].closed
    sent = bytes(sockets[0].sent)
    assert b"Host: tenant-abc123.live.dynatrace.com" in sent
    assert b"Authorization: Api-Token READ-ONLY-SECRET" in sent
    assert b"8.8.8.8" not in sent


@pytest.mark.parametrize("invalid", [
    "https://private.example/api/v2/settings/effectiveValues?x=y",
    "https://tenant-abc123.live.dynatrace.com/private?x=y",
    "http://tenant-abc123.live.dynatrace.com/api/v2/settings/effectiveValues?x=y",
    "https://tenant-abc123.live.dynatrace.com/api/v1/userSessionQueryLanguage/table",
    "https://tenant-abc123.live.dynatrace.com:444/api/v2/settings/effectiveValues?x=y",
])
def test_different_host_endpoint_or_transport_denied_before_dns_and_socket(
    invalid, monkeypatch,
):
    monkeypatch.setattr(
        socket, "create_connection",
        lambda *a, **k: pytest.fail("denied request may not open TCP"),
    )
    client = DynatracePinnedOpener(
        resolver=lambda host, port: pytest.fail("denied request may not resolve DNS")
    )
    with pytest.raises(ValueError, match="outside approved scope"):
        client.open(Request(invalid, headers={"Authorization": "Api-Token SECRET"}))


def test_dns_rebinding_to_loopback_prevents_token_transmission(monkeypatch):
    attempts = []

    def resolver(host, port):
        attempts.append(host)
        return ("8.8.8.8",) if len(attempts) == 1 else ("127.0.0.1",)

    monkeypatch.setattr(
        socket, "create_connection",
        lambda *a, **k: pytest.fail("rebinding cannot reach TCP"),
    )
    with pytest.raises(URLError, match="pinned public egress denied"):
        DynatracePinnedOpener(resolver).open(_request())
    assert len(attempts) == 2


def test_mixed_private_public_dns_answer_denied_before_socket(monkeypatch):
    monkeypatch.setattr(
        socket, "create_connection",
        lambda *a, **k: pytest.fail("mixed DNS cannot reach TCP"),
    )
    with pytest.raises(URLError, match="pinned public egress denied"):
        DynatracePinnedOpener(
            lambda host, port: ("8.8.8.8", "10.0.0.3")
        ).open(_request())


def test_http_redirect_does_not_trigger_secondary_request(monkeypatch):
    sockets, sni, destinations = _network(monkeypatch, status=302)
    client = DynatracePinnedOpener(lambda host, port: ("1.1.1.1",))
    with client.open(_request(), timeout=4) as response:
        assert response.getcode() == 302
    assert len(destinations) == 1
    assert destinations[0] == (("1.1.1.1", 443), 4)
    assert sni == [_TENANT]
    assert sockets[0].closed


def test_both_live_readers_use_pinned_default_path_with_only_memory_io(monkeypatch):
    sockets, sni, destinations = _network(monkeypatch)
    cls = DynatracePinnedOpener
    factory = lambda: cls(lambda host, port: ("8.8.4.4",))
    monkeypatch.setattr(settings, "DynatracePinnedOpener", factory)
    monkeypatch.setattr(rum, "DynatracePinnedOpener", factory)

    result = settings.read_live_dynatrace_apdex_settings(
        base_url=_BASE, application_scope=_APP,
        api_token="SETTINGS-READ-GRANT",
    )
    assert result["dynatrace_provider_requests"] == 1
    assert result["actual_dynatrace_tenant_consulted"] is True

    result = rum.read_live_dynatrace_action_population(
        base_url=_BASE, application_id=_APP,
        target_url="https://example.org/vida",
        dynatrace_device="MOBILE",
        start_timestamp_ms=1_780_000_000_000,
        end_timestamp_ms=1_780_000_900_000,
        api_token="USQL-READ-GRANT",
    )
    assert result["provider_requests"] == 1
    assert result["action_counts"] == {
        "load": 2, "xhr": 3, "custom": 0, "other": 0,
    }
    assert result["usql_reported_counts_extrapolated"] is True
    assert result["rasai_same_browser_sample_verified"] is False
    assert destinations == [
        (("8.8.4.4", 443), 10.0), (("8.8.4.4", 443), 10.0),
    ]
    assert sni == [_TENANT, _TENANT]
    assert all(sock.closed for sock in sockets)
    wire = b"".join(bytes(sock.sent) for sock in sockets)
    assert b"Api-Token SETTINGS-READ-GRANT" in wire
    assert b"Api-Token USQL-READ-GRANT" in wire
    assert b"8.8.4.4" not in wire
