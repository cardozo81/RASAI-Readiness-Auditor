"""Bounded read-only collectors for external analytics and public Web history.

The collectors in this module never write to ``audit.db`` and never affect
SARI-001/SCORE-GEO-004.  They persist normalized observations only in the
rebuildable ``artifacts/observability/observability.db`` sidecar plus sanitized source artifacts.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from rasai.observability.store import observability_database_path
import sqlite3
import time
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

from .store import ObservabilityStore, new_dataset

CLARITY_ENDPOINT = "https://www.clarity.ms/export-data/api/v1/project-live-insights"
COMMON_CRAWL_COLLECTIONS_ENDPOINT = "https://index.commoncrawl.org/collinfo.json"
SOURCE_CLARITY = "MICROSOFT_CLARITY_LIVE_INSIGHTS"
SOURCE_COMMON_CRAWL = "COMMON_CRAWL_CDX_HISTORY"

JsonOpener = Callable[..., Any]

_EXTENSION_SCHEMA = """
CREATE TABLE IF NOT EXISTS behavioral_observations (
    record_id TEXT NOT NULL,
    dataset_id TEXT NOT NULL REFERENCES datasets(dataset_id) ON DELETE CASCADE,
    metric_name TEXT NOT NULL,
    normalized_url TEXT,
    device TEXT,
    dimensions_json TEXT NOT NULL,
    values_json TEXT NOT NULL,
    PRIMARY KEY(dataset_id,record_id)
);
CREATE INDEX IF NOT EXISTS idx_obs_behavior_dataset
    ON behavioral_observations(dataset_id,metric_name,normalized_url,device);
CREATE TABLE IF NOT EXISTS web_archive_observations (
    record_id TEXT NOT NULL,
    dataset_id TEXT NOT NULL REFERENCES datasets(dataset_id) ON DELETE CASCADE,
    collection TEXT NOT NULL,
    target_url TEXT NOT NULL,
    captured_at TEXT,
    status TEXT,
    mime TEXT,
    digest TEXT,
    warc_filename TEXT,
    warc_offset INTEGER,
    warc_length INTEGER,
    metadata_json TEXT NOT NULL,
    PRIMARY KEY(dataset_id,record_id)
);
CREATE INDEX IF NOT EXISTS idx_obs_archive_dataset
    ON web_archive_observations(dataset_id,target_url,collection,captured_at);
