"""Canonical on-demand prerequisite lifecycle.

Lightweight at import time: no Docker invocation, network access or filesystem
writes until a capability is explicitly requested. Consumers must not install
dependencies directly. The Docker daemon/image are managed by Docker Desktop,
not copied into RASAi's audit or source directories.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable
import shutil
import subprocess

ARCHITECTURE_BROWSER = "architecture.browser.oci"


@dataclass(frozen=True)
class PrerequisiteResult:
    ready: bool
    reason: str
    changed: bool = False


def prepare_prerequisite(
    capability: str, *,
    consent: Callable[[str], bool],
    source_root: Path | None = None,
) -> PrerequisiteResult:
    """Prepare one declared capability with explicit consent for host changes.

    Never installs Docker or elevates privileges: Docker Desktop installation
    requires the OS-native installer and a separate user decision. A safe,
    locally shipped Dockerfile may be built only with prior authorization.
    Runtime isolation still must be attested by the capture before site DNS.
    """
    if capability != ARCHITECTURE_BROWSER:
        return PrerequisiteResult(False, "UNSUPPORTED_PREREQUISITE")
    # Lazy import avoids loading Playwright or Docker dependencies at startup.
    from rasai.architecture_isolated_capture import inspect_local_image

    if inspect_local_image() is not None:
        return PrerequisiteResult(True, "PREREQUISITE_READY")
    docker = shutil.which("docker")
    if docker is None:
        return PrerequisiteResult(False, "DOCKER_INSTALL_REQUIRED")
    root = (source_root or Path(__file__).resolve().parents[2]).resolve()
    dockerfile = root / "Dockerfile.architecture-offline"
    if not dockerfile.is_file() or not (root / "pyproject.toml").is_file():
        return PrerequisiteResult(False, "OCI_BUILD_SOURCE_UNAVAILABLE")
    if not consent(
        "A descoberta dinamica precisa preparar uma imagem Docker isolada. "
        "A operacao pode baixar pacotes gratuitos e ocupar espaco em disco. "
        "Deseja autorizar a preparacao agora?"
    ):
        return PrerequisiteResult(False, "PREREQUISITE_DECLINED")
    # Dockerfile is a fixed repository-controlled path; user input never
    # interpolates into the command. No shell, no --privileged, no mounts.
    try:
        build = subprocess.run(
            [docker, "build", "--file", str(dockerfile),
             "--tag", "rasai-architecture-offline:local", str(root)],
            stdin=subprocess.DEVNULL,
            capture_output=True, text=True, timeout=900, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return PrerequisiteResult(False, "OCI_BUILD_FAILED")
    # Never expose build output: it could include local build or registry data.
    if build.returncode != 0 or inspect_local_image() is None:
        return PrerequisiteResult(False, "OCI_BUILD_FAILED")
    return PrerequisiteResult(True, "PREREQUISITE_READY", changed=True)
