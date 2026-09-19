"""Concurrency-safe composition for core selective reprocessing.

Core recovery and the downstream component recovery must share one RPR id, but they
must not achieve that by temporarily replacing module globals. This adapter installs
stable ContextVar-aware hooks once and replaces the first-generation core wrapper with
a context-safe equivalent. Separate threads/tasks therefore cannot borrow another
AUD's reprocess id or pending-item filter.
"""
from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rasai.audit_fulfillment import FAILED_RETRYABLE, SUCCESS, project_report_validity, recalculate
from rasai.persistence import AuditWorkspace


@dataclass(frozen=True, slots=True)
class _CoreReprocessContext:
    audit_id: str
    reprocess_id: str


_CONTEXT: ContextVar[_CoreReprocessContext | None] = ContextVar(
    "rasai_core_reprocess_context",
    default=None,
)
_INSTALLED = False


def _install_contextual_hooks(module: Any, core: Any) -> None:
    start = module.start_reprocess_run
    if not getattr(start, "_rasai_contextual_rpr_start", False):
        def contextual_start(workspace: Any, audit_id: str, *args: Any, **kwargs: Any) -> str:
            current = _CONTEXT.get()
            if current is not None and current.audit_id == audit_id:
                return current.reprocess_id
            return start(workspace, audit_id, *args, **kwargs)

        contextual_start._rasai_contextual_rpr_start = True
        contextual_start._rasai_original = start
        module.start_reprocess_run = contextual_start

    finish = module.finish_reprocess_run
    if not getattr(finish, "_rasai_contextual_rpr_finish", False):
        def contextual_finish(workspace: Any, reprocess_id: str, *args: Any, **kwargs: Any):
            current = _CONTEXT.get()
            if current is not None and current.reprocess_id == reprocess_id:
                return recalculate(workspace, current.audit_id)
            return finish(workspace, reprocess_id, *args, **kwargs)

        contextual_finish._rasai_contextual_rpr_finish = True
        contextual_finish._rasai_original = finish
        module.finish_reprocess_run = contextual_finish

    latest = module._latest_pending
    if not getattr(latest, "_rasai_contextual_core_filter", False):
        def contextual_latest(workspace: AuditWorkspace, audit_id: str):
            items = latest(workspace, audit_id)
            current = _CONTEXT.get()
            if current is None or current.audit_id != audit_id:
                return items
            unresolved = core._core_unresolved(workspace, audit_id)
            return tuple(
                item
                for item in items
                if item.component not in core.CORE_COMPONENTS
                and not (unresolved and item.component in core._AI_COMPONENTS)
            )

        contextual_latest._rasai_contextual_core_filter = True
        contextual_latest._rasai_original = latest
        module._latest_pending = contextual_latest


def _safe_core_wrapper(base: Any, module: Any, core: Any):
    if getattr(base, "_rasai_core_reprocessing_contextsafe", False):
        return base

    def reprocess_with_core_context(
        audit_id: str,
        *,
        audits_root: str | Path = "audits",
        source: str = "CLI",
    ):
        workspace = AuditWorkspace.open(Path(audits_root) / audit_id)
        module._backfill_contract(workspace, audit_id)
        core.synchronize_core_work_items(workspace, audit_id)
        if not core._core_unresolved(workspace, audit_id):
            return base(audit_id, audits_root=audits_root, source=source)

        initial_items = core.list_work_items(workspace, audit_id)
        skipped_success = sum(item.required and item.status == SUCCESS for item in initial_items)
        reprocess_id = core.start_reprocess_run(
            workspace,
            audit_id,
            source=source,
            note="selective core prerequisite recovery",
        )
        attempted = 0
        successful = 0
        affected: set[str] = set()

        for item in tuple(
            value
            for value in core._retryable_core(workspace, audit_id)
            if value.component == core.HTTP_ACQUISITION
        ):
            attempted += 1
            ok, changed = core._attempt(workspace, audit_id, item, reprocess_id)
            successful += int(ok)
            affected.update(changed)
        core.synchronize_core_work_items(workspace, audit_id)

        render_items = tuple(
            value
            for value in core._retryable_core(workspace, audit_id)
            if value.component == core.RENDER_CAPTURE
        )
        if render_items:
            from rasai import m3

            with m3.BrowserIdentityRenderer() as renderer:
                for item in render_items:
                    attempted += 1
                    ok, changed = core._attempt(
                        workspace,
                        audit_id,
                        item,
                        reprocess_id,
                        renderer=renderer,
                    )
                    successful += int(ok)
                    affected.update(changed)
        core.synchronize_core_work_items(workspace, audit_id)

        for item in tuple(
            value
            for value in core._retryable_core(workspace, audit_id)
            if value.component == core.CONTENT_EXTRACTION
        ):
            attempted += 1
            ok, changed = core._attempt(workspace, audit_id, item, reprocess_id)
            successful += int(ok)
            affected.update(changed)
        core.synchronize_core_work_items(workspace, audit_id)

        for snapshot_id in sorted(affected):
            core._recompute_deterministic_snapshot(
                workspace,
                audit_id,
                snapshot_id,
                reprocess_id,
            )
        if affected:
            from rasai.reprocess_ai import recompute_derived_after_ai

            recompute_derived_after_ai(
                workspace=workspace,
                audit_id=audit_id,
                reprocess_id=reprocess_id,
                semantic_changed=False,
            )

        token = _CONTEXT.set(_CoreReprocessContext(audit_id, reprocess_id))
        try:
            downstream = base(audit_id, audits_root=audits_root, source=source)
        finally:
            _CONTEXT.reset(token)

        attempted += int(getattr(downstream, "attempted_items", 0) or 0)
        successful += int(getattr(downstream, "successful_items", 0) or 0)
        summary = recalculate(workspace, audit_id)
        summary = core.finish_reprocess_run(
            workspace,
            reprocess_id,
            status=SUCCESS if summary.processing_status == "COMPLETE" else FAILED_RETRYABLE,
            attempted_items=attempted,
            successful_items=successful,
            note=(
                "all configured requirements satisfied"
                if summary.processing_status == "COMPLETE"
                else "one or more configured requirements remain unresolved"
            ),
        )
        summary = project_report_validity(audit_id=audit_id, workspace=workspace)
        return module.ReprocessResult(
            audit_id=audit_id,
            reprocess_id=reprocess_id,
            processing_status=summary.processing_status,
            score_status=summary.score_status,
            report_status=summary.report_status,
            consolidation_eligible=summary.consolidation_eligible,
            attempted_items=attempted,
            successful_items=successful,
            skipped_success_items=skipped_success,
            remaining_items=summary.pending_items + summary.blocked_items,
            temporal_expired_items=summary.expired_items,
            report_root=workspace.root / "report-catalog",
        )

    reprocess_with_core_context._rasai_core_reprocessing_contextsafe = True
    reprocess_with_core_context._rasai_original = base
    return reprocess_with_core_context


def install() -> None:
    """Replace temporary-global core composition with stable ContextVar hooks."""
    global _INSTALLED
    if _INSTALLED:
        return

    from rasai import audit_reprocess, core_reprocessing

    current = audit_reprocess.reprocess_audit
    unsafe_base = getattr(current, "_rasai_original", None)
    base = unsafe_base if getattr(current, "_rasai_core_reprocessing", False) and callable(unsafe_base) else current

    _install_contextual_hooks(audit_reprocess, core_reprocessing)
    audit_reprocess.reprocess_audit = _safe_core_wrapper(base, audit_reprocess, core_reprocessing)
    _INSTALLED = True
