"""Optional acquisition service never blocks independent audit paths."""
from types import SimpleNamespace
from unittest.mock import Mock, patch

from rasai.architecture_acquisition_preferences import STATIC, DYNAMIC, SKIP
from rasai.architecture_acquisition_service import run_optional_discovery
from rasai.architecture_probe import ProbeCaptures
from rasai.domain import DeviceContext


URL = "https://example.org/"
DEVICE = DeviceContext.MOBILE


def test_skip_never_prepares_or_captures_or_consent():
    consent = Mock(side_effect=AssertionError("no consent"))
    prepare = Mock(side_effect=AssertionError("no prepare"))
    capture = Mock(side_effect=AssertionError("no capture"))
    result = run_optional_discovery(
        URL, DEVICE, mode=SKIP, consent=consent,
        static_capture=capture, dynamic_capture=capture, prepare=prepare,
    )
    assert not result.executed and result.reason == "DISCOVERY_DECLINED"
    assert result.assessment.architecture.value == "UNKNOWN"
    consent.assert_not_called()
    prepare.assert_not_called()
    capture.assert_not_called()


def test_static_requires_no_docker_and_cannot_fabricate_rendered_dom():
    prepare = Mock(side_effect=AssertionError("Docker must not run"))
    capture = Mock(return_value=ProbeCaptures(
        URL, URL, DEVICE, "<main>Server content</main>", None,
        "STATIC_MODE_NO_RENDERED_DOM",
    ))
    result = run_optional_discovery(
        URL, DEVICE, mode=STATIC, consent=lambda _: False,
        static_capture=capture, prepare=prepare,
    )
    assert result.executed and result.assessment.architecture.value == "UNKNOWN"
    assert result.reason == "STATIC_MODE_NO_RENDERED_DOM"
    prepare.assert_not_called()
    capture.assert_called_once()


def test_dynamic_refusal_never_starts_browser_or_http():
    capture = Mock(side_effect=AssertionError("browser must not run"))
    prepare = Mock(return_value=SimpleNamespace(
        ready=False, reason="PREREQUISITE_DECLINED",
    ))
    result = run_optional_discovery(
        URL, DEVICE, mode=DYNAMIC, consent=lambda _: False,
        dynamic_capture=capture, prepare=prepare,
    )
    assert not result.executed
    assert result.reason == "PREREQUISITE_DECLINED"
    assert result.assessment.architecture.value == "UNKNOWN"
    capture.assert_not_called()


def test_dynamic_ready_dispatches_only_canonical_probe():
    capture = Mock(return_value=ProbeCaptures(
        URL, URL, DEVICE, "<html><body><main><h1>Page</h1><p>Visible server content present.</p></main></body></html>",
        "<html><body><main><h1>Page</h1><p>Visible server content present.</p></main></body></html>",
    ))
    prepare = Mock(return_value=SimpleNamespace(ready=True, reason="PREREQUISITE_READY"))
    with patch("rasai.architecture_probe._validate_public_url", side_effect=lambda url, _: url):
        result = run_optional_discovery(
            URL, DEVICE, mode=DYNAMIC, consent=lambda _: True,
            dynamic_capture=capture, prepare=prepare,
        )
    assert result.executed
    assert result.assessment.architecture.value == "STATIC_OR_SSR"
    capture.assert_called_once()


def test_static_network_failure_abstains_without_docker_or_global_failure():
    result = run_optional_discovery(
        URL, DEVICE, mode=STATIC, consent=lambda _: False,
        static_capture=Mock(side_effect=OSError("private network details")),
        prepare=Mock(side_effect=AssertionError("no Docker")),
    )
    assert not result.executed
    assert result.reason == "OPTIONAL_DISCOVERY_UNAVAILABLE"
    assert result.assessment.architecture.value == "UNKNOWN"


def test_dynamic_worker_failure_abstains_after_ready_prerequisite():
    result = run_optional_discovery(
        URL, DEVICE, mode=DYNAMIC, consent=lambda _: True,
        prepare=lambda *_args, **_kwargs: SimpleNamespace(ready=True),
        dynamic_capture=Mock(side_effect=RuntimeError("worker error with private details")),
    )
    assert not result.executed
    assert result.reason == "OPTIONAL_DISCOVERY_UNAVAILABLE"
    assert result.assessment.architecture.value == "UNKNOWN"


def test_dynamic_prerequisite_failure_abstains_before_site_capture():
    capture = Mock(side_effect=AssertionError("no network or Docker renderer"))
    result = run_optional_discovery(
        URL, DEVICE, mode=DYNAMIC, consent=lambda _: False,
        prepare=Mock(side_effect=OSError("private Docker daemon details")),
        dynamic_capture=capture,
    )
    assert not result.executed
    assert result.reason == "OPTIONAL_PREREQUISITE_UNAVAILABLE"
    assert result.assessment.architecture.value == "UNKNOWN"
    capture.assert_not_called()


