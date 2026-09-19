"""Point fixes discovered by the governed-pipeline human smoke.

The module is deliberately additive and idempotent.  It does not redesign report HTML
or provider policy.  It closes remaining ownership/binding gaps between the governed
collection/AI lifecycle and console/runtime adapters.
"""
from __future__ import annotations

from contextvars import ContextVar
from dataclasses import replace
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
from typing import Any, Mapping, Sequence

_INSTALLED = False
_EFFECTIVE_SEARCH_QUERIES: ContextVar[tuple[str, ...]] = ContextVar(
    "rasai_effective_search_queries", default=()
)


def _table_exists(connection: sqlite3.Connection, table: str) -> bool:
    return connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone() is not None


def _database(workspace: Any) -> Path:
    value = Path(workspace.database) if hasattr(workspace, "database") else Path(workspace)
    return value if value.name == "audit.db" else value / "audit.db"


def _saved_configuration(workspace: Any, audit_id: str) -> dict[str, Any]:
    database = _database(workspace)
    if not database.is_file():
        return {}
    connection = sqlite3.connect(database)
    try:
        if not _table_exists(connection, "audit_execution_configurations"):
            return {}
        row = connection.execute(
            "SELECT configuration_json FROM audit_execution_configurations WHERE audit_id=?",
            (audit_id,),
        ).fetchone()
    finally:
        connection.close()
    if not row or not row[0]:
        return {}
    try:
        value = json.loads(str(row[0]))
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return dict(value) if isinstance(value, dict) else {}


def _cat08_required(workspace: Any, audit_id: str) -> bool:
    payload = _saved_configuration(workspace, audit_id)
    catalog = payload.get("audit_catalog")
    if not isinstance(catalog, Mapping):
        return False
    selected = {str(value).upper() for value in (catalog.get("selected") or ())}
    if "CAT-08" not in selected:
        return False
    for raw in catalog.get("items") or ():
        if not isinstance(raw, Mapping):
            continue
        catalog_id = str(raw.get("id") or raw.get("catalog_id") or "").upper()
        if catalog_id != "CAT-08":
            continue
        return bool(raw.get("selected", True)) and str(raw.get("ai_mode") or "").upper() == "REQUIRED"
    return bool(catalog.get("ai_enabled"))


def _primary_ai_context(workspace: Any, audit_id: str) -> tuple[str, str, str] | None:
    database = _database(workspace)
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    try:
        if not _table_exists(connection, "ai_audit_sessions"):
            return None
        row = connection.execute(
            "SELECT * FROM ai_audit_sessions WHERE audit_id=?", (audit_id,)
        ).fetchone()
    finally:
        connection.close()
    if row is None:
        return None
    strategy = str(row["strategy"] or "").upper()
    if strategy == "AUTO":
        return ("auto", "", "")
    if strategy in {"NONE", ""}:
        return None
    provider = str(row["effective_provider"] or row["initial_provider"] or "").casefold()
    model = str(row["effective_model"] or row["initial_model"] or "")
    reasoning = str(
        row["effective_reasoning_profile"] or row["initial_reasoning_profile"] or ""
    ).upper()
    return (provider, model, reasoning) if provider else None


def _install_improvement_governed_hook() -> None:
    """Make CAT-08 execute inside the governed AI window and always enter fulfillment."""
    from rasai import ai_orchestration_unification as orchestration
    from rasai import audit_phase_runtime as phase
    from rasai import improvement_intelligence as improvement
    from rasai.audit_fulfillment import (
        FAILED_RETRYABLE,
        PENDING,
        REPLAY_SAFE,
        register_work_item,
        set_work_item_status,
    )

    hook = phase._AI_HOOKS.get("IMPROVEMENT_INTELLIGENCE")
    if hook is None:
        return
    current = hook.callback
    if bool(getattr(current, "_rasai_post_smoke_improvement", False)):
        return

    def governed(*, audit_id: str, workspace: Any, evidence_snapshot: Any):
        required = _cat08_required(workspace, audit_id)
        if required:
            payload = _saved_configuration(workspace, audit_id)
            settings = payload.get("settings") if isinstance(payload.get("settings"), Mapping) else {}
            feature = (
                settings.get("improvement_intelligence")
                if isinstance(settings, Mapping)
                and isinstance(settings.get("improvement_intelligence"), Mapping)
                else {}
            )
            register_work_item(
                workspace,
                audit_id=audit_id,
                component="IMPROVEMENT_INTELLIGENCE",
                required=True,
                temporal_mode=REPLAY_SAFE,
                status=PENDING,
                retryable=True,
                configuration={
                    "requested": True,
                    "required_by": "CAT-08",
                    "domains": str(feature.get("domains") or ""),
                    "max_recommendations": str(feature.get("max_recommendations") or ""),
                    "timeout_seconds": str(feature.get("timeout_seconds") or ""),
                },
            )

        context = _primary_ai_context(workspace, audit_id)
        token = orchestration._PRIMARY_AI_CONTEXT.set(context) if context is not None else None
        previous = os.environ.get(improvement.ENABLED_ENV)
        if required:
            os.environ[improvement.ENABLED_ENV] = "true"
        try:
            result = dict(
                current(
                    audit_id=audit_id,
                    workspace=workspace,
                    evidence_snapshot=evidence_snapshot,
                )
                or {}
            )
        finally:
            if token is not None:
                orchestration._PRIMARY_AI_CONTEXT.reset(token)
            if required:
                if previous is None:
                    os.environ.pop(improvement.ENABLED_ENV, None)
                else:
                    os.environ[improvement.ENABLED_ENV] = previous

        status = str(result.get("status") or "").upper()
        if required and status not in {"COMPLETE", "SUCCESS"}:
            set_work_item_status(
                workspace,
                audit_id=audit_id,
                component="IMPROVEMENT_INTELLIGENCE",
                status=FAILED_RETRYABLE,
                error_class="AI_ANALYSIS" if status not in {"SKIPPED", "NOT_CONFIGURED"} else "CONFIGURATION",
                error_code=str(result.get("reason") or status or "IMPROVEMENT_INCOMPLETE"),
                error_message=str(
                    result.get("reason")
                    or "CAT-08 obrigatório não concluiu a análise profunda governada"
                )[:1000],
                retryable=True,
            )
        return result

    governed._rasai_post_smoke_improvement = True
    governed._rasai_original = current
    phase.register_ai_hook("IMPROVEMENT_INTELLIGENCE", governed, order=hook.order)


