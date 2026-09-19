"""Governed selective reprocessing lifecycle.

Core reprocessing already owns HTTP/render/extraction recovery.  This module composes
*inside* that wrapper: after core recovery but before its downstream AI recovery it
finishes pending live/external collectors, seals a new evidence version, projects only
stale dependent AI tasks back to fulfillment, then lets the existing semantic/
technical/content recovery run.  Registered advisory AI runs after those recoveries and
before the first report renderer.

No provider retry/fallback/pricing logic is duplicated here.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, replace
from pathlib import Path
import json
import sqlite3
from typing import Any, Iterator, Mapping

from rasai.ai_governance import (
    TASK_STALE,
    collection_state_is_terminal,
    latest_evidence_snapshot,
    seal_evidence,
)
from rasai.audit_fulfillment import (
    FAILED_RETRYABLE,
    NOT_APPLICABLE,
    SUCCESS,
    list_work_items,
    project_report_validity,
    recalculate,
    set_work_item_status,
)
from rasai.audit_phase_runtime import mark_ai_sealed, run_registered_ai_phase
from rasai.operational_log import try_append_operational_event
from rasai.persistence import AuditWorkspace


_INSTALLED = False
_AI_COMPONENTS = frozenset(
    {"SEMANTIC_AI", "TECHNICAL_AI", "CONTENT_REMEDIATION_AI", "IMPROVEMENT_INTELLIGENCE"}
)
_LIVE_COMPONENTS = frozenset(
    {"WEB_PERFORMANCE", "SYNTHETIC_APDEX", "EXPERIENCE_APDEX"}
)
_OPTIONAL_COLLECTORS = frozenset(
    {"SEARCH_INTELLIGENCE", "GOOGLE_SEARCH_CONSOLE"}
)


@dataclass(frozen=True, slots=True)
class ReprocessPreparation:
    snapshot: Any
    recovered: dict[str, str]
    evaluated_optional: frozenset[str]
    sealed_new_evidence: bool


def _table_exists(connection: sqlite3.Connection, name: str) -> bool:
    return connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone() is not None


def _pending_item(workspace: Any, audit_id: str, component: str):
    return next(
        (
            item
            for item in list_work_items(workspace, audit_id, pending_only=True)
            if bool(item.required) and str(item.component) == component
        ),
        None,
    )


def _current_reprocess_id(workspace: Any, audit_id: str) -> str | None:
    try:
        from rasai import reprocess_runtime_safety

        value = reprocess_runtime_safety._RPR_CONTEXT.get()
        if value is not None and value.audit_id == audit_id and value.reprocess_id:
            return str(value.reprocess_id)
    except Exception:
        pass
    connection = sqlite3.connect(workspace.database)
    try:
        row = connection.execute(
            """SELECT reprocess_id FROM audit_reprocess_runs
               WHERE audit_id=? AND completed_at IS NULL
               ORDER BY started_at DESC LIMIT 1""",
            (audit_id,),
        ).fetchone()
    except sqlite3.OperationalError:
        row = None
    finally:
        connection.close()
    return str(row[0]) if row and row[0] else None


def _apply_live_result(
    workspace: Any,
    audit_id: str,
    component: str,
    *,
    success: bool,
    result_ref: str,
) -> None:
    if success:
        set_work_item_status(
            workspace,
            audit_id=audit_id,
            component=component,
            status=SUCCESS,
            result_ref=result_ref,
            retryable=True,
        )
        return
    set_work_item_status(
        workspace,
        audit_id=audit_id,
        component=component,
        status=FAILED_RETRYABLE,
        error_class="RECOVERY",
        error_code=f"{component}_RETRY_INCOMPLETE",
        error_message=f"selective reprocessing did not satisfy {component}/AUDIT",
        retryable=True,
    )


def _recover_live_measurements(workspace: Any, audit_id: str) -> dict[str, str]:
    states: dict[str, str] = {}
    for component in ("WEB_PERFORMANCE", "SYNTHETIC_APDEX", "EXPERIENCE_APDEX"):
        item = _pending_item(workspace, audit_id, component)
        if item is None:
            continue
        try:
            if component == "WEB_PERFORMANCE":
                from rasai.reprocess_measurements import recover_web_performance
                success = bool(
                    recover_web_performance(
                        workspace=workspace,
                        audit_id=audit_id,
                        item=item,
                    )
                )
                ref = "web-performance:effective"
            elif component == "SYNTHETIC_APDEX":
                from rasai.reprocess_measurements import recover_synthetic_apdex
                success = bool(
                    recover_synthetic_apdex(
                        workspace=workspace,
                        audit_id=audit_id,
                        item=item,
                    )
                )
                ref = "synthetic-apdex:effective"
            else:
                from rasai.reprocess_measurements import recover_experience_apdex
                success = bool(
                    recover_experience_apdex(
                        workspace=workspace,
                        audit_id=audit_id,
                        item=item,
                    )
                )
                ref = "experience-apdex:effective"
        except Exception as exc:
            success = False
            ref = f"{component.casefold()}:incomplete"
            try_append_operational_event(
                workspace,
                "AUDIT_REPROCESS_COLLECTION_FAILURE",
                level="WARNING",
                audit_id=audit_id,
                component=component,
                error_type=type(exc).__name__,
                error_message=str(exc)[:512],
            )
        _apply_live_result(
            workspace,
            audit_id,
            component,
            success=success,
            result_ref=ref,
        )
        states[component] = "SUCCESS" if success else "FAILED_RETRYABLE"
    return states


def _registered_collector(name: str):
    from rasai import audit_phase_runtime

    hook = audit_phase_runtime._COLLECTION_HOOKS.get(str(name).upper())
    return hook.callback if hook is not None else None


def _recover_optional_collectors(
    workspace: Any,
    audit_id: str,
) -> tuple[dict[str, str], frozenset[str]]:
    """Retry only explicitly required optional collectors that are still pending.

    Search Intelligence and Google Search Console are part of the fulfillment
    denominator when explicitly requested. Non-blocking observability sources such as
    Common Crawl, CrUX History and Clarity are not retried merely because another RPR
    requirement is pending; refreshing those observations requires a new audit unless
    they gain an explicit required work-item contract.
    """
    from rasai import selective_optional_reprocess as optional

    states: dict[str, str] = {}
    evaluated: set[str] = set()

    search = _pending_item(workspace, audit_id, "SEARCH_INTELLIGENCE")
    if search is not None and not optional._expired(search):
        evaluated.add("SEARCH_INTELLIGENCE")
        try:
            success = bool(optional._recover_search(workspace, audit_id, search))
        except Exception as exc:
            success = False
            set_work_item_status(
                workspace,
                audit_id=audit_id,
                component="SEARCH_INTELLIGENCE",
                status=FAILED_RETRYABLE,
                error_class="SEARCH_PROVIDER",
                error_code="SEARCH_INTELLIGENCE_RUNTIME_ERROR",
                error_message=f"{type(exc).__name__}: {str(exc)[:512]}",
                retryable=True,
            )
        states["SEARCH_INTELLIGENCE"] = "SUCCESS" if success else "FAILED_RETRYABLE"

    gsc = _pending_item(workspace, audit_id, "GOOGLE_SEARCH_CONSOLE")
    if gsc is not None and not optional._expired(gsc):
        callback = _registered_collector("GOOGLE_SEARCH_CONSOLE")
        if callback is not None:
            evaluated.add("GOOGLE_SEARCH_CONSOLE")
            with optional._original_optional_environment(workspace, audit_id):
                try:
                    raw = callback(audit_id=audit_id, workspace=workspace, source_blocked=False)
                    state = str((raw or {}).get("collection_state") or (raw or {}).get("service_state") or "SUCCESS").upper()
                except Exception as exc:
                    state = "ERROR"
                    try_append_operational_event(
                        workspace,
                        "AUDIT_REPROCESS_COLLECTION_FAILURE",
                        level="WARNING",
                        audit_id=audit_id,
                        component="GOOGLE_SEARCH_CONSOLE",
                        error_type=type(exc).__name__,
                        error_message=str(exc)[:512],
                    )
            optional._reconcile_gsc_rpr(workspace, audit_id)
            refreshed = _pending_item(workspace, audit_id, "GOOGLE_SEARCH_CONSOLE")
            states["GOOGLE_SEARCH_CONSOLE"] = state if refreshed is not None else "SUCCESS"

    return states, frozenset(evaluated)

def _collection_states(workspace: Any, audit_id: str) -> dict[str, str]:
    states: dict[str, str] = {}
    for item in list_work_items(workspace, audit_id):
        if not bool(item.required):
            continue
        component = str(item.component)
        if component in {
            "SEMANTIC_AI",
            "TECHNICAL_AI",
            "CONTENT_REMEDIATION_AI",
            "IMPROVEMENT_INTELLIGENCE",
        }:
            continue
        states[f"FULFILLMENT:{component}:{item.scope_key}"] = str(item.status).upper()

    connection = sqlite3.connect(workspace.database)
    connection.row_factory = sqlite3.Row
    try:
        if _table_exists(connection, "standards_service_runs"):
            rows = connection.execute(
                "SELECT service_id,state FROM standards_service_runs WHERE audit_id=?",
                (audit_id,),
            ).fetchall()
            for row in rows:
                states[f"SERVICE:{row['service_id']}"] = str(row["state"] or "NO_DATA").upper()
    finally:
        connection.close()
    return states


def _terminalized_states(states: Mapping[str, str]) -> dict[str, str]:
    output: dict[str, str] = {}
    for key, value in states.items():
        state = str(value or "NO_DATA").upper()
        # A still-waiting prerequisite at the end of the bounded collection attempt is
        # represented as a terminal limitation in this evidence version. It remains
        # retryable in fulfillment, but must not leave the evidence seal racing forever.
        if not collection_state_is_terminal(state):
            state = "PARTIAL" if state in {"WAITING_FOR_DATA", "PENDING"} else "ERROR"
        output[str(key)] = state
    return output


def _stale_tasks_to_fulfillment(workspace: Any, audit_id: str) -> int:
    connection = sqlite3.connect(workspace.database)
    connection.row_factory = sqlite3.Row
    try:
        try:
            rows = connection.execute(
                """SELECT ai_task_id,purpose,scope_key FROM ai_tasks
                   WHERE audit_id=? AND status=?""",
                (audit_id, TASK_STALE),
            ).fetchall()
        except sqlite3.OperationalError:
            return 0
    finally:
        connection.close()

    changed = 0
    for row in rows:
        purpose = str(row["purpose"] or "").upper()
        if purpose == "SEMANTIC_M7":
            component = "SEMANTIC_AI"
            scope_key = str(row["scope_key"])
        elif purpose == "TECHNICAL_AI":
            component = "TECHNICAL_AI"
            scope_key = "AUDIT"
        elif purpose == "IMPROVEMENT_INTELLIGENCE":
            component = "IMPROVEMENT_INTELLIGENCE"
            scope_key = "AUDIT"
        else:
            continue
        set_work_item_status(
            workspace,
            audit_id=audit_id,
            component=component,
            scope_key=scope_key,
            status=FAILED_RETRYABLE,
            error_class="EVIDENCE_VERSION",
            error_code="AI_RESULT_STALE",
            error_message=(
                "resultado de IA invalidado porque sua dependência de evidência mudou; "
                "somente esta finalidade será reprocessada"
            ),
            retryable=True,
        )
        changed += 1
    return changed


def prepare_reprocess_evidence(workspace: Any, audit_id: str) -> Any:
    """Finish bounded pending collection and seal the evidence used by RPR AI."""
    try_append_operational_event(
        workspace,
        "AUDIT_REPROCESS_COLLECTION_PHASE_STARTED",
        audit_id=audit_id,
        reprocess_id=_current_reprocess_id(workspace, audit_id),
    )
    recovered = {}
    recovered.update(_recover_live_measurements(workspace, audit_id))
    recovered.update(_recover_optional_collectors(workspace, audit_id))
    states = _terminalized_states(_collection_states(workspace, audit_id))
    prior = latest_evidence_snapshot(workspace, audit_id)
    snapshot = seal_evidence(
        workspace=workspace,
        audit_id=audit_id,
        collection_states=states,
        context={
            "phase": "AUDIT_REPROCESS",
            "reprocess_id": _current_reprocess_id(workspace, audit_id),
            "recovered_collectors": recovered,
        },
    )
    stale = _stale_tasks_to_fulfillment(workspace, audit_id)
    try_append_operational_event(
        workspace,
        "AUDIT_REPROCESS_EVIDENCE_SEALED",
        audit_id=audit_id,
        reprocess_id=_current_reprocess_id(workspace, audit_id),
        evidence_snapshot_id=snapshot.evidence_snapshot_id,
        evidence_version=snapshot.version_number,
        evidence_fingerprint=snapshot.fingerprint,
        supersedes_snapshot_id=(prior.evidence_snapshot_id if prior is not None else None),
        stale_ai_tasks=stale,
        collector_states=states,
    )
    return snapshot


@contextmanager
def _suppress_mid_reprocess_reporting() -> Iterator[Any]:
    from rasai import report_completion

    current = report_completion.finalize_audit_report_site

    def deferred(*args: Any, **kwargs: Any):
        del args, kwargs
        return None

    report_completion.finalize_audit_report_site = deferred
    try:
        yield current
    finally:
        report_completion.finalize_audit_report_site = current


def _registered_ai_and_report(
    *,
    workspace: Any,
    audit_id: str,
    renderer: Any,
) -> None:
    snapshot = latest_evidence_snapshot(workspace, audit_id)
    if snapshot is None:
        raise RuntimeError("RPR cannot run AI without a sealed evidence version")
    outcomes = run_registered_ai_phase(
        audit_id=audit_id,
        workspace=workspace,
        evidence_snapshot=snapshot,
    )
    mark_ai_sealed(
        audit_id=audit_id,
        workspace=workspace,
        evidence_snapshot=snapshot,
        outcomes=outcomes,
    )
    renderer(audit_id=audit_id, workspace=workspace)
    project_report_validity(audit_id=audit_id, workspace=workspace)


def _install_core_composition() -> None:
    """Inject pre-AI collection into the core-reprocessing wrapper factory.

    core_reprocessing.install() executes later from ai_efficiency_policy. Replacing the
    factory *before* that install lets its existing wrapper remain owner of core capture,
    reprocess ids, archive semantics and final accounting while this module owns only the
    new causal boundary.
    """
    from rasai import core_reprocessing

    factory = core_reprocessing._wrap_reprocess
    if bool(getattr(factory, "_rasai_governed_reprocess", False)):
        return

    def wrap_reprocess(original: Any, module: Any):
        def downstream_after_core(
            audit_id: str,
            *,
            audits_root: str | Path = "audits",
            source: str = "CLI",
        ):
            workspace = AuditWorkspace.open(Path(audits_root) / audit_id)
            prepare_reprocess_evidence(workspace, audit_id)

            # These collectors were already attempted before the seal. Even when they
            # remain retryable, they must not be called again after AI in this same RPR.
            latest = module._latest_pending

            def ai_only_pending(active_workspace: Any, active_audit_id: str):
                return tuple(
                    item
                    for item in latest(active_workspace, active_audit_id)
                    if str(item.component) not in _LIVE_COMPONENTS
                    and str(item.component) not in _OPTIONAL_COLLECTORS
                )

            module._latest_pending = ai_only_pending
            try:
                with _suppress_mid_reprocess_reporting() as renderer:
                    result = original(
                        audit_id,
                        audits_root=audits_root,
                        source=source,
                    )
                    _registered_ai_and_report(
                        workspace=workspace,
                        audit_id=audit_id,
                        renderer=renderer,
                    )
                    summary = recalculate(workspace, audit_id)
                    try:
                        result = replace(
                            result,
                            processing_status=summary.processing_status,
                            score_status=summary.score_status,
                            report_status=summary.report_status,
                            consolidation_eligible=summary.consolidation_eligible,
                            remaining_items=summary.pending_items + summary.blocked_items,
                            temporal_expired_items=summary.expired_items,
                        )
                    except TypeError:
                        pass
                    return result
            finally:
                module._latest_pending = latest

        downstream_after_core._rasai_governed_reprocess_downstream = True
        downstream_after_core._rasai_original = original
        return factory(downstream_after_core, module)

    wrap_reprocess._rasai_governed_reprocess = True
    wrap_reprocess._rasai_original = factory
    core_reprocessing._wrap_reprocess = wrap_reprocess


def install_pre_core() -> None:
    """Install before ai_efficiency_policy/core_reprocessing installs its wrapper."""
    global _INSTALLED
    if _INSTALLED:
        return
    _install_core_composition()
    _INSTALLED = True


__all__ = ["install_pre_core", "prepare_reprocess_evidence"]
