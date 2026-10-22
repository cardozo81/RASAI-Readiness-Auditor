"""Opt-in, networkless inline-JavaScript replay for COBS evidence.

Reuses the OCI architecture worker unchanged. Only previously authorized
HTML bytes are supplied. Missing assets, failed isolation or unstable DOM
produce explicit inconclusive outcomes, not live-site attestation.
"""
from __future__ import annotations

import base64
import binascii
from hashlib import sha256
import json
import re
import shutil
import subprocess
from typing import Any, Mapping, Sequence
from urllib.parse import urlsplit

from rasai.architecture_isolated_capture import (
    inspect_local_image, sandbox_command,
)
from rasai.url_utils import normalize_url
from rasai.geo_competitor_offline_assets import _origin, MAX_ASSETS, MAX_TOTAL_ASSET_BYTES

_MAX_HTML_BYTES = 1_000_000
_MAX_MANIFEST_BYTES = 4_500_000
_MAX_OUTPUT_BYTES = 1_500_000
_IMAGE_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_ALLOWED_HEADERS = (
    "content-security-policy", "x-content-type-options",
    "cross-origin-resource-policy", "cross-origin-opener-policy",
    "cross-origin-embedder-policy", "referrer-policy",
)
_WORKER_REASONS = frozenset({
    "ISOLATED_BROWSER_UNAVAILABLE", "ISOLATED_MANIFEST_INVALID",
    "ISOLATED_NAVIGATION_NOT_ATTESTED", "ISOLATED_RENDER_LIMIT",
    "ISOLATED_RESOURCES_BLOCKED", "ISOLATED_CONTENT_NOT_STABLE",
    "ISOLATED_CONTENT_NOT_ATTESTED",
})


def _outcome(status: str, *, source_sha256: str | None = None,
             device: str | None = None, rendered_sha256: str | None = None,
             rendered_bytes: int | None = None,
             bundle_sha256: str | None = None,
             supplied_assets: int = 0,
             lexical_inventory: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "contract_version": "RASAI-COBS-NETWORKLESS-INLINE-REPLAY-1",
        "status": status, "source_html_sha256": source_sha256,
        "isolated_rendered_html_sha256": rendered_sha256,
        "isolated_rendered_html_bytes": rendered_bytes,
        "replay_device": device,
        "offline_asset_bundle_sha256": bundle_sha256,
        "offline_supplied_asset_count": supplied_assets,
        "offline_asset_provenance_attested": False,
        "isolated_dom_materiality_observed": status == "INLINE_DOM_STABLE_IN_OCI",
        "live_site_hydration_proven": False,
        "live_primary_content_proven": False,
        "same_serp_device_or_population_proven": False,
        "rendered_html_persisted": False,
        "isolated_lexical_inventory": lexical_inventory,
        "isolated_lexical_inventory_is_live_evidence": False,
        "additional_public_http_requests": 0,
        "audit_writes": 0, "score_changed": False,
        "limitations": (
            "Replay de JavaScript inline a partir de HTML ja obtido com consentimento; "
            "Chromium sem rede e sem recursos externos. Estabilidade no OCI "
            "nao atesta hidratacao live, conteudo editorial, equivalencia "
            "locale/device, indexacao, citacoes ou ranking."
        ),
    }



def _bounded_lexical_inventory(
    url: str, source_html: bytes, rendered_html: bytes, *,
    source_content_type: str,
) -> dict[str, Any]:
    """Compare text features of the SAME bytes before and after OCI replay.

    This is a lexical, offline experiment, not primary-content, crawl,
    accessibility, audience, editorial-quality or Search-provider evidence.
    Never persist the rendered DOM or raw source text.
    """
    from rasai.search_intelligence.content import extract_rendered_page_features

    domain = urlsplit(url).hostname or ""
    before = extract_rendered_page_features(
        source_html, requested_url=url, final_url=url,
        domain=domain, query="", content_type=source_content_type,
    )
    after = extract_rendered_page_features(
        rendered_html, requested_url=url, final_url=url,
        domain=domain, query="", content_type="text/html; charset=utf-8",
    )

    def bounded(value: Any, max_chars: int) -> str | None:
        return value[:max_chars] if isinstance(value, str) else None

    def snapshot(features: Any) -> dict[str, Any]:
        headings = tuple(features.headings)
        types = tuple(features.jsonld_types)
        return {
            "word_count_observed_html": features.word_count,
            "title": bounded(features.title, 300),
            "meta_description": bounded(features.meta_description, 300),
            "headings_sample": [bounded(item, 240) for item in headings[:20]],
            "headings_truncated": len(headings) > 20
                or any(len(item) > 240 for item in headings[:20]),
            "jsonld_types_sample": [bounded(item, 120) for item in types[:20]],
            "jsonld_types_truncated": len(types) > 20
                or any(len(item) > 120 for item in types[:20]),
        }

    return {
        "contract_version": "RASAI-COBS-NETWORKLESS-LEXICAL-INVENTORY-1",
        "method": "SAME_SOURCE_HTML_VS_OCI_DOM_OFFLINE",
        "static_html": snapshot(before),
        "isolated_dom": snapshot(after),
        "observed_word_count_delta": after.word_count - before.word_count,
        "content_readiness_proven": False,
        "live_site_hydration_proven": False,
        "primary_content_proven": False,
        "semantic_or_editorial_gap_proven": False,
        "same_serp_population_proven": False,
        "raw_html_persisted": False,
        "additional_public_http_requests": 0,
    }


