"""Read-only report projection for persisted fulfillment state.

The historical fulfillment/finalizer chain mixed three concerns:

1. reconciling canonical fulfillment from persisted execution state;
2. deciding when the AUD is logically complete; and
3. projecting that state into HTML/JSON presentation.

Governed execution keeps (1) and (2) before the first report renderer. During report
materialization, only filesystem presentation artifacts may change; ``audit.db`` is
read-only. This module also removes the older AI-seal sync because AI sealing happens
before final scoring/recommendation derivations.
"""
from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any

from rasai.governed_analysis_runtime import report_projection_active


_INSTALLED = False


def project_persisted_fulfillment(*, workspace: Any, audit_id: str):
    """Project the already-persisted fulfillment summary without recalculating it."""
    from rasai import audit_fulfillment

    summary = audit_fulfillment.read_summary(workspace, audit_id)
    if summary is None:
        return None

    report_dir = Path(workspace.root) / "report"
    report_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "audit_id": summary.audit_id,
        "contract_version": audit_fulfillment.CONTRACT_VERSION,
        "processing_status": summary.processing_status,
        "score_status": summary.score_status,
        "report_status": summary.report_status,
        "consolidation_eligible": summary.consolidation_eligible,
        "temporal_status": summary.temporal_status,
        "required_items": summary.required_items,
        "successful_items": summary.successful_items,
        "pending_items": summary.pending_items,
        "blocked_items": summary.blocked_items,
        "expired_items": summary.expired_items,
        "total_attempts": summary.total_attempts,
        "reprocess_count": summary.reprocess_count,
        "last_reprocess_id": summary.last_reprocess_id,
        "completed_at": summary.completed_at,
    }
    (report_dir / "processing-status.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
        newline="\n",
    )

    banner = audit_fulfillment._banner(summary)
    marker = audit_fulfillment._REPORT_MARKER
    for path in report_dir.glob("*.html"):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
        if marker in text:
            text = re.sub(
                re.escape(marker)
                + r'<section class="rasai-fulfillment-banner.*?</section>',
                banner,
                text,
                count=1,
                flags=re.DOTALL,
            )
        else:
            body = re.search(r"<body(?:\s[^>]*)?>", text, flags=re.IGNORECASE)
            if body:
                text = text[: body.end()] + banner + text[body.end() :]
            else:
                text = banner + text
        try:
            path.write_text(text, encoding="utf-8", newline="\n")
        except OSError:
            continue
    return summary


def reconcile_before_reporting(*, workspace: Any, audit_id: str):
    """Persist the canonical fulfillment outcome immediately before reporting."""
    if report_projection_active():
        raise RuntimeError(
            "FULFILLMENT_RECONCILIATION_DURING_REPORT: durable reconciliation must precede reporting"
        )

    # Core and optional fulfillment projections are distinct views over the same
    # persisted AUD. Reconcile both before the final logical status is calculated.
    # Neither operation performs source/API/provider collection.
    from rasai import core_reprocessing
    from rasai import fulfillment_execution_contract as contract

    core_reprocessing.synchronize_core_work_items(workspace, audit_id)
    return contract.reconcile_requested_components(
        workspace=workspace,
        audit_id=audit_id,
    )


def _install_projection_reconciliation_guard() -> None:
    from rasai import fulfillment_execution_contract as contract

    current = contract.reconcile_requested_components
    if bool(getattr(current, "_rasai_governed_report_projection", False)):
        return

    def reconcile_requested_components(*, workspace: Any, audit_id: str) -> None:
        if report_projection_active():
            project_persisted_fulfillment(workspace=workspace, audit_id=audit_id)
            return
        current(workspace=workspace, audit_id=audit_id)

    reconcile_requested_components._rasai_governed_report_projection = True
    reconcile_requested_components._rasai_original = current
    contract.reconcile_requested_components = reconcile_requested_components


def _remove_early_ai_seal_sync() -> None:
    """Remove the legacy durable sync that ran before M9/M10 completed."""
    from rasai import audit_phase_runtime as phase

    current = phase.mark_ai_sealed
    if not bool(getattr(current, "_rasai_final_persisted_sync", False)):
        return
    base = getattr(current, "_rasai_original", None)
    if not callable(base):
        raise RuntimeError("governed AI-seal wrapper lost its original callable")
    phase.mark_ai_sealed = base

    try:
        from rasai import audit_runner
        audit_runner.mark_ai_sealed = base
    except ImportError:
        pass
    try:
        from rasai import governed_reprocess_runtime as rpr
        rpr.mark_ai_sealed = base
    except ImportError:
        pass


def _install_audit_pre_report_boundary() -> None:
    """Run durable fulfillment reconciliation after final derivations, before M11."""
    try:
        from rasai import audit_runner
    except ImportError:
        return

    current = audit_runner.execute_m11
    if bool(getattr(current, "_rasai_pre_report_fulfillment", False)):
        return

    def execute_m11_after_fulfillment(*args: Any, **kwargs: Any):
        # audit_runner owns durable reconciliation before it sets REPORTING.
        # execute_m11 is already inside the read-only projection boundary.
        return current(*args, **kwargs)

    execute_m11_after_fulfillment._rasai_pre_report_fulfillment = True
    execute_m11_after_fulfillment._rasai_original = current
    audit_runner.execute_m11 = execute_m11_after_fulfillment


def _install_reprocess_boundary() -> None:
    """Keep RPR durable reconciliation before its renderer and projection-only after it."""
    try:
        from rasai import governed_reprocess_runtime as rpr
    except ImportError:
        return

    current_mark = rpr.mark_ai_sealed
    if not bool(getattr(current_mark, "_rasai_rpr_pre_report_fulfillment", False)):
        def mark_and_reconcile(*args: Any, **kwargs: Any):
            result = current_mark(*args, **kwargs)
            audit_id = str(kwargs.get("audit_id") or "")
            workspace = kwargs.get("workspace")
            if audit_id and workspace is not None:
                reconcile_before_reporting(workspace=workspace, audit_id=audit_id)
            return result

        mark_and_reconcile._rasai_rpr_pre_report_fulfillment = True
        mark_and_reconcile._rasai_original = current_mark
        rpr.mark_ai_sealed = mark_and_reconcile

    # RPR historically recalculated fulfillment again after the renderer. Once the
    # governed pre-report reconciliation is complete, that late call must be a pure
    # filesystem projection from the persisted summary.
    rpr.project_report_validity = project_persisted_fulfillment


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    # These adapters are execution governance, not report features. Installing them at
    # this late bootstrap point guarantees that all legacy RPR/fulfillment wrappers are
    # already composed before we add selective stale invalidation and M24 continuation.
    from rasai.governed_fulfillment_invalidation import install as install_stale_invalidation
    from rasai.m24_partial_runtime import install as install_m24_partial
    from rasai.m24_reprocess_compat import install as install_m24_reprocess_compat

    install_stale_invalidation()
    install_m24_reprocess_compat()
    install_m24_partial()
    _install_projection_reconciliation_guard()
    _remove_early_ai_seal_sync()
    _install_audit_pre_report_boundary()
    _install_reprocess_boundary()
    _INSTALLED = True


__all__ = [
    "install",
    "project_persisted_fulfillment",
    "reconcile_before_reporting",
]
