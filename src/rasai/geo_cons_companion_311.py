"""#311: optional CONS-manifest-scoped GEO advisory companion, read-only.

Not injected into canonical CONS-3 report/manifest and never promoted to a
calibrated GEO trend. The CONS manifest is only an audit-ID inventory, not an
attestation of its own HTML or a substitute for each AUD's source checks.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
from typing import Any, Sequence

from rasai.geo_longitudinal_311 import build_geo_longitudinal_preview

_AUD = re.compile(r"^AUD-[A-Za-z0-9-]{1,100}$")
_CONS = re.compile(r"^CONS-[A-Za-z0-9-]{1,100}$")
_SHA = re.compile(r"^[a-fA-F0-9]{64}$")
_MAX_BYTES = 1024 * 1024


def build_cons_geo_advisory(cons_dir: Path, audits_root: Path) -> dict[str, Any]:
    """Reuse only explicit source AUD IDs of one CONS-3 manifest, never its db_path."""
    root = Path(audits_root)
    cons = Path(cons_dir)
    if (
        not root.is_dir() or root.is_symlink()
        or not cons.is_dir() or cons.is_symlink()
        or not _CONS.fullmatch(cons.name)
        or cons.resolve().parent != (root / "consolidated").resolve()
    ):
        raise ValueError("invalid CONS directory under audits_root/consolidated")
    manifest = cons / "manifest.json"
    html = cons / "report.html"
    if (
        not manifest.is_file() or manifest.is_symlink()
        or not html.is_file() or html.is_symlink()
        or manifest.stat().st_size > _MAX_BYTES
    ):
        raise ValueError("canonical CONS manifest/report missing or unsafe")
    try:
        stored = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        raise ValueError("cannot parse CONS manifest") from exc
    if not isinstance(stored, dict) or stored.get("cons_id") != cons.name:
        raise ValueError("CONS manifest identity mismatch")
    if stored.get("report_format_version") != "CONS-3":
        raise ValueError("unsupported CONS report format")
    if not _SHA.fullmatch(str(stored.get("request_fingerprint") or "")):
        raise ValueError("CONS fingerprint missing/invalid")
    source = stored.get("source_audits")
    if not isinstance(source, list) or not 2 <= len(source) <= 100:
        raise ValueError("CONS must explicitly list 2..100 source AUDs")
    paths = []
    seen = set()
    for record in source:
        if not isinstance(record, dict) or not _AUD.fullmatch(
            str(record.get("audit_id") or "")
        ):
            raise ValueError("invalid CONS source audit identity")
        name = record["audit_id"]
        if name in seen:
            raise ValueError("duplicate CONS source AUD")
        seen.add(name)
        # NEVER use path embedded in a manifest (can be user-editable,
        # absolute or outside audits_root). Derive an AUD-directory path.
        path = root / name
        if path.is_symlink() or path.resolve().parent != root.resolve():
            raise ValueError("untrusted AUD source path")
        paths.append(path)
    preview = build_geo_longitudinal_preview(paths)
    preview["cons_reference"] = {
        "cons_id": cons.name,
        "manifest_request_fingerprint": stored["request_fingerprint"],
        "scope": "SOURCE_AUD_IDENTITIES_ONLY",
        "manifest_cryptographically_attested": False,
        "native_cons_report_modified": False,
        "integration_status": "SEPARATE_READONLY_COMPANION_NOT_NATIVE_CONS",
    }
    return preview


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Read-only GEO advisory from one CONS-3 manifest; not a CONS report update."
    )
    parser.add_argument("--audits-root", type=Path, required=True)
    parser.add_argument("--cons-dir", type=Path, required=True)
    parser.add_argument("--format", choices=("json", "html"), default="json")
    args = parser.parse_args(argv)
    try:
        value = build_cons_geo_advisory(args.cons_dir, args.audits_root)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    if args.format == "html":
        from rasai.geo_longitudinal_html_311 import render_geo_longitudinal_html
        print(render_geo_longitudinal_html(value))
    else:
        print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
