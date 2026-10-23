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

from rasai.architecture_public_html import public_html_failure
from rasai.architecture_image_identity import IMAGE_SOURCE_LABEL, expected_source_sha256
from rasai.architecture_resource_budget import MAX_ASSETS, MAX_BUNDLE_BYTES, MAX_ROOT_BYTES, MAX_ASSET_BYTES
from rasai.architecture_probe import ProbeCaptures, with_capture_origin
from rasai.domain import DeviceContext
from rasai.geo_competitor_pinned_egress import PublicWebPinnedOpener
from rasai.search_intelligence.content import (
    ContentFetchStatus, PublicWebFetcher, _validate_public_url, _default_resolver,
)
from rasai.url_utils import normalize_url

OFFLINE_IMAGE = "rasai-architecture-offline:local"
_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")


class ArchitectureAssetFailure(ValueError):
    """Bounded resource failure code. Never hold page URLs or content."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def local_docker_transport(docker: str) -> bool:
    """Reject remote daemons before transferring sources or page evidence."""
    host_override = os.environ.get("DOCKER_HOST", "").strip()
    if host_override and not host_override.startswith(("unix://", "npipe://")):
        return False
    try:
        context = subprocess.run(
            [docker, "context", "inspect", "--format", "{{.Endpoints.docker.Host}}"],
            capture_output=True, text=True, timeout=10, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return (
        context.returncode == 0
        and context.stdout.strip().startswith(("unix://", "npipe://"))
    )


def inspect_local_image() -> str | None:
    """Verify a locally built OCI image before performing any DNS or HTTP."""
    docker = shutil.which("docker")
    if docker is None:
        return None
    if not local_docker_transport(docker):
        return None
    # The tag can persist across RASAi updates. Reject images carrying no
    # identity label or a label from an older worker before any site DNS/HTTP.
    try:
        expected = expected_source_sha256()
        result = subprocess.run(
            [docker, "image", "inspect", "--format",
             '{{.Id}}|{{index .Config.Labels "' + IMAGE_SOURCE_LABEL + '"}}',
             OFFLINE_IMAGE],
            capture_output=True, text=True, timeout=10, check=False,
        )
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None
    parts = result.stdout.strip().split("|")
    if result.returncode != 0 or len(parts) != 2:
        return None
    digest, image_source = parts
    return digest if _DIGEST.fullmatch(digest) and image_source == expected else None


class _AssetReferences(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.urls: list[str] = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag in {"script", "img", "source", "iframe"} and attributes.get("src"):
            self.urls.append(attributes["src"])
        elif tag == "link" and attributes.get("href"):
            relations = set((attributes.get("rel") or "").lower().split())
            relevant = relations & {"stylesheet", "preload", "modulepreload", "icon"}
            if relevant:
                reference = attributes["href"]
                # Inline data: favicons are image-only document metadata.
                # They have no HTTP endpoint to pin and keeping their original
                # HTML preserves browser fidelity without enabling egress.
                # Never exempt executable script, style, or preload references.
                if relevant == {"icon"} and (
                    reference.lstrip().lower().startswith("data:image/")
                    or reference.strip().lower() == "data:,"
                ):
                    return
                self.urls.append(reference)


def _encode_asset(url: str, document) -> dict:
    content_type = document.headers.get("content-type", "")
    if (document.status != ContentFetchStatus.OBSERVED
            or document.final_url != url or document.http_status is None
            or not 200 <= document.http_status < 300
            or not isinstance(document.body, bytes)
            or not content_type or "\r" in content_type or "\n" in content_type):
        raise ArchitectureAssetFailure("OCI_ASSET_UNAVAILABLE")
    # Preserve relevant browser response policy. Stripping CSP from the replay
    # could execute scripts forbidden on the real page and misclassify a site.
    safe_headers = {}
    for header in (
        "content-type", "content-security-policy", "x-content-type-options",
        "cross-origin-resource-policy", "cross-origin-opener-policy",
        "cross-origin-embedder-policy", "referrer-policy",
    ):
        value = document.headers.get(header, "")
        if value:
            if not isinstance(value, str) or len(value) > 8192 or any(
                ord(char) < 32 and char != "\t" for char in value
            ):
                raise ArchitectureAssetFailure("OCI_ASSET_POLICY_REJECTED")
            safe_headers[header] = value
    return {
        "url": url,
        "content_type": content_type,
        "response_headers": safe_headers,
        "status": document.http_status,
        "body_b64": base64.b64encode(document.body).decode("ascii"),
    }


def _bundle_resources(target: str, root, raw: str) -> list[dict]:
    root_record = _encode_asset(target, root)
    parser = _AssetReferences()
    parser.feed(raw)
    # Count unique fetchable resources, not HTML reference occurrences.
    # Shared bundles can be repeated dozens of times without increasing
    # network exposure. Inspect every reference before using the budget:
    # duplicates cannot hide an unsafe destination or malformed URL.
    candidates: list[str] = []
    seen = {target}
    for reference in parser.urls:
        try:
            candidate = normalize_url(urljoin(target, reference))
        except ValueError as exc:
            raise ArchitectureAssetFailure("OCI_ASSET_URL_REJECTED") from exc
        # Cross-origin assets are permitted only as bounded host-fetched public
        # resources. The networkless browser never fetches them itself.
        try:
            _validate_public_url(candidate, _default_resolver)
        except (ValueError, OSError) as exc:
            raise ArchitectureAssetFailure("OCI_CROSS_ORIGIN_ASSET_REJECTED") from exc
        if candidate in seen:
            continue
        seen.add(candidate)
        candidates.append(candidate)
        if len(candidates) > MAX_ASSETS:
            raise ArchitectureAssetFailure("OCI_ASSET_COUNT_LIMIT")
    fetcher = PublicWebFetcher(
        timeout_seconds=4.0, max_redirects=0, max_bytes=MAX_ASSET_BYTES,
        opener=PublicWebPinnedOpener(),
    )
    assets = [root_record]
    for candidate in candidates:
        # Revalidate immediately before each host-side request: reject a
        # destination whose DNS/public eligibility changed since inventory.
        try:
            _validate_public_url(candidate, _default_resolver)
        except (ValueError, OSError) as exc:
            raise ArchitectureAssetFailure("OCI_CROSS_ORIGIN_ASSET_REJECTED") from exc
        assets.append(_encode_asset(candidate, fetcher.fetch(candidate)))
    return assets


def sandbox_command(docker: str, digest: str) -> list[str]:
    """Immutable image identifier and fixed no-network flags, without volumes."""
    if not _DIGEST.fullmatch(digest):
        raise ValueError("OCI image identifier must be a verified local digest")
    return [
        docker, "run", "--rm", "--interactive", "--pull=never",
        "--network=none", "--read-only", "--cap-drop=ALL", "--log-driver=none",
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
    # A local image alone is not network attestation. Denied socket/DNS probes
    # must pass in the exact immutable image before any site DNS is attempted.
    try:
        from rasai.architecture_isolation_smoke import verify_isolation
        verify_isolation(digest=digest, docker=docker)
    except (RuntimeError, OSError, ValueError, subprocess.TimeoutExpired):
        return ProbeCaptures(url, url, device, None, None, "OCI_NETWORK_ISOLATION_NOT_ATTESTED")
    # Network isolation tests do not exercise Chromium. Prove the same
    # immutable image can render a synthetic local bundle with no network.
    try:
        from rasai.architecture_isolation_smoke import verify_browser_canary
        verify_browser_canary(digest=digest, docker=docker)
    except (RuntimeError, OSError, ValueError, subprocess.TimeoutExpired):
        return ProbeCaptures(url, url, device, None, None, "OCI_BROWSER_CANARY_FAILED")
    try:
        target = _validate_public_url(normalize_url(url), _default_resolver)
    except (ValueError, OSError):
        return ProbeCaptures(url, url, device, None, None, "PUBLIC_TARGET_REJECTED")
    fetcher = PublicWebFetcher(
        timeout_seconds=8.0, max_redirects=2, max_bytes=MAX_ROOT_BYTES,
        opener=PublicWebPinnedOpener(),
    )
    document = fetcher.fetch(target)
    reason = public_html_failure(document, target)
    if reason is not None:
        return ProbeCaptures(target, target, device, None, None, reason)
    final_target = document.final_url
    redirect_chain = tuple(getattr(document, "redirects", ()))
    raw = document.body.decode("utf-8", errors="replace")
    # A failed OCI stage cannot attribute redirected RAW to the initial URL.
    # public_html_failure already validated this public redirect chain.
    def partial_capture(reason: str) -> ProbeCaptures:
        return with_capture_origin(ProbeCaptures(
            target, final_target, device, raw, None, reason,
            redirect_chain=redirect_chain,
        ), transport="PINNED_HTTP_STATIC")
    # Distinguish unsafe/unavailable HTML resources from Chromium failures.
    # Preserve only bounded reason codes; never expose URLs, HTML or stderr.
    try:
        resources = _bundle_resources(final_target, document, raw)
    except ArchitectureAssetFailure as exc:
        return partial_capture(exc.reason)
    except (ValueError, OSError):
        return partial_capture("OCI_ASSET_BUNDLE_REJECTED")
    try:
        payload = json.dumps({
            "url": final_target, "device": device.value.lower(), "resources": resources,
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
            return partial_capture("OCI_WORKER_PROCESS_FAILED")
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
            return with_capture_origin(ProbeCaptures(
                target, final_target, device, raw, result["rendered_html"],
                redirect_chain=redirect_chain,
            ), transport="ISOLATED_OCI_RENDER")
        # Only server-owned, documented reason codes; never propagate browser
        # exception text, source HTML, headers, Docker stderr or arbitrary URLs.
        supported = {
            "ISOLATED_BROWSER_UNAVAILABLE", "ISOLATED_MANIFEST_INVALID",
            "ISOLATED_NAVIGATION_NOT_ATTESTED", "ISOLATED_RENDER_LIMIT",
            "ISOLATED_RESOURCES_BLOCKED",
            "ISOLATED_CONTENT_NOT_STABLE", "ISOLATED_CONTENT_NOT_ATTESTED",
        }
        reason = result["reason"]
        if finished.returncode == 2 and reason in supported and result["rendered_html"] is None:
            return partial_capture(reason)
        return partial_capture("ISOLATED_RENDER_INCONCLUSIVE")
    except subprocess.TimeoutExpired:
        return partial_capture("OCI_WORKER_TIMEOUT")
    except (ValueError, json.JSONDecodeError):
        return partial_capture("OCI_WORKER_OUTPUT_INVALID")
    except OSError:
        return partial_capture("OCI_WORKER_PROCESS_FAILED")
