"""Compatibility bridge for governed M24 selective reprocessing.

The legacy RPR helper reconstructed ``M24Diagnostic`` with a historical
``scoring_impact`` constructor argument that no longer exists in the canonical
M24 dataclass.  Governed M24 continuation is shared by initial processing and RPR,
so the reprocessor only needs a faithful loader for the persisted diagnostics.

This module deliberately does not implement provider selection, retry/fallback,
continuation, scoring, or persistence policy.  Those remain owned by the canonical
M24/governance runtimes.
"""
from __future__ import annotations

import json
import sqlite3
from typing import Any


_INSTALLED = False


def _load_json(value: Any, default: Any) -> Any:
    if value in (None, ""):
        return default
    if isinstance(value, (dict, list, tuple)):
        return value
    try:
        return json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return default


def load_persisted_m24_diagnostics(workspace: Any, audit_id: str):
    """Reopen persisted M24 facts using the current canonical dataclass contract."""
    from rasai.m24_crawling_discovery import M24Diagnostic

    connection = sqlite3.connect(workspace.database)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
            "SELECT code,category,severity,title,scope_url,observed_value,evidence_ids,remediation "
            "FROM m24_diagnostics WHERE audit_id=? ORDER BY diagnostic_id",
            (audit_id,),
        ).fetchall()
    finally:
        connection.close()

    return tuple(
        M24Diagnostic(
            code=str(row["code"]),
            category=str(row["category"]),
            severity=str(row["severity"]),
            title=str(row["title"]),
            scope_url=str(row["scope_url"]) if row["scope_url"] else None,
            observed=dict(_load_json(row["observed_value"], {})),
            evidence_ids=tuple(
                str(value)
                for value in _load_json(row["evidence_ids"], [])
                if str(value).strip()
            ),
            remediation=str(row["remediation"]),
        )
        for row in rows
    )


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    try:
        from rasai import reprocess_ai
    except ImportError:
        _INSTALLED = True
        return

    current = getattr(reprocess_ai, "_m24_diagnostics", None)
    if current is not None and not bool(getattr(current, "_rasai_current_m24_contract", False)):
        load_persisted_m24_diagnostics._rasai_current_m24_contract = True
        load_persisted_m24_diagnostics._rasai_original = current
        reprocess_ai._m24_diagnostics = load_persisted_m24_diagnostics
    _INSTALLED = True


__all__ = ["install", "load_persisted_m24_diagnostics"]
