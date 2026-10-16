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
    if (not isinstance(evidence, dict) or len(evidence) != 7
            or not all(value is True for value in evidence.values())):
        raise RuntimeError("Container network isolation was not proved")
    return evidence


def main() -> int:
    try:
        result = verify_isolation()
    except (RuntimeError, OSError, ValueError, subprocess.TimeoutExpired):
        print("OCI_NETWORK_ISOLATION_NOT_ATTESTED")
        return 2
    print("OCI_NETWORK_ISOLATION_BLOCKED: " + json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
