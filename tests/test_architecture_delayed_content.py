"""#646: bounded static evidence, late SPA/hydration and HTTPS redirect handling."""
from __future__ import annotations

from dataclasses import replace
from unittest.mock import patch

from rasai.architecture_dom_settle import (
    MAX_SETTLE_MS, wait_for_material_dom, DOM_SAMPLE_JS,
)
from rasai.architecture_raw_signals import inspect_raw_html_signals
from rasai.architecture_discovery import assess_architecture
from rasai.architecture_probe import ProbeCaptures, probe_architecture, with_capture_origin
from rasai.domain import DeviceContext


def test_646_static_html_exposes_only_bounded_raw_structural_signals():
    html = (
        '<html><body><div id="app"><main>'
        '<h1>Welcome</h1><p>' + 'Important information for clients. ' * 5 +
        '</p></main><script src="/bundle.js"></script>'
        '<script>window.clientApp = true</script>'
        '<div class="skeleton"></div></div></body></html>'
    )
    result = assess_architecture(
        raw_html=html, rendered_html=None,
        quality_reason="STATIC_MODE_NO_RENDERED_DOM",
    )
    assert result.architecture.value == "UNKNOWN"
    assert result.raw_available and not result.rendered_available
    signals = result.raw_signals
    assert signals is not None and signals.status == "RAW_STRUCTURAL_SIGNALS_OBSERVED"
    assert signals.raw_main_text_present
    assert signals.h1_present and signals.app_root_marker_present
    assert signals.external_script_tags == 1 and signals.inline_script_tags == 1
    assert signals.hidden_placeholder_present
    assert signals.rendered_dom_observed is False
    assert signals.architecture_inferred is False
    from rasai.console_architecture_discovery import describe_architecture_assessment
    summary = "\n".join(describe_architecture_assessment(result))
    assert "Sinais observados somente no HTML RAW" in summary
    assert "Classe permanece UNKNOWN" in summary
    assert "Important information for clients" not in summary


def test_646_raw_budget_and_absence_never_infer_rendered_classification():
    assert inspect_raw_html_signals(None).status == "RAW_HTML_UNAVAILABLE"
    assert inspect_raw_html_signals("x" * 1_000_001).status == "RAW_HTML_INVALID_OR_OVERSIZE"
    assert inspect_raw_html_signals("<div>" * 20_001).status == (
        "RAW_HTML_STRUCTURE_UNVERIFIABLE"
    )
    assert inspect_raw_html_signals("<main><p>Short</p></main>").architecture_inferred is False


class _TimedDomPage:
    def __init__(self, timeline):
        self.ms = 0
        self.timeline = sorted(timeline)

    def evaluate(self, expression):
        assert expression == DOM_SAMPLE_JS
        sample = self.timeline[0][1]
        for at, value in self.timeline:
            if self.ms >= at:
                sample = value
        return sample

    def wait_for_timeout(self, delay):
        self.ms += delay


def _dom(text="", *, loading=False, has_main=True):
    return {"text": text, "loading": loading, "hasMain": has_main}


def test_646_late_spa_materiality_with_stable_observed_window():
    page = _TimedDomPage([
        (0, _dom("", loading=True)),
        (400, _dom("Loading...", loading=True)),
        (1200, _dom("The full insurance plan becomes visible only after hydration.")),
    ])
    result = wait_for_material_dom(page, time_source=lambda: page.ms / 1000)
    assert result.stable
    assert result.reason is None
    assert page.ms >= 1200
    assert page.ms <= MAX_SETTLE_MS
    assert result.loading_marker_observed
    assert result.material_text_observed
    assert result.samples >= 5


def test_646_redirected_or_tls_delayed_content_does_not_consume_spa_budget_early():
    page = _TimedDomPage([
        (0, _dom("", has_main=False)),
        (1400, _dom("Loaded content after HTTPS redirect and delayed app hydration")),
    ])
    result = wait_for_material_dom(page, time_source=lambda: page.ms / 1000)
    assert result.stable
    assert page.ms >= 1400


def test_646_unsettled_spinner_or_streaming_dom_abstains_without_infinite_wait():
    page = _TimedDomPage([
        (0, _dom("", loading=True)),
        (500, _dom("Loading...", loading=True)),
        (1800, _dom("Final content not visible", loading=True)),
    ])
    result = wait_for_material_dom(page, time_source=lambda: page.ms / 1000)
    assert result.stable is False
    assert result.reason == "ISOLATED_CONTENT_NOT_STABLE"
    assert page.ms <= MAX_SETTLE_MS


def test_646_verified_host_related_redirect_carries_original_and_final_identity():
    from rasai.architecture_probe import CaptureOriginDigest
    original = "http://example.org/"
    final = "https://www.example.org/"
    base = ProbeCaptures(
        original, final, DeviceContext.MOBILE, "<main>Hello from server</main>",
        None, "STATIC_MODE_NO_RENDERED_DOM", redirect_chain=("https://www.example.org/",),
    )
    observed = with_capture_origin(base, transport="PINNED_HTTP_STATIC")
    assert observed.origin.redirect_chain == observed.redirect_chain
    with patch("rasai.architecture_probe._validate_public_url", side_effect=lambda url, _: url):
        classification = probe_architecture(
            original, DeviceContext.MOBILE, capture=lambda *_: observed,
        )
    assert classification.architecture.value == "UNKNOWN"
    assert classification.raw_signals is not None
    # Tampering after stamping fails even if final URL is a publicly valid address.
    with patch("rasai.architecture_probe._validate_public_url", side_effect=lambda url, _: url):
        try:
            probe_architecture(
                original, DeviceContext.MOBILE,
                capture=lambda *_: replace(observed, redirect_chain=()),
            )
        except ValueError as error:
            assert "digest mismatch" in str(error)
        else:
            raise AssertionError("Tampered redirect origin must be rejected")


def test_646_unproven_cross_host_or_https_downgrade_never_becomes_valid():
    for original, final in (
        ("https://example.org/", "https://other.example.org/"),
        ("https://example.org/", "http://example.org/"),
    ):
        candidate = with_capture_origin(ProbeCaptures(
            original, final, DeviceContext.MOBILE, "<main>content</main>",
            None, "STATIC_MODE_NO_RENDERED_DOM", redirect_chain=(final,),
        ), transport="PINNED_HTTP_STATIC")
        with patch("rasai.architecture_probe._validate_public_url", side_effect=lambda url, _: url):
            try:
                probe_architecture(original, DeviceContext.MOBILE, capture=lambda *_: candidate)
            except ValueError:
                pass
            else:
                raise AssertionError("Cross-host/downgrade classification not allowed")
