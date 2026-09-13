"""Refine terminal progress and prevent report-only refreshes from recollecting APIs.

This module is console-only glue. It keeps Improvement Intelligence inside the same
workload-aware progress model used by the rest of the audit and intercepts the single
post-analysis report refresh so it remains strictly local/read-only. The initial audit
finalization still executes the normal collector chain; only the immediate refresh after
console-owned Improvement Intelligence bypasses network/provider collectors.
"""
from __future__ import annotations

from functools import wraps
import threading
from typing import Any, Callable

_INSTALLED = False
_STATE = threading.local()
_PHASE = "IMPROVEMENT_INTELLIGENCE"


def _refresh_reports_local_only(*, audit_id: str, workspace: Any) -> tuple[str, ...]:
    """Refresh projections affected by late AI persistence without network collection."""
    from rasai.improvement_intelligence import write_improvement_report
    from rasai.report_ai_cost_attribution import enrich_ai_cost_attribution
    from rasai.report_manifest import write_report_manifest
    from rasai.report_scale_ux import enhance_report_directory
    from rasai import report_navigation

    errors: list[str] = []

    def run(label: str, function: Callable[[], object]) -> None:
        try:
            function()
        except Exception as exc:
            errors.append(f"{label}:{type(exc).__name__}:{str(exc)[:240]}")

    report_dir = workspace.root / "report"
    run(
        "improvement-intelligence",
        lambda: write_improvement_report(audit_id=audit_id, workspace=workspace),
    )
    # Reconcile persisted AI attempts/costs, including ai-usage.html, without calling
    # any provider. The implementation is read-only over audit.db and report HTML.
    run(
        "ai-cost-attribution",
        lambda: enrich_ai_cost_attribution(audit_id=audit_id, workspace=workspace),
    )
    run("navigation", lambda: report_navigation.normalize_report_navigation(report_dir))
    run("report-ux", lambda: enhance_report_directory(report_dir))
    run("manifest", lambda: write_report_manifest(report_dir))
    return tuple(errors)


def _install_progress_contract() -> None:
    from rasai import console_progress_model as model
    from rasai import console_runtime
    from rasai import improvement_intelligence_console as improvement_console

    if _PHASE not in model._ORDER:
        model._ORDER = (*model._ORDER, _PHASE)

    original_weights = model.workload_weights
    if not getattr(original_weights, "_rasai_improvement_weight", False):
        @wraps(original_weights)
        def workload_weights(state: Any) -> dict[str, float]:
            weights = dict(original_weights(state))
            if bool(getattr(state, "improvement_enabled", False)):
                effort = str(getattr(state, "improvement_reasoning", "") or "MEDIUM").upper()
                effort_factor = {
                    "NONE": 0.8,
                    "LOW": 0.85,
                    "MEDIUM": 1.0,
                    "HIGH": 1.25,
                    "EXTRA_HIGH": 1.5,
                    "XHIGH": 1.5,
                }.get(effort, 1.0)
                # One URL, up to two structured provider attempts plus local synthesis.
                # This is a work projection, not an ETA.
                weights[_PHASE] = 12.0 * effort_factor
            return weights

        workload_weights._rasai_improvement_weight = True  # type: ignore[attr-defined]
        model.workload_weights = workload_weights

    # Improvement Intelligence reports exact internal progress, but its console callback
    # historically stamped every substage as API:<provider>. Normalize the operation
    # before render_header is called: only AI_ANALYSIS is a provider call; evidence,
    # HTML/security/metrics/discovery/SERP correlation, preparation, persistence and
    # report refresh are local work over evidence already collected by the audit.
    original_set_progress = console_runtime.set_runtime_progress
    if not getattr(original_set_progress, "_rasai_improvement_operation_truth", False):
        @wraps(original_set_progress)
        def set_runtime_progress(
            state: Any,
            label: str,
            percent: float | None,
            *,
            detail: str = "",
            exact: bool = False,
        ) -> None:
            if str(getattr(state, "status", "")).upper() == _PHASE:
                stage = detail.partition(":")[0].strip().upper()
                if stage and stage != "AI_ANALYSIS":
                    state.operation = f"LOCAL:IMPROVEMENT_{stage}"
            original_set_progress(state, label, percent, detail=detail, exact=exact)

        set_runtime_progress._rasai_improvement_operation_truth = True  # type: ignore[attr-defined]
        console_runtime.set_runtime_progress = set_runtime_progress

    # Replace the legacy fixed 94->99 projection before the console feature installs.
    # set_runtime_progress still receives the exact substage percentage; the workload
    # model projects it into the execution-wide range dynamically.
    def install_projection() -> None:
        console_runtime._PHASE_PROGRESS[_PHASE] = ("Análise profunda e melhorias", 0.0)
        console_runtime._rasai_improvement_progress_projection = True

    improvement_console._install_progress_projection = install_projection


def _install_local_refresh_guard() -> None:
    from rasai import improvement_intelligence_console as improvement_console
    from rasai import report_completion

    execute = improvement_console.execute_improvement_intelligence
    if not getattr(execute, "_rasai_local_refresh_marker", False):
        @wraps(execute)
        def execute_with_refresh_marker(*args: Any, **kwargs: Any):
            progress = kwargs.get("progress")
            try:
                result = execute(*args, **kwargs)
            except Exception:
                # The console failure path still rebuilds the advisory page, but should
                # not issue any collector/provider request while doing so.
                _STATE.pending = True
                _STATE.progress = None
                raise
            _STATE.pending = True
            _STATE.progress = progress if callable(progress) else None
            return result

        execute_with_refresh_marker._rasai_local_refresh_marker = True  # type: ignore[attr-defined]
        improvement_console.execute_improvement_intelligence = execute_with_refresh_marker

    original_finalize = report_completion.finalize_audit_report_site
    if getattr(original_finalize, "_rasai_improvement_local_refresh_guard", False):
        return

    @wraps(original_finalize)
    def finalize_with_local_refresh(*, audit_id: str, workspace: Any, **kwargs: Any):
        if not bool(getattr(_STATE, "pending", False)):
            return original_finalize(audit_id=audit_id, workspace=workspace, **kwargs)

        _STATE.pending = False
        progress = getattr(_STATE, "progress", None)
        _STATE.progress = None
        if callable(progress):
            progress(
                "REPORT_REFRESH",
                98.0,
                "atualizando projeções HTML locais; nenhum collector/API será chamado novamente",
            )

        errors = _refresh_reports_local_only(audit_id=audit_id, workspace=workspace)
        inspected = report_completion.inspect_audit_report_site(
            audit_id=audit_id,
            workspace=workspace,
        )

        if callable(progress):
            progress(
                "REPORT_REFRESH",
                100.0,
                "relatórios locais atualizados a partir das evidências já persistidas",
            )

        return report_completion.AuditReportCompletion(
            expected_pages=inspected.expected_pages,
            generated_pages=inspected.generated_pages,
            missing_pages=inspected.missing_pages,
            renderer_errors=tuple((*getattr(inspected, "renderer_errors", ()), *errors)),
        )

    finalize_with_local_refresh._rasai_improvement_local_refresh_guard = True  # type: ignore[attr-defined]
    report_completion.finalize_audit_report_site = finalize_with_local_refresh


def install() -> None:
    """Install the progress/refinalization refinement once for the interactive console."""
    global _INSTALLED
    if _INSTALLED:
        return
    _install_progress_contract()
    # At this point console_entrypoint has already composed standards/GSC/external
    # finalizer wrappers. Installing this guard now makes it the outermost guard.
    _install_local_refresh_guard()
    _INSTALLED = True
