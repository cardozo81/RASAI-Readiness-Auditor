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


def test_legacy_flag_cannot_launch_native_browser(monkeypatch):
    monkeypatch.setenv("RASAI_ARCH_PROBE_EGRESS_GUARDED", "1")
    monkeypatch.delenv("RASAI_ARCH_PROBE_OFFLINE_CONTAINER", raising=False)
    with patch("rasai.architecture_live_capture._default_resolver") as resolver:
        result = capture_public_architecture("https://example.org/", DeviceContext.MOBILE)
    assert result.quality_reason == "SAFE_EGRESS_NOT_CONFIGURED"
    resolver.assert_not_called()


def test_explicit_sandbox_flag_delegates_without_native_chromium(monkeypatch):
    monkeypatch.setenv("RASAI_ARCH_PROBE_OFFLINE_CONTAINER", "1")
    with patch("rasai.architecture_isolated_capture.capture_isolated_public_architecture") as capture:
        capture.return_value = "isolated"
        assert capture_public_architecture("https://example.org/", DeviceContext.MOBILE) == "isolated"
    capture.assert_called_once()



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
        raise AssertionError("Native Chromium egress must never be permitted")

    def fulfill(self, *, status, body, headers):
        self.action = "fulfill"
        self.response = (status, body, headers)


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
        from types import SimpleNamespace
        resource = SimpleNamespace(
            status="OBSERVED", final_url="https://example.org/script.js",
            http_status=200, body=b"console.log('ok')",
            headers={"content-type": "application/javascript"},
        )
        class FakeFetcher:
            def fetch(self, _url):
                return resource
        gate = install_architecture_browser_routes(
            ctx, "https://example.org/", max_requests=2,
            resource_fetcher=FakeFetcher(),
        )
        handler = ctx.routes[0][1]
        same = _FakeRoute("https://example.org/script.js")
        handler(same)
        post = _FakeRoute("https://example.org/action", "POST")
        handler(post)
        cross = _FakeRoute("https://attacker.example.org/")
        handler(cross)
    assert same.action == "fulfill"
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


def test_root_navigation_uses_existing_pinned_snapshot_without_second_fetch(monkeypatch):
    from rasai.architecture_live_capture import install_architecture_browser_routes
    from types import SimpleNamespace
    source = SimpleNamespace(
        status="OBSERVED", final_url="https://example.org/",
        http_status=200, body=b"<html><main>same bytes</main></html>",
        headers={"content-type": "text/html; charset=utf-8",
                 "set-cookie": "session=secret",
                 "content-security-policy": "default-src 'self'"},
    )
    class ExplodingFetcher:
        def fetch(self, _url):
            raise AssertionError("Do not refetch the initial document")
    ctx = _FakeBrowserContext()
    with patch("rasai.architecture_live_capture._validate_public_url", side_effect=lambda url, _resolver: url):
        install_architecture_browser_routes(
            ctx, "https://example.org/", initial_document=source,
            resource_fetcher=ExplodingFetcher(),
        )
        navigation = _FakeRoute("https://example.org/")
        ctx.routes[0][1](navigation)
    assert navigation.action == "fulfill"
    status, body, headers = navigation.response
    assert status == 200 and body == source.body
    assert headers["content-security-policy"] == "default-src 'self'"
    assert "set-cookie" not in headers


def test_pinned_resource_enforces_response_identity_and_global_byte_budget(monkeypatch):
    from rasai.architecture_live_capture import install_architecture_browser_routes
    from types import SimpleNamespace
    responses = [
        SimpleNamespace(status="OBSERVED", final_url="https://example.org/a.js",
                        http_status=200, body=b"12345",
                        headers={"content-type": "text/javascript"}),
        SimpleNamespace(status="OBSERVED", final_url="https://example.org/b.js",
                        http_status=200, body=b"67890",
                        headers={"content-type": "text/javascript"}),
        SimpleNamespace(status="OBSERVED", final_url="https://example.org/other",
                        http_status=200, body=b"1",
                        headers={"content-type": "text/javascript"}),
    ]
    class Fetcher:
        def fetch(self, _url):
            return responses.pop(0)
    ctx = _FakeBrowserContext()
    with patch("rasai.architecture_live_capture._validate_public_url", side_effect=lambda url, _resolver: url):
        gate = install_architecture_browser_routes(
            ctx, "https://example.org/", resource_fetcher=Fetcher(), max_total_bytes=8,
        )
        first, second, third = (
            _FakeRoute("https://example.org/a.js"),
            _FakeRoute("https://example.org/b.js"),
            _FakeRoute("https://example.org/c.js"),
        )
        for request in (first, second, third):
            ctx.routes[0][1](request)
    assert first.action == "fulfill"
    assert second.action == "abort"  # total would exceed 8 bytes
    assert third.action == "abort"   # final URL identity does not match
    assert gate.blocked == 2


def test_browser_pinned_fetcher_default_has_no_redirects_and_numeric_ip(monkeypatch):
    from rasai.architecture_live_capture import install_architecture_browser_routes
    from rasai.geo_competitor_pinned_egress import PublicWebPinnedOpener
    ctx = _FakeBrowserContext()
    install_architecture_browser_routes(ctx, "https://example.org/")
    handler = ctx.routes[0][1]
    fetcher = handler.__closure__
    assert fetcher  # Browser safety is enforced by the closure-bound transport.
    # Never enable native routing: this is a deliberate contract even when
    # a browser DNS preflight resolves a public IP.
    assert "continue_" not in handler.__code__.co_names
    assert "fetch" in handler.__code__.co_names


def test_fetch_failure_aborts_instead_of_native_fallback(monkeypatch):
    from rasai.architecture_live_capture import install_architecture_browser_routes
    class FailedFetcher:
        def fetch(self, _url):
            raise OSError("simulated network failure")
    ctx = _FakeBrowserContext()
    with patch("rasai.architecture_live_capture._validate_public_url", side_effect=lambda url, _resolver: url):
        gate = install_architecture_browser_routes(
            ctx, "https://example.org/", resource_fetcher=FailedFetcher()
        )
        route = _FakeRoute("https://example.org/a.js")
        ctx.routes[0][1](route)
    assert route.action == "abort" and gate.blocked == 1
