"""Pure contract of the unprivileged, networkless architecture renderer."""
import base64
import pytest

from rasai.architecture_offline_worker import validate_bundle, MAX_ENTRIES


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


def test_manifest_caps_total_body_and_resources():
    candidate = bundle()
    candidate["resources"][0]["body_b64"] = base64.b64encode(b"x" * 3_000_001).decode()
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
