"""Direct Google Search Console collectors using documented REST APIs.

Authentication is supplied as an OAuth bearer token by the caller. Tokens are
never persisted in RASAI artifacts or the observability sidecar.
"""
from __future__ import annotations

from datetime import date
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from .store import ObservabilityStore, new_dataset

SEARCH_ANALYTICS_ENDPOINT = "https://www.googleapis.com/webmasters/v3/sites/{site}/searchAnalytics/query"
URL_INSPECTION_ENDPOINT = "https://searchconsole.googleapis.com/v1/urlInspection/index:inspect"
SOURCE_SEARCH = "GOOGLE_SEARCH_CONSOLE_SEARCH_ANALYTICS"
SOURCE_APPEARANCE = "GOOGLE_SEARCH_CONSOLE_SEARCH_APPEARANCE"
SOURCE_INSPECTION = "GOOGLE_SEARCH_CONSOLE_URL_INSPECTION"

JsonOpener = Callable[..., Any]


def collect_search_analytics(
    *,
    audit_workspace: str | Path,
    site_url: str,
    access_token: str,
    start_date: str,
    end_date: str,
    dimensions: tuple[str, ...] = ("date", "query", "page", "device", "country"),
    search_type: str = "web",
    row_limit: int = 25_000,
    max_rows: int = 100_000,
    data_state: str = "final",
    surface_dimension: str | None = None,
    timeout: float = 60.0,
    opener: JsonOpener = urlopen,
) -> str:
    _validate_period(start_date, end_date)
    token = access_token.strip()
    if not token:
        raise ValueError("Google Search Console access token is required")
    if surface_dimension is not None and surface_dimension not in dimensions:
        raise ValueError("surface_dimension must be present in dimensions")
    source_type = SOURCE_APPEARANCE if surface_dimension == "searchAppearance" else SOURCE_SEARCH
    max_rows = max(1, int(max_rows))
    page_size = max(1, min(int(row_limit), 25_000, max_rows))
    endpoint = SEARCH_ANALYTICS_ENDPOINT.format(site=quote(site_url, safe=""))
    raw_pages: list[dict[str, Any]] = []
    normalized: list[dict[str, Any]] = []
    start_row = 0
    while start_row < max_rows:
        payload = {
            "startDate": start_date,
            "endDate": end_date,
            "dimensions": list(dimensions),
            "type": search_type,
            "aggregationType": "auto",
            "rowLimit": min(page_size, max_rows - start_row),
            "startRow": start_row,
            "dataState": data_state,
        }
        response = _post_json(endpoint, payload, token, timeout, opener)
        raw_pages.append(response)
        rows = response.get("rows") or []
        if not isinstance(rows, list):
            raise ValueError("Search Console response rows must be a list")
        for offset, row in enumerate(rows):
            if not isinstance(row, dict):
                continue
            keys = row.get("keys") or []
            mapping = {
                dimension: (str(keys[index]) if index < len(keys) else None)
                for index, dimension in enumerate(dimensions)
            }
            observed_surface = mapping.get(surface_dimension) if surface_dimension else None
            normalized.append(
                {
                    "record_id": f"GSC-SA-{start_row + offset + 1:08d}",
                    "source": source_type,
                    "observed_date": mapping.get("date"),
                    "query_text": mapping.get("query"),
                    "url": mapping.get("page"),
                    "device": mapping.get("device"),
                    "country": mapping.get("country"),
                    "surface": observed_surface or search_type,
                    "clicks": row.get("clicks"),
                    "impressions": row.get("impressions"),
                    "ctr": row.get("ctr"),
                    "position": row.get("position"),
                    "metadata": {
                        "dimensions": mapping,
                        "search_type": search_type,
                        "surface_dimension": surface_dimension,
                        "responseAggregationType": response.get("responseAggregationType"),
                    },
                }
            )
        if len(rows) < payload["rowLimit"] or not rows:
            break
        start_row += len(rows)

    artifact = {
        "format_version": "RASAI-GSC-SA-001",
        "source": source_type,
        "site_url": site_url,
        "period_start": start_date,
        "period_end": end_date,
        "dimensions": list(dimensions),
        "type": search_type,
        "data_state": data_state,
        "surface_dimension": surface_dimension,
        "requested_max_rows": max_rows,
        "page_size": page_size,
        "responses": raw_pages,
    }
    return _persist(
        audit_workspace=audit_workspace,
        source_type=source_type,
        capture_method="DIRECT_OFFICIAL_API",
        artifact=artifact,
        period_start=start_date,
        period_end=end_date,
        search_rows=normalized,
        metadata={
            "site_url": site_url,
            "dimensions": list(dimensions),
            "search_type": search_type,
            "surface_dimension": surface_dimension,
            "rows": len(normalized),
            "requested_max_rows": max_rows,
            "page_size": page_size,
            "coverage_note": "Search Analytics may return top rows rather than every row available for the property.",
        },
    )


