"""Generate report/report-manifest.json from immutable audit metadata.

The manifest is a projection index, not a second evidence store. It deliberately
contains no score values, findings or evidence payloads and opens audit.db in
read-only/query-only mode.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from typing import Any

from rasai.report_contract import (
    OBSERVABILITY_CONTRACT_VERSION,
    REPORT_ALIASES,
    REPORT_CONTRACT_VERSION,
    SARI_VERSION,
    REPORT_SURFACES,
)

MANIFEST_FILE = "report-manifest.json"


def write_report_manifest(report_dir: str | Path) -> Path | None:
    root = Path(report_dir)
    database = root.parent / "audit.db"
    if not root.is_dir() or not database.is_file():
        return None

    metadata = _read_audit_metadata(database)
    generated_pages = [
        surface.filename
        for surface in REPORT_SURFACES
        if (root / surface.filename).is_file()
    ]
    aliases = {
        alias: canonical
        for alias, canonical in REPORT_ALIASES.items()
        if (root / alias).is_file()
    }
    manifest: dict[str, Any] = {
        "audit_id": metadata.get("audit_id"),
        "auditor_version": metadata.get("auditor_version"),
        "ruleset_version": metadata.get("ruleset_version"),
        "sari_version": SARI_VERSION,
        "scoring_version": metadata.get("scoring_version"),
        "report_contract_version": REPORT_CONTRACT_VERSION,
        "observability_contract_version": (
            OBSERVABILITY_CONTRACT_VERSION if "observability.html" in generated_pages else None
        ),
        "generated_pages": generated_pages,
        "aliases": aliases,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_db": "audit.db",
    }
    if metadata.get("scoring_versions") and len(metadata["scoring_versions"]) > 1:
        # Multiple versions inside one AUD are preserved as an integrity signal;
        # they are never collapsed or rewritten by the report projection.
        manifest["scoring_versions"] = metadata["scoring_versions"]

    path = root / MANIFEST_FILE
    path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return path


def _read_audit_metadata(database: Path) -> dict[str, Any]:
    connection = sqlite3.connect(f"file:{database.as_posix()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA query_only=ON")
        audit = _one(connection, "SELECT audit_id,auditor_version,ruleset_version FROM audits LIMIT 1")
        versions = _scoring_versions(connection, str(audit["audit_id"]) if audit is not None else None)
        return {
            "audit_id": str(audit["audit_id"]) if audit is not None else None,
            "auditor_version": str(audit["auditor_version"]) if audit is not None and audit["auditor_version"] is not None else None,
            "ruleset_version": str(audit["ruleset_version"]) if audit is not None and audit["ruleset_version"] is not None else None,
            "scoring_version": versions[0] if len(versions) == 1 else None,
            "scoring_versions": versions,
        }
    finally:
        connection.close()


def _one(connection: sqlite3.Connection, sql: str) -> sqlite3.Row | None:
    try:
        return connection.execute(sql).fetchone()
    except sqlite3.OperationalError:
        return None


def _scoring_versions(connection: sqlite3.Connection, audit_id: str | None) -> list[str]:
    if not audit_id:
        return []
    try:
        rows = connection.execute(
            "SELECT DISTINCT scoring_version FROM scores WHERE audit_id=? AND scoring_version IS NOT NULL ORDER BY scoring_version",
            (audit_id,),
        ).fetchall()
    except sqlite3.OperationalError:
        return []
    return [str(row[0]) for row in rows if row[0]]
