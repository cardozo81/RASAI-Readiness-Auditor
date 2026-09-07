"""Read-only Google Search Console resource collectors.

These collectors use documented endpoints and persist raw responses as
observability datasets. They never mutate Search Console properties/sitemaps.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from .store import ObservabilityStore, new_dataset

SITES_ENDPOINT = "https://www.googleapis.com/webmasters/v3/sites"
SITEMAPS_ENDPOINT = "https://www.googleapis.com/webmasters/v3/sites/{site}/sitemaps"
SOURCE_SITES = "GOOGLE_SEARCH_CONSOLE_PROPERTIES"
SOURCE_SITEMAPS = "GOOGLE_SEARCH_CONSOLE_SITEMAPS"
JsonOpener = Callable[..., Any]


def collect_sites(
    *,
    audit_workspace: str | Path,
    access_token: str,
    timeout: float = 60.0,
    opener: JsonOpener = urlopen,
) -> str:
    token = _token(access_token)
    response = _get_json(SITES_ENDPOINT, token, timeout, opener)
    entries = response.get("siteEntry") or []
    summary = [
        {
            "site_url": str(item.get("siteUrl") or ""),
            "permission_level": str(item.get("permissionLevel") or ""),
        }
        for item in entries if isinstance(item, dict)
    ]
    return _persist(
        audit_workspace=audit_workspace,
        source=SOURCE_SITES,
        artifact={"format_version": "RASAI-GSC-SITES-001", "source": SOURCE_SITES, "response": response},
        metadata={"properties": summary, "count": len(summary), "read_only": True},
    )


def collect_sitemaps(
    *,
    audit_workspace: str | Path,
    site_url: str,
    access_token: str,
    timeout: float = 60.0,
    opener: JsonOpener = urlopen,
) -> str:
    token = _token(access_token)
    endpoint = SITEMAPS_ENDPOINT.format(site=quote(site_url, safe=""))
    response = _get_json(endpoint, token, timeout, opener)
    items = response.get("sitemap") or []
    summary: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        summary.append(
            {
                "path": item.get("path"),
                "last_submitted": item.get("lastSubmitted"),
                "last_downloaded": item.get("lastDownloaded"),
                "is_pending": item.get("isPending"),
                "warnings": item.get("warnings"),
                "errors": item.get("errors"),
                "submitted": [
                    {"type": content.get("type"), "submitted": content.get("submitted")}
                    for content in (item.get("contents") or []) if isinstance(content, dict)
                ],
            }
        )
    return _persist(
        audit_workspace=audit_workspace,
        source=SOURCE_SITEMAPS,
        artifact={
            "format_version": "RASAI-GSC-SITEMAPS-001",
            "source": SOURCE_SITEMAPS,
            "site_url": site_url,
            "response": response,
        },
        metadata={
            "site_url": site_url,
            "sitemaps": summary,
            "count": len(summary),
            "indexed_field_policy": "DEPRECATED_FIELD_NOT_USED",
            "read_only": True,
        },
    )


def _get_json(endpoint: str, token: str, timeout: float, opener: JsonOpener) -> dict[str, Any]:
    request = Request(endpoint, method="GET", headers={"Authorization": f"Bearer {token}", "Accept": "application/json"})
    try:
        response = opener(request, timeout=timeout)
        raw = response.read()
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:1000]
        raise RuntimeError(f"Google Search Console HTTP {exc.code}: {detail}") from exc
    except URLError as exc:
        raise RuntimeError(f"Google Search Console network error: {exc.reason}") from exc
    try:
        decoded = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Google Search Console returned invalid JSON") from exc
    if not isinstance(decoded, dict):
        raise ValueError("Google Search Console JSON root must be an object")
    return decoded


def _persist(*, audit_workspace: str | Path, source: str, artifact: dict[str, Any], metadata: dict[str, Any]) -> str:
    raw = (json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    digest = hashlib.sha256(raw).hexdigest()
    dataset_id = f"OBS-{digest[:16].upper()}"
    with ObservabilityStore(audit_workspace) as store:
        path = store.artifacts / f"{source.casefold().replace('_','-')}-{digest[:16]}.json"
        path.write_bytes(raw)
        dataset = new_dataset(
            dataset_id=dataset_id,
            source_type=source,
            capture_method="DIRECT_OFFICIAL_API",
            artifact_path=path.relative_to(store.workspace).as_posix(),
            artifact_sha256=digest,
            metadata=metadata,
        )
        store.replace_dataset_rows(dataset)
    return dataset_id


def _token(value: str) -> str:
    token = value.strip()
    if not token:
        raise ValueError("Google Search Console access token is required")
    return token
