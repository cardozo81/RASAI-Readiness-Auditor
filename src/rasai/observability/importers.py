"""Import-first adapters for observed search data without a documented API path."""
from __future__ import annotations

import csv
from datetime import date, datetime
import hashlib
import io
import json
from pathlib import Path
import re
import sqlite3
from typing import Any
from urllib.parse import urlsplit

from .store import ObservabilityStore, new_dataset

IMPORT_FORMAT = "RASAI-OBS-IMPORT-001"
SOURCE_BING_EXPORT = "BING_WEBMASTER_TOOLS_SEARCH_PERFORMANCE_EXPORT"


def import_observability_json(*, audit_workspace: str | Path, path: str | Path) -> str:
    source_path = Path(path)
    raw = source_path.read_bytes()
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("observability import must be UTF-8 JSON") from exc
    if not isinstance(payload, dict) or payload.get("format_version") != IMPORT_FORMAT:
        raise ValueError(f"format_version must be {IMPORT_FORMAT}")
    source = payload.get("source") or {}
    if not isinstance(source, dict):
        raise ValueError("source must be an object")
    source_type = str(source.get("type") or "").strip().upper()
    if not source_type:
        raise ValueError("source.type is required")
    capture_method = str(source.get("capture_method") or "NORMALIZED_EXPORT").strip().upper()
    origins = _audit_origins(Path(audit_workspace))
    search_rows = [
        _search_item(item, source_type, origins, index)
        for index, item in enumerate(_list(payload.get("search_performance")), 1)
    ]
    index_rows = [
        _index_item(item, source_type, origins, index)
        for index, item in enumerate(_list(payload.get("index_observations")), 1)
    ]
    crux_rows = [
        _crux_item(item, origins, index)
        for index, item in enumerate(_list(payload.get("crux_history")), 1)
    ]
    if not (search_rows or index_rows or crux_rows):
        raise ValueError("observability import contains no records")
    digest = hashlib.sha256(raw).hexdigest()
    dataset_id = f"OBS-{digest[:16].upper()}"
    with ObservabilityStore(audit_workspace) as store:
        artifact_path = store.artifacts / f"observability-import-{digest[:16]}.json"
        if not artifact_path.exists() or artifact_path.read_bytes() != raw:
            artifact_path.write_bytes(raw)
        dataset = new_dataset(
            dataset_id=dataset_id,
            source_type=source_type,
            capture_method=capture_method,
            artifact_path=artifact_path.relative_to(store.workspace).as_posix(),
            artifact_sha256=digest,
            period_start=_optional_date(source.get("period_start")),
            period_end=_optional_date(source.get("period_end")),
            metadata=_metadata(source.get("metadata"), "source.metadata"),
        )
        _validate_period(dataset.period_start, dataset.period_end, "source period")
        store.replace_dataset_rows(dataset, search_rows=search_rows, index_rows=index_rows, crux_rows=crux_rows)
    return dataset_id