"""


def ensure_extension_schema(connection: sqlite3.Connection) -> None:
    with connection:
        connection.executescript(_EXTENSION_SCHEMA)


def behavioral_rows(audit_workspace: str | Path) -> list[dict[str, Any]]:
    path = observability_database_path(audit_workspace)
    if not path.is_file():
        return []
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    try:
        ensure_extension_schema(connection)
        return [dict(row) for row in connection.execute(
            """SELECT * FROM behavioral_observations
               ORDER BY metric_name,COALESCE(normalized_url,''),COALESCE(device,''),dataset_id,record_id"""
        )]
    finally:
        connection.close()


def archive_rows(audit_workspace: str | Path) -> list[dict[str, Any]]:
    path = observability_database_path(audit_workspace)
    if not path.is_file():
        return []
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    try:
        ensure_extension_schema(connection)
        return [dict(row) for row in connection.execute(
            """SELECT * FROM web_archive_observations
               ORDER BY target_url,captured_at,collection,dataset_id,record_id"""
        )]
    finally:
        connection.close()


def collect_clarity_insights(
    *,
    audit_workspace: str | Path,
    api_token: str,
    days: int = 1,
    dimensions: tuple[str, ...] = ("URL", "Device"),
    timeout: float = 30.0,
    opener: JsonOpener = urlopen,
) -> str:
    """Collect aggregate Microsoft Clarity Data Export API observations.

    Only dashboard aggregates are persisted.  Session replay, visitor/session IDs,
    keystrokes, form values and raw interaction streams are outside this contract.
    When the URL dimension is available, rows are restricted to the audited origin.
    """
    workspace = Path(audit_workspace)
    token = str(api_token).strip()
    if not token:
        raise ValueError("Microsoft Clarity API token is required")
    if int(days) not in {1, 2, 3}:
        raise ValueError("Microsoft Clarity days must be 1, 2 or 3")
    dims = tuple(str(item).strip() for item in dimensions if str(item).strip())
    if not dims:
        dims = ("URL", "Device")
    if len(dims) > 3:
        raise ValueError("Microsoft Clarity accepts at most three dimensions")

    parameters: list[tuple[str, str]] = [("numOfDays", str(int(days)))]
    parameters.extend((f"dimension{index}", value) for index, value in enumerate(dims, 1))
    request = Request(
        CLARITY_ENDPOINT + "?" + urlencode(parameters),
        method="GET",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "RASAi/Clarity-Observability",
        },
    )
    payload = _read_json(request, timeout=timeout, opener=opener, provider="Microsoft Clarity")
    if not isinstance(payload, list):
        raise ValueError("Microsoft Clarity response root must be a list")

    allowed_origins = {value.casefold() for value in _audit_origins(workspace)}
    normalized: list[dict[str, Any]] = []
    sanitized_response: list[dict[str, Any]] = []
    excluded_out_of_scope = 0
    counter = 0
    for block in payload:
        if not isinstance(block, dict):
            continue
        metric_name = str(block.get("metricName") or "UNKNOWN").strip() or "UNKNOWN"
        information = block.get("information") or []
        if not isinstance(information, list):
            continue
        sanitized_information: list[dict[str, Any]] = []
        for raw in information:
            if not isinstance(raw, dict):
                continue
            row = {str(key): value for key, value in raw.items()}
            url_value = _casefold_lookup(row, "URL")
            normalized_url = _absolute_http_url(url_value) if url_value else None
            if normalized_url is not None and _origin(normalized_url).casefold() not in allowed_origins:
                excluded_out_of_scope += 1
                continue
            dimension_values: dict[str, Any] = {}
            dimension_keys = {item.casefold() for item in dims}
            for dimension in dims:
                value = _casefold_lookup(row, dimension)
                if value is not None:
                    dimension_values[dimension] = value
            values = {
                key: value
                for key, value in row.items()
                if key.casefold() not in dimension_keys
            }
            counter += 1
            normalized.append(
                {
                    "record_id": f"CLARITY-{counter:08d}",
                    "metric_name": metric_name,
                    "normalized_url": normalized_url,
                    "device": str(_casefold_lookup(row, "Device") or "").strip() or None,
                    "dimensions": dimension_values,
                    "values": values,
                }
            )
            sanitized_information.append(row)
        sanitized_response.append({"metricName": metric_name, "information": sanitized_information})

    artifact = {
        "format_version": "RASAI-CLARITY-001",
        "source": SOURCE_CLARITY,
        "capture_method": "DIRECT_OFFICIAL_API",
        "rolling_window_hours": int(days) * 24,
        "dimensions": list(dims),
        "scope_policy": "AUDITED_ORIGIN_ONLY_WHEN_URL_DIMENSION_PRESENT",
        "response": sanitized_response,
    }
    dataset_id, dataset = _dataset(
        workspace,
        source_type=SOURCE_CLARITY,
        artifact=artifact,
        prefix="clarity",
        metadata={
            "rolling_window_hours": int(days) * 24,
            "dimensions": list(dims),
            "rows": len(normalized),
            "excluded_out_of_scope": excluded_out_of_scope,
            "aggregation_only": True,
            "session_replay_persisted": False,
            "secret_persisted": False,
        },
    )
    with ObservabilityStore(workspace) as store:
        ensure_extension_schema(store.connection)
        store.replace_dataset_rows(dataset)
        with store.connection:
            store.connection.execute("DELETE FROM behavioral_observations WHERE dataset_id=?", (dataset_id,))
            for row in normalized:
                store.connection.execute(
                    """INSERT INTO behavioral_observations(
                        record_id,dataset_id,metric_name,normalized_url,device,dimensions_json,values_json
                    ) VALUES (?,?,?,?,?,?,?)""",
                    (
                        row["record_id"], dataset_id, row["metric_name"], row["normalized_url"], row["device"],
                        _dump(row["dimensions"]), _dump(row["values"]),
                    ),
                )
    return dataset_id


def collect_common_crawl_history(
    *,
    audit_workspace: str | Path,
    max_urls: int = 3,
    collection_count: int = 2,
    timeout: float = 20.0,
    min_interval_seconds: float = 0.5,
    opener: JsonOpener = urlopen,
) -> str:
    """Observe exact audited URLs in recent Common Crawl CDX indexes.

    The collector is credential-free and bounded.  It does not fetch WARC content and
    therefore only establishes historical Common Crawl observations, never Google/Bing
    indexation or current reachability.
    """
    workspace = Path(audit_workspace)
    if max_urls < 0 or max_urls > 25:
        raise ValueError("Common Crawl max_urls must be between 0 and 25")
    if collection_count < 1 or collection_count > 6:
        raise ValueError("Common Crawl collection_count must be between 1 and 6")
    urls = _audit_urls(workspace)
    selected_urls = urls[:max_urls] if max_urls else []

    collection_request = Request(
        COMMON_CRAWL_COLLECTIONS_ENDPOINT,
        method="GET",
        headers={"Accept": "application/json", "User-Agent": _common_crawl_user_agent()},
    )
    collections = _read_json(
        collection_request,
        timeout=timeout,
        opener=opener,
        provider="Common Crawl collections",
    )
    if not isinstance(collections, list):
        raise ValueError("Common Crawl collinfo response root must be a list")
    usable = [
        item for item in collections
        if isinstance(item, dict) and str(item.get("id") or "").strip() and str(item.get("cdx-api") or "").strip()
    ][:collection_count]

    observations: list[dict[str, Any]] = []
    request_count = 0
    counter = 0
    errors: list[str] = []
    error_details: list[dict[str, Any]] = []
    no_capture_details: list[dict[str, Any]] = []
    for collection in usable:
        collection_id = str(collection["id"])
        endpoint = str(collection["cdx-api"])
        for target_url in selected_urls:
            if request_count:
                time.sleep(max(0.0, float(min_interval_seconds)))
            request_count += 1
            query = urlencode({"url": target_url, "output": "json"})
            request = Request(
                endpoint + ("&" if "?" in endpoint else "?") + query,
                method="GET",
                headers={"Accept": "application/x-ndjson, application/json", "User-Agent": _common_crawl_user_agent()},
            )
            try:
                lines = _read_text(request, timeout=timeout, opener=opener, provider="Common Crawl CDX")
            except (OSError, RuntimeError, ValueError) as exc:
                error_type = type(exc).__name__
                message = str(exc).strip()[:500]
                detail = {
                    "collection": collection_id,
                    "target_url": target_url,
                    "endpoint": endpoint,
                    "error_type": error_type,
                    "message": message or None,
                }
                if _common_crawl_no_capture_message(message):
                    # Common Crawl uses HTTP 404 for a valid "no capture in this index"
                    # answer. It is coverage/no-data, not provider/transport failure.
                    no_capture_details.append(detail)
                    continue
                errors.append(f"{collection_id}:{target_url}:{error_type}:{message}" if message else f"{collection_id}:{target_url}:{error_type}")
                error_details.append(detail)
                continue
            for raw_line in lines.splitlines()[:100]:
                raw_line = raw_line.strip()
                if not raw_line:
                    continue
                try:
                    row = json.loads(raw_line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(row, dict):
                    continue
                observed_url = str(row.get("url") or target_url)
                if _origin(observed_url).casefold() not in {value.casefold() for value in _audit_origins(workspace)}:
                    continue
                counter += 1
                observations.append(
                    {
                        "record_id": f"CC-{counter:08d}",
                        "collection": collection_id,
                        "target_url": target_url,
                        "captured_at": _cc_timestamp(row.get("timestamp")),
                        "status": str(row.get("status") or "") or None,
                        "mime": str(row.get("mime") or "") or None,
                        "digest": str(row.get("digest") or "") or None,
                        "warc_filename": str(row.get("filename") or "") or None,
                        "warc_offset": _int_or_none(row.get("offset")),
                        "warc_length": _int_or_none(row.get("length")),
                        "metadata": {
                            "urlkey": row.get("urlkey"),
                            "redirect": row.get("redirect"),
                            "languages": row.get("languages"),
                            "encoding": row.get("encoding"),
                        },
                    }
                )

    artifact = {
        "format_version": "RASAI-COMMON-CRAWL-001",
        "source": SOURCE_COMMON_CRAWL,
        "capture_method": "DIRECT_PUBLIC_INDEX_API",
        "collections": [str(item["id"]) for item in usable],
        "requested_urls": selected_urls,
        "requests": request_count,
        "errors": errors,
        "error_details": error_details,
        "no_capture_details": no_capture_details,
        "observations": observations,
    }
    dates = [row["captured_at"] for row in observations if row["captured_at"]]
    dataset_id, dataset = _dataset(
        workspace,
        source_type=SOURCE_COMMON_CRAWL,
        artifact=artifact,
        prefix="common-crawl",
        period_start=min(dates, default=None),
        period_end=max(dates, default=None),
        metadata={
            "requested_urls": len(selected_urls),
            "collection_count": len(usable),
            "requests": request_count,
            "rows": len(observations),
            "errors": len(errors),
            "no_captures": len(no_capture_details),
            "scope": "URL",
            "device_dimension": False,
            "warc_content_fetched": False,
            "credential_required": False,
        },
    )
    with ObservabilityStore(workspace) as store:
        ensure_extension_schema(store.connection)
        store.replace_dataset_rows(dataset)
        with store.connection:
            store.connection.execute("DELETE FROM web_archive_observations WHERE dataset_id=?", (dataset_id,))
            for row in observations:
                store.connection.execute(
                    """INSERT INTO web_archive_observations(
                        record_id,dataset_id,collection,target_url,captured_at,status,mime,digest,
                        warc_filename,warc_offset,warc_length,metadata_json
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        row["record_id"], dataset_id, row["collection"], row["target_url"], row["captured_at"],
                        row["status"], row["mime"], row["digest"], row["warc_filename"], row["warc_offset"],
                        row["warc_length"], _dump(row["metadata"]),
                    ),
                )
    return dataset_id


