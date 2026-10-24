"""Focused offline regressions from AUD-A16711D11A8A40BDA303A362C45CCEDD."""
from __future__ import annotations

from types import SimpleNamespace
import gzip

from rasai.acquisition import HttpAcquisitionResult
from rasai.discovery import DiscoveryEngine, SitemapState
from rasai.m14_discovery import discover_url_set
from rasai.m24_discovery_extensions import install_discovery_extensions
from rasai.m24_crawling_discovery import _analyze_sitemap_artifact


ORIGIN = "https://public.example.test"


def _http(url: str, body: bytes, content_type: str = "application/xml"):
    return HttpAcquisitionResult(
        requested_url=url, final_url=url, status=200,
        headers=(("Content-Type", content_type),), body=body,
        redirects=(), network_error=None, elapsed_ms=1,
    )


class _FakeClient:
    def __init__(self, mapping):
        self.mapping = mapping
        self.urls: list[str] = []

    def acquire(self, url):
        self.urls.append(url)
        return self.mapping.get(url, _http(url, b"", "text/plain"))


def _xml_urls(n: int, *, offset: int = 0) -> bytes:
    return ("<urlset>" + "".join(
        f"<url><loc>{ORIGIN}/page-{i}</loc></url>" for i in range(offset, offset + n)
    ) + "</urlset>").encode()


def test_a167_plain_xml_with_gz_suffix_is_not_invalid_gzip(tmp_path):
    install_discovery_extensions()
    url = ORIGIN + "/sitemap.xml.gz"
    plain = _xml_urls(3)
    client = _FakeClient({url: _http(url, plain, "text/xml")})
    engine = DiscoveryEngine(http_client=client)
    result = engine._acquire_sitemap(url, ORIGIN)
    assert result.state is SitemapState.OBTAINED
    assert len(result.page_urls) == 3
    directory = tmp_path / "artifacts"
    directory.mkdir()
    (directory / "sitemap.response").write_bytes(plain)
    artifact = _analyze_sitemap_artifact(
        SimpleNamespace(root=tmp_path),
        {"artifact_reference": "artifacts/sitemap.response"},
        url, ORIGIN,
    )
    assert artifact["format"] == "XML_URLSET"
    assert len(artifact["page_urls"]) == 3


def test_a167_genuine_gzip_is_decompressed_once():
    install_discovery_extensions()
    url = ORIGIN + "/sitemap.xml.gz"
    client = _FakeClient({url: _http(url, gzip.compress(_xml_urls(2)), "application/gzip")})
    result = DiscoveryEngine(http_client=client)._acquire_sitemap(url, ORIGIN)
    assert result.state is SitemapState.OBTAINED
    assert len(result.page_urls) == 2


def test_a167_single_url_limits_sitemap_fetches_and_candidate_inventory():
    install_discovery_extensions()
    index = ORIGIN + "/sitemap.xml"
    children = [ORIGIN + f"/map-{i}.xml" for i in range(30)]
    sitemap_index = ("<sitemapindex>" + "".join(
        f"<sitemap><loc>{child}</loc></sitemap>" for child in children
    ) + "</sitemapindex>").encode()
    mapping = {
        ORIGIN + "/robots.txt": _http(ORIGIN + "/robots.txt", b"", "text/plain"),
        index: _http(index, sitemap_index),
        ORIGIN + "/": _http(ORIGIN + "/", b"<main>One URL</main>", "text/html"),
    }
    for idx, child in enumerate(children):
        mapping[child] = _http(child, _xml_urls(275, offset=idx * 275))
    client = _FakeClient(mapping)
    outcome = DiscoveryEngine(http_client=client).discover(ORIGIN + "/", max_pages=1)
    assert outcome.total_audited == 1
    assert len(outcome.sitemaps) == 12
    assert outcome.total_discovered <= 2_000
    assert len([url for url in client.urls if "/map-" in url]) == 11
    assert any(x.startswith("SITEMAP_RESOURCE_BUDGET_EXHAUSTED") for x in outcome.discovery_limitations)
    assert any(x.startswith("DISCOVERY_CANDIDATE_BUDGET_EXHAUSTED") for x in outcome.discovery_limitations)


def test_a167_explicit_url_scope_still_bounds_sitemap_resources():
    install_discovery_extensions()
    index = ORIGIN + "/sitemap.xml"
    children = [ORIGIN + f"/child-{i}.xml" for i in range(30)]
    root = ("<sitemapindex>" + "".join(
        f"<sitemap><loc>{url}</loc></sitemap>" for url in children
    ) + "</sitemapindex>").encode()
    mapping = {
        ORIGIN + "/robots.txt": _http(ORIGIN + "/robots.txt", b"", "text/plain"),
        index: _http(index, root),
        ORIGIN + "/fixed": _http(ORIGIN + "/fixed", b"<main>Fixed</main>", "text/html"),
    }
    mapping.update({url: _http(url, _xml_urls(1)) for url in children})
    result = discover_url_set(
        DiscoveryEngine(http_client=_FakeClient(mapping)),
        (ORIGIN + "/fixed",), max_pages=1,
    )
    assert len(result.pages) == 1
    assert len(result.sitemaps) == 12
    assert any("SITEMAP_RESOURCE_BUDGET_EXHAUSTED" in x for x in result.discovery_limitations)
