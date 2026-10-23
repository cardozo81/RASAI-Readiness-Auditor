"""Generic failure transparency for isolated public-resource acquisition.

No live DNS, Docker, third-party host, user data or AUD writes.
"""
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from rasai.architecture_discovery import assess_architecture
from rasai.architecture_isolated_capture import (
    ArchitectureAssetFailure, ContentFetchStatus, _asset_failure_reason,
    _bundle_resources,
)
from rasai.architecture_probe import ProbeCaptures, probe_architecture, with_capture_origin
from rasai.architecture_resource_diagnostic import ResourcePreflightDiagnostic
from rasai.console_architecture_discovery import describe_architecture_assessment
from rasai.domain import ArchitectureClassification, DeviceContext


URL = "https://example.org/"


def resource(*, status=ContentFetchStatus.OBSERVED, http=200,
             error=None, final=URL, content_type="text/javascript", body=b"data"):
    return SimpleNamespace(
        status=status, http_status=http, error_code=error, final_url=final,
        headers={"content-type": content_type} if content_type is not None else {},
        body=body, error_message="PRIVATE-UNTRUSTED-DO-NOT-PRINT",
    )


@pytest.mark.parametrize(("document", "reason"), [
    (resource(status=ContentFetchStatus.BLOCKED, http=None),
     "OCI_ASSET_DESTINATION_BLOCKED"),
    (resource(status=ContentFetchStatus.UNAVAILABLE, http=None,
              error="CONTENT_TLS_ERROR"), "OCI_ASSET_TLS_FAILURE"),
    (resource(status=ContentFetchStatus.UNAVAILABLE, http=None,
              error="CONTENT_TIMEOUT"), "OCI_ASSET_TIMEOUT"),
    (resource(status=ContentFetchStatus.ERROR, error="CONTENT_BODY_LIMIT"),
     "OCI_ASSET_SIZE_LIMIT"),
    (resource(status=ContentFetchStatus.ERROR, http=302,
              error="TOO_MANY_REDIRECTS"), "OCI_ASSET_REDIRECT_BLOCKED"),
    (resource(status=ContentFetchStatus.UNAVAILABLE, http=None,
              error="CONTENT_NETWORK_ERROR"), "OCI_ASSET_NETWORK_UNAVAILABLE"),
    (resource(http=403), "OCI_ASSET_HTTP_NOT_SUCCESS"),
    (resource(final="https://example.org/other"), "OCI_ASSET_FINAL_URL_MISMATCH"),
    (resource(content_type=None), "OCI_ASSET_CONTENT_TYPE_MISSING"),
    (resource(body=None), "OCI_ASSET_UNAVAILABLE"),
    (resource(), None),
])
def test_bounded_fetcher_failure_taxonomy(document, reason):
    assert _asset_failure_reason(document, URL) == reason


def test_resource_diagnostic_is_finite_and_refuses_invalid_or_unbounded_values():
    good = ResourcePreflightDiagnostic(
        kind="script", phase="fetch", ordinal=2, candidates=5,
    )
    assert good.ordinal == 2
    for invalid in (
        dict(kind="http://private.example", phase="fetch"),
        dict(kind="script", phase="fetch", ordinal=65, candidates=65),
        dict(kind="script", phase="fetch", ordinal=2, candidates=1),
        dict(kind="script", phase="fetch", ordinal=True, candidates=1),
        dict(kind="script", phase="read-database"),
    ):
        with pytest.raises(ValueError):
            ResourcePreflightDiagnostic(**invalid)


def test_failing_css_dependency_reports_kind_and_position_without_page_urls(monkeypatch):
    html = ('<main>Visible host content.</main>'
            '<script src="/app.js"></script>'
            '<link rel="stylesheet" href="/site.css">')
    root = resource(content_type="text/html", body=html.encode())
    js = resource(final="https://example.org/app.js")
    bad_css = resource(http=403, final="https://example.org/site.css")
    monkeypatch.setattr(
        "rasai.architecture_isolated_capture._validate_public_url",
        lambda url, _: url,
    )
    with patch("rasai.architecture_isolated_capture.PublicWebFetcher") as fetcher:
        fetcher.return_value.fetch.side_effect = [js, bad_css]
        with pytest.raises(ArchitectureAssetFailure) as error:
            _bundle_resources(URL, root, html)
    assert error.value.reason == "OCI_ASSET_HTTP_NOT_SUCCESS"
    assert error.value.diagnostic == ResourcePreflightDiagnostic(
        kind="stylesheet", phase="fetch", ordinal=2, candidates=2,
    )
    assert fetcher.return_value.fetch.call_count == 2

    capture = with_capture_origin(
        ProbeCaptures(
            URL, URL, DeviceContext.MOBILE, html, None,
            error.value.reason, resource_diagnostic=error.value.diagnostic,
        ),
        transport="PINNED_HTTP_STATIC",
    )
    assessed = probe_architecture(URL, DeviceContext.MOBILE, capture=lambda *_: capture)
    assert assessed.architecture is ArchitectureClassification.UNKNOWN
    assert assessed.rendered_available is False
    assert assessed.resource_diagnostic == error.value.diagnostic
    text = "\n".join(describe_architecture_assessment(assessed))
    assert "Recurso associado à limitação: folha de estilo" in text
    assert "Posição no inventário permitido: 2 de 2" in text
    assert "OCI_ASSET_HTTP_NOT_SUCCESS" not in text
    assert "PRIVATE-UNTRUSTED" not in text
    assert "/site.css" not in text
    assert "/app.js" not in text


def test_script_tls_failure_does_not_fall_back_to_unpinned_render(monkeypatch):
    html = '<main>Shell</main><script src="/runtime.js"></script>'
    root = resource(content_type="text/html", body=html.encode())
    tls_failure = resource(
        status=ContentFetchStatus.UNAVAILABLE, http=None,
        error="CONTENT_TLS_ERROR", final="https://example.org/runtime.js",
    )
    monkeypatch.setattr(
        "rasai.architecture_isolated_capture._validate_public_url",
        lambda url, _: url,
    )
    with patch("rasai.architecture_isolated_capture.PublicWebFetcher") as fetcher:
        fetcher.return_value.fetch.return_value = tls_failure
        with pytest.raises(ArchitectureAssetFailure) as error:
            _bundle_resources(URL, root, html)
    assert error.value.reason == "OCI_ASSET_TLS_FAILURE"
    assert error.value.diagnostic.kind == "script"
    assert error.value.diagnostic.ordinal == 1
    assert error.value.diagnostic.candidates == 1


def test_failed_asset_without_render_never_upgrades_architecture():
    html = '<div id="root"></div><script src="/app.js"></script>'
    assessment = assess_architecture(
        raw_html=html, rendered_html=None, quality_reason="OCI_ASSET_TIMEOUT",
    )
    assert assessment.architecture is ArchitectureClassification.UNKNOWN
    assert assessment.hypothesis is not None
    assert assessment.hypothesis.likely is ArchitectureClassification.CSR_SPA
    assert assessment.resource_diagnostic is None
