"""Governed collection/deterministic/report boundary composition.

This module does not reimplement collectors.  It reuses the existing standards,
observability and fulfillment implementations while enforcing one causal contract:

    collection -> deterministic persistence -> evidence seal -> AI -> final sync
    -> report projection

Legacy finalizer wrappers are kept for presentation compatibility, but their network and
audit.db-mutating functions are guarded while the report projection context is active.
The same original functions remain callable by collection/reprocessing phases.
"""
from __future__ import annotations

from contextvars import ContextVar
from datetime import datetime, timezone
import hashlib
import json
import os
import sqlite3
from typing import Any, Callable, Mapping


_REPORT_PROJECTION: ContextVar[bool] = ContextVar(
    "rasai_report_projection_only",
    default=False,
)
_PRE_INSTALLED = False
_POST_INSTALLED = False
_ORIGINALS: dict[str, Callable[..., Any]] = {}

_BASE_METRIC_IDS = (
    "crawlability_coverage",
    "indexability_coverage",
    "sitemap_audited_url_coverage",
    "canonical_declaration_coverage",
    "canonical_consistency_rate",
    "structured_data_coverage",
    "structured_data_validity_rate",
    "structured_data_visible_consistency_rate",
    "structured_entity_consistency_rate",
    "http_2xx_success_rate",
    "http_5xx_rate",
    "ttfb_p50",
    "ttfb_p75",
    "ttfb_p95",
    "ttfb_p99",
    "domain_mrr",
    "domain_serp_visibility_rate",
    "precision_at_10",
    "ndcg_at_10",
    "judged_mrr",
)


def report_projection_active() -> bool:
    return bool(_REPORT_PROJECTION.get())


def _remember(name: str, function: Callable[..., Any]) -> Callable[..., Any]:
    _ORIGINALS.setdefault(name, function)
    return _ORIGINALS[name]


def _guard(
    name: str,
    function: Callable[..., Any],
    *,
    projection_result: Callable[..., Any] | Any = None,
) -> Callable[..., Any]:
    original = _remember(name, function)
    if bool(getattr(function, "_rasai_projection_guard", False)):
        return function

    def guarded(*args: Any, **kwargs: Any):
        if report_projection_active():
            if callable(projection_result):
                return projection_result(*args, **kwargs)
            return projection_result
        return original(*args, **kwargs)

    guarded._rasai_projection_guard = True
    guarded._rasai_original = original
    return guarded


def _table_exists(connection: sqlite3.Connection, name: str) -> bool:
    return connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone() is not None


def _persisted_service_result(
    workspace: Any,
    audit_id: str,
    service_id: str,
) -> dict[str, Any]:
    connection = sqlite3.connect(workspace.database)
    connection.row_factory = sqlite3.Row
    try:
        if not _table_exists(connection, "standards_service_runs"):
            return {
                "service_state": "NOT_CONFIGURED",
                "collection_state": "NOT_CONFIGURED",
                "requested": False,
                "configured": False,
                "effective_enabled": False,
                "targets_attempted": 0,
                "targets_succeeded": 0,
            }
        row = connection.execute(
            "SELECT * FROM standards_service_runs WHERE audit_id=? AND service_id=?",
            (audit_id, service_id),
        ).fetchone()
        if row is None:
            return {
                "service_state": "NOT_CONFIGURED",
                "collection_state": "NOT_CONFIGURED",
                "requested": False,
                "configured": False,
                "effective_enabled": False,
                "targets_attempted": 0,
                "targets_succeeded": 0,
            }
        details: dict[str, Any] = {}
        try:
            parsed = json.loads(str(row["details_json"] or "{}"))
            if isinstance(parsed, dict):
                details = dict(parsed)
        except (TypeError, ValueError, json.JSONDecodeError):
            pass
        state = str(row["state"] or "NO_DATA").upper()
        details.setdefault("service_state", state)
        details.setdefault("collection_state", state)
        details.setdefault("requested", bool(row["requested"]))
        details.setdefault("configured", bool(row["configured"]))
        details.setdefault("effective_enabled", bool(row["effective_enabled"]))
        details.setdefault("targets_attempted", int(row["targets_attempted"] or 0))
        details.setdefault("targets_succeeded", int(row["targets_succeeded"] or 0))
        return details
    finally:
        connection.close()


