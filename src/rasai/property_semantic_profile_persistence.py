"""Write-once audit persistence for declared property semantic context."""
from __future__ import annotations

import json
import sqlite3
from typing import Any

from rasai.persistence import AuditWorkspace
from rasai.property_semantic_profile import PropertySemanticProfile, build_property_semantic_profile


def persist_property_semantic_profile(
    *,
    workspace: AuditWorkspace,
    audit_id: str,
    profile: PropertySemanticProfile,
    created_at: str,
) -> None:
    """Freeze the effective property context used by an AUD without later overwrite."""
    source_mode = "AUTO" if profile.is_fully_auto else "MANUAL" if not profile.auto_fields else "MIXED"
    connection = sqlite3.connect(workspace.database)
    try:
        with connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS property_semantic_contexts (
                    audit_id TEXT PRIMARY KEY REFERENCES audits(audit_id) ON DELETE CASCADE,
                    business_sector TEXT NOT NULL,
                    business_description TEXT NOT NULL,
                    primary_offering TEXT NOT NULL,
                    target_audience_profile TEXT NOT NULL,
                    primary_goal TEXT NOT NULL,
                    positioning TEXT NOT NULL,
                    configured_fields TEXT NOT NULL,
                    auto_fields TEXT NOT NULL,
                    source_mode TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                INSERT INTO property_semantic_contexts VALUES (?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(audit_id) DO NOTHING
                """,
                (
                    audit_id,
                    profile.business_sector,
                    profile.business_description,
                    profile.primary_offering,
                    profile.target_audience_profile,
                    profile.primary_goal,
                    profile.positioning,
                    json.dumps(list(profile.configured_fields), ensure_ascii=False),
                    json.dumps(list(profile.auto_fields), ensure_ascii=False),
                    source_mode,
                    created_at,
                ),
            )
    finally:
        connection.close()


def load_property_semantic_profile(
    *,
    workspace: AuditWorkspace,
    audit_id: str,
) -> tuple[PropertySemanticProfile, dict[str, Any]] | None:
    connection = sqlite3.connect(workspace.database)
    connection.row_factory = sqlite3.Row
    try:
        try:
            row = connection.execute(
                "SELECT * FROM property_semantic_contexts WHERE audit_id=?",
                (audit_id,),
            ).fetchone()
        except sqlite3.OperationalError as exc:
            if "no such table" in str(exc).lower():
                return None
            raise
        if row is None:
            return None
        profile = build_property_semantic_profile(
            business_sector=str(row["business_sector"]),
            business_description=str(row["business_description"]),
            primary_offering=str(row["primary_offering"]),
            target_audience_profile=str(row["target_audience_profile"]),
            primary_goal=str(row["primary_goal"]),
            positioning=str(row["positioning"]),
        )
        return profile, {
            "source_mode": str(row["source_mode"]),
            "configured_fields": json.loads(str(row["configured_fields"])),
            "auto_fields": json.loads(str(row["auto_fields"])),
            "created_at": str(row["created_at"]),
        }
    finally:
        connection.close()
