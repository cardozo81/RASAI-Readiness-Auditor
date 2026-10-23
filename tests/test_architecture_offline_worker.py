"""Pure contract of the unprivileged, networkless architecture renderer."""
import base64
import json
import pytest

from rasai.architecture_offline_worker import (
    validate_bundle, MAX_ENTRIES, MAX_MANIFEST_BYTES,
    MAX_RESOURCE_BYTES, MAX_BROWSER_REQUESTS,
)
from rasai.architecture_resource_budget import (
    MAX_ASSETS, MAX_ROOT_BYTES, MAX_ASSET_BYTES, MAX_STYLESHEET_BYTES,
    MAX_SCRIPT_BYTES, MAX_BUNDLE_BYTES,
)


def bundle():
    return {
        "url": "https://example.org/",
        "device": "mobile",
        "resources": [{
            "url": "https://example.org/",
            "body_b64": base64.b64encode(b"<main>offline</main>").decode(),
            "status": 200,
            "content_type": "text/html",
        }],
    }


def test_valid_offline_bundle():
    target, device, table = validate_bundle(bundle())
    assert target == "https://example.org/"
    assert device == "mobile"
    assert table[target][0] == b"<main>offline</main>"


@pytest.mark.parametrize("mutator", [
    lambda b: b.update({"url": "http://localhost/"}),
    lambda b: b.update({"device": "phone"}),
    lambda b: b["resources"][0].update({"url": "https://private.example/"}),
    lambda b: b["resources"][0].update({"body_b64": "not-base64!"}),
    lambda b: b["resources"][0].update({"status": 302}),
    lambda b: b["resources"][0].update({"content_type": "text/html\r\nx-evil:1"}),
    lambda b: b["resources"].append(dict(b["resources"][0])),
    lambda b: b.update({"extra": "not allowed"}),
])
def test_offline_manifest_rejects_malformed_or_divergent_resource(mutator):
    candidate = bundle()
    mutator(candidate)
    with pytest.raises(ValueError):
        validate_bundle(candidate)


def test_host_and_worker_caps_support_all_64_assets_at_existing_per_resource_byte_limits():
    assert MAX_ASSETS == 64
    assert MAX_ENTRIES == MAX_ASSETS + 1 == 65
    assert MAX_BROWSER_REQUESTS == 70
    assert MAX_BUNDLE_BYTES == MAX_MANIFEST_BYTES == 52_000_000
    assert MAX_RESOURCE_BYTES == MAX_ROOT_BYTES + MAX_ASSETS * MAX_ASSET_BYTES

    candidate = bundle()
    candidate["resources"][0]["body_b64"] = base64.b64encode(
        b"h" * MAX_ROOT_BYTES
    ).decode("ascii")
    asset_body = base64.b64encode(b"x" * MAX_ASSET_BYTES).decode("ascii")
    candidate["resources"].extend({
        "url": f"https://example.org/resource-{n}.js",
        "body_b64": asset_body,
        "status": 200,
        "content_type": "text/javascript",
    } for n in range(MAX_ASSETS))
    payload_bytes = len(json.dumps(candidate, separators=(",", ":")).encode("utf-8"))
    # Neither the host nor the OCI stdin limit rejects the maximum legal
    # inventory before the worker enforces its intended decoded-byte budget.
    assert payload_bytes < MAX_BUNDLE_BYTES
    _target, _device, table = validate_bundle(candidate)
    assert len(table) == MAX_ENTRIES
    assert sum(len(item[0]) for item in table.values()) == MAX_RESOURCE_BYTES


def test_manifest_caps_total_body_and_resources():
    candidate = bundle()
    candidate["resources"][0]["body_b64"] = base64.b64encode(b"x" * (MAX_RESOURCE_BYTES + 1)).decode()
    with pytest.raises(ValueError, match="budget"):
        validate_bundle(candidate)
    candidate = bundle()
    candidate["resources"].extend({
        "url": f"https://example.org/{n}",
        "body_b64": "",
        "status": 200,
        "content_type": "text/plain",
    } for n in range(MAX_ENTRIES))
    with pytest.raises(ValueError):
        validate_bundle(candidate)