def _persisted_gsc_projection(*, audit_id: str, workspace: Any, **_: Any) -> dict[str, Any]:
    result = _persisted_service_result(workspace, audit_id, "google-search-console")
    result.setdefault("operations", [])
    result.setdefault("errors", [])
    return result


def _persisted_external_projection(
    *,
    audit_id: str,
    workspace: Any,
    **_: Any,
) -> dict[str, dict[str, Any]]:
    return {
        service_id: _persisted_service_result(workspace, audit_id, service_id)
        for service_id in ("crux-history", "microsoft-clarity", "common-crawl")
    }


def _collect_standard_service(
    *,
    audit_id: str,
    workspace: Any,
    service_id: str,
) -> dict[str, Any]:
    from rasai import standards_metrics as metrics
    from rasai.standards_service_registry import (
        DEFAULT_STANDARDS_MAX_URLS,
        DEFAULT_STANDARDS_TIMEOUT_SECONDS,
        STANDARDS_MAX_URLS_ENV,
        STANDARDS_TIMEOUT_ENV,
        service,
        service_state,
    )

    environment = os.environ
    max_urls = metrics._nonnegative_int(
        environment.get(STANDARDS_MAX_URLS_ENV),
        DEFAULT_STANDARDS_MAX_URLS,
    )
    timeout = metrics._positive_float(
        environment.get(STANDARDS_TIMEOUT_ENV),
        DEFAULT_STANDARDS_TIMEOUT_SECONDS,
    )
    state_info = service_state(service(service_id), environment)
    connection = sqlite3.connect(workspace.database)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    attempted = succeeded = 0
    details: dict[str, Any] = {}
    try:
        with connection:
            metrics._init(connection)
            if not bool(state_info["effective_enabled"]):
                state = str(state_info["state"] or "DISABLED").upper()
                metrics._service_run(
                    connection,
                    audit_id=audit_id,
                    service_id=service_id,
                    state_info=state_info,
                    state=state,
                )
            else:
                if service_id == "w3c-validator":
                    attempted, succeeded, details = metrics._w3c_validator(
                        connection,
                        audit_id,
                        max_urls,
                        timeout,
                    )
                elif service_id == "mdn-observatory":
                    attempted, succeeded, details = metrics._mdn_observatory(
                        connection,
                        audit_id,
                        timeout,
                    )
                else:
                    raise ValueError(f"unsupported standards collector: {service_id}")
                state = (
                    "SUCCESS"
                    if attempted and attempted == succeeded
                    else "PARTIAL"
                    if succeeded
                    else "NO_DATA"
                )
                metrics._service_run(
                    connection,
                    audit_id=audit_id,
                    service_id=service_id,
                    state_info=state_info,
                    state=state,
                    attempted=attempted,
                    succeeded=succeeded,
                    details=details,
                )
    except Exception as exc:
        state = "ERROR"
        details = {"error": f"{type(exc).__name__}: {str(exc)[:500]}"}
        try:
            with connection:
                metrics._init(connection)
                metrics._service_run(
                    connection,
                    audit_id=audit_id,
                    service_id=service_id,
                    state_info=state_info,
                    state=state,
                    attempted=attempted,
                    succeeded=succeeded,
                    details=details,
                )
        except Exception:
            pass
    finally:
        connection.close()
    return {
        "collection_state": state,
        "service_id": service_id,
        "requested": bool(state_info.get("requested")),
        "configured": bool(state_info.get("configured")),
        "effective_enabled": bool(state_info.get("effective_enabled")),
        "targets_attempted": attempted,
        "targets_succeeded": succeeded,
        "details": details,
    }


def _collect_w3c_html(*, audit_id: str, workspace: Any, source_blocked: bool = False):
    del source_blocked
    return _collect_standard_service(
        audit_id=audit_id,
        workspace=workspace,
        service_id="w3c-validator",
    )


def _collect_mdn_observatory(*, audit_id: str, workspace: Any, source_blocked: bool = False):
    del source_blocked
    return _collect_standard_service(
        audit_id=audit_id,
        workspace=workspace,
        service_id="mdn-observatory",
    )


def _collect_web_platform(*, audit_id: str, workspace: Any, source_blocked: bool = False):
    del source_blocked
    original = _ORIGINALS["web_platform_baseline.materialize"]
    result = dict(original(audit_id=audit_id, workspace=workspace) or {})
    result["collection_state"] = str(
        result.get("collection_state") or result.get("state") or "SUCCESS"
    ).upper()
    return result


