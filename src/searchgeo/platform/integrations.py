"""External outcome/log integrations for the RASAi platform control plane.

These collectors persist observed datasets outside ``audit.db``. They therefore
cannot silently change SARI/SCORE-GEO results and can be compared around
milestones as outcome evidence with an explicit non-causality boundary.
"""
from __future__ import annotations

import csv
from datetime import date
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Any, Iterable, Sequence
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from .models import ExternalDataset
from .store import PlatformStore, new_id, utc_now

_GA4_ENDPOINT = "https://analyticsdata.googleapis.com/v1beta/properties/{property_id}:runReport"
_AI_CRAWLER_MARKERS: tuple[tuple[str, str], ...] = (
    ("oai-searchbot", "OpenAI Search crawler"),
    ("gptbot", "OpenAI training crawler"),
    ("chatgpt-user", "ChatGPT user-triggered fetch"),
    ("claudebot", "Anthropic crawler"),
    ("claude-user", "Anthropic user-triggered fetch"),
    ("perplexitybot", "Perplexity crawler"),
)
_COMBINED_LOG_RE = re.compile(
    r'^(?P<ip>\S+) \S+ \S+ \[(?P<time>[^\]]+)\] "(?P<method>\S+) (?P<path>\S+) (?P<protocol>[^"]+)" (?P<status>\d{3}) (?P<bytes>\S+)(?: "(?P<referer>[^"]*)" "(?P<ua>[^"]*)")?'
)


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _absolute_url(origin: str, value: str | None) -> str | None:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    parts = urlsplit(text)
    if parts.scheme in {"http", "https"} and parts.hostname:
        return text
    return origin.rstrip("/") + "/" + text.lstrip("/")


def _dataset_scope(store: PlatformStore, property_id: str) -> tuple[str, str]:
    hierarchy = store.hierarchy_for_property(property_id)
    return str(hierarchy["organization_id"]), str(hierarchy["project_id"])


def _persist_records(
    store: PlatformStore,
    *,
    property_id: str,
    environment_id: str,
    source_type: str,
    records: list[dict[str, Any]],
    period_start: str | None,
    period_end: str | None,
    artifact_path: str | None = None,
    artifact_sha256: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> ExternalDataset:
    organization_id, project_id = _dataset_scope(store, property_id)
    dataset = ExternalDataset(
        dataset_id=new_id("EXT"),
        organization_id=organization_id,
        project_id=project_id,
        property_id=property_id,
        environment_id=environment_id,
        source_type=source_type.upper(),
        period_start=period_start,
        period_end=period_end,
        captured_at=utc_now(),
        artifact_path=artifact_path,
        artifact_sha256=artifact_sha256,
        row_count=len(records),
        metadata=metadata or {},
    )
    store.add_external_dataset(dataset, records)
    return dataset


def collect_ga4(
    store: PlatformStore,
    *,
    property_id: str,
    environment_id: str,
    ga4_property_id: str,
    start_date: str,
    end_date: str,
    access_token_env: str = "GOOGLE_ANALYTICS_ACCESS_TOKEN",
    dimensions: Sequence[str] = ("date", "pagePathPlusQueryString"),
    metrics: Sequence[str] = ("sessions", "activeUsers", "screenPageViews", "keyEvents", "totalRevenue"),
    timeout_seconds: int = 30,
) -> ExternalDataset:
    """Call the official GA4 Data API ``runReport`` endpoint with a bearer token.

    Authentication stays external to RASAi: the database stores only integration
    metadata/environment-variable names, never the bearer token itself.
    """
    date.fromisoformat(start_date)
    date.fromisoformat(end_date)
    if end_date < start_date:
        raise ValueError("end_date must be >= start_date")
    token = os.environ.get(access_token_env, "").strip()
    if not token:
        raise RuntimeError(f"missing GA4 bearer token in environment variable {access_token_env}")
    payload = {
        "dateRanges": [{"startDate": start_date, "endDate": end_date}],
        "dimensions": [{"name": name} for name in dimensions],
        "metrics": [{"name": name} for name in metrics],
        "limit": "100000",
    }
    url = _GA4_ENDPOINT.format(property_id=ga4_property_id.strip())
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "RASAi/GA4-Collector",
        },
    )
    with urlopen(request, timeout=max(1, timeout_seconds)) as response:
        data = json.loads(response.read().decode("utf-8"))
    dimension_headers = [str(item.get("name") or "") for item in data.get("dimensionHeaders", [])]
    metric_headers = [str(item.get("name") or "") for item in data.get("metricHeaders", [])]
    property_row = next((p for p in store.list_properties() if p.property_id == property_id), None)
    if property_row is None:
        raise KeyError(f"property not found: {property_id}")
    records: list[dict[str, Any]] = []
    for index, row in enumerate(data.get("rows", []), start=1):
        dim_values = [str(item.get("value") or "") for item in row.get("dimensionValues", [])]
        metric_values = [str(item.get("value") or "") for item in row.get("metricValues", [])]
        dims = dict(zip(dimension_headers, dim_values))
        metric_map: dict[str, Any] = {}
        for name, value in zip(metric_headers, metric_values):
            try:
                metric_map[name] = float(value)
            except (TypeError, ValueError):
                metric_map[name] = value
        page_value = dims.get("pagePathPlusQueryString") or dims.get("pagePath") or dims.get("landingPagePlusQueryString")
        records.append(
            {
                "record_id": str(index),
                "observed_at": dims.get("date"),
                "normalized_url": _absolute_url(property_row.canonical_origin, page_value),
                "dimensions": dims,
                "metrics": metric_map,
                "metadata": {},
            }
        )
    return _persist_records(
        store,
        property_id=property_id,
        environment_id=environment_id,
        source_type="GA4",
        records=records,
        period_start=start_date,
        period_end=end_date,
        metadata={
            "ga4_property_id": str(ga4_property_id),
            "dimensions": list(dimensions),
            "metrics": list(metrics),
            "currency": (data.get("metadata") or {}).get("currencyCode"),
            "timezone": (data.get("metadata") or {}).get("timeZone"),
            "row_count_reported": data.get("rowCount"),
            "authentication": f"bearer-token-env:{access_token_env}",
        },
    )


