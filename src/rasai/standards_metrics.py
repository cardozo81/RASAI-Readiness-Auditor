"""Derived readiness, retrieval and standards observations.

This module is additive and advisory. It reuses persisted RASAi evidence, performs
bounded optional standards calls, and stores observations in additive audit.db tables.
It never changes SARI-001 or SCORE-GEO-004.
"""
from __future__ import annotations

from datetime import datetime, timezone
from html import escape
import json
import math
import os
from pathlib import Path
import sqlite3
from statistics import fmean
from typing import Any, Iterable, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen
from uuid import uuid4

from rasai.persistence import AuditWorkspace
from rasai.standards_service_registry import (
    DEFAULT_STANDARDS_MAX_URLS,
    DEFAULT_STANDARDS_TIMEOUT_SECONDS,
    MDN_OBSERVATORY_ENV,
    STANDARDS_MAX_URLS_ENV,
    STANDARDS_TIMEOUT_ENV,
    W3C_VALIDATOR_ENV,
    service,
    service_state,
    service_states,
)

CONTRACT_VERSION = "STANDARDS-METRICS-001"
REPORT_FILE = "standards.html"
W3C_VALIDATOR_ENDPOINT = "https://validator.w3.org/nu/"
MDN_OBSERVATORY_ENDPOINT = "https://observatory-api.mdn.mozilla.net/api/v2/scan"


class StandardsExternalError(RuntimeError):
    pass


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json(value: Any, default: Any = None) -> Any:
    if isinstance(value, (dict, list)):
        return value
    if value in (None, ""):
        return default
    try:
        return json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return default


def _dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _bool(raw: str | None, default: bool) -> bool:
    if raw is None or not raw.strip():
        return default
    value = raw.strip().casefold()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    raise ValueError("boolean setting must use true/false, 1/0, yes/no or on/off")


def _nonnegative_int(raw: str | None, default: int) -> int:
    if raw is None or not raw.strip():
        return default
    value = int(raw)
    if value < 0:
        raise ValueError("value must be >= 0")
    return value


def _positive_float(raw: str | None, default: float) -> float:
    if raw is None or not raw.strip():
        return default
    value = float(raw)
    if not math.isfinite(value) or value <= 0:
        raise ValueError("value must be a positive finite number")
    return value