def _collect_css(*, audit_id: str, workspace: Any, source_blocked: bool = False):
    del source_blocked
    original = _ORIGINALS["standards_css_validation.collect"]
    return dict(original(audit_id=audit_id, workspace=workspace) or {})


def _reconcile_base_standards(*, audit_id: str, workspace: Any, **_: Any):
    from rasai import standards_metrics as metrics
    from rasai.standards_service_registry import service_states

    environment = os.environ
    states = {str(item["id"]): item for item in service_states(environment)}
    connection = sqlite3.connect(workspace.database)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        with connection:
            metrics._init(connection)
            placeholders = ",".join("?" for _ in _BASE_METRIC_IDS)
            connection.execute(
                f"DELETE FROM standards_metric_observations WHERE audit_id=? "
                f"AND metric_id IN ({placeholders})",
                (audit_id, *_BASE_METRIC_IDS),
            )

            derived = states["derived-readiness"]
            if bool(derived["effective_enabled"]):
                metrics._derived_metrics(connection, audit_id)
                metrics._service_run(
                    connection,
                    audit_id=audit_id,
                    service_id="derived-readiness",
                    state_info=derived,
                    state="SUCCESS",
                    succeeded=1,
                )
            else:
                metrics._service_run(
                    connection,
                    audit_id=audit_id,
                    service_id="derived-readiness",
                    state_info=derived,
                )

            retrieval = states["retrieval-metrics"]
            if bool(retrieval["effective_enabled"]):
                metrics._retrieval_metrics(connection, audit_id)
                metrics._service_run(
                    connection,
                    audit_id=audit_id,
                    service_id="retrieval-metrics",
                    state_info=retrieval,
                    state="SUCCESS",
                    succeeded=1,
                )
            else:
                metrics._service_run(
                    connection,
                    audit_id=audit_id,
                    service_id="retrieval-metrics",
                    state_info=retrieval,
                )

            # Some canonical services are collected by other modules.  Keep their
            # richer persisted run when present; create only the readiness row that is
            # otherwise required by standards reporting.
            for service_id in (
                "open-web-metrics",
                "pagespeed",
                "crux",
                "google-search-console",
            ):
                exists = connection.execute(
                    "SELECT 1 FROM standards_service_runs WHERE audit_id=? AND service_id=?",
                    (audit_id, service_id),
                ).fetchone()
                if exists is None and service_id in states:
                    metrics._service_run(
                        connection,
                        audit_id=audit_id,
                        service_id=service_id,
                        state_info=states[service_id],
                    )
    finally:
        connection.close()
    return {"status": "SUCCESS", "metrics": "base-readiness-reconciled"}


def _reconcile_ir(*, audit_id: str, workspace: Any, **_: Any):
    _ORIGINALS["standards_ir.reconcile"](audit_id=audit_id, workspace=workspace)
    return {"status": "SUCCESS"}


def _reconcile_operational(*, audit_id: str, workspace: Any, **_: Any):
    _ORIGINALS["standards_operational.reconcile"](
        audit_id=audit_id,
        workspace=workspace,
    )
    return {"status": "SUCCESS"}


def _reconcile_structured(*, audit_id: str, workspace: Any, **_: Any):
    _ORIGINALS["standards_structured.reconcile"](
        audit_id=audit_id,
        workspace=workspace,
    )
    return {"status": "SUCCESS"}


def _reconcile_gsc(*, audit_id: str, workspace: Any, **_: Any):
    result = _persisted_gsc_projection(audit_id=audit_id, workspace=workspace)
    _ORIGINALS["gsc.clear_all_metrics"](audit_id=audit_id, workspace=workspace)
    if bool(result.get("effective_enabled")):
        for name in (
            "gsc.metrics.reconcile",
            "gsc.freshness.reconcile",
            "gsc.sitemap.reconcile",
            "gsc.visibility.reconcile",
        ):
            _ORIGINALS[name](audit_id=audit_id, workspace=workspace)
    _ORIGINALS["gsc.clear_without_success"](
        audit_id=audit_id,
        workspace=workspace,
        result=result,
    )
    return {
        "status": str(result.get("collection_state") or "NOT_CONFIGURED").upper(),
        "effective_enabled": bool(result.get("effective_enabled")),
    }


