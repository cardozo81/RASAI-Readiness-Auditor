"""Observed content-use controls relevant to Search and generative surfaces.

The analyzer reports publisher directives as facts. It does not penalize a site
for choosing restrictive policies and it does not convert them into SARI.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
import sqlite3
from typing import Any

_MAX_SNIPPET_RE = re.compile(r"(?:^|[,\s])max-snippet\s*:\s*(-?\d+)", re.IGNORECASE)
_DATA_NOSNIPPET_RE = re.compile(r"\bdata-nosnippet(?:\s*=\s*(?:['\"][^'\"]*['\"]|[^\s>]+))?", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class ContentControlObservation:
    url: str
    device: str
    meta_robots: str | None
    x_robots_tag: tuple[str, ...]
    nosnippet: bool
    max_snippet: int | None
    data_nosnippet_count: int
    interpretation: str
    evidence_quality: str


def analyze_content_controls(audit_workspace: str | Path) -> tuple[ContentControlObservation, ...]:
    workspace = Path(audit_workspace)
    connection = _ro(workspace / "audit.db")
    try:
        rows = connection.execute(
            """SELECT ps.*,p.normalized_url FROM page_snapshots ps
               JOIN pages p ON p.page_id=ps.page_id
               WHERE p.audit_id=(SELECT audit_id FROM audits ORDER BY rowid LIMIT 1)
               ORDER BY p.normalized_url,ps.device,ps.captured_at,ps.rowid"""
        ).fetchall()
        latest: dict[tuple[str, str], sqlite3.Row] = {}
        for row in rows:
            latest[(str(row["normalized_url"]), str(row["device"]).upper())] = row
        output: list[ContentControlObservation] = []
        for (url, device), row in latest.items():
            meta = str(row["meta_robots"] or "").strip() or None
            metadata = _json(row["browser_metadata"], {}) if "browser_metadata" in row.keys() else {}
            raw_http = metadata.get("raw_http") if isinstance(metadata, dict) else None
            x_values = tuple(
                str(item).strip() for item in ((raw_http or {}).get("x_robots_tag") or [])
                if str(item).strip()
            ) if isinstance(raw_http, dict) else ()
            directive_text = ", ".join(value for value in (meta, *x_values) if value)
            lowered = directive_text.casefold()
            nosnippet = _has_directive(lowered, "nosnippet")
            max_snippet = _max_snippet(directive_text)
            html_ref = row["rendered_artifact_ref"] or row["raw_artifact_ref"]
            html = _read(workspace, html_ref)
            data_count = len(_DATA_NOSNIPPET_RE.findall(html)) if html else 0
            if nosnippet or max_snippet == 0:
                interpretation = "DIRECT_SNIPPET_USE_RESTRICTED"
            elif max_snippet is not None and max_snippet >= 0:
                interpretation = "DIRECT_SNIPPET_USE_LIMITED"
            elif data_count:
                interpretation = "SELECTIVE_CONTENT_EXCLUSION"
            else:
                interpretation = "NO_SNIPPET_RESTRICTION_OBSERVED"
            quality = "HIGH" if x_values or isinstance(raw_http, dict) else "MEDIUM"
            output.append(
                ContentControlObservation(
                    url=url,
                    device=device,
                    meta_robots=meta,
                    x_robots_tag=x_values,
                    nosnippet=nosnippet,
                    max_snippet=max_snippet,
                    data_nosnippet_count=data_count,
                    interpretation=interpretation,
                    evidence_quality=quality,
                )
            )
        return tuple(output)
    finally:
        connection.close()


def _has_directive(text: str, directive: str) -> bool:
    tokens = [part.strip().split(":", 1)[0] for part in re.split(r"[,\s]+", text) if part.strip()]
    return directive.casefold() in {token.casefold() for token in tokens}


def _max_snippet(text: str) -> int | None:
    match = _MAX_SNIPPET_RE.search(text)
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def _read(workspace: Path, reference: Any) -> str | None:
    if not reference:
        return None
    path = workspace / str(reference)
    if not path.is_file():
        return None
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _json(value: Any, default: Any) -> Any:
    if value is None:
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return default


def _ro(database: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    return connection
