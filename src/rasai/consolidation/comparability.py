"""Comparability helpers over the rebuildable analytical index."""
from __future__ import annotations

from pathlib import Path
import hashlib
import json
import sqlite3
from typing import Any


def annotate_score_url_universes(
    index_path: Path,
    rows: tuple[dict[str, Any], ...],
) -> tuple[dict[str, Any], ...]:
    """Attach a stable URL-set fingerprint to audit-level score rows.

    The URL universe lives in the derived index. Source AUD databases remain
    untouched. The helper is read-only and intentionally separate from scoring.
    """
    audit_ids = sorted({str(row.get("audit_id") or "") for row in rows if row.get("audit_id")})
    if not audit_ids:
        return rows
    connection = sqlite3.connect(f"file:{index_path.resolve().as_posix()}?mode=ro", uri=True)
    try:
        mapping: dict[str, str] = {}
        for audit_id in audit_ids:
            urls = [
                str(row[0]) for row in connection.execute(
                    "SELECT url FROM audit_urls WHERE audit_id=? ORDER BY url", (audit_id,)
                ).fetchall()
            ]
            payload = json.dumps(urls, ensure_ascii=False, separators=(",", ":"))
            mapping[audit_id] = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    finally:
        connection.close()
    return tuple(
        {**row, "url_universe": mapping.get(str(row.get("audit_id") or ""), "UNKNOWN")}
        for row in rows
    )
