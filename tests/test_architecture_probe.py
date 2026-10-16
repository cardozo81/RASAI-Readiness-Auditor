"""Architecture probe: no network without a supplied transport."""
from unittest.mock import patch
import pytest
from rasai.architecture_probe import probe_architecture, ProbeCaptures
from rasai.domain import ArchitectureClassification, DeviceContext


def test_probe_reuses_assessment_without_any_audit_runtime():
    target = "https://example.org/"
    body = "<html><main>Public content visible.</main></html>"
    with patch("rasai.architecture_probe._validate_public_url", side_effect=lambda u, _: u), patch(
        "rasai.architecture_probe.assess_architecture"
    ) as assess:
        probe_architecture(target, DeviceContext.MOBILE, capture=lambda url, device:
            ProbeCaptures(url, url, device, body, body))
        assert assess.call_count == 1
        assert assess.call_args.kwargs["raw_html"] == body


def test_mismatched_capture_identity_fails_closed():
    target = "https://example.org/"
    with patch("rasai.architecture_probe._validate_public_url", side_effect=lambda u, _: u):
        with pytest.raises(ValueError, match="identity"):
            probe_architecture(target, DeviceContext.MOBILE, capture=lambda url, device:
                ProbeCaptures(url, url, DeviceContext.DESKTOP, "", ""))


def test_unvalidated_redirect_fails_closed():
    target = "https://example.org/"
    with patch("rasai.architecture_probe._validate_public_url", side_effect=lambda u, _: u):
        with pytest.raises(ValueError, match="final URL"):
            probe_architecture(target, DeviceContext.MOBILE, capture=lambda url, device:
                ProbeCaptures(url, "https://other.example.org/", device, "", ""))

def test_inconclusive_capture_does_not_resolve_dns():
    target = "https://example.org/"
    with patch("rasai.architecture_probe._default_resolver") as resolve:
        result = probe_architecture(target, DeviceContext.MOBILE, capture=lambda url, device:
            ProbeCaptures(url, url, device, None, None, "SAFE_EGRESS_NOT_CONFIGURED"))
    resolve.assert_not_called()
    assert result.architecture is ArchitectureClassification.UNKNOWN
    assert result.limitation == "SAFE_EGRESS_NOT_CONFIGURED"
