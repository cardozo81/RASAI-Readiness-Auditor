"""Persistence adapter for M4 extraction fields without changing the M1 schema."""

from __future__ import annotations

import sqlite3

from rasai.domain import PageSnapshot
from rasai.persistence import AuditWorkspace


class SnapshotExtractionWriter:
    """Update extraction-owned PageSnapshot fields in the existing SQLite schema."""

    def __init__(self, workspace: AuditWorkspace) -> None:
        self._database = workspace.database

    def update(self, snapshot: PageSnapshot) -> None:
        connection = sqlite3.connect(self._database)
        try:
            with connection:
                cursor = connection.execute(
                    """
                    UPDATE page_snapshots SET
                        title = ?,
                        description = ?,
                        canonical = ?,
                        meta_robots = ?,
                        main_content_ref = ?,
                        structured_data_ref = ?
                    WHERE snapshot_id = ? AND page_id = ? AND device = ?
                    """,
                    (
                        snapshot.title,
                        snapshot.description,
                        snapshot.canonical,
                        snapshot.meta_robots,
                        snapshot.main_content_ref,
                        snapshot.structured_data_ref,
                        snapshot.snapshot_id,
                        snapshot.page_id,
                        snapshot.device.value,
                    ),
                )
            if cursor.rowcount != 1:
                raise KeyError(f"snapshot not found or scope mismatch: {snapshot.snapshot_id}")
        finally:
            connection.close()
