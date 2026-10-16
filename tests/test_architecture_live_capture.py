"""Architecture preview network safety is closed by default."""
from unittest.mock import patch

from rasai.architecture_live_capture import capture_public_architecture
from rasai.domain import DeviceContext


def test_no_network_or_browser_without_protected_egress(monkeypatch):
    monkeypatch.delenv("RASAI_ARCH_PROBE_EGRESS_GUARDED", raising=False)
    with patch("rasai.architecture_live_capture.PublicWebFetcher") as fetch, patch(
        "rasai.architecture_live_capture._default_resolver"
    ) as resolver:
        result = capture_public_architecture("https://example.org/", DeviceContext.MOBILE)
    assert result.quality_reason == "SAFE_EGRESS_NOT_CONFIGURED"
    assert result.raw_html is None
    assert result.rendered_html is None
    fetch.assert_not_called()
    resolver.assert_not_called()


def test_guarded_egress_requires_exact_opt_in(monkeypatch):
    monkeypatch.setenv("RASAI_ARCH_PROBE_EGRESS_GUARDED", "true")
    with patch("rasai.architecture_live_capture.PublicWebFetcher") as fetch:
        result = capture_public_architecture("https://example.org/", DeviceContext.DESKTOP)
    assert result.quality_reason == "SAFE_EGRESS_NOT_CONFIGURED"
    fetch.assert_not_called()


def test_guarded_http_uses_pinned_ip_transport(monkeypatch):
    from rasai.geo_competitor_pinned_egress import PublicWebPinnedOpener
    monkeypatch.setenv("RASAI_ARCH_PROBE_EGRESS_GUARDED", "1")
    with patch("rasai.architecture_live_capture._validate_public_url", side_effect=lambda url, resolver: url), patch(
        "rasai.architecture_live_capture.PublicWebFetcher"
    ) as fetch:
        fetch.return_value.fetch.return_value.status = "BLOCKED"
        fetch.return_value.fetch.return_value.final_url = None
        value = capture_public_architecture("https://example.org/", DeviceContext.MOBILE)
    assert value.quality_reason == "HTTP_CAPTURE_UNAVAILABLE"
    assert isinstance(fetch.call_args.kwargs["opener"], PublicWebPinnedOpener)
    assert fetch.call_args.kwargs["max_redirects"] == 0
    assert fetch.call_args.kwargs["max_bytes"] == 1_000_000


class _FakeRequest:
    def __init__(self, url: str, method: str = "GET"):
        self.url = url
        self.method = method


class _FakeRoute:
    def __init__(self, url: str, method: str = "GET"):
        self.request = _FakeRequest(url, method)
        self.action = None

    def abort(self):
        self.action = "abort"

    def continue_(self):
        self.action = "continue"


class _FakeWebSocket:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True

    def connect(self):
        raise AssertionError("WebSocket must not contact the target")


class _FakeBrowserContext:
    def __init__(self):
        self.routes = []
        self.ws_routes = []
        self.page_created = False

    def route(self, pattern, handler):
        assert not self.page_created
        self.routes.append((pattern, handler))

    def route_web_socket(self, pattern, handler):
        assert not self.page_created
        self.ws_routes.append((pattern, handler))

    def new_page(self):
        assert self.routes and self.ws_routes
        self.page_created = True


def test_browser_routes_cover_popups_and_websockets_before_page_creation():
    from rasai.architecture_live_capture import install_architecture_browser_routes
    ctx = _FakeBrowserContext()
    gate = install_architecture_browser_routes(
        ctx, "https://example.org/", resolver=lambda _host, _port: ("93.184.215.14",)
    )
    assert ctx.routes[0][0] == "**/*"
    assert ctx.ws_routes[0][0] == "**/*"
    ctx.new_page()
    socket = _FakeWebSocket()
    ctx.ws_routes[0][1](socket)
    assert socket.closed
    assert gate.blocked == 1


def test_browser_route_refuses_post_cross_origin_private_and_excess(monkeypatch):
    from rasai.architecture_live_capture import install_architecture_browser_routes
    ctx = _FakeBrowserContext()
    with patch("rasai.architecture_live_capture._validate_public_url", side_effect=lambda url, _resolver: url):
        gate = install_architecture_browser_routes(ctx, "https://example.org/", max_requests=2)
        handler = ctx.routes[0][1]
        same = _FakeRoute("https://example.org/script.js")
        handler(same)
        post = _FakeRoute("https://example.org/action", "POST")
        handler(post)
        cross = _FakeRoute("https://attacker.example.org/")
        handler(cross)
    assert same.action == "continue"
    assert post.action == cross.action == "abort"
    assert gate.requested == 3
    assert gate.blocked == 2


def test_browser_route_rejects_dns_validation_failure():
    from rasai.architecture_live_capture import install_architecture_browser_routes
    ctx = _FakeBrowserContext()
    def reject(_url, _resolver):
        raise ValueError("Private destination")
    with patch("rasai.architecture_live_capture._validate_public_url", side_effect=reject):
        install_architecture_browser_routes(ctx, "https://example.org/")
        route = _FakeRoute("https://example.org/resource.js")
        ctx.routes[0][1](route)
    assert route.action == "abort"


def test_browser_guard_registration_does_not_suffice_as_egress_proof():
    from rasai.architecture_live_capture import install_architecture_browser_routes
    ctx = _FakeBrowserContext()
    gate = install_architecture_browser_routes(ctx, "https://example.org/")
    assert gate.requested == 0
    assert gate.blocked == 0
    # The external egress attestation remains mandatory. This API only
    # bounds/blocks application requests, not Chromium's native sockets.
