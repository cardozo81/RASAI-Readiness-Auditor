"""#210: versioned, isolated same-domain comparison package, not CONS-3.

No side effect on source AUDs, the analytical index or the production
same-URL CONS path. Requires an explicitly opt-in physical source metadata
reconciliation before making a standalone report artifact.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
from typing import Any, Sequence

from rasai.consolidation.domain_comparative_html_210 import (
    render_same_domain_advisory_html,
)
from rasai.consolidation.domain_comparative_index_210 import (
    domain_preview_from_index,
)
from rasai.consolidation.reader import source_file_fingerprint

_VERSION = "CONS-DOMAIN-COMPARATIVE-1"


def _encode(obj: Any) -> bytes:
    return (
        json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2,
                   allow_nan=False) + "\n"
    ).encode("utf-8")


def materialize_same_domain_package(
    audits_root: Path, audit_ids: Sequence[str],
) -> dict[str, Any]:
    """Opt-in standalone CDOM package; never mutate existing CONS-3 output."""
    root = Path(audits_root)
    # The source preview rejects unsafe roots, missing index and linked AUDs.
    preview = domain_preview_from_index(
        root, audit_ids, verify_source_metadata=True,
    )
    if preview.get("eligible") is not True:
        raise ValueError(
            "source AUDs are not comparable by exact hostname/device: "
            + str(preview.get("reason") or "UNVERIFIED")
        )
    source_ids = [str(item["audit_id"]) for item in preview["audits"]]
    fingerprints = {}
    for audit_id in source_ids:
        parent = root / audit_id
        source = parent / "audit.db"
        if (
            parent.is_symlink() or source.is_symlink() or not source.is_file()
            or parent.resolve().parent != root.resolve()
        ):
            raise ValueError("physical source became unsafe before package materialization")
        fingerprints[audit_id] = source_file_fingerprint(source)
    inputs = {
        "contract_version": _VERSION,
        "comparison_mode": "SAME_DOMAIN_COMPARATIVE",
        "source_audit_ids": source_ids,
        "source_file_metadata_fingerprints": fingerprints,
        "source_package_freshness_verified": False,
        "advisory": preview,
    }
    request_fingerprint = sha256(_encode(inputs)).hexdigest()
    package_id = "CDOM-" + request_fingerprint[:32].upper()
    manifest = {
        **inputs,
        "package_id": package_id,
        "request_fingerprint": request_fingerprint,
        "native_cons3_created": False,
        "longitudinal_series_created": False,
        "page_score_or_apdex_deltas_eligible": False,
        "provider_requests": 0,
        "audit_writes": 0,
        "limitations": (
            "Pacote local de comparação consultiva de URLs distintas. "
            "Não é CONS-3, nem série da mesma URL, nem autenticação "
            "criptográfica dos bytes das AUDs: fingerprints de origem "
            "usam path, tamanho e mtime. Score, Apdex e CWV entre "
            "universos não são comparáveis."
        ),
    }
    report_bytes = render_same_domain_advisory_html(preview).encode("utf-8")
    manifest_bytes = _encode(manifest)
    destination_root = root / "consolidated-domain"
    dest = destination_root / package_id
    if destination_root.is_symlink() or (
        destination_root.exists() and not destination_root.is_dir()
    ):
        raise ValueError("unsafe comparison package destination")
    if dest.is_symlink():
        raise ValueError("existing comparison package is a symlink")
    if dest.exists():
        if (
            not dest.is_dir() or (dest / "manifest.json").is_symlink()
            or (dest / "report.html").is_symlink()
            or (dest / "manifest.json").read_bytes() != manifest_bytes
            or (dest / "report.html").read_bytes() != report_bytes
        ):
            raise ValueError("existing versioned package differs; will not overwrite")
        return {
            "package_id": package_id,
            "manifest_path": str(dest / "manifest.json"),
            "html_path": str(dest / "report.html"),
            "status": "IDEMPOTENT_EXISTING",
            "audit_writes": 0,
            "provider_requests": 0,
        }

    destination_root.mkdir(exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=".cdomain-staging-", dir=destination_root))
    try:
        (temporary / "manifest.json").write_bytes(manifest_bytes)
        (temporary / "report.html").write_bytes(report_bytes)
        if dest.exists() or dest.is_symlink():
            raise ValueError("comparison package destination unexpectedly exists")
        os.rename(temporary, dest)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
    return {
        "package_id": package_id,
        "manifest_path": str(dest / "manifest.json"),
        "html_path": str(dest / "report.html"),
        "status": "MATERIALIZED",
        "audit_writes": 0,
        "provider_requests": 0,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Opt-in separate same-host domain comparison package, never CONS-3."
    )
    parser.add_argument("--audits-root", type=Path, required=True)
    parser.add_argument("--audit-id", action="append", required=True)
    parser.add_argument("--write-domain-package", action="store_true")
    args = parser.parse_args(argv)
    if not args.write_domain_package:
        parser.error("explicit --write-domain-package required")
    try:
        outcome = materialize_same_domain_package(
            args.audits_root, args.audit_id,
        )
    except (ValueError, OSError, sqlite3.DatabaseError) as exc:
        parser.error(str(exc))
    print(json.dumps(outcome, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
