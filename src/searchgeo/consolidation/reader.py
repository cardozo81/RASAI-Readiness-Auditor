"""Read immutable evidence from one SearchGEO AUD workspace.

No function in this module opens an audit database in write mode.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
import hashlib
import json
import sqlite3
from typing import Any, Iterable
from urllib.parse import urlsplit

from .models import SourceAudit


@dataclass(frozen=True, slots=True)
class AuditBundle:
    source: SourceAudit
    scores: tuple[dict[str, Any], ...]
    performance: tuple[dict[str, Any], ...]
    apdex: tuple[dict[str, Any], ...]
    findings: tuple[dict[str, Any], ...]


def source_file_fingerprint(path: Path) -> str:
    stat = path.stat()
    material = f"{path.resolve()}|{stat.st_size}|{stat.st_mtime_ns}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def url_set_fingerprint(urls: tuple[str, ...]) -> str:
    payload = json.dumps(sorted(set(urls)), ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@contextmanager
def _open_read_only(path: Path):
    connection = sqlite3.connect(f"file:{path.resolve().as_posix()}?mode=ro", uri=True, timeout=2.0)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")
    try:
        yield connection
    finally:
        connection.close()


def _table_exists(connection: sqlite3.Connection, table: str) -> bool:
    return connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1", (table,)
    ).fetchone() is not None


def _columns(connection: sqlite3.Connection, table: str) -> set[str]:
    if not _table_exists(connection, table):
        return set()
    return {str(row[1]) for row in connection.execute(f'PRAGMA table_info("{table}")').fetchall()}


def _rows(connection: sqlite3.Connection, sql: str, params: Iterable[Any] = ()) -> tuple[dict[str, Any], ...]:
    return tuple(dict(row) for row in connection.execute(sql, tuple(params)).fetchall())


def _hostname(value: str) -> str:
    value = (value or "").strip()
    if not value:
        return ""
    split = urlsplit(value if "://" in value else f"https://{value}")
    return (split.hostname or "").casefold()


def _audit_urls(connection: sqlite3.Connection, audit_id: str) -> tuple[str, ...]:
    values: list[str] = []
    if _table_exists(connection, "pages"):
        cols = _columns(connection, "pages")
        if {"audit_id", "normalized_url"} <= cols:
            values.extend(
                str(row[0]) for row in connection.execute(
                    "SELECT DISTINCT normalized_url FROM pages WHERE audit_id=? ORDER BY normalized_url",
                    (audit_id,),
                ).fetchall() if row[0]
            )
    if not values and _table_exists(connection, "audit_input_urls"):
        cols = _columns(connection, "audit_input_urls")
        if {"audit_id", "normalized_url"} <= cols:
            values.extend(
                str(row[0]) for row in connection.execute(
                    "SELECT DISTINCT normalized_url FROM audit_input_urls WHERE audit_id=? ORDER BY normalized_url",
                    (audit_id,),
                ).fetchall() if row[0]
            )
    return tuple(dict.fromkeys(values))


def _domains(connection: sqlite3.Connection, audit_id: str, urls: tuple[str, ...]) -> tuple[str, ...]:
    domains: list[str] = []
    if _table_exists(connection, "audit_targets"):
        cols = _columns(connection, "audit_targets")
        if {"audit_id", "normalized_origin"} <= cols:
            for row in connection.execute(
                "SELECT DISTINCT normalized_origin FROM audit_targets WHERE audit_id=?",
                (audit_id,),
            ).fetchall():
                host = _hostname(str(row[0] or ""))
                if host:
                    domains.append(host)
    for url in urls:
        host = _hostname(url)
        if host:
            domains.append(host)
    return tuple(sorted(dict.fromkeys(domains)))


def _devices(connection: sqlite3.Connection, audit_id: str) -> tuple[str, ...]:
    if not (_table_exists(connection, "page_snapshots") and _table_exists(connection, "pages")):
        return ()
    pcols = _columns(connection, "pages")
    scols = _columns(connection, "page_snapshots")
    if not ({"page_id", "audit_id"} <= pcols and {"page_id", "device"} <= scols):
        return ()
    rows = connection.execute(
        """SELECT DISTINCT upper(ps.device)
           FROM page_snapshots ps JOIN pages p ON p.page_id=ps.page_id
           WHERE p.audit_id=? ORDER BY upper(ps.device)""",
        (audit_id,),
    ).fetchall()
    return tuple(str(row[0]) for row in rows if row[0])


def _read_scores(connection: sqlite3.Connection, audit_id: str) -> tuple[dict[str, Any], ...]:
    required = {
        "audit_id", "dimension", "device", "value", "coverage", "confidence",
        "consolidation_status", "scoring_version", "calculated_at",
    }
    if not required <= _columns(connection, "scores"):
        return ()
    return _rows(
        connection,
        """SELECT audit_id,upper(device) device,dimension,value,coverage,confidence,
                  consolidation_status,scoring_version,calculated_at
           FROM scores WHERE audit_id=? ORDER BY calculated_at,device,dimension""",
        (audit_id,),
    )


def _read_performance(connection: sqlite3.Connection, audit_id: str) -> tuple[dict[str, Any], ...]:
    cols = _columns(connection, "web_performance_observations")
    required = {"audit_id", "url", "device", "captured_at"}
    if not required <= cols:
        return ()
    wanted = [
        "status", "strategy", "performance_score", "accessibility_score", "best_practices_score",
        "seo_score", "fcp_lab_ms", "speed_index_lab_ms", "lcp_lab_ms", "tbt_lab_ms", "cls_lab",
        "field_source", "field_scope", "lcp_p75_ms", "inp_p75_ms", "cls_p75", "cwv_assessment",
    ]
    select = ["audit_id", "url", "upper(device) AS device", "captured_at"]
    select.extend(name if name in cols else f"NULL AS {name}" for name in wanted)
    return _rows(
        connection,
        f"SELECT {','.join(select)} FROM web_performance_observations WHERE audit_id=? ORDER BY captured_at,url,device",
        (audit_id,),
    )


def _read_apdex(connection: sqlite3.Connection, audit_id: str) -> tuple[dict[str, Any], ...]:
    cols = _columns(connection, "synthetic_apdex_summaries")
    required = {"audit_id", "url", "device", "calculated_at"}
    if not required <= cols:
        return ()
    wanted = [
        "profile_id", "threshold_seconds", "valid_samples", "invalid_samples", "satisfied_count",
        "tolerating_count", "frustrated_count", "apdex_score", "small_group", "final_group",
        "median_ms", "p75_ms", "p90_ms", "p95_ms", "p99_ms", "trend_percent",
    ]
    select = ["audit_id", "url", "upper(device) AS device", "calculated_at"]
    select.extend(name if name in cols else f"NULL AS {name}" for name in wanted)
    return _rows(
        connection,
        f"SELECT {','.join(select)} FROM synthetic_apdex_summaries WHERE audit_id=? ORDER BY calculated_at,url,device",
        (audit_id,),
    )


def _read_findings(connection: sqlite3.Connection, audit_id: str) -> tuple[dict[str, Any], ...]:
    cols = _columns(connection, "findings")
    required = {"audit_id", "device", "severity", "category", "page_id"}
    if not required <= cols:
        return ()
    if _table_exists(connection, "pages") and {"page_id", "normalized_url"} <= _columns(connection, "pages"):
        return _rows(
            connection,
            """SELECT f.audit_id,upper(f.device) device,f.severity,f.category,
                      f.page_id,p.normalized_url AS url
               FROM findings f LEFT JOIN pages p ON p.page_id=f.page_id
               WHERE f.audit_id=?""",
            (audit_id,),
        )
    return _rows(
        connection,
        "SELECT audit_id,upper(device) device,severity,category,page_id,NULL AS url FROM findings WHERE audit_id=?",
        (audit_id,),
    )


def read_audit_bundle(db_path: Path) -> AuditBundle:
    fingerprint = source_file_fingerprint(db_path)
    with _open_read_only(db_path) as connection:
        if not _table_exists(connection, "audits"):
            raise ValueError("missing audits table")
        cols = _columns(connection, "audits")
        required = {"audit_id", "created_at", "auditor_version", "ruleset_version"}
        if not required <= cols:
            raise ValueError("audit metadata is incomplete")
        row = connection.execute("SELECT * FROM audits ORDER BY created_at DESC LIMIT 1").fetchone()
        if row is None:
            raise ValueError("audits table is empty")
        audit = dict(row)
        audit_id = str(audit["audit_id"])
        urls = _audit_urls(connection, audit_id)
        domains = _domains(connection, audit_id, urls)
        devices = _devices(connection, audit_id)
        created_at = str(audit.get("created_at") or "")
        started_at = str(audit.get("started_at") or "") or None
        completed_at = str(audit.get("completed_at") or "") or None
        source = SourceAudit(
            audit_id=audit_id,
            db_path=db_path,
            source_fingerprint=fingerprint,
            url_set_fingerprint=url_set_fingerprint(urls),
            project_name=str(audit.get("project_name") or ""),
            status=str(audit.get("status") or ""),
            completion_status=str(audit.get("completion_status") or "") or None,
            created_at=created_at,
            started_at=started_at,
            completed_at=completed_at,
            event_time=completed_at or started_at or created_at,
            auditor_version=str(audit.get("auditor_version") or ""),
            ruleset_version=str(audit.get("ruleset_version") or ""),
            domains=domains,
            devices=devices,
            urls=urls,
        )
        return AuditBundle(
            source=source,
            scores=_read_scores(connection, audit_id),
            performance=_read_performance(connection, audit_id),
            apdex=_read_apdex(connection, audit_id),
            findings=_read_findings(connection, audit_id),
        )