def _dataset(
    workspace: Path,
    *,
    source_type: str,
    artifact: dict[str, Any],
    prefix: str,
    metadata: dict[str, Any],
    period_start: str | None = None,
    period_end: str | None = None,
) -> tuple[str, Any]:
    raw = (json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    digest = hashlib.sha256(raw).hexdigest()
    dataset_id = f"OBS-{digest[:16].upper()}"
    artifacts = workspace / "artifacts" / "observability"
    artifacts.mkdir(parents=True, exist_ok=True)
    artifact_path = artifacts / f"{prefix}-{digest[:16]}.json"
    artifact_path.write_bytes(raw)
    dataset = new_dataset(
        dataset_id=dataset_id,
        source_type=source_type,
        capture_method=str(artifact.get("capture_method") or "DIRECT_EXTERNAL_API"),
        artifact_path=artifact_path.relative_to(workspace).as_posix(),
        artifact_sha256=digest,
        period_start=period_start,
        period_end=period_end,
        metadata=metadata,
    )
    return dataset_id, dataset


def _audit_urls(workspace: Path) -> list[str]:
    database = workspace / "audit.db"
    if not database.is_file():
        raise FileNotFoundError(database)
    connection = sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)
    connection.execute("PRAGMA query_only=ON")
    try:
        return [str(row[0]) for row in connection.execute(
            "SELECT normalized_url FROM pages ORDER BY rowid"
        ).fetchall()]
    finally:
        connection.close()


