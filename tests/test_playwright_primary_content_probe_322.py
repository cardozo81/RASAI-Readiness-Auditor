"""#322: focused fake-Playwright safety tests; no navigation, AI, network, SQLite."""
from __future__ import annotations

from rasai.playwright_primary_content_probe_322 import observe_existing_playwright_page


class Clock:
    def __init__(self, since_ms=300):
        self.origin_ns = 1_000_000_000
        self.now = self.origin_ns + since_ms * 1_000_000

    def read(self):
        return self.now

    def sleep(self, seconds):
        self.now += int(seconds * 1_000_000_000)


class Page:
    def __init__(self, values):
        self.values = list(values)
        self.calls = 0
        self.script = None

    def evaluate(self, script):
        self.calls += 1
        self.script = script
        return self.values[min(self.calls - 1, len(self.values) - 1)]


READY = {
    "main_text_characters": 430,
    "heading_text_characters": 21,
    "skeleton_present": False,
}
LOADING = {
    "main_text_characters": 0,
    "heading_text_characters": 0,
    "skeleton_present": True,
}


def run(page, clock=None, **kwargs):
    clock = clock or Clock()
    fields = dict(
        page=page, sample_id="M25-X", context_id="CTX-X", page_id="PAGE-X",
        device="MOBILE", architecture="CSR_SPA",
        navigation_started_monotonic_ns=clock.origin_ns,
        load_ms=200, enabled=True, window_ms=750, poll_ms=125,
        monotonic_ns=clock.read, sleep=clock.sleep,
    )
    fields.update(kwargs)
    return observe_existing_playwright_page(**fields)


def test_existing_page_only_and_stable_materiality_after_load():
    page = Page([READY, READY])
    result = run(page)
    assert result.status == "OBSERVED"
    assert result.primary_content_ms == 300
    assert result.post_load_delta_ms == 100
    assert result.sample_id == "M25-X" and result.context_id == "CTX-X"
    assert result.page_id == "PAGE-X" and result.device == "MOBILE"
    assert page.calls == 2
    assert "document.querySelector" in page.script
    assert "fetch(" not in page.script and "goto(" not in page.script


def test_opt_out_static_and_unknown_cannot_probe_page():
    for arch, enabled in (("CSR_SPA", False), ("STATIC_OR_SSR", True), ("UNKNOWN", True)):
        page = Page([READY])
        outcome = run(page, architecture=arch, enabled=enabled)
        assert outcome.status == "NOT_APPLICABLE"
        assert page.calls == 0


def test_skeleton_and_incomplete_main_are_never_observed():
    page = Page([LOADING] * 10)
    observed = run(page)
    assert observed.status == "TIMEOUT"
    assert observed.post_load_delta_ms is None
    assert page.calls <= 7
    incomplete = run(Page([
        dict(READY, heading_text_characters=0),
        dict(READY, heading_text_characters=0),
    ]))
    assert incomplete.status == "TIMEOUT"


def test_probe_abstains_without_real_same_sample_origin_or_live_page():
    invalid = run(Page([READY]), navigation_started_monotonic_ns=None)
    assert invalid.status == "ERROR"
    assert invalid.reason == "invalid_same_sample_clock_or_poll"
    missing = run(None)
    assert missing.status == "ERROR"
    assert missing.reason == "missing_live_browser_page"
    wrong_context = run(Page([READY]), page_id="")
    assert wrong_context.status == "ERROR"
    assert wrong_context.reason == "missing_page_or_device_identity"


def test_probe_failure_is_bounded_and_does_not_leak_browser_exception():
    class BrokenPage:
        def evaluate(self, _script):
            raise RuntimeError("SECRET_CONTENT_DO_NOT_LOG")

    failure = run(BrokenPage())
    assert failure.status == "ERROR"
    assert failure.reason == "same_sample_dom_probe_failed"
    assert "SECRET" not in failure.reason


def test_overbudget_dom_read_censors_and_never_returns_false_ready():
    clock = Clock(since_ms=850)
    page = Page([READY])
    # Window ends at 950ms; DOM evaluation consumes 200ms.
    class SlowPage(Page):
        def evaluate(self, script):
            value = super().evaluate(script)
            clock.now += 200_000_000
            return value

    slow = SlowPage([READY])
    result = run(slow, clock=clock)
    assert result.status == "TIMEOUT"
    assert result.primary_content_ms is None
    assert slow.calls == 1


def test_bad_dom_types_and_nonmonotonic_clock_fail_closed():
    assert run(Page([dict(READY, main_text_characters="400")])).reason == (
        "invalid_dom_probe_response"
    )
    assert run(Page([dict(READY, skeleton_present=1)])).status == "ERROR"
    bad_clock = Clock()
    bad_clock.now = bad_clock.origin_ns - 1
    assert run(Page([READY]), clock=bad_clock).reason == "inconsistent_monotonic_origin"
