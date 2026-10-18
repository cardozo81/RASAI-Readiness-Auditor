"""Static architecture mode is explicitly limited and never boots Docker."""
from types import SimpleNamespace
from unittest.mock import patch

from rasai.architecture_acquisition_preferences import (
    STATIC, DYNAMIC, read_mode, write_mode, preference_path,
)
from rasai.architecture_static_capture import capture_static_public_architecture
from rasai.architecture_probe import probe_architecture
from rasai.domain import DeviceContext
from rasai.search_intelligence.content import ContentFetchStatus


def test_default_mode_is_static_and_can_switch_back_and_forth(tmp_path):
    assert read_mode(tmp_path) == STATIC
    write_mode(DYNAMIC, tmp_path)
    assert read_mode(tmp_path) == DYNAMIC
    write_mode(STATIC, tmp_path)
    assert read_mode(tmp_path) == STATIC
    assert preference_path(tmp_path).parent == tmp_path / ".rasai-runtime" / "architecture"


def test_invalid_preference_fails_to_safe_static(tmp_path):
    file = preference_path(tmp_path)
    file.parent.mkdir(parents=True)
    file.write_text('{"mode":"DYNAMIC","version":999}', encoding="utf-8")
    assert read_mode(tmp_path) == STATIC
    file.write_text("invalid json", encoding="utf-8")
    assert read_mode(tmp_path) == STATIC


def test_static_fetch_never_invokes_container_or_claims_classification(monkeypatch):
    url = "https://example.org/"
    root = SimpleNamespace(
        status=ContentFetchStatus.OBSERVED, final_url=url, http_status=200,
        body=b"<html><main>Server supplied content.</main></html>",
        headers={"content-type": "text/html"},
    )
    monkeypatch.setattr("rasai.architecture_static_capture._validate_public_url",
                        lambda value, _: value)
    with patch("rasai.architecture_static_capture.PublicWebFetcher") as fetch, patch(
        "rasai.architecture_probe._default_resolver"
    ) as validate_dns, patch(
        "rasai.architecture_static_capture.subprocess.run", create=True
    ) as docker:
        fetch.return_value.fetch.return_value = root
        result = probe_architecture(
            url, DeviceContext.MOBILE, capture=capture_static_public_architecture,
        )
    assert result.architecture.value == "UNKNOWN"
    assert result.limitation == "STATIC_MODE_NO_RENDERED_DOM"
    docker.assert_not_called()
    validate_dns.assert_not_called()


def test_static_rejects_redirects_without_browser_fallback(monkeypatch):
    url = "https://google.com/"
    root = SimpleNamespace(
        status=ContentFetchStatus.ERROR, final_url=url,
        http_status=301, error_code="TOO_MANY_REDIRECTS",
        body=b"", headers={},
    )
    monkeypatch.setattr("rasai.architecture_static_capture._validate_public_url",
                        lambda value, _: value)
    with patch("rasai.architecture_static_capture.PublicWebFetcher") as fetch:
        fetch.return_value.fetch.return_value = root
        observation = capture_static_public_architecture(url, DeviceContext.MOBILE)
    assert observation.quality_reason == "PUBLIC_REDIRECT_NOT_FOLLOWED"
    assert observation.rendered_html is None
