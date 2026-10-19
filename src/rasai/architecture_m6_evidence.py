"""Read persisted M6 architecture evidence without external acquisition or writes.

An audit reprocess/complement may inspect this read-only inventory. No replay,
scoring, file mutation, new requests, or inference across URL/device/snapshot.
"""
from __future__ import annotations

from pathlib import Path
import sqlite3

from rasai.architecture_context import ArchitectureObservation, CLASSES
from rasai.audit_configuration_reuse import normalize_audit_id

MAX_OBSERVATIONS = 2000


def read_audit_architecture_observations(
    audits_root: str | Path, audit_id: str,
) -> tuple[ArchitectureObservation, ...]:
    normalized = normalize_audit_id(audit_id)
    root = Path(audits_root).resolve()
    workspace = root / normalized
    database = workspace / "audit.db"
    if (workspace.is_symlink() or database.is_symlink()
            or not database.resolve().is_relative_to(root)
            or not database.is_file()):
        return ()
    try:
        connection = sqlite3.connect(
            database.resolve().as_uri() + "?mode=ro", uri=True, timeout=1.0,
        )
        try:
            connection.execute("PRAGMA query_only=ON")
            rows = connection.execute(
                """SELECT ps.snapshot_id, ps.page_id, ps.device,
                          ps.requested_url, ps.final_url, ps.architecture_classification,
                          ps.raw_artifact_ref, ps.rendered_artifact_ref
                   FROM page_snapshots ps JOIN pages p ON ps.page_id=p.page_id
                   WHERE p.audit_id=?
                   ORDER BY ps.snapshot_id LIMIT ?""",
                (normalized, MAX_OBSERVATIONS + 1),
            ).fetchall()
        finally:
            connection.close()
    except (OSError, sqlite3.Error, ValueError):
        return ()
    if len(rows) > MAX_OBSERVATIONS:
        return ()
    observations = []
    seen = set()
    for snapshot_id, page_id, device, requested, final, architecture, raw, rendered in rows:
        identity = (snapshot_id, page_id, device, requested, final)
        if (not all(isinstance(item, str) and item.strip() for item in identity)
                or identity in seen or architecture not in CLASSES
                or not isinstance(raw, str) or not raw.strip()
                or not isinstance(rendered, str) or not rendered.strip()):
            # Never elevate an incomplete or duplicated RAW/rendered pair.
            continue
        seen.add(identity)
        observations.append(ArchitectureObservation(
            architecture=architecture, requested_url=requested,
            final_url=final, device=device, snapshot_id=snapshot_id,
            evidence_ref=raw, audit_id=normalized, page_id=page_id,
        ))
    return tuple(observations)