def _sync_fulfillment_preseal(*, audit_id: str, workspace: Any, **_: Any):
    _ORIGINALS["fulfillment.sync"](audit_id=audit_id, workspace=workspace)
    _ORIGINALS["core.sync"](workspace, audit_id)
    return {"status": "SUCCESS"}


def _final_persisted_sync(*, audit_id: str, workspace: Any) -> None:
    _ORIGINALS["fulfillment.sync"](audit_id=audit_id, workspace=workspace)
    _ORIGINALS["core.sync"](workspace, audit_id)
    try:
        _ORIGINALS["fulfillment.project_validity"](
            audit_id=audit_id,
            workspace=workspace,
        )
    except TypeError:
        _ORIGINALS["fulfillment.project_validity"](workspace, audit_id)


def _logical_db_fingerprint(database: Any) -> str:
    path = str(database)
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=2.0)
    try:
        digest = hashlib.sha256()
        for line in connection.iterdump():
            digest.update(line.encode("utf-8", errors="surrogatepass"))
            digest.update(b"\n")
        return digest.hexdigest()
    finally:
        connection.close()


def _install_projection_guards() -> None:
    from rasai import (
        audit_fulfillment_runtime,
        core_reprocessing,
        external_observability_runtime,
        selective_optional_reprocess,
        standards_css_validation,
        standards_gsc_observability_runtime,
        standards_ir_reconciliation,
        standards_metrics,
        standards_operational_reconciliation,
        standards_structured_data_reconciliation,
        web_platform_baseline,
    )
    from rasai import standards_gsc_crawl_freshness_metrics as gsc_freshness
    from rasai import standards_gsc_metrics as gsc_metrics
    from rasai import standards_gsc_sitemap_metrics as gsc_sitemap
    from rasai import standards_gsc_visibility_metrics as gsc_visibility

    standards_metrics.execute_standards_metrics = _guard(
        "standards_metrics.execute",
        standards_metrics.execute_standards_metrics,
    )
    web_platform_baseline.materialize_web_platform_baseline = _guard(
        "web_platform_baseline.materialize",
        web_platform_baseline.materialize_web_platform_baseline,
        projection_result=lambda **_: {"state": "PROJECTION_ONLY", "attempted": 0, "succeeded": 0},
    )
    standards_css_validation.collect_css_validation = _guard(
        "standards_css_validation.collect",
        standards_css_validation.collect_css_validation,
        projection_result=lambda **_: {
            "collection_state": "PROJECTION_ONLY",
            "state_info": {"effective_enabled": False},
            "attempted": 0,
            "succeeded": 0,
            "errors": [],
        },
    )

    standards_ir_reconciliation.reconcile_information_retrieval_metrics = _guard(
        "standards_ir.reconcile",
        standards_ir_reconciliation.reconcile_information_retrieval_metrics,
    )
    standards_operational_reconciliation.reconcile_operational_http_metrics = _guard(
        "standards_operational.reconcile",
        standards_operational_reconciliation.reconcile_operational_http_metrics,
    )
    standards_structured_data_reconciliation.reconcile_structured_data_metrics = _guard(
        "standards_structured.reconcile",
        standards_structured_data_reconciliation.reconcile_structured_data_metrics,
    )

    gsc_metrics.reconcile_gsc_observational_metrics = _guard(
        "gsc.metrics.reconcile",
        gsc_metrics.reconcile_gsc_observational_metrics,
    )
    gsc_freshness.reconcile_gsc_crawl_freshness_metrics = _guard(
        "gsc.freshness.reconcile",
        gsc_freshness.reconcile_gsc_crawl_freshness_metrics,
    )
    gsc_sitemap.reconcile_gsc_sitemap_metrics = _guard(
        "gsc.sitemap.reconcile",
        gsc_sitemap.reconcile_gsc_sitemap_metrics,
    )
    gsc_visibility.reconcile_gsc_visibility_counts = _guard(
        "gsc.visibility.reconcile",
        gsc_visibility.reconcile_gsc_visibility_counts,
    )

    standards_gsc_observability_runtime._clear_all_gsc_metric_projections = _guard(
        "gsc.clear_all_metrics",
        standards_gsc_observability_runtime._clear_all_gsc_metric_projections,
    )
    standards_gsc_observability_runtime._update_service_run = _guard(
        "gsc.update_service_run",
        standards_gsc_observability_runtime._update_service_run,
    )
    standards_gsc_observability_runtime._clear_metrics_without_current_success = _guard(
        "gsc.clear_without_success",
        standards_gsc_observability_runtime._clear_metrics_without_current_success,
    )
    standards_gsc_observability_runtime.collect_configured_search_console = _guard(
        "gsc.collect",
        standards_gsc_observability_runtime.collect_configured_search_console,
        projection_result=_persisted_gsc_projection,
    )
    external_observability_runtime.collect_configured_external_observability = _guard(
        "external_observability.collect",
        external_observability_runtime.collect_configured_external_observability,
        projection_result=_persisted_external_projection,
    )

    audit_fulfillment_runtime._sync_persisted_components = _guard(
        "fulfillment.sync",
        audit_fulfillment_runtime._sync_persisted_components,
    )
    audit_fulfillment_runtime.project_report_validity = _guard(
        "fulfillment.project_validity",
        audit_fulfillment_runtime.project_report_validity,
    )
    core_reprocessing.synchronize_core_work_items = _guard(
        "core.sync",
        core_reprocessing.synchronize_core_work_items,
    )
    core_reprocessing.project_report_validity = _guard(
        "core.project_validity",
        core_reprocessing.project_report_validity,
    )

    selective_optional_reprocess._recover_search = _guard(
        "selective_optional.recover_search",
        selective_optional_reprocess._recover_search,
        projection_result=False,
    )
    selective_optional_reprocess._record_optional_attempts = _guard(
        "selective_optional.record_attempts",
        selective_optional_reprocess._record_optional_attempts,
    )
    if hasattr(selective_optional_reprocess, "_reconcile_gsc_rpr"):
        selective_optional_reprocess._reconcile_gsc_rpr = _guard(
            "selective_optional.reconcile_gsc",
            selective_optional_reprocess._reconcile_gsc_rpr,
        )


