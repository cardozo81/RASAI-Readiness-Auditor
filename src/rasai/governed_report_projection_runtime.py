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
    """Return the persisted fulfillment summary without filesystem report projection."""
    from rasai import audit_fulfillment
    return audit_fulfillment.read_summary(workspace, audit_id)

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
    """Ensure AI sealing does not trigger an extra durable sync before M9/M10."""
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
    _install_reprocess_boundary()
    _INSTALLED = True


__all__ = [
    "install",
    "project_persisted_fulfillment",
    "reconcile_before_reporting",
]