def import_ga4_csv(
    store: PlatformStore,
    *,
    property_id: str,
    environment_id: str,
    path: str | Path,
    period_start: str | None = None,
    period_end: str | None = None,
) -> ExternalDataset:
    source = Path(path)
    property_row = next((p for p in store.list_properties() if p.property_id == property_id), None)
    if property_row is None:
        raise KeyError(f"property not found: {property_id}")
    records: list[dict[str, Any]] = []
    with source.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        for index, row in enumerate(reader, start=1):
            normalized = {str(k or "").strip(): str(v or "").strip() for k, v in row.items()}
            path_value = (
                normalized.get("pagePathPlusQueryString")
                or normalized.get("pagePath")
                or normalized.get("landingPagePlusQueryString")
                or normalized.get("url")
            )
            dimensions: dict[str, Any] = {}
            metrics: dict[str, Any] = {}
            for key, value in normalized.items():
                try:
                    metrics[key] = float(value.replace(",", "."))
                except (ValueError, AttributeError):
                    dimensions[key] = value
            records.append(
                {
                    "record_id": str(index),
                    "observed_at": normalized.get("date") or normalized.get("Date"),
                    "normalized_url": _absolute_url(property_row.canonical_origin, path_value),
                    "dimensions": dimensions,
                    "metrics": metrics,
                    "metadata": {},
                }
            )
    return _persist_records(
        store,
        property_id=property_id,
        environment_id=environment_id,
        source_type="GA4_CSV",
        records=records,
        period_start=period_start,
        period_end=period_end,
        artifact_path=str(source.resolve()),
        artifact_sha256=_sha(source),
        metadata={"format": "csv", "source": "user-provided export"},
    )


def classify_ai_crawler(user_agent: str | None) -> str | None:
    text = str(user_agent or "").casefold()
    for marker, label in _AI_CRAWLER_MARKERS:
        if marker in text:
            return label
    return None


