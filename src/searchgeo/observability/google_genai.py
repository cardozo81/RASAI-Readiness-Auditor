"""Import-first Google Generative AI Search Console observations.

The public product surface is export-driven here: RASAi does not presume a
dedicated API endpoint. Only fields present in the supplied export are stored.
"""
from __future__ import annotations

import csv
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import re
import sqlite3
from typing import Any
from urllib.parse import urlsplit

from .store import ObservabilityStore, new_dataset

SOURCE_PERFORMANCE = "GOOGLE_SEARCH_CONSOLE_GENERATIVE_AI_PERFORMANCE_EXPORT"
SOURCE_CONTROL = "GOOGLE_SEARCH_CONSOLE_GENERATIVE_AI_CONTROL"


def import_google_genai_performance_csv(
    *,
    audit_workspace: str | Path,
    path: str | Path,
    surface: str = "search",
) -> str:
    workspace = Path(audit_workspace)
    source_path = Path(path)
    raw = source_path.read_bytes()
    text = raw.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise ValueError("Google GenAI Performance CSV has no header")
    origins = _origins(workspace)
    surface_value = surface.strip().upper()
    if surface_value not in {"SEARCH", "DISCOVER"}:
        raise ValueError("surface must be search or discover")
    source_type = f"{SOURCE_PERFORMANCE}_{surface_value}"
    rows: list[dict[str, Any]] = []
    dates: list[str] = []
    for index, source_row in enumerate(reader, 1):
        normalized = {_header(key): value for key, value in source_row.items() if key is not None}
        url = _pick(normalized, "page", "url", "pagina", "landingpage")
        if url:
            _same_origin(url, origins, f"row {index} URL")
        observed_date = _date(_pick(normalized, "date", "data"))
        if observed_date:
            dates.append(observed_date)
        raw_impressions = _pick(normalized, "impressions", "impressoes")
        impressions, suppressed = _impressions(raw_impressions)
        rows.append(
            {
                "record_id": f"GOOGLE-GENAI-{index:08d}",
                "source": source_type,
                "observed_date": observed_date,
                "query_text": None,
                "url": url,
                "device": _pick(normalized, "device", "dispositivo"),
                "country": _pick(normalized, "country", "pais", "countrycode"),
                "surface": f"GENAI_{surface_value}",
                "clicks": None,
                "impressions": impressions,
                "ctr": None,
                "position": None,
                "metadata": {
                    "raw": source_row,
                    "suppressed_or_rounded_token": suppressed,
                    "zero_semantics": "EXPORT_ZERO_MAY_INCLUDE_SUPPRESSED_OR_ROUNDED_VALUES",
                },
            }
        )
    if not rows:
        raise ValueError("Google GenAI Performance CSV contains no data rows")
    digest = hashlib.sha256(raw + surface_value.encode("ascii")).hexdigest()
    dataset_id = f"OBS-{digest[:16].upper()}"
    with ObservabilityStore(workspace) as store:
        artifact_path = store.artifacts / f"google-genai-performance-{surface_value.casefold()}-{digest[:16]}.csv"
        if not artifact_path.exists() or artifact_path.read_bytes() != raw:
            artifact_path.write_bytes(raw)
        dataset = new_dataset(
            dataset_id=dataset_id,
            source_type=source_type,
            capture_method="NORMALIZED_EXPORT",
            artifact_path=artifact_path.relative_to(store.workspace).as_posix(),
            artifact_sha256=hashlib.sha256(raw).hexdigest(),
            period_start=min(dates, default=None),
            period_end=max(dates, default=None),
            metadata={
                "surface": surface_value,
                "rows": len(rows),
                "metrics": ["impressions"],
                "unsupported_not_invented": ["clicks", "ctr", "position", "query", "citation_count"],
                "zero_semantics": "A zero in an exported file is not independently interpreted as proof of zero visibility.",
            },
        )
        store.replace_dataset_rows(dataset, search_rows=rows)
    return dataset_id


def persist_google_genai_control(
    *,
    audit_workspace: str | Path,
    state: str,
    source_label: str = "MANUAL_SEARCH_CONSOLE_OBSERVATION",
    observed_at: str | None = None,
) -> str:
    workspace = Path(audit_workspace)
    normalized = state.strip().upper()
    if normalized not in {"INCLUDE", "EXCLUDE", "INHERIT"}:
        raise ValueError("state must be INCLUDE, EXCLUDE or INHERIT")
    timestamp = observed_at or datetime.now(timezone.utc).isoformat()
    payload = {
        "format_version": "RASAI-GOOGLE-GENAI-CONTROL-001",
        "source": SOURCE_CONTROL,
        "capture_method": source_label,
        "state": normalized,
        "observed_at": timestamp,
        "scoring_impact": "NONE",
    }
    raw = (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    digest = hashlib.sha256(raw).hexdigest()
    dataset_id = f"OBS-{digest[:16].upper()}"
    with ObservabilityStore(workspace) as store:
        artifact_path = store.artifacts / f"google-genai-control-{digest[:16]}.json"
        artifact_path.write_bytes(raw)
        dataset = new_dataset(
            dataset_id=dataset_id,
            source_type=SOURCE_CONTROL,
            capture_method=source_label,
            artifact_path=artifact_path.relative_to(store.workspace).as_posix(),
            artifact_sha256=digest,
            metadata={"state": normalized, "observed_at": timestamp, "scoring_impact": "NONE"},
        )
        store.replace_dataset_rows(dataset)
    return dataset_id


def _origins(workspace: Path) -> set[str]:
    database = workspace / "audit.db"
    connection = sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)
    connection.execute("PRAGMA query_only=ON")
    try:
        return {
            str(row[0]).rstrip("/")
            for row in connection.execute("SELECT DISTINCT normalized_origin FROM audit_targets")
            if row[0]
        }
    finally:
        connection.close()


def _same_origin(url: str, origins: set[str], field: str) -> None:
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError(f"{field} must be an absolute HTTP(S) URL")
    origin = f"{parsed.scheme.lower()}://{parsed.hostname.lower()}" + (f":{parsed.port}" if parsed.port else "")
    if origin.casefold() not in {item.casefold() for item in origins}:
        raise ValueError(f"{field} is outside audited origin: {url}")


def _header(value: str) -> str:
    return "".join(ch for ch in value.casefold().strip() if ch.isalnum())


def _pick(row: dict[str, str], *names: str) -> str | None:
    for name in names:
        value = row.get(_header(name))
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def _date(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value[:10]).date().isoformat()
    except ValueError as exc:
        raise ValueError(f"invalid ISO date: {value}") from exc


def _impressions(value: str | None) -> tuple[float | None, bool]:
    if value is None or value == "":
        return None, False
    text = str(value).strip()
    if text in {"~", "-", "—"}:
        return 0.0, True
    compact = text.replace(" ", "")
    if re.fullmatch(r"\d{1,3}(?:[.,]\d{3})+", compact):
        compact = compact.replace(",", "").replace(".", "")
    elif "," in compact and "." not in compact:
        compact = compact.replace(",", ".")
    try:
        return float(compact), False
    except ValueError as exc:
        raise ValueError(f"invalid impressions value: {value}") from exc
