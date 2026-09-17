"""Read-only report projection for persisted fulfillment state.

The historical fulfillment finalizer mixed two concerns: reconciling/mutating the
canonical AUD state and projecting that state into ``report/``.  Governed execution
must finish every durable reconciliation before reporting starts, while report
materialization may only read ``audit.db`` and write report artifacts.

This composition keeps the existing public banner/status contract without allowing a
late finalizer wrapper to mutate canonical audit state.
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


def _install_pre_report_reconciliation() -> None:
    """Make the final durable fulfillment state part of the AI-close boundary."""
    from rasai import audit_phase_runtime as phase
    from rasai import fulfillment_execution_contract as contract

    current = phase.mark_ai_sealed
    if bool(getattr(current, "_rasai_pre_report_fulfillment", False)):
        return

    def mark_ai_sealed(*args: Any, **kwargs: Any):
        result = current(*args, **kwargs)
        audit_id = str(kwargs.get("audit_id") or "")
        workspace = kwargs.get("workspace")
        if audit_id and workspace is not None:
            contract.reconcile_requested_components(
                workspace=workspace,
                audit_id=audit_id,
            )
        return result

    mark_ai_sealed._rasai_pre_report_fulfillment = True
    mark_ai_sealed._rasai_original = current
    phase.mark_ai_sealed = mark_ai_sealed

    # These modules import the phase callable by value. Keep every execution path on
    # the same boundary rather than allowing CLI and RPR to diverge.
    try:
        from rasai import audit_runner
        audit_runner.mark_ai_sealed = mark_ai_sealed
    except ImportError:
        pass
    try:
        from rasai import governed_reprocess_runtime
        governed_reprocess_runtime.mark_ai_sealed = mark_ai_sealed
    except ImportError:
        pass


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    _install_projection_reconciliation_guard()
    _install_pre_report_reconciliation()
    _INSTALLED = True


__all__ = ["install", "project_persisted_fulfillment"]
