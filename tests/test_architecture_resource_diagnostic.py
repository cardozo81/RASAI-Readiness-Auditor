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


def test_oversize_css_can_be_acquired_with_bounded_type_specific_fetcher(monkeypatch):
    from rasai.architecture_resource_budget import (
        MAX_ASSET_BYTES, MAX_STYLESHEET_BYTES, MAX_RESOURCE_BYTES,
    )
    assert MAX_ASSET_BYTES == 500_000
    assert MAX_STYLESHEET_BYTES == 2_000_000
    assert MAX_RESOURCE_BYTES == 33_000_000
    css_url = "https://example.org/assets/site.css"
    html = '<main>Layout</main><link rel="stylesheet" href="/assets/site.css">'
    root = resource(content_type="text/html", body=html.encode())
    css_body = b"x" * 1_500_000
    css = resource(final=css_url, content_type="text/css; charset=utf-8", body=css_body)
    limits = []

    class FakeFetcher:
        def __init__(self, **kwargs):
            limits.append(kwargs["max_bytes"])
            self._cap = kwargs["max_bytes"]

        def fetch(self, url):
            assert url == css_url
            assert len(css.body) <= self._cap
            return css

    monkeypatch.setattr(
        "rasai.architecture_isolated_capture._validate_public_url",
        lambda url, _: url,
    )
    monkeypatch.setattr(
        "rasai.architecture_isolated_capture.PublicWebFetcher", FakeFetcher,
    )
    captured = _bundle_resources(URL, root, html)
    assert limits == [MAX_ASSET_BYTES, MAX_STYLESHEET_BYTES]
    assert len(captured) == 2
    import base64
    assert base64.b64decode(captured[1]["body_b64"]) == css_body


def test_css_preload_as_style_receives_css_limit_without_domain_rule(monkeypatch):
    from rasai.architecture_resource_budget import MAX_STYLESHEET_BYTES
    url = "https://example.org/shared.css"
    html = '<link rel="preload" as="style" href="/shared.css">'
    root = resource(content_type="text/html", body=html.encode())
    stylesheet = resource(final=url, content_type="text/css", body=b"x" * 700_000)
    fetch_caps = []

    class FakeFetcher:
        def __init__(self, **kwargs):
            self.limit = kwargs["max_bytes"]
            fetch_caps.append(self.limit)
        def fetch(self, link):
            assert link == url
            assert len(stylesheet.body) <= self.limit
            return stylesheet

    monkeypatch.setattr(
        "rasai.architecture_isolated_capture._validate_public_url",
        lambda link, _: link,
    )
    monkeypatch.setattr("rasai.architecture_isolated_capture.PublicWebFetcher", FakeFetcher)
    result = _bundle_resources(URL, root, html)
    assert len(result) == 2
    assert MAX_STYLESHEET_BYTES in fetch_caps


def test_css_above_two_megabytes_still_abstains_and_preserves_failure_kind(monkeypatch):
    from rasai.architecture_resource_budget import MAX_STYLESHEET_BYTES
    html = '<main>Page</main><link rel="stylesheet" href="/big.css">'
    root = resource(content_type="text/html", body=html.encode())
    # Simulates the fetcher's own bounded response failure; no large body
    # crosses the boundary or reaches the worker.
    css = resource(
        status=ContentFetchStatus.ERROR, error="CONTENT_BODY_LIMIT",
        final="https://example.org/big.css", body=b"",
    )
    monkeypatch.setattr(
        "rasai.architecture_isolated_capture._validate_public_url",
        lambda u, _: u,
    )

    def build(**kwargs):
        if kwargs["max_bytes"] == MAX_STYLESHEET_BYTES:
            return SimpleNamespace(fetch=lambda _: css)
        return SimpleNamespace(fetch=lambda _: (_ for _ in ()).throw(
            AssertionError("CSS must not use default 500KB fetcher")
        ))

    monkeypatch.setattr(
        "rasai.architecture_isolated_capture.PublicWebFetcher", build,
    )
    with pytest.raises(ArchitectureAssetFailure) as error:
        _bundle_resources(URL, root, html)
    assert error.value.reason == "OCI_ASSET_SIZE_LIMIT"
    assert error.value.diagnostic.kind == "stylesheet"


def test_mislabeled_oversize_css_does_not_bypass_default_asset_ceiling(monkeypatch):
    html = '<link rel="stylesheet" href="/unexpected.html">'
    root = resource(content_type="text/html", body=html.encode())
    wrong = resource(
        final="https://example.org/unexpected.html",
        content_type="text/html", body=b"x" * 700_000,
    )
    monkeypatch.setattr(
        "rasai.architecture_isolated_capture._validate_public_url", lambda u, _: u,
    )
    with patch("rasai.architecture_isolated_capture.PublicWebFetcher") as fetch:
        fetch.return_value.fetch.return_value = wrong
        with pytest.raises(ArchitectureAssetFailure) as error:
            _bundle_resources(URL, root, html)
    assert error.value.reason == "OCI_ASSET_SIZE_LIMIT"
    assert error.value.diagnostic.kind == "stylesheet"


def test_css_cannot_eat_through_aggregate_worker_memory_budget(monkeypatch):
    import rasai.architecture_isolated_capture as isolated
    html = ('<main>Page</main>'
            '<link rel="stylesheet" href="/first.css">'
            '<link rel="stylesheet" href="/second.css">')
    root = resource(content_type="text/html", body=html.encode())
    first = resource(
        final="https://example.org/first.css", content_type="text/css",
        body=b"x" * 650_000,
    )
    second = resource(
        final="https://example.org/second.css", content_type="text/css",
        body=b"x" * 650_000,
    )
    monkeypatch.setattr(isolated, "_validate_public_url", lambda u, _: u)
    monkeypatch.setattr(isolated, "MAX_RESOURCE_BYTES", 1_000_000)
    with patch("rasai.architecture_isolated_capture.PublicWebFetcher") as fetch:
        fetch.return_value.fetch.side_effect = [first, second]
        with pytest.raises(ArchitectureAssetFailure) as error:
            _bundle_resources(URL, root, html)
    assert error.value.reason == "OCI_ASSET_TOTAL_BYTES_LIMIT"
    assert error.value.diagnostic.kind == "stylesheet"
    assert error.value.diagnostic.ordinal == 2
    assert error.value.diagnostic.candidates == 2


