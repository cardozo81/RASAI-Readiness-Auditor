from __future__ import annotations

import sqlite3
from pathlib import Path

from rasai.persistence import AuditWorkspace
from rasai.property_semantic_profile import build_property_semantic_profile
from rasai.property_semantic_profile_persistence import (
    load_property_semantic_profile,
    persist_property_semantic_profile,
)


def _workspace(tmp_path: Path) -> AuditWorkspace:
    workspace = AuditWorkspace.create(tmp_path, "AUD-SEMANTIC-PROFILE")
    connection = sqlite3.connect(workspace.database)
    try:
        with connection:
            connection.execute("CREATE TABLE IF NOT EXISTS audits(audit_id TEXT PRIMARY KEY)")
            connection.execute("INSERT OR IGNORE INTO audits VALUES (?)", ("AUD-SEMANTIC-PROFILE",))
    finally:
        connection.close()
    return workspace


def test_property_semantic_profile_is_write_once_per_audit(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    first = build_property_semantic_profile(
        business_sector="Software B2B",
        primary_offering="Finance SaaS",
    )
    second = build_property_semantic_profile(
        business_sector="Healthcare",
        primary_offering="Clinical SaaS",
    )

    persist_property_semantic_profile(
        workspace=workspace,
        audit_id="AUD-SEMANTIC-PROFILE",
        profile=first,
        created_at="2026-09-17T10:00:00Z",
    )
    persist_property_semantic_profile(
        workspace=workspace,
        audit_id="AUD-SEMANTIC-PROFILE",
        profile=second,
        created_at="2026-09-17T11:00:00Z",
    )

    loaded = load_property_semantic_profile(workspace=workspace, audit_id="AUD-SEMANTIC-PROFILE")
    assert loaded is not None
    profile, metadata = loaded
    assert profile.business_sector == "Software B2B"
    assert profile.primary_offering == "Finance SaaS"
    assert metadata["source_mode"] == "MIXED"
    assert metadata["created_at"] == "2026-09-17T10:00:00Z"
