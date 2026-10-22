"""Bounded offline asset replay contract; no DNS, HTTP or Docker in tests."""
from __future__ import annotations

import base64
from hashlib import sha256
import json
from pathlib import Path

import pytest

from rasai.geo_competitor_offline_assets import (
    CONTRACT, load_offline_asset_bundle,
)
from rasai import geo_competitor_inline_render as replay


URL = "https://example.org/catalog"
JS_URL = "https://example.org/scripts/app.js"
BODY = b"document.querySelector('main').textContent = 'Material from bundled JS';"


def _entry(url=JS_URL, content=BODY, mime="application/javascript"):
    return {"url": url, "content_type": mime,
            "body_b64": base64.b64encode(content).decode("ascii"),
            "sha256": sha256(content).hexdigest()}


def _file(tmp_path, resources=None, **changes):
    payload = {
        "contract_version": CONTRACT, "target_url": URL,
        "resources": resources if resources is not None else [_entry()],
    }
    payload.update(changes)
    path = tmp_path / "assets.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_local_resources_are_verified_and_never_source_attested(tmp_path, monkeypatch):
    path = _file(tmp_path)
    resources, digest = load_offline_asset_bundle(path, target_url=URL)
    assert len(resources) == 1
    assert resources[0]["sha256"] == sha256(BODY).hexdigest()
    assert len(digest) == 64
    monkeypatch.setattr(replay, "inspect_local_image", lambda: None)
    result = replay.inspect_inline_spa_replay(
        URL, b"<html><main>Shell only</main><script src='/scripts/app.js'></script></html>",
        device="mobile", response_headers={"content-type": "text/html"},
        additional_resources=resources, asset_bundle_sha256=digest,
    )
    assert result["status"] == "OCI_IMAGE_NOT_AVAILABLE"
    assert result["additional_public_http_requests"] == 0
    assert result["offline_asset_provenance_attested"] is False


@pytest.mark.parametrize("change", [
    {"target_url": "https://other.example.org/catalog"},
    {"contract_version": "unknown"},
    {"resources": [_entry(url="https://cdn.example.com/app.js")]},
    {"resources": [_entry(url=URL)]},
    {"resources": [_entry(), _entry()]},
    {"resources": [{**_entry(), "sha256": "0" * 64}]},
    {"resources": [_entry(content=b"x" * 2_000_001)]},
    {"resources": [_entry(mime="text/html")]},
    {"resources": []},
])
def test_bundle_refuses_ambiguous_unbounded_or_other_origin_assets(tmp_path, change):
    file = _file(tmp_path, **change)
    with pytest.raises(ValueError):
        load_offline_asset_bundle(file, target_url=URL)


def test_duplicate_json_and_non_json_numbers_fail_even_if_rehashed(tmp_path):
    file = tmp_path / "assets.json"
    file.write_text('{"contract_version":"'+CONTRACT+'","target_url":"'+URL+'",'
                    '"resources":[],"resources":[]}', encoding="utf-8")
    with pytest.raises(ValueError):
        load_offline_asset_bundle(file, target_url=URL)
    file.write_text('{"contract_version":"'+CONTRACT+'","target_url":"'+URL+'",'
                    '"resources":NaN}', encoding="utf-8")
    with pytest.raises(ValueError):
        load_offline_asset_bundle(file, target_url=URL)


def test_source_aud_package_and_symlink_are_forbidden(tmp_path):
    package = tmp_path / "AUD-TEMP"
    package.mkdir()
    file = package / "assets.json"
    file.write_text(json.dumps({"contract_version": CONTRACT, "target_url": URL,
                                "resources": [_entry()]}), encoding="utf-8")
    with pytest.raises(ValueError):
        load_offline_asset_bundle(file, target_url=URL)
    outside = _file(tmp_path)
    link = tmp_path / "link.json"
    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("symlink unsupported")
    with pytest.raises(ValueError):
        load_offline_asset_bundle(link, target_url=URL)


def test_inline_replay_rejects_forged_asset_bytes_before_worker(monkeypatch):
    monkeypatch.setattr(replay, "inspect_local_image",
                        lambda: pytest.fail("unverified asset must not enter Docker"))
    result = replay.inspect_inline_spa_replay(
        URL, b"<html><main>Shell only</main></html>", device="desktop",
        additional_resources=[{**_entry(), "body_b64": base64.b64encode(b"forged").decode()}],
        asset_bundle_sha256="a" * 64,
    )
    assert result["status"] == "OFFLINE_ASSET_INPUT_UNVERIFIABLE"
    assert result["isolated_dom_materiality_observed"] is False


def test_live_site_and_primary_content_are_never_promoted(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from rasai import architecture_isolation_smoke as smoke
    resources, digest = load_offline_asset_bundle(_file(tmp_path), target_url=URL)
    monkeypatch.setattr(replay, "inspect_local_image", lambda: "sha256:" + "a" * 64)
    monkeypatch.setattr(replay.shutil, "which", lambda _: "/usr/bin/docker")
    monkeypatch.setattr(smoke, "verify_isolation", lambda **kw: True)
    monkeypatch.setattr(smoke, "verify_browser_canary", lambda **kw: True)
    recorded = []

    def run(args, **kwargs):
        assert "--network=none" in args
        manifest = json.loads(kwargs["input"])
        recorded.extend(manifest["resources"])
        return SimpleNamespace(returncode=0, stdout=json.dumps({
            "rendered_html": "<html><main>Material from bundled JS</main></html>",
            "reason": None,
        }))
    monkeypatch.setattr(replay.subprocess, "run", run)
    result = replay.inspect_inline_spa_replay(
        URL, b"<html><main>Shell only</main><script src='/scripts/app.js'></script></html>",
        device="desktop", additional_resources=resources, asset_bundle_sha256=digest,
        response_headers={"content-type": "text/html"},
    )
    assert len(recorded) == 2
    assert recorded[1]["url"] == JS_URL
    assert base64.b64decode(recorded[1]["body_b64"]) == BODY
    assert result["status"] == "INLINE_DOM_STABLE_IN_OCI"
    assert result["offline_supplied_asset_count"] == 1
    assert result["offline_asset_bundle_sha256"] == digest
    assert result["offline_asset_provenance_attested"] is False
    assert result["live_site_hydration_proven"] is False
    assert result["live_primary_content_proven"] is False
    assert result["additional_public_http_requests"] == 0
