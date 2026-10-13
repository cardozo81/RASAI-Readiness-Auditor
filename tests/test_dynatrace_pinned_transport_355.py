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
    assert dns == [(_TENANT, None), (_TENANT, 443)]
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


@pytest.mark.parametrize("raw_json", [
    '{"items":[],"totalCount":0,"totalCount":0}',
    '{"items":[{"schemaId":"bad"}],"items":[],"totalCount":0}',
    (
        '{"items":[{"schemaId":'
        '"builtin:rum.web.key-performance-metric-load-actions",'
        '"value":{"thresholds":{"toleratedThresholdSeconds":2,'
        '"toleratedThresholdSeconds":4}}}],"totalCount":1}'
    ),
])
def test_live_settings_duplicate_json_keys_are_rejected_without_claiming_scope(
    raw_json,
):
    """#355: root/nested last-key-wins may not forge effective settings."""
    class Reply:
        headers = {"Content-Type": "application/json"}
        def __enter__(self): return self
        def __exit__(self, *_): return False
        def getcode(self): return 200
        def read(self, size): return raw_json.encode("utf-8")[:size]

    class MemoryOpener:
        def __init__(self): self.requests = []
        def open(self, request, timeout):
            self.requests.append((request, timeout))
            return Reply()

    fake = MemoryOpener()
    with pytest.raises(ValueError, match="Settings API response is not valid JSON") as err:
        settings.read_live_dynatrace_apdex_settings(
            base_url=_BASE, application_scope=_APP,
            api_token="PRIVATE-SETTINGS-TOKEN", opener=fake,
        )
    assert len(fake.requests) == 1
    assert fake.requests[0][1] == 10
    assert "PRIVATE-SETTINGS-TOKEN" not in str(err.value)
    assert _BASE not in str(err.value)


@pytest.mark.parametrize(
    ("media", "accepted"),
    [
        ("application/json", True),
        ("Application/JSON; charset=UTF-8", True),
        ("text/html", False),
        ("application/problem+json", False),
        ("application/vnd.api+json", False),
        ("application/jsonp", False),
        ("", False),
    ],
)
def test_live_settings_only_accepts_documented_json_response_media_type(
    media, accepted,
):
    """#355: MIME identity is verified, not inferred from JSON-shaped body."""
    class Reply:
        headers = {"Content-Type": media}
        def __init__(self): self.reads = 0
        def __enter__(self): return self
        def __exit__(self, *_): return False
        def getcode(self): return 200
        def read(self, size):
            self.reads += 1
            return b'{"items":[],"totalCount":0}'

    class InMemoryTransport:
        def __init__(self):
            self.requests = []
            self.response = Reply()
        def open(self, request, timeout):
            self.requests.append((request, timeout))
            return self.response

    fake = InMemoryTransport()
    args = dict(
        base_url=_BASE, application_scope=_APP,
        api_token="PRIVATE-SETTINGS-TOKEN", opener=fake,
    )
    if accepted:
        out = settings.read_live_dynatrace_apdex_settings(**args)
        assert out["actual_dynatrace_tenant_consulted"] is True
        assert out["dynatrace_provider_requests"] == 1
        assert fake.response.reads == 1
    else:
        with pytest.raises(ValueError, match="Settings API response is not JSON") as exc:
            settings.read_live_dynatrace_apdex_settings(**args)
        assert fake.response.reads == 0
        assert "PRIVATE-SETTINGS-TOKEN" not in str(exc.value)
        assert _BASE not in str(exc.value)
    assert len(fake.requests) == 1
    assert fake.requests[0][1] == 10
    assert "PRIVATE-SETTINGS-TOKEN" not in fake.requests[0][0].full_url


@pytest.mark.parametrize("non_json_number", ["NaN", "Infinity", "-Infinity"])
def test_live_settings_rejects_nonstandard_json_numeric_constants(
    non_json_number,
):
    """#355: Python decoder extensions may not attest Settings API JSON."""
    malformed = (
        '{"items":[],"totalCount":0,"ignored":'
        + non_json_number + '}'
    )

    class Reply:
        headers = {"Content-Type": "application/json"}
        def __enter__(self): return self
        def __exit__(self, *_): return False
        def getcode(self): return 200
        def read(self, size): return malformed.encode("utf-8")[:size]

    class MemoryOpener:
        def __init__(self): self.calls = []
        def open(self, request, timeout):
            self.calls.append((request, timeout))
            return Reply()

    fake = MemoryOpener()
    with pytest.raises(ValueError, match="Settings API response is not valid JSON") as exc:
        settings.read_live_dynatrace_apdex_settings(
            base_url=_BASE, application_scope=_APP,
            api_token="PRIVATE-SETTINGS-TOKEN", opener=fake,
        )
    assert len(fake.calls) == 1
    assert fake.calls[0][1] == 10
    assert "PRIVATE-SETTINGS-TOKEN" not in str(exc.value)
    assert _BASE not in str(exc.value)


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


@pytest.mark.parametrize(
    ("length_policy", "expected_error", "reads"),
    [
        ("exact", None, 1),
        ("absent", None, 1),
        ("understated", "response length mismatch", 1),
        ("overstated", "response length mismatch", 1),
        ("non_numeric", "content length invalid", 0),
        ("ambiguous", "content length invalid", 0),
        ("unbounded", "exceeds bounded size", 0),
    ],
)
def test_355_live_settings_refuses_truncated_or_ambiguous_http_body_length(
    length_policy, expected_error, reads,
):
    """A parseable partial HTTP body cannot be authenticated as a whole page."""
    raw = b'{"items":[],"totalCount":0}'

    class Reply:
        def __init__(self):
            self.reads = 0
            self.headers = {"Content-Type": "application/json"}
            length = {
                "exact": str(len(raw)),
                "understated": str(len(raw) - 1),
                "overstated": str(len(raw) + 7),
                "non_numeric": "invalid",
                "ambiguous": f"{len(raw)},{len(raw)}",
                "unbounded": str(1024 * 1024 + 1),
            }.get(length_policy)
            if length is not None:
                self.headers["Content-Length"] = length

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def getcode(self):
            return 200

        def read(self, size):
            self.reads += 1
            assert size == 1024 * 1024 + 1
            return raw[:size]

    class MemoryOpener:
        def __init__(self):
            self.requests = []
            self.response = Reply()

        def open(self, request, timeout):
            self.requests.append((request, timeout))
            return self.response

    opener = MemoryOpener()
    params = {
        "base_url": _BASE,
        "application_scope": _APP,
        "api_token": "DO-NOT-RENDER-TEST-TOKEN",
        "opener": opener,
    }
    if expected_error:
        with pytest.raises(ValueError, match=expected_error) as caught:
            settings.read_live_dynatrace_apdex_settings(**params)
        assert "DO-NOT-RENDER-TEST-TOKEN" not in str(caught.value)
        assert _BASE not in str(caught.value)
    else:
        result = settings.read_live_dynatrace_apdex_settings(**params)
        assert result["settings_provenance"] == (
            "LIVE_DYNATRACE_SETTINGS_API_EFFECTIVE_VALUES"
        )
        assert result["actual_dynatrace_tenant_consulted"] is True
        assert result["rum_action_population_verified"] is False
    assert len(opener.requests) == 1
    assert opener.response.reads == reads
