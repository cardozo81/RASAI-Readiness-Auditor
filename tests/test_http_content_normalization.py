"""Bounded canonical HTTP normalization of archived gzip, robots and RAW (#665)."""
from __future__ import annotations

import gzip
import hashlib
from pathlib import Path

import pytest

from rasai.acquisition import HttpAcquisitionResult, decode_body, decode_captured_text, normalize_http_content
from rasai.discovery import DiscoveryEngine, RobotsState
from rasai.m24_discovery_extensions import _interpret_robots_m24
from rasai.architecture_raw_signals import inspect_raw_html_signals
from rasai.architecture_audit_facts import _raw_from_attested_snapshot


def _acq(url, body, encoding=None):
    headers = (("Content-Type", "text/plain; charset=utf-8"),)
    if encoding:
        headers += (("Content-Encoding", encoding),)
    return HttpAcquisitionResult(
        requested_url=url, final_url=url, status=200, headers=headers,
        body=body, redirects=(), network_error=None, elapsed_ms=1,
    )


def test_attested_gzip_raw_reveals_html_without_mutating_digest(tmp_path: Path):
    html = ('<html><head><script src="/a.js"></script><script>one()</script>'
            '<script type="application/ld+json">{"@type":"WebSite"}</script></head>'
            '<body><main><h1>Schema.org</h1>' + ' substantial' * 12
            + '</main></body></html>').encode()
    raw = gzip.compress(html)
    digest = hashlib.sha256(raw).hexdigest()
    assert decode_captured_text(raw).encode() == html
    signals = inspect_raw_html_signals(decode_captured_text(raw))
    assert signals.h1_present and signals.external_script_tags == 1
    assert signals.inline_script_tags == 2
    artifact = tmp_path / "artifacts" / "raw.html"
    artifact.parent.mkdir()
    artifact.write_bytes(raw)
    metadata = {"architecture_artifact_binding": {
        "version": "m3-artifact-binding-v1", "raw_sha256": digest,
    }}
    assert _raw_from_attested_snapshot(tmp_path, "artifacts/raw.html", metadata) == html.decode()
    assert artifact.read_bytes() == raw
    assert hashlib.sha256(artifact.read_bytes()).hexdigest() == digest


def test_corrupt_oversized_unsupported_encoding_abstains_and_plain_remains():
    with pytest.raises(ValueError):
        normalize_http_content(b"\x1f\x8b" + b"corrupt")
    with pytest.raises(ValueError):
        normalize_http_content(gzip.compress(b"x" * 2048), max_output_bytes=1024)
    with pytest.raises(ValueError):
        normalize_http_content(b"plain", content_encoding="gzip")
    with pytest.raises(ValueError):
        normalize_http_content(b"plain", content_encoding="br")
    assert normalize_http_content(b"plain") == b"plain"
    assert decode_captured_text(b"<h1>Olá</h1>") == "<h1>Olá</h1>"


def test_gzip_robots_retains_declared_sitemap_distinct_from_conventional():
    robots_url = "https://schema.org/robots.txt"
    declared_url = "https://schema.org/docs/sitemap.xml"
    body = gzip.compress(f"User-agent: *\nAllow: /\nSitemap: {declared_url}\n".encode())
    result = _acq(robots_url, body, "gzip")
    engine = DiscoveryEngine()
    for parser in (DiscoveryEngine._interpret_robots, _interpret_robots_m24):
        state, policy, urls = parser(engine, robots_url, result, "https://schema.org")
        assert state is RobotsState.OBTAINED
        assert urls == (declared_url,)
        assert policy is not None
    assert declared_url in decode_body(result)