def collect_url_inspection(
    *,
    audit_workspace: str | Path,
    site_url: str,
    access_token: str,
    urls: tuple[str, ...] | None = None,
    language_code: str = "pt-BR",
    timeout: float = 60.0,
    opener: JsonOpener = urlopen,
) -> str:
    token = access_token.strip()
    if not token:
        raise ValueError("Google Search Console access token is required")
    audit_urls = _audit_urls(Path(audit_workspace))
    requested = tuple(urls) if urls else audit_urls
    unknown = sorted(set(requested) - set(audit_urls))
    if unknown:
        raise ValueError("URL Inspection is restricted to persisted audit URLs: " + ", ".join(unknown[:5]))
    raw: list[dict[str, Any]] = []
    normalized: list[dict[str, Any]] = []
    for index, url in enumerate(requested, 1):
        payload = {"inspectionUrl": url, "siteUrl": site_url, "languageCode": language_code}
        try:
            response = _post_json(URL_INSPECTION_ENDPOINT, payload, token, timeout, opener)
            raw.append({"url": url, "response": response})
            result = response.get("inspectionResult") or {}
            index_status = result.get("indexStatusResult") or {}
            normalized.append(
                {
                    "record_id": f"GSC-UI-{index:08d}",
                    "source": SOURCE_INSPECTION,
                    "url": url,
                    "verdict": index_status.get("verdict"),
                    "coverage_state": index_status.get("coverageState"),
                    "indexing_state": index_status.get("indexingState"),
                    "robots_txt_state": index_status.get("robotsTxtState"),
                    "page_fetch_state": index_status.get("pageFetchState"),
                    "user_canonical": index_status.get("userCanonical"),
                    "selected_canonical": index_status.get("googleCanonical"),
                    "last_crawl_time": index_status.get("lastCrawlTime"),
                    "crawled_as": index_status.get("crawledAs"),
                    "referring_urls": tuple(index_status.get("referringUrls") or ()),
                    "sitemap_urls": tuple(index_status.get("sitemap") or ()),
                    "metadata": {"inspectionResultLink": result.get("inspectionResultLink")},
                }
            )
        except (OSError, ValueError, RuntimeError) as exc:
            raw.append({"url": url, "error": f"{type(exc).__name__}: {exc}"})
            normalized.append(
                {
                    "record_id": f"GSC-UI-{index:08d}",
                    "source": SOURCE_INSPECTION,
                    "url": url,
                    "verdict": "ERROR",
                    "coverage_state": None,
                    "indexing_state": None,
                    "robots_txt_state": None,
                    "page_fetch_state": None,
                    "user_canonical": None,
                    "selected_canonical": None,
                    "last_crawl_time": None,
                    "crawled_as": None,
                    "referring_urls": (),
                    "sitemap_urls": (),
                    "metadata": {"error": f"{type(exc).__name__}: {exc}"},
                }
            )
    artifact = {
        "format_version": "RASAI-GSC-UI-001",
        "source": SOURCE_INSPECTION,
        "site_url": site_url,
        "language_code": language_code,
        "results": raw,
    }
    return _persist(
        audit_workspace=audit_workspace,
        source_type=SOURCE_INSPECTION,
        capture_method="DIRECT_OFFICIAL_API",
        artifact=artifact,
        period_start=None,
        period_end=None,
        index_rows=normalized,
        metadata={
            "site_url": site_url,
            "requested_urls": len(requested),
            "errors": sum(row["verdict"] == "ERROR" for row in normalized),
        },
    )


def _post_json(endpoint: str, payload: dict[str, Any], token: str, timeout: float, opener: JsonOpener) -> dict[str, Any]:
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    request = Request(
        endpoint,
        data=body,
        method="POST",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json", "Accept": "application/json"},
    )
    try:
        response = opener(request, timeout=timeout)
        raw = response.read()
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:1000]
        raise RuntimeError(f"Google API HTTP {exc.code}: {detail}") from exc
    except URLError as exc:
        raise RuntimeError(f"Google API network error: {exc.reason}") from exc
    try:
        decoded = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Google API returned invalid JSON") from exc
    if not isinstance(decoded, dict):
        raise ValueError("Google API JSON root must be an object")
    return decoded


def _persist(
    *,
    audit_workspace: str | Path,
    source_type: str,
    capture_method: str,
    artifact: dict[str, Any],
    period_start: str | None,
    period_end: str | None,
    search_rows: list[dict[str, Any]] | None = None,
    index_rows: list[dict[str, Any]] | None = None,
    metadata: dict[str, Any] | None = None,
) -> str:
    raw = (json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    digest = hashlib.sha256(raw).hexdigest()
    dataset_id = f"OBS-{digest[:16].upper()}"
    with ObservabilityStore(audit_workspace) as store:
        artifact_path = store.artifacts / f"{source_type.casefold().replace('_','-')}-{digest[:16]}.json"
        artifact_path.write_bytes(raw)
        relative = artifact_path.relative_to(store.workspace).as_posix()
        dataset = new_dataset(
            dataset_id=dataset_id,
            source_type=source_type,
            capture_method=capture_method,
            artifact_path=relative,
            artifact_sha256=digest,
            period_start=period_start,
            period_end=period_end,
            metadata=metadata,
        )
        store.replace_dataset_rows(dataset, search_rows=search_rows or (), index_rows=index_rows or ())
    return dataset_id


def _audit_urls(workspace: Path) -> tuple[str, ...]:
    database = workspace / "audit.db"
    uri = database.resolve().as_uri() + "?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    connection.execute("PRAGMA query_only=ON")
    try:
        rows = connection.execute("SELECT normalized_url FROM pages ORDER BY normalized_url").fetchall()
        return tuple(str(row[0]) for row in rows)
    finally:
        connection.close()


def _validate_period(start_date: str, end_date: str) -> None:
    try:
        start = date.fromisoformat(start_date)
        end = date.fromisoformat(end_date)
    except ValueError as exc:
        raise ValueError("start/end date must use YYYY-MM-DD") from exc
    if start > end:
        raise ValueError("start date cannot be after end date")