def import_bing_search_performance_csv(
    *, audit_workspace: str | Path, path: str | Path, surface: str | None = None,
) -> str:
    source_path = Path(path)
    raw = source_path.read_bytes()
    text = raw.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise ValueError("Bing Search Performance CSV has no header")
    origins = _audit_origins(Path(audit_workspace))
    surface_override = str(surface).strip() if surface is not None and str(surface).strip() else None
    source_type = (
        SOURCE_BING_EXPORT
        if surface_override is None
        else f"{SOURCE_BING_EXPORT}_{_source_suffix(surface_override)}"
    )
    rows: list[dict[str, Any]] = []
    dates: list[str] = []
    for index, source_row in enumerate(reader, 1):
        row = {_header(key): value for key, value in source_row.items() if key is not None}
        url = _pick(row, "page", "url", "servedpage", "pagina")
        if url:
            _same_origin(url, origins, f"row {index} URL")
        observed_date = _date_or_none(_pick(row, "date", "data"))
        if observed_date:
            dates.append(observed_date)
        row_surface = surface_override or _pick(row, "source", "traffic source", "trafficsource", "origem", "surface")
        rows.append(
            {
                "record_id": f"BING-EXP-{index:08d}",
                "source": source_type,
                "observed_date": observed_date,
                "query_text": _pick(row, "query", "keyword", "searchterm", "consulta", "palavrachave"),
                "url": url,
                "device": _pick(row, "device", "dispositivo"),
                "country": _pick(row, "country", "pais"),
                "surface": row_surface,
                "clicks": _number_or_none(_pick(row, "clicks", "cliques")),
                "impressions": _number_or_none(_pick(row, "impressions", "impressoes")),
                "ctr": _ratio_or_none(_pick(row, "ctr", "avgctr", "averagetr")),
                "position": _number_or_none(_pick(row, "position", "avgposition", "averageposition", "posicao")),
                "metadata": {"raw": source_row, "surface_override": surface_override},
            }
        )
    if not rows:
        raise ValueError("Bing Search Performance CSV contains no data rows")
    raw_digest = hashlib.sha256(raw).hexdigest()
    identity_material = raw if surface_override is None else raw + b"\0surface=" + surface_override.casefold().encode("utf-8")
    identity_digest = hashlib.sha256(identity_material).hexdigest()
    dataset_id = f"OBS-{identity_digest[:16].upper()}"
    with ObservabilityStore(audit_workspace) as store:
        artifact_path = store.artifacts / f"bing-search-performance-{raw_digest[:16]}.csv"
        if not artifact_path.exists() or artifact_path.read_bytes() != raw:
            artifact_path.write_bytes(raw)
        dataset = new_dataset(
            dataset_id=dataset_id,
            source_type=source_type,
            capture_method="NORMALIZED_EXPORT",
            artifact_path=artifact_path.relative_to(store.workspace).as_posix(),
            artifact_sha256=raw_digest,
            period_start=min(dates, default=None),
            period_end=max(dates, default=None),
            metadata={
                "rows": len(rows),
                "surface_override": surface_override,
                "identity_includes_surface_override": surface_override is not None,
            },
        )
        store.replace_dataset_rows(dataset, search_rows=rows)
    return dataset_id


def _search_item(raw: Any, source_type: str, origins: set[str], index: int) -> dict[str, Any]:
    item = _object(raw, f"search_performance[{index}]")
    url = _optional_text(item.get("url"))
    if url:
        _same_origin(url, origins, f"search_performance[{index}].url")
    return {
        "record_id": f"IMP-SP-{index:08d}", "source": source_type,
        "observed_date": _date_or_none(item.get("date")), "query_text": _optional_text(item.get("query")),
        "url": url, "device": _optional_text(item.get("device")), "country": _optional_text(item.get("country")),
        "surface": _optional_text(item.get("surface")), "clicks": _number_or_none(item.get("clicks")),
        "impressions": _number_or_none(item.get("impressions")), "ctr": _ratio_or_none(item.get("ctr")),
        "position": _number_or_none(item.get("position")),
        "metadata": _metadata(item.get("metadata"), f"search_performance[{index}].metadata"),
    }


def _index_item(raw: Any, source_type: str, origins: set[str], index: int) -> dict[str, Any]:
    item = _object(raw, f"index_observations[{index}]")
    url = str(item.get("url") or "").strip()
    _same_origin(url, origins, f"index_observations[{index}].url")
    return {
        "record_id": f"IMP-IDX-{index:08d}", "source": source_type, "url": url,
        "verdict": _optional_text(item.get("verdict")), "coverage_state": _optional_text(item.get("coverage_state")),
        "indexing_state": _optional_text(item.get("indexing_state")), "robots_txt_state": _optional_text(item.get("robots_txt_state")),
        "page_fetch_state": _optional_text(item.get("page_fetch_state")), "user_canonical": _optional_text(item.get("user_canonical")),
        "selected_canonical": _optional_text(item.get("selected_canonical")), "last_crawl_time": _optional_text(item.get("last_crawl_time")),
        "crawled_as": _optional_text(item.get("crawled_as")), "referring_urls": tuple(item.get("referring_urls") or ()),
        "sitemap_urls": tuple(item.get("sitemap_urls") or ()),
        "metadata": _metadata(item.get("metadata"), f"index_observations[{index}].metadata"),
    }


