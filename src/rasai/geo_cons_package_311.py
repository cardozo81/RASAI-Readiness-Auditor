"""#311: persist a versioned GEO advisory *outside* canonical CONS-3.

Never mutates CONS report/manifest, indexes, AUDs or GEO snapshots.
Missing snapshots are explicit N/D exclusions, not invented trends.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any, Sequence

from rasai.geo_cons_companion_311 import build_cons_geo_advisory
from rasai.geo_longitudinal_html_311 import render_geo_longitudinal_html

_MAX_SOURCE_BYTES = 256 * 1024 * 1024


def _file_digest(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        raise ValueError("source file unavailable or linked")
    if path.stat().st_size > _MAX_SOURCE_BYTES:
        raise ValueError("source file exceeds verification limit")
    digest = sha256()
    consumed = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            consumed += len(chunk)
            if consumed > _MAX_SOURCE_BYTES:
                raise ValueError("source grew beyond verification byte limit")
            digest.update(chunk)
    # A source may grow or truncate after the preliminary stat. Hashing
    # different physical bytes must never attest a stable CONS/AUD input.
    if consumed != path.stat().st_size:
        raise ValueError("source size changed during verification")
    return digest.hexdigest()


def _bytes(payload: Any) -> bytes:
    return (
        json.dumps(payload, sort_keys=True, ensure_ascii=False,
                   indent=2, allow_nan=False) + "\n"
    ).encode("utf-8")


def materialize_cons_geo_companion(
    cons_dir: Path, audits_root: Path,
) -> dict[str, Any]:
    """Persist only independently versioned observational GEO files."""
    root = Path(audits_root)
    cons = Path(cons_dir)
    preview = build_cons_geo_advisory(cons, root)
    if (preview.get("provider_requests") != 0
            or preview.get("audit_writes") != 0
            or preview.get("cons_reference", {}).get("native_cons_report_modified") is not False):
        raise ValueError("non-readonly GEO companion projection rejected")
    if any(
        item.get("trend_conclusion") != "N/D"
        or item.get("trend_rate") is not None
        for item in preview.get("timelines", ())
    ):
        raise ValueError("unverified GEO trends are not packageable")
    canonical = cons / "manifest.json"
    report = cons / "report.html"
    source_manifest_digest = _file_digest(canonical)
    source_report_digest = _file_digest(report)
    doc = json.loads(canonical.read_text(encoding="utf-8"))
    source_ids = [item["audit_id"] for item in doc["source_audits"]]
    file_hashes: dict[str, str | None] = {}
    for audit_id in source_ids:
        parent = root / audit_id
        db = parent / "audit.db"
        if parent.is_symlink() or db.is_symlink():
            raise ValueError("GEO companion source AUD is linked")
        if db.is_file():
            if any(Path(str(db) + suffix).exists()
                   for suffix in ("-wal", "-shm", "-journal")):
                raise ValueError("GEO companion source AUD has SQLite sidecars")
            file_hashes[audit_id] = _file_digest(db)
        else:
            file_hashes[audit_id] = None

    manifest = {
        "contract_version": "RASAI-CONS-GEO-COMPANION-PACKAGE-311-001",
        "source_cons_id": cons.name,
        "source_cons_request_fingerprint": doc["request_fingerprint"],
        "source_cons_manifest_sha256": source_manifest_digest,
        "source_cons_report_sha256": source_report_digest,
        "source_aud_db_sha256": file_hashes,
        "cons_reference_cryptographically_attested": False,
        "native_cons_modified": False,
        "geo_trends_calibrated": False,
        "provider_requests": 0,
        "audit_writes": 0,
        "advisory": preview,
        "limitations": (
            "GEO-only advisory from persisted AUD provenance and CONS source "
            "IDs. Hashes describe bytes read locally, not signatures proving "
            "authenticity of third-party data or comparable longitudinal "
            "exposure. No GEO metric is injected into CONS-3."
        ),
    }
    payload = _bytes(manifest)
    html = render_geo_longitudinal_html(preview).encode("utf-8")
    fingerprint = sha256(payload + sha256(html).digest()).hexdigest()
    package_id = "GCOMP-" + fingerprint[:32].upper()
    destination_root = root / "consolidated-geo-companions"
    if (destination_root.is_symlink()
            or (destination_root.exists() and not destination_root.is_dir())):
        raise ValueError("unsafe GEO companion output destination")
    destination = destination_root / package_id
    if destination.is_symlink():
        raise ValueError("GEO companion output is a link")

    def existing() -> dict[str, Any]:
        if (not destination.is_dir()
                or (destination / "manifest.json").is_symlink()
                or (destination / "report.html").is_symlink()
                or (destination / "manifest.json").read_bytes() != payload
                or (destination / "report.html").read_bytes() != html):
            raise ValueError("existing GEO companion package differs")
        return {
            "status": "IDEMPOTENT_EXISTING",
            "package_id": package_id,
            "manifest_path": str(destination / "manifest.json"),
            "report_path": str(destination / "report.html"),
            "audit_writes": 0, "cons_writes": 0, "provider_requests": 0,
        }

    def reverify_sources() -> None:
        """Protect both fresh publish and idempotent returns from input races."""
        if (_file_digest(canonical) != source_manifest_digest
                or _file_digest(report) != source_report_digest):
            raise ValueError("CONS source changed during GEO companion packaging")
        for audit_id, saved_hash in file_hashes.items():
            parent = root / audit_id
            db = parent / "audit.db"
            if parent.is_symlink() or db.is_symlink():
                raise ValueError("GEO companion source AUD became a link")
            if saved_hash is not None:
                if any(Path(str(db) + suffix).exists()
                       for suffix in ("-wal", "-shm", "-journal")):
                    raise ValueError("GEO companion source AUD gained SQLite sidecars")
                if _file_digest(db) != saved_hash:
                    raise ValueError("source AUD changed during GEO companion packaging")
            elif db.exists():
                raise ValueError("missing source AUD appeared during packaging")

    # First preview may have read mutable AUDs before the first SHA-256 pass.
    # A second independent read must produce the same projection; otherwise
    # the package would claim that the SHA-256 values attest stale findings.
    reverify_sources()
    if build_cons_geo_advisory(cons, root) != preview:
        raise ValueError("GEO companion projection changed during packaging")
    # Ensure the second preview did not see a source moving underneath it.
    reverify_sources()
    if destination.exists():
        return existing()

    destination_root.mkdir(exist_ok=True)
    if destination_root.is_symlink():
        raise ValueError("GEO companion output root became a link")
    staging = Path(tempfile.mkdtemp(prefix=".gcomp-staging-", dir=destination_root))
    try:
        (staging / "manifest.json").write_bytes(payload)
        (staging / "report.html").write_bytes(html)
        if destination.exists() or destination.is_symlink():
            raise ValueError("GEO companion package destination appeared")
        # A CONS/AUD file or SQLite journal can change after the preview
        # comparison and before writing the staging files. Recheck the
        # complete physical source seal immediately before publication.
        reverify_sources()
        os.rename(staging, destination)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return {
        "status": "MATERIALIZED",
        "package_id": package_id,
        "manifest_path": str(destination / "manifest.json"),
        "report_path": str(destination / "report.html"),
        "audit_writes": 0, "cons_writes": 0, "provider_requests": 0,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Persist separate versioned GEO CONS advisory; never alter CONS-3."
    )
    parser.add_argument("--cons-dir", type=Path, required=True)
    parser.add_argument("--audits-root", type=Path, required=True)
    parser.add_argument("--write-geo-companion", action="store_true")
    args = parser.parse_args(argv)
    if not args.write_geo_companion:
        parser.error("explicit --write-geo-companion required")
    try:
        outcome = materialize_cons_geo_companion(args.cons_dir, args.audits_root)
    except (ValueError, OSError, TypeError, KeyError) as exc:
        parser.error(str(exc))
    print(json.dumps(outcome, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