def test_offline_manifest_retains_csp_and_rejects_header_injection():
    candidate = bundle()
    candidate["resources"][0]["response_headers"] = {
        "content-type": "text/html",
        "content-security-policy": "default-src 'self'; script-src 'none'",
    }
    _, _, table = validate_bundle(candidate)
    assert table["https://example.org/"][3]["content-security-policy"].endswith("'none'")
    candidate["resources"][0]["response_headers"]["content-security-policy"] = "abc\r\nset-cookie:bad"
    with pytest.raises(ValueError, match="headers"):
        validate_bundle(candidate)


def test_worker_accepts_large_css_while_retaining_small_default_asset_limit():
    candidate = bundle()
    css = b"c" * 1_500_000
    candidate["resources"].append({
        "url": "https://example.org/large.css",
        "resource_kind": "stylesheet",
        "body_b64": base64.b64encode(css).decode("ascii"),
        "status": 200,
        "content_type": "text/css; charset=utf-8",
    })
    _, _, table = validate_bundle(candidate)
    assert table["https://example.org/large.css"][0] == css
    assert MAX_STYLESHEET_BYTES == 2_000_000
    assert MAX_ASSET_BYTES == 500_000


@pytest.mark.parametrize("mime,kind,cap", [
    ("text/javascript", "script", MAX_SCRIPT_BYTES),
    ("application/javascript", "modulepreload", MAX_SCRIPT_BYTES),
    ("text/html", "unknown", MAX_ASSET_BYTES),
    ("text/css", "stylesheet", MAX_STYLESHEET_BYTES),
])
def test_worker_refuses_single_asset_above_mime_budget(mime, kind, cap):
    candidate = bundle()
    candidate["resources"].append({
        "url": "https://example.org/asset",
        "resource_kind": kind,
        "body_b64": base64.b64encode(b"x" * (cap + 1)).decode("ascii"),
        "status": 200,
        "content_type": mime,
    })
    with pytest.raises(ValueError, match="individual resource budget"):
        validate_bundle(candidate)


def test_worker_rejects_html_root_over_document_limit():
    candidate = bundle()
    candidate["resources"][0]["body_b64"] = base64.b64encode(
        b"x" * (MAX_ROOT_BYTES + 1)
    ).decode("ascii")
    with pytest.raises(ValueError, match="individual resource budget"):
        validate_bundle(candidate)


@pytest.mark.parametrize("mime,role", [
    ("text/javascript; charset=utf-8", "script"),
    ("application/javascript", "modulepreload"),
    ("application/ecmascript", "script"),
])
def test_worker_accepts_large_declared_javascript_below_four_megabytes(mime, role):
    candidate = bundle()
    script = b"j" * 1_500_000
    candidate["resources"].append({
        "url": "https://example.org/program.js",
        "resource_kind": role,
        "body_b64": base64.b64encode(script).decode("ascii"),
        "status": 200,
        "content_type": mime,
    })
    _, _, entries = validate_bundle(candidate)
    assert entries["https://example.org/program.js"][0] == script


@pytest.mark.parametrize("mime,kind", [
    ("text/javascript", "image"),
    ("text/javascript", "unknown"),
    ("text/plain", "script"),
    ("text/html", "script"),
    ("text/css", "script"),
    ("application/javascript", "stylesheet"),
])
def test_worker_rejects_large_scripts_when_role_or_mime_mismatch(mime, kind):
    candidate = bundle()
    candidate["resources"].append({
        "url": "https://example.org/ambiguous-resource",
        "resource_kind": kind,
        "body_b64": base64.b64encode(b"x" * 650_000).decode("ascii"),
        "status": 200,
        "content_type": mime,
    })
    with pytest.raises(ValueError, match="individual resource budget"):
        validate_bundle(candidate)


def test_worker_refuses_forged_or_unknown_resource_role():
    for role in ("document", "https://confidential.example", "runtime", None):
        candidate = bundle()
        candidate["resources"].append({
            "url": "https://example.org/asset",
            "resource_kind": role,
            "body_b64": "",
            "status": 200,
            "content_type": "text/javascript",
        })
        with pytest.raises(ValueError, match="resource kind"):
            validate_bundle(candidate)


def test_worker_legacy_resource_without_role_cannot_claim_large_js_allowance():
    candidate = bundle()
    candidate["resources"].append({
        "url": "https://example.org/legacy.js",
        "body_b64": base64.b64encode(b"x" * 600_000).decode("ascii"),
        "status": 200,
        "content_type": "text/javascript",
    })
    with pytest.raises(ValueError, match="individual resource budget"):
        validate_bundle(candidate)