@pytest.mark.parametrize("link", [
    '<script src="/runtime.js"></script>',
    '<link rel="modulepreload" href="/runtime.js">',
    '<link rel="preload" as="script" href="/runtime.js">',
])
def test_large_js_bundle_role_and_worker_limits_are_consistent(monkeypatch, link):
    """No domain-dependent exception; 1.5MB script passes host and worker."""
    from rasai.architecture_offline_worker import validate_bundle
    from rasai.architecture_resource_budget import MAX_SCRIPT_BYTES
    from rasai.architecture_isolated_capture import _bundle_resources
    from rasai.architecture_resource_budget import MAX_ASSET_BYTES
    import json

    html = "<main>Shell</main>" + link
    root = resource(content_type="text/html", body=html.encode())
    js_url = "https://example.org/runtime.js"
    js = resource(final=js_url, content_type="application/javascript; charset=utf-8",
                  body=b"x" * 1_500_000)
    caps = []

    class FakeFetcher:
        def __init__(self, **kwargs):
            self.max_bytes = kwargs["max_bytes"]
            caps.append(self.max_bytes)
        def fetch(self, url):
            assert url == js_url
            assert len(js.body) <= self.max_bytes
            return js

    monkeypatch.setattr(
        "rasai.architecture_isolated_capture._validate_public_url",
        lambda url, _: url,
    )
    monkeypatch.setattr(
        "rasai.architecture_isolated_capture.PublicWebFetcher", FakeFetcher,
    )
    assets = _bundle_resources(URL, root, html)
    assert caps == [MAX_ASSET_BYTES, MAX_SCRIPT_BYTES]
    assert assets[1]["resource_kind"] in {"script", "modulepreload"}
    _, _, decoded = validate_bundle({
        "url": URL, "device": "mobile", "resources": assets,
    })
    assert decoded[js_url][0] == js.body


def test_script_four_megabyte_cap_still_refuses_oversized_js(monkeypatch):
    from rasai.architecture_resource_budget import MAX_SCRIPT_BYTES
    html = '<script src="/huge.js"></script>'
    root = resource(content_type="text/html", body=html.encode())
    failed = resource(
        status=ContentFetchStatus.ERROR, http=200, error="CONTENT_BODY_LIMIT",
        final="https://example.org/huge.js", body=b"",
    )
    observed = []
    class FakeFetcher:
        def __init__(self, **kwargs):
            self.max_bytes = kwargs["max_bytes"]
        def fetch(self, url):
            observed.append(self.max_bytes)
            return failed

    monkeypatch.setattr(
        "rasai.architecture_isolated_capture._validate_public_url",
        lambda url, _: url,
    )
    monkeypatch.setattr(
        "rasai.architecture_isolated_capture.PublicWebFetcher", FakeFetcher,
    )
    with pytest.raises(ArchitectureAssetFailure) as error:
        _bundle_resources(URL, root, html)
    assert observed == [MAX_SCRIPT_BYTES]
    assert error.value.reason == "OCI_ASSET_SIZE_LIMIT"
    assert error.value.diagnostic.kind == "script"


@pytest.mark.parametrize("response_type", [
    "text/plain", "text/html", "application/json", "text/css",
])
def test_declared_script_with_wrong_mime_cannot_exceed_default_cap(monkeypatch, response_type):
    html = '<script src="/app.js"></script>'
    root = resource(content_type="text/html", body=html.encode())
    invalid = resource(
        final="https://example.org/app.js",
        content_type=response_type, body=b"x" * 750_000,
    )
    monkeypatch.setattr(
        "rasai.architecture_isolated_capture._validate_public_url",
        lambda url, _: url,
    )
    with patch("rasai.architecture_isolated_capture.PublicWebFetcher") as fetcher:
        fetcher.return_value.fetch.return_value = invalid
        with pytest.raises(ArchitectureAssetFailure) as error:
            _bundle_resources(URL, root, html)
    assert error.value.reason == "OCI_ASSET_SIZE_LIMIT"
    assert error.value.diagnostic.kind == "script"


def test_multiple_large_scripts_still_obey_original_aggregate_budget(monkeypatch):
    import rasai.architecture_isolated_capture as isolated
    html = '<script src="/one.js"></script><script src="/two.js"></script>'
    root = resource(content_type="text/html", body=html.encode())
    first = resource(final="https://example.org/one.js",
                     content_type="text/javascript", body=b"x" * 700_000)
    second = resource(final="https://example.org/two.js",
                      content_type="text/javascript", body=b"x" * 700_000)
    monkeypatch.setattr(isolated, "_validate_public_url", lambda u, _: u)
    monkeypatch.setattr(isolated, "MAX_RESOURCE_BYTES", 1_000_000)
    with patch("rasai.architecture_isolated_capture.PublicWebFetcher") as fetcher:
        fetcher.return_value.fetch.side_effect = [first, second]
        with pytest.raises(ArchitectureAssetFailure) as error:
            _bundle_resources(URL, root, html)
    assert error.value.reason == "OCI_ASSET_TOTAL_BYTES_LIMIT"
    assert error.value.diagnostic.kind == "script"
    assert error.value.diagnostic.ordinal == 2
