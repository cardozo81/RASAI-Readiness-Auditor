"""Networkless physical OCI matrix for the canonical architecture classifier.

Run with python -m tests.architecture_offline_classification_matrix.
No external URL is fetched. Synthetic HTML and scripts are piped to a
container whose network isolation is attested immediately before use.
Only classification enums are printed; DOM bodies remain in process memory.
"""
from __future__ import annotations

import base64
import json
import shutil
import subprocess

from rasai.architecture_discovery import assess_architecture
from rasai.architecture_isolated_capture import inspect_local_image, sandbox_command
from rasai.architecture_isolation_smoke import verify_browser_canary, verify_isolation

TARGET = "https://example.org/"
SCRIPT = TARGET + "app.js"
STATIC = "<html><body><main>Visible static material presented from the server.</main></body></html>"

CASES = (
    ("STATIC_OR_SSR", STATIC, None),
    (
        "CSR_SPA",
        '<html><body><main id="app"></main><script src="/app.js"></script></body></html>',
        "document.querySelector('main').textContent = "
        "'Client-side material added to the previously empty page.';",
    ),
    (
        "HYDRATED",
        '<html><body><main>Visible server-delivered content.</main>'
        '<script src="/app.js"></script></body></html>',
        "document.querySelector('main').textContent += "
        "' Additional content inserted by client JavaScript.';",
    ),
    (
        "MIXED",
        '<html><body><main>Original server-delivered product summary.</main>'
        '<script src="/app.js"></script></body></html>',
        "document.querySelector('main').textContent = "
        "'Completely different client-generated navigation content.';",
    ),
)


def _resource(url: str, data: str, content_type: str) -> dict[str, object]:
    return {
        "url": url,
        "body_b64": base64.b64encode(data.encode("utf-8")).decode("ascii"),
        "content_type": content_type,
        "response_headers": {"content-type": content_type},
        "status": 200,
    }


def test_matrix_case(
    *,
    docker: str,
    digest: str,
    device: str,
    expected: str,
    raw_html: str,
    script: str | None,
) -> None:
    resources = [_resource(TARGET, raw_html, "text/html")]
    if script is not None:
        resources.append(_resource(SCRIPT, script, "application/javascript"))
    payload = json.dumps(
        {"url": TARGET, "device": device, "resources": resources},
        separators=(",", ":"),
    )
    finished = subprocess.run(
        sandbox_command(docker, digest),
        input=payload,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if finished.returncode != 0 or len(finished.stdout) > 1_500_000:
        raise RuntimeError("OCI_MATRIX_RENDER_FAILED")
    try:
        result = json.loads(finished.stdout)
        if not isinstance(result, dict) or result.get("reason") is not None:
            raise ValueError
        html = result.get("rendered_html")
        if not isinstance(html, str):
            raise ValueError
        measured = assess_architecture(raw_html=raw_html, rendered_html=html)
    except (ValueError, TypeError) as exc:
        raise RuntimeError("OCI_MATRIX_RESULT_INVALID") from exc
    if measured.limitation is not None or measured.architecture.value != expected:
        raise RuntimeError("OCI_MATRIX_CLASSIFICATION_MISMATCH")


def run_matrix(*, docker: str, digest: str) -> None:
    for device in ("mobile", "desktop"):
        for label, raw, script in CASES:
            test_matrix_case(
                docker=docker, digest=digest, device=device,
                expected=label, raw_html=raw, script=script,
            )
            print("OCI_MATRIX_PASS:", device, label, flush=True)


def main() -> int:
    digest = inspect_local_image()
    docker = shutil.which("docker")
    if digest is None or docker is None:
        raise SystemExit("OCI_MATRIX_LOCAL_IMAGE_REQUIRED")
    evidence = verify_isolation(digest=digest, docker=docker)
    if len(evidence) != 11 or not all(evidence.values()):
        raise SystemExit("OCI_MATRIX_NETWORK_NOT_ATTESTED")
    verify_browser_canary(digest=digest, docker=docker)
    run_matrix(docker=docker, digest=digest)
    print("OCI_MATRIX_ALL_8_PASSED", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