def _audit_origins(workspace: Path) -> set[str]:
    database = workspace / "audit.db"
    if not database.is_file():
        raise FileNotFoundError(database)
    connection = sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)
    connection.execute("PRAGMA query_only=ON")
    try:
        values = {
            str(row[0]).rstrip("/")
            for row in connection.execute("SELECT DISTINCT normalized_origin FROM audit_targets").fetchall()
            if row[0]
        }
    finally:
        connection.close()
    if not values:
        values = {_origin(url) for url in _audit_urls(workspace)}
    return values




def _common_crawl_no_capture_message(value: Any) -> bool:
    """Return True for Common Crawl's valid no-capture response, not transport failure."""
    message = str(value or "").casefold()
    return "404" in message and "no captures found" in message

def _read_json(request: Request, *, timeout: float, opener: JsonOpener, provider: str) -> Any:
    text = _read_text(request, timeout=timeout, opener=opener, provider=provider)
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{provider} returned invalid JSON") from exc


def _read_text(request: Request, *, timeout: float, opener: JsonOpener, provider: str) -> str:
    try:
        response = opener(request, timeout=max(1.0, float(timeout)))
        raw = response.read()
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"{provider} HTTP {exc.code}: {detail}") from exc
    except URLError as exc:
        raise RuntimeError(f"{provider} network error: {exc.reason}") from exc
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"{provider} returned non-UTF-8 data") from exc


def _casefold_lookup(row: dict[str, Any], key: str) -> Any:
    wanted = key.casefold()
    for current, value in row.items():
        if current.casefold() == wanted:
            return value
    return None


def _absolute_http_url(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    parsed = urlsplit(text)
    if parsed.scheme.casefold() not in {"http", "https"} or not parsed.hostname:
        return None
    return text


def _origin(value: str) -> str:
    parsed = urlsplit(str(value))
    if parsed.scheme.casefold() not in {"http", "https"} or not parsed.hostname:
        raise ValueError(f"invalid HTTP(S) URL: {value}")
    default_port = (parsed.scheme.casefold() == "https" and parsed.port == 443) or (
        parsed.scheme.casefold() == "http" and parsed.port == 80
    )
    port = "" if parsed.port is None or default_port else f":{parsed.port}"
    return f"{parsed.scheme.casefold()}://{parsed.hostname.casefold()}{port}"


def _cc_timestamp(value: Any) -> str | None:
    text = str(value or "").strip()
    if len(text) != 14 or not text.isdigit():
        return None
    return f"{text[0:4]}-{text[4:6]}-{text[6:8]}T{text[8:10]}:{text[10:12]}:{text[12:14]}Z"


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _common_crawl_user_agent() -> str:
    return "RASAi-Readiness-Auditor/0.1 (read-only Common Crawl index integration)"
