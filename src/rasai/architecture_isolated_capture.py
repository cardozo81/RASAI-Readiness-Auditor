"""OCI sandbox boundary for standalone architecture preview.

Only the host-side PublicWebPinnedOpener can contact public HTTP destinations.
Untrusted HTML/JS executes in a Docker container with --network none, no
mounts, no capabilities, a non-root user, and a read-only root filesystem.
This is opt-in and fails closed before DNS when Docker/image is unavailable.
"""
from __future__ import annotations

import base64
import json
import os
import re
import shutil
import subprocess
from html.parser import HTMLParser
from urllib.parse import urljoin

from rasai.architecture_probe import ProbeCaptures
from rasai.domain import DeviceContext
from rasai.geo_competitor_pinned_egress import PublicWebPinnedOpener
from rasai.search_intelligence.content import (
    ContentFetchStatus, PublicWebFetcher, _validate_public_url, _default_resolver,
)
from rasai.url_utils import normalize_url, normalized_origin

OFFLINE_IMAGE = "rasai-architecture-offline:local"
_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
MAX_ASSETS = 24
MAX_BUNDLE_BYTES = 4_500_000


def inspect_local_image() -> str | None:
    """Verify a locally built OCI image before performing any DNS or HTTP."""
    docker = shutil.which("docker")
    if docker is None:
        return None
    try:
        result = subprocess.run(
            [docker, "image", "inspect", "--format", "{{.Id}}", OFFLINE_IMAGE],
            capture_output=True, text=True, timeout=10, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    digest = result.stdout.strip()
    return digest if result.returncode == 0 and _DIGEST.fullmatch(digest) else None


class _AssetReferences(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.urls: list[str] = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag in {"script", "img", "source", "iframe"} and attributes.get("src"):
            self.urls.append(attributes["src"])
        elif tag == "link" and attributes.get("href"):
            relations = (attributes.get("rel") or "").lower().split()
            if set(relations) & {"stylesheet", "preload", "modulepreload", "icon"}:
                self.urls.append(attributes["href"])


def _encode_asset(url: str, document) -> dict:
    content_type = document.headers.get("content-type", "")
    if (document.status != ContentFetchStatus.OBSERVED
            or document.final_url != url or document.http_status is None
            or not 200 <= document.http_status < 300
            or not isinstance(document.body, bytes)
            or not content_type or "\r" in content_type or "\n" in content_type):
        raise ValueError("Pinned resource unavailable")
    return {
        "url": url,
        "content_type": content_type,
        "status": document.http_status,
        "body_b64": base64.b64encode(document.body).decode("ascii"),
    }


def _bundle_resources(target: str, root, raw: str) -> list[dict]:
    root_record = _encode_asset(target, root)
    parser = _AssetReferences()
    parser.feed(raw)
    if len(parser.urls) > MAX_ASSETS:
        raise ValueError("Too many architecture page resources")
    fetcher = PublicWebFetcher(
        timeout_seconds=4.0, max_redirects=0, max_bytes=500_000,
        opener=PublicWebPinnedOpener(),
    )
    assets = [root_record]
    seen = {target}
    for reference in parser.urls:
        candidate = normalize_url(urljoin(target, reference))
        if candidate in seen:
            continue
        # Fail closed if the page needs third-party JS/CSS/fonts.
        if normalized_origin(candidate) != normalized_origin(target):
            raise ValueError("External page resources cannot be replayed offline")
        seen.add(candidate)
        _validate_public_url(candidate, _default_resolver)
        assets.append(_encode_asset(candidate, fetcher.fetch(candidate)))
    return assets


def sandbox_command(docker: str, digest: str) -> list[str]:
    """Immutable image identifier and fixed no-network flags, without volumes."""
    if not _DIGEST.fullmatch(digest):
        raise ValueError("OCI image identifier must be a verified local digest")
    return [
        docker, "run", "--rm", "--interactive", "--pull=never",
        "--network=none", "--read-only", "--cap-drop=ALL",
        "--security-opt=no-new-privileges", "--pids-limit=128",
        "--memory=1g", "--cpus=1", "--user=10001:10001",
        "--tmpfs=/tmp:rw,nosuid,nodev,size=128m",
        "--env=PYTHONIOENCODING=utf-8",
        digest,
    ]


def capture_isolated_public_architecture(url: str, device: DeviceContext) -> ProbeCaptures:
    """Browser has no network; only vetted root/assets are passed on stdin."""
    if device not in {DeviceContext.MOBILE, DeviceContext.DESKTOP}:
        raise ValueError("Unsupported architecture probe device")
    # No DNS, browser or site request occurs before checking local sandbox.
    digest = inspect_local_image()
    if digest is None:
        return ProbeCaptures(url, url, device, None, None, "OCI_IMAGE_NOT_AVAILABLE")
    docker = shutil.which("docker")
    if docker is None:
        return ProbeCaptures(url, url, device, None, None, "OCI_RUNTIME_NOT_AVAILABLE")
    try:
        target = _validate_public_url(normalize_url(url), _default_resolver)
    except (ValueError, OSError):
        return ProbeCaptures(url, url, device, None, None, "PUBLIC_TARGET_REJECTED")
    fetcher = PublicWebFetcher(
        timeout_seconds=8.0, max_redirects=0, max_bytes=1_000_000,
        opener=PublicWebPinnedOpener(),
    )
    document = fetcher.fetch(target)
    if (document.status != ContentFetchStatus.OBSERVED
            or document.final_url != target or document.http_status is None
            or not 200 <= document.http_status < 300
            or "text/html" not in document.headers.get("content-type", "").lower()):
        return ProbeCaptures(target, target, device, None, None, "PUBLIC_HTML_UNAVAILABLE")
    raw = document.body.decode("utf-8", errors="replace")
    try:
        resources = _bundle_resources(target, document, raw)
        payload = json.dumps({
            "url": target, "device": device.value.lower(), "resources": resources,
        }, separators=(",", ":"), ensure_ascii=False)
        if len(payload.encode("utf-8")) > MAX_BUNDLE_BYTES:
            raise ValueError("Offline manifest size cap")
        # stdin is only page data; no host mounts, Docker API socket, audit.db,
        # provider keys or parent environment are delivered to the container.
        finished = subprocess.run(
            sandbox_command(docker, digest), input=payload, capture_output=True,
            text=True, timeout=40, check=False,
        )
        if finished.returncode not in {0, 2} or len(finished.stdout) > 1_500_000:
            raise ValueError("Offline renderer rejected")
        result = json.loads(finished.stdout)
        if (not isinstance(result, dict)
                or set(result) != {"rendered_html", "reason"}
                or (result["reason"] is not None and
                    (not isinstance(result["reason"], str) or len(result["reason"]) > 100))
                or (result["rendered_html"] is not None and
                    (not isinstance(result["rendered_html"], str)
                     or len(result["rendered_html"]) > 1_000_000))):
            raise ValueError("Invalid offline renderer response")
        if finished.returncode == 0 and result["reason"] is None and result["rendered_html"] is not None:
            return ProbeCaptures(target, target, device, raw, result["rendered_html"])
        return ProbeCaptures(target, target, device, raw, None, "ISOLATED_RENDER_INCONCLUSIVE")
    except (ValueError, OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
        return ProbeCaptures(target, target, device, raw, None, "ISOLATED_RENDER_INCONCLUSIVE")
