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
import hashlib
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
_DERIVED_RECOVERY_COMPONENTS = frozenset({"PASSIVE_SECURITY"})


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


_MATERIAL_TABLES = frozenset({
    "web_performance_runs",
    "web_performance_observations",
    "synthetic_apdex_runs",
    "synthetic_apdex_samples",
    "synthetic_apdex_summaries",
    "synthetic_ux_apdex_runs",
    "synthetic_ux_apdex_samples",
    "synthetic_ux_apdex_summaries",
    "standards_service_runs",
    "standards_metric_observations",
})
_VOLATILE_MATERIAL_COLUMNS = frozenset({
    "created_at",
    "updated_at",
    "captured_at",
    "calculated_at",
    "attempted_at",
    "started_at",
    "finished_at",
    "completed_at",
    "observed_at",
    "last_attempt_at",
    "error_message",
    "last_error_message",
})


def _material_table_names(connection: sqlite3.Connection) -> tuple[str, ...]:
    names = {
        str(row[0])
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    return tuple(sorted(
        name for name in names
        if name in _MATERIAL_TABLES
        or name.startswith("serp_")
        or name.startswith("passive_security_")
    ))


def _material_rows(
    connection: sqlite3.Connection,
    table: str,
    *,
    audit_id: str | None,
) -> list[dict[str, Any]]:
    columns = [
        str(row[1])
        for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
    ]
    selected = [name for name in columns if name not in _VOLATILE_MATERIAL_COLUMNS]
    if not selected:
        return []
    connection.row_factory = sqlite3.Row
    where = " WHERE audit_id=?" if audit_id is not None and "audit_id" in columns else ""
    params = (audit_id,) if where else ()
    rows = connection.execute(
        f"SELECT {','.join(selected)} FROM {table}{where}",
        params,
    ).fetchall()
    values = [dict(row) for row in rows]
    values.sort(
        key=lambda row: json.dumps(
            row,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
    )
    return values


def _material_state_fingerprint(workspace: Any, audit_id: str) -> str:
    payload: dict[str, Any] = {"audit": {}, "observability": {}}
    connection = sqlite3.connect(workspace.database)
    try:
        for table in _material_table_names(connection):
            payload["audit"][table] = _material_rows(
                connection,
                table,
                audit_id=audit_id,
            )
    finally:
        connection.close()

    try:
        from rasai.observability.store import observability_database_path
        sidecar = observability_database_path(Path(workspace.root))
    except Exception:
        sidecar = Path(workspace.root) / "artifacts" / "observability" / "observability.db"
    if sidecar.is_file():
        connection = sqlite3.connect(sidecar)
        try:
            names = {
                str(row[0])
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            for table in sorted(name for name in names if not name.startswith("sqlite_") and name != "integration_attempts"):
                payload["observability"][table] = _material_rows(
                    connection,
                    table,
                    audit_id=None,
                )
        finally:
            connection.close()

    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _current_evidence_ids(workspace: Any, audit_id: str) -> tuple[str, ...]:
    connection = sqlite3.connect(workspace.database)
    try:
        if not _table_exists(connection, "evidence"):
            return ()
        return tuple(
            str(row[0])
            for row in connection.execute(
                "SELECT evidence_id FROM evidence WHERE audit_id=? ORDER BY evidence_id",
                (audit_id,),
            ).fetchall()
        )
    finally:
        connection.close()


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
    from rasai import selective_optional_reprocess as optional

    states: dict[str, str] = {}
    for component in ("WEB_PERFORMANCE", "SYNTHETIC_APDEX", "EXPERIENCE_APDEX"):
        item = _pending_item(workspace, audit_id, component)
        if item is None:
            continue
        if optional._expired(item):
            try_append_operational_event(
                workspace,
                "AUDIT_REPROCESS_ITEM_EXPIRED",
                level="WARNING",
                audit_id=audit_id,
                reprocess_id=_current_reprocess_id(workspace, audit_id),
                component=component,
                scope_key=str(getattr(item, "scope_key", "AUDIT")),
                valid_until=getattr(item, "valid_until", None),
            )
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

def _passive_component_signature(workspace: Any, audit_id: str, *, persisted: bool) -> tuple[tuple[str, ...], ...]:
    from rasai import passive_security as security

    connection = sqlite3.connect(workspace.database)
    connection.row_factory = sqlite3.Row
    try:
        security.ensure_schema(connection)
        if persisted:
            rows = connection.execute(
                """SELECT component_id,library,version,ecosystem,confidence
                   FROM passive_security_components WHERE audit_id=?""",
                (audit_id,),
            ).fetchall()
            values = [
                (
                    str(row["component_id"] or ""),
                    str(row["library"] or ""),
                    str(row["version"] or ""),
                    str(row["ecosystem"] or ""),
                    str(row["confidence"] or ""),
                )
                for row in rows
            ]
        else:
            _resources, components, _context = security._resource_inventory(
                connection,
                workspace,
                audit_id,
            )
            values = [
                (
                    str(item.get("component_id") or ""),
                    str(item.get("library") or ""),
                    str(item.get("version") or ""),
                    str(item.get("ecosystem") or ""),
                    str(item.get("confidence") or ""),
                )
                for item in components
            ]
        return tuple(sorted(values))
    finally:
        connection.close()


def _archive_passive_security(workspace: Any, audit_id: str) -> None:
    reprocess_id = _current_reprocess_id(workspace, audit_id)
    if not reprocess_id:
        return
    from rasai.audit_fulfillment import archive_rows

    specs = (
        ("passive_security_runs", "run", "audit_id"),
        ("passive_security_resources", "resource", "resource_id"),
        ("passive_security_components", "component", "component_id"),
        ("passive_security_integrations", "integration", "integration_id"),
        ("passive_security_advisories", "advisory", "row_id"),
        ("passive_security_findings", "finding", "finding_id"),
        ("passive_security_remediations", "remediation", "remediation_id"),
    )
    connection = sqlite3.connect(workspace.database)
    connection.row_factory = sqlite3.Row
    try:
        existing = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        for table, entity_type, id_field in specs:
            if table not in existing:
                continue
            rows = [
                dict(row)
                for row in connection.execute(
                    f"SELECT * FROM {table} WHERE audit_id=?",
                    (audit_id,),
                ).fetchall()
            ]
            if rows:
                archive_rows(
                    workspace,
                    audit_id=audit_id,
                    reprocess_id=reprocess_id,
                    component="PASSIVE_SECURITY",
                    entity_type=entity_type,
                    id_field=id_field,
                    rows=rows,
                )
    finally:
        connection.close()


def _recover_impacted_deterministic(workspace: Any, audit_id: str) -> dict[str, str]:
    item = _pending_item(workspace, audit_id, "PASSIVE_SECURITY")
    if item is None:
        return {}

    from rasai import passive_security as security
    from rasai import selective_optional_reprocess as optional
    from rasai.reprocess_runtime_safety import record_reprocess_evaluation

    prior_components = _passive_component_signature(workspace, audit_id, persisted=True)
    current_components = _passive_component_signature(workspace, audit_id, persisted=False)
    components_changed = prior_components != current_components
    _archive_passive_security(workspace, audit_id)
    external_refreshed = False
    try:
        with optional._original_optional_environment(workspace, audit_id):
            if components_changed:
                security.collect_external_intelligence(
                    audit_id=audit_id,
                    workspace=workspace,
                    source_blocked=False,
                )
                external_refreshed = True
            result = security.analyze_passive_security(
                audit_id=audit_id,
                workspace=workspace,
                source_blocked=False,
            )
        status = str(result.get("status") or "").upper()
        success = status in {"COMPLETED", "PARTIAL"}
    except Exception as exc:
        status = "ERROR"
        success = False
        try_append_operational_event(
            workspace,
            "AUDIT_REPROCESS_DERIVED_FAILURE",
            level="WARNING",
            audit_id=audit_id,
            component="PASSIVE_SECURITY",
            error_type=type(exc).__name__,
            error_message=str(exc)[:512],
        )

    if success:
        set_work_item_status(
            workspace,
            audit_id=audit_id,
            component="PASSIVE_SECURITY",
            status=SUCCESS,
            result_ref=f"passive_security_runs:{audit_id}",
            retryable=True,
        )
    else:
        set_work_item_status(
            workspace,
            audit_id=audit_id,
            component="PASSIVE_SECURITY",
            status=FAILED_RETRYABLE,
            error_class="PASSIVE_SECURITY",
            error_code=status or "NO_RESULT",
            error_message="CAT-10 não pôde ser recalculado a partir da evidência efetiva",
            retryable=True,
        )

    reprocess_id = _current_reprocess_id(workspace, audit_id)
    if reprocess_id:
        refreshed = next(
            (
                value
                for value in list_work_items(workspace, audit_id)
                if str(value.component) == "PASSIVE_SECURITY"
            ),
            item,
        )
        record_reprocess_evaluation(
            workspace,
            item=refreshed,
            reprocess_id=reprocess_id,
            metadata={
                "component": "PASSIVE_SECURITY",
                "kind": "DEPENDENCY_IMPACT_RECALCULATION",
                "components_changed": components_changed,
                "external_intelligence_refreshed": external_refreshed,
            },
        )
    try_append_operational_event(
        workspace,
        "AUDIT_REPROCESS_DERIVED_RECALCULATED",
        audit_id=audit_id,
        component="PASSIVE_SECURITY",
        status="SUCCESS" if success else "FAILED_RETRYABLE",
        components_changed=components_changed,
        external_intelligence_refreshed=external_refreshed,
    )
    return {"PASSIVE_SECURITY": "SUCCESS" if success else "FAILED_RETRYABLE"}


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


def _required_pending(workspace: Any, audit_id: str) -> tuple[Any, ...]:
    return tuple(
        item
        for item in list_work_items(workspace, audit_id, pending_only=True)
        if bool(item.required)
    )


def _prepare_reprocess(workspace: Any, audit_id: str) -> ReprocessPreparation:
    """Retry pending dependencies and version evidence only after a material change."""
    try_append_operational_event(
        workspace,
        "AUDIT_REPROCESS_COLLECTION_PHASE_STARTED",
        audit_id=audit_id,
        reprocess_id=_current_reprocess_id(workspace, audit_id),
    )
    prior = latest_evidence_snapshot(workspace, audit_id)
    before_material = _material_state_fingerprint(workspace, audit_id)
    recovered: dict[str, str] = {}
    recovered.update(_recover_live_measurements(workspace, audit_id))
    optional_states, evaluated_optional = _recover_optional_collectors(workspace, audit_id)
    recovered.update(optional_states)
    recovered.update(_recover_impacted_deterministic(workspace, audit_id))
    states = _terminalized_states(_collection_states(workspace, audit_id))
    after_material = _material_state_fingerprint(workspace, audit_id)
    current_evidence = _current_evidence_ids(workspace, audit_id)
    material_changed = before_material != after_material
    evidence_changed = prior is None or current_evidence != tuple(prior.evidence_ids)
    if prior is not None and not material_changed and not evidence_changed:
        snapshot = prior
        stale = 0
    else:
        snapshot = seal_evidence(
            workspace=workspace,
            audit_id=audit_id,
            collection_states={},
            context={
                "material_state_fingerprint": after_material,
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
        recovered_collectors=recovered,
        material_state_changed=material_changed,
        evidence_ids_changed=evidence_changed,
    )
    return ReprocessPreparation(
        snapshot=snapshot,
        recovered=recovered,
        evaluated_optional=evaluated_optional,
        sealed_new_evidence=(
            prior is None or snapshot.evidence_snapshot_id != prior.evidence_snapshot_id
        ),
    )


def prepare_reprocess_evidence(workspace: Any, audit_id: str) -> Any:
    """Compatibility entrypoint returning the evidence snapshot prepared for RPR."""
    return _prepare_reprocess(workspace, audit_id).snapshot


@contextmanager
def _defer_mid_reprocess_projection() -> Iterator[tuple[Any, Any, Any]]:
    """Defer derived strategy/catalog projection until all RPR work is final."""
    from rasai import directed_analysis, report_completion

    data_finalizer = report_completion.finalize_audit_report_site
    directed_finalizer = directed_analysis.reprocess_directed_analysis
    catalog_finalizer = report_completion.materialize_catalog_report_projection

    def deferred(*args: Any, **kwargs: Any):
        del args, kwargs
        return None

    report_completion.finalize_audit_report_site = deferred
    directed_analysis.reprocess_directed_analysis = deferred
    report_completion.materialize_catalog_report_projection = deferred
    try:
        yield data_finalizer, directed_finalizer, catalog_finalizer
    finally:
        report_completion.finalize_audit_report_site = data_finalizer
        directed_analysis.reprocess_directed_analysis = directed_finalizer
        report_completion.materialize_catalog_report_projection = catalog_finalizer


@contextmanager
def _defer_reprocess_finish(
    module: Any,
    *,
    workspace: Any,
    audit_id: str,
    reprocess_id: str,
) -> Iterator[Any]:
    """Keep the RPR open until governed AI and final projections are complete."""
    current_start = module.start_reprocess_run
    current_finish = module.finish_reprocess_run

    def reuse_start(*args: Any, **kwargs: Any) -> str:
        del args, kwargs
        return reprocess_id

    def defer_finish(*args: Any, **kwargs: Any):
        del args, kwargs
        return recalculate(workspace, audit_id)

    module.start_reprocess_run = reuse_start
    module.finish_reprocess_run = defer_finish
    try:
        yield current_finish
    finally:
        module.start_reprocess_run = current_start
        module.finish_reprocess_run = current_finish


def _registered_ai_purposes(
    workspace: Any,
    audit_id: str,
    recovered: Mapping[str, str],
) -> frozenset[str]:
    """Return only registered AI purposes justified by this RPR dependency graph."""
    pending = _required_pending(workspace, audit_id)
    blockers = tuple(
        item
        for item in pending
        if str(item.component) != "IMPROVEMENT_INTELLIGENCE"
    )
    if blockers:
        # Registered/advisory AI is downstream of the primary required AI pipeline.
        # Running it while semantic/technical/content or collection work is unresolved
        # would spend provider quota on context that may still change.
        return frozenset()

    purposes: set[str] = set()
    if _pending_item(workspace, audit_id, "IMPROVEMENT_INTELLIGENCE") is not None:
        purposes.add("IMPROVEMENT_INTELLIGENCE")
    if str(recovered.get("SEARCH_INTELLIGENCE") or "").upper() == "SUCCESS":
        purposes.add("COMPETITIVE_INTELLIGENCE")
    return frozenset(purposes)


def _registered_ai_and_report(
    *,
    workspace: Any,
    audit_id: str,
    preparation: ReprocessPreparation,
    data_finalizer: Any,
    directed_finalizer: Any,
    catalog_finalizer: Any,
) -> None:
    """Finish AI/derived data first and materialize report-catalog exactly once."""
    from rasai import selective_optional_reprocess as optional

    snapshot = preparation.snapshot
    if snapshot is None:
        raise RuntimeError("RPR cannot run AI without a sealed evidence version")

    purposes = _registered_ai_purposes(workspace, audit_id, preparation.recovered)
    evaluated = set(preparation.evaluated_optional)
    outcomes: dict[str, Mapping[str, Any]] = {}
    non_ai_pending = tuple(
        item
        for item in _required_pending(workspace, audit_id)
        if str(item.component) not in _AI_COMPONENTS
    )
    if not non_ai_pending:
        if purposes:
            with optional._original_optional_environment(workspace, audit_id):
                outcomes = run_registered_ai_phase(
                    audit_id=audit_id,
                    workspace=workspace,
                    evidence_snapshot=snapshot,
                    purposes=purposes,
                )
            if "IMPROVEMENT_INTELLIGENCE" in purposes:
                evaluated.add("IMPROVEMENT_INTELLIGENCE")
        if not _required_pending(workspace, audit_id):
            mark_ai_sealed(
                audit_id=audit_id,
                workspace=workspace,
                evidence_snapshot=snapshot,
                outcomes=outcomes,
            )

    data_finalizer(audit_id=audit_id, workspace=workspace)
    if evaluated:
        optional._record_optional_attempts(workspace, audit_id, evaluated)

    summary = recalculate(workspace, audit_id)
    if str(summary.processing_status).upper() == "COMPLETE":
        directed_finalizer(audit_id=audit_id, workspace=workspace)
    catalog_finalizer(audit_id=audit_id, workspace=workspace)
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
            pending = _required_pending(workspace, audit_id)
            if not pending:
                # A complete AUD is a true no-op: no collector, provider or AI call is
                # justified merely because the operator requested reprocessing.
                return original(audit_id, audits_root=audits_root, source=source)

            prior_snapshot = latest_evidence_snapshot(workspace, audit_id)
            active_reprocess_id = _current_reprocess_id(workspace, audit_id)
            owns_reprocess = active_reprocess_id is None
            reprocess_id = active_reprocess_id or module.start_reprocess_run(
                workspace,
                audit_id,
                source=source,
                note="governed selective dependency recovery",
            )
            owned_finish = module.finish_reprocess_run

            # Pure AI retries reuse the exact sealed evidence version. A new seal is
            # created only when core evidence may have changed, no seal exists yet, or
            # a pending non-AI prerequisite is actually evaluated in this RPR.
            refresh_evidence = (
                prior_snapshot is None
                or active_reprocess_id is not None
                or any(str(item.component) not in _AI_COMPONENTS for item in pending)
            )
            preparation = (
                _prepare_reprocess(workspace, audit_id)
                if refresh_evidence
                else ReprocessPreparation(
                    snapshot=prior_snapshot,
                    recovered={},
                    evaluated_optional=frozenset(),
                    sealed_new_evidence=False,
                )
            )

            latest = module._latest_pending

            def ai_only_pending(active_workspace: Any, active_audit_id: str):
                return tuple(
                    item
                    for item in latest(active_workspace, active_audit_id)
                    if str(item.component) not in _LIVE_COMPONENTS
                    and str(item.component) not in _OPTIONAL_COLLECTORS
                    and str(item.component) not in _DERIVED_RECOVERY_COMPONENTS
                )

            module._latest_pending = ai_only_pending
            result = None
            try:
                with _defer_reprocess_finish(
                    module,
                    workspace=workspace,
                    audit_id=audit_id,
                    reprocess_id=reprocess_id,
                ) as final_finish:
                    with _defer_mid_reprocess_projection() as (
                        data_finalizer,
                        directed_finalizer,
                        catalog_finalizer,
                    ):
                        result = original(
                            audit_id,
                            audits_root=audits_root,
                            source=source,
                        )
                        _registered_ai_and_report(
                            workspace=workspace,
                            audit_id=audit_id,
                            preparation=preparation,
                            data_finalizer=data_finalizer,
                            directed_finalizer=directed_finalizer,
                            catalog_finalizer=catalog_finalizer,
                        )

                    summary = recalculate(workspace, audit_id)
                    live_or_derived = _LIVE_COMPONENTS | _DERIVED_RECOVERY_COMPONENTS
                    live_attempted = sum(
                        1 for name in preparation.recovered if name in live_or_derived
                    )
                    live_successful = sum(
                        1
                        for name, state in preparation.recovered.items()
                        if name in live_or_derived and str(state).upper() == SUCCESS
                    )
                    attempted = int(getattr(result, "attempted_items", 0) or 0) + live_attempted
                    successful = int(getattr(result, "successful_items", 0) or 0) + live_successful

                    if owns_reprocess:
                        summary = final_finish(
                            workspace,
                            reprocess_id,
                            status=(
                                SUCCESS
                                if str(summary.processing_status).upper() == "COMPLETE"
                                else FAILED_RETRYABLE
                            ),
                            attempted_items=attempted,
                            successful_items=successful,
                            note=(
                                "all configured requirements satisfied"
                                if str(summary.processing_status).upper() == "COMPLETE"
                                else "one or more configured requirements remain unresolved"
                            ),
                        )

                    try:
                        result = replace(
                            result,
                            reprocess_id=(
                                getattr(result, "reprocess_id", None) or reprocess_id
                            ),
                            processing_status=summary.processing_status,
                            score_status=summary.score_status,
                            report_status=summary.report_status,
                            consolidation_eligible=summary.consolidation_eligible,
                            attempted_items=attempted,
                            successful_items=successful,
                            remaining_items=summary.pending_items + summary.blocked_items,
                            temporal_expired_items=summary.expired_items,
                        )
                    except TypeError:
                        pass
                    return result
            except Exception:
                if owns_reprocess:
                    try:
                        summary = recalculate(workspace, audit_id)
                        owned_finish(
                            workspace,
                            reprocess_id,
                            status=FAILED_RETRYABLE,
                            attempted_items=int(getattr(result, "attempted_items", 0) or 0),
                            successful_items=int(getattr(result, "successful_items", 0) or 0),
                            note="governed selective reprocessing failed before final projection",
                        )
                    except Exception:
                        pass
                raise
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
