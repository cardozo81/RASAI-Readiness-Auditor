"""Read-only bridge from persisted M6 snapshots to advisory architecture context.

No report mutation, collection, scoring or provider access.
"""
from __future__ import annotations

from pathlib import Path
import sqlite3

from rasai.architecture_context import ArchitectureObservation, resolve_architecture


def observed_architecture_for_snapshot(
    database: Path,
    *,
    audit_id: str,
    page_id: str,
    snapshot_id: str,
    requested_url: str,
    final_url: str,
    device: str,
):
    """Return a scoped advisory context, abstaining for absent/ambiguous M6 rows.

    This function does not grant any consumer permission to inherit architecture.
    """
    if not all(isinstance(x, str) and x.strip() for x in (
        audit_id, page_id, snapshot_id, requested_url, final_url, device
    )):
        raise ValueError("Complete audited snapshot identity is required")
    path = Path(database)
    if (not path.is_file() or path.is_symlink() or path.parent.is_symlink()
            or any(Path(str(path) + suffix).exists()
                   for suffix in ("-wal", "-shm", "-journal"))):
        raise ValueError("Source is missing, unsealed or not a regular SQLite file")
    before = path.stat()
    seal = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
    observations = ()
    with sqlite3.connect(path.resolve().as_uri() + "?mode=ro&immutable=1", uri=True) as con:
        con.execute("PRAGMA query_only=ON")
        try:
            rows = con.execute(
                """SELECT ps.architecture_classification
                   FROM page_snapshots ps
                   JOIN pages p ON p.page_id=ps.page_id
                   WHERE p.audit_id=? AND ps.page_id=? AND ps.snapshot_id=?
                     AND ps.requested_url=? AND ps.final_url=? AND ps.device=?
                   LIMIT 2""",
                (audit_id, page_id, snapshot_id, requested_url, final_url, device),
            ).fetchall()
            # Reject reused physical snapshot identifiers across contexts.
            duplicates = con.execute(
                "SELECT COUNT(*) FROM page_snapshots WHERE snapshot_id=?",
                (snapshot_id,),
            ).fetchone()[0]
        except sqlite3.DatabaseError:
            rows, duplicates = (), 0
    after = path.stat()
    if (path.is_symlink() or path.parent.is_symlink()
            or any(Path(str(path) + suffix).exists()
                   for suffix in ("-wal", "-shm", "-journal"))
            or (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns) != seal):
        raise ValueError("SQLite source changed during advisory read")
    if len(rows) == 1 and duplicates == 1:
        observations = (ArchitectureObservation(
            architecture=str(rows[0][0] or "UNKNOWN"),
            requested_url=requested_url,
            final_url=final_url,
            device=device,
            snapshot_id=snapshot_id,
            page_id=page_id,
            audit_id=audit_id,
            evidence_ref="sqlite:page_snapshots:" + snapshot_id,
        ),)
    return resolve_architecture(
        mode="AUTO", declared_architecture=None,
        observations=observations,
        requested_url=requested_url,
        final_url=final_url,
        device=device,
        snapshot_id=snapshot_id,
        page_id=page_id,
        audit_id=audit_id,
        consumer_id="m6_read_only_diagnostic",
        advisory_consumers=frozenset({"m6_read_only_diagnostic"}),
    )
