from __future__ import annotations

from rasai.device_context_capture import _same_session_lazy_probe
from rasai.javascript_spa import JavascriptSpaAnalyzer
from rasai.m6 import _evaluate_024_same_session
from rasai.domain import RuleResult


class _Page:
    def __init__(self, after_html: str) -> None:
        self.after_html = after_html
        self.scrolls = 0
        self.waits: list[int] = []

    def evaluate(self, script: str) -> None:
        assert "scrollBy" in script
        self.scrolls += 1

    def wait_for_timeout(self, milliseconds: int) -> None:
        self.waits.append(milliseconds)

    def content(self) -> str:
        return self.after_html


def test_lazy_probe_reuses_same_page_without_navigation() -> None:
    initial = "<html><body><img loading='lazy' data-src='/hero.jpg'></body></html>"
    page = _Page("<html><body><main>Conteúdo carregado após scroll</main></body></html>")

    metadata = _same_session_lazy_probe(page, initial)

    assert metadata["attempted"] is True
    assert metadata["state"] == "CAPTURED"
    assert metadata["after_probe_content_recoverable"] is True
    assert metadata["additional_navigation_requests"] == 0
    assert metadata["capture_method"] == "SAME_PAGE_BOUNDED_SCROLL"
    assert page.scrolls == 3
    assert page.waits == [250, 250, 250]


def test_m6_consumes_same_session_result_without_html_refetch() -> None:
    initial = "<html><body><img loading='lazy' data-src='/hero.jpg'></body></html>"
    preliminary = JavascriptSpaAnalyzer().lazy_loading(initial, after_probe_html=None)
    evaluation = _evaluate_024_same_session(
        preliminary,
        {
            "attempted": True,
            "state": "CAPTURED",
            "after_probe_content_recoverable": True,
            "capture_method": "SAME_PAGE_BOUNDED_SCROLL",
            "additional_navigation_requests": 0,
            "scroll_steps": 3,
            "settle_ms": 250,
        },
    )

    assert evaluation.result is RuleResult.PASS
    assert evaluation.reason == "CONTENT_RECOVERED_BY_BOUNDED_SCROLL"
    assert evaluation.observed_value["additional_navigation_requests"] == 0
