"""Chrome UX Report History API collector.

Uses the official queryHistoryRecord endpoint and persists weekly p75/density
series in observability.db without changing the source audit database.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen

from .store import ObservabilityStore, new_dataset

ENDPOINT = "https://chromeuxreport.googleapis.com/v1/records:queryHistoryRecord"
SOURCE = "CHROME_UX_REPORT_HISTORY"
DEFAULT_METRICS = (
    "largest_contentful_paint",
    "interaction_to_next_paint",
    "cumulative_layout_shift",
)
JsonOpener = Callable[..., Any]


def collect_crux_history(
    *,
    audit_workspace: str | Path,
    api_key: str,
    target: str,
    target_scope: str = "url",
    form_factor: str | None = None,
    metrics: tuple[str, ...] = DEFAULT_METRICS,
    collection_period_count: int = 40,
    timeout: float = 60.0,
    opener: JsonOpener = urlopen,
) -> str:
    workspace = Path(audit_workspace)
    key = api_key.strip()
    if not key:
        raise ValueError("CrUX API key is required")
    scope = target_scope.strip().lower()
    if scope not in {"url", "origin"}:
        raise ValueError("target_scope must be url or origin")
    normalized_target = _validate_target(workspace, target, scope)
    metric_names = tuple(str(metric).strip() for metric in metrics if str(metric).strip())
    if not metric_names:
        raise ValueError("at least one CrUX metric is required")
    count = max(1, min(int(collection_period_count), 40))
    payload: dict[str, Any] = {
        scope: normalized_target,
        "metrics": list(metric_names),
        "collectionPeriodCount": count,
    }
    normalized_form_factor = form_factor.upper() if form_factor else None
    if normalized_form_factor:
        payload["formFactor"] = normalized_form_factor
    endpoint = f"{ENDPOINT}?key={quote(key, safe='')}"
    response = _post_json(endpoint, payload, timeout, opener)
    rows = _normalize(
        response,
        target=normalized_target,
        target_scope=scope,
        form_factor=normalized_form_factor,
    )
    artifact = {
        "format_version": "RASAI-CRUX-HISTORY-001",
        "source": SOURCE,
        "request": {k: v for k, v in payload.items()},
        "response": response,
    }
    # endpoint/API key are deliberately absent from the artifact.
    raw = (json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    digest = hashlib.sha256(raw).hexdigest()
    dataset_id = f"OBS-{digest[:16].upper()}"
    with ObservabilityStore(workspace) as store:
        artifact_path = store.artifacts / f"crux-history-{digest[:16]}.json"
        artifact_path.write_bytes(raw)
        periods = [row.get("period_end") for row in rows if row.get("period_end")]
        dataset = new_dataset(
            dataset_id=dataset_id,
            source_type=SOURCE,
            capture_method="DIRECT_OFFICIAL_API",
            artifact_path=artifact_path.relative_to(store.workspace).as_posix(),
            artifact_sha256=digest,
            period_start=min((row.get("period_start") for row in rows if row.get("period_start")), default=None),
            period_end=max(periods, default=None),
            metadata={
                "target": normalized_target,
                "target_scope": scope,
                "form_factor": normalized_form_factor,
                "metrics": list(metric_names),
                "points": len(rows),
                "scope_policy": "AUDITED_ORIGIN_ONLY",
            },
        )
        store.replace_dataset_rows(dataset, crux_rows=rows)
    return dataset_id


def _validate_target(workspace: Path, target: str, scope: str) -> str:
    value = str(target).strip()
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("CrUX target must be an absolute HTTP(S) URL")
    origin = _origin(parsed)
    allowed = _audit_origins(workspace)
    if origin.casefold() not in {item.casefold() for item in allowed}:
        raise ValueError(f"CrUX target is outside audited origin: {value}")
    if scope == "origin":
        if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
            raise ValueError("CrUX origin target must not contain path, query or fragment")
        return origin
    return value


def _audit_origins(workspace: Path) -> set[str]:
    database = workspace / "audit.db"
    if not database.is_file():
        raise FileNotFoundError(database)
    connection = sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)
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
        raise ValueError("audit contains no normalized origin for CrUX scoping")
    return origins


def _origin(parsed: Any) -> str:
    default_port = (parsed.scheme.casefold() == "https" and parsed.port == 443) or (
        parsed.scheme.casefold() == "http" and parsed.port == 80
    )
    port = "" if parsed.port is None or default_port else f":{parsed.port}"
    return f"{parsed.scheme.casefold()}://{str(parsed.hostname).casefold()}{port}"


def _post_json(endpoint: str, payload: dict[str, Any], timeout: float, opener: JsonOpener) -> dict[str, Any]:
    request = Request(
        endpoint,
        data=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    try:
        response = opener(request, timeout=timeout)
        raw = response.read()
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:1000]
        raise RuntimeError(f"CrUX History HTTP {exc.code}: {detail}") from exc
    except URLError as exc:
        raise RuntimeError(f"CrUX History network error: {exc.reason}") from exc
    try:
        decoded = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("CrUX History returned invalid JSON") from exc
    if not isinstance(decoded, dict):
        raise ValueError("CrUX History JSON root must be an object")
    return decoded


def _normalize(response: dict[str, Any], *, target: str, target_scope: str, form_factor: str | None) -> list[dict[str, Any]]:
    record = response.get("record") or {}
    periods = record.get("collectionPeriods") or []
    metrics = record.get("metrics") or {}
    if not isinstance(metrics, dict):
        raise ValueError("CrUX History response.metrics must be an object")
    rows: list[dict[str, Any]] = []
    counter = 0
    for metric_name, metric_data in metrics.items():
        if not isinstance(metric_data, dict):
            continue
        percentiles = metric_data.get("percentilesTimeseries") or {}
        p75s = percentiles.get("p75s") or [] if isinstance(percentiles, dict) else []
        histograms = metric_data.get("histogramTimeseries") or []
        densities: list[list[Any]] = []
        if isinstance(histograms, list):
            for bucket in histograms:
                if isinstance(bucket, dict) and isinstance(bucket.get("densities"), list):
                    densities.append(bucket["densities"])
        length = max(len(periods), len(p75s), *(len(item) for item in densities), 0)
        for index in range(length):
            period = periods[index] if index < len(periods) and isinstance(periods[index], dict) else {}
            counter += 1
            rows.append(
                {
                    "record_id": f"CRUX-H-{counter:08d}",
                    "target": target,
                    "target_scope": target_scope.upper(),
                    "form_factor": form_factor,
                    "metric": str(metric_name),
                    "period_start": _date(period.get("firstDate")),
                    "period_end": _date(period.get("lastDate")),
                    "p75": _number(p75s[index] if index < len(p75s) else None),
                    "good_density": _number(densities[0][index] if len(densities) > 0 and index < len(densities[0]) else None),
                    "needs_improvement_density": _number(densities[1][index] if len(densities) > 1 and index < len(densities[1]) else None),
                    "poor_density": _number(densities[2][index] if len(densities) > 2 and index < len(densities[2]) else None),
                    "metadata": {"collection_index": index},
                }
            )
    return rows


def _date(value: Any) -> str | None:
    if not isinstance(value, dict):
        return None
    try:
        return f"{int(value['year']):04d}-{int(value['month']):02d}-{int(value['day']):02d}"
    except (KeyError, TypeError, ValueError):
        return None


def _number(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, str) and value.casefold() == "nan":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
