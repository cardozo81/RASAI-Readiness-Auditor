"""#601: bounded, read-only physical identity of FAQ source snapshots.

A snapshot's rendered HTML remains a *without-click* observation. Persisted
URL/device columns are reported with their exact evidence scope when present.
This reader does not authenticate user actions, attest a crawler, or score FAQ.
"""
from __future__ import annotations

from dataclasses import dataclass
import sqlite3
from urllib.parse import urlsplit


@dataclass(frozen=True)
class FaqSnapshotScope:
    snapshot_id: str
    page_id: str
    artifact_ref: object
    requested_url: str
    final_url: str
    device: str


def _url(value: object) -> str:
    if not isinstance(value, str) or len(value) > 2048 or value != value.strip():
        return "N/D"
    if any(ord(character) < 32 or ord(character) == 127 or character == "\\" for character in value):
        return "N/D"
    try:
        url = urlsplit(value)
        _ = url.port
        if (url.scheme not in {"http", "https"} or not url.hostname
                or url.username is not None or url.password is not None
                or url.port == 0):
            return "N/D"
    except ValueError:
        return "N/D"
    return value


def read_faq_snapshot_scopes(
    connection: sqlite3.Connection, audit_id: str, *, limit: int = 12,
) -> tuple[tuple[FaqSnapshotScope, ...], bool, str]:
    """Select one audit, fail closed on ambiguous IDs even outside the sample.

    Legacy snapshots without all scope columns remain N/D. A persisted string
    is source metadata, never a statement about a browser action.
    """
    if not isinstance(audit_id, str) or not audit_id.startswith("AUD-"):
        return (), False, "INVALID_AUDIT_ID"
    if type(limit) is not int or not 1 <= limit <= 100:
        return (), False, "INVALID_LIMIT"
    try:
        columns = {
            row[1] for row in connection.execute("PRAGMA table_info(page_snapshots)")
        }
        required = {"snapshot_id", "page_id", "rendered_artifact_ref"}
        if not required.issubset(columns):
            return (), False, "MISSING_SNAPSHOT_SCHEMA"
        page_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(pages)")
        }
        if not {"page_id", "audit_id"}.issubset(page_columns):
            return (), False, "MISSING_PAGES_SCHEMA"
        # A duplicate snapshot outside the 12-row display limit can still
        # collide with a capture in this AUD. A complete identity census is
        # required before emitting any audit-level FAQ counts.
        ambiguous = connection.execute(
            "SELECT 1 FROM page_snapshots x "
            "WHERE x.snapshot_id IN ("
              "SELECT s.snapshot_id FROM page_snapshots s "
              "JOIN pages p ON p.page_id=s.page_id WHERE p.audit_id=?) "
            "GROUP BY x.snapshot_id HAVING COUNT(*) != 1 LIMIT 1",
            (audit_id,),
        ).fetchone()
        if ambiguous:
            return (), False, "AMBIGUOUS_SNAPSHOT_ID"
        invalid = connection.execute(
            "SELECT 1 FROM page_snapshots s "
            "JOIN pages p ON p.page_id=s.page_id "
            "WHERE p.audit_id=? AND "
            "(s.snapshot_id IS NULL OR TRIM(s.snapshot_id)='') LIMIT 1",
            (audit_id,),
        ).fetchone()
        if invalid:
            return (), False, "AMBIGUOUS_SNAPSHOT_ID"
        optional = [
            "s." + name if name in columns else "NULL"
            for name in ("requested_url", "final_url", "device")
        ]
        rows = connection.execute(
            "SELECT s.snapshot_id,s.page_id,s.rendered_artifact_ref,"
            + ",".join(optional)
            + ",(SELECT COUNT(*) FROM page_snapshots x "
              "WHERE x.snapshot_id=s.snapshot_id) "
              "FROM page_snapshots s JOIN pages p ON p.page_id=s.page_id "
              "WHERE p.audit_id=? ORDER BY s.snapshot_id LIMIT ?",
            (audit_id, limit + 1),
        ).fetchall()
    except sqlite3.Error:
        return (), False, "UNVERIFIABLE_SOURCE"
    result: list[FaqSnapshotScope] = []
    observed: set[str] = set()
    for snapshot_id, page_id, ref, requested, final, device, count in rows:
        if (not isinstance(snapshot_id, str) or not snapshot_id.strip()
                or not isinstance(page_id, str) or not page_id.strip()
                or count != 1 or snapshot_id in observed):
            return (), False, "AMBIGUOUS_SNAPSHOT_ID"
        observed.add(snapshot_id)
        result.append(FaqSnapshotScope(
            snapshot_id=snapshot_id,
            page_id=page_id,
            artifact_ref=ref,
            requested_url=_url(requested),
            final_url=_url(final),
            device=(device.upper() if isinstance(device, str)
                    and device.upper() in {"DESKTOP", "MOBILE"}
                    and device == device.strip() else "N/D"),
        ))
    truncated = len(result) > limit
    return tuple(result[:limit]), truncated, "OBSERVATIONAL_SCOPE_ONLY"


__all__ = ["FaqSnapshotScope", "read_faq_snapshot_scopes"]
