from __future__ import annotations

import sqlite3
from pathlib import Path
from types import SimpleNamespace

from rasai.semantic_coherence import (
    PROPERTY_COHERENCE_LABELS_PT_BR,
    coherence_prompt_directive,
)
from rasai.semantic_coherence_persistence import aggregate_property_coherence


def test_coherence_prompt_requires_audit_primary_language_for_free_text() -> None:
    directive = coherence_prompt_directive()
    assert "primary_language" in directive
    assert "Brazilian Portuguese" in directive
    assert "declared_context" in directive
    assert "observed_context" in directive
    assert "reasoning_summary" in directive


def test_property_coherence_summary_uses_pt_br_description(tmp_path: Path) -> None:
    database = tmp_path / "audit.db"
    connection = sqlite3.connect(database)
    try:
        connection.executescript(
            """
            CREATE TABLE audits(audit_id TEXT PRIMARY KEY);
            CREATE TABLE page_snapshots(snapshot_id TEXT PRIMARY KEY);
            INSERT INTO audits VALUES('AUD-LANG');
            INSERT INTO page_snapshots VALUES('S1');
            """
        )
        connection.commit()
    finally:
        connection.close()

    workspace = SimpleNamespace(database=database)
    aggregate_property_coherence(workspace=workspace, audit_id="AUD-LANG")

    connection = sqlite3.connect(database)
    try:
        summary = connection.execute(
            "SELECT summary FROM property_semantic_summaries WHERE audit_id=? AND criterion_id='SC-X02'",
            ("AUD-LANG",),
        ).fetchone()[0]
    finally:
        connection.close()
    assert summary.startswith(PROPERTY_COHERENCE_LABELS_PT_BR["SC-X02"])
    assert "primary offering remains aligned" not in summary.casefold()
