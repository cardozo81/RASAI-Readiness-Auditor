"""Post-run collection coverage for the interactive console."""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import sqlite3

from rasai.secret_safety import redact_text


@dataclass(frozen=True, slots=True)
class CollectionCoverage:
    web_enabled: bool
    web_status: str
    web_reason: str
    pagespeed_attempts: int
    pagespeed_successes: int
    crux_attempts: int
    crux_successes: int
    crux_via_pagespeed: int
    accessibility_requested: bool
    accessibility_obtained: int
    accessibility_contexts: int
    accessibility_reason: str


@dataclass(frozen=True, slots=True)
class WebPerformanceAttemptDiagnostic:
    service: str
    status: str
    http_status: int | None
    error_code: str | None
    error_message: str | None


def load_web_performance_attempt_diagnostics(
    workspace: Path | None,
    audit_id: str | None = None,
) -> tuple[WebPerformanceAttemptDiagnostic, ...]:
    """Return the latest persisted attempt per M21 external service without probing again."""
    if workspace is None:
        return ()
    database = workspace / "audit.db"
    if not database.is_file():
        return ()
    try:
        db = sqlite3.connect(f"file:{database}?mode=ro", uri=True, timeout=0.5)
        db.row_factory = sqlite3.Row
        try:
            exists = db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='web_performance_attempts'"
            ).fetchone()
            if exists is None:
                return ()
            if audit_id:
                rows = db.execute(
                    """SELECT service,status,http_status,error_code,error_message,created_at
                       FROM web_performance_attempts
                       WHERE audit_id=?
                       ORDER BY created_at DESC,rowid DESC""",
                    (audit_id,),
                ).fetchall()
            else:
                rows = db.execute(
                    """SELECT service,status,http_status,error_code,error_message,created_at
                       FROM web_performance_attempts
                       ORDER BY created_at DESC,rowid DESC"""
                ).fetchall()
        finally:
            db.close()
    except sqlite3.Error:
        return ()

    latest: dict[str, WebPerformanceAttemptDiagnostic] = {}
    for row in rows:
        service = str(row["service"] or "").upper()
        if not service or service in latest:
            continue
        message = str(row["error_message"] or "").strip()
        latest[service] = WebPerformanceAttemptDiagnostic(
            service=service,
            status=str(row["status"] or "UNKNOWN").upper(),
            http_status=int(row["http_status"]) if row["http_status"] is not None else None,
            error_code=str(row["error_code"] or "").strip() or None,
            error_message=redact_text(message) if message else None,
        )

    order = {"PAGESPEED_INSIGHTS": 0, "CRUX_API": 1}
    return tuple(
        sorted(latest.values(), key=lambda item: (order.get(item.service, 99), item.service))
    )


def load_collection_coverage(workspace: Path | None) -> CollectionCoverage | None:
    if workspace is None:
        return None
    database = workspace / "audit.db"
    if not database.is_file():
        return None
    try:
        db = sqlite3.connect(f"file:{database}?mode=ro", uri=True, timeout=0.5)
        db.row_factory = sqlite3.Row
        try:
            run = db.execute("SELECT * FROM web_performance_runs ORDER BY updated_at DESC LIMIT 1").fetchone()
            if run is None:
                return None
            attempts = list(db.execute("SELECT service,status FROM web_performance_attempts").fetchall())
            observations = list(db.execute("SELECT * FROM web_performance_observations").fetchall())
        finally:
            db.close()
    except sqlite3.Error:
        return None

    categories = _json_list(run["categories"])
    a11y_requested = bool(run["enabled"]) and "accessibility" in categories
    a11y_obtained = sum(
        row["accessibility_score"] is not None and bool(row["pagespeed_artifact_reference"])
        for row in observations
    )
    errors = sorted({str(row["error_summary"]) for row in observations if row["error_summary"]})
    if not bool(run["enabled"]):
        a11y_reason = "coleta Web Performance desabilitada"
    elif not a11y_requested:
        a11y_reason = "categoria accessibility não solicitada ao Lighthouse"
    elif a11y_obtained == len(observations) and observations:
        a11y_reason = "categoria/score Lighthouse obtido em todos os contextos"
    elif errors:
        a11y_reason = "; ".join(errors[:2])
    else:
        a11y_reason = "PageSpeed/Lighthouse não forneceu artifact/categoria em todos os contextos"

    psi = [row for row in attempts if str(row["service"]).upper() == "PAGESPEED_INSIGHTS"]
    crux = [row for row in attempts if str(row["service"]).upper() == "CRUX_API"]
    crux_via_pagespeed = sum(
        str(row["field_source"] or "").upper() == "PAGESPEED_CRUX"
        for row in observations
        if "field_source" in row.keys()
    )
    return CollectionCoverage(
        web_enabled=bool(run["enabled"]),
        web_status=str(run["status"]),
        web_reason=str(run["reason"] or ""),
        pagespeed_attempts=len(psi),
        pagespeed_successes=sum(str(row["status"]) == "SUCCESS" for row in psi),
        crux_attempts=len(crux),
        crux_successes=sum(str(row["status"]) == "SUCCESS" for row in crux),
        crux_via_pagespeed=crux_via_pagespeed,
        accessibility_requested=a11y_requested,
        accessibility_obtained=a11y_obtained,
        accessibility_contexts=len(observations),
        accessibility_reason=a11y_reason,
    )


def _json_list(value) -> list[str]:
    if isinstance(value, list):
        return [str(item).casefold() for item in value]
    if not value:
        return []
    try:
        parsed = json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
    return [str(item).casefold() for item in parsed] if isinstance(parsed, list) else []
