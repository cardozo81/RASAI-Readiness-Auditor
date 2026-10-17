"""Physical negative test: an OCI architecture worker must have zero egress.

Run only against an explicitly built local image. No external request is made
by the Python host; all socket attempts execute within docker --network none.
A successful connection or DNS lookup is a hard test failure.
"""
from __future__ import annotations

import json
import shutil
import subprocess

from rasai.architecture_isolated_capture import inspect_local_image, sandbox_command

# This script is executed entirely within the restricted container.
_CONTAINER_PROBE = r"""
import json
import socket

targets = (
    ("public_ipv4", "1.1.1.1", 443),
    ("private_ipv4", "10.0.0.1", 80),
    ("link_local_metadata", "169.254.169.254", 80),
    ("loopback", "127.0.0.1", 80),
    ("private_ipv6", "fd00::1", 443),
    ("loopback_ipv6", "::1", 80),
)
blocked = {}
for label, host, port in targets:
    try:
        sock = socket.create_connection((host, port), timeout=0.5)
    except OSError:
        blocked[label] = True
    else:
        sock.close()
        blocked[label] = False
# WebRTC and native browser traffic may use UDP, which a TCP-only test
# does not exercise. A networkless namespace has no route for any of these.
for label, host, family in (
    ("udp_public_ipv4", "1.1.1.1", socket.AF_INET),
    ("udp_private_ipv4", "10.0.0.1", socket.AF_INET),
    ("udp_metadata_ipv4", "169.254.169.254", socket.AF_INET),
    ("udp_private_ipv6", "fd00::1", socket.AF_INET6),
):
    with socket.socket(family, socket.SOCK_DGRAM) as datagram:
        datagram.settimeout(0.5)
        try:
            datagram.sendto(b"RASAI-NETWORKLESS-TEST", (host, 443))
        except OSError:
            blocked[label] = True
        else:
            blocked[label] = False
try:
    addresses = socket.getaddrinfo("www.example.org", 443)
except OSError:
    blocked["external_dns"] = True
else:
    blocked["external_dns"] = False
print(json.dumps(blocked, sort_keys=True))
"""


def verify_isolation(*, digest: str | None = None, docker: str | None = None) -> dict[str, bool]:
    digest = digest if digest is not None else inspect_local_image()
    docker = docker if docker is not None else shutil.which("docker")
    if digest is None or docker is None:
        raise RuntimeError("Local OCI image/daemon not verified")
    command = sandbox_command(docker, digest)
    command.insert(-1, "--entrypoint=python")
    command.extend(["-c", _CONTAINER_PROBE])
    completed = subprocess.run(
        command, input="", capture_output=True, text=True,
        timeout=15, check=False,
    )
    if completed.returncode != 0 or len(completed.stdout) > 4096:
        raise RuntimeError("Isolated network test did not complete")
    evidence = json.loads(completed.stdout)
    if (not isinstance(evidence, dict) or len(evidence) != 11
            or not all(value is True for value in evidence.values())):
        raise RuntimeError("Container network isolation was not proved")
    return evidence



def verify_browser_canary(*, digest: str, docker: str) -> None:
    """Run a deterministic offline Chromium smoke before contacting a real site.

    Uses the exact immutable image/CLI restrictions as the actual render,
    but only a synthetic HTML document. stdout is a small, validated status;
    stderr is never shown, logged or returned to the operator.
    """
    import base64
    from rasai.architecture_isolated_capture import sandbox_command

    html = b"<html><body><main>rasai-offline-canary</main></body></html>"
    manifest = json.dumps({
        "url": "https://example.org/",
        "device": "mobile",
        "resources": [{
            "url": "https://example.org/",
            "status": 200,
            "content_type": "text/html",
            "response_headers": {"content-type": "text/html"},
            "body_b64": base64.b64encode(html).decode("ascii"),
        }],
    }, separators=(",", ":"))
    completed = subprocess.run(
        sandbox_command(docker, digest), input=manifest, capture_output=True,
        text=True, timeout=25, check=False,
    )
    if completed.returncode != 0 or len(completed.stdout) > 100_000:
        # Only a finite, worker-owned diagnostic vocabulary may be printed,
        # because Docker stderr and source/user data are untrusted.
        if completed.returncode == 2 and len(completed.stdout) <= 4096:
            try:
                reason = json.loads(completed.stdout).get("reason")
            except (ValueError, AttributeError, TypeError):
                reason = None
            if reason in {
                "ISOLATED_BROWSER_UNAVAILABLE", "ISOLATED_MANIFEST_INVALID",
                "ISOLATED_NAVIGATION_NOT_ATTESTED", "ISOLATED_RENDER_LIMIT",
                "ISOLATED_RESOURCES_BLOCKED",
            }:
                raise RuntimeError("CANARY_" + reason)
        raise RuntimeError("CANARY_EXECUTION_FAILED")
    result = json.loads(completed.stdout)
    if (not isinstance(result, dict)
            or set(result) != {"rendered_html", "reason"}
            or result["reason"] is not None
            or not isinstance(result["rendered_html"], str)
            or "rasai-offline-canary" not in result["rendered_html"]):
        raise RuntimeError("Browser canary did not render synthetic HTML")


def main() -> int:
    import sys
    if sys.argv[1:] not in ([], ["--browser"]):
        print("OCI_SMOKE_OPTION_INVALID")
        return 2
    try:
        result = verify_isolation()
    except (RuntimeError, OSError, ValueError, subprocess.TimeoutExpired):
        print("OCI_NETWORK_ISOLATION_NOT_ATTESTED")
        return 2
    print("OCI_NETWORK_ISOLATION_BLOCKED: " + json.dumps(result, sort_keys=True))
    if sys.argv[1:] == ["--browser"]:
        digest, docker = inspect_local_image(), shutil.which("docker")
        if digest is None or docker is None:
            print("OCI_BROWSER_CANARY_FAILED")
            return 2
        try:
            verify_browser_canary(digest=digest, docker=docker)
        except RuntimeError as exc:
            if str(exc).startswith("CANARY_"):
                print("OCI_BROWSER_CANARY_FAILED: " + str(exc))
            else:
                print("OCI_BROWSER_CANARY_FAILED")
            return 2
        except (OSError, ValueError, subprocess.TimeoutExpired):
            print("OCI_BROWSER_CANARY_FAILED")
            return 2
        print("OCI_BROWSER_CANARY_PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
