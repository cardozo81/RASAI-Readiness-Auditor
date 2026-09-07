"""Persistence adapter for M6 architecture classification."""

from __future__ import annotations

import sqlite3

from rasai.domain import ArchitectureClassification
from rasai.persistence import AuditWorkspace


class SnapshotArchitectureWriter:
    def __init__(self, workspace: AuditWorkspace) -> None:
        self._database = workspace.database

    def update(self, snapshot_id: str, classification: ArchitectureClassification) -> None:
        connection = sqlite3.connect(self._database)
        try:
            with connection:
                cursor = connection.execute(
                    "UPDATE page_snapshots SET architecture_classification = ? WHERE snapshot_id = ?",
                    (classification.value, snapshot_id),
                )
            if cursor.rowcount != 1:
                raise KeyError(f"snapshot not found: {snapshot_id}")
        finally:
            connection.close()
