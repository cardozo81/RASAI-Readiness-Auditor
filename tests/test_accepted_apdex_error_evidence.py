from __future__ import annotations

from types import SimpleNamespace

from rasai import accepted_apdex_error_evidence as evidence
from rasai.accepted_apdex_error_evidence_compat import install as install_compat


class _FakePage:
    def __init__(self) -> None:
        self.handlers = {}

    def on(self, event, handler):
        self.handlers[event] = handler
        return self


class _FakeContext:
    def __init__(self) -> None:
        self.page = _FakePage()
        self.cdp_page = None

    def new_page(self):
        return self.page

    def new_cdp_session(self, page):
        self.cdp_page = page
        return "session"


def test_page_proxy_collects_scoped_error_evidence() -> None:
    page = _FakePage()
    proxy = evidence._PageProxy(page)
    called = []
    evidence._begin_capture("https://www.example.com/page")
    try:
        proxy.on("requestfailed", lambda request: called.append("request"))
        proxy.on("response", lambda response: called.append("response"))
        proxy.on("console", lambda message: called.append("console"))
        proxy.on("pageerror", lambda error: called.append("js"))

        request = SimpleNamespace(
            url="https://cdn.example.net/app.js",
            resource_type="script",
            failure="net::ERR_FAILED",
        )
        page.handlers["requestfailed"](request)
        first_party_request = SimpleNamespace(resource_type="xhr")
        response = SimpleNamespace(
            status=503,
            url="https://example.com/api",
            request=first_party_request,
        )
        page.handlers["response"](response)
        message = SimpleNamespace(
            type="error",
            text="widget failed",
            location={"url": "https://third.example/widget.js"},
        )
        page.handlers["console"](message)
        page.handlers["pageerror"](RuntimeError("boom"))
        details = evidence._finish_capture()
    finally:
        # Idempotent cleanup if the assertion path exits early.
        evidence._finish_capture()

    assert called == ["request", "response", "console", "js"]
    assert [item["error_type"] for item in details] == [
        "REQUEST_FAILED", "HTTP_ERROR", "CONSOLE_ERROR", "JAVASCRIPT_ERROR"
    ]
    assert details[0]["first_party"] is False
    assert details[1]["first_party"] is True
    assert details[1]["http_status"] == 503
    assert details[2]["source_url"] == "https://third.example/widget.js"


def test_context_proxy_unwraps_page_for_cdp_session() -> None:
    install_compat()
    context = _FakeContext()
    proxy = evidence._ContextProxy(context)
    page_proxy = proxy.new_page()

    assert proxy.new_cdp_session(page_proxy) == "session"
    assert context.cdp_page is context.page
