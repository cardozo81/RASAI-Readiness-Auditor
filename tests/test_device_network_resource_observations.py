"""Bounded resource capture contract without HTTP requests or a browser."""
from rasai.device_context_capture import _observed_resource_metadata


def test_response_metadata_is_limited_without_new_egress():
    rows = {
        str(i): {"resource_type": "Stylesheet", "host": "cdn.example.org",
                 "status": 200} for i in range(180)
    }
    got = _observed_resource_metadata({
        "available": True, "resource_responses": rows,
        "resource_response_truncated": True,
    })
    assert got["count"] == 160
    assert len(got["items"]) == 160
    assert got["truncated"] is True
    assert got["additional_network_requests"] == 0


def test_network_unavailable_is_not_claimed_as_zero_capture():
    result = _observed_resource_metadata({})
    assert result["state"] == "UNAVAILABLE"
    assert result["count"] == 0
    assert result["additional_network_requests"] == 0



def test_cdp_same_page_observes_fetch_stylesheet_subframes_and_public_tls_only():
    from rasai.device_context_capture import _setup_document_capture

    class FakeCDP:
        def __init__(self):
            self.events = {}
        def send(self, action, args=None):
            return {"frameTree": {"frame": {"id": "main"}}} if action == "Page.getFrameTree" else {}
        def on(self, name, callback):
            self.events[name] = callback

    class Context:
        def __init__(self):
            self.cdp = FakeCDP()
        def new_cdp_session(self, _page):
            return self.cdp

    context = Context()
    _session, capture = _setup_document_capture(context, object())
    handler = context.cdp.events["Network.responseReceived"]
    handler({"type":"Document", "frameId":"main", "requestId":"main",
             "response":{"url":"https://www.example.org/","protocol":"h2",
                 "remoteIPAddress":"8.8.8.8",
                 "securityDetails":{"protocol":"TLS 1.3","issuer":"Public CA",
                                    "subjectName":"www.example.org",
                                    "validFrom":1790000000,"validTo":1900000000}}})
    handler({"type":"Document", "frameId":"frame2", "requestId":"sub",
             "response":{"url":"https://third.example.org/frame?token=private","status":200}})
    handler({"type":"Stylesheet","requestId":"css",
             "response":{"url":"https://cdn.example.org/app.css?key=hidden","status":200}})
    handler({"type":"Fetch","requestId":"api",
             "response":{"url":"https://api.example.org/internal?token=secret","status":201}})
    handler({"type":"Document", "frameId":"main", "requestId":"again",
             "response":{"url":"http://www.example.org/","remoteIPAddress":"10.0.0.1"}})
    items=_observed_resource_metadata(capture)["items"]
    assert len(items) == 3
    assert {x["resource_type"] for x in items} == {"SubframeDocument","Stylesheet","Fetch"}
    assert "secret" not in repr(items)
    assert "hidden" not in repr(items)
    assert "token" not in repr(items)
    assert capture["main_response_network"]["remote_public_peer_ip"] is None



def test_navigation_response_fallback_uses_same_connection_and_preserves_cdp():
    from rasai.device_context_capture import _backfill_main_public_peer_from_navigation

    class Response:
        url = "https://www.example.org/path?session=do-not-store"
        calls = 0

        def server_addr(self):
            self.calls += 1
            return {"ipAddress": "8.8.4.4", "port": 443}

    existing = {"state": "OBSERVED_MAIN_DOCUMENT_RESPONSE",
                "remote_public_peer_ip": None,
                "from_service_worker": False, "from_disk_cache": False}
    capture = {"response_url": "https://www.example.org/path",
               "main_response_network": existing}
    response = Response()
    _backfill_main_public_peer_from_navigation(response, capture)
    assert existing["remote_public_peer_ip"] == "8.8.4.4"
    assert existing["remote_public_peer_ip_source"] == "PLAYWRIGHT_MAIN_NAVIGATION_RESPONSE_SERVER_ADDR"
    assert response.calls == 1

    # An already observed CDP peer remains authoritative.
    existing["remote_public_peer_ip"] = "8.8.8.8"
    _backfill_main_public_peer_from_navigation(response, capture)
    assert existing["remote_public_peer_ip"] == "8.8.8.8"
    assert response.calls == 1


def test_navigation_peer_fallback_rejects_unattributed_cached_and_private():
    from rasai.device_context_capture import _backfill_main_public_peer_from_navigation

    class Response:
        def __init__(self, url, addr):
            self.url, self.addr = url, addr

        def server_addr(self):
            return {"ipAddress": self.addr, "port": 443}

    for overrides, url, ip in (
        ({}, "https://different.example.org/", "8.8.4.4"),
        ({}, "https://www.example.org/", "10.0.0.1"),
        ({"from_service_worker": True}, "https://www.example.org/", "8.8.4.4"),
        ({"from_disk_cache": True}, "https://www.example.org/", "8.8.4.4"),
    ):
        observed = {"state": "OBSERVED_MAIN_DOCUMENT_RESPONSE",
                    "remote_public_peer_ip": None, **overrides}
        capture = {"response_url": "https://www.example.org/",
                   "main_response_network": observed}
        _backfill_main_public_peer_from_navigation(Response(url, ip), capture)
        assert observed["remote_public_peer_ip"] is None
        assert "remote_public_peer_ip_source" not in observed


def test_navigation_peer_fallback_is_optional_if_server_address_unavailable():
    from rasai.device_context_capture import _backfill_main_public_peer_from_navigation

    class Response:
        url = "https://www.example.org/"

        def server_addr(self):
            raise RuntimeError("Browser server address unavailable")

    observed = {"state": "OBSERVED_MAIN_DOCUMENT_RESPONSE",
                "remote_public_peer_ip": None}
    _backfill_main_public_peer_from_navigation(
        Response(), {"response_url": Response.url, "main_response_network": observed}
    )
    assert observed["remote_public_peer_ip"] is None
