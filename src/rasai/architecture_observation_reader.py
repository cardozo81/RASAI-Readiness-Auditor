"""Canonical read-only M6 advisory adapter.

The sole physical observation reader enforces the same SQLite source identity,
artifact binding and (when configured) Ed25519 anchor as historical reprocessing.
A lightweight classification-only SQL query must never bypass those gates.
"""
from __future__ import annotations

from pathlib import Path

from rasai.architecture_context import resolve_architecture
from rasai.architecture_m6_evidence import read_audit_architecture_observations


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
    """Resolve one physical AUD snapshot; abstain on missing or unsafe evidence."""
    if not all(isinstance(x, str) and x.strip() for x in (
        audit_id, page_id, snapshot_id, requested_url, final_url, device
    )):
        raise ValueError("Complete audited snapshot identity is required")
    path = Path(database)
    if (path.name != "audit.db" or path.parent.name != audit_id
            or path.is_symlink() or not path.is_file()):
        raise ValueError("Canonical physical AUD database is required")
    observations = read_audit_architecture_observations(path.parent.parent, audit_id)
    return resolve_architecture(
        mode="AUTO", declared_architecture=None,
        observations=observations, requested_url=requested_url,
        final_url=final_url, device=device, snapshot_id=snapshot_id,
        page_id=page_id, audit_id=audit_id,
        consumer_id="m6_read_only_diagnostic",
        advisory_consumers=frozenset({"m6_read_only_diagnostic"}),
    )
