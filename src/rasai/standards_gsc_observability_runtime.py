"""Bounded Search Console collection composed into audit finalization.

The external data is persisted in observability.db/artifacts, not promoted to SARI or
SCORE-GEO evidence. audit.db stores standards-service execution state plus advisory
metrics derived from already-persisted GSC observations.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
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

# Projection eligibility is tied to the operation result from the *current*
# finalization. Historical sidecar datasets remain preserved, but they must not be
# surfaced as if they were freshly collected when the corresponding operation failed,
# was skipped, or the service is disabled for this run.
_GSC_METRICS_BY_OPERATION: dict[str, tuple[str, ...]] = {
    "URL_INSPECTION": (
        "gsc_url_inspection_response_coverage",
        "gsc_url_inspection_verdict_pass_rate",
        "gsc_indexing_allowed_rate",
        "gsc_robots_allowed_rate",
        "gsc_page_fetch_success_rate",
        "gsc_exact_canonical_agreement_rate",
        "gsc_sitemap_association_rate",
        "gsc_last_crawl_time_coverage",
        "gsc_last_crawl_age_p50_days",
        "gsc_last_crawl_age_p75_days",
        "gsc_last_crawl_age_p95_days",
    ),
    "SITEMAPS": (
        "gsc_sitemap_count",
        "gsc_sitemap_error_free_rate",
        "gsc_sitemap_warning_free_rate",
        "gsc_sitemap_pending_rate",
        "gsc_sitemap_reported_submitted_urls",
    ),
    "SEARCH_ANALYTICS": (
        "gsc_returned_search_rows",
        "gsc_returned_row_clicks",
        "gsc_returned_row_impressions",
        "gsc_returned_row_ctr",
        "gsc_returned_row_impression_weighted_position",
        "gsc_returned_distinct_queries",
        "gsc_returned_distinct_urls",
        "gsc_returned_distinct_query_url_pairs",
    ),
}

_GSC_REPORT_PANEL_MARKERS = (
    "RASAI_GSC_OBSERVATIONAL_METRICS",
    "RASAI_GSC_CRAWL_FRESHNESS_METRICS",
    "RASAI_GSC_SITEMAP_METRICS",
    "RASAI_GSC_RETURNED_VISIBILITY_COUNTS",
)


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


def _successful_operation_names(result: Mapping[str, Any]) -> set[str]:
    operations = result.get("operations")
    if not isinstance(operations, list):
        return set()
    return {
        str(item.get("name") or "").strip().upper()
        for item in operations
        if isinstance(item, Mapping)
        and str(item.get("status") or "").strip().upper() == "SUCCESS"
        and str(item.get("dataset_id") or "").strip()
    }


def _clear_metrics_without_current_success(
    *,
    audit_id: str,
    workspace: Any,
    result: Mapping[str, Any],
) -> None:
    """Hide stale GSC projections when their operation did not succeed this run.

    Raw historical datasets remain untouched in observability.db. Only the advisory
    audit.db projection for the current audit/report is removed.
    """
    successful = _successful_operation_names(result)
    stale_metric_ids = tuple(
        metric_id
        for operation, metric_ids in _GSC_METRICS_BY_OPERATION.items()
        if operation not in successful
        for metric_id in metric_ids
    )
    if not stale_metric_ids:
        return

    connection = sqlite3.connect(workspace.database)
    try:
        exists = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='standards_metric_observations'"
        ).fetchone()
        if exists is None:
            return
        placeholders = ",".join("?" for _ in stale_metric_ids)
        with connection:
            connection.execute(
                f"DELETE FROM standards_metric_observations WHERE audit_id=? AND metric_id IN ({placeholders})",
                (audit_id, *stale_metric_ids),
            )
    finally:
        connection.close()


def _remove_marked_panel(path: Path, marker: str) -> bool:
    """Remove one previously inserted report block without touching unrelated content."""
    if not path.is_file():
        return False
    text = path.read_text(encoding="utf-8")
    original = text
    start_token = f"<!-- {marker}:START -->"
    end_token = f"<!-- {marker}:END -->"
    while True:
        start = text.find(start_token)
        if start < 0:
            break
        end = text.find(end_token, start + len(start_token))
        if end < 0:
            # Do not truncate a malformed document. Leave it intact for normal report
            # validation to surface rather than deleting an unbounded suffix.
            break
        text = text[:start] + text[end + len(end_token):]
    if text == original:
        return False
    path.write_text(text, encoding="utf-8", newline="\n")
    return True


def _clear_gsc_report_panels(report_dir: Path) -> bool:
    """Remove all GSC advisory panels so the current finalization can re-project them."""
    path = report_dir / "observability.html"
    changed = False
    for marker in _GSC_REPORT_PANEL_MARKERS:
        changed = _remove_marked_panel(path, marker) or changed
    return changed


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
    from rasai.standards_gsc_crawl_freshness_metrics import (
        enrich_gsc_crawl_freshness_report,
        reconcile_gsc_crawl_freshness_metrics,
    )
    from rasai.standards_gsc_metrics import enrich_gsc_metrics_report, reconcile_gsc_observational_metrics
    from rasai.standards_gsc_sitemap_metrics import enrich_gsc_sitemap_report, reconcile_gsc_sitemap_metrics
    from rasai.standards_gsc_visibility_metrics import enrich_gsc_visibility_report, reconcile_gsc_visibility_counts
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
                enrich_observability_report(audit_workspace=workspace.root)
                reconcile_gsc_observational_metrics(audit_id=audit_id, workspace=workspace)
                reconcile_gsc_crawl_freshness_metrics(audit_id=audit_id, workspace=workspace)
                reconcile_gsc_sitemap_metrics(audit_id=audit_id, workspace=workspace)
                reconcile_gsc_visibility_counts(audit_id=audit_id, workspace=workspace)

            _clear_metrics_without_current_success(audit_id=audit_id, workspace=workspace, result=result)
            report_dir = workspace.root / "report"
            _clear_gsc_report_panels(report_dir)

            # standards.html is a full render from audit.db, so regenerate it even when
            # GSC is disabled/partial after stale projections have been removed.
            write_standards_report(audit_id=audit_id, workspace=workspace)

            if bool(result.get("effective_enabled")):
                enrich_existing_reports(audit_id=audit_id, workspace=workspace)
                enrich_gsc_metrics_report(audit_id=audit_id, workspace=workspace)
                enrich_gsc_crawl_freshness_report(audit_id=audit_id, workspace=workspace)
                enrich_gsc_sitemap_report(audit_id=audit_id, workspace=workspace)
                enrich_gsc_visibility_report(audit_id=audit_id, workspace=workspace)
                report_navigation.normalize_report_navigation(report_dir)
                enhance_report_directory(report_dir)

            # Report hashes must match the post-cleanup/post-projection files even when
            # the service is disabled and only stale panels were removed.
            write_report_manifest(report_dir)
        except Exception as exc:
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