def _project_improvement_console_state(state: Any) -> None:
    audit_id = str(getattr(state, "audit_id", "") or "").strip()
    if not audit_id:
        return
    root = Path(str(getattr(state, "audits_root", "audits") or "audits")) / audit_id
    database = root / "audit.db"
    if not database.is_file():
        return
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    try:
        if not _table_exists(connection, "audit_fulfillment_work_items"):
            return
        row = connection.execute(
            """SELECT status,last_error_message,last_error_code,effective_result_ref
               FROM audit_fulfillment_work_items
               WHERE audit_id=? AND component='IMPROVEMENT_INTELLIGENCE'
               ORDER BY updated_at DESC,rowid DESC LIMIT 1""",
            (audit_id,),
        ).fetchone()
    finally:
        connection.close()
    if row is None:
        return
    status = str(row["status"] or "").upper()
    state.improvement_last_status = "COMPLETE" if status == "SUCCESS" else "COMPLETE_WITH_LIMITATIONS"
    state.improvement_last_detail = str(row["last_error_message"] or row["last_error_code"] or "")
    report = root / "report" / "improvement-intelligence.html"
    state.improvement_last_report = str(report) if report.is_file() else ""


def _install_improvement_console_adapter() -> None:
    """Keep Improvement console UI/readiness aligned with the governed AI owner."""
    try:
        from rasai import console_entrypoint
        from rasai import improvement_intelligence_console as feature
    except ImportError:
        return

    current = feature.install
    if bool(getattr(current, "_rasai_post_smoke_governed_owner", False)):
        return

    def install(console_module: Any) -> None:
        before = console_module.run_audit_from_console
        current(console_module)

        def run(state: Any) -> int:
            code = int(before(state) or 0)
            _project_improvement_console_state(state)
            return code

        run._rasai_post_smoke_improvement_projection = True
        run._rasai_original = before
        console_module.run_audit_from_console = run

    install._rasai_post_smoke_governed_owner = True
    install._rasai_original = current
    feature.install = install
    console_entrypoint.install_improvement_intelligence_console = install


def _install_improvement_runtime_adapter() -> None:
    """Re-register the governed CAT-08 hook after its runtime installer runs."""
    try:
        from rasai import console_entrypoint
        from rasai import improvement_intelligence_runtime as runtime
    except ImportError:
        _install_improvement_governed_hook()
        return

    current = runtime.install
    if not bool(getattr(current, "_rasai_post_smoke_hook_refresh", False)):
        def install() -> None:
            current()
            _install_improvement_governed_hook()
        install._rasai_post_smoke_hook_refresh = True
        install._rasai_original = current
        runtime.install = install
        console_entrypoint.install_improvement_intelligence_runtime = install
    _install_improvement_governed_hook()


def _latest_common_crawl_dataset(workspace_root: str | Path) -> str:
    database = Path(workspace_root) / "observability.db"
    if not database.is_file():
        raise RuntimeError("COMMON_CRAWL_PRESEAL_DATASET_MISSING")
    connection = sqlite3.connect(database)
    try:
        if not _table_exists(connection, "datasets"):
            raise RuntimeError("COMMON_CRAWL_PRESEAL_DATASET_MISSING")
        row = connection.execute(
            """SELECT dataset_id FROM datasets
               WHERE source_type='COMMON_CRAWL_CDX_HISTORY'
               ORDER BY collected_at DESC,rowid DESC LIMIT 1"""
        ).fetchone()
    finally:
        connection.close()
    if row is None or not row[0]:
        raise RuntimeError("COMMON_CRAWL_PRESEAL_DATASET_MISSING")
    return str(row[0])


