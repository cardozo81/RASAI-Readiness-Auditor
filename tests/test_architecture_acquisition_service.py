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
