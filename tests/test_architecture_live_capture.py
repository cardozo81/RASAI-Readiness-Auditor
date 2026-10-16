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