def _install_common_crawl_preseal() -> None:
    """Collect Common Crawl before evidence seal; scoring may only reuse persisted data."""
    from rasai import external_observability_runtime as external
    from rasai import external_sari
    from rasai.audit_phase_runtime import register_collection_hook
    from rasai.external_observability_policy import (
        COMMON_CRAWL_ENABLED_ENV,
        COMMON_CRAWL_INDEX_COUNT_ENV,
        COMMON_CRAWL_MAX_URLS_ENV,
        DEFAULT_COMMON_CRAWL_INDEX_COUNT,
        DEFAULT_COMMON_CRAWL_MAX_URLS,
        DEFAULT_EXTERNAL_TIMEOUT_SECONDS,
    )
    from rasai.standards_service_registry import service, service_state

    current = external.collect_configured_external_observability
    if bool(getattr(current, "_rasai_post_smoke_common_crawl", False)):
        return

    def collector(*, audit_id: str, workspace: Any, source_blocked: bool = False):
        del source_blocked
        effective = dict(os.environ)
        without_common = dict(effective)
        without_common[COMMON_CRAWL_ENABLED_ENV] = "false"
        outcomes = dict(
            current(
                audit_id=audit_id,
                workspace=workspace,
                env=without_common,
            )
            or {}
        )
        state_info = service_state(service("common-crawl"), effective)
        max_urls = external._non_negative_int(
            effective.get(COMMON_CRAWL_MAX_URLS_ENV), DEFAULT_COMMON_CRAWL_MAX_URLS
        )
        enabled = bool(state_info.get("effective_enabled")) and max_urls > 0
        if not enabled:
            common = external._base_result(
                state=str(state_info.get("state") or "DISABLED"),
                configured=bool(state_info.get("configured")),
                enabled=False,
                detail="Common Crawl não solicitado nesta AUD",
            )
        else:
            targets = external._audit_public_urls(workspace, audit_id, limit=max_urls)
            if not targets:
                common = external._base_result(
                    state="NO_DATA",
                    configured=bool(state_info.get("configured")),
                    enabled=True,
                    detail="Common Crawl sem URL pública elegível",
                )
            else:
                try:
                    dataset_id = external.collect_common_crawl_history(
                        audit_workspace=workspace.root,
                        targets=targets,
                        index_count=external._positive_int(
                            effective.get(COMMON_CRAWL_INDEX_COUNT_ENV),
                            DEFAULT_COMMON_CRAWL_INDEX_COUNT,
                        ),
                        timeout=external._positive_float(
                            effective.get("RASAI_STANDARDS_TIMEOUT_SECONDS"),
                            DEFAULT_EXTERNAL_TIMEOUT_SECONDS,
                        ),
                    )
                    common = external._base_result(
                        state="SUCCESS",
                        configured=True,
                        enabled=True,
                        detail=f"dataset={dataset_id}",
                    )
                    common["dataset_id"] = dataset_id
                except Exception as exc:
                    common = external._base_result(
                        state="ERROR",
                        configured=True,
                        enabled=True,
                        detail=f"{type(exc).__name__}: {str(exc)[:300]}",
                    )
        outcomes["common-crawl"] = common
        external._upsert_service_run(
            workspace=workspace,
            audit_id=audit_id,
            service_id="common-crawl",
            requested=bool(state_info.get("effective_enabled")),
            configured=bool(state_info.get("configured")),
            enabled=enabled,
            state=str(common.get("service_state") or "UNKNOWN"),
            attempted=1 if enabled else 0,
            succeeded=1 if str(common.get("service_state") or "").upper() == "SUCCESS" else 0,
            details=common,
        )
        from rasai.governed_optional_runtime import _aggregate
        return {"collection_state": _aggregate(outcomes), "services": outcomes}

    collector._rasai_post_smoke_common_crawl = True
    collector._rasai_original = current
    register_collection_hook("EXTERNAL_OBSERVABILITY", collector, order=50)

    # external_sari still owns deterministic BR-GEO-060 derivation before scoring.  It
    # must now resolve only the dataset collected above and never perform network I/O.
    def persisted_common_crawl(*, audit_workspace: Any, **_kwargs: Any) -> str:
        return _latest_common_crawl_dataset(audit_workspace)

    persisted_common_crawl._rasai_post_smoke_persisted_only = True
    external_sari.collect_common_crawl_history = persisted_common_crawl


