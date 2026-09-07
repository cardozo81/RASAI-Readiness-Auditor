"""Post-run collection coverage for the interactive console."""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import sqlite3


@dataclass(frozen=True, slots=True)
class CollectionCoverage:
    web_enabled: bool
    web_status: str
    web_reason: str
    pagespeed_attempts: int
    pagespeed_successes: int
    crux_attempts: int
    crux_successes: int
    accessibility_requested: bool
    accessibility_obtained: int
    accessibility_contexts: int
    accessibility_reason: str


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
            observations = list(db.execute("SELECT accessibility_score,pagespeed_artifact_reference,error_summary FROM web_performance_observations").fetchall())
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
    return CollectionCoverage(
        web_enabled=bool(run["enabled"]),
        web_status=str(run["status"]),
        web_reason=str(run["reason"] or ""),
        pagespeed_attempts=len(psi),
        pagespeed_successes=sum(str(row["status"]) == "SUCCESS" for row in psi),
        crux_attempts=len(crux),
        crux_successes=sum(str(row["status"]) == "SUCCESS" for row in crux),
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