def import_cloudflare_logpush(
    store: PlatformStore,
    *,
    property_id: str,
    environment_id: str,
    path: str | Path,
) -> ExternalDataset:
    """Import Cloudflare HTTP request Logpush JSON/JSONL exports.

    The importer intentionally accepts a field subset and preserves the original
    record as metadata so Cloudflare schema additions do not require rewriting
    historical evidence.
    """
    source = Path(path)
    property_row = next((p for p in store.list_properties() if p.property_id == property_id), None)
    if property_row is None:
        raise KeyError(f"property not found: {property_id}")
    text = source.read_text(encoding="utf-8-sig")
    stripped = text.lstrip()
    raw_rows: list[dict[str, Any]] = []
    if stripped.startswith("["):
        value = json.loads(text)
        if not isinstance(value, list):
            raise ValueError("Cloudflare JSON export must contain an array")
        raw_rows = [item for item in value if isinstance(item, dict)]
    else:
        for line_number, line in enumerate(text.splitlines(), start=1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"Cloudflare JSONL line {line_number} is not an object")
            raw_rows.append(value)
    records: list[dict[str, Any]] = []
    for index, row in enumerate(raw_rows, start=1):
        host = row.get("ClientRequestHost") or row.get("EdgeRequestHost") or property_row.hostname
        scheme = row.get("ClientRequestScheme") or urlsplit(property_row.canonical_origin).scheme or "https"
        uri = str(row.get("ClientRequestURI") or "/")
        url = uri if uri.startswith("http://") or uri.startswith("https://") else f"{scheme}://{host}{uri if uri.startswith('/') else '/' + uri}"
        ua = str(row.get("ClientRequestUserAgent") or "")
        crawler = classify_ai_crawler(ua)
        records.append(
            {
                "record_id": str(row.get("RayID") or index),
                "observed_at": str(row.get("EdgeStartTimestamp") or row.get("ClientRequestTimestamp") or "") or None,
                "normalized_url": url,
                "dimensions": {
                    "method": row.get("ClientRequestMethod"),
                    "user_agent": ua,
                    "ai_crawler": crawler,
                    "host": host,
                },
                "metrics": {
                    "status": row.get("EdgeResponseStatus"),
                    "response_bytes": row.get("EdgeResponseBytes"),
                    "response_body_bytes": row.get("EdgeResponseBodyBytes"),
                },
                "metadata": {"raw": row},
            }
        )
    return _persist_records(
        store,
        property_id=property_id,
        environment_id=environment_id,
        source_type="CLOUDFLARE_LOGPUSH",
        records=records,
        period_start=None,
        period_end=None,
        artifact_path=str(source.resolve()),
        artifact_sha256=_sha(source),
        metadata={"format": "json/jsonl", "ai_crawler_classification": "user-agent marker heuristic"},
    )


def import_combined_access_log(
    store: PlatformStore,
    *,
    property_id: str,
    environment_id: str,
    path: str | Path,
) -> ExternalDataset:
    source = Path(path)
    property_row = next((p for p in store.list_properties() if p.property_id == property_id), None)
    if property_row is None:
        raise KeyError(f"property not found: {property_id}")
    records: list[dict[str, Any]] = []
    skipped = 0
    with source.open("r", encoding="utf-8", errors="replace") as stream:
        for line_number, line in enumerate(stream, start=1):
            match = _COMBINED_LOG_RE.match(line.rstrip("\n"))
            if not match:
                skipped += 1
                continue
            values = match.groupdict()
            ua = values.get("ua") or ""
            try:
                byte_count: int | None = int(values["bytes"]) if values["bytes"] != "-" else None
            except (TypeError, ValueError):
                byte_count = None
            records.append(
                {
                    "record_id": str(line_number),
                    "observed_at": values.get("time"),
                    "normalized_url": _absolute_url(property_row.canonical_origin, values.get("path")),
                    "dimensions": {
                        "method": values.get("method"),
                        "protocol": values.get("protocol"),
                        "user_agent": ua,
                        "ai_crawler": classify_ai_crawler(ua),
                        "referer": values.get("referer"),
                    },
                    "metrics": {"status": int(values["status"]), "response_bytes": byte_count},
                    "metadata": {"client_ip": values.get("ip")},
                }
            )
    return _persist_records(
        store,
        property_id=property_id,
        environment_id=environment_id,
        source_type="HTTP_ACCESS_LOG",
        records=records,
        period_start=None,
        period_end=None,
        artifact_path=str(source.resolve()),
        artifact_sha256=_sha(source),
        metadata={"format": "combined/common-compatible", "skipped_lines": skipped, "ai_crawler_classification": "user-agent marker heuristic"},
    )


def crawler_summary(store: PlatformStore, dataset_id: str) -> list[dict[str, Any]]:
    summary: dict[str, dict[str, Any]] = {}
    for record in store.external_records(dataset_id):
        crawler = str((record.get("dimensions") or {}).get("ai_crawler") or "").strip()
        if not crawler:
            continue
        item = summary.setdefault(crawler, {"crawler": crawler, "requests": 0, "status_2xx": 0, "status_4xx_5xx": 0, "urls": set()})
        item["requests"] += 1
        url = record.get("normalized_url")
        if url:
            item["urls"].add(url)
        status = (record.get("metrics") or {}).get("status")
        try:
            code = int(status)
        except (TypeError, ValueError):
            continue
        if 200 <= code < 300:
            item["status_2xx"] += 1
        elif code >= 400:
            item["status_4xx_5xx"] += 1
    output: list[dict[str, Any]] = []
    for item in summary.values():
        output.append({**item, "unique_urls": len(item.pop("urls"))})
    return sorted(output, key=lambda item: (-int(item["requests"]), str(item["crawler"])))
