"""Comparability helpers over immutable AUD evidence and the analytical index."""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path
import hashlib
import json
import sqlite3
from typing import Any


def annotate_score_url_universes(
    index_path: Path,
    rows: tuple[dict[str, Any], ...],
) -> tuple[dict[str, Any], ...]:
    """Attach a stable URL-set fingerprint to audit-level score rows."""
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


def _lineage_from_database(database: Path, audit_id: str) -> dict[str, Any]:
    if not database.is_file():
        return {}
    connection = sqlite3.connect(f"file:{database.resolve().as_posix()}?mode=ro", uri=True, timeout=1.0)
    connection.row_factory = sqlite3.Row
    try:
        exists = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='audit_execution_configurations'"
        ).fetchone()
        if not exists:
            return {}
        row = connection.execute(
            """SELECT configuration_kind,configuration_hash,source_audit_id,
                      changed_fields_json,execution_series_id
               FROM audit_execution_configurations WHERE audit_id=?""",
            (audit_id,),
        ).fetchone()
        if row is None:
            return {}
        try:
            changed = json.loads(str(row["changed_fields_json"] or "[]"))
        except json.JSONDecodeError:
            changed = []
        return {
            "configuration_kind": str(row["configuration_kind"] or "") or None,
            "configuration_hash": str(row["configuration_hash"] or "") or None,
            "configuration_source_audit_id": str(row["source_audit_id"] or "") or None,
            "execution_series_id": str(row["execution_series_id"] or "") or None,
            "configuration_changed_fields": tuple(
                str(item) for item in changed if isinstance(item, str)
            ),
        }
    finally:
        connection.close()


def annotate_audit_configurations(
    audits_root: Path,
    audits: tuple[dict[str, Any], ...],
) -> tuple[dict[str, Any], ...]:
    """Attach configuration lineage without making the rebuildable index authoritative."""
    output: list[dict[str, Any]] = []
    for audit in audits:
        audit_id = str(audit.get("audit_id") or "")
        relative = str(audit.get("db_path") or "")
        database = Path(relative)
        if not database.is_absolute():
            database = audits_root / database
        try:
            lineage = _lineage_from_database(database, audit_id)
        except sqlite3.Error:
            lineage = {}
        output.append({**audit, **lineage})
    return tuple(output)


def _selected_pair(
    ordered: list[dict[str, Any]],
    *,
    comparison_mode: str,
    baseline_audit_id: str | None,
    current_audit_id: str | None,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    if comparison_mode == "MANUAL":
        by_id = {str(row.get("audit_id") or ""): row for row in ordered}
        return (
            by_id.get(str(baseline_audit_id or "")),
            by_id.get(str(current_audit_id or "")),
        )
    if len(ordered) < 2:
        return None, None
    if comparison_mode == "LATEST_PREVIOUS":
        return ordered[-2], ordered[-1]
    return ordered[0], ordered[-1]


def configuration_comparability(
    audits: tuple[dict[str, Any], ...],
    *,
    comparison_mode: str = "FIRST_LAST",
    baseline_audit_id: str | None = None,
    current_audit_id: str | None = None,
) -> dict[str, Any]:
    """Summarize methodological comparability without changing any metric value."""
    with_snapshot = [row for row in audits if row.get("configuration_hash")]
    missing = len(audits) - len(with_snapshot)
    by_series: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in with_snapshot:
        series = str(row.get("execution_series_id") or "")
        if series:
            by_series[series].append(row)

    repeated = {series: rows for series, rows in by_series.items() if len(rows) >= 2}
    exact_series: list[str] = []
    partial_series: list[str] = []
    for series, rows in repeated.items():
        hashes = {str(row.get("configuration_hash") or "") for row in rows}
        if len(hashes) == 1:
            exact_series.append(series)
        else:
            partial_series.append(series)

    ordered = sorted(
        audits,
        key=lambda row: (str(row.get("event_time") or ""), str(row.get("audit_id") or "")),
    )
    baseline, current = _selected_pair(
        ordered,
        comparison_mode=comparison_mode,
        baseline_audit_id=baseline_audit_id,
        current_audit_id=current_audit_id,
    )
    pair_status = "INSUFFICIENT_DATA"
    selected_baseline_id = str(baseline.get("audit_id") or "") if baseline else None
    selected_current_id = str(current.get("audit_id") or "") if current else None
    altered_fields: set[str] = set()
    if baseline is not None and current is not None:
        baseline_hash = str(baseline.get("configuration_hash") or "")
        current_hash = str(current.get("configuration_hash") or "")
        if baseline_hash and current_hash:
            same_hash = baseline_hash == current_hash
            same_series = (
                bool(baseline.get("execution_series_id"))
                and baseline.get("execution_series_id") == current.get("execution_series_id")
            )
            if same_series and same_hash:
                pair_status = "EXACT"
            elif same_series:
                pair_status = "PARTIAL"
                altered_fields.update(
                    str(item) for item in baseline.get("configuration_changed_fields") or ()
                )
                altered_fields.update(
                    str(item) for item in current.get("configuration_changed_fields") or ()
                )
            elif same_hash:
                pair_status = "EQUIVALENT_WITHOUT_LINEAGE"
            else:
                pair_status = "UNRELATED"

    return {
        "audits": len(audits),
        "with_snapshot": len(with_snapshot),
        "without_snapshot": missing,
        "repeated_series": len(repeated),
        "exact_series": len(exact_series),
        "partial_series": len(partial_series),
        "comparison_mode": comparison_mode,
        "pair_status": pair_status,
        "baseline_audit_id": selected_baseline_id,
        "current_audit_id": selected_current_id,
        "altered_fields": sorted(altered_fields),
    }