def _install_effective_search_snapshot() -> None:
    """Persist the exact SERP terms sent to the child without duplicate execution."""
    try:
        from rasai import audit_configuration_reuse_console as reuse
        from rasai import console_entrypoint
        from rasai import console_governed_search_runtime as governed
    except ImportError:
        return

    current_settings = reuse._search_execution_settings
    if not bool(getattr(current_settings, "_rasai_effective_search_snapshot", False)):
        def search_settings(state: Any):
            value = current_settings(state)
            queries = _EFFECTIVE_SEARCH_QUERIES.get()
            if not queries or value is None:
                return value
            output = dict(value)
            output["enabled"] = True
            output["queries"] = list(queries)
            return output
        search_settings._rasai_effective_search_snapshot = True
        search_settings._rasai_original = current_settings
        reuse._search_execution_settings = search_settings

    def install(console_module: Any) -> None:
        if getattr(console_module, "_rasai_governed_search_runtime", False):
            return
        original_run = console_module.run_audit_from_console

        def run(state: Any) -> int:
            queries = tuple(getattr(state, "search_queries", ()) or ())
            if not queries:
                return int(original_run(state) or 0)
            from rasai import console_runtime
            original_build = console_runtime.build_command

            def governed_build(current: Any) -> list[str]:
                return governed._append_search_args(
                    list(original_build(current)), current, queries=queries
                )

            state.search_queries = ()
            console_runtime.build_command = governed_build
            token = _EFFECTIVE_SEARCH_QUERIES.set(queries)
            try:
                code = int(original_run(state) or 0)
            finally:
                _EFFECTIVE_SEARCH_QUERIES.reset(token)
                console_runtime.build_command = original_build
                state.search_queries = queries
            governed._project_result(state)
            return code

        run._rasai_governed_search = True
        run._rasai_original = original_run
        console_module.run_audit_from_console = run
        console_module._rasai_governed_search_runtime = True
        governed._INSTALLED = True

    install._rasai_effective_search_snapshot = True
    governed.install = install
    console_entrypoint.install_console_governed_search_runtime = install


def _record_dependency(
    *, workspace: Any, audit_id: str, purpose: str, extra_name: str, ready: bool
) -> None:
    from rasai.ai_dependency_contract import record_dependency_snapshot
    from rasai.audit_phase_runtime import require_sealed_evidence
    try:
        snapshot = require_sealed_evidence(audit_id=audit_id, workspace=workspace)
    except RuntimeError:
        snapshot = None
    sealed = snapshot is not None
    record_dependency_snapshot(
        workspace=workspace,
        audit_id=audit_id,
        purpose=purpose,
        expected=("EVIDENCE_SEALED", extra_name),
        present={
            "EVIDENCE_SEALED": "SUCCESS" if sealed else "PENDING",
            extra_name: "SUCCESS" if ready else "PENDING",
        },
        evidence_ids=getattr(snapshot, "evidence_ids", ()) if snapshot is not None else (),
        context_fingerprint_input={
            "evidence_snapshot_id": getattr(snapshot, "evidence_snapshot_id", None),
            "purpose": purpose,
        },
        ready=sealed and ready,
    )


def _backfill_semantic_task(workspace: Any, audit_id: str) -> None:
    from rasai.ai_governance import begin_round, complete_round, latest_evidence_snapshot, register_task
    snapshot = latest_evidence_snapshot(workspace, audit_id)
    if snapshot is None:
        return
    connection = sqlite3.connect(workspace.database)
    connection.row_factory = sqlite3.Row
    try:
        exists = connection.execute(
            "SELECT 1 FROM ai_tasks WHERE audit_id=? AND purpose='SEMANTIC_M7' LIMIT 1",
            (audit_id,),
        ).fetchone()
        if exists is not None or not _table_exists(connection, "semantic_assessments"):
            return
        rows = connection.execute(
            """SELECT sa.* FROM semantic_assessments sa
               JOIN page_snapshots ps ON ps.snapshot_id=sa.snapshot_id
               JOIN pages p ON p.page_id=ps.page_id
               WHERE p.audit_id=? ORDER BY sa.snapshot_id,sa.assessment_type""",
            (audit_id,),
        ).fetchall()
    finally:
        connection.close()
    groups: dict[str, list[sqlite3.Row]] = {}
    for row in rows:
        provider = str(row["provider"] or "").upper()
        if provider in {"", "NONE", "FALLBACK", "DETERMINISTIC"}:
            continue
        groups.setdefault(str(row["snapshot_id"]), []).append(row)
    for scope_key, items in groups.items():
        requirements = tuple(dict.fromkeys(str(row["assessment_type"]) for row in items))
        task_id = register_task(
            workspace=workspace,
            audit_id=audit_id,
            purpose="SEMANTIC_M7",
            scope_type="SNAPSHOT",
            scope_key=scope_key,
            evidence_snapshot_id=snapshot.evidence_snapshot_id,
            requirements=requirements,
            semantic_contract_version="M18-SEMANTIC-22-v1",
        )
        round_id = begin_round(
            workspace=workspace,
            ai_task_id=task_id,
            requested_requirements=requirements,
            input_payload={"snapshot_id": scope_key, "evidence_snapshot_id": snapshot.evidence_snapshot_id},
            input_summary={"persisted_assessments": len(items), "backfilled_from": "semantic_assessments"},
        )
        accepted = {
            str(row["assessment_type"]): {
                "result": row["result"],
                "confidence": row["confidence"],
                "provider": row["provider"],
                "model": row["model"],
                "evidence_ids": json.loads(str(row["evidence_ids"] or "[]")),
            }
            for row in items
        }
        complete_round(
            workspace=workspace,
            ai_round_id=round_id,
            accepted=accepted,
            rejected={},
            missing=(),
            output_payload={"source": "persisted-semantic-assessments", "count": len(items)},
        )