def _init(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS standards_metric_observations (
            observation_id TEXT PRIMARY KEY,
            audit_id TEXT NOT NULL REFERENCES audits(audit_id) ON DELETE CASCADE,
            metric_id TEXT NOT NULL,
            label TEXT NOT NULL,
            scope TEXT NOT NULL,
            target TEXT,
            device TEXT,
            state TEXT NOT NULL,
            value REAL,
            numerator REAL,
            denominator REAL,
            unit TEXT,
            source TEXT NOT NULL,
            methodology TEXT NOT NULL,
            relation_degree INTEGER NOT NULL,
            details_json TEXT NOT NULL,
            observed_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_standards_metric_audit_metric
            ON standards_metric_observations(audit_id, metric_id, scope);

        CREATE TABLE IF NOT EXISTS standards_service_runs (
            audit_id TEXT NOT NULL REFERENCES audits(audit_id) ON DELETE CASCADE,
            service_id TEXT NOT NULL,
            requested INTEGER NOT NULL,
            configured INTEGER NOT NULL,
            effective_enabled INTEGER NOT NULL,
            state TEXT NOT NULL,
            targets_attempted INTEGER NOT NULL,
            targets_succeeded INTEGER NOT NULL,
            details_json TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (audit_id, service_id)
        );
        """
    )


def _record(
    connection: sqlite3.Connection,
    *,
    audit_id: str,
    metric_id: str,
    label: str,
    scope: str,
    state: str,
    source: str,
    methodology: str,
    relation_degree: int,
    target: str | None = None,
    device: str | None = None,
    value: float | None = None,
    numerator: float | None = None,
    denominator: float | None = None,
    unit: str | None = None,
    details: Mapping[str, Any] | None = None,
) -> None:
    connection.execute(
        """INSERT INTO standards_metric_observations (
            observation_id,audit_id,metric_id,label,scope,target,device,state,value,
            numerator,denominator,unit,source,methodology,relation_degree,details_json,observed_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            f"SMO-{uuid4().hex.upper()}", audit_id, metric_id, label, scope, target,
            device, state, value, numerator, denominator, unit, source, methodology,
            relation_degree, _dump(dict(details or {})), _utc_now(),
        ),
    )


def _service_run(
    connection: sqlite3.Connection,
    *,
    audit_id: str,
    service_id: str,
    state_info: Mapping[str, Any],
    state: str | None = None,
    attempted: int = 0,
    succeeded: int = 0,
    details: Mapping[str, Any] | None = None,
) -> None:
    connection.execute(
        """INSERT OR REPLACE INTO standards_service_runs (
            audit_id,service_id,requested,configured,effective_enabled,state,
            targets_attempted,targets_succeeded,details_json,updated_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (
            audit_id,
            service_id,
            int(bool(state_info.get("requested"))),
            int(bool(state_info.get("configured"))),
            int(bool(state_info.get("effective_enabled"))),
            state or str(state_info.get("state") or "UNKNOWN"),
            attempted,
            succeeded,
            _dump(dict(details or {})),
            _utc_now(),
        ),
    )


def _percentage(numerator: int | float, denominator: int | float) -> float | None:
    if not denominator:
        return None
    return round(float(numerator) * 100.0 / float(denominator), 3)


def _state_for_ratio(value: float | None) -> str:
    return "NO_DATA" if value is None else "MEASURED"


def _rule_rows(connection: sqlite3.Connection, audit_id: str) -> list[sqlite3.Row]:
    return list(connection.execute(
        """SELECT re.rule_id,re.page_id,re.snapshot_id,re.device,re.result,re.observed_value,
                  p.normalized_url
           FROM rule_executions re
           LEFT JOIN pages p ON p.page_id=re.page_id
           WHERE re.audit_id=? ORDER BY re.rule_id,re.page_id,re.snapshot_id""",
        (audit_id,),
    ).fetchall())


def _derived_metrics(connection: sqlite3.Connection, audit_id: str) -> None:
    item = service("derived-readiness")
    page_rows = list(connection.execute(
        "SELECT page_id,normalized_url,discovery_sources FROM pages WHERE audit_id=? ORDER BY rowid",
        (audit_id,),
    ).fetchall())
    snapshots = list(connection.execute(
        """SELECT ps.*,p.normalized_url FROM page_snapshots ps
           JOIN pages p ON p.page_id=ps.page_id WHERE p.audit_id=? ORDER BY p.rowid,ps.device""",
        (audit_id,),
    ).fetchall())
    rules = _rule_rows(connection, audit_id)
    by_page_rule: dict[tuple[str, str], str] = {}
    by_snapshot_rule: dict[tuple[str, str], str] = {}
    for row in rules:
        if row["snapshot_id"]:
            by_snapshot_rule[(str(row["snapshot_id"]), str(row["rule_id"]))] = str(row["result"])
        elif row["page_id"]:
            by_page_rule[(str(row["page_id"]), str(row["rule_id"]))] = str(row["result"])

    total_pages = len(page_rows)
    crawl_pass = sum(by_page_rule.get((str(row["page_id"]), "BR-GEO-005")) == "PASS" for row in page_rows)
    crawl_known = sum(by_page_rule.get((str(row["page_id"]), "BR-GEO-005")) in {"PASS", "FAIL", "WARNING"} for row in page_rows)
    value = _percentage(crawl_pass, crawl_known)
    _record(
        connection, audit_id=audit_id, metric_id="crawlability_coverage", label="Crawlability Coverage",
        scope="URL_SET", state=_state_for_ratio(value), value=value, numerator=crawl_pass,
        denominator=crawl_known, unit="percent", source="RASAi RuleExecutions",
        methodology="BR-GEO-005 PASS / URLs with determinate technical retrievability",
        relation_degree=item.relation_degree,
        details={"audited_urls": total_pages, "unknown_or_non_determinate": total_pages - crawl_known},
    )

    snapshot_by_page: dict[str, list[sqlite3.Row]] = {}
    for snap in snapshots:
        snapshot_by_page.setdefault(str(snap["page_id"]), []).append(snap)
    index_pass = 0
    index_known = 0
    index_unknown: list[str] = []
    required_page = ("BR-GEO-005", "BR-GEO-006", "BR-GEO-009")
    required_snapshot = ("BR-GEO-011", "BR-GEO-012", "BR-GEO-016")
    for page in page_rows:
        page_id = str(page["page_id"])
        page_results = [by_page_rule.get((page_id, rule_id)) for rule_id in required_page]
        page_snaps = snapshot_by_page.get(page_id, [])
        snapshot_results = [
            [by_snapshot_rule.get((str(snap["snapshot_id"]), rule_id)) for rule_id in required_snapshot]
            for snap in page_snaps
        ]
        flat = [*page_results, *(value for group in snapshot_results for value in group)]
        if not page_snaps or any(value not in {"PASS", "FAIL", "WARNING"} for value in flat):
            index_unknown.append(str(page["normalized_url"]))
            continue
        index_known += 1
        if all(value == "PASS" for value in flat):
            index_pass += 1
    value = _percentage(index_pass, index_known)
    _record(
        connection, audit_id=audit_id, metric_id="indexability_coverage", label="Indexability Coverage",
        scope="URL_SET", state=_state_for_ratio(value), value=value, numerator=index_pass,
        denominator=index_known, unit="percent", source="RASAi RuleExecutions",
        methodology=(
            "Conservative URL aggregation over BR-GEO-005/006/009 and per-snapshot "
            "BR-GEO-011/012/016; all observed device snapshots must PASS"
        ), relation_degree=item.relation_degree,
        details={"audited_urls": total_pages, "unknown_urls": index_unknown[:100]},
    )

    sitemap_pages = 0
    for row in page_rows:
        sources = _json(row["discovery_sources"], []) or []
        if "SITEMAP" in {str(value).upper() for value in sources}:
            sitemap_pages += 1
    value = _percentage(sitemap_pages, total_pages)
    _record(
        connection, audit_id=audit_id, metric_id="sitemap_audited_url_coverage", label="Sitemap Coverage of Audited URLs",
        scope="URL_SET", state=_state_for_ratio(value), value=value, numerator=sitemap_pages,
        denominator=total_pages, unit="percent", source="RASAi discovery provenance",
        methodology="Audited URLs discovered through SITEMAP / audited URL universe",
        relation_degree=item.relation_degree,
        details={"boundary": "Measures the audited universe, not completeness of every URL that exists on the site."},
    )

    declared = [snap for snap in snapshots if str(snap["canonical"] or "").strip()]
    declared_count = len(declared)
    value = _percentage(declared_count, len(snapshots))
    _record(
        connection, audit_id=audit_id, metric_id="canonical_declaration_coverage", label="Canonical Declaration Coverage",
        scope="DEVICE_SNAPSHOT", state=_state_for_ratio(value), value=value, numerator=declared_count,
        denominator=len(snapshots), unit="percent", source="page_snapshots.canonical",
        methodology="Snapshots with an explicit canonical / snapshots observed",
        relation_degree=item.relation_degree,
    )
    valid_declared = sum(
        by_snapshot_rule.get((str(snap["snapshot_id"]), "BR-GEO-013")) == "PASS"
        for snap in declared
    )
    value = _percentage(valid_declared, declared_count)
    _record(
        connection, audit_id=audit_id, metric_id="canonical_consistency_rate", label="Canonical Consistency Rate",
        scope="DEVICE_SNAPSHOT", state=_state_for_ratio(value), value=value, numerator=valid_declared,
        denominator=declared_count, unit="percent", source="RASAi RuleExecutions",
        methodology="BR-GEO-013 PASS / snapshots with declared canonical",
        relation_degree=item.relation_degree,
    )

    sd_present = [snap for snap in snapshots if str(snap["structured_data_ref"] or "").strip()]
    value = _percentage(len(sd_present), len(snapshots))
    _record(
        connection, audit_id=audit_id, metric_id="structured_data_coverage", label="Structured Data Coverage",
        scope="DEVICE_SNAPSHOT", state=_state_for_ratio(value), value=value, numerator=len(sd_present),
        denominator=len(snapshots), unit="percent", source="page_snapshots.structured_data_ref",
        methodology="Snapshots with materialized structured data / snapshots observed",
        relation_degree=item.relation_degree,
    )
    for metric_id, label, rule_id in (
        ("structured_data_validity_rate", "Structured Data Validity Rate", "BR-GEO-034"),
        ("structured_data_visible_consistency_rate", "Structured Data to Visible Content Consistency", "BR-GEO-036"),
        ("structured_entity_consistency_rate", "Structured Entity Consistency", "BR-GEO-037"),
    ):
        applicable = [row for row in rules if row["rule_id"] == rule_id and row["result"] in {"PASS", "FAIL", "WARNING"}]
        passed = sum(row["result"] == "PASS" for row in applicable)
        value = _percentage(passed, len(applicable))
        _record(
            connection, audit_id=audit_id, metric_id=metric_id, label=label,
            scope="DEVICE_SNAPSHOT", state=_state_for_ratio(value), value=value,
            numerator=passed, denominator=len(applicable), unit="percent", source="RASAi RuleExecutions",
            methodology=f"{rule_id} PASS / determinate applicable executions",
            relation_degree=item.relation_degree,
        )

    statuses = [int(snap["http_status"]) for snap in snapshots if snap["http_status"] is not None]
    http_2xx = sum(200 <= status <= 299 for status in statuses)
    server_errors = sum(500 <= status <= 599 for status in statuses)
    for metric_id, label, numerator in (
        ("http_2xx_success_rate", "HTTP 2xx Success Rate", http_2xx),
        ("http_5xx_rate", "HTTP 5xx Rate", server_errors),
    ):
        value = _percentage(numerator, len(statuses))
        _record(
            connection, audit_id=audit_id, metric_id=metric_id, label=label,
            scope="DEVICE_SNAPSHOT", state=_state_for_ratio(value), value=value,
            numerator=numerator, denominator=len(statuses), unit="percent", source="page_snapshots.http_status",
            methodology="Observed browser snapshot HTTP status distribution",
            relation_degree=4,
        )

    ttfb_values: list[float] = []
    for snap in snapshots:
        metadata = _json(snap["browser_metadata"], {}) or {}
        metrics = metadata.get("open_web_metrics") if isinstance(metadata, dict) else None
        nav = metrics.get("navigation") if isinstance(metrics, dict) else None
        raw = nav.get("ttfb_from_navigation_start_ms") if isinstance(nav, dict) else None
        if isinstance(raw, (int, float)) and math.isfinite(float(raw)) and float(raw) >= 0:
            ttfb_values.append(float(raw))
    for percentile in (50, 75, 95, 99):
        value = _percentile(ttfb_values, percentile / 100.0)
        _record(
            connection, audit_id=audit_id, metric_id=f"ttfb_p{percentile}", label=f"TTFB p{percentile}",
            scope="DEVICE_SNAPSHOT", state="NO_DATA" if value is None else "MEASURED", value=value,
            denominator=len(ttfb_values), unit="ms", source="OPEN-WEB-METRICS-001",
            methodology=f"Percentile p{percentile} of browser Navigation Timing TTFB observations",
            relation_degree=4,
        )


def _percentile(values: Iterable[float], q: float) -> float | None:
    ordered = sorted(float(value) for value in values)
    if not ordered:
        return None
    if len(ordered) == 1:
        return round(ordered[0], 3)
    position = (len(ordered) - 1) * q
    low = math.floor(position)
    high = math.ceil(position)
    if low == high:
        return round(ordered[low], 3)
    fraction = position - low
    return round(ordered[low] + (ordered[high] - ordered[low]) * fraction, 3)


def precision_at_k(grades: Iterable[float], k: int) -> float | None:
    values = list(grades)[:k]
    if not values or k <= 0:
        return None
    return sum(value > 0 for value in values) / len(values)


def reciprocal_rank(grades: Iterable[float]) -> float:
    for index, value in enumerate(grades, start=1):
        if value > 0:
            return 1.0 / index
    return 0.0


def ndcg_at_k(grades: Iterable[float], k: int) -> float | None:
    values = [max(0.0, float(value)) for value in list(grades)[:k]]
    if not values or k <= 0:
        return None
    def dcg(items: list[float]) -> float:
        return sum((2.0 ** grade - 1.0) / math.log2(index + 2.0) for index, grade in enumerate(items))
    ideal = dcg(sorted(values, reverse=True))
    if ideal <= 0:
        return 0.0
    return dcg(values) / ideal


def _retrieval_metrics(connection: sqlite3.Connection, audit_id: str) -> None:
    item = service("retrieval-metrics")
    exists = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='serp_observations'"
    ).fetchone()
    if exists is None:
        _record(
            connection, audit_id=audit_id, metric_id="domain_mrr", label="Domain Mean Reciprocal Rank",
            scope="SEARCH_QUERY", state="NO_DATA", source="Search Intelligence",
            methodology="Mean reciprocal rank of the domain of interest across persisted SERP observations",
            relation_degree=item.relation_degree,
            details={"reason": "SERP_OBSERVATIONS_NOT_AVAILABLE"},
        )
        return
    observations = list(connection.execute(
        """SELECT observation_id,query,domain_of_interest,customer_position,observation_status,quality_metadata
           FROM serp_observations WHERE audit_id=? AND domain_of_interest IS NOT NULL
           ORDER BY collected_at""",
        (audit_id,),
    ).fetchall())
    if not observations:
        _record(
            connection, audit_id=audit_id, metric_id="domain_mrr", label="Domain Mean Reciprocal Rank",
            scope="SEARCH_QUERY", state="NO_DATA", source="Search Intelligence",
            methodology="Mean reciprocal rank of the domain of interest across persisted SERP observations",
            relation_degree=item.relation_degree,
            details={"reason": "NO_DOMAIN_SERP_OBSERVATIONS"},
        )
        return
    reciprocals = [0.0 if row["customer_position"] is None else 1.0 / max(1, int(row["customer_position"])) for row in observations]
    found = sum(row["customer_position"] is not None for row in observations)
    mrr = fmean(reciprocals)
    _record(
        connection, audit_id=audit_id, metric_id="domain_mrr", label="Domain Mean Reciprocal Rank",
        scope="SEARCH_QUERY", state="MEASURED", value=round(mrr, 6), numerator=sum(reciprocals),
        denominator=len(reciprocals), unit="ratio", source="Search Intelligence SERP observations",
        methodology="Mean of 1/rank for the configured domain; not-found observations contribute zero",
        relation_degree=item.relation_degree,
        details={"queries_observed": len(observations), "domain_found": found},
    )
    visibility = _percentage(found, len(observations))
    _record(
        connection, audit_id=audit_id, metric_id="domain_serp_visibility_rate", label="Domain SERP Visibility Rate",
        scope="SEARCH_QUERY", state="MEASURED", value=visibility, numerator=found,
        denominator=len(observations), unit="percent", source="Search Intelligence SERP observations",
        methodology="Queries where domain was observed / queries with persisted observation",
        relation_degree=item.relation_degree,
    )

    if connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='serp_results'").fetchone() is None:
        return
    precision_values: list[float] = []
    ndcg_values: list[float] = []
    rr_values: list[float] = []
    judged_queries = 0
    for obs in observations:
        rows = connection.execute(
            "SELECT position,metadata FROM serp_results WHERE observation_id=? ORDER BY position",
            (obs["observation_id"],),
        ).fetchall()
        grades: list[float] = []
        has_judgment = False
        for row in rows:
            metadata = _json(row["metadata"], {}) or {}
            raw_grade = metadata.get("relevance_grade") if isinstance(metadata, dict) else None
            if raw_grade is None and isinstance(metadata, dict) and "relevant" in metadata:
                raw_grade = 1 if bool(metadata.get("relevant")) else 0
            if raw_grade is None:
                grades.append(0.0)
                continue
            try:
                grade = max(0.0, float(raw_grade))
            except (TypeError, ValueError):
                grade = 0.0
            grades.append(grade)
            has_judgment = True
        if not has_judgment:
            continue
        judged_queries += 1
        p = precision_at_k(grades, 10)
        n = ndcg_at_k(grades, 10)
        if p is not None:
            precision_values.append(p)
        if n is not None:
            ndcg_values.append(n)
        rr_values.append(reciprocal_rank(grades))
    for metric_id, label, values in (
        ("precision_at_10", "Precision@10", precision_values),
        ("ndcg_at_10", "nDCG@10", ndcg_values),
        ("judged_mrr", "Judged-result MRR", rr_values),
    ):
        value = None if not values else round(fmean(values), 6)
        _record(
            connection, audit_id=audit_id, metric_id=metric_id, label=label,
            scope="SEARCH_QUERY", state="NO_DATA" if value is None else "MEASURED", value=value,
            denominator=len(values), unit="ratio", source="Search Intelligence relevance judgments",
            methodology="Classical Information Retrieval metric over explicit persisted relevance judgments",
            relation_degree=item.relation_degree,
            details={"judged_queries": judged_queries, "boundary": "No relevance is inferred when qrels/judgments are absent."},
        )


def _request_json(request: Request, timeout: float) -> dict[str, Any]:
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8", errors="replace"))
    except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        raise StandardsExternalError(f"{type(exc).__name__}: {exc}") from exc
    if not isinstance(payload, dict):
        raise StandardsExternalError("external service returned a non-object JSON payload")
    return payload


def _w3c_validator(connection: sqlite3.Connection, audit_id: str, max_urls: int, timeout: float) -> tuple[int, int, dict[str, Any]]:
    item = service("w3c-validator")
    pages = list(connection.execute(
        "SELECT normalized_url FROM pages WHERE audit_id=? ORDER BY rowid",
        (audit_id,),
    ).fetchall())
    urls = [str(row[0]) for row in pages]
    if max_urls:
        urls = urls[:max_urls]
    attempted = succeeded = 0
    for url in urls:
        attempted += 1
        endpoint = W3C_VALIDATOR_ENDPOINT + "?" + urlencode({"doc": url, "out": "json"})
        request = Request(endpoint, headers={"Accept": "application/json", "User-Agent": "RASAi-Readiness-Auditor/0.1"})
        try:
            payload = _request_json(request, timeout)
            messages = payload.get("messages") if isinstance(payload.get("messages"), list) else []
            errors = sum(isinstance(message, dict) and message.get("type") == "error" for message in messages)
            non_document = sum(isinstance(message, dict) and message.get("type") == "non-document-error" for message in messages)
            warnings = sum(
                isinstance(message, dict) and message.get("type") == "info" and message.get("subtype") == "warning"
                for message in messages
            )
            if non_document:
                outcome = "INDETERMINATE"
            elif errors:
                outcome = "FAIL"
            else:
                outcome = "PASS"
            succeeded += 1
            _record(
                connection, audit_id=audit_id, metric_id="w3c_html_conformance", label="W3C HTML Conformance",
                scope="URL", target=url, state=outcome, value=float(errors), unit="error_count",
                source="W3C Nu HTML Checker", methodology="W3C Nu Checker out=json outcome",
                relation_degree=item.relation_degree,
                details={"errors": errors, "warnings": warnings, "non_document_errors": non_document, "message_count": len(messages)},
            )
        except StandardsExternalError as exc:
            _record(
                connection, audit_id=audit_id, metric_id="w3c_html_conformance", label="W3C HTML Conformance",
                scope="URL", target=url, state="ERROR", source="W3C Nu HTML Checker",
                methodology="W3C Nu Checker out=json outcome", relation_degree=item.relation_degree,
                details={"error": str(exc)[:500]},
            )
    return attempted, succeeded, {"max_urls": max_urls, "endpoint": W3C_VALIDATOR_ENDPOINT}


def _mdn_observatory(connection: sqlite3.Connection, audit_id: str, timeout: float) -> tuple[int, int, dict[str, Any]]:
    item = service("mdn-observatory")
    targets = list(connection.execute(
        "SELECT DISTINCT normalized_origin FROM audit_targets WHERE audit_id=? ORDER BY normalized_origin",
        (audit_id,),
    ).fetchall())
    attempted = succeeded = 0
    details: dict[str, Any] = {"endpoint": MDN_OBSERVATORY_ENDPOINT}
    for row in targets:
        origin = str(row[0])
        host = urlparse(origin).hostname
        if not host:
            continue
        attempted += 1
        endpoint = MDN_OBSERVATORY_ENDPOINT + "?" + urlencode({"host": host})
        request = Request(endpoint, data=b"", method="POST", headers={"Accept": "application/json", "User-Agent": "RASAi-Readiness-Auditor/0.1"})
        try:
            payload = _request_json(request, timeout)
            if payload.get("error"):
                raise StandardsExternalError(str(payload.get("message") or payload.get("error")))
            succeeded += 1
            score = payload.get("score")
            score_value = float(score) if isinstance(score, (int, float)) else None
            _record(
                connection, audit_id=audit_id, metric_id="mdn_http_observatory", label="MDN HTTP Observatory",
                scope="ORIGIN", target=origin, state="MEASURED", value=score_value, unit="source_score",
                source="MDN HTTP Observatory", methodology="MDN HTTP Observatory API v2 source grade/score",
                relation_degree=item.relation_degree,
                details={
                    "grade": payload.get("grade"), "score": score, "tests_failed": payload.get("tests_failed"),
                    "tests_passed": payload.get("tests_passed"), "tests_quantity": payload.get("tests_quantity"),
                    "algorithm_version": payload.get("algorithm_version"), "scanned_at": payload.get("scanned_at"),
                    "details_url": payload.get("details_url"),
                },
            )
        except StandardsExternalError as exc:
            _record(
                connection, audit_id=audit_id, metric_id="mdn_http_observatory", label="MDN HTTP Observatory",
                scope="ORIGIN", target=origin, state="ERROR", source="MDN HTTP Observatory",
                methodology="MDN HTTP Observatory API v2 source grade/score", relation_degree=item.relation_degree,
                details={"error": str(exc)[:500]},
            )
    return attempted, succeeded, details


def execute_standards_metrics(
    *,
    audit_id: str,
    workspace: AuditWorkspace,
    env: Mapping[str, str] | None = None,
) -> None:
    environment = env if env is not None else os.environ
    max_urls = _nonnegative_int(environment.get(STANDARDS_MAX_URLS_ENV), DEFAULT_STANDARDS_MAX_URLS)
    timeout = _positive_float(environment.get(STANDARDS_TIMEOUT_ENV), DEFAULT_STANDARDS_TIMEOUT_SECONDS)
    connection = sqlite3.connect(workspace.database)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        with connection:
            _init(connection)
            connection.execute("DELETE FROM standards_metric_observations WHERE audit_id=?", (audit_id,))
            connection.execute("DELETE FROM standards_service_runs WHERE audit_id=?", (audit_id,))

            states = {str(item["id"]): item for item in service_states(environment)}
            derived = states["derived-readiness"]
            if bool(derived["effective_enabled"]):
                _derived_metrics(connection, audit_id)
                _service_run(connection, audit_id=audit_id, service_id="derived-readiness", state_info=derived, state="SUCCESS", succeeded=1)
            else:
                _service_run(connection, audit_id=audit_id, service_id="derived-readiness", state_info=derived)

            retrieval = states["retrieval-metrics"]
            if bool(retrieval["effective_enabled"]):
                _retrieval_metrics(connection, audit_id)
                _service_run(connection, audit_id=audit_id, service_id="retrieval-metrics", state_info=retrieval, state="SUCCESS", succeeded=1)
            else:
                _service_run(connection, audit_id=audit_id, service_id="retrieval-metrics", state_info=retrieval)

            for service_id, runner in (
                ("w3c-validator", lambda: _w3c_validator(connection, audit_id, max_urls, timeout)),
                ("mdn-observatory", lambda: _mdn_observatory(connection, audit_id, timeout)),
            ):
                state_info = states[service_id]
                if not bool(state_info["effective_enabled"]):
                    _service_run(connection, audit_id=audit_id, service_id=service_id, state_info=state_info)
                    continue
                attempted = succeeded = 0
                details: dict[str, Any] = {}
                try:
                    attempted, succeeded, details = runner()
                    state = "SUCCESS" if attempted and attempted == succeeded else "PARTIAL" if succeeded else "NO_DATA"
                except Exception as exc:
                    state = "ERROR"
                    details = {"error": f"{type(exc).__name__}: {str(exc)[:500]}"}
                _service_run(
                    connection, audit_id=audit_id, service_id=service_id, state_info=state_info,
                    state=state, attempted=attempted, succeeded=succeeded, details=details,
                )

            baseline = states["web-platform-baseline"]
            baseline_details = {
                "dataset": environment.get("RASAI_WEB_FEATURES_DATASET"),
                "reason": "Feature usage detection is not inferred without a versioned web-features mapping pipeline.",
            }
            baseline_state = "NO_DATA" if bool(baseline["effective_enabled"]) else str(baseline["state"])
            _service_run(connection, audit_id=audit_id, service_id="web-platform-baseline", state_info=baseline, state=baseline_state, details=baseline_details)

            # Existing integrations remain owned by their canonical modules. The service
            # matrix records readiness without duplicating their acquisitions here.
            for service_id in ("open-web-metrics", "pagespeed", "crux", "google-search-console"):
                state_info = states[service_id]
                _service_run(connection, audit_id=audit_id, service_id=service_id, state_info=state_info)
    finally:
        connection.close()


def load_metrics(audit_id: str, workspace: AuditWorkspace) -> tuple[dict[str, Any], ...]:
    connection = sqlite3.connect(workspace.database)
    connection.row_factory = sqlite3.Row
    try:
        if connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='standards_metric_observations'").fetchone() is None:
            return ()
        rows = connection.execute(
            "SELECT * FROM standards_metric_observations WHERE audit_id=? ORDER BY relation_degree DESC,metric_id,target,device",
            (audit_id,),
        ).fetchall()
        return tuple({**dict(row), "details": _json(row["details_json"], {}) or {}} for row in rows)
    finally:
        connection.close()


def load_service_runs(audit_id: str, workspace: AuditWorkspace) -> tuple[dict[str, Any], ...]:
    connection = sqlite3.connect(workspace.database)
    connection.row_factory = sqlite3.Row
    try:
        if connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='standards_service_runs'").fetchone() is None:
            return ()
        rows = connection.execute(
            "SELECT * FROM standards_service_runs WHERE audit_id=? ORDER BY service_id", (audit_id,)
        ).fetchall()
        return tuple({**dict(row), "details": _json(row["details_json"], {}) or {}} for row in rows)
    finally:
        connection.close()


def _fmt_metric(row: Mapping[str, Any]) -> str:
    value = row.get("value")
    unit = str(row.get("unit") or "")
    if value is None:
        return escape(str(row.get("state") or "N/A"))
    numeric = float(value)
    if unit == "percent":
        return f"{numeric:.1f}%"
    if unit == "ms":
        return f"{numeric:.0f} ms"
    if unit == "ratio":
        return f"{numeric:.3f}"
    if unit == "error_count":
        return f"{numeric:.0f} erro(s)"
    return f"{numeric:g}"


def write_standards_report(*, audit_id: str, workspace: AuditWorkspace) -> Path:
    from rasai import report_navigation
    report_dir = workspace.root / "report"
    report_dir.mkdir(parents=True, exist_ok=True)
    path = report_dir / REPORT_FILE
    metrics = load_metrics(audit_id, workspace)
    runs = load_service_runs(audit_id, workspace)
    nav = report_navigation.render_report_navigation(report_dir, REPORT_FILE)

    headline_ids = (
        "crawlability_coverage", "indexability_coverage", "canonical_consistency_rate",
        "structured_data_coverage", "domain_mrr", "ttfb_p95",
    )
    first_by_id: dict[str, dict[str, Any]] = {}
    for row in metrics:
        first_by_id.setdefault(str(row["metric_id"]), row)
    cards = []
    for metric_id in headline_ids:
        row = first_by_id.get(metric_id)
        if row is None:
            continue
        cards.append(
            "<div class='metric'><small>" + escape(str(row["label"])) + "</small><strong>" + _fmt_metric(row) +
            "</strong><span>Relação RASAi " + str(row["relation_degree"]) + "/5</span></div>"
        )

    service_rows = []
    registry = {item.id: item for item in __import__("rasai.standards_service_registry", fromlist=["services"]).services()}
    for run in runs:
        item = registry.get(str(run["service_id"]))
        if item is None:
            continue
        service_rows.append(
            "<tr><td><strong>" + escape(item.label) + "</strong><br><small>" + escape(item.purpose) + "</small></td>"
            + f"<td>{item.relation_degree}/5</td><td>{escape(', '.join(item.scopes))}</td>"
            + f"<td>{escape(str(run['state']))}</td><td><code>{escape(item.enabled_env)}</code></td>"
            + f"<td>{'sim' if item.credential_envs else 'não'}</td></tr>"
        )

    metric_rows = []
    for row in metrics:
        metric_rows.append(
            "<tr><td><strong>" + escape(str(row["label"])) + "</strong><br><code>" + escape(str(row["metric_id"])) + "</code></td>"
            + f"<td>{escape(str(row['scope']))}</td><td>{escape(str(row['target'] or '-'))}</td>"
            + f"<td>{_fmt_metric(row)}</td><td>{escape(str(row['state']))}</td><td>{row['relation_degree']}/5</td>"
            + f"<td>{escape(str(row['source']))}</td></tr>"
        )

    html = f"""<!doctype html>
<html lang='pt-BR'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
<title>RASAi · Métricas e padrões</title><link rel='stylesheet' href='css/site.css'></head><body>
<div class='app-shell'>{nav}<main class='app-main'>
<header class='hero'><div class='eyebrow'>Métricas e padrões · {CONTRACT_VERSION}</div>
<h1>Métricas fundamentadas e serviços de referência</h1>
<p>Esta página separa métricas derivadas RASAi de scores emitidos por fontes externas. Nenhum item desta superfície altera SARI-001/SCORE-GEO-004 sem uma mudança metodológica explícita e versionada.</p></header>
<section class='panel'><h2>Resumo</h2><div class='metric-grid'>{''.join(cards) or '<p>Sem métricas materializadas.</p>'}</div></section>
<section class='panel'><h2>Serviços e controles</h2><p>Serviços sem credencial e sem cobrança de provider são habilitados por default. Serviços que exigem credencial permanecem desabilitados até a credencial existir. Todos possuem toggle explícito.</p>
<div class='table-wrap'><table><thead><tr><th>Serviço</th><th>Relação</th><th>Escopo</th><th>Estado</th><th>Toggle</th><th>Credencial</th></tr></thead><tbody>{''.join(service_rows)}</tbody></table></div></section>
<section class='panel'><h2>Observações materializadas</h2>
<div class='table-wrap'><table><thead><tr><th>Métrica</th><th>Escopo</th><th>Alvo</th><th>Valor</th><th>Estado</th><th>Relação</th><th>Fonte</th></tr></thead><tbody>{''.join(metric_rows)}</tbody></table></div></section>
<section class='panel'><h2>Fronteiras metodológicas</h2><div class='notice'>Crawlability, Indexability, Sitemap Coverage e consolidações semelhantes são métricas derivadas RASAi, com fórmulas explícitas sobre evidência persistida. W3C Nu não fornece um score oficial; o RASAi preserva apenas outcome e contagens. MDN Observatory preserva grade/score da própria fonte. nDCG/Precision não são inferidos sem julgamentos de relevância explícitos.</div></section>
<footer class='footer'>RASAi · métricas advisory e evidence-bound · não altera scoring</footer>
</main></div></body></html>"""
    path.write_text(html, encoding="utf-8", newline="\n")
    return path


def _insert_panel(path: Path, marker: str, html: str) -> None:
    if not path.is_file():
        return
    text = path.read_text(encoding="utf-8")
    if marker in text:
        return
    block = f"<!-- {marker}:START -->{html}<!-- {marker}:END -->"
    if "</main>" in text:
        text = text.replace("</main>", block + "</main>", 1)
    else:
        text = text.replace("</body>", block + "</body>", 1)
    path.write_text(text, encoding="utf-8", newline="\n")


def enrich_existing_reports(*, audit_id: str, workspace: AuditWorkspace) -> None:
    metrics = load_metrics(audit_id, workspace)
    by_id: dict[str, dict[str, Any]] = {}
    for row in metrics:
        by_id.setdefault(str(row["metric_id"]), row)
    summary_ids = (
        "crawlability_coverage", "indexability_coverage", "sitemap_audited_url_coverage",
        "canonical_consistency_rate", "structured_data_coverage", "domain_mrr",
    )
    cards = []
    for metric_id in summary_ids:
        row = by_id.get(metric_id)
        if row is None:
            continue
        cards.append(
            f"<div class='metric'><small>{escape(str(row['label']))}</small><strong>{_fmt_metric(row)}</strong>"
            f"<span>Relação {row['relation_degree']}/5 · {escape(str(row['scope']))}</span></div>"
        )
    if cards:
        _insert_panel(
            workspace.root / "report" / "index.html", "RASAI_STANDARDS_OVERVIEW",
            "<section class='panel'><h2>Métricas de Search, AI e padrões</h2><p>Consolidações derivadas são identificadas separadamente do SARI. Escopos URL, origem, device e query não são misturados.</p><div class='metric-grid'>"
            + "".join(cards) + "</div><p><a href='standards.html'>Abrir métricas, serviços e metodologia</a></p></section>",
        )

    discovery_ids = (
        "crawlability_coverage", "indexability_coverage", "sitemap_audited_url_coverage",
        "canonical_declaration_coverage", "canonical_consistency_rate", "structured_data_coverage",
        "structured_data_validity_rate", "structured_data_visible_consistency_rate",
    )
    discovery_cards = [
        f"<div class='metric'><small>{escape(str(by_id[mid]['label']))}</small><strong>{_fmt_metric(by_id[mid])}</strong></div>"
        for mid in discovery_ids if mid in by_id
    ]
    if discovery_cards:
        _insert_panel(
            workspace.root / "report" / "crawling-discovery.html", "RASAI_DERIVED_DISCOVERY_METRICS",
            "<section class='panel'><h2>Métricas derivadas de descoberta e indexabilidade</h2><p>Estas consolidações reutilizam RuleExecutions e proveniência já persistidos; não são scores oficiais do Google e não adicionam peso ao SARI.</p><div class='metric-grid'>"
            + "".join(discovery_cards) + "</div></section>",
        )

    search_ids = ("domain_mrr", "domain_serp_visibility_rate", "precision_at_10", "ndcg_at_10", "judged_mrr")
    search_cards = [
        f"<div class='metric'><small>{escape(str(by_id[mid]['label']))}</small><strong>{_fmt_metric(by_id[mid])}</strong></div>"
        for mid in search_ids if mid in by_id
    ]
    if search_cards:
        _insert_panel(
            workspace.root / "report" / "search-intelligence.html", "RASAI_RETRIEVAL_METRICS",
            "<section class='panel'><h2>Métricas de Information Retrieval</h2><p>MRR do domínio usa a posição observada por query. Precision/nDCG somente aparecem quando relevance judgments explícitos estão persistidos.</p><div class='metric-grid'>"
            + "".join(search_cards) + "</div></section>",
        )
