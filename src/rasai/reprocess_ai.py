"""Selective replay-safe AI recovery for an existing logical AUD."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sqlite3
from typing import Any

from rasai.audit_fulfillment import WorkItem, archive_rows
from rasai.domain import DeviceContext, EvidenceType, RuleResult, Severity, new_id, utc_now
from rasai.evidence import EvidenceManager
from rasai.persistence import AuditPersistence, AuditWorkspace


def _load(value: Any, default: Any) -> Any:
    if value in (None, ""):
        return default
    if isinstance(value, (dict, list, tuple)):
        return value
    try:
        return json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return default


def _contract_configuration(workspace: AuditWorkspace, audit_id: str) -> dict[str, Any]:
    connection = sqlite3.connect(workspace.database)
    try:
        row = connection.execute(
            "SELECT configuration FROM audit_fulfillment_contracts WHERE audit_id=?", (audit_id,)
        ).fetchone()
    except sqlite3.OperationalError:
        row = None
    finally:
        connection.close()
    value = _load(row[0], {}) if row else {}
    return dict(value) if isinstance(value, dict) else {}


def build_reprocess_provider(workspace: AuditWorkspace, audit_id: str, item: WorkItem | None = None):
    """Build the RPR provider without mutating the original AUD configuration.

    An explicit execution-local RPR policy wins. Without one, legacy/direct callers
    keep the original behavior of reconstructing the provider from AUD provenance.
    """
    from rasai.provider_registry import get_provider_registration
    from rasai.provider_runtime_policy import build_semantic_provider, provider_reasoning_env
    from rasai.reprocess_policy import current_policy, provider_override

    policy = current_policy()
    override_provider, override_model, override_reasoning = provider_override()
    if policy.use_ai is True:
        selection = str(override_provider or "none").strip().casefold()
        environment = dict(os.environ)
        registration = get_provider_registration(selection)
        if registration is not None and override_reasoning:
            reasoning_env = provider_reasoning_env(registration.provider_name)
            if reasoning_env:
                environment[reasoning_env] = override_reasoning
        return build_semantic_provider(
            selection,
            model_override=(
                override_model if selection not in {"none", "auto", ""} else None
            ),
            env=environment,
        )

    contract = _contract_configuration(workspace, audit_id)
    selection = str(contract.get("semantic_provider") or "").strip()
    if not selection and item is not None:
        selection = str(item.configuration.get("provider") or "").strip()
    model: str | None = None
    connection = sqlite3.connect(workspace.database)
    connection.row_factory = sqlite3.Row
    try:
        table = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='ai_provider_attempts'"
        ).fetchone()
        if table:
            params: list[Any] = [audit_id]
            sql = "SELECT provider,model FROM ai_provider_attempts WHERE audit_id=?"
            if item is not None and item.scope_key not in {"AUDIT", ""}:
                sql += " AND snapshot_id=?"
                params.append(item.scope_key)
            sql += " ORDER BY finished_at DESC,rowid DESC LIMIT 1"
            row = connection.execute(sql, tuple(params)).fetchone()
            if row is not None:
                if not selection:
                    selection = str(row["provider"] or "")
                model = str(row["model"] or "").strip() or None
    except sqlite3.OperationalError:
        pass
    finally:
        connection.close()
    if not selection or selection.upper() == "NONE":
        raise ValueError("original audit did not persist an eligible AI provider selection")
    if selection.upper() == "AUTO":
        model = None
    return build_semantic_provider(selection, model_override=model)


def _archive_query(
    workspace: AuditWorkspace,
    *,
    audit_id: str,
    reprocess_id: str,
    component: str,
    entity_type: str,
    id_field: str,
    sql: str,
    params: tuple[Any, ...],
) -> tuple[dict[str, Any], ...]:
    connection = sqlite3.connect(workspace.database)
    connection.row_factory = sqlite3.Row
    try:
        rows = tuple(dict(row) for row in connection.execute(sql, params).fetchall())
    finally:
        connection.close()
    if rows:
        archive_rows(
            workspace,audit_id=audit_id,reprocess_id=reprocess_id,component=component,
            entity_type=entity_type,id_field=id_field,rows=rows,
        )
    return rows


def _semantic_ready(workspace: AuditWorkspace, snapshot_id: str) -> bool:
    connection = sqlite3.connect(workspace.database)
    try:
        row = connection.execute(
            "SELECT main_content_ref FROM page_snapshots WHERE snapshot_id=?", (snapshot_id,)
        ).fetchone()
    finally:
        connection.close()
    if row is None or not row[0]:
        return False
    path = workspace.root / str(row[0])
    return path.is_file() and bool(path.read_text(encoding="utf-8", errors="replace").strip())


def _clear_semantic_snapshot(
    workspace: AuditWorkspace,
    *,
    audit_id: str,
    snapshot_id: str,
    reprocess_id: str,
) -> None:
    semantic_rules = tuple(f"BR-GEO-{number:03d}" for number in range(28, 50))
    placeholders = ",".join("?" for _ in semantic_rules)
    executions = _archive_query(
        workspace,audit_id=audit_id,reprocess_id=reprocess_id,component="SEMANTIC_AI",
        entity_type="rule_execution",id_field="rule_execution_id",
        sql=f"SELECT * FROM rule_executions WHERE audit_id=? AND snapshot_id=? AND rule_id IN ({placeholders})",
        params=(audit_id,snapshot_id,*semantic_rules),
    )
    execution_ids = tuple(str(row["rule_execution_id"]) for row in executions)
    if execution_ids:
        marks = ",".join("?" for _ in execution_ids)
        _archive_query(
            workspace,audit_id=audit_id,reprocess_id=reprocess_id,component="SEMANTIC_AI",
            entity_type="finding",id_field="finding_id",
            sql=f"SELECT * FROM findings WHERE audit_id=? AND rule_execution_id IN ({marks})",
            params=(audit_id,*execution_ids),
        )
    _archive_query(
        workspace,audit_id=audit_id,reprocess_id=reprocess_id,component="SEMANTIC_AI",
        entity_type="semantic_assessment",id_field="assessment_id",
        sql="SELECT * FROM semantic_assessments WHERE snapshot_id=?",
        params=(snapshot_id,),
    )
    _archive_query(
        workspace,audit_id=audit_id,reprocess_id=reprocess_id,component="SEMANTIC_AI",
        entity_type="entity_observation",id_field="entity_observation_id",
        sql="SELECT * FROM entity_observations WHERE snapshot_id=?",
        params=(snapshot_id,),
    )
    connection = sqlite3.connect(workspace.database)
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        with connection:
            if execution_ids:
                marks = ",".join("?" for _ in execution_ids)
                connection.execute(f"DELETE FROM findings WHERE rule_execution_id IN ({marks})", execution_ids)
                connection.execute(f"DELETE FROM rule_executions WHERE rule_execution_id IN ({marks})", execution_ids)
            try:
                connection.execute("DELETE FROM semantic_assessments WHERE snapshot_id=?", (snapshot_id,))
                connection.execute("DELETE FROM entity_observations WHERE snapshot_id=?", (snapshot_id,))
            except sqlite3.OperationalError:
                pass
    finally:
        connection.close()


def _m7_inputs(workspace: AuditWorkspace, audit_id: str, snapshot_id: str):
    from rasai.domain import ArchitectureClassification
    from rasai.m3 import M3ExecutionResult
    from rasai.m4 import M4ExecutionResult
    from rasai.m5 import M5ExecutionResult
    from rasai.m6 import M6ExecutionResult

    connection = sqlite3.connect(workspace.database)
    connection.row_factory = sqlite3.Row
    try:
        snapshot = connection.execute(
            """SELECT ps.*,p.audit_id FROM page_snapshots ps
               JOIN pages p ON p.page_id=ps.page_id WHERE ps.snapshot_id=?""",
            (snapshot_id,),
        ).fetchone()
        if snapshot is None or str(snapshot["audit_id"]) != audit_id:
            raise ValueError(f"snapshot does not belong to audit: {snapshot_id}")
        page_id = str(snapshot["page_id"])
        device = DeviceContext(str(snapshot["device"]))
        evidence_ids = tuple(
            str(row[0]) for row in connection.execute(
                """SELECT evidence_id FROM evidence
                   WHERE audit_id=? AND snapshot_id=? AND source IN ('RENDERED_DOM','RAW_HTML_FALLBACK')
                   ORDER BY captured_at,evidence_id""",
                (audit_id,snapshot_id),
            ).fetchall()
        )
        m5_ids = tuple(
            str(row[0]) for row in connection.execute(
                """SELECT rule_execution_id FROM rule_executions
                   WHERE audit_id=? AND page_id=? AND rule_id='BR-GEO-009' ORDER BY executed_at,rowid""",
                (audit_id,page_id),
            ).fetchall()
        )
        m6_ids = tuple(
            str(row[0]) for row in connection.execute(
                """SELECT rule_execution_id FROM rule_executions
                   WHERE audit_id=? AND snapshot_id=? AND rule_id='BR-GEO-020' ORDER BY executed_at,rowid""",
                (audit_id,snapshot_id),
            ).fetchall()
        )
    finally:
        connection.close()
    architecture = ArchitectureClassification(str(snapshot["architecture_classification"]))
    return (
        M3ExecutionResult(snapshot_ids={page_id:{device:snapshot_id}},failures=()),
        M4ExecutionResult(evidence_ids={snapshot_id:evidence_ids},failures=()),
        M5ExecutionResult(rule_execution_ids=m5_ids,finding_ids=(),registry_rule_ids=()),
        M6ExecutionResult(rule_execution_ids=m6_ids,finding_ids=(),architecture_by_snapshot={snapshot_id:architecture}),
    )


def recover_semantic_item(
    *,
    workspace: AuditWorkspace,
    audit_id: str,
    item: WorkItem,
    reprocess_id: str,
    provider: Any | None = None,
) -> tuple[bool, Any]:
    """Replace only one pending semantic snapshot and preserve its prior version."""
    from rasai.m7 import execute_m7
    from rasai.m18_persistence import persist_provider_runtime
    from rasai.semantic import ProviderState

    snapshot_id = item.scope_key
    if snapshot_id == "AUDIT" or not _semantic_ready(workspace,snapshot_id):
        return False, provider
    active_provider = provider or build_reprocess_provider(workspace,audit_id,item)
    _clear_semantic_snapshot(workspace,audit_id=audit_id,snapshot_id=snapshot_id,reprocess_id=reprocess_id)
    m3,m4,m5,m6 = _m7_inputs(workspace,audit_id,snapshot_id)
    with AuditPersistence(workspace) as persistence:
        result = execute_m7(
            audit_id=audit_id,m3_result=m3,m4_result=m4,m5_result=m5,m6_result=m6,
            persistence=persistence,workspace=workspace,provider=active_provider,
        )
    persist_provider_runtime(
        audit_id=audit_id,provider=active_provider,workspace=workspace,audit_mode=result.audit_mode.value,
    )
    state = result.provider_states.get(snapshot_id)
    return state is ProviderState.AVAILABLE, active_provider


def _successful_m20_snapshots(workspace: AuditWorkspace, audit_id: str) -> frozenset[str]:
    connection = sqlite3.connect(workspace.database)
    try:
        rows = connection.execute(
            """SELECT DISTINCT snapshot_id FROM content_remediation_attempts
               WHERE audit_id=? AND status='SUCCESS'""", (audit_id,)
        ).fetchall()
        return frozenset(str(row[0]) for row in rows if row[0])
    except sqlite3.OperationalError:
        return frozenset()
    finally:
        connection.close()


class _SkipSuccessfulM20Router:
    def __init__(self, base: Any, successful: frozenset[str]) -> None:
        self.base = base
        self.successful = successful
        self.providers = getattr(base,"providers",())
        self.strategy = getattr(base,"strategy","UNKNOWN")

    def analyze(self, request: Any):
        from rasai.m20_ai import ContentRemediationResult, ProviderState
        if str(getattr(request,"snapshot_id","")) in self.successful:
            return ContentRemediationResult(ProviderState.AVAILABLE,suggestions=(),reason="REUSED_EFFECTIVE_SUCCESS")
        return self.base.analyze(request)

    def consume_attempts(self):
        method = getattr(self.base,"consume_attempts",None)
        return method() if callable(method) else ()


def recover_content_remediation(
    *,
    workspace: AuditWorkspace,
    audit_id: str,
    item: WorkItem,
    provider: Any | None = None,
    force_all_contexts: bool = False,
) -> tuple[bool, Any, str]:
    from rasai import m20

    active_provider = provider or build_reprocess_provider(workspace,audit_id,item)
    successful = frozenset() if force_all_contexts else _successful_m20_snapshots(workspace,audit_id)
    original_factory = m20.build_content_remediation_router

    def selective_factory(base_provider: Any):
        return _SkipSuccessfulM20Router(original_factory(base_provider),successful)

    m20.build_content_remediation_router = selective_factory
    try:
        result = m20.execute_m20(
            audit_id=audit_id,enabled=True,semantic_provider=active_provider,workspace=workspace,
        )
    finally:
        m20.build_content_remediation_router = original_factory
    status = str(result.status)
    return status in {"SUCCESS","NO_SAFE_SUGGESTIONS","NO_ELIGIBLE_FINDINGS"}, active_provider, status


def _m24_diagnostics(workspace: AuditWorkspace, audit_id: str):
    from rasai.m24_crawling_discovery import M24Diagnostic
    connection = sqlite3.connect(workspace.database)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
            "SELECT * FROM m24_diagnostics WHERE audit_id=? ORDER BY diagnostic_id", (audit_id,)
        ).fetchall()
    finally:
        connection.close()
    return tuple(
        M24Diagnostic(
            code=str(row["code"]),category=str(row["category"]),severity=str(row["severity"]),
            title=str(row["title"]),scope_url=row["scope_url"],observed=_load(row["observed_value"],{}),
            evidence_ids=tuple(str(value) for value in _load(row["evidence_ids"],[])),
            remediation=str(row["remediation"]),scoring_impact=str(row["scoring_impact"]),
        )
        for row in rows
    )


def _clear_m24_scoring(workspace: AuditWorkspace, *, audit_id: str, reprocess_id: str) -> None:
    rules=("BR-GEO-055","BR-GEO-056")
    executions=_archive_query(
        workspace,audit_id=audit_id,reprocess_id=reprocess_id,component="TECHNICAL_AI",
        entity_type="rule_execution",id_field="rule_execution_id",
        sql="SELECT * FROM rule_executions WHERE audit_id=? AND rule_id IN (?,?)",params=(audit_id,*rules),
    )
    ids=tuple(str(row["rule_execution_id"]) for row in executions)
    if ids:
        marks=",".join("?" for _ in ids)
        _archive_query(
            workspace,audit_id=audit_id,reprocess_id=reprocess_id,component="TECHNICAL_AI",
            entity_type="finding",id_field="finding_id",sql=f"SELECT * FROM findings WHERE rule_execution_id IN ({marks})",params=ids,
        )
        connection=sqlite3.connect(workspace.database)
        connection.execute("PRAGMA foreign_keys=ON")
        try:
            with connection:
                connection.execute(f"DELETE FROM findings WHERE rule_execution_id IN ({marks})",ids)
                connection.execute(f"DELETE FROM rule_executions WHERE rule_execution_id IN ({marks})",ids)
        finally:
            connection.close()


def recover_technical_ai(
    *,
    workspace: AuditWorkspace,
    audit_id: str,
    item: WorkItem,
    reprocess_id: str,
    provider: Any | None = None,
) -> tuple[bool, Any]:
    from rasai.m24_ai import maybe_remediate_m24
    from rasai.m24_scoring import persist_m24_scoring_assessments
    from rasai.semantic import ProviderState

    active_provider=provider or build_reprocess_provider(workspace,audit_id,item)
    diagnostics=_m24_diagnostics(workspace,audit_id)
    result=maybe_remediate_m24(audit_id=audit_id,workspace=workspace,provider=active_provider,diagnostics=diagnostics)
    if result.state is not ProviderState.AVAILABLE:
        return False,active_provider
    _clear_m24_scoring(workspace,audit_id=audit_id,reprocess_id=reprocess_id)
    assessments=tuple((result.explanation or {}).get("resource_assessments") or ())
    with AuditPersistence(workspace) as persistence:
        persist_m24_scoring_assessments(
            audit_id=audit_id,persistence=persistence,ai_state=result.state.value,
            provider=result.provider,model=result.model,assessments=assessments,
        )
    return True,active_provider


def _clear_rule(
    workspace: AuditWorkspace,
    *,
    audit_id: str,
    rule_id: str,
    reprocess_id: str,
    component: str,
) -> None:
    executions=_archive_query(
        workspace,audit_id=audit_id,reprocess_id=reprocess_id,component=component,
        entity_type="rule_execution",id_field="rule_execution_id",
        sql="SELECT * FROM rule_executions WHERE audit_id=? AND rule_id=?",params=(audit_id,rule_id),
    )
    ids=tuple(str(row["rule_execution_id"]) for row in executions)
    if not ids:
        return
    marks=",".join("?" for _ in ids)
    _archive_query(
        workspace,audit_id=audit_id,reprocess_id=reprocess_id,component=component,
        entity_type="finding",id_field="finding_id",sql=f"SELECT * FROM findings WHERE rule_execution_id IN ({marks})",params=ids,
    )
    connection=sqlite3.connect(workspace.database)
    connection.execute("PRAGMA foreign_keys=ON")
    try:
        with connection:
            connection.execute(f"DELETE FROM findings WHERE rule_execution_id IN ({marks})",ids)
            connection.execute(f"DELETE FROM rule_executions WHERE rule_execution_id IN ({marks})",ids)
    finally:
        connection.close()


def _all_m3(workspace: AuditWorkspace, audit_id: str):
    from rasai.m3 import M3ExecutionResult
    connection=sqlite3.connect(workspace.database)
    connection.row_factory=sqlite3.Row
    try:
        rows=connection.execute(
            """SELECT ps.snapshot_id,ps.page_id,ps.device FROM page_snapshots ps JOIN pages p ON p.page_id=ps.page_id
               WHERE p.audit_id=? ORDER BY p.normalized_url,ps.device,ps.captured_at DESC""",(audit_id,),
        ).fetchall()
    finally:
        connection.close()
    mapping:dict[str,dict[DeviceContext,str]]={}
    for row in rows:
        device=DeviceContext(str(row["device"]))
        mapping.setdefault(str(row["page_id"]),{}).setdefault(device,str(row["snapshot_id"]))
    return M3ExecutionResult(snapshot_ids=mapping,failures=())


def _refresh_m8(workspace: AuditWorkspace, audit_id: str, reprocess_id: str) -> None:
    from rasai.m8 import execute_m8
    connection=sqlite3.connect(workspace.database)
    try:
        devices={str(row[0]) for row in connection.execute(
            """SELECT DISTINCT ps.device FROM page_snapshots ps JOIN pages p ON p.page_id=ps.page_id WHERE p.audit_id=?""",
            (audit_id,),
        ).fetchall()}
    finally:
        connection.close()
    if not {"DESKTOP","MOBILE"}.issubset(devices):
        return
    _clear_rule(workspace,audit_id=audit_id,rule_id="BR-GEO-052",reprocess_id=reprocess_id,component="DERIVED_RECOMPUTE")
    with AuditPersistence(workspace) as persistence:
        execute_m8(audit_id=audit_id,m3_result=_all_m3(workspace,audit_id),persistence=persistence,workspace=workspace)


def _refresh_integrity_rule(workspace: AuditWorkspace, audit_id: str, reprocess_id: str) -> None:
    from rasai.pre_scoring_rules import _persist
    _clear_rule(workspace,audit_id=audit_id,rule_id="BR-GEO-053",reprocess_id=reprocess_id,component="DERIVED_RECOMPUTE")
    with AuditPersistence(workspace) as persistence:
        connection=sqlite3.connect(workspace.database)
        try:
            ids=tuple(str(row[0]) for row in connection.execute(
                "SELECT finding_id FROM findings WHERE audit_id=? AND rule_id<>'BR-GEO-053' ORDER BY finding_id",(audit_id,),
            ).fetchall())
        finally:
            connection.close()
        invalid:list[dict[str,str]]=[]
        checked=0
        for finding_id in ids:
            finding=persistence.findings.get(finding_id)
            if finding is None:
                invalid.append({"finding_id":finding_id,"reason":"FINDING_NOT_REOPENABLE"})
                continue
            checked += 1
            execution=persistence.rule_executions.get(finding.rule_execution_id)
            if execution is None:
                invalid.append({"finding_id":finding_id,"reason":"RULE_EXECUTION_NOT_REOPENABLE"})
                continue
            for evidence_id in finding.evidence_ids:
                if persistence.evidence.get(evidence_id) is None:
                    invalid.append({"finding_id":finding_id,"reason":f"EVIDENCE_NOT_REOPENABLE:{evidence_id}"})
        _persist(
            audit_id=audit_id,page_id=None,snapshot_id=None,device=None,rule_id="BR-GEO-053",
            title="Every finding must be fully traceable",category="AUDITOR_INTEGRITY",severity=Severity.CRITICAL,
            result=RuleResult.FAIL if invalid else RuleResult.PASS,observed={"checked_findings":checked,"invalid":invalid},
            expected="every supplied finding reopens its RuleExecution and every referenced Evidence",
            manager=EvidenceManager(persistence),persistence=persistence,
        )


def _reset_scores(workspace: AuditWorkspace, audit_id: str, reprocess_id: str) -> None:
    _archive_query(
        workspace,audit_id=audit_id,reprocess_id=reprocess_id,component="DERIVED_RECOMPUTE",
        entity_type="score",id_field="score_id",sql="SELECT * FROM scores WHERE audit_id=?",params=(audit_id,),
    )
    _archive_query(
        workspace,audit_id=audit_id,reprocess_id=reprocess_id,component="DERIVED_RECOMPUTE",
        entity_type="score_contribution",id_field="contribution_id",
        sql="""SELECT sc.* FROM score_contributions sc JOIN scores s ON s.score_id=sc.score_id WHERE s.audit_id=?""",params=(audit_id,),
    )
    connection=sqlite3.connect(workspace.database)
    connection.execute("PRAGMA foreign_keys=ON")
    try:
        with connection:
            connection.execute("DELETE FROM scores WHERE audit_id=?",(audit_id,))
    except sqlite3.OperationalError:
        pass
    finally:
        connection.close()
    _clear_rule(workspace,audit_id=audit_id,rule_id="BR-GEO-054",reprocess_id=reprocess_id,component="DERIVED_RECOMPUTE")


def _reset_recommendations(workspace: AuditWorkspace, audit_id: str, reprocess_id: str) -> None:
    for table,entity,id_field in (
        ("recommendations","recommendation","recommendation_id"),
        ("remediation_groups","remediation_group","group_id"),
    ):
        try:
            _archive_query(
                workspace,audit_id=audit_id,reprocess_id=reprocess_id,component="DERIVED_RECOMPUTE",
                entity_type=entity,id_field=id_field,sql=f"SELECT * FROM {table} WHERE audit_id=?",params=(audit_id,),
            )
        except sqlite3.OperationalError:
            pass
    connection=sqlite3.connect(workspace.database)
    connection.execute("PRAGMA foreign_keys=ON")
    try:
        with connection:
            connection.execute("DELETE FROM recommendations WHERE audit_id=?",(audit_id,))
            connection.execute("DELETE FROM remediation_groups WHERE audit_id=?",(audit_id,))
    except sqlite3.OperationalError:
        pass
    finally:
        connection.close()


def recompute_derived_after_ai(
    *,
    workspace: AuditWorkspace,
    audit_id: str,
    reprocess_id: str,
    semantic_changed: bool,
) -> None:
    """Rebuild only derived data whose source AI evidence changed."""
    from rasai.m9 import execute_m9
    from rasai.m10 import execute_m10
    from rasai.m14_linking import link_findings_to_elements

    if semantic_changed:
        _refresh_m8(workspace,audit_id,reprocess_id)
    _refresh_integrity_rule(workspace,audit_id,reprocess_id)
    _reset_scores(workspace,audit_id,reprocess_id)
    _reset_recommendations(workspace,audit_id,reprocess_id)
    with AuditPersistence(workspace) as persistence:
        connection=sqlite3.connect(workspace.database)
        try:
            execution_ids=tuple(str(row[0]) for row in connection.execute(
                """SELECT rule_execution_id FROM rule_executions
                   WHERE audit_id=? AND rule_id<>'BR-GEO-054' ORDER BY executed_at,rowid""",(audit_id,),
            ).fetchall())
        finally:
            connection.close()
        execute_m9(audit_id=audit_id,rule_execution_ids=execution_ids,persistence=persistence,workspace=workspace)
        connection=sqlite3.connect(workspace.database)
        try:
            finding_ids=tuple(str(row[0]) for row in connection.execute(
                "SELECT finding_id FROM findings WHERE audit_id=? ORDER BY finding_id",(audit_id,),
            ).fetchall())
        finally:
            connection.close()
        execute_m10(audit_id=audit_id,finding_ids=finding_ids,persistence=persistence,workspace=workspace)
        link_findings_to_elements(finding_ids=finding_ids,persistence=persistence,workspace=workspace)


def invalidate_content_remediation_dependency(workspace: AuditWorkspace, audit_id: str) -> bool:
    """Invalidate a previously successful M20 result when its semantic findings changed."""
    connection=sqlite3.connect(workspace.database)
    try:
        row=connection.execute(
            """SELECT work_item_id FROM audit_fulfillment_work_items
               WHERE audit_id=? AND component='CONTENT_REMEDIATION_AI' AND required=1 LIMIT 1""",(audit_id,),
        ).fetchone()
        if row is None:
            return False
        with connection:
            connection.execute(
                """UPDATE audit_fulfillment_work_items SET status='PENDING',retryable=1,
                   effective_result_ref=NULL,last_error_class='DEPENDENCY_CHANGED',
                   last_error_code='SEMANTIC_EFFECTIVE_RESULT_CHANGED',
                   last_error_message='semantic effective findings changed during reprocessing',updated_at=?
                   WHERE work_item_id=?""",(utc_now().isoformat(),row[0]),
            )
        return True
    finally:
        connection.close()