def _install_phase_hooks() -> None:
    from rasai import audit_phase_runtime as phase

    phase.register_collection_hook("W3C_HTML_VALIDATOR", _collect_w3c_html, order=31)
    phase.register_collection_hook("MDN_OBSERVATORY", _collect_mdn_observatory, order=32)
    phase.register_collection_hook("WEB_PLATFORM_BASELINE", _collect_web_platform, order=33)
    phase.register_collection_hook("W3C_CSS_VALIDATOR", _collect_css, order=34)

    phase.register_deterministic_hook("STANDARDS_BASE", _reconcile_base_standards, order=10)
    phase.register_deterministic_hook("STRICT_INFORMATION_RETRIEVAL", _reconcile_ir, order=20)
    phase.register_deterministic_hook("OPERATIONAL_HTTP", _reconcile_operational, order=30)
    phase.register_deterministic_hook("STRUCTURED_DATA", _reconcile_structured, order=40)
    phase.register_deterministic_hook("GSC_METRICS", _reconcile_gsc, order=50)
    phase.register_deterministic_hook("FULFILLMENT_SYNC", _sync_fulfillment_preseal, order=90)


def install_pre() -> None:
    """Install collection/deterministic governance before runtime wrappers compose."""
    global _PRE_INSTALLED
    if _PRE_INSTALLED:
        return
    _install_projection_guards()
    _install_phase_hooks()
    _PRE_INSTALLED = True


