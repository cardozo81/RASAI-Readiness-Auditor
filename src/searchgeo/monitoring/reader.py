"""Read immutable evidence from one persisted RASAi audit workspace."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any
from urllib.parse import urlsplit

from .models import AuditSnapshot, Signal

_RULE_HIGH = {5, 6, 7, 9, 10, 11, 15, 18, 19, 20, 21, 23, 25, 26, 28, 38}
_RULE_MEDIUM = {12, 13, 14, 16, 17, 22, 24, 27, 29, 30, 31, 32, 33, 34, 36, 37, 39, 40, 42, 43, 44, 45, 47, 48, 49, 50, 51, 52}
_RULE_LOW = {3, 8, 35, 41, 46}
_RULE_CRITICAL = {1, 53, 54}


def _rule_severity(rule_id: str) -> str:
    try:
        number = int(rule_id.rsplit("-", 1)[-1])
    except (TypeError, ValueError):
        return "INFO"
    if number in _RULE_CRITICAL:
        return "CRITICAL"
    if number in _RULE_HIGH:
        return "HIGH"
    if number in _RULE_MEDIUM:
        return "MEDIUM"
    if number in _RULE_LOW:
        return "LOW"
    return "INFO"


def _connect(database: Path) -> sqlite3.Connection:
    if not database.is_file():
        raise FileNotFoundError(f"audit database not found: {database}")
    uri = database.resolve().as_uri() + "?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    return connection


def _tables(connection: sqlite3.Connection) -> set[str]:
    return {str(row[0]) for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def _json(value: Any, default: Any) -> Any:
    if value is None:
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return default


def _url_fingerprint(urls: list[str]) -> str:
    payload = "\n".join(sorted(set(urls))).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def read_audit_snapshot(workspace: str | Path) -> AuditSnapshot:
    root = Path(workspace)
    database = root / "audit.db"
    connection = _connect(database)
    try:
        tables = _tables(connection)
        audit = connection.execute("SELECT * FROM audits ORDER BY rowid LIMIT 1").fetchone()
        if audit is None:
            raise ValueError(f"no audit metadata found in {database}")
        audit_id = str(audit["audit_id"])
        page_rows = list(connection.execute("SELECT page_id,normalized_url FROM pages WHERE audit_id=? ORDER BY normalized_url", (audit_id,)))
        page_url = {str(row["page_id"]): str(row["normalized_url"]) for row in page_rows}
        urls = [str(row["normalized_url"]) for row in page_rows]
        targets = list(connection.execute("SELECT normalized_origin FROM audit_targets WHERE audit_id=?", (audit_id,)))
        origins = sorted({str(row[0]).rstrip("/") for row in targets if row[0]})
        domains = tuple(sorted({urlsplit(origin).hostname.lower() for origin in origins if urlsplit(origin).hostname}))
        signals: dict[str, Signal] = {}
        limitations: list[str] = []

        _read_rules(connection, audit_id, page_url, signals)
        _read_page_state(connection, audit_id, page_url, signals)
        scoring_versions = _read_scores(connection, tables, audit_id, signals)
        _read_findings(connection, audit_id, page_url, signals)
        _read_performance(connection, tables, audit_id, signals)
        _read_apdex(connection, tables, audit_id, signals)
        _read_ux_apdex(connection, tables, audit_id, signals)

        devices = tuple(sorted({signal.device for signal in signals.values() if signal.device}))
        event_time = str(audit["completed_at"] or audit["started_at"] or audit["created_at"])
        if str(audit["status"]).upper() not in {"COMPLETED", "COMPLETE", "COMPLETE_WITH_LIMITATIONS"}:
            limitations.append(f"audit status is {audit['status']}; comparison may reflect an incomplete run")
        if not urls:
            limitations.append("audit contains no persisted pages")
        return AuditSnapshot(
            audit_id=audit_id,
            workspace=root,
            project_name=str(audit["project_name"]),
            event_time=event_time,
            status=str(audit["status"]),
            completion_status=(str(audit["completion_status"]) if audit["completion_status"] is not None else None),
            auditor_version=str(audit["auditor_version"]),
            ruleset_version=str(audit["ruleset_version"]),
            scoring_versions=scoring_versions,
            domains=domains,
            devices=devices,
            urls=tuple(sorted(set(urls))),
            signals=signals,
            limitations=tuple(limitations + [f"url_set_sha256={_url_fingerprint(urls)}"]),
        )
    finally:
        connection.close()


def _read_rules(connection: sqlite3.Connection, audit_id: str, page_url: dict[str, str], signals: dict[str, Signal]) -> None:
    rows = connection.execute(
        """SELECT rule_id,page_id,device,result,observed_value,error,executed_at,rowid
           FROM rule_executions WHERE audit_id=? ORDER BY rowid""",
        (audit_id,),
    ).fetchall()
    latest: dict[tuple[str, str | None, str | None], sqlite3.Row] = {}
    for row in rows:
        latest[(str(row["rule_id"]), row["page_id"], row["device"])] = row
    for (rule_id, page_id, device), row in latest.items():
        url = page_url.get(str(page_id)) if page_id is not None else None
        device_text = str(device).upper() if device else "GLOBAL"
        key = f"RULE|{device_text}|{url or 'GLOBAL'}|{rule_id}"
        observed = _json(row["observed_value"], {})
        signals[key] = Signal(
            key=key,
            domain="RULE",
            label=rule_id,
            value=str(row["result"]).upper(),
            device=(device_text if device else None),
            url=url,
            rule_id=rule_id,
            severity=_rule_severity(rule_id),
            direction="RESULT",
            metadata={"observed": observed, "error": row["error"], "executed_at": row["executed_at"]},
        )


def _read_page_state(connection: sqlite3.Connection, audit_id: str, page_url: dict[str, str], signals: dict[str, Signal]) -> None:
    rows = connection.execute(
        """SELECT s.*, p.audit_id FROM page_snapshots s JOIN pages p ON p.page_id=s.page_id
           WHERE p.audit_id=? ORDER BY s.captured_at,s.rowid""",
        (audit_id,),
    ).fetchall()
    latest: dict[tuple[str, str], sqlite3.Row] = {}
    for row in rows:
        latest[(str(row["page_id"]), str(row["device"]).upper())] = row
    fields = (
        ("http_status", "HTTP status", "HIGH"),
        ("final_url", "Final URL", "MEDIUM"),
        ("canonical", "Canonical", "MEDIUM"),
        ("meta_robots", "Meta robots", "HIGH"),
        ("title", "Title", "MEDIUM"),
    )
    for (page_id, device), row in latest.items():
        url = page_url.get(page_id)
        if not url:
            continue
        for field, label, severity in fields:
            key = f"PAGE|{device}|{url}|{field}"
            signals[key] = Signal(
                key=key,
                domain="PAGE",
                label=label,
                value=row[field],
                device=device,
                url=url,
                severity=severity,
                direction="STATE",
                metadata={"field": field, "captured_at": row["captured_at"]},
            )


def _read_scores(connection: sqlite3.Connection, tables: set[str], audit_id: str, signals: dict[str, Signal]) -> tuple[str, ...]:
    if "scores" not in tables:
        return ()
    rows = connection.execute(
        """SELECT dimension,device,value,coverage,confidence,consolidation_status,scoring_version,calculated_at,rowid
           FROM scores WHERE audit_id=? ORDER BY rowid""",
        (audit_id,),
    ).fetchall()
    latest: dict[tuple[str, str], sqlite3.Row] = {}
    for row in rows:
        latest[(str(row["device"]).upper(), str(row["dimension"]))] = row
    versions = sorted({str(row["scoring_version"]) for row in rows if row["scoring_version"]})
    for (device, dimension), row in latest.items():
        key = f"SCORE|{device}|{dimension}"
        signals[key] = Signal(
            key=key,
            domain="SCORE",
            label=dimension,
            value=(float(row["value"]) if row["value"] is not None else None),
            device=device,
            severity="HIGH" if dimension in {"TECHNICAL_ACCESSIBILITY", "INDEXABILITY", "CONTENT_EXTRACTABILITY"} else "MEDIUM",
            direction="HIGHER_BETTER",
            unit="points",
            metadata={
                "coverage": float(row["coverage"]),
                "confidence": str(row["confidence"]),
                "consolidation_status": str(row["consolidation_status"]),
                "scoring_version": str(row["scoring_version"]),
                "calculated_at": str(row["calculated_at"]),
            },
        )
    return tuple(versions)


def _read_findings(connection: sqlite3.Connection, audit_id: str, page_url: dict[str, str], signals: dict[str, Signal]) -> None:
    rows = connection.execute(
        "SELECT severity,rule_id,page_id,device,status FROM findings WHERE audit_id=?",
        (audit_id,),
    ).fetchall()
    counts: dict[str, int] = {}
    for row in rows:
        severity = str(row["severity"]).upper()
        if str(row["status"]).upper() not in {"RESOLVED", "CLOSED", "DISMISSED"}:
            counts[severity] = counts.get(severity, 0) + 1
    for severity in ("CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"):
        key = f"FINDINGS|{severity}"
        signals[key] = Signal(
            key=key,
            domain="FINDINGS",
            label=f"{severity} findings",
            value=counts.get(severity, 0),
            severity=severity,
            direction="LOWER_BETTER",
            unit="count",
        )


def _read_performance(connection: sqlite3.Connection, tables: set[str], audit_id: str, signals: dict[str, Signal]) -> None:
    if "web_performance_observations" not in tables:
        return
    rows = connection.execute(
        """SELECT * FROM web_performance_observations WHERE audit_id=? ORDER BY captured_at,rowid""",
        (audit_id,),
    ).fetchall()
    latest: dict[tuple[str, str], sqlite3.Row] = {}
    for row in rows:
        latest[(str(row["device"]).upper(), str(row["url"]))] = row
    metrics = (
        ("performance_score", "Lighthouse Performance", "HIGHER_BETTER", "score"),
        ("accessibility_score", "Lighthouse Accessibility", "HIGHER_BETTER", "score"),
        ("seo_score", "Lighthouse SEO", "HIGHER_BETTER", "score"),
        ("lcp_lab_ms", "LCP lab", "LOWER_BETTER", "ms"),
        ("tbt_lab_ms", "TBT lab", "LOWER_BETTER", "ms"),
        ("cls_lab", "CLS lab", "LOWER_BETTER", "ratio"),
        ("lcp_p75_ms", "LCP p75", "LOWER_BETTER", "ms"),
        ("inp_p75_ms", "INP p75", "LOWER_BETTER", "ms"),
        ("cls_p75", "CLS p75", "LOWER_BETTER", "ratio"),
    )
    for (device, url), row in latest.items():
        for field, label, direction, unit in metrics:
            value = row[field]
            if value is None:
                continue
            key = f"PERF|{device}|{url}|{field}"
            signals[key] = Signal(
                key=key, domain="PERFORMANCE", label=label, value=float(value), device=device,
                url=url, severity="MEDIUM", direction=direction, unit=unit,
                metadata={"field_source": row["field_source"], "field_scope": row["field_scope"], "captured_at": row["captured_at"]},
            )


def _read_apdex(connection: sqlite3.Connection, tables: set[str], audit_id: str, signals: dict[str, Signal]) -> None:
    if "synthetic_apdex_summaries" not in tables:
        return
    rows = connection.execute("SELECT * FROM synthetic_apdex_summaries WHERE audit_id=? ORDER BY calculated_at,rowid", (audit_id,)).fetchall()
    latest: dict[tuple[str, str, str], sqlite3.Row] = {}
    for row in rows:
        latest[(str(row["device"]).upper(), str(row["url"]), str(row["profile_id"]))] = row
    for (device, url, profile), row in latest.items():
        for field, label, direction, unit in (
            ("apdex_score", "Synthetic Navigation Apdex", "HIGHER_BETTER", "score"),
            ("mean_ms", "Synthetic navigation mean", "LOWER_BETTER", "ms"),
            ("p95_ms", "Synthetic navigation p95", "LOWER_BETTER", "ms"),
        ):
            value = row[field]
            if value is None:
                continue
            key = f"APDEX|{device}|{url}|{profile}|{field}"
            signals[key] = Signal(
                key=key, domain="APDEX", label=label, value=float(value), device=device, url=url,
                severity="MEDIUM", direction=direction, unit=unit,
                metadata={"profile_id": profile, "threshold_seconds": row["threshold_seconds"], "valid_samples": row["valid_samples"], "final_group": bool(row["final_group"])},
            )


def _read_ux_apdex(connection: sqlite3.Connection, tables: set[str], audit_id: str, signals: dict[str, Signal]) -> None:
    table = "synthetic_ux_apdex_summaries"
    if table not in tables:
        return
    rows = connection.execute(f"SELECT * FROM {table} WHERE audit_id=? ORDER BY rowid", (audit_id,)).fetchall()
    for row in rows:
        names = set(row.keys())
        url = str(row["url"]) if "url" in names else "GLOBAL"
        device = str(row["device"]).upper() if "device" in names else "GLOBAL"
        profile = str(row["profile_id"]) if "profile_id" in names else "DEFAULT"
        score_field = "apdex_score" if "apdex_score" in names else None
        if score_field and row[score_field] is not None:
            key = f"UX_APDEX|{device}|{url}|{profile}|apdex_score"
            signals[key] = Signal(
                key=key, domain="UX_APDEX", label="Synthetic User Experience Apdex",
                value=float(row[score_field]), device=(device if device != "GLOBAL" else None),
                url=(url if url != "GLOBAL" else None), severity="MEDIUM", direction="HIGHER_BETTER", unit="score",
                metadata={"profile_id": profile},
            )