def _crux_item(raw: Any, origins: set[str], index: int) -> dict[str, Any]:
    item = _object(raw, f"crux_history[{index}]")
    target = str(item.get("target") or "").strip()
    scope = str(item.get("target_scope") or "URL").strip().upper()
    if scope not in {"URL", "ORIGIN"}:
        raise ValueError(f"crux_history[{index}].target_scope must be URL or ORIGIN")
    _same_origin(target, origins, f"crux_history[{index}].target")
    parsed = urlsplit(target)
    if scope == "ORIGIN" and ((parsed.path not in {"", "/"}) or parsed.query or parsed.fragment):
        raise ValueError(f"crux_history[{index}].target must be an origin when target_scope=ORIGIN")
    metric = str(item.get("metric") or "").strip()
    if not metric:
        raise ValueError(f"crux_history[{index}].metric is required")
    period_start = _date_or_none(item.get("period_start"))
    period_end = _date_or_none(item.get("period_end"))
    _validate_period(period_start, period_end, f"crux_history[{index}] period")
    return {
        "record_id": f"IMP-CX-{index:08d}", "target": target,
        "target_scope": scope, "form_factor": _optional_text(item.get("form_factor")),
        "metric": metric, "period_start": period_start,
        "period_end": period_end, "p75": _number_or_none(item.get("p75")),
        "good_density": _number_or_none(item.get("good_density")), "needs_improvement_density": _number_or_none(item.get("needs_improvement_density")),
        "poor_density": _number_or_none(item.get("poor_density")),
        "metadata": _metadata(item.get("metadata"), f"crux_history[{index}].metadata"),
    }


def _audit_origins(workspace: Path) -> set[str]:
    database = workspace / "audit.db"
    uri = database.resolve().as_uri() + "?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    connection.execute("PRAGMA query_only=ON")
    try:
        origins = {
            str(row[0]).rstrip("/")
            for row in connection.execute("SELECT DISTINCT normalized_origin FROM audit_targets")
            if row[0]
        }
    finally:
        connection.close()
    if not origins:
        raise ValueError("audit contains no normalized origin for observability scoping")
    return origins


def _same_origin(url: str, origins: set[str], field: str) -> None:
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError(f"{field} must be an absolute HTTP(S) URL")
    origin = f"{parsed.scheme.lower()}://{parsed.hostname.lower()}" + (f":{parsed.port}" if parsed.port else "")
    normalized = {value.casefold() for value in origins}
    if origin.casefold() not in normalized:
        raise ValueError(f"{field} is outside audited origin: {url}")


def _list(value: Any) -> list[Any]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("observation arrays must be JSON lists")
    return value


def _object(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{field} must be an object")
    return value


def _metadata(value: Any, field: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"{field} must be an object")
    return value


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_date(value: Any) -> str | None:
    return _date_or_none(value)


def _date_or_none(value: Any) -> str | None:
    text = _optional_text(value)
    if not text:
        return None
    try:
        return datetime.fromisoformat(text[:10]).date().isoformat()
    except ValueError:
        raise ValueError(f"invalid ISO date: {text}")


def _validate_period(start: str | None, end: str | None, field: str) -> None:
    if not start or not end:
        return
    if date.fromisoformat(start) > date.fromisoformat(end):
        raise ValueError(f"{field} start cannot be after end")


def _number_or_none(value: Any) -> float | None:
    text = _optional_text(value)
    if text is None:
        return None
    normalized = text.replace("%", "").replace(",", ".") if isinstance(value, str) else value
    try:
        return float(normalized)
    except (TypeError, ValueError):
        return None


def _ratio_or_none(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, str) and "%" in value:
        number = _number_or_none(value)
        return None if number is None else number / 100.0
    number = _number_or_none(value)
    if number is not None and 1.0 < number <= 100.0:
        return number / 100.0
    return number


def _source_suffix(value: str) -> str:
    suffix = re.sub(r"[^A-Z0-9]+", "_", value.upper()).strip("_")
    return suffix or "SURFACE"


def _header(value: str) -> str:
    return "".join(ch for ch in value.casefold().strip() if ch.isalnum() or ch == " ").replace(" ", "")


def _pick(row: dict[str, str], *names: str) -> str | None:
    for name in names:
        value = row.get(_header(name))
        if value is not None and str(value).strip():
            return str(value).strip()
    return None