def _prepare_content_task(workspace: Any, audit_id: str) -> tuple[str, str, tuple[str, ...]]:
    """Create the M20 task and first round before any provider attempt."""
    from rasai import m20
    from rasai.ai_governance import begin_round, latest_evidence_snapshot, register_task

    snapshot = latest_evidence_snapshot(workspace, audit_id)
    if snapshot is None:
        raise RuntimeError("CONTENT_REMEDIATION_REQUIRES_SEALED_EVIDENCE")
    requests = m20._load_requests(audit_id=audit_id, workspace=workspace)
    requirements = tuple(
        dict.fromkeys(
            f"FINDING:{finding.finding_id}"
            for request in requests
            for finding in request.findings
            if finding.finding_id
        )
    ) or ("CONTENT_REMEDIATION_RESULT",)
    task_id = register_task(
        workspace=workspace,
        audit_id=audit_id,
        purpose="CONTENT_REMEDIATION",
        scope_type="AUDIT",
        scope_key="AUDIT",
        evidence_snapshot_id=snapshot.evidence_snapshot_id,
        requirements=requirements,
        semantic_contract_version="M20-CONTENT-REMEDIATION-v3",
    )
    round_id = begin_round(
        workspace=workspace,
        ai_task_id=task_id,
        requested_requirements=requirements,
        input_payload={
            "evidence_snapshot_id": snapshot.evidence_snapshot_id,
            "request_contexts": len(requests),
            "finding_count": sum(len(request.findings) for request in requests),
        },
        input_summary={
            "request_contexts": len(requests),
            "eligible_findings": sum(len(request.findings) for request in requests),
        },
    )
    return task_id, round_id, requirements


def _complete_content_task(
    workspace: Any,
    round_id: str,
    requirements: Sequence[str],
    result: Any,
    *,
    failed: bool = False,
) -> None:
    from rasai.ai_governance import complete_round

    status = str(getattr(result, "status", "") or "").upper()
    success = not failed and status == "SUCCESS"
    complete_round(
        workspace=workspace,
        ai_round_id=round_id,
        accepted=(
            {requirement: {"status": "SUCCESS"} for requirement in requirements}
            if success
            else {}
        ),
        rejected={},
        missing=() if success else requirements,
        output_payload={
            "status": status or ("FAILED" if failed else "UNKNOWN"),
            "generated_suggestions": len(getattr(result, "suggestion_ids", ()) or ()),
            "attempted_contexts": int(getattr(result, "attempted_contexts", 0) or 0),
        },
        failed=not success,
    )


def _backfill_content_task(workspace: Any, audit_id: str) -> None:
    from rasai.ai_governance import begin_round, complete_round, latest_evidence_snapshot, register_task
    snapshot = latest_evidence_snapshot(workspace, audit_id)
    if snapshot is None:
        return
    connection = sqlite3.connect(workspace.database)
    connection.row_factory = sqlite3.Row
    try:
        exists = connection.execute(
            "SELECT 1 FROM ai_tasks WHERE audit_id=? AND purpose='CONTENT_REMEDIATION' LIMIT 1",
            (audit_id,),
        ).fetchone()
        if exists is not None or not _table_exists(connection, "content_remediation_runs"):
            return
        run = connection.execute(
            "SELECT * FROM content_remediation_runs WHERE audit_id=?", (audit_id,)
        ).fetchone()
        attempts = (
            connection.execute(
                "SELECT * FROM content_remediation_attempts WHERE audit_id=? ORDER BY started_at",
                (audit_id,),
            ).fetchall()
            if _table_exists(connection, "content_remediation_attempts")
            else []
        )
        suggestions = (
            connection.execute(
                "SELECT finding_id,suggestion_id FROM content_remediation_suggestions WHERE audit_id=?",
                (audit_id,),
            ).fetchall()
            if _table_exists(connection, "content_remediation_suggestions")
            else []
        )
    finally:
        connection.close()
    if run is None or not attempts:
        return
    requirements = tuple(
        dict.fromkeys(f"FINDING:{row['finding_id']}" for row in suggestions if row["finding_id"])
    ) or ("CONTENT_REMEDIATION_RESULT",)
    task_id = register_task(
        workspace=workspace,
        audit_id=audit_id,
        purpose="CONTENT_REMEDIATION",
        scope_type="AUDIT",
        scope_key="AUDIT",
        evidence_snapshot_id=snapshot.evidence_snapshot_id,
        requirements=requirements,
        semantic_contract_version="M20-CONTENT-REMEDIATION-v3",
    )
    round_id = begin_round(
        workspace=workspace,
        ai_task_id=task_id,
        requested_requirements=requirements,
        input_payload={"evidence_snapshot_id": snapshot.evidence_snapshot_id},
        input_summary={"attempts": len(attempts), "eligible_findings": int(run["eligible_findings"] or 0)},
    )
    success = str(run["status"] or "").upper() == "SUCCESS"
    accepted = (
        {requirement: {"status": "SUCCESS"} for requirement in requirements}
        if success else {}
    )
    complete_round(
        workspace=workspace,
        ai_round_id=round_id,
        accepted=accepted,
        rejected={},
        missing=() if success else requirements,
        output_payload={
            "status": run["status"],
            "generated_suggestions": int(run["generated_suggestions"] or 0),
            "attempts": len(attempts),
        },
        failed=not success,
    )


