"""Read-only #603 Windows evidence preflight and signed review acceptance.

Never signs for a reviewer, creates documents, contacts providers, copies
private evidence into Git, or rewrites a sealed AUD. Printed output is redacted.
"""
from __future__ import annotations

import argparse
from collections import deque
from contextlib import closing
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
from typing import Any, Sequence

AUD_ID = "AUD-EAFBFF6E3F6E415CB0DD41F561B5B2DF"
_SKIPPED = frozenset({".git", ".venv", "venv", "node_modules", "__pycache__", ".pytest_cache"})
_MAX_DIRECTORIES = 2000
_MAX_DEPTH = 7


def _candidates(root: Path, audit_id: str) -> list[Path]:
    """Bounded local search; never follow symlinks, network or arbitrary files."""
    if not root.is_dir() or root.is_symlink():
        return []
    queue = deque([(root, 0)])
    matches: list[Path] = []
    visited = 0
    while queue and visited < _MAX_DIRECTORIES:
        current, depth = queue.popleft()
        visited += 1
        if current.name == audit_id and (current / "audit.db").is_file():
            matches.append(current)
            continue
        if depth >= _MAX_DEPTH:
            continue
        try:
            with os.scandir(current) as entries:
                for item in entries:
                    if item.name in _SKIPPED or item.name.startswith("."):
                        continue
                    if item.is_dir(follow_symlinks=False) and not item.is_symlink():
                        queue.append((Path(item.path), depth + 1))
        except (OSError, PermissionError):
            continue
    return matches[:20]


def _utc_day(value: Any) -> str | None:
    if not isinstance(value, str) or not value or value != value.strip():
        return None
    try:
        instant = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if instant.tzinfo is None or instant.utcoffset() is None:
            return None
        return instant.astimezone(timezone.utc).date().isoformat()
    except (TypeError, ValueError, OverflowError):
        return None


def _inspect_aud(folder: Path, audit_id: str) -> dict[str, Any]:
    result: dict[str, Any] = {
        "aud_status": "NOT_VERIFIABLE",
        "snapshots": 0,
        "snapshots_with_utc_date": 0,
        "capture_utc_days": [],
    }
    db = folder / "audit.db"
    if (
        folder.name != audit_id or folder.is_symlink() or not folder.is_dir()
        or db.is_symlink() or not db.is_file()
        or any(Path(str(db) + suffix).exists() for suffix in ("-wal", "-shm", "-journal"))
    ):
        return result
    try:
        with closing(sqlite3.connect(
            db.resolve().as_uri() + "?mode=ro&immutable=1", uri=True, timeout=2,
        )) as connection:
            connection.execute("PRAGMA query_only=ON")
            status = connection.execute(
                "SELECT status,completion_status FROM audits WHERE audit_id=? LIMIT 2",
                (audit_id,),
            ).fetchall()
            if (len(status) != 1 or str(status[0][0]).upper() != "COMPLETED"
                    or str(status[0][1]).upper() != "COMPLETE"):
                return result
            columns = {r[1] for r in connection.execute("PRAGMA table_info(page_snapshots)")}
            if not {"snapshot_id", "page_id", "main_content_ref", "captured_at"} <= columns:
                return result
            rows = connection.execute(
                "SELECT s.captured_at FROM page_snapshots AS s "
                "JOIN pages AS p ON p.page_id=s.page_id "
                "WHERE p.audit_id=? LIMIT 1001", (audit_id,),
            ).fetchall()
            if not 0 < len(rows) <= 1000:
                return result
            days = [_utc_day(row[0]) for row in rows]
            return {
                "aud_status": "SEALED_AUD_METADATA_READY",
                "snapshots": len(rows),
                "snapshots_with_utc_date": sum(day is not None for day in days),
                "capture_utc_days": sorted({d for d in days if d is not None})[:16],
            }
    except (sqlite3.Error, OSError, ValueError, TypeError):
        return result


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    obj: dict[str, Any] = {}
    for key, val in pairs:
        if key in obj:
            raise ValueError("duplicate JSON key")
        obj[key] = val
    return obj


