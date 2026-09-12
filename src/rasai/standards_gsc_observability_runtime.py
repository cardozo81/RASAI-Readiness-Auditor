"""Bounded Search Console collection composed into audit finalization.

The external data is persisted in observability.db/artifacts, not promoted to SARI or
SCORE-GEO evidence. audit.db stores standards-service execution state plus advisory
metrics derived from already-persisted GSC observations.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import os
import sqlite3
from typing import Any, Mapping

from rasai.observability.google_search_console import collect_search_analytics, collect_url_inspection
from rasai.observability.gsc_resources import collect_sitemaps
from rasai.observability.reporting import enrich_observability_report
from rasai.secret_safety import redact_text
from rasai.standards_gsc_policy import (
    GSC_FINAL_DATA_LAG_DAYS_ENV,
    GSC_SEARCH_ANALYTICS_DAYS_ENV,
    GSC_SEARCH_MAX_ROWS_ENV,
    final_data_lag_days,
    search_analytics_days,
    search_max_rows,
)
from rasai.standards_service_registry import (
    DEFAULT_STANDARDS_MAX_URLS,
    DEFAULT_STANDARDS_TIMEOUT_SECONDS,
    GSC_SITE_URL_ENV,
    STANDARDS_MAX_URLS_ENV,
    STANDARDS_TIMEOUT_ENV,
    service,
    service_state,
)

GSC_TOKEN_ENV = "RASAI_GOOGLE_SEARCH_CONSOLE_ACCESS_TOKEN"


def _bounded_urls(workspace: Any, audit_id: str, limit: int) -> tuple[str, ...]:
    connection = sqlite3.connect(workspace.database)
    try:
        rows = connection.execute(
            "SELECT normalized_url FROM pages WHERE audit_id=? ORDER BY rowid",
            (audit_id,),
        ).fetchall()
    finally:
        connection.close()
    values = tuple(str(row[0]) for row in rows)
    return values if limit == 0 else values[:limit]


def _int_env(environment: Mapping[str, str], name: str, default: int, *, minimum: int = 0) -> int:
    raw = str(environment.get(name) or "").strip()
    value = default if not raw else int(raw)
    if value < minimum:
        raise ValueError(f"{name} must be >= {minimum}")
    return value


def _float_env(environment: Mapping[str, str], name: str, default: float) -> float:
    raw = str(environment.get(name) or "").strip()
    value = default if not raw else float(raw)
    if value <= 0:
        raise ValueError(f"{name} must be > 0")
    return value


def collect_configured_search_console(
    *,
    audit_id: str,
    workspace: Any,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    environment = env if env is not None else os.environ
    state_info = service_state(service("google-search-console"), environment)
    result: dict[str, Any] = {
        "service_state": str(state_info["state"]),
        "requested": bool(state_info["requested"]),
        "configured": bool(state_info["configured"]),
        "effective_enabled": bool(state_info["effective_enabled"]),
        "operations": [],
        "errors": [],
    }
    if not bool(state_info["effective_enabled"]):
        return result

    token = str(environment.get(GSC_TOKEN_ENV) or "").strip()
    site_url = str(environment.get(GSC_SITE_URL_ENV) or "").strip()
    max_urls = _int_env(environment, STANDARDS_MAX_URLS_ENV, DEFAULT_STANDARDS_MAX_URLS)
    timeout = _float_env(environment, STANDARDS_TIMEOUT_ENV, DEFAULT_STANDARDS_TIMEOUT_SECONDS)
    days = search_analytics_days(environment.get(GSC_SEARCH_ANALYTICS_DAYS_ENV))
    max_rows = search_max_rows(environment.get(GSC_SEARCH_MAX_ROWS_ENV))
    lag_days = final_data_lag_days(environment.get(GSC_FINAL_DATA_LAG_DAYS_ENV))
    urls = _bounded_urls(workspace, audit_id, max_urls)

    # These counters represent logical API collection operations, not URL-level
    # successes. URL Inspection persists per-URL ERROR rows in observability.db and its
    # own report shows that finer-grained outcome without overstating this run summary.
    attempted = 0
    succeeded = 0

    def run_operation(name: str, callback: Any, **metadata: Any) -> None:
        nonlocal attempted, succeeded
        attempted += 1
        try:
            dataset_id = callback()
            succeeded += 1
            result["operations"].append({
                "name": name,
                "status": "SUCCESS",
                "dataset_id": dataset_id,
                **metadata,
            })
        except Exception as exc:
            message = redact_text(f"{name}:{type(exc).__name__}:{str(exc)[:400]}")
            result["operations"].append({"name": name, "status": "ERROR", **metadata})
            result["errors"].append(message)

    run_operation(
        "SITEMAPS",
        lambda: collect_sitemaps(
            audit_workspace=workspace.root,
            site_url=site_url,
            access_token=token,
            timeout=timeout,
        ),
        property=site_url,
    )

    if urls:
        run_operation(
            "URL_INSPECTION",
            lambda: collect_url_inspection(
                audit_workspace=workspace.root,
                site_url=site_url,
                access_token=token,
                urls=urls,
                timeout=timeout,
            ),
            requested_urls=len(urls),
        )

    if days > 0:
        end_date = datetime.now(timezone.utc).date() - timedelta(days=lag_days)
        start_date = end_date - timedelta(days=days - 1)
        result["search_analytics_period"] = {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "data_state": "final",
            "days": days,
            "lag_days": lag_days,
            "max_rows": max_rows,
        }
        run_operation(
            "SEARCH_ANALYTICS",
            lambda: collect_search_analytics(
                audit_workspace=workspace.root,
                site_url=site_url,
                access_token=token,
                start_date=start_date.isoformat(),
                end_date=end_date.isoformat(),
                max_rows=max_rows,
                data_state="final",
                timeout=timeout,
            ),
            days=days,
            max_rows=max_rows,
        )

    result["targets_attempted"] = attempted
    result["targets_succeeded"] = succeeded
    result["requested_url_inspections"] = len(urls)
    if attempted == 0:
        result["collection_state"] = "NO_DATA"
    elif succeeded == attempted:
        result["collection_state"] = "SUCCESS"
    elif succeeded > 0:
        result["collection_state"] = "PARTIAL"
    else:
        result["collection_state"] = "ERROR"
    return result


def _update_service_run(*, audit_id: str, workspace: Any, result: Mapping[str, Any]) -> None:
    connection = sqlite3.connect(workspace.database)
    try:
        exists = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='standards_service_runs'"
        ).fetchone()
        if exists is None:
            return
        with connection:
            connection.execute(
                """UPDATE standards_service_runs
                   SET state=?,targets_attempted=?,targets_succeeded=?,details_json=?,updated_at=?
                   WHERE audit_id=? AND service_id='google-search-console'""",
                (
                    str(result.get("collection_state") or result.get("service_state") or "UNKNOWN"),
                    int(result.get("targets_attempted") or 0),
                    int(result.get("targets_succeeded") or 0),
                    json.dumps(dict(result), ensure_ascii=False, sort_keys=True, separators=(",", ":")),
                    datetime.now(timezone.utc).isoformat(),
                    audit_id,
                ),
            )
    finally:
        connection.close()


def install() -> None:
    """Wrap final report materialization with credential-gated GSC observability."""
    from rasai import report_completion, report_navigation
    from rasai.report_manifest import write_report_manifest
    from rasai.report_scale_ux import enhance_report_directory
    from rasai.standards_gsc_metrics import enrich_gsc_metrics_report, reconcile_gsc_observational_metrics
    from rasai.standards_metrics import enrich_existing_reports, write_standards_report

    if getattr(report_completion, "_rasai_gsc_observability_runtime", False):
        return
    original = report_completion.finalize_audit_report_site

    def finalize_with_gsc(*, audit_id: str, workspace: Any, context_interpretations=(), routing_snapshot=None):
        base = original(
            audit_id=audit_id,
            workspace=workspace,
            context_interpretations=context_interpretations,
            routing_snapshot=routing_snapshot,
        )
        errors = list(base.renderer_errors)
        try:
            result = collect_configured_search_console(audit_id=audit_id, workspace=workspace)
            _update_service_run(audit_id=audit_id, workspace=workspace, result=result)
            if bool(result.get("effective_enabled")):
                # Provider errors remain service state/details. They are not report-render
                # failures and do not turn a valid audit mini-site into a renderer warning.
                enrich_observability_report(audit_workspace=workspace.root)
                reconcile_gsc_observational_metrics(audit_id=audit_id, workspace=workspace)
                write_standards_report(audit_id=audit_id, workspace=workspace)
                enrich_existing_reports(audit_id=audit_id, workspace=workspace)
                enrich_gsc_metrics_report(audit_id=audit_id, workspace=workspace)
                report_dir = workspace.root / "report"
                report_navigation.normalize_report_navigation(report_dir)
                enhance_report_directory(report_dir)
                write_report_manifest(report_dir)
        except Exception as exc:
            # Only composition/rendering failures reach renderer_errors. External-call
            # failures are contained by collect_configured_search_console above.
            errors.append(f"gsc-runtime:{type(exc).__name__}:{redact_text(str(exc)[:500])}")

        inspected = report_completion.inspect_audit_report_site(audit_id=audit_id, workspace=workspace)
        return report_completion.AuditReportCompletion(
            expected_pages=inspected.expected_pages,
            generated_pages=inspected.generated_pages,
            missing_pages=inspected.missing_pages,
            renderer_errors=tuple(errors),
        )

    report_completion.finalize_audit_report_site = finalize_with_gsc
    report_completion._rasai_gsc_observability_runtime = True
