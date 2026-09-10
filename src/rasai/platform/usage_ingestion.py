"""Read-only projection of execution telemetry into the Product Platform usage ledger.

The immutable ``AUD-*/audit.db`` remains the source evidence. This module opens it
read-only and emits idempotent usage events into the control plane, so SaaS analytics
can aggregate by tenant/user/domain/URL/provider without mutating historical AUDs.
"""
from __future__ import annotations

from pathlib import Path
import sqlite3
from typing import Any
from urllib.parse import urlsplit


def _table_exists(connection: sqlite3.Connection, table: str) -> bool:
    row = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    return row is not None


def _row_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()}


def _host(url: str | None) -> str | None:
    if not url:
        return None
    return (urlsplit(str(url)).hostname or "").lower() or None


def _metadata(
    row: dict[str, Any],
    *,
    user_id: str | None,
    environment_id: str,
    job_id: str,
    operation: str,
    resource_type: str,
    url: str | None = None,
) -> dict[str, Any]:
    resolved_url = url or row.get("url") or row.get("normalized_url")
    result: dict[str, Any] = {
        "user_id": user_id,
        "environment_id": environment_id,
        "job_id": job_id,
        "operation": operation,
        "resource_type": resource_type,
        "url": resolved_url,
        "domain": _host(resolved_url),
        "status": row.get("status"),
        "model": row.get("model"),
        "duration_ms": row.get("duration_ms"),
        "input_tokens": row.get("input_tokens"),
        "cached_input_tokens": row.get("cached_input_tokens"),
        "output_tokens": row.get("output_tokens"),
        "reasoning_tokens": row.get("reasoning_tokens"),
        "total_tokens": row.get("total_tokens"),
        "decision": row.get("decision"),
        "retry": bool(row.get("retry_eligible")) and str(row.get("decision") or "").upper() == "RETRY",
        "fallback_from_provider": row.get("fallback_from_provider"),
        "error_code": row.get("error_code"),
        "http_status": row.get("http_status"),
        "device": row.get("device"),
    }
    return {key: value for key, value in result.items() if value is not None}


