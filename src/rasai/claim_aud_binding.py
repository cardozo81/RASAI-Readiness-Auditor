"""#603: optional physical AUD-to-claim literal-text identity, strictly offline.

This corroborates only that a specific, globally unique snapshot stores the
same literal text in its main-content artifact. The source may be incomplete;
an exact match is not proof of commercial accuracy, product applicability,
same browser session, regulatory authorization or legal compliance.
"""
from __future__ import annotations

from contextlib import closing
from datetime import date, datetime, timezone
from hashlib import sha256
from pathlib import Path
import sqlite3
from typing import Any, Mapping, Sequence

from rasai.geo_query_ledger import _audit_digest

_MAX_ARTIFACT_BYTES = 2_000_000


def _ref_file(root: Path, reference: object) -> Path | None:
    if (not isinstance(reference, str) or not reference
            or len(reference) > 260 or "\\" in reference
            or ":" in reference or reference.startswith("/")
            or "\x00" in reference):
        return None
    parts = reference.split("/")
    if (parts[0] != "artifacts" or len(parts) < 2
            or any(not p or p in {".", ".."} for p in parts)):
        return None
    current = root
    for name in parts:
        current = current / name
        if current.is_symlink():
            return None
    try:
        if (not current.is_file()
                or not current.resolve().is_relative_to(root.resolve())
                or not 0 < current.stat().st_size <= _MAX_ARTIFACT_BYTES):
            return None
    except (OSError, ValueError):
        return None
    return current


def _utc_capture_day(value: object) -> date | None:
    """Reject unzoned timestamps; never infer a historical local timezone."""
    if not isinstance(value, str) or not value or value != value.strip():
        return None
    try:
        captured = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if captured.tzinfo is None or captured.utcoffset() is None:
            return None
        return captured.astimezone(timezone.utc).date()
    except (TypeError, ValueError, OverflowError):
        return None


