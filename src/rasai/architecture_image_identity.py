"""Source identity for the optional networkless architecture OCI worker.

Only source files that determine the isolated worker runtime are fingerprinted.
The local image tag is not proof of freshness: the trusted Docker daemon must
report the matching source SHA-256 label on its immutable image ID.
"""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path

IMAGE_SOURCE_LABEL = "org.rasai.architecture.source-sha256"
WORKER_INPUTS = (
    "Dockerfile.architecture-offline",
    "pyproject.toml",
    "src/rasai/architecture_image_identity.py",
    "src/rasai/architecture_offline_worker.py",
    "src/rasai/architecture_resource_budget.py",
    "src/rasai/architecture_dom_settle.py",
    "src/rasai/rendering.py",
    "src/rasai/domain.py",
    "src/rasai/url_utils.py",
)


def expected_source_sha256(root: Path | None = None) -> str:
    """Hash the reviewed worker source and its direct local runtime dependencies.

    No Docker, DNS, network or subprocess. Refuse missing/symlinked inputs rather
    than silently accepting an unverifiable image. Length framing avoids
    concatenation ambiguity across input files.
    """
    project = (root or Path(__file__).resolve().parents[2]).resolve()
    digest = sha256()
    for relative in WORKER_INPUTS:
        path = project / relative
        if path.is_symlink() or not path.is_file():
            raise ValueError("OCI_WORKER_SOURCE_UNAVAILABLE")
        try:
            data = path.read_bytes()
        except OSError as exc:
            raise ValueError("OCI_WORKER_SOURCE_UNAVAILABLE") from exc
        digest.update(relative.encode("ascii"))
        digest.update(b"\x00")
        digest.update(len(data).to_bytes(8, "big"))
        digest.update(data)
    return digest.hexdigest()
