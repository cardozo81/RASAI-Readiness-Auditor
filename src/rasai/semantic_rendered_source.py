"""Narrow, evidence-verified rendered-semantic fallback for an HTTP-403 RAW path.

This does NOT turn BR-GEO-006/009/020 into PASS. It only permits M7 advisory
semantic analysis of the *same* physically material browser DOM after a
blocked standalone HTTP acquisition, with explicit hash and AUD identity.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


def verified_rendered_semantic_source(
    *, persistence: Any, workspace: Any, audit_id: str,
    page_id: str, snapshot_id: str,
) -> bool:
    if not all(isinstance(x, str) and x for x in (audit_id, page_id, snapshot_id)):
        return False
    try:
        page = persistence.pages.get(page_id)
        snapshot = persistence.snapshots.get(snapshot_id)
    except (AttributeError, KeyError, ValueError):
        return False
    if (
        page is None or snapshot is None
        or str(getattr(page, "audit_id", "")) != audit_id
        or str(getattr(snapshot, "page_id", "")) != page_id
        or str(getattr(snapshot, "snapshot_id", "")) != snapshot_id
        or int(getattr(snapshot, "http_status", 0) or 0) != 200
    ):
        return False
    metadata = getattr(snapshot, "browser_metadata", None)
    if isinstance(metadata, str):
        try:
            metadata = json.loads(metadata)
        except (TypeError, ValueError):
            return False
    if not isinstance(metadata, Mapping):
        return False
    raw = metadata.get("raw_http")
    quality = metadata.get("capture_quality")
    binding = metadata.get("architecture_artifact_binding")
    if (
        not isinstance(raw, Mapping) or raw.get("status") != 403
        or not isinstance(quality, Mapping)
        or quality.get("state") not in {"READY", "RECOVERED"}
        or not isinstance(quality.get("final"), Mapping)
        or int(quality["final"].get("main_text_length", 0) or 0) < 160
        or not isinstance(binding, Mapping)
        or binding.get("version") != "m3-artifact-binding-v1"
    ):
        return False
    expected = binding.get("rendered_sha256")
    if not isinstance(expected, str) or len(expected) != 64:
        return False

    def bounded_artifact(reference: Any, *, max_bytes: int) -> bytes | None:
        if not isinstance(reference, str):
            return None
        rel = Path(reference)
        if rel.is_absolute() or ".." in rel.parts or not reference.startswith("artifacts/"):
            return None
        root = Path(workspace.root)
        path = root / rel
        try:
            if path.is_symlink() or not path.is_file():
                return None
            size = path.stat().st_size
            if not 0 < size <= max_bytes:
                return None
            return path.read_bytes()
        except OSError:
            return None

    html = bounded_artifact(
        getattr(snapshot, "rendered_artifact_ref", None), max_bytes=8_000_000,
    )
    if html is None or hashlib.sha256(html).hexdigest() != expected:
        return False
    main = bounded_artifact(
        getattr(snapshot, "main_content_ref", None), max_bytes=1_000_000,
    )
    if main is None or len(main.decode("utf-8", errors="replace").strip()) < 160:
        return False
    from rasai.render_materiality import _strong_primary_content, observe_materiality
    return _strong_primary_content(observe_materiality(html.decode("utf-8", errors="replace")))