def test_auto_audit_adapter_reuses_canonical_service_without_altering_configuration(monkeypatch):
    from rasai.architecture_choice_audit_adapter import (
        observe_auto_architecture_before_audit, prepare_audit_choice_configuration,
    )
    from rasai.architecture_choice import ArchitectureChoice
    from rasai.architecture_acquisition_service import DiscoveryExecution
    from rasai.architecture_discovery import assess_architecture
    from rasai.architecture_acquisition_preferences import STATIC
    from rasai.domain import DeviceContext
    snapshot = {"targets": ["https://example.org/"]}
    frozen = prepare_audit_choice_configuration(snapshot, choice=ArchitectureChoice("AUTO"))
    received = []
    expected = DiscoveryExecution(True, STATIC, assess_architecture(
        raw_html="<main>HTML</main>", rendered_html=None,
        quality_reason="STATIC_MODE_NO_RENDERED_DOM"), "STATIC_MODE_NO_RENDERED_DOM")

    def fake_service(url, device, *, mode, consent):
        received.append((url, device, mode))
        return expected

    monkeypatch.setattr("rasai.architecture_acquisition_service.run_optional_discovery", fake_service)
    result = observe_auto_architecture_before_audit(
        "https://example.org/", DeviceContext.MOBILE,
        mode=STATIC, consent=lambda _: False)
    assert result is expected
    assert received == [("https://example.org/", DeviceContext.MOBILE, STATIC)]
    assert snapshot == {"targets": ["https://example.org/"]}
    assert frozen["architecture_choice"]["mode"] == "AUTO"


def test_reprocess_reads_historical_choice_without_any_network(monkeypatch):
    from types import SimpleNamespace
    from rasai.architecture_choice import ArchitectureChoice
    from rasai.architecture_choice_audit_adapter import (
        read_architecture_choice_for_reprocess, prepare_audit_choice_configuration,
    )
    from rasai.audit_configuration_reuse import configuration_hash
    snapshot = prepare_audit_choice_configuration(
        {"targets": ["https://example.org/"]}, choice=ArchitectureChoice("AUTO"),
    )
    stored = SimpleNamespace(configuration=snapshot,
                             configuration_hash=configuration_hash(snapshot))
    calls = []

    def read(root, audit_id):
        calls.append((root, audit_id))
        return stored

    monkeypatch.setattr("rasai.audit_configuration_reuse.load_reusable_audit_configuration", read)
    resolved = read_architecture_choice_for_reprocess("/tmp/rasai-audits", "aud-123")
    assert resolved.choice.mode == "AUTO"
    assert resolved.explicitly_configured
    assert calls == [("/tmp/rasai-audits", "aud-123")]


def test_reprocess_historical_choice_abstains_when_unavailable(monkeypatch):
    from rasai.architecture_choice_audit_adapter import read_architecture_choice_for_reprocess
    def missing(*args):
        raise FileNotFoundError("historical configuration unavailable")
    monkeypatch.setattr("rasai.audit_configuration_reuse.load_reusable_audit_configuration", missing)
    assert read_architecture_choice_for_reprocess("/tmp/rasai-audits", "aud-123") is None


def test_reprocess_historical_choice_rejects_modified_sealed_snapshot(monkeypatch):
    """Never display a claimed historical architecture when its seal disagrees."""
    from types import SimpleNamespace
    from rasai.architecture_choice import ArchitectureChoice
    from rasai.architecture_choice_audit_adapter import (
        read_architecture_choice_for_reprocess, prepare_audit_choice_configuration,
    )
    from rasai.audit_configuration_reuse import configuration_hash
    original = prepare_audit_choice_configuration(
        {"targets": ["https://example.org/"]}, choice=ArchitectureChoice("AUTO"),
    )
    modified = dict(original, targets=["https://different.example.org/"])
    saved = SimpleNamespace(configuration=modified,
                            configuration_hash=configuration_hash(original))
    monkeypatch.setattr(
        "rasai.audit_configuration_reuse.load_reusable_audit_configuration",
        lambda *_: saved,
    )
    assert read_architecture_choice_for_reprocess("/tmp/audits", "aud-123") is None


def test_new_capture_origin_is_bound_before_classification_and_not_manifest_attested():
    import hashlib
    import pytest
    from rasai.architecture_probe import ProbeCaptures, with_capture_origin
    captured = ProbeCaptures(URL, URL, DEVICE, "<main>Hello</main>", "<main>Hello</main>")
    stamped = with_capture_origin(captured, transport="ISOLATED_OCI_RENDER")
    assert stamped.origin.transport == "ISOLATED_OCI_RENDER"
    assert stamped.origin.requested_url == URL
    assert stamped.origin.device == DEVICE.value
    assert stamped.origin.raw_sha256 == hashlib.sha256(b"<main>Hello</main>").hexdigest()
    assert stamped.origin.rendered_sha256 == stamped.origin.raw_sha256
    assert stamped.origin.attested is False
    assert captured.origin is None
    with pytest.raises(ValueError, match="cannot be replaced"):
        with_capture_origin(stamped, transport="ISOLATED_OCI_RENDER")


def test_static_capture_origin_omits_unobserved_rendered_document():
    from rasai.architecture_probe import ProbeCaptures, with_capture_origin
    stamped = with_capture_origin(ProbeCaptures(
        URL, URL, DEVICE, "<main>RAW</main>", None, "STATIC_MODE_NO_RENDERED_DOM",
    ), transport="PINNED_HTTP_STATIC")
    assert stamped.origin.raw_sha256 is not None
    assert stamped.origin.rendered_sha256 is None
    assert stamped.origin.attested is False