def inspect_inline_spa_replay(
    url: str, html: bytes, *, device: str,
    response_headers: Mapping[str, str] | None = None,
    additional_resources: Sequence[Mapping[str, str]] = (),
    asset_bundle_sha256: str | None = None,
) -> dict[str, Any]:
    """Replay one already-obtained document in isolated OCI without network.

    Caller enforces robots, exact-host and GET consent. This routine cannot
    fetch assets, bypass CSP/TLS or authenticate any external provider.
    """
    if device not in ("desktop", "mobile"):
        raise ValueError("explicit desktop/mobile replay device required")
    if not isinstance(url, str) or len(url) > 2048:
        raise ValueError("bounded canonical replay URL required")
    try:
        parts = urlsplit(url)
        valid = (
            parts.scheme in {"http", "https"}
            and parts.hostname is not None and parts.username is None
            and parts.password is None and not parts.fragment
            and normalize_url(url) == url
        )
    except ValueError:
        valid = False
    if not valid:
        raise ValueError("unambiguous canonical HTTP(S) replay URL required")
    if not isinstance(html, bytes) or not html or len(html) > _MAX_HTML_BYTES:
        return _outcome("INPUT_HTML_NOT_ELIGIBLE", device=device)
    source_sha = sha256(html).hexdigest()
    if response_headers is None:
        response_headers = {"content-type": "text/html; charset=utf-8"}
    if not isinstance(response_headers, Mapping):
        return _outcome("RESPONSE_POLICY_UNVERIFIABLE", source_sha256=source_sha, device=device)
    lower_headers: dict[str, str] = {}
    for key, value in response_headers.items():
        if not isinstance(key, str) or not isinstance(value, str):
            return _outcome("RESPONSE_POLICY_UNVERIFIABLE", source_sha256=source_sha, device=device)
        name = key.lower()
        if name in ("content-type", *_ALLOWED_HEADERS):
            if (name in lower_headers or len(value) > 8192 or
                    any(ord(ch) < 32 and ch != "\t" for ch in value)):
                return _outcome("RESPONSE_POLICY_UNVERIFIABLE", source_sha256=source_sha, device=device)
            lower_headers[name] = value
    mime = lower_headers.get("content-type")
    if not mime or mime.split(";", 1)[0].strip().lower() not in (
        "text/html", "application/xhtml+xml"
    ):
        return _outcome("RESPONSE_POLICY_UNVERIFIABLE", source_sha256=source_sha, device=device)
    # A local asset bundle is NOT source authenticated. A replay may use
    # preexisting same-origin bytes but cannot fetch any missing resources.
    resource_entries = []
    if (isinstance(additional_resources, (str, bytes))
            or not isinstance(additional_resources, (list, tuple))
            or len(additional_resources) > MAX_ASSETS):
        return _outcome("OFFLINE_ASSET_INPUT_UNVERIFIABLE", source_sha256=source_sha, device=device)
    if additional_resources and (
        not isinstance(asset_bundle_sha256, str)
        or re.fullmatch(r"[0-9a-f]{64}", asset_bundle_sha256) is None
    ):
        return _outcome("OFFLINE_ASSET_INPUT_UNVERIFIABLE", source_sha256=source_sha, device=device)
    seen = {url}
    total = 0
    for item in additional_resources:
        if not isinstance(item, Mapping) or set(item) != {
            "url", "content_type", "body_b64", "sha256",
        }:
            return _outcome("OFFLINE_ASSET_INPUT_UNVERIFIABLE", source_sha256=source_sha, device=device)
        asset_url = item["url"]
        content_type = item["content_type"]
        encoded = item["body_b64"]
        digest = item["sha256"]
        try:
            same_origin = _origin(asset_url) == _origin(url)
            body = base64.b64decode(encoded, validate=True)
        except (ValueError, TypeError, binascii.Error):
            return _outcome("OFFLINE_ASSET_INPUT_UNVERIFIABLE", source_sha256=source_sha, device=device)
        total += len(body)
        if (not same_origin or asset_url in seen
                or not isinstance(content_type, str) or len(content_type) > 120
                or "\r" in content_type or "\n" in content_type
                or not isinstance(digest, str) or sha256(body).hexdigest() != digest
                or not body or total > MAX_TOTAL_ASSET_BYTES):
            return _outcome("OFFLINE_ASSET_INPUT_UNVERIFIABLE", source_sha256=source_sha, device=device)
        seen.add(asset_url)
        resource_entries.append({
            "url": asset_url, "body_b64": encoded,
            "content_type": content_type, "status": 200,
            "response_headers": {"content-type": content_type},
        })
    # Preserve real CSP; never relax source policy to force a positive result.
    payload = json.dumps({
        "url": url, "device": device,
        "resources": [{
            "url": url, "body_b64": base64.b64encode(html).decode("ascii"),
            "content_type": mime, "status": 200,
            "response_headers": lower_headers,
        }, *resource_entries],
    }, separators=(",", ":"), ensure_ascii=False)
    if len(payload.encode("utf-8")) > _MAX_MANIFEST_BYTES:
        return _outcome("INPUT_BUNDLE_LIMIT", source_sha256=source_sha, device=device)
    digest = inspect_local_image()
    if not isinstance(digest, str) or not _IMAGE_DIGEST.fullmatch(digest):
        return _outcome("OCI_IMAGE_NOT_AVAILABLE", source_sha256=source_sha, device=device)
    docker = shutil.which("docker")
    if docker is None:
        return _outcome("OCI_RUNTIME_NOT_AVAILABLE", source_sha256=source_sha, device=device)
    try:
        from rasai.architecture_isolation_smoke import (
            verify_isolation, verify_browser_canary,
        )
        verify_isolation(digest=digest, docker=docker)
        verify_browser_canary(digest=digest, docker=docker)
    except (RuntimeError, OSError, ValueError, subprocess.TimeoutExpired):
        return _outcome("OCI_ISOLATION_NOT_ATTESTED", source_sha256=source_sha, device=device)
    try:
        finished = subprocess.run(
            sandbox_command(docker, digest), input=payload,
            capture_output=True, text=True, timeout=40, check=False,
        )
        if (finished.returncode not in (0, 2)
                or len(finished.stdout.encode("utf-8")) > _MAX_OUTPUT_BYTES):
            status = "OCI_PROCESS_UNVERIFIABLE"
        else:
            result = json.loads(finished.stdout)
            if not isinstance(result, dict) or set(result) != {"rendered_html", "reason"}:
                status = "OCI_OUTPUT_UNVERIFIABLE"
            elif (finished.returncode == 0 and result["reason"] is None
                  and isinstance(result["rendered_html"], str)):
                rendered = result["rendered_html"].encode("utf-8")
                if len(rendered) > _MAX_HTML_BYTES:
                    status = "OCI_OUTPUT_UNVERIFIABLE"
                else:
                    lexical = _bounded_lexical_inventory(
                        url, html, rendered,
                        source_content_type=lower_headers["content-type"],
                    )
                    return _outcome(
                        "INLINE_DOM_STABLE_IN_OCI", source_sha256=source_sha,
                        device=device, rendered_sha256=sha256(rendered).hexdigest(),
                        rendered_bytes=len(rendered),
                        bundle_sha256=asset_bundle_sha256,
                        supplied_assets=len(resource_entries),
                        lexical_inventory=lexical,
                    )
            elif (finished.returncode == 2 and result["rendered_html"] is None
                  and result["reason"] in _WORKER_REASONS):
                status = result["reason"]
            else:
                status = "OCI_OUTPUT_UNVERIFIABLE"
    except subprocess.TimeoutExpired:
        status = "OCI_WORKER_TIMEOUT"
    except (OSError, ValueError, TypeError, UnicodeError, json.JSONDecodeError):
        status = "OCI_OUTPUT_UNVERIFIABLE"
    return _outcome(status, source_sha256=source_sha, device=device,
                    bundle_sha256=asset_bundle_sha256,
                    supplied_assets=len(resource_entries))


__all__ = ["inspect_inline_spa_replay"]