def bind_claim_texts(
    audit_dir: Path, audit_id: str, observations: Sequence[Mapping[str, Any]],
    *, expected_at_date: date | None = None,
) -> dict[str, Any]:
    """Bind manifest claims to observed text in one immutable physical AUD.

    A successful local digest means *byte consistency*, not authority of the
    audited site or the externally signed documentary claim review.
    """
    unavailable = {
        "status": "NOT_VERIFIABLE",
        "reason": "AUD_SOURCE_OR_SCOPE_NOT_VERIFIED",
        "audit_id": audit_id,
        "source_audit_db_sha256": None,
        "claims": {},
    }
    root = Path(audit_dir)
    db = root / "audit.db"
    if (not isinstance(audit_id, str) or not audit_id.startswith("AUD-")
            or root.name != audit_id or root.is_symlink() or not root.is_dir()
            or db.is_symlink() or not db.is_file()
            or any(Path(str(db) + suffix).exists() for suffix in (
                "-wal", "-shm", "-journal"))
            or len(observations) > 50
            or (expected_at_date is not None and type(expected_at_date) is not date)):
        # An untrusted manifest cannot replace the snapshot capture date.
        return unavailable
    try:
        before, before_size = _audit_digest(db)
        with closing(sqlite3.connect(
            db.resolve().as_uri() + "?mode=ro&immutable=1",
            uri=True, timeout=2,
        )) as con:
            con.execute("PRAGMA query_only=ON")
            audit_cols = {r[1] for r in con.execute("PRAGMA table_info(audits)")}
            page_cols = {r[1] for r in con.execute("PRAGMA table_info(pages)")}
            snap_cols = {r[1] for r in con.execute("PRAGMA table_info(page_snapshots)")}
            if (not {"audit_id", "status", "completion_status"} <= audit_cols
                    or not {"page_id", "audit_id"} <= page_cols
                    or not {"snapshot_id", "page_id", "main_content_ref"} <= snap_cols
                    or (expected_at_date is not None and "captured_at" not in snap_cols)):
                return unavailable
            aud = con.execute(
                "SELECT audit_id,status,completion_status FROM audits LIMIT 2"
            ).fetchall()
            if (len(aud) != 1 or aud[0][0] != audit_id
                    or str(aud[0][1]).upper() != "COMPLETED"
                    or str(aud[0][2]).upper() != "COMPLETE"):
                return unavailable
            outcomes: dict[str, Any] = {}
            artifact_seals: dict[Path, str] = {}
            for observation in observations:
                claim_id = observation["claim_id"]
                snapshot_id = observation.get("snapshot_id")
                claim = observation.get("claim_text")
                denied = {
                    "status": "NOT_VERIFIED",
                    "reason": "SNAPSHOT_OR_LITERAL_TEXT_NOT_MATCHED",
                    "snapshot_id": snapshot_id if isinstance(snapshot_id, str) else None,
                }
                if (not isinstance(snapshot_id, str)
                        or not snapshot_id.startswith("SNP-")
                        or len(snapshot_id) > 128
                        or not isinstance(claim, str)
                        or not 8 <= len(claim) <= 8192
                        or claim != claim.strip()):
                    outcomes[claim_id] = denied
                    continue
                # Global census prevents a snapshot reused by other AUDs
                # from satisfying the operator's chosen physical identity.
                capture_column = (
                    "s.captured_at" if expected_at_date is not None else "NULL"
                )
                matches = con.execute(
                    "SELECT s.page_id,p.audit_id,s.main_content_ref, "
                    + capture_column
                    + " FROM page_snapshots s JOIN pages p ON p.page_id=s.page_id "
                      "WHERE s.snapshot_id=? LIMIT 2",
                    (snapshot_id,),
                ).fetchall()
                count = con.execute(
                    "SELECT COUNT(*) FROM page_snapshots WHERE snapshot_id=?",
                    (snapshot_id,)
                ).fetchone()[0]
                if len(matches) != 1 or count != 1 or matches[0][1] != audit_id:
                    outcomes[claim_id] = denied
                    continue
                if (expected_at_date is not None
                        and _utc_capture_day(matches[0][3]) != expected_at_date):
                    outcomes[claim_id] = {
                        **denied, "reason": "SNAPSHOT_CAPTURE_DATE_NOT_ATTESTED",
                    }
                    continue
                path = _ref_file(root, matches[0][2])
                if path is None:
                    outcomes[claim_id] = denied
                    continue
                raw = path.read_bytes()
                # Reject truncated/replaced textual evidence; never normalize
                # whitespace or accentuation to manufacture a literal match.
                if not 0 < len(raw) <= _MAX_ARTIFACT_BYTES:
                    outcomes[claim_id] = denied
                    continue
                digest = sha256(raw).hexdigest()
                artifact_seals[path] = digest
                try:
                    matched = claim in raw.decode("utf-8")
                except UnicodeError:
                    matched = False
                if not matched:
                    outcomes[claim_id] = denied
                    continue
                outcomes[claim_id] = {
                    "status": "TEXT_PRESENT_IN_SNAPSHOT_MAIN_CONTENT",
                    "reason": None,
                    "snapshot_id": snapshot_id,
                    "page_id": matches[0][0],
                    "source_artifact_ref": matches[0][2],
                    "main_content_sha256": digest,
                    "interpretation": "LITERAL_TEXT_ONLY_NOT_SOURCE_AUTHENTICITY",
                }
        # Verify both physical sources *after* using their contents. No
        # mutation of a snapshot or database may leak an accepted binding.
        if any(
            path.is_symlink() or not path.is_file()
            or sha256(path.read_bytes()).hexdigest() != digest
            for path, digest in artifact_seals.items()
        ):
            return unavailable
        if any(Path(str(db) + suffix).exists() for suffix in (
            "-wal", "-shm", "-journal")):
            return unavailable
        after, after_size = _audit_digest(db)
        if before != after or before_size != after_size:
            return unavailable
        return {
            "status": "OBSERVATIONAL_BINDING_CHECKED",
            "reason": None,
            "audit_id": audit_id,
            "source_audit_db_sha256": before,
            "claims": outcomes,
        }
    except (OSError, sqlite3.Error, ValueError, TypeError, OverflowError, KeyError):
        return unavailable


__all__ = ["bind_claim_texts"]
