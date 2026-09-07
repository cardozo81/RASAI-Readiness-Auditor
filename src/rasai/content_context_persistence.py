"""Persistence for the audit-level content analysis context.

The resolved context is stored once so semantic analysis, content remediation and
static reports can all prove which configuration was actually used.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from rasai.content_context import ContentAnalysisContext, build_content_analysis_context
from rasai.persistence import AuditWorkspace


def persist_content_analysis_context(
    *,
    workspace: AuditWorkspace,
    audit_id: str,
    context: ContentAnalysisContext,
    created_at: str,
) -> None:
    """Persist the first effective context for an audit and never overwrite it.

    Report regeneration may happen after environment variables have changed.
    Replacing the row in that situation would destroy provenance, so this table
    is intentionally write-once per ``audit_id``.
    """

    source_mode = (
        "AUTO"
        if context.is_fully_auto
        else "MANUAL"
        if not context.auto_fields
        else "MIXED"
    )
    connection = sqlite3.connect(workspace.database)
    try:
        with connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS content_analysis_contexts (
                    audit_id TEXT PRIMARY KEY REFERENCES audits(audit_id) ON DELETE CASCADE,
                    risk_profile TEXT NOT NULL,
                    ymyl_category TEXT NOT NULL,
                    page_purpose TEXT NOT NULL,
                    intended_audience TEXT NOT NULL,
                    experience_requirement TEXT NOT NULL,
                    freshness_sensitivity TEXT NOT NULL,
                    content_origin TEXT NOT NULL,
                    configured_fields TEXT NOT NULL,
                    auto_fields TEXT NOT NULL,
                    source_mode TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                INSERT INTO content_analysis_contexts VALUES (
                    ?,?,?,?,?,?,?,?,?,?,?,?
                )
                ON CONFLICT(audit_id) DO NOTHING
                """,
                (
                    audit_id,
                    context.risk_profile.value,
                    context.ymyl_category.value,
                    context.page_purpose.value,
                    context.intended_audience.value,
                    context.experience_requirement.value,
                    context.freshness_sensitivity.value,
                    context.content_origin.value,
                    json.dumps(list(context.configured_fields), ensure_ascii=False),
                    json.dumps(list(context.auto_fields), ensure_ascii=False),
                    source_mode,
                    created_at,
                ),
            )
    finally:
        connection.close()


def load_content_analysis_context(
    *,
    workspace: AuditWorkspace,
    audit_id: str,
) -> tuple[ContentAnalysisContext, dict[str, Any]] | None:
    connection = sqlite3.connect(workspace.database)
    connection.row_factory = sqlite3.Row
    try:
        try:
            row = connection.execute(
                "SELECT * FROM content_analysis_contexts WHERE audit_id=?",
                (audit_id,),
            ).fetchone()
        except sqlite3.OperationalError as exc:
            if "no such table" in str(exc).lower():
                return None
            raise
        if row is None:
            return None
        context = build_content_analysis_context(
            risk_profile=str(row["risk_profile"]),
            ymyl_category=str(row["ymyl_category"]),
            page_purpose=str(row["page_purpose"]),
            intended_audience=str(row["intended_audience"]),
            experience_requirement=str(row["experience_requirement"]),
            freshness_sensitivity=str(row["freshness_sensitivity"]),
            content_origin=str(row["content_origin"]),
        )
        metadata = {
            "source_mode": str(row["source_mode"]),
            "configured_fields": json.loads(str(row["configured_fields"])),
            "auto_fields": json.loads(str(row["auto_fields"])),
            "created_at": str(row["created_at"]),
        }
        return context, metadata
    finally:
        connection.close()
