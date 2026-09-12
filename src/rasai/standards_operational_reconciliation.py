"""Reconcile operational HTTP metrics at physical URL-acquisition scope.

M2 performs one direct HTTP acquisition per audited URL. M3 persists that acquisition
metadata into every device snapshot as ``browser_metadata.raw_http``. This module
therefore deduplicates by ``page_id`` before computing operational rates so Mobile and
Desktop snapshots cannot double-count the same physical request.
"""
from __future__ import annotations

from html import escape
import json
import sqlite3
from typing import Any
from urllib.parse import urlsplit

from rasai.persistence import AuditWorkspace
from rasai.standards_metrics import _fmt_metric, _insert_panel, _record, load_metrics
from rasai.standards_service_registry import service

_OPERATIONAL_METRIC_IDS = (
    "http_physical_observation_coverage",
    "http_2xx_success_rate",
    "http_4xx_rate",
    "http_5xx_rate",
    "transport_error_rate",
    "transport_timeout_rate",
    "redirect_rate",
    "redirect_completion_rate",
    "cross_host_redirect_rate",
)


def _json(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if value in (None, ""):
        return {}
    try:
        decoded = json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return decoded if isinstance(decoded, dict) else {}


def _status(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if 100 <= parsed <= 599 else None


def _host(value: Any) -> str:
    try:
        return (urlsplit(str(value or "")).hostname or "").casefold()
    except ValueError:
        return ""


def _percentage(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return round(numerator * 100.0 / denominator, 3)


def _physical_observations(connection: sqlite3.Connection, audit_id: str) -> tuple[int, list[dict[str, Any]]]:
    total_pages = int(connection.execute(
        "SELECT COUNT(*) FROM pages WHERE audit_id=?", (audit_id,),
    ).fetchone()[0])
    rows = connection.execute(
        """SELECT ps.page_id,p.normalized_url,ps.browser_metadata
           FROM page_snapshots ps
           JOIN pages p ON p.page_id=ps.page_id
           WHERE p.audit_id=?
           ORDER BY p.rowid,ps.device""",
        (audit_id,),
    ).fetchall()
    by_page: dict[str, dict[str, Any]] = {}
    for row in rows:
        page_id = str(row["page_id"])
        if page_id in by_page:
            continue
        metadata = _json(row["browser_metadata"])
        raw = metadata.get("raw_http")
        if not isinstance(raw, dict):
            continue
        requested_url = str(raw.get("requested_url") or row["normalized_url"] or "")
        final_url = str(raw.get("final_url") or "")
        try:
            redirect_count = max(0, int(raw.get("redirect_count") or 0))
        except (TypeError, ValueError):
            redirect_count = 0
        by_page[page_id] = {
            "page_id": page_id,
            "url": str(row["normalized_url"] or requested_url),
            "requested_url": requested_url,
            "final_url": final_url,
            "status": _status(raw.get("status")),
            "network_error": str(raw.get("network_error") or "").strip().upper() or None,
            "redirect_count": redirect_count,
        }
    return total_pages, list(by_page.values())


def reconcile_operational_http_metrics(*, audit_id: str, workspace: AuditWorkspace) -> None:
    """Replace device-duplicated HTTP rates with URL-level physical-acquisition rates."""
    item = service("derived-readiness")
    connection = sqlite3.connect(workspace.database)
    connection.row_factory = sqlite3.Row
    try:
        tables = {
            str(row[0])
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        if not {"standards_metric_observations", "standards_service_runs", "pages", "page_snapshots"}.issubset(tables):
            return
        enabled = connection.execute(
            """SELECT effective_enabled FROM standards_service_runs
               WHERE audit_id=? AND service_id='derived-readiness'""",
            (audit_id,),
        ).fetchone()
        if enabled is None or not bool(enabled[0]):
            return

        total_pages, observations = _physical_observations(connection, audit_id)
        observed = len(observations)
        statuses = [item["status"] for item in observations if item["status"] is not None]
        transport_errors = sum(item["network_error"] is not None for item in observations)
        timeouts = sum(item["network_error"] == "TIMEOUT" for item in observations)
        redirected = [item for item in observations if item["redirect_count"] > 0]
        redirect_completed = sum(
            item["network_error"] is None
            and item["final_url"]
            and item["status"] is not None
            and 200 <= int(item["status"]) <= 399
            for item in redirected
        )
        cross_host = sum(
            bool(_host(item["requested_url"]))
            and bool(_host(item["final_url"]))
            and _host(item["requested_url"]) != _host(item["final_url"])
            for item in redirected
        )

        metrics = (
            (
                "http_physical_observation_coverage",
                "Physical HTTP Observation Coverage",
                observed,
                total_pages,
                "Physical URL acquisitions materialized in raw_http / audited URLs",
            ),
            (
                "http_2xx_success_rate",
                "HTTP 2xx Success Rate",
                sum(200 <= int(status) <= 299 for status in statuses),
                observed,
                "Physical URL acquisitions ending with HTTP 2xx / all physical observations; transport failures remain in the denominator",
            ),
            (
                "http_4xx_rate",
                "HTTP 4xx Rate",
                sum(400 <= int(status) <= 499 for status in statuses),
                observed,
                "Physical URL acquisitions ending with HTTP 4xx / all physical observations",
            ),
            (
                "http_5xx_rate",
                "HTTP 5xx Rate",
                sum(500 <= int(status) <= 599 for status in statuses),
                observed,
                "Physical URL acquisitions ending with HTTP 5xx / all physical observations",
            ),
            (
                "transport_error_rate",
                "Transport Error Rate",
                transport_errors,
                observed,
                "Physical URL acquisitions with a persisted network_error / physical observations",
            ),
            (
                "transport_timeout_rate",
                "Transport Timeout Rate",
                timeouts,
                observed,
                "Physical URL acquisitions with network_error=TIMEOUT / physical observations",
            ),
            (
                "redirect_rate",
                "Redirect Rate",
                len(redirected),
                observed,
                "Physical URL acquisitions with one or more redirects / physical observations",
            ),
            (
                "redirect_completion_rate",
                "Redirect Completion Rate",
                redirect_completed,
                len(redirected),
                "Redirected physical acquisitions ending without network error at HTTP 2xx/3xx / redirected acquisitions",
            ),
            (
                "cross_host_redirect_rate",
                "Cross-host Redirect Rate",
                cross_host,
                len(redirected),
                "Redirected physical acquisitions whose final hostname differs from requested hostname / redirected acquisitions",
            ),
        )

        with connection:
            placeholders = ",".join("?" for _ in _OPERATIONAL_METRIC_IDS)
            connection.execute(
                f"DELETE FROM standards_metric_observations WHERE audit_id=? AND metric_id IN ({placeholders})",
                (audit_id, *_OPERATIONAL_METRIC_IDS),
            )
            for metric_id, label, numerator, denominator, methodology in metrics:
                value = _percentage(int(numerator), int(denominator))
                _record(
                    connection,
                    audit_id=audit_id,
                    metric_id=metric_id,
                    label=label,
                    scope="URL_SET",
                    state="NO_DATA" if value is None else "MEASURED",
                    value=value,
                    numerator=float(numerator),
                    denominator=float(denominator),
                    unit="percent",
                    source="M2 physical HTTP acquisition persisted as page_snapshots.browser_metadata.raw_http",
                    methodology=methodology,
                    relation_degree=4,
                    details={
                        "physical_observations": observed,
                        "determinate_http_statuses": len(statuses),
                        "audited_urls": total_pages,
                        "deduplicated_by": "page_id",
                        "boundary": "Device snapshots do not multiply the same physical M2 HTTP acquisition.",
                    },
                )
    finally:
        connection.close()


def enrich_operational_http_report(*, audit_id: str, workspace: AuditWorkspace) -> None:
    metrics = {
        str(row["metric_id"]): row
        for row in load_metrics(audit_id, workspace)
        if str(row["metric_id"]) in _OPERATIONAL_METRIC_IDS
    }
    if not metrics:
        return
    preferred = (
        "http_physical_observation_coverage",
        "http_2xx_success_rate",
        "http_4xx_rate",
        "http_5xx_rate",
        "transport_error_rate",
        "transport_timeout_rate",
        "redirect_rate",
        "redirect_completion_rate",
        "cross_host_redirect_rate",
    )
    cards = []
    for metric_id in preferred:
        row = metrics.get(metric_id)
        if row is None:
            continue
        cards.append(
            "<div class='metric'><small>" + escape(str(row["label"])) + "</small><strong>"
            + _fmt_metric(row) + "</strong><span>URL_SET - aquisição física M2 por URL</span></div>"
        )
    _insert_panel(
        workspace.root / "report" / "crawling-discovery.html",
        "RASAI_OPERATIONAL_HTTP_METRICS",
        "<section class='panel'><h2>HTTP operacional por aquisição física</h2>"
        "<p>Uma observação corresponde a uma aquisição M2 por URL. Snapshots Mobile/Desktop não multiplicam a mesma request. "
        "Timeouts e erros de transporte permanecem no denominador da taxa de sucesso.</p>"
        "<div class='metric-grid'>" + "".join(cards) + "</div>"
        "<p><a href='standards.html'>Abrir metodologia, fontes e demais métricas</a></p></section>",
    )


def install() -> None:
    """Reconcile URL-level operational metrics and refresh affected report projections."""
    from rasai import report_completion, report_navigation
    from rasai.report_manifest import write_report_manifest
    from rasai.report_scale_ux import enhance_report_directory
    from rasai.standards_metrics import enrich_existing_reports, write_standards_report

    if getattr(report_completion, "_rasai_operational_http_reconciliation", False):
        return
    original = report_completion.finalize_audit_report_site

    def finalize_with_operational_metrics(*, audit_id: str, workspace: Any, context_interpretations=(), routing_snapshot=None):
        base = original(
            audit_id=audit_id,
            workspace=workspace,
            context_interpretations=context_interpretations,
            routing_snapshot=routing_snapshot,
        )
        errors = list(base.renderer_errors)
        try:
            reconcile_operational_http_metrics(audit_id=audit_id, workspace=workspace)
            write_standards_report(audit_id=audit_id, workspace=workspace)
            enrich_existing_reports(audit_id=audit_id, workspace=workspace)
            enrich_operational_http_report(audit_id=audit_id, workspace=workspace)
            report_dir = workspace.root / "report"
            report_navigation.normalize_report_navigation(report_dir)
            enhance_report_directory(report_dir)
            write_report_manifest(report_dir)
        except Exception as exc:
            errors.append(f"operational-http:{type(exc).__name__}:{str(exc)[:400]}")
        inspected = report_completion.inspect_audit_report_site(audit_id=audit_id, workspace=workspace)
        return report_completion.AuditReportCompletion(
            expected_pages=inspected.expected_pages,
            generated_pages=inspected.generated_pages,
            missing_pages=inspected.missing_pages,
            renderer_errors=tuple(errors),
        )

    report_completion.finalize_audit_report_site = finalize_with_operational_metrics
    report_completion._rasai_operational_http_reconciliation = True