def _install_ai_governance_completion() -> None:
    """Ensure semantic/content AI expose dependency + task/round provenance."""
    from rasai import audit_runner
    from rasai.m18_persistence import attempt_governance
    from rasai.semantic_partial_runtime import governed_execution_context

    # Preserve every already-installed audit_runner wrapper (progress, corpus,
    # fulfillment and recovery). The governed semantic context makes the canonical
    # _safe_provider_call task/round-aware without replacing that wrapper chain.
    current_m7 = audit_runner.execute_m7
    if not bool(getattr(current_m7, "_rasai_post_smoke_governance", False)):
        def execute_m7(*args: Any, **kwargs: Any):
            audit_id = str(kwargs.get("audit_id") or "")
            workspace = kwargs.get("workspace")
            if audit_id and workspace is not None:
                _record_dependency(
                    workspace=workspace,
                    audit_id=audit_id,
                    purpose="SEMANTIC_AI",
                    extra_name="SEMANTIC_EVIDENCE_CONTEXT",
                    ready=True,
                )
            if audit_id and workspace is not None:
                with governed_execution_context(audit_id=audit_id, workspace=workspace):
                    result = current_m7(*args, **kwargs)
            else:
                result = current_m7(*args, **kwargs)
            if audit_id and workspace is not None:
                _backfill_semantic_task(workspace, audit_id)
            return result
        execute_m7._rasai_post_smoke_governance = True
        execute_m7._rasai_original = current_m7
        audit_runner.execute_m7 = execute_m7

    current_m20 = audit_runner.execute_m20
    if not bool(getattr(current_m20, "_rasai_post_smoke_governance", False)):
        def execute_m20(*args: Any, **kwargs: Any):
            audit_id = str(kwargs.get("audit_id") or "")
            workspace = kwargs.get("workspace")
            enabled = bool(kwargs.get("enabled"))
            if not (audit_id and workspace is not None and enabled):
                return current_m20(*args, **kwargs)

            _record_dependency(
                workspace=workspace,
                audit_id=audit_id,
                purpose="CONTENT_REMEDIATION",
                extra_name="CONTENT_FINDINGS_CONTEXT",
                ready=True,
            )
            task_id, round_id, requirements = _prepare_content_task(workspace, audit_id)
            try:
                with attempt_governance(
                    operation="CONTENT_REMEDIATION",
                    ai_task_id=task_id,
                    ai_round_id=round_id,
                ):
                    result = current_m20(*args, **kwargs)
            except Exception:
                _complete_content_task(
                    workspace,
                    round_id,
                    requirements,
                    None,
                    failed=True,
                )
                raise
            _complete_content_task(
                workspace,
                round_id,
                requirements,
                result,
            )
            return result
        execute_m20._rasai_post_smoke_governance = True
        execute_m20._rasai_original = current_m20
        audit_runner.execute_m20 = execute_m20


def _sidecar_source_counts(database: Any) -> dict[str, int]:
    result: dict[str, int] = {}
    sidecar = Path(database).parent / "observability.db"
    if not sidecar.is_file():
        return result
    connection = sqlite3.connect(sidecar)
    connection.row_factory = sqlite3.Row
    try:
        if not _table_exists(connection, "datasets"):
            return result
        datasets = [dict(row) for row in connection.execute("SELECT * FROM datasets")]
        for dataset in datasets:
            source = str(dataset.get("source_type") or "")
            dataset_id = str(dataset.get("dataset_id") or "")
            table = (
                "crux_history" if source == "CHROME_UX_REPORT_HISTORY"
                else "web_archive_observations" if source == "COMMON_CRAWL_CDX_HISTORY"
                else "behavioral_observations" if source == "MICROSOFT_CLARITY_LIVE_INSIGHTS"
                else "search_performance" if source.startswith("GOOGLE_SEARCH_CONSOLE_")
                else None
            )
            count = 0
            if table and _table_exists(connection, table):
                columns = {str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})")}
                if "dataset_id" in columns:
                    row = connection.execute(
                        f"SELECT COUNT(*) FROM {table} WHERE dataset_id=?", (dataset_id,)
                    ).fetchone()
                    count = int(row[0] or 0) if row else 0
            result[source] = result.get(source, 0) + max(count, 1 if dataset_id else 0)
    finally:
        connection.close()
    return result