def _install_seal_composition() -> None:
    from rasai import ai_governance, audit_phase_runtime as phase

    current = phase.seal_collection_evidence
    if not bool(getattr(current, "_rasai_deterministic_before_seal", False)):
        def seal_after_deterministic(*args: Any, **kwargs: Any):
            audit_id = str(kwargs.get("audit_id") or "")
            workspace = kwargs.get("workspace")
            if not audit_id or workspace is None:
                return current(*args, **kwargs)
            outcomes = phase.run_deterministic_phase(
                audit_id=audit_id,
                workspace=workspace,
            )
            patched = dict(kwargs)
            existing = dict(patched.pop("deterministic_analysis", {}) or {})
            existing.update(outcomes)
            patched["deterministic_analysis"] = existing
            return current(*args, **patched)

        seal_after_deterministic._rasai_deterministic_before_seal = True
        seal_after_deterministic._rasai_original = current
        phase.seal_collection_evidence = seal_after_deterministic

        try:
            from rasai import audit_runner
            audit_runner.seal_collection_evidence = seal_after_deterministic
        except ImportError:
            pass

    # RPR imported ai_governance.seal_evidence by value before selective invalidation
    # was necessarily installed. Rebind it to the *current* canonical function and run
    # the same deterministic phase immediately before the new evidence version is sealed.
    try:
        from rasai import governed_reprocess_runtime as rpr
    except ImportError:
        return
    current_canonical = ai_governance.seal_evidence
    existing_rpr = getattr(rpr, "seal_evidence", None)
    if bool(getattr(existing_rpr, "_rasai_deterministic_before_seal", False)):
        return

    def reprocess_seal(*args: Any, **kwargs: Any):
        audit_id = str(kwargs.get("audit_id") or "")
        workspace = kwargs.get("workspace")
        if not audit_id or workspace is None:
            return current_canonical(*args, **kwargs)
        outcomes = phase.run_deterministic_phase(
            audit_id=audit_id,
            workspace=workspace,
        )
        patched = dict(kwargs)
        context = dict(patched.get("context") or {})
        context["deterministic_analysis"] = outcomes
        patched["context"] = context
        return current_canonical(*args, **patched)

    reprocess_seal._rasai_deterministic_before_seal = True
    reprocess_seal._rasai_original = current_canonical
    rpr.seal_evidence = reprocess_seal


def _install_final_sync() -> None:
    from rasai import audit_phase_runtime as phase

    current = phase.mark_ai_sealed
    if bool(getattr(current, "_rasai_final_persisted_sync", False)):
        return

    def mark_and_sync(*args: Any, **kwargs: Any):
        result = current(*args, **kwargs)
        audit_id = str(kwargs.get("audit_id") or "")
        workspace = kwargs.get("workspace")
        if audit_id and workspace is not None:
            _final_persisted_sync(audit_id=audit_id, workspace=workspace)
        return result

    mark_and_sync._rasai_final_persisted_sync = True
    mark_and_sync._rasai_original = current
    phase.mark_ai_sealed = mark_and_sync
    try:
        from rasai import audit_runner
        audit_runner.mark_ai_sealed = mark_and_sync
    except ImportError:
        pass
    try:
        from rasai import governed_reprocess_runtime as rpr
        rpr.mark_ai_sealed = mark_and_sync
    except ImportError:
        pass


def _install_readonly_finalizer() -> None:
    from rasai import report_completion

    current = report_completion.finalize_audit_report_site
    if bool(getattr(current, "_rasai_readonly_projection_boundary", False)):
        return

    def finalize_readonly(*args: Any, **kwargs: Any):
        workspace = kwargs.get("workspace")
        audit_id = str(kwargs.get("audit_id") or (args[0] if args else ""))
        if workspace is None:
            return current(*args, **kwargs)
        before = _logical_db_fingerprint(workspace.database)
        token = _REPORT_PROJECTION.set(True)
        try:
            result = current(*args, **kwargs)
        finally:
            _REPORT_PROJECTION.reset(token)
        after = _logical_db_fingerprint(workspace.database)
        if after != before:
            from rasai.operational_log import try_append_operational_event
            try_append_operational_event(
                workspace,
                "REPORT_RENDERER_MUTATED_AUDIT_DB",
                level="ERROR",
                audit_id=audit_id,
                before_fingerprint=before,
                after_fingerprint=after,
            )
            raise RuntimeError(
                "REPORT_RENDERER_MUTATED_AUDIT_DB: report materialization must be read-only"
            )
        return result

    finalize_readonly._rasai_readonly_projection_boundary = True
    finalize_readonly._rasai_original = current
    report_completion.finalize_audit_report_site = finalize_readonly


def install_post() -> None:
    """Install after provider/reprocess/finalizer composition is complete."""
    global _POST_INSTALLED
    if _POST_INSTALLED:
        return

    # Ensure the governance features introduced on this branch are active even when a
    # caller uses the normal entrypoint composition rather than importing them directly.
    from rasai.ai_selective_invalidation import install as install_selective_invalidation
    from rasai.semantic_partial_runtime import install as install_semantic_partial

    install_selective_invalidation()
    install_semantic_partial()
    _install_seal_composition()
    _install_final_sync()
    _install_readonly_finalizer()
    _POST_INSTALLED = True


__all__ = ["install_pre", "install_post", "report_projection_active"]
