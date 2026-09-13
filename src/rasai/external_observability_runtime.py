"""Safe external observability composed into audit finalization.

The runtime is intentionally non-blocking: provider/public-index failures are recorded
as service outcomes and never turn website readiness into a failure.  All external
records go to observability.db; audit.db receives only the existing service-run status
metadata needed by the standards report.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
import os
import sqlite3
from typing import Any, Mapping

from rasai.external_observability_policy import (
    CLARITY_DAYS_ENV,
    CLARITY_DIMENSIONS_ENV,
    CLARITY_TOKEN_ENV,
    COMMON_CRAWL_INDEX_COUNT_ENV,
    COMMON_CRAWL_MAX_URLS_ENV,
    clarity_days,
    clarity_dimensions,
    common_crawl_index_count,
    common_crawl_max_urls,
)
from rasai.external_observability_reporting import enrich_external_observability_reports
from rasai.observability.crux_history import collect_crux_history
from rasai.observability.external_sources import collect_clarity_insights, collect_common_crawl_history
from rasai.observability.reporting import enrich_observability_report
from rasai.secret_safety import redact_text
from rasai.standards_service_registry import (
    DEFAULT_STANDARDS_TIMEOUT_SECONDS,
    STANDARDS_TIMEOUT_ENV,
    service,
    service_state,
)

_LOGGER = logging.getLogger(__name__)
CRUX_KEY_ENV = "RASAI_CRUX_API_KEY"
_DEVICE_TO_CRUX = {"mobile": "PHONE", "desktop": "DESKTOP", "tablet": "TABLET"}
_SERVICE_IDS = ("crux-history", "microsoft-clarity", "common-crawl")


def collect_configured_external_observability(
    *,
    audit_id: str,
    workspace: Any,
    env: Mapping[str, str] | None = None,
) -> dict[str, dict[str, Any]]:
    environment = env if env is not None else os.environ
    timeout = _positive_float(environment.get(STANDARDS_TIMEOUT_ENV), DEFAULT_STANDARDS_TIMEOUT_SECONDS)
    outcomes: dict[str, dict[str, Any]] = {}

    crux_state = service_state(service("crux-history"), environment)
    crux_result = _base_result(crux_state)
    if bool(crux_state["effective_enabled"]):
        key = str(environment.get(CRUX_KEY_ENV) or "").strip()
        targets = _origin_form_factors(workspace, audit_id)
        attempted = 0
        succeeded = 0
        datasets: list[str] = []
        errors: list[str] = []
        for origin, form_factor in targets:
            attempted += 1
            try:
                datasets.append(
                    collect_crux_history(
                        audit_workspace=workspace.root,
                        api_key=key,
                        target=origin,
                        target_scope="origin",
                        form_factor=form_factor,
                        collection_period_count=40,
                        timeout=timeout,
                    )
                )
                succeeded += 1
            except Exception as exc:
                errors.append(_safe_error("CRUX_HISTORY", exc))
        crux_result.update(
            targets_attempted=attempted,
            targets_succeeded=succeeded,
            datasets=datasets,
            errors=errors,
            collection_state=_collection_state(attempted, succeeded),
            scope="ORIGIN+FORM_FACTOR",
        )
    outcomes["crux-history"] = crux_result

    clarity_state = service_state(service("microsoft-clarity"), environment)
    clarity_result = _base_result(clarity_state)
    if bool(clarity_state["effective_enabled"]):
        attempted = 1
        try:
            dataset_id = collect_clarity_insights(
                audit_workspace=workspace.root,
                api_token=str(environment.get(CLARITY_TOKEN_ENV) or ""),
                days=clarity_days(environment.get(CLARITY_DAYS_ENV)),
                dimensions=clarity_dimensions(environment.get(CLARITY_DIMENSIONS_ENV)),
                timeout=timeout,
            )
            clarity_result.update(
                targets_attempted=attempted,
                targets_succeeded=1,
                datasets=[dataset_id],
                errors=[],
                collection_state="SUCCESS",
                scope="ORIGIN/URL+DEVICE_WHEN_DIMENSION_PRESENT",
            )
        except Exception as exc:
            clarity_result.update(
                targets_attempted=attempted,
                targets_succeeded=0,
                datasets=[],
                errors=[_safe_error("CLARITY", exc)],
                collection_state="ERROR",
            )
    outcomes["microsoft-clarity"] = clarity_result

    common_state = service_state(service("common-crawl"), environment)
    common_result = _base_result(common_state)
    if bool(common_state["effective_enabled"]):
        max_urls = common_crawl_max_urls(environment.get(COMMON_CRAWL_MAX_URLS_ENV))
        if max_urls == 0:
            common_result.update(
                targets_attempted=0,
                targets_succeeded=0,
                datasets=[],
                errors=[],
                collection_state="NO_DATA",
                reason="COMMON_CRAWL_MAX_URLS_ZERO",
            )
        else:
            try:
                dataset_id = collect_common_crawl_history(
                    audit_workspace=workspace.root,
                    max_urls=max_urls,
                    collection_count=common_crawl_index_count(environment.get(COMMON_CRAWL_INDEX_COUNT_ENV)),
                    timeout=timeout,
                )
                common_result.update(
                    targets_attempted=1,
                    targets_succeeded=1,
                    datasets=[dataset_id],
                    errors=[],
                    collection_state="SUCCESS",
                    scope="URL",
                )
            except Exception as exc:
                common_result.update(
                    targets_attempted=1,
                    targets_succeeded=0,
                    datasets=[],
                    errors=[_safe_error("COMMON_CRAWL", exc)],
                    collection_state="ERROR",
                )
    outcomes["common-crawl"] = common_result

    for service_id, result in outcomes.items():
        _upsert_service_run(audit_id=audit_id, workspace=workspace, service_id=service_id, result=result)
    return outcomes


def _base_result(state_info: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "service_state": str(state_info.get("state") or "UNKNOWN"),
        "requested": bool(state_info.get("requested")),
        "configured": bool(state_info.get("configured")),
        "effective_enabled": bool(state_info.get("effective_enabled")),
        "configuration_source": str(state_info.get("configuration_source") or ""),
        "missing_configuration": list(state_info.get("missing_configuration") or ()),
        "targets_attempted": 0,
        "targets_succeeded": 0,
        "datasets": [],
        "errors": [],
        "collection_state": str(state_info.get("state") or "UNKNOWN"),
    }


def _origin_form_factors(workspace: Any, audit_id: str) -> tuple[tuple[str, str | None], ...]:
    connection = sqlite3.connect(workspace.database)
    try:
        origins = [
            str(row[0]).rstrip("/")
            for row in connection.execute(
                "SELECT DISTINCT normalized_origin FROM audit_targets WHERE audit_id=? ORDER BY normalized_origin",
                (audit_id,),
            ).fetchall()
            if row[0]
        ]
        devices = {
            str(row[0]).strip().casefold()
            for row in connection.execute(
                """SELECT DISTINCT ps.device FROM page_snapshots ps
                   JOIN pages p ON p.page_id=ps.page_id WHERE p.audit_id=?""",
                (audit_id,),
            ).fetchall()
            if row[0]
        }
    finally:
        connection.close()
    form_factors = tuple(_DEVICE_TO_CRUX[item] for item in ("mobile", "desktop", "tablet") if item in devices)
    result: list[tuple[str, str | None]] = []
    for origin in origins:
        result.append((origin, None))
        result.extend((origin, form_factor) for form_factor in form_factors)
    return tuple(result)


def _upsert_service_run(*, audit_id: str, workspace: Any, service_id: str, result: Mapping[str, Any]) -> None:
    if service_id not in _SERVICE_IDS:
        return
    connection = sqlite3.connect(workspace.database)
    try:
        exists = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='standards_service_runs'"
        ).fetchone()
        if exists is None:
            return
        with connection:
            connection.execute(
                """INSERT OR REPLACE INTO standards_service_runs(
                    audit_id,service_id,requested,configured,effective_enabled,state,
                    targets_attempted,targets_succeeded,details_json,updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (
                    audit_id,
                    service_id,
                    int(bool(result.get("requested"))),
                    int(bool(result.get("configured"))),
                    int(bool(result.get("effective_enabled"))),
                    str(result.get("collection_state") or result.get("service_state") or "UNKNOWN"),
                    int(result.get("targets_attempted") or 0),
                    int(result.get("targets_succeeded") or 0),
                    json.dumps(dict(result), ensure_ascii=False, sort_keys=True, separators=(",", ":")),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
    finally:
        connection.close()


def _collection_state(attempted: int, succeeded: int) -> str:
    if attempted <= 0:
        return "NO_DATA"
    if succeeded == attempted:
        return "SUCCESS"
    if succeeded > 0:
        return "PARTIAL"
    return "ERROR"


def _positive_float(raw: str | None, default: float) -> float:
    if raw is None or not str(raw).strip():
        return default
    value = float(str(raw).strip())
    if value <= 0 or value >= 3600:
        raise ValueError("external observability timeout must be > 0 and < 3600 seconds")
    return value


def _safe_error(label: str, exc: Exception) -> str:
    return redact_text(f"{label}:{type(exc).__name__}:{str(exc)[:350]}")


def install() -> None:
    """Wrap final report materialization after the canonical/GSC finalizers."""
    from rasai import report_completion, report_navigation
    from rasai.report_manifest import write_report_manifest
    from rasai.report_scale_ux import enhance_report_directory
    from rasai.standards_metrics import enrich_existing_reports, write_standards_report

    if getattr(report_completion, "_rasai_external_observability_runtime", False):
        return
    original = report_completion.finalize_audit_report_site

    def finalize_with_external_observability(*, audit_id: str, workspace: Any, context_interpretations=(), routing_snapshot=None):
        base = original(
            audit_id=audit_id,
            workspace=workspace,
            context_interpretations=context_interpretations,
            routing_snapshot=routing_snapshot,
        )
        if base.missing_pages:
            return base
        try:
            outcomes = collect_configured_external_observability(audit_id=audit_id, workspace=workspace)
            if any(bool(item.get("effective_enabled")) for item in outcomes.values()):
                enrich_observability_report(audit_workspace=workspace.root)
                enrich_external_observability_reports(audit_workspace=workspace.root)
                write_standards_report(audit_id=audit_id, workspace=workspace)
                enrich_existing_reports(audit_id=audit_id, workspace=workspace)
                # standards re-render may replace thematic pages; project external
                # panels once more against their final current-run HTML.
                enrich_external_observability_reports(audit_workspace=workspace.root)
                report_navigation.normalize_report_navigation(workspace.root / "report")
                enhance_report_directory(workspace.root / "report")
                write_report_manifest(workspace.root / "report")
            for service_id, result in outcomes.items():
                if result.get("collection_state") in {"ERROR", "PARTIAL"}:
                    _LOGGER.warning(
                        "External observability %s completed as %s: %s",
                        service_id,
                        result.get("collection_state"),
                        "; ".join(str(item) for item in result.get("errors") or ()),
                    )
        except Exception:
            # External enrichment must not compromise the already completed canonical
            # audit/report.  Details go to the application log without changing score.
            _LOGGER.exception("External observability finalization failed; canonical audit preserved")

        return report_completion.inspect_audit_report_site(audit_id=audit_id, workspace=workspace)

    report_completion.finalize_audit_report_site = finalize_with_external_observability
    report_completion._rasai_external_observability_runtime = True