def _standards_summary(database: Path, data: Any) -> str:
    """Existing CAT-01 standards table with MDN source score exposed when persisted."""
    from rasai import catalog_report_evidence as e
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    try:
        metrics = e._audit_rows(connection, "standards_metric_observations", data.audit_id)
        services = e._audit_rows(connection, "standards_service_runs", data.audit_id)
    finally:
        connection.close()
    wanted = {
        "w3c_html_conformance": "Conformidade HTML W3C",
        "w3c_css_conformance": "Conformidade CSS W3C",
        "mdn_http_observatory": "MDN HTTP Observatory",
        "web_platform_widely_available_count": "Recursos amplamente disponíveis",
        "web_platform_newly_available_count": "Recursos recentemente disponíveis",
        "web_platform_limited_availability_count": "Recursos com disponibilidade limitada",
    }
    rows: list[Sequence[Any]] = []
    modals: list[str] = []
    for index, item in enumerate(metrics, 1):
        key = str(item.get("metric_id") or item.get("metric_key") or "")
        if key not in wanted:
            continue
        raw = item.get("value")
        if raw is None:
            value: Any = "—"
        elif key == "mdn_http_observatory":
            details = json.loads(str(item.get("details_json") or "{}"))
            grade = details.get("grade") if isinstance(details, Mapping) else None
            value = f"{float(raw):.0f}" + (f" · {grade}" if grade else "")
        elif str(item.get("unit") or "") == "error_count":
            value = f"{int(float(raw))} erro(s)"
        else:
            number = float(raw)
            value = int(number) if number.is_integer() else round(number, 3)
        detail: Any = "-"
        if key in {"w3c_html_conformance", "w3c_css_conformance"}:
            from rasai.execution_consistency_runtime import _w3c_detail_modal
            detail, modal = _w3c_detail_modal(e, item, index=index)
            detail = e._Html(
                str(detail)
                + " · <a href='cat-09.html#w3c-remediation'>Ver remediações no CAT-09</a>"
            )
            modals.append(modal)
        rows.append((wanted[key], value, e._status_label(item.get("state") or item.get("status")), detail))
    for item in services:
        service_id = str(item.get("service_id") or "")
        if service_id not in {"w3c-validator", "mdn-observatory", "w3c-css-validator", "web-platform-baseline"}:
            continue
        result = f"{item.get('targets_succeeded', 0)}/{item.get('targets_attempted', 0)} alvo(s)"
        rows.append((e._friendly_service(service_id) + " · execução", result, e._status_label(item.get("state")), "-"))
    return e._table(
        ("Verificação", "Resultado", "Estado", "Detalhe"),
        rows,
        empty="Nenhuma métrica de padrões web foi persistida.",
        sortable=bool(rows),
    ) + "".join(modals)


def _align_report_bindings() -> None:
    """Align all catalog surfaces to one functional status/source projection."""
    from rasai import catalog_report_evidence as evidence
    from rasai import catalog_report_governance as governance
    from rasai import catalog_report_page as page
    from rasai import catalog_report_search_trust as search_trust
    from rasai import catalog_state_trust as state_trust

    current_status = page._catalog_status
    if not bool(getattr(current_status, "_rasai_post_smoke_status", False)):
        def status(database: Any, data: Any, catalog_id: str):
            value, tone, detail = current_status(database, data, catalog_id)
            if catalog_id == "CAT-04" and catalog_id in data.selected:
                available = int(state_trust._web_result_count(database, data.audit_id) or 0)
                if available > 0 and str(value).upper() in {
                    "FALHA", "ERRO", "SEM RESULTADO", "INDISPONÍVEL"
                }:
                    return (
                        "PARCIAL",
                        "warn",
                        "PageSpeed/CrUX atual possui falha reprocessável ou ausência de dados, mas há evidência válida de performance em CrUX History e/ou métricas da sessão do navegador.",
                    )
            return value, tone, detail
        status._rasai_post_smoke_status = True
        status._rasai_original = current_status
        page._catalog_status = status
    else:
        status = current_status

    current_sources = page._catalog_sources
    if not bool(getattr(current_sources, "_rasai_post_smoke_sources", False)):
        def sources(database: Any, data: Any, catalog_id: str):
            rows = list(current_sources(database, data, catalog_id))
            names = {str(row[0]) for row in rows}
            if catalog_id == "CAT-02" and state_trust._accessibility_count(database, data.audit_id) == 0:
                rows = [row for row in rows if str(row[0]) != "web_performance_observations"]
                names = {str(row[0]) for row in rows}
            connection = sqlite3.connect(database)
            try:
                if catalog_id == "CAT-04" and _table_exists(connection, "standards_metric_observations"):
                    count = connection.execute(
                        """SELECT COUNT(*) FROM standards_metric_observations
                           WHERE audit_id=? AND source='OPEN-WEB-METRICS-001' AND value IS NOT NULL""",
                        (data.audit_id,),
                    ).fetchone()[0]
                    if count and "standards_metric_observations (open-web)" not in names:
                        rows.append(("standards_metric_observations (open-web)", "Métricas da sessão do navegador", int(count)))
                if catalog_id == "CAT-05" and _table_exists(connection, "serp_observations"):
                    count = connection.execute(
                        "SELECT COUNT(*) FROM serp_observations WHERE audit_id=?", (data.audit_id,)
                    ).fetchone()[0]
                    if count and "serp_observations" not in names:
                        rows.append(("serp_observations", "Observações SERP da AUD", int(count)))
            finally:
                connection.close()
            sidecar = _sidecar_source_counts(database)
            if catalog_id in {"CAT-04", "CAT-05"}:
                crux = sidecar.get("CHROME_UX_REPORT_HISTORY", 0)
                if crux and "observability.crux_history" not in names:
                    rows.append(("observability.crux_history", "Série histórica CrUX", crux))
            if catalog_id == "CAT-05":
                common = sidecar.get("COMMON_CRAWL_CDX_HISTORY", 0)
                clarity = sidecar.get("MICROSOFT_CLARITY_LIVE_INSIGHTS", 0)
                gsc = sum(value for key, value in sidecar.items() if key.startswith("GOOGLE_SEARCH_CONSOLE_"))
                for name, label, count in (
                    ("observability.common_crawl", "Histórico Common Crawl", common),
                    ("observability.clarity", "Microsoft Clarity", clarity),
                    ("observability.gsc", "Google Search Console", gsc),
                ):
                    if count and name not in names:
                        rows.append((name, label, count))
            return rows
        sources._rasai_post_smoke_sources = True
        sources._rasai_original = current_sources
        page._catalog_sources = sources
    else:
        sources = current_sources

    current_states = search_trust._source_states
    if not bool(getattr(current_states, "_rasai_post_smoke_gsc", False)):
        def source_states(database: Path, data: Any):
            values = list(current_states(database, data))
            connection = sqlite3.connect(database)
            connection.row_factory = sqlite3.Row
            try:
                runs = []
                if _table_exists(connection, "standards_service_runs"):
                    runs = [
                        dict(row)
                        for row in connection.execute(
                            "SELECT * FROM standards_service_runs WHERE audit_id=? AND service_id='google-search-console'",
                            (data.audit_id,),
                        ).fetchall()
                    ]
            finally:
                connection.close()
            if runs and not any(bool(row.get("requested")) for row in runs):
                for index, item in enumerate(values):
                    if str(item.source_id).upper() != "GOOGLE_SEARCH_CONSOLE":
                        continue
                    values[index] = replace(
                        item,
                        requested=False,
                        enabled=False,
                        executed=False,
                        execution_status="NOT_REQUESTED",
                        data_available=False,
                        data_status="NO_DATA",
                        freshness_mode="NOT_APPLICABLE",
                        captured_at=None,
                        source_audit_id=None,
                        error_count=0,
                        result_count=0,
                        detail="GSC configurado, porém desabilitado/não solicitado nesta AUD",
                    ).validate()
            return tuple(values)
        source_states._rasai_post_smoke_gsc = True
        source_states._rasai_original = current_states
        search_trust._source_states = source_states

    evidence._standards_summary = _standards_summary
    page._standards_summary = _standards_summary
    governance._catalog_status = page._catalog_status
    governance._catalog_sources = page._catalog_sources

    site = sys.modules.get("rasai.catalog_report_site")
    if site is not None:
        site._catalog_status = page._catalog_status
        site._catalog_sources = page._catalog_sources
        site._standards_summary = _standards_summary


