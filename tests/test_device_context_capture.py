from __future__ import annotations

import base64
import hashlib

from rasai.device_context_capture import (
    _MAX_DOCUMENT_SOURCE_BYTES,
    _document_source_metadata,
    _rendered_dom_metadata,
)


class _FakeCdpSession:
    def __init__(self, payload: dict[str, object] | None = None) -> None:
        self.payload = payload or {"body": "<html>ok</html>", "base64Encoded": False}
        self.calls: list[tuple[str, dict[str, object] | None]] = []

    def send(self, method: str, params: dict[str, object] | None = None):
        self.calls.append((method, params))
        if method != "Network.getResponseBody":
            raise AssertionError(f"unexpected CDP method: {method}")
        return self.payload


def _capture(*, finished: dict[str, float] | None = None, failed: set[str] | None = None) -> dict[str, object]:
    return {
        "available": True,
        "request_id": "REQ-1",
        "response_url": "https://example.test/page",
        "finished": finished if finished is not None else {"REQ-1": 128.0},
        "failed": failed if failed is not None else set(),
    }


def test_document_source_reads_only_already_finished_bounded_response() -> None:
    session = _FakeCdpSession()
    result = _document_source_metadata(
        session,
        _capture(),
        content_type="text/html; charset=utf-8",
    )

    expected = b"<html>ok</html>"
    assert result["capture_state"] == "CAPTURED"
    assert result["sha256"] == hashlib.sha256(expected).hexdigest()
    assert result["bytes"] == len(expected)
    assert result["additional_network_requests"] == 0
    assert session.calls == [("Network.getResponseBody", {"requestId": "REQ-1"})]


def test_document_source_does_not_wait_or_read_body_before_loading_finished() -> None:
    session = _FakeCdpSession()
    result = _document_source_metadata(
        session,
        _capture(finished={}),
        content_type="text/html",
    )

    assert result["capture_state"] == "SKIPPED_NOT_FINISHED"
    assert result["reason"] == "MAIN_DOCUMENT_NOT_CONFIRMED_FINISHED"
    assert result["additional_network_requests"] == 0
    assert session.calls == []


def test_document_source_skips_large_response_without_body_read() -> None:
    session = _FakeCdpSession()
    result = _document_source_metadata(
        session,
        _capture(finished={"REQ-1": float(_MAX_DOCUMENT_SOURCE_BYTES + 1)}),
        content_type="text/html",
    )

    assert result["capture_state"] == "SKIPPED_SIZE_LIMIT"
    assert result["reason"] == "MAIN_DOCUMENT_EXCEEDS_CAPTURE_LIMIT"
    assert session.calls == []


def test_document_source_decodes_base64_without_new_navigation() -> None:
    expected = b"\x00binary-document\xff"
    session = _FakeCdpSession(
        {
            "body": base64.b64encode(expected).decode("ascii"),
            "base64Encoded": True,
        }
    )
    result = _document_source_metadata(session, _capture(), content_type="application/octet-stream")

    assert result["capture_state"] == "CAPTURED"
    assert result["sha256"] == hashlib.sha256(expected).hexdigest()
    assert result["bytes"] == len(expected)
    assert result["additional_network_requests"] == 0


def test_document_source_failure_is_fail_open_and_does_not_retry() -> None:
    class _FailingSession(_FakeCdpSession):
        def send(self, method: str, params: dict[str, object] | None = None):
            self.calls.append((method, params))
            raise RuntimeError("buffer unavailable")

    session = _FailingSession()
    result = _document_source_metadata(session, _capture(), content_type="text/html")

    assert result["capture_state"] == "CAPTURE_FAILED"
    assert result["reason"] == "CDP_RESPONSE_BODY_UNAVAILABLE"
    assert result["error"] == "RuntimeError"
    assert len(session.calls) == 1
    assert result["additional_network_requests"] == 0


def test_rendered_dom_fingerprint_is_local_and_deterministic() -> None:
    html = "<html><body>rendered</body></html>"
    first = _rendered_dom_metadata(html)
    second = _rendered_dom_metadata(html)

    assert first == second
    assert first["capture_state"] == "CAPTURED"
    assert first["sha256"] == hashlib.sha256(html.encode("utf-8")).hexdigest()
    assert first["additional_network_requests"] == 0


class _FakeDriftPage:
    def __init__(self, html: str):
        self.html = html
        self.calls = 0

    def content(self) -> str:
        self.calls += 1
        return self.html


def test_incomplete_capture_records_dom_growth_without_changing_original():
    from rasai.device_context_capture import _optional_screenshot_dom_correlation
    old = "<html><body><main></main></body></html>"
    new = "<html><body><main><h1>Seguro de Vida</h1><p>" + ("Cobertura " * 40) + "</p></main></body></html>"
    page = _FakeDriftPage(new)
    original = old
    result = _optional_screenshot_dom_correlation(
        page, old, {"state": "INCOMPLETE"}, b"image"
    )
    assert result["state"] == "OBSERVED"
    assert result["captured_main_text_length"] == 0
    assert result["main_text_delta"] > 0
    assert result["captured_dom_sha256"] == hashlib.sha256(old.encode()).hexdigest()
    assert old == original
    assert page.calls == 1


def test_healthy_capture_does_not_probe_dom_again():
    from rasai.device_context_capture import _optional_screenshot_dom_correlation
    page = _FakeDriftPage("<html><main>changed</main></html>")
    result = _optional_screenshot_dom_correlation(
        page, "<main>healthy</main>", {"state": "READY"}, b"image"
    )
    assert result["state"] == "NOT_APPLICABLE"
    assert page.calls == 0


def test_missing_screenshot_never_probes_dom():
    from rasai.device_context_capture import _optional_screenshot_dom_correlation
    page = _FakeDriftPage("<main>changed</main>")
    result = _optional_screenshot_dom_correlation(
        page, "<main></main>", {"state": "INCOMPLETE"}, None
    )
    assert result["state"] == "NOT_APPLICABLE"
    assert page.calls == 0


def test_screenshot_dom_probe_fails_open_on_page_content_error():
    from rasai.device_context_capture import _optional_screenshot_dom_correlation

    class _FailingPage:
        def content(self):
            raise RuntimeError("page closed between capture phases")

    result = _optional_screenshot_dom_correlation(
        _FailingPage(), "<main></main>", {"state": "INCOMPLETE"}, b"image"
    )
    assert result == {
        "state": "UNAVAILABLE",
        "contract_version": "SCREENSHOT-DOM-CORRELATION-001",
    }