def ingest_audit_usage(
    store: Any,
    audit: Any,
    *,
    organization_id: str,
    project_id: str,
    property_id: str,
    environment_id: str,
    user_id: str | None,
    job_id: str,
) -> int:
    """Project known telemetry tables from one completed AUD into usage_events."""
    database = Path(audit.workspace_path) / "audit.db"
    if not database.is_file():
        return 0
    connection = sqlite3.connect(f"file:{database.as_posix()}?mode=ro", uri=True, timeout=1.0)
    connection.row_factory = sqlite3.Row
    inserted = 0
    try:
        page_urls: dict[str, str] = {}
        if _table_exists(connection, "pages"):
            for row in connection.execute("SELECT page_id,normalized_url FROM pages WHERE audit_id=?", (audit.audit_id,)):
                page_urls[str(row["page_id"])] = str(row["normalized_url"])

        # One auditable processed-URL event per page. This is independent from any
        # provider and gives a stable denominator for domain/URL consumption views.
        for page_id, url in page_urls.items():
            result = store.record_usage_once(
                source_key=f"audit:{audit.audit_id}:page:{page_id}",
                organization_id=organization_id,
                project_id=project_id,
                property_id=property_id,
                audit_id=audit.audit_id,
                category="URL_PROCESSED",
                quantity=1,
                unit="url",
                metadata={
                    "environment_id": environment_id,
                    "user_id": user_id,
                    "job_id": job_id,
                    "operation": "AUDIT",
                    "resource_type": "CRAWLING",
                    "url": url,
                    "domain": _host(url),
                    "status": audit.status,
                },
                occurred_at=audit.event_time,
            )
            inserted += int(result.get("usage_event_id") is not None)

        if _table_exists(connection, "page_snapshots"):
            rows = connection.execute(
                """SELECT ps.snapshot_id,ps.page_id,ps.device,p.normalized_url
                   FROM page_snapshots ps JOIN pages p ON p.page_id=ps.page_id
                   WHERE p.audit_id=?""",
                (audit.audit_id,),
            ).fetchall()
            for raw in rows:
                row = _row_dict(raw)
                result = store.record_usage_once(
                    source_key=f"audit:{audit.audit_id}:browser:{row['snapshot_id']}",
                    organization_id=organization_id,
                    project_id=project_id,
                    property_id=property_id,
                    audit_id=audit.audit_id,
                    category="BROWSER_EXECUTION",
                    quantity=1,
                    unit="execution",
                    provider="PLAYWRIGHT",
                    metadata=_metadata(
                        row,
                        user_id=user_id,
                        environment_id=environment_id,
                        job_id=job_id,
                        operation="RENDER",
                        resource_type="BROWSER",
                    ),
                    occurred_at=audit.event_time,
                )
                inserted += int(result.get("usage_event_id") is not None)

        for table, operation in (
            ("ai_provider_attempts", "SEMANTIC_ANALYSIS"),
            ("content_remediation_attempts", "CONTENT_REMEDIATION"),
        ):
            if not _table_exists(connection, table):
                continue
            for raw in connection.execute(f"SELECT * FROM {table} WHERE audit_id=?", (audit.audit_id,)):
                row = _row_dict(raw)
                attempt_id = str(row.get("attempt_id") or "unknown")
                result = store.record_usage_once(
                    source_key=f"audit:{audit.audit_id}:{table}:{attempt_id}",
                    organization_id=organization_id,
                    project_id=project_id,
                    property_id=property_id,
                    audit_id=audit.audit_id,
                    category="AI_PROVIDER_CALL",
                    quantity=1,
                    unit="call",
                    cost_estimate=row.get("estimated_cost"),
                    currency=row.get("cost_currency"),
                    provider=row.get("provider"),
                    metadata=_metadata(
                        row,
                        user_id=user_id,
                        environment_id=environment_id,
                        job_id=job_id,
                        operation=operation,
                        resource_type="AI",
                    ),
                    occurred_at=row.get("started_at") or audit.event_time,
                )
                inserted += int(result.get("usage_event_id") is not None)

        if _table_exists(connection, "web_performance_attempts"):
            for raw in connection.execute("SELECT * FROM web_performance_attempts WHERE audit_id=?", (audit.audit_id,)):
                row = _row_dict(raw)
                attempt_id = str(row.get("attempt_id") or f"{row.get('service')}:{row.get('page_id')}:{row.get('created_at')}")
                url = page_urls.get(str(row.get("page_id") or ""))
                result = store.record_usage_once(
                    source_key=f"audit:{audit.audit_id}:web-performance:{attempt_id}",
                    organization_id=organization_id,
                    project_id=project_id,
                    property_id=property_id,
                    audit_id=audit.audit_id,
                    category="INTEGRATION_CALL",
                    quantity=1,
                    unit="call",
                    provider=row.get("service"),
                    metadata=_metadata(
                        row,
                        user_id=user_id,
                        environment_id=environment_id,
                        job_id=job_id,
                        operation="WEB_PERFORMANCE",
                        resource_type="INTEGRATION",
                        url=url,
                    ),
                    occurred_at=row.get("created_at") or audit.event_time,
                )
                inserted += int(result.get("usage_event_id") is not None)
    finally:
        connection.close()
    return inserted


def record_search_monitor_usage(store: Any, job: Any, run: Any) -> int:
    """Record provider/resource counts exposed by SEARCH-MONITOR-001."""
    inserted = 0
    common = {
        "organization_id": job.organization_id,
        "project_id": job.project_id,
        "property_id": job.property_id,
        "audit_id": None,
    }
    metadata = {
        "environment_id": job.environment_id,
        "user_id": job.requested_by,
        "job_id": job.job_id,
        "operation": "SEARCH_MONITOR",
        "resource_type": "SEARCH",
        "query_id": run.query_id,
        "status": run.status,
    }
    counts = (
        ("SERP_PROVIDER_CALL", int(run.serp_http_requests or 0), "call", run.provider, "SERP"),
        ("CONTENT_FETCH", int(run.content_http_requests or 0), "request", None, "CONTENT"),
        ("AI_PROVIDER_CALL", int(run.ai_provider_calls or 0), "call", run.ai_provider, "AI"),
    )
    for category, quantity, unit, provider, resource in counts:
        if quantity <= 0:
            continue
        result = store.record_usage_once(
            source_key=f"search:{run.monitor_run_id}:{category}",
            category=category,
            quantity=quantity,
            unit=unit,
            provider=provider,
            metadata={**metadata, "resource_type": resource},
            occurred_at=run.completed_at,
            **common,
        )
        inserted += int(result.get("usage_event_id") is not None)
    return inserted