def _packet(path: Path, expected_audit: str) -> dict[str, Any]:
    fallback = {"packet_status": "PRIVATE_PACKET_NOT_READY", "packet_claims": 0}
    try:
        if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= 32768:
            return fallback
        obj = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_pairs)
        if (not isinstance(obj, dict)
                or set(obj) != {"audit_id", "at_date", "claims"}
                or obj["audit_id"] != expected_audit
                or not isinstance(obj["at_date"], str)
                or not isinstance(obj["claims"], list)
                or not 0 < len(obj["claims"]) <= 50):
            return fallback
        root = path.parent.resolve()
        for row in obj["claims"]:
            if (not isinstance(row, dict)
                    or not {"claim_id", "snapshot_id", "product_scope",
                            "claim_file", "document_file", "receipt_file"} <= row.keys()):
                return fallback
            for field in ("claim_file", "document_file", "receipt_file"):
                name = row[field]
                if not isinstance(name, str) or not name or len(name) > 240:
                    return fallback
                rel = Path(name)
                if (rel.is_absolute() or "." in rel.parts or ".." in rel.parts
                        or ":" in name or "\\" in name or "\x00" in name):
                    return fallback
                candidate = root
                for part in rel.parts:
                    candidate = candidate / part
                    if candidate.is_symlink():
                        return fallback
                if (not candidate.is_file() or not candidate.resolve().is_relative_to(root)
                        or candidate.stat().st_size == 0):
                    return fallback
        return {
            "packet_status": "PRIVATE_FILES_PRESENT_NOT_YET_AUTHENTICATED",
            "packet_claims": len(obj["claims"]),
            "manifest_utc_date": obj["at_date"],
        }
    except (OSError, ValueError, TypeError, UnicodeError):
        return fallback


def inspect(
    *, audit_directory: Path | None, search_root: Path | None,
    manifest: Path | None, audit_id: str = AUD_ID,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    public: dict[str, Any] = {
        "contract": "RASAI-603-LOCAL-EVIDENCE-READINESS-001",
        "status": "AUD_DIRECTORY_REQUIRED",
        "audit_id": audit_id,
        "provider_requests": 0,
        "audit_writes": 0,
        "official_source_authenticated_by_this_tool": False,
        "legal_compliance_certified": False,
    }
    if audit_directory is None and search_root is not None:
        found = _candidates(search_root, audit_id)
        if len(found) > 1:
            return {**public, "status": "MULTIPLE_AUD_CANDIDATES",
                    "candidate_count": len(found)}
        if len(found) == 1:
            audit_directory = found[0]
    if audit_directory is None:
        return public
    metadata = _inspect_aud(audit_directory, audit_id)
    public.update(metadata)
    if metadata["aud_status"] != "SEALED_AUD_METADATA_READY":
        return {**public, "status": "AUD_SOURCE_NOT_VERIFIABLE"}
    if manifest is None:
        return {**public, "status": "PRIVATE_SIGNED_PACKET_REQUIRED"}
    packet = _packet(manifest, audit_id)
    public.update(packet)
    if packet["packet_status"] != "PRIVATE_FILES_PRESENT_NOT_YET_AUTHENTICATED":
        return {**public, "status": "PRIVATE_PACKET_NOT_READY"}

    trusted_env = os.environ if env is None else env
    raw_key = trusted_env.get("RASAI_CLAIM_REVIEW_HMAC_KEY_HEX", "")
    try:
        key = bytes.fromhex(raw_key) if 64 <= len(raw_key) <= 256 else b""
    except ValueError:
        key = b""
    reviewers = frozenset(
        x.strip() for x in trusted_env.get("RASAI_CLAIM_REVIEWER_ALLOWLIST", "").split(",")
        if x.strip()
    )
    if len(key) < 32 or not reviewers:
        return {**public, "status": "PRIVATE_REVIEW_CREDENTIALS_REQUIRED"}

    # The already tested #603 gate checks MAC, reviewer allowlist, literal
    # snapshot binding, UTC capture applicability, collection date and
    # physical integrity. Never copy receipt contents to this report.
    from rasai.claim_review_physical_gate import inspect_physical_claim_review_gate
    checked = inspect_physical_claim_review_gate(
        audit_directory, manifest, trusted_key=key, trusted_reviewer_ids=reviewers,
    )
    redacted = (
        "status", "submitted_claims", "observed_claims",
        "promoted_documentary_decisions", "reviewed_as_corroborated",
        "reviewed_as_contradicted", "unverified_claims",
        "source_aud_integrity_unchanged",
    )
    return {
        **public, "status": checked["status"],
        "gate": {field: checked[field] for field in redacted if field in checked},
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Read-only Windows evidence triage and private gate #603"
    )
    parser.add_argument("--audit-directory", type=Path)
    parser.add_argument("--search-root", type=Path)
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args(argv)
    result = inspect(
        audit_directory=args.audit_directory,
        search_root=args.search_root if args.audit_directory is None else None,
        manifest=args.manifest,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["status"] == "AUTHENTICATED_REVIEW_AND_AUD_LINK_VERIFIED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
