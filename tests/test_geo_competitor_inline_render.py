"""Offline-only COBS inline replay regressions: no actual Docker or HTTP."""
from __future__ import annotations

import base64
from hashlib import sha256
import json
import subprocess
from types import SimpleNamespace

import pytest
from rasai import geo_competitor_inline_render as replay

URL = "https://example.org/catalog"
HTML = b"<html><main><script>document.write('Material after inline JS')</script></main></html>"


def test_missing_image_abstains_without_starting_container(monkeypatch):
    monkeypatch.setattr(replay, "inspect_local_image", lambda: None)
    monkeypatch.setattr(replay.subprocess, "run",
                        lambda *a, **k: pytest.fail("Docker must not execute"))
    result = replay.inspect_inline_spa_replay(
        URL, HTML, device="desktop", response_headers={"content-type": "text/html"},
    )
    assert result["status"] == "OCI_IMAGE_NOT_AVAILABLE"
    assert result["source_html_sha256"] == sha256(HTML).hexdigest()
    assert result["live_primary_content_proven"] is False
    assert result["additional_public_http_requests"] == result["audit_writes"] == 0


def test_invalid_url_device_html_policy_fail_before_docker(monkeypatch):
    monkeypatch.setattr(replay, "inspect_local_image",
                        lambda: pytest.fail("must not probe Docker"))
    with pytest.raises(ValueError, match="device"):
        replay.inspect_inline_spa_replay(URL, HTML, device="tablet")
    with pytest.raises(ValueError, match="canonical"):
        replay.inspect_inline_spa_replay(
            "http://user:password@example.org/catalog", HTML, device="mobile",
        )
    too_large = replay.inspect_inline_spa_replay(
        URL, b"a" * 1_000_001, device="mobile",
    )
    assert too_large["status"] == "INPUT_HTML_NOT_ELIGIBLE"
    forbidden = replay.inspect_inline_spa_replay(
        URL, HTML, device="desktop",
        response_headers={"content-type": "text/html", "content-security-policy": "a\nb"},
    )
    assert forbidden["status"] == "RESPONSE_POLICY_UNVERIFIABLE"


def _isolated(monkeypatch, response):
    monkeypatch.setattr(replay, "inspect_local_image", lambda: "sha256:" + "a" * 64)
    monkeypatch.setattr(replay.shutil, "which", lambda name: "/usr/bin/docker")
    from rasai import architecture_isolation_smoke as smoke
    attested = []
    monkeypatch.setattr(smoke, "verify_isolation", lambda **kw: attested.append("network"))
    monkeypatch.setattr(smoke, "verify_browser_canary", lambda **kw: attested.append("browser"))
    sent = []

    def run(args, **kwargs):
        assert "--network=none" in args and "--cap-drop=ALL" in args
        assert "--read-only" in args and "--pull=never" in args
        assert "--security-opt=no-new-privileges" in args
        assert kwargs["timeout"] == 40
        payload = json.loads(kwargs["input"])
        assert payload["url"] == URL
        assert payload["resources"][0]["url"] == URL
        assert base64.b64decode(payload["resources"][0]["body_b64"]) == HTML
        assert len(payload["resources"]) == 1
        sent.append(payload)
        return response

    monkeypatch.setattr(replay.subprocess, "run", run)
    return attested, sent


def test_valid_inline_result_proves_only_oci_replay(monkeypatch):
    rendered = "<html><main>Material after inline JS</main></html>"
    attest, sent = _isolated(monkeypatch, SimpleNamespace(
        returncode=0, stdout=json.dumps({"rendered_html": rendered, "reason": None}),
    ))
    result = replay.inspect_inline_spa_replay(
        URL, HTML, device="desktop",
        response_headers={"content-type": "text/html",
                          "content-security-policy": "default-src 'self'"},
    )
    assert attest == ["network", "browser"]
    assert sent[0]["resources"][0]["response_headers"]["content-security-policy"] == "default-src 'self'"
    assert result["status"] == "INLINE_DOM_STABLE_IN_OCI"
    assert result["isolated_dom_materiality_observed"] is True
    assert result["isolated_rendered_html_sha256"] == sha256(rendered.encode()).hexdigest()
    assert result["live_site_hydration_proven"] is False
    assert result["same_serp_device_or_population_proven"] is False
    assert result["score_changed"] is False


@pytest.mark.parametrize("response,status", [
    (SimpleNamespace(returncode=2, stdout=json.dumps(
        {"rendered_html": None, "reason": "ISOLATED_RESOURCES_BLOCKED"}
    )), "ISOLATED_RESOURCES_BLOCKED"),
    (SimpleNamespace(returncode=2, stdout=json.dumps(
        {"rendered_html": None, "reason": "ISOLATED_CONTENT_NOT_STABLE"}
    )), "ISOLATED_CONTENT_NOT_STABLE"),
    (SimpleNamespace(returncode=2, stdout=json.dumps(
        {"rendered_html": None, "reason": "LEAK_SECRET_TO_OUTPUT"}
    )), "OCI_OUTPUT_UNVERIFIABLE"),
    (SimpleNamespace(returncode=0, stdout=json.dumps(
        {"rendered_html": None, "reason": None}
    )), "OCI_OUTPUT_UNVERIFIABLE"),
])
def test_abstention_never_promotes_missing_assets(monkeypatch, response, status):
    _isolated(monkeypatch, response)
    result = replay.inspect_inline_spa_replay(URL, HTML, device="mobile")
    assert result["status"] == status
    assert result["isolated_rendered_html_sha256"] is None
    assert result["isolated_dom_materiality_observed"] is False
    assert result["live_primary_content_proven"] is False


def test_no_unattested_container_execution(monkeypatch):
    monkeypatch.setattr(replay, "inspect_local_image", lambda: "sha256:" + "a" * 64)
    monkeypatch.setattr(replay.shutil, "which", lambda name: "/usr/bin/docker")
    from rasai import architecture_isolation_smoke as smoke
    monkeypatch.setattr(smoke, "verify_isolation",
                        lambda **kw: (_ for _ in ()).throw(RuntimeError("denied")))
    monkeypatch.setattr(replay.subprocess, "run",
                        lambda *a, **k: pytest.fail("unattested worker must not execute"))
    result = replay.inspect_inline_spa_replay(URL, HTML, device="desktop")
    assert result["status"] == "OCI_ISOLATION_NOT_ATTESTED"


def test_worker_timeout_is_inconclusive(monkeypatch):
    _isolated(monkeypatch, None)
    monkeypatch.setattr(replay.subprocess, "run", lambda *a, **kw: (
        (_ for _ in ()).throw(subprocess.TimeoutExpired(cmd=["docker"], timeout=40))
    ))
    assert replay.inspect_inline_spa_replay(URL, HTML, device="desktop")["status"] == "OCI_WORKER_TIMEOUT"
