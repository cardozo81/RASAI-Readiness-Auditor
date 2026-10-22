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


def test_successful_replay_exposes_only_bounded_offline_lexical_differences(monkeypatch):
    """A real source-to-OCI DOM difference is observable, but not live content."""
    rendered = (
        "<html><head><title>Produto de exemplo</title></head>"
        "<body><main><h1>Conteudo carregado no OCI</h1>"
        "<p>Descricao detalhada apos JavaScript.</p></main></body></html>"
    )
    _isolated(monkeypatch, SimpleNamespace(
        returncode=0,
        stdout=json.dumps({"rendered_html": rendered, "reason": None}),
    ))
    result = replay.inspect_inline_spa_replay(URL, HTML, device="desktop")
    inventory = result["isolated_lexical_inventory"]
    assert result["status"] == "INLINE_DOM_STABLE_IN_OCI"
    assert inventory["contract_version"] == "RASAI-COBS-NETWORKLESS-LEXICAL-INVENTORY-1"
    assert inventory["method"] == "SAME_SOURCE_HTML_VS_OCI_DOM_OFFLINE"
    assert inventory["static_html"]["word_count_observed_html"] == 0
    assert inventory["isolated_dom"]["word_count_observed_html"] > 0
    assert inventory["observed_word_count_delta"] > 0
    assert inventory["isolated_dom"]["title"] == "Produto de exemplo"
    assert "Conteudo carregado no OCI" in inventory["isolated_dom"]["headings_sample"]
    assert not inventory["content_readiness_proven"]
    assert not inventory["live_site_hydration_proven"]
    assert not inventory["primary_content_proven"]
    assert not inventory["semantic_or_editorial_gap_proven"]
    assert result["isolated_lexical_inventory_is_live_evidence"] is False
    assert result["rendered_html_persisted"] is False
    assert result["additional_public_http_requests"] == 0


def test_lexical_inventory_is_bounded_and_never_exposes_raw_dom(monkeypatch):
    """Bound labels and headings; raw HTML must not appear in advisory metadata."""
    secret_marker = "DO_NOT_PERSIST_RAW_HTML"
    rendered = "<html><head><title>" + "T" * 900 + "</title></head><body>"
    rendered += "".join(f"<h2>{'A' * 270} {i}</h2>" for i in range(28))
    rendered += "<script>const private = '" + secret_marker + "';</script></body></html>"
    _isolated(monkeypatch, SimpleNamespace(
        returncode=0,
        stdout=json.dumps({"rendered_html": rendered, "reason": None}),
    ))
    result = replay.inspect_inline_spa_replay(URL, HTML, device="mobile")
    inventory = result["isolated_lexical_inventory"]["isolated_dom"]
    assert len(inventory["title"]) == 300
    assert len(inventory["headings_sample"]) == 20
    assert all(len(value) <= 240 for value in inventory["headings_sample"])
    assert inventory["headings_truncated"] is True
    assert secret_marker not in json.dumps(result)
    assert result["score_changed"] is False


def test_inconclusive_replay_has_no_lexical_inventory(monkeypatch):
    _isolated(monkeypatch, SimpleNamespace(
        returncode=2,
        stdout=json.dumps({
            "rendered_html": None, "reason": "ISOLATED_RESOURCES_BLOCKED",
        }),
    ))
    result = replay.inspect_inline_spa_replay(URL, HTML, device="mobile")
    assert result["status"] == "ISOLATED_RESOURCES_BLOCKED"
    assert result["isolated_lexical_inventory"] is None
    assert result["isolated_dom_materiality_observed"] is False
