"""#646: bounded static evidence, late SPA/hydration and HTTPS redirect handling."""
from __future__ import annotations

from dataclasses import replace
from unittest.mock import patch

from rasai.architecture_dom_settle import (
    MAX_SETTLE_MS, ISOLATED_PREVIEW_SETTLE_MS, wait_for_material_dom, DOM_SAMPLE_JS,
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



def test_646_late_spa_update_replaces_early_server_like_content_before_decision():
    """Never certify an SSR-looking first paint at the 850ms checkpoint."""
    initial = "Visible server content that will be replaced by client hydration."
    final = "Different client-side document loaded later in the same page."
    page = _TimedDomPage([
        (0, _dom(initial)),
        (1400, _dom(final)),
    ])
    result = wait_for_material_dom(page, time_source=lambda: page.ms / 1000)
    assert result.stable
    assert result.content_transitions >= 1
    assert result.observed_ms >= 2600
    assert page.ms >= 2600 and page.ms <= MAX_SETTLE_MS


def test_646_materiality_censored_when_final_change_prevents_stable_tail():
    page = _TimedDomPage([
        (0, _dom("Initial server-looking text with a complete title")),
        (2600, _dom("Late conflicting SPA update arrives too close to timeout")),
    ])
    result = wait_for_material_dom(page, time_source=lambda: page.ms / 1000)
    assert not result.stable
    assert result.reason == "ISOLATED_CONTENT_NOT_STABLE"
    assert result.content_transitions == 1
    assert result.observed_ms <= MAX_SETTLE_MS


def test_646_redirect_transport_provenance_is_bounded_and_no_raw_urls_leak():
    from rasai.console_architecture_discovery import describe_architecture_assessment
    target = "http://example.org/private?key=operator-secret"
    final = "https://example.org/private?key=operator-secret"
    original = with_capture_origin(ProbeCaptures(
        target, final, DeviceContext.MOBILE,
        "<main>Server returned the physical document</main>", None,
        "STATIC_MODE_NO_RENDERED_DOM", redirect_chain=(final,),
    ), transport="PINNED_HTTP_STATIC")
    with patch("rasai.architecture_probe._validate_public_url", side_effect=lambda url, _: url):
        result = probe_architecture(target, DeviceContext.MOBILE, capture=lambda *_: original)
    assert result.redirect_hops_reported == 1
    assert result.protocol_transition == "HTTP_TO_HTTPS"
    assert result.acquisition_transport == "PINNED_HTTP_STATIC"
    text = "\n".join(describe_architecture_assessment(result))
    assert "1 redirecionamento(s) HTTP" in text
    assert "HTTP para HTTPS" in text
    assert "operator-secret" not in text
    assert "/private" not in text
    assert result.architecture.value == "UNKNOWN"


def test_menu_preview_delayed_spa_does_not_change_default_dom_budget():
    timeline = [
        (0, _dom("", loading=True)),
        (3400, _dom("The actual SPA content is rendered after the old budget.")),
    ]
    original = _TimedDomPage(timeline)
    default = wait_for_material_dom(original, time_source=lambda: original.ms / 1000)
    assert not default.stable and default.reason == "ISOLATED_CONTENT_NOT_STABLE"
    assert default.bounded_ms == MAX_SETTLE_MS
    assert original.ms <= MAX_SETTLE_MS

    preview = _TimedDomPage(timeline)
    result = wait_for_material_dom(
        preview, time_source=lambda: preview.ms / 1000,
        isolated_preview=True,
    )
    assert result.stable and result.reason is None
    assert result.bounded_ms == ISOLATED_PREVIEW_SETTLE_MS
    assert result.observed_ms >= 5000
    assert preview.ms <= ISOLATED_PREVIEW_SETTLE_MS


def test_menu_preview_detects_change_after_original_ssr_looking_window():
    page = _TimedDomPage([
        (0, _dom("Server-looking text is initially stable before hydration.")),
        (3600, _dom("Client content replaces server text after the old deadline.")),
    ])
    result = wait_for_material_dom(
        page, time_source=lambda: page.ms / 1000, isolated_preview=True,
    )
    assert result.stable and result.content_transitions == 1
    assert result.observed_ms >= 5000


def test_menu_preview_never_accepts_permanent_spinner_or_last_second_change():
    spinner = _TimedDomPage([
        (0, _dom("", loading=True)),
        (3000, _dom("Still fetching content after four seconds", loading=True)),
    ])
    pending = wait_for_material_dom(
        spinner, time_source=lambda: spinner.ms / 1000, isolated_preview=True,
    )
    assert not pending.stable and pending.reason == "ISOLATED_CONTENT_NOT_STABLE"
    assert pending.bounded_ms == ISOLATED_PREVIEW_SETTLE_MS

    changed = _TimedDomPage([
        (0, _dom("Initial material from server visible in main content.")),
        (5000, _dom("Late replacement too close to the final deadline.")),
    ])
    late = wait_for_material_dom(
        changed, time_source=lambda: changed.ms / 1000, isolated_preview=True,
    )
    assert not late.stable and late.content_transitions == 1


def test_menu_preview_rejects_incorrect_opt_in_type():
    import pytest
    page = _TimedDomPage([(0, _dom("Original content of the same page is visible."))])
    with pytest.raises(ValueError, match="boolean"):
        wait_for_material_dom(page, time_source=lambda: page.ms / 1000,
                              isolated_preview=1)
    assert page.ms == 0