def _install_report_alignment() -> None:
    from rasai import catalog_projection_consistency as projection
    from rasai import catalog_report_governance as governance

    current_sync = projection._sync_site_bindings
    if not bool(getattr(current_sync, "_rasai_post_smoke_alignment", False)):
        def sync() -> None:
            current_sync()
            _align_report_bindings()
        sync._rasai_post_smoke_alignment = True
        sync._rasai_original = current_sync
        projection._sync_site_bindings = sync

    current_sari = governance._sari_body
    if not bool(getattr(current_sari, "_rasai_post_smoke_preliminary", False)):
        def sari(data: Any) -> str:
            html = current_sari(data)
            fulfillment = data.fulfillment if isinstance(getattr(data, "fulfillment", None), Mapping) else {}
            final = str(fulfillment.get("score_status") or "").upper() == "FINAL" and bool(
                fulfillment.get("consolidation_eligible")
            )
            if not final:
                html = html.replace("<small>Cobertura ", "<small>PRELIMINAR · Cobertura ")
            return html
        sari._rasai_post_smoke_preliminary = True
        sari._rasai_original = current_sari
        governance._sari_body = sari
        site = sys.modules.get("rasai.catalog_report_site")
        if site is not None:
            site._sari_body = sari
    _align_report_bindings()


def _install_request_remediation_dedup() -> None:
    """Suppress derived console symptoms already represented by a CORS cause."""
    from rasai import request_remediation_intelligence as request
    current = request.collect_request_error_evidence
    if bool(getattr(current, "_rasai_post_smoke_cause_dedup", False)):
        return

    def collect(database: Any, audit_id: str, *, sources: set[str] | None = None):
        events, universe = current(database, audit_id, sources=sources)
        cors: set[tuple[str, str]] = set()
        for item in events:
            if str(item.get("family") or "").upper() != "CORS":
                continue
            sample = str(item.get("sample_key") or "")
            resource = str(item.get("normalized_url") or "")
            if sample and resource:
                cors.add((sample, resource))
        output = []
        for item in events:
            if str(item.get("family") or "").upper() == "CONSOLE_RUNTIME":
                key = (str(item.get("sample_key") or ""), str(item.get("normalized_url") or ""))
                message = str(item.get("message") or "").casefold()
                if key in cors and ("failed to load resource" in message or "err_failed" in message):
                    continue
            output.append(item)
        return output, universe

    collect._rasai_post_smoke_cause_dedup = True
    collect._rasai_original = current
    request.collect_request_error_evidence = collect


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    _install_common_crawl_preseal()
    _install_improvement_runtime_adapter()
    _install_improvement_console_adapter()
    _install_effective_search_snapshot()
    _install_ai_governance_completion()
    _install_report_alignment()
    _install_request_remediation_dedup()
    _INSTALLED = True


__all__ = ["install"]
