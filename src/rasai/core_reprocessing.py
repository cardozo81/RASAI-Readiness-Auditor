"""Bounded selective recovery for core evidence required by one logical AUD.

Collection work is versioned as RPR attempts and successful requirements are never
recollected.  A source capture that failed during the original execution may be retried
inside the configured LIVE_RECOLLECTION window.  A capture that was recorded as
successful but whose persisted artifact later disappeared is an integrity failure and is
never replaced with a later version of the website.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from types import SimpleNamespace
from typing import Any

from rasai.acquisition import HttpAcquisitionResult, HttpClient, NetworkError, NetworkErrorKind, RedirectHop
from rasai.audit_fulfillment import (
    BLOCKED,
    DISABLED,
    FAILED_PERMANENT,
    FAILED_RETRYABLE,
    LIVE_RECOLLECTION,
    NOT_APPLICABLE,
    PENDING,
    REPLAY_SAFE,
    RUNNING,
    SUCCESS,
    WAITING_FOR_DATA,
    WorkItem,
    archive_rows,
    begin_attempt,
    finish_attempt,
    finish_reprocess_run,
    list_work_items,
    project_report_validity,
    recalculate,
    register_work_item,
    set_work_item_status,
    start_reprocess_run,
)
from rasai.domain import DeviceContext, Evidence, EvidenceType, PageSnapshot, RuleExecution, RuleResult, new_id, utc_now
from rasai.evidence import EvidenceManager
from rasai.persistence import AuditPersistence, AuditWorkspace
from rasai.reprocess_policy import blocking_dependencies, item_executable, selected_counts

DISCOVERY_ACQUISITION = "DISCOVERY_ACQUISITION"
HTTP_ACQUISITION = "HTTP_ACQUISITION"
RENDER_CAPTURE = "RENDER_CAPTURE"
CONTENT_EXTRACTION = "CONTENT_EXTRACTION"
CORE_COMPONENTS = frozenset({DISCOVERY_ACQUISITION, HTTP_ACQUISITION, RENDER_CAPTURE, CONTENT_EXTRACTION})
_AI_COMPONENTS = frozenset({"SEMANTIC_AI", "TECHNICAL_AI", "CONTENT_REMEDIATION_AI"})
_RETRYABLE_STATES = frozenset({PENDING, RUNNING, WAITING_FOR_DATA, FAILED_RETRYABLE})
_RESOLVED_STATES = frozenset({SUCCESS, DISABLED, NOT_APPLICABLE})
_REDIRECT_FAILURES = frozenset({"REDIRECT_LOOP", "TOO_MANY_REDIRECTS", "INVALID_REDIRECT"})
_INSTALLED = False


def _load(raw: Any, default: Any) -> Any:
    if raw in (None, ""):
        return default
    if isinstance(raw, (dict, list, tuple)):
        return raw
    try:
        return json.loads(str(raw))
    except (TypeError, ValueError, json.JSONDecodeError):
        return default


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _expired(item: WorkItem) -> bool:
    if item.temporal_mode != LIVE_RECOLLECTION or item.status == SUCCESS:
        return False
    deadline = _parse_time(item.valid_until)
    return bool(deadline and datetime.now(timezone.utc) > deadline)


def _file_exists(workspace: AuditWorkspace, reference: str | None) -> bool:
    return bool(reference and (workspace.root / str(reference)).is_file())


def _latest_rule_result(
    connection: sqlite3.Connection,
    audit_id: str,
    rule_id: str,
    *,
    page_id: str | None = None,
    snapshot_id: str | None = None,
) -> str | None:
    clauses = ["audit_id=?", "rule_id=?"]
    params: list[Any] = [audit_id, rule_id]
    if page_id is not None:
        clauses.append("page_id=?")
        params.append(page_id)
    if snapshot_id is not None:
        clauses.append("snapshot_id=?")
        params.append(snapshot_id)
    row = connection.execute(
        f"SELECT result FROM rule_executions WHERE {' AND '.join(clauses)} "
        "ORDER BY executed_at DESC,rowid DESC LIMIT 1",
        tuple(params),
    ).fetchone()
    return str(row[0]) if row else None


def _set_item(
    workspace: AuditWorkspace,
    *,
    audit_id: str,
    component: str,
    scope_key: str,
    status: str,
    temporal_mode: str,
    retryable: bool,
    source_captured_at: str | None,
    configuration: dict[str, Any],
    result_ref: str | None = None,
    error_code: str | None = None,
    error_message: str | None = None,
) -> None:
    register_work_item(
        workspace,
        audit_id=audit_id,
        component=component,
        scope_key=scope_key,
        required=True,
        temporal_mode=temporal_mode,
        status=status,
        retryable=retryable,
        source_captured_at=source_captured_at,
        configuration=configuration,
    )
    set_work_item_status(
        workspace,
        audit_id=audit_id,
        component=component,
        scope_key=scope_key,
        status=status,
        result_ref=result_ref,
        error_class=None if status == SUCCESS else "CORE_PREREQUISITE",
        error_code=error_code,
        error_message=error_message,
        retryable=retryable,
    )


def synchronize_core_work_items(workspace: AuditWorkspace, audit_id: str) -> None:
    """Project acquisition/render/extraction requirements from persisted evidence."""
    connection = sqlite3.connect(workspace.database)
    connection.row_factory = sqlite3.Row
    try:
        audit = connection.execute(
            "SELECT status,started_at,created_at FROM audits WHERE audit_id=?", (audit_id,)
        ).fetchone()
        if audit is None:
            raise ValueError(f"audit_id not found in audit.db: {audit_id}")
        audit_time = str(audit["started_at"] or audit["created_at"] or "") or None
        pages = tuple(connection.execute(
            "SELECT page_id,normalized_url FROM pages WHERE audit_id=? ORDER BY depth,page_id",
            (audit_id,),
        ).fetchall())
        snapshots = tuple(connection.execute(
            """SELECT ps.* FROM page_snapshots ps JOIN pages p ON p.page_id=ps.page_id
               WHERE p.audit_id=? ORDER BY ps.captured_at,ps.snapshot_id""",
            (audit_id,),
        ).fetchall())

        page_states: list[tuple[str, str, bool]] = []
        for page in pages:
            page_id = str(page["page_id"])
            url = str(page["normalized_url"])
            http_ok = _latest_rule_result(connection,audit_id,"BR-GEO-005",page_id=page_id) == RuleResult.PASS.value
            page_states.append((page_id,url,http_ok))

        snapshot_states: list[dict[str, Any]] = []
        for snapshot in snapshots:
            snapshot_id = str(snapshot["snapshot_id"])
            metadata = _load(snapshot["browser_metadata"], {})
            rendered_ref = str(snapshot["rendered_artifact_ref"] or "") or None
            raw_ref = str(snapshot["raw_artifact_ref"] or "") or None
            rendered_exists = _file_exists(workspace,rendered_ref)
            raw_exists = _file_exists(workspace,raw_ref)
            render_declared_success = bool(metadata.get("render_succeeded"))
            extraction_evidence = bool(connection.execute(
                """SELECT 1 FROM evidence WHERE audit_id=? AND snapshot_id=?
                   AND source IN ('RENDERED_DOM','RAW_HTML_FALLBACK') LIMIT 1""",
                (audit_id,snapshot_id),
            ).fetchone())
            snapshot_states.append({
                "snapshot_id": snapshot_id,
                "page_id": str(snapshot["page_id"]),
                "device": str(snapshot["device"]),
                "url": str(snapshot["requested_url"]),
                "captured_at": str(snapshot["captured_at"] or audit_time or "") or None,
                "rendered_ref": rendered_ref,
                "raw_ref": raw_ref,
                "rendered_exists": rendered_exists,
                "raw_exists": raw_exists,
                "render_declared_success": render_declared_success,
                "extraction_evidence": extraction_evidence,
            })
    finally:
        connection.close()

    existing_discovery = next(
        (item for item in list_work_items(workspace, audit_id) if item.component == DISCOVERY_ACQUISITION),
        None,
    )
    audit_status = str(audit["status"] or "").upper()
    if existing_discovery is not None and existing_discovery.status == SUCCESS:
        discovery_status = SUCCESS
        discovery_retryable = True
        discovery_code = None
    elif audit_status == "COMPLETED":
        discovery_status = SUCCESS
        discovery_retryable = False
        discovery_code = None
    elif existing_discovery is None and pages and (
        snapshots or audit_status in {"ACQUIRING", "ANALYZING", "COMPARING", "SCORING", "RECOMMENDING", "REPORTING"}
    ):
        # Conservative legacy backfill: persisted downstream evidence proves M2 had
        # already returned. A FAILED/CANCELLED legacy AUD without this proof remains
        # retryable rather than being silently declared complete.
        discovery_status = SUCCESS
        discovery_retryable = True
        discovery_code = None
    else:
        discovery_status = FAILED_RETRYABLE
        discovery_retryable = True
        discovery_code = "DISCOVERY_ACQUISITION_INCOMPLETE"
    _set_item(
        workspace,
        audit_id=audit_id,
        component=DISCOVERY_ACQUISITION,
        scope_key="AUDIT",
        status=discovery_status,
        temporal_mode=LIVE_RECOLLECTION,
        retryable=discovery_retryable,
        source_captured_at=audit_time,
        configuration={"stage": "M2_DISCOVERY_ACQUISITION"},
        result_ref=f"discovery:{audit_id}:effective" if discovery_status == SUCCESS else None,
        error_code=discovery_code,
        error_message=(
            None
            if discovery_status == SUCCESS
            else "a descoberta/aquisição inicial não possui checkpoint final confirmado"
        ),
    )

    for page_id,url,http_ok in page_states:
        _set_item(
            workspace,audit_id=audit_id,component=HTTP_ACQUISITION,scope_key=page_id,
            status=SUCCESS if http_ok else FAILED_RETRYABLE,temporal_mode=LIVE_RECOLLECTION,
            retryable=not http_ok or True,source_captured_at=audit_time,
            configuration={"page_id":page_id,"url":url},
            result_ref=f"http:{page_id}:effective" if http_ok else None,
            error_code=None if http_ok else "HTTP_ACQUISITION_INCOMPLETE",
            error_message=None if http_ok else "no effective retrievable HTTP acquisition is persisted for this page",
        )

    for state in snapshot_states:
        snapshot_id = state["snapshot_id"]
        config = {"page_id":state["page_id"],"device":state["device"],"url":state["url"]}
        if state["render_declared_success"] and state["rendered_exists"]:
            render_status,render_retryable,render_code = SUCCESS,True,None
            render_ref = state["rendered_ref"]
        elif state["render_declared_success"]:
            # A successful source that disappeared is evidence-integrity loss, not a
            # transient collection failure. Re-fetching would silently replace history.
            render_status,render_retryable,render_code = BLOCKED,False,"PERSISTED_RENDER_ARTIFACT_MISSING"
            render_ref = None
        else:
            render_status,render_retryable,render_code = FAILED_RETRYABLE,True,"RENDER_CAPTURE_INCOMPLETE"
            render_ref = None
        _set_item(
            workspace,audit_id=audit_id,component=RENDER_CAPTURE,scope_key=snapshot_id,
            status=render_status,temporal_mode=LIVE_RECOLLECTION,retryable=render_retryable,
            source_captured_at=state["captured_at"],configuration=config,result_ref=render_ref,
            error_code=render_code,
            error_message=(None if render_status == SUCCESS else (
                "persisted successful rendered artifact is missing; a later page version cannot replace it"
                if render_status == BLOCKED else "browser document capture did not succeed"
            )),
        )

        source_available = bool(state["rendered_exists"] or state["raw_exists"])
        source_was_declared = bool(state["rendered_ref"] or state["raw_ref"])
        if state["extraction_evidence"]:
            extraction_status,extraction_retryable,extraction_code = SUCCESS,True,None
        elif source_available:
            extraction_status,extraction_retryable,extraction_code = FAILED_RETRYABLE,True,"EXTRACTION_INCOMPLETE"
        elif state["render_declared_success"] or source_was_declared:
            extraction_status,extraction_retryable,extraction_code = BLOCKED,False,"PERSISTED_EXTRACTION_SOURCE_MISSING"
        else:
            extraction_status,extraction_retryable,extraction_code = WAITING_FOR_DATA,True,"EXTRACTION_SOURCE_UNAVAILABLE"
        _set_item(
            workspace,audit_id=audit_id,component=CONTENT_EXTRACTION,scope_key=snapshot_id,
            status=extraction_status,temporal_mode=REPLAY_SAFE,retryable=extraction_retryable,
            source_captured_at=state["captured_at"],configuration={"page_id":state["page_id"],"device":state["device"]},
            result_ref=f"extraction:{snapshot_id}:effective" if extraction_status == SUCCESS else None,
            error_code=extraction_code,
            error_message=(None if extraction_status == SUCCESS else (
                "persisted source artifact required for extraction is missing"
                if extraction_status == BLOCKED else "deterministic extraction is not yet complete"
            )),
        )

    # An interrupted M3 can die before a PageSnapshot row is created. The original
    # device universe is therefore read from the durable resume/configuration contract,
    # not inferred from whatever snapshots happened to survive.
    from rasai.audit_resume_runtime import expected_devices_for_audit

    expected_devices = expected_devices_for_audit(workspace, audit_id)
    effective_pairs = {
        (str(state["page_id"]), str(state["device"]).upper()): str(state["snapshot_id"])
        for state in snapshot_states
    }

    # Reconcile a previously planned context if its snapshot was persisted before the
    # process died but the fulfillment item itself never reached SUCCESS.
    for item in list_work_items(workspace, audit_id):
        if item.component != RENDER_CAPTURE or not bool(item.configuration.get("planned")):
            continue
        page_id = str(item.configuration.get("page_id") or "")
        device = str(item.configuration.get("device") or "").upper()
        snapshot_id = effective_pairs.get((page_id, device))
        if snapshot_id:
            set_work_item_status(
                workspace,
                audit_id=audit_id,
                component=RENDER_CAPTURE,
                scope_key=item.scope_key,
                status=SUCCESS,
                result_ref=f"render:{snapshot_id}:effective",
                retryable=False,
            )

    for page_id, url, http_ok in page_states:
        for device in expected_devices:
            normalized_device = str(device).upper()
            if (page_id, normalized_device) in effective_pairs:
                continue
            planned_scope = f"PLANNED:{page_id}:{normalized_device}"
            _set_item(
                workspace,
                audit_id=audit_id,
                component=RENDER_CAPTURE,
                scope_key=planned_scope,
                status=PENDING if http_ok else WAITING_FOR_DATA,
                temporal_mode=LIVE_RECOLLECTION,
                retryable=True,
                source_captured_at=audit_time,
                configuration={
                    "page_id": page_id,
                    "device": normalized_device,
                    "url": url,
                    "planned": True,
                },
                error_code=None if http_ok else "HTTP_ACQUISITION_REQUIRED",
                error_message=(
                    "contexto de renderização previsto pela configuração original ainda não foi materializado"
                    if http_ok
                    else "contexto de renderização aguarda aquisição HTTP recuperável"
                ),
            )
    recalculate(workspace,audit_id)


def _core_items(workspace: AuditWorkspace, audit_id: str) -> tuple[WorkItem, ...]:
    return tuple(item for item in list_work_items(workspace,audit_id) if item.required and item.component in CORE_COMPONENTS)


def _retryable_core(workspace: AuditWorkspace, audit_id: str) -> tuple[WorkItem, ...]:
    return tuple(
        item for item in _core_items(workspace,audit_id)
        if item_executable(item)
        and item.retryable
        and item.status in _RETRYABLE_STATES
        and not _expired(item)
    )


def _core_unresolved(workspace: AuditWorkspace, audit_id: str) -> bool:
    return any(
        item_executable(item) and item.status not in _RESOLVED_STATES
        for item in _core_items(workspace,audit_id)
    )


def _archive_rows_for_query(
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
        rows = tuple(dict(row) for row in connection.execute(sql,params).fetchall())
    finally:
        connection.close()
    if rows:
        archive_rows(
            workspace,audit_id=audit_id,reprocess_id=reprocess_id,component=component,
            entity_type=entity_type,id_field=id_field,rows=rows,
        )
    return rows


def _archive_rule_scope(
    workspace: AuditWorkspace,
    *,
    audit_id: str,
    reprocess_id: str,
    rule_ids: tuple[str, ...],
    page_id: str | None = None,
    snapshot_id: str | None = None,
) -> None:
    marks = ",".join("?" for _ in rule_ids)
    clauses = ["audit_id=?",f"rule_id IN ({marks})"]
    params: list[Any] = [audit_id,*rule_ids]
    if page_id is not None:
        clauses.append("page_id=?")
        params.append(page_id)
    if snapshot_id is not None:
        clauses.append("snapshot_id=?")
        params.append(snapshot_id)
    executions = _archive_rows_for_query(
        workspace,audit_id=audit_id,reprocess_id=reprocess_id,component="CORE_DERIVED",
        entity_type="rule_execution",id_field="rule_execution_id",
        sql=f"SELECT * FROM rule_executions WHERE {' AND '.join(clauses)}",params=tuple(params),
    )
    ids = tuple(str(row["rule_execution_id"]) for row in executions)
    if not ids:
        return
    id_marks = ",".join("?" for _ in ids)
    _archive_rows_for_query(
        workspace,audit_id=audit_id,reprocess_id=reprocess_id,component="CORE_DERIVED",
        entity_type="finding",id_field="finding_id",
        sql=f"SELECT * FROM findings WHERE rule_execution_id IN ({id_marks})",params=ids,
    )
    connection = sqlite3.connect(workspace.database)
    connection.execute("PRAGMA foreign_keys=ON")
    try:
        with connection:
            connection.execute(f"DELETE FROM findings WHERE rule_execution_id IN ({id_marks})",ids)
            connection.execute(f"DELETE FROM rule_executions WHERE rule_execution_id IN ({id_marks})",ids)
    finally:
        connection.close()


def _write_artifact(workspace: AuditWorkspace, reprocess_id: str, family: str, filename: str, payload: bytes) -> str | None:
    if not payload:
        return None
    directory = workspace.artifacts / "reprocess" / reprocess_id / family
    directory.mkdir(parents=True,exist_ok=True)
    path = directory / filename
    path.write_bytes(payload)
    return path.relative_to(workspace.root).as_posix()


def _read_bytes(workspace: AuditWorkspace, reference: str | None) -> bytes:
    return (workspace.root / str(reference)).read_bytes() if _file_exists(workspace,reference) else b""


def _load_acquisition(workspace: AuditWorkspace, page_id: str) -> HttpAcquisitionResult | None:
    connection = sqlite3.connect(workspace.database)
    connection.row_factory = sqlite3.Row
    try:
        row = connection.execute(
            """SELECT observed_value,artifact_reference FROM evidence
               WHERE page_id=? AND evidence_type=? AND source='http'
               ORDER BY captured_at DESC,rowid DESC LIMIT 1""",
            (page_id,EvidenceType.HTTP_RESPONSE.value),
        ).fetchone()
    finally:
        connection.close()
    if row is None:
        return None
    observed = _load(row["observed_value"],{})
    redirects = tuple(
        RedirectHop(
            status=int(item.get("status") or 0),source_url=str(item.get("source_url") or ""),
            location=str(item.get("location") or ""),target_url=str(item.get("target_url") or ""),
        )
        for item in observed.get("redirect_chain",()) if isinstance(item,dict)
    )
    raw_error = observed.get("network_error")
    network_error = None
    if isinstance(raw_error,dict) and raw_error.get("kind"):
        try:
            kind = NetworkErrorKind(str(raw_error["kind"]))
        except ValueError:
            kind = NetworkErrorKind.UNKNOWN
        network_error = NetworkError(kind,str(raw_error.get("message") or ""))
    headers: list[tuple[str,str]] = []
    for pair in observed.get("headers",()):
        if isinstance(pair,(list,tuple)) and len(pair) == 2:
            headers.append((str(pair[0]),str(pair[1])))
    return HttpAcquisitionResult(
        requested_url=str(observed.get("requested_url") or ""),
        final_url=str(observed.get("final_url")) if observed.get("final_url") else None,
        status=int(observed["status"]) if observed.get("status") is not None else None,
        headers=tuple(headers),body=_read_bytes(workspace,row["artifact_reference"]),redirects=redirects,
        network_error=network_error,elapsed_ms=int(observed.get("elapsed_ms") or 0),
    )


def _replace_http_rules(
    workspace: AuditWorkspace,
    *,
    audit_id: str,
    page_id: str,
    acquisition: HttpAcquisitionResult,
    evidence_ids: tuple[str, ...],
    reprocess_id: str,
) -> None:
    _archive_rule_scope(
        workspace,audit_id=audit_id,reprocess_id=reprocess_id,
        rule_ids=("BR-GEO-004","BR-GEO-005","BR-GEO-007"),page_id=page_id,
    )
    error_kind = acquisition.network_error.kind.value if acquisition.network_error else None
    retrievable = acquisition.network_error is None and acquisition.status is not None
    if error_kind in _REDIRECT_FAILURES:
        redirect_result = RuleResult.FAIL
    elif acquisition.network_error is not None:
        redirect_result = RuleResult.NOT_APPLICABLE
    else:
        redirect_result = RuleResult.PASS
    executions = (
        RuleExecution(new_id("REX"),audit_id,"BR-GEO-004","1",page_id,None,None,RuleResult.PASS,
            {"requested_url":acquisition.requested_url,"final_url":acquisition.final_url,"status":acquisition.status,
             "network_error":error_kind,"body_preserved":bool(acquisition.body)},
            "HTTP acquisition result and body artifact are preserved when available",evidence_ids,utc_now()),
        RuleExecution(new_id("REX"),audit_id,"BR-GEO-005","1",page_id,None,None,
            RuleResult.PASS if retrievable else RuleResult.FAIL,
            {"status":acquisition.status,"network_error":error_kind},
            "page yields a technical HTTP response without DNS/TLS/connection/timeout failure",evidence_ids,utc_now()),
        RuleExecution(new_id("REX"),audit_id,"BR-GEO-007","1",page_id,None,None,redirect_result,
            {"redirects":[{"status":hop.status,"source_url":hop.source_url,"location":hop.location,"target_url":hop.target_url} for hop in acquisition.redirects],
             "network_error":error_kind},"redirect chain resolves without loops or invalid hops",evidence_ids,utc_now()),
    )
    with AuditPersistence(workspace) as persistence:
        for execution in executions:
            persistence.rule_executions.add(execution)


def _archive_incomplete_discovery(
    workspace: AuditWorkspace,
    *,
    audit_id: str,
    reprocess_id: str,
) -> tuple[bool, str]:
    """Archive and clear only a partially persisted M2 stage before replaying it.

    M3 cannot have started while the audit still owns an unfinished M2 attempt. If a
    snapshot is present, recovery refuses destructive cleanup because downstream
    evidence proves the boundary is no longer an isolated discovery stage.
    """
    connection = sqlite3.connect(workspace.database)
    connection.row_factory = sqlite3.Row
    try:
        snapshots = int(connection.execute(
            """SELECT count(*) FROM page_snapshots ps
               JOIN pages p ON p.page_id=ps.page_id WHERE p.audit_id=?""",
            (audit_id,),
        ).fetchone()[0])
        pages = tuple(dict(row) for row in connection.execute(
            "SELECT * FROM pages WHERE audit_id=? ORDER BY rowid",
            (audit_id,),
        ).fetchall())
        evidence = tuple(dict(row) for row in connection.execute(
            "SELECT * FROM evidence WHERE audit_id=? ORDER BY rowid",
            (audit_id,),
        ).fetchall())
        rules = tuple(dict(row) for row in connection.execute(
            "SELECT * FROM rule_executions WHERE audit_id=? ORDER BY rowid",
            (audit_id,),
        ).fetchall())
    finally:
        connection.close()

    if snapshots:
        return False, "DISCOVERY_PARTIAL_WITH_DOWNSTREAM_EVIDENCE"

    if pages:
        archive_rows(
            workspace,
            audit_id=audit_id,
            reprocess_id=reprocess_id,
            component=DISCOVERY_ACQUISITION,
            entity_type="partial_m2_page",
            id_field="page_id",
            rows=pages,
        )
    if evidence:
        archive_rows(
            workspace,
            audit_id=audit_id,
            reprocess_id=reprocess_id,
            component=DISCOVERY_ACQUISITION,
            entity_type="partial_m2_evidence",
            id_field="evidence_id",
            rows=evidence,
        )
    if rules:
        archive_rows(
            workspace,
            audit_id=audit_id,
            reprocess_id=reprocess_id,
            component=DISCOVERY_ACQUISITION,
            entity_type="partial_m2_rule_execution",
            id_field="rule_execution_id",
            rows=rules,
        )

    connection = sqlite3.connect(workspace.database)
    connection.execute("PRAGMA foreign_keys=ON")
    try:
        with connection:
            rule_ids = tuple(str(row["rule_execution_id"]) for row in rules)
            if rule_ids:
                marks = ",".join("?" for _ in rule_ids)
                connection.execute(
                    f"DELETE FROM findings WHERE rule_execution_id IN ({marks})",
                    rule_ids,
                )
            connection.execute("DELETE FROM rule_executions WHERE audit_id=?", (audit_id,))
            connection.execute("DELETE FROM evidence WHERE audit_id=?", (audit_id,))
            connection.execute("DELETE FROM pages WHERE audit_id=?", (audit_id,))
    finally:
        connection.close()
    return True, "PARTIAL_DISCOVERY_ARCHIVED"


def _recover_discovery(
    workspace: AuditWorkspace,
    audit_id: str,
    item: WorkItem,
    reprocess_id: str,
) -> tuple[bool,str,set[str]]:
    from rasai.audit_resume_runtime import load_resume_plan
    from rasai.m2 import execute_m2

    plan = load_resume_plan(workspace, audit_id)
    targets = tuple(str(value) for value in plan.get("targets", ()) if str(value).strip())
    if not targets:
        return False, "AUDIT_RESUME_PLAN_UNAVAILABLE", set()

    with AuditPersistence(workspace) as persistence:
        audit = persistence.audits.get(audit_id)
        if audit is None:
            return False, "AUDIT_NOT_FOUND", set()
        connection = sqlite3.connect(workspace.database)
        connection.row_factory = sqlite3.Row
        try:
            target_row = connection.execute(
                "SELECT target_id FROM audit_targets WHERE audit_id=? ORDER BY rowid LIMIT 1",
                (audit_id,),
            ).fetchone()
        finally:
            connection.close()
        if target_row is None:
            return False, "AUDIT_TARGET_NOT_FOUND", set()
        target = persistence.targets.get(str(target_row["target_id"]))
        if target is None:
            return False, "AUDIT_TARGET_NOT_FOUND", set()

        cleared, code = _archive_incomplete_discovery(
            workspace,
            audit_id=audit_id,
            reprocess_id=reprocess_id,
        )
        if not cleared:
            return False, code, set()

        explicit_urls = targets if str(plan.get("target_type") or "").upper() == "URL_SET" else None
        result = execute_m2(
            audit,
            target,
            persistence,
            workspace,
            explicit_urls=explicit_urls,
        )
    if not result.page_ids:
        return False, "DISCOVERY_RETURNED_NO_PAGES", set()
    return True, "DISCOVERY_ACQUISITION_RECOVERED", set()


def _recover_http(workspace: AuditWorkspace, audit_id: str, item: WorkItem, reprocess_id: str) -> tuple[bool,str,set[str]]:
    page_id = item.scope_key
    url = str(item.configuration.get("url") or "").strip()
    if not url:
        return False,"PAGE_URL_UNAVAILABLE",set()
    acquisition = HttpClient().acquire(url)
    artifact_ref = _write_artifact(workspace,reprocess_id,"http",f"{page_id}.response",acquisition.body)
    from rasai import m2
    response = Evidence(
        new_id("EV-GEO"),audit_id,page_id,None,None,EvidenceType.HTTP_RESPONSE,"http",
        m2._http_observed_value(acquisition),artifact_ref,utc_now(),
    )
    evidence_ids: list[str] = []
    with AuditPersistence(workspace) as persistence:
        persistence.evidence.add(response)
        evidence_ids.append(response.evidence_id)
        if acquisition.headers:
            header = Evidence(new_id("EV-GEO"),audit_id,page_id,None,None,EvidenceType.HTTP_HEADER,"http",
                {"headers":[list(value) for value in acquisition.headers]},None,utc_now())
            persistence.evidence.add(header)
            evidence_ids.append(header.evidence_id)
    if artifact_ref:
        connection = sqlite3.connect(workspace.database)
        try:
            with connection:
                connection.execute(
                    "UPDATE page_snapshots SET raw_artifact_ref=? WHERE page_id=? AND raw_artifact_ref IS NULL",
                    (artifact_ref,page_id),
                )
        finally:
            connection.close()
    _replace_http_rules(
        workspace,audit_id=audit_id,page_id=page_id,acquisition=acquisition,
        evidence_ids=tuple(evidence_ids),reprocess_id=reprocess_id,
    )
    connection = sqlite3.connect(workspace.database)
    try:
        snapshots = {str(row[0]) for row in connection.execute(
            "SELECT snapshot_id FROM page_snapshots WHERE page_id=?",(page_id,)
        ).fetchall()}
    finally:
        connection.close()
    success = acquisition.network_error is None and acquisition.status is not None
    code = "HTTP_ACQUISITION_RECOVERED" if success else (
        acquisition.network_error.kind.value if acquisition.network_error else "HTTP_RESPONSE_UNAVAILABLE"
    )
    return success,code,snapshots


def _snapshot_row(workspace: AuditWorkspace, audit_id: str, snapshot_id: str) -> sqlite3.Row | None:
    connection = sqlite3.connect(workspace.database)
    connection.row_factory = sqlite3.Row
    try:
        return connection.execute(
            """SELECT ps.* FROM page_snapshots ps JOIN pages p ON p.page_id=ps.page_id
               WHERE ps.snapshot_id=? AND p.audit_id=?""",(snapshot_id,audit_id),
        ).fetchone()
    finally:
        connection.close()


def _archive_snapshot(workspace: AuditWorkspace, *, audit_id: str, snapshot_id: str, reprocess_id: str, component: str) -> None:
    row = _snapshot_row(workspace,audit_id,snapshot_id)
    if row is not None:
        archive_rows(
            workspace,audit_id=audit_id,reprocess_id=reprocess_id,component=component,
            entity_type="page_snapshot",id_field="snapshot_id",rows=(dict(row),),
        )


def _recover_render(
    workspace: AuditWorkspace,
    audit_id: str,
    item: WorkItem,
    reprocess_id: str,
    renderer: Any,
) -> tuple[bool,str,set[str]]:
    snapshot_id = item.scope_key
    row = _snapshot_row(workspace,audit_id,snapshot_id)

    # A planned item represents a device context that belonged to the original
    # execution contract but never got a PageSnapshot row before interruption.
    if row is None and bool(item.configuration.get("planned")):
        page_id = str(item.configuration.get("page_id") or "")
        url = str(item.configuration.get("url") or "")
        raw_device = str(item.configuration.get("device") or "").upper()
        if not page_id or not url or raw_device not in {"MOBILE", "DESKTOP"}:
            return False,"PLANNED_RENDER_CONTEXT_INVALID",set()
        device = DeviceContext(raw_device)
        acquisition = _load_acquisition(workspace,page_id)
        if acquisition is None:
            return False,"HTTP_ACQUISITION_REQUIRED",set()
        trace = [
            {"url":hop.source_url,"status":hop.status,"location":hop.location}
            for hop in acquisition.redirects
        ]
        try:
            result = renderer.render(url,device,preflight_navigation_trace=trace)
        except TypeError:
            result = renderer.render(url,device)
        if result.error_kind is not None or not result.rendered_html:
            return False,getattr(result.error_kind,"value",None) or "RENDERED_DOCUMENT_UNAVAILABLE",set()

        snapshot_id = new_id("SNP")
        rendered_ref = _write_artifact(
            workspace,reprocess_id,"rendered",f"{snapshot_id}.html",result.rendered_html.encode("utf-8")
        )
        visual_ref = _write_artifact(
            workspace,reprocess_id,"visual",f"{snapshot_id}.png",result.screenshot_png or b""
        )
        connection = sqlite3.connect(workspace.database)
        try:
            raw = connection.execute(
                """SELECT artifact_reference FROM evidence
                   WHERE audit_id=? AND page_id=? AND evidence_type=? AND source='http'
                   ORDER BY captured_at DESC,rowid DESC LIMIT 1""",
                (audit_id,page_id,EvidenceType.HTTP_RESPONSE.value),
            ).fetchone()
        finally:
            connection.close()
        raw_ref = str(raw[0]) if raw is not None and raw[0] else None
        metadata = dict(result.browser_metadata or {})
        metadata["render_succeeded"] = True
        metadata["visual_artifact_ref"] = visual_ref
        metadata["audit_device_context"] = list(
            __import__("rasai.audit_resume_runtime",fromlist=["expected_devices_for_audit"])
            .expected_devices_for_audit(workspace,audit_id)
        )
        metadata["reprocess_capture"] = {
            "reprocess_id":reprocess_id,
            "captured_at":utc_now().isoformat(),
            "planned_context_recovery":True,
        }
        snapshot = PageSnapshot(
            snapshot_id=snapshot_id,
            page_id=page_id,
            device=device,
            requested_url=url,
            final_url=result.final_url or acquisition.final_url or url,
            captured_at=utc_now(),
            http_status=result.http_status if result.http_status is not None else acquisition.status,
            content_type=result.content_type or acquisition.header("Content-Type"),
            rendering_mode="PLAYWRIGHT_CHROMIUM",
            raw_artifact_ref=raw_ref,
            rendered_artifact_ref=rendered_ref,
            browser_metadata=metadata,
        )
        with AuditPersistence(workspace) as persistence:
            persistence.snapshots.add(snapshot)
        return True,"PLANNED_RENDER_CAPTURE_RECOVERED",{snapshot_id}

    if row is None:
        return False,"SNAPSHOT_NOT_FOUND",set()
    metadata = _load(row["browser_metadata"],{})
    if bool(metadata.get("render_succeeded")):
        return False,"PERSISTED_RENDER_ARTIFACT_MISSING",set()
    device = DeviceContext(str(row["device"]))
    acquisition = _load_acquisition(workspace,str(row["page_id"]))
    trace = ([{"url":hop.source_url,"status":hop.status,"location":hop.location} for hop in acquisition.redirects]
             if acquisition is not None else [])
    try:
        result = renderer.render(str(row["requested_url"]),device,preflight_navigation_trace=trace)
    except TypeError:
        result = renderer.render(str(row["requested_url"]),device)
    if result.error_kind is not None or not result.rendered_html:
        return False,getattr(result.error_kind,"value",None) or "RENDERED_DOCUMENT_UNAVAILABLE",set()
    _archive_snapshot(workspace,audit_id=audit_id,snapshot_id=snapshot_id,reprocess_id=reprocess_id,component=RENDER_CAPTURE)
    rendered_ref = _write_artifact(workspace,reprocess_id,"rendered",f"{snapshot_id}.html",result.rendered_html.encode("utf-8"))
    visual_ref = _write_artifact(workspace,reprocess_id,"visual",f"{snapshot_id}.png",result.screenshot_png or b"")
    metadata.update(dict(result.browser_metadata or {}))
    metadata["render_succeeded"] = True
    metadata["visual_artifact_ref"] = visual_ref
    metadata["reprocess_capture"] = {"reprocess_id":reprocess_id,"captured_at":utc_now().isoformat()}
    connection = sqlite3.connect(workspace.database)
    try:
        with connection:
            connection.execute(
                """UPDATE page_snapshots SET final_url=?,http_status=?,content_type=?,rendered_artifact_ref=?,browser_metadata=?
                   WHERE snapshot_id=?""",
                (result.final_url or row["final_url"],result.http_status if result.http_status is not None else row["http_status"],
                 result.content_type or row["content_type"],rendered_ref,json.dumps(metadata,ensure_ascii=False,sort_keys=True),snapshot_id),
            )
    finally:
        connection.close()
    return True,"RENDER_CAPTURE_RECOVERED",{snapshot_id}


def _recover_extraction(workspace: AuditWorkspace, audit_id: str, item: WorkItem, reprocess_id: str) -> tuple[bool,str,set[str]]:
    from rasai.m3 import M3ExecutionResult
    from rasai.m4 import execute_m4
    snapshot_id = item.scope_key
    row = _snapshot_row(workspace,audit_id,snapshot_id)
    if row is None:
        return False,"SNAPSHOT_NOT_FOUND",set()
    if not (_file_exists(workspace,row["rendered_artifact_ref"]) or _file_exists(workspace,row["raw_artifact_ref"])):
        return False,"EXTRACTION_SOURCE_UNAVAILABLE",set()
    _archive_snapshot(workspace,audit_id=audit_id,snapshot_id=snapshot_id,reprocess_id=reprocess_id,component=CONTENT_EXTRACTION)
    page_id = str(row["page_id"])
    device = DeviceContext(str(row["device"]))
    with AuditPersistence(workspace) as persistence:
        result = execute_m4(M3ExecutionResult(snapshot_ids={page_id:{device:snapshot_id}},failures=()),persistence,workspace)
    failure = next((entry for entry in result.failures if entry.snapshot_id == snapshot_id),None)
    if failure is not None:
        return False,failure.error_kind,set()
    return True,"EXTRACTION_RECOVERED",{snapshot_id}


def _attempt(
    workspace: AuditWorkspace,
    audit_id: str,
    item: WorkItem,
    reprocess_id: str,
    *,
    renderer: Any | None = None,
) -> tuple[bool,set[str]]:
    attempt_id = begin_attempt(
        workspace,audit_id=audit_id,component=item.component,scope_key=item.scope_key,
        reprocess_id=reprocess_id,metadata={"temporal_mode":item.temporal_mode},
    )
    try:
        if item.component == DISCOVERY_ACQUISITION:
            success,code,affected = _recover_discovery(workspace,audit_id,item,reprocess_id)
        elif item.component == HTTP_ACQUISITION:
            success,code,affected = _recover_http(workspace,audit_id,item,reprocess_id)
        elif item.component == RENDER_CAPTURE:
            if renderer is None:
                raise RuntimeError("renderer session is required")
            success,code,affected = _recover_render(workspace,audit_id,item,reprocess_id,renderer)
        elif item.component == CONTENT_EXTRACTION:
            success,code,affected = _recover_extraction(workspace,audit_id,item,reprocess_id)
        else:
            success,code,affected = False,"UNSUPPORTED_CORE_COMPONENT",set()
    except Exception as exc:
        finish_attempt(
            workspace,attempt_id,status=FAILED_RETRYABLE,error_class=type(exc).__name__,
            error_code="CORE_RECOVERY_EXCEPTION",error_message=str(exc),retryable=True,
        )
        return False,set()
    if success:
        finish_attempt(
            workspace,attempt_id,status=SUCCESS,result_ref=f"{item.component.casefold()}:{item.scope_key}:effective",
            metadata={"result_code":code},retryable=True,
        )
        return True,affected
    finish_attempt(
        workspace,attempt_id,status=WAITING_FOR_DATA if code == "EXTRACTION_SOURCE_UNAVAILABLE" else FAILED_RETRYABLE,
        error_class="CORE_RECOVERY",error_code=code,
        error_message=f"selective recovery did not satisfy {item.component}/{item.scope_key}",retryable=True,
    )
    return False,set()


def _recompute_deterministic_snapshot(
    workspace: AuditWorkspace,
    audit_id: str,
    snapshot_id: str,
    reprocess_id: str,
) -> None:
    """Refresh deterministic page/snapshot rules from current effective evidence."""
    from rasai import m5, m6
    from rasai.javascript_spa import JavascriptSpaAnalyzer
    from rasai.rules import DependencyResolver, RuleEvaluation, baseline_registry
    from rasai.spa_persistence import SnapshotArchitectureWriter

    row = _snapshot_row(workspace,audit_id,snapshot_id)
    if row is None:
        return
    page_id = str(row["page_id"])
    acquisition = _load_acquisition(workspace,page_id)
    if acquisition is None:
        return
    _archive_rule_scope(workspace,audit_id=audit_id,reprocess_id=reprocess_id,rule_ids=("BR-GEO-006","BR-GEO-008","BR-GEO-009"),page_id=page_id)
    _archive_rule_scope(workspace,audit_id=audit_id,reprocess_id=reprocess_id,rule_ids=tuple(f"BR-GEO-{value:03d}" for value in range(10,17)),snapshot_id=snapshot_id)
    _archive_rule_scope(workspace,audit_id=audit_id,reprocess_id=reprocess_id,rule_ids=tuple(f"BR-GEO-{value:03d}" for value in range(19,25)),snapshot_id=snapshot_id)

    connection = sqlite3.connect(workspace.database)
    connection.row_factory = sqlite3.Row
    try:
        pages = tuple(connection.execute("SELECT page_id,normalized_url FROM pages WHERE audit_id=?",(audit_id,)).fetchall())
        target = connection.execute("SELECT normalized_origin FROM audit_targets WHERE audit_id=? ORDER BY rowid LIMIT 1",(audit_id,)).fetchone()
        execution_ids = tuple(str(entry[0]) for entry in connection.execute(
            "SELECT rule_execution_id FROM rule_executions WHERE audit_id=? ORDER BY executed_at,rowid",(audit_id,)
        ).fetchall())
    finally:
        connection.close()
    acquisitions: dict[str,HttpAcquisitionResult] = {}
    for page in pages:
        loaded = _load_acquisition(workspace,str(page["page_id"]))
        if loaded is not None:
            acquisitions[str(page["normalized_url"])] = loaded
    m2_view = SimpleNamespace(discovery=SimpleNamespace(page_acquisitions=acquisitions,origin=str(target[0]) if target else ""))
    registry = baseline_registry()
    resolver = DependencyResolver()
    with AuditPersistence(workspace) as persistence:
        state = m5._ExecutionState.create()
        for execution_id in execution_ids:
            execution = persistence.rule_executions.get(execution_id)
            if execution is not None:
                state.put(execution)
        manager = EvidenceManager(persistence)
        for rule_id,evaluation in (
            ("BR-GEO-006",m5._evaluate_final_response(acquisition)),
            ("BR-GEO-008",m5._evaluate_redirect_materiality(acquisition)),
            ("BR-GEO-009",m5._evaluate_analyzable_html(acquisition)),
        ):
            execution = m5._execute_new(
                definition=registry.get(rule_id),evaluation=evaluation,audit_id=audit_id,page_id=page_id,
                snapshot_id=None,device=None,manager=manager,persistence=persistence,resolver=resolver,state=state,
            )
            m5._persist_finding_if_needed(registry.get(rule_id),execution,persistence)
        snapshot = persistence.snapshots.get(snapshot_id)
        if snapshot is None:
            return
        for rule_id,evaluation in (
            ("BR-GEO-010",m5._evaluate_rendering(snapshot_id=snapshot_id,render_failed=False,extraction_failure=None,main_content_ref=snapshot.main_content_ref)),
            ("BR-GEO-011",m5._evaluate_index_directives(acquisition,snapshot.meta_robots)),
            ("BR-GEO-012",m5._evaluate_noindex(acquisition,snapshot.meta_robots)),
            ("BR-GEO-013",m5._evaluate_canonical(snapshot,workspace)),
            ("BR-GEO-014",m5._evaluate_canonical_target(snapshot,m2_view)),
            ("BR-GEO-015",m5._evaluate_raw_rendered_indexability(snapshot,workspace)),
            ("BR-GEO-016",m5._evaluate_soft404(snapshot,acquisition,workspace)),
        ):
            execution = m5._execute_new(
                definition=registry.get(rule_id),evaluation=evaluation,audit_id=audit_id,page_id=page_id,
                snapshot_id=snapshot_id,device=snapshot.device,manager=manager,persistence=persistence,resolver=resolver,state=state,
            )
            m5._persist_finding_if_needed(registry.get(rule_id),execution,persistence)

    with AuditPersistence(workspace) as persistence:
        snapshot = persistence.snapshots.get(snapshot_id)
        if snapshot is None:
            return
        raw_html = _read_bytes(workspace,snapshot.raw_artifact_ref).decode("utf-8",errors="replace") if _file_exists(workspace,snapshot.raw_artifact_ref) else None
        rendered_html = _read_bytes(workspace,snapshot.rendered_artifact_ref).decode("utf-8",errors="replace") if _file_exists(workspace,snapshot.rendered_artifact_ref) else None
        analyzer = JavascriptSpaAnalyzer()
        comparison = analyzer.compare(raw_html,rendered_html) if raw_html is not None and rendered_html is not None else None
        classification = comparison.architecture if comparison is not None else snapshot.architecture_classification
        SnapshotArchitectureWriter(workspace).update(snapshot_id,classification)
        evaluations: dict[str,Any] = {
            "BR-GEO-019":m6._evaluate_019(comparison),
            "BR-GEO-020":m6._evaluate_020(comparison),
            "BR-GEO-021":m6._evaluate_021(classification,acquisition,rendered_html),
            "BR-GEO-022":m6._evaluate_022(analyzer,rendered_html,snapshot.final_url or snapshot.requested_url,str(target[0]) if target else ""),
            "BR-GEO-023":m6._evaluate_023(analyzer,rendered_html,acquisition.status),
        }
        if rendered_html is None:
            evaluations["BR-GEO-024"] = m6._unknown("RENDERED_UNAVAILABLE","lazy-loaded essential content remains recoverable")
        else:
            preliminary = analyzer.lazy_loading(rendered_html,after_probe_html=None)
            same_session = snapshot.browser_metadata.get("bounded_lazy_probe") if isinstance(snapshot.browser_metadata,dict) else None
            if not preliminary.has_lazy_signals or preliminary.initial_content_recoverable:
                evaluations["BR-GEO-024"] = m6._evaluate_024(analyzer,rendered_html,None)
            elif isinstance(same_session,dict) and same_session.get("attempted"):
                evaluations["BR-GEO-024"] = m6._evaluate_024_same_session(preliminary,same_session)
            else:
                evaluations["BR-GEO-024"] = m6._unknown("LAZY_PROBE_UNAVAILABLE_NO_REFETCH","lazy-loaded essential content remains recoverable")
        connection = sqlite3.connect(workspace.database)
        try:
            prior_ids = tuple(str(entry[0]) for entry in connection.execute(
                "SELECT rule_execution_id FROM rule_executions WHERE audit_id=? ORDER BY executed_at,rowid",(audit_id,)
            ).fetchall())
        finally:
            connection.close()
        prior = m6._PriorState(persistence,prior_ids)
        resolver = DependencyResolver()
        manager = EvidenceManager(persistence)
        for definition in m6._M6_DEFINITIONS:
            dependency = resolver.resolve(definition,lambda dep,p=page_id,s=snapshot_id: prior.lookup(dep,page_id=p,snapshot_id=s))
            evaluation = evaluations[definition.rule_id]
            if not dependency.applicable:
                evaluation = RuleEvaluation(
                    result=dependency.result or RuleResult.UNKNOWN,observed_value={"dependency_reason":dependency.reason},
                    expected_condition=evaluation.expected_condition,reason=dependency.reason,
                )
            execution = m6._persist_execution(
                definition,evaluation,audit_id=audit_id,page_id=page_id,snapshot_id=snapshot_id,
                device=snapshot.device,manager=manager,persistence=persistence,
            )
            m6._persist_finding(definition,execution,persistence)


def _invalidate_core_dependents(workspace: AuditWorkspace, audit_id: str) -> bool:
    """Reopen only derived work whose effective inputs changed after core recovery."""
    from rasai.governed_fulfillment_invalidation import invalidate_work_item

    return invalidate_work_item(
        workspace,
        audit_id=audit_id,
        component="PASSIVE_SECURITY",
        error_class="EVIDENCE_DEPENDENCY",
        error_code="PASSIVE_SECURITY_INPUT_CHANGED",
        error_message=(
            "CAT-10 invalidado seletivamente porque HTTP/render/conteúdo persistido "
            "que alimenta sua análise foi recuperado"
        ),
    )


def _wrap_reprocess(original: Any, module: Any):
    if getattr(original,"_rasai_core_reprocessing",False):
        return original

    def reprocess_with_core(audit_id: str, *, audits_root: str | Path = "audits", source: str = "CLI"):
        workspace = AuditWorkspace.open(Path(audits_root) / audit_id)
        module._backfill_contract(workspace,audit_id)
        synchronize_core_work_items(workspace,audit_id)
        core_unresolved = _core_unresolved(workspace,audit_id)
        if not core_unresolved:
            return original(audit_id,audits_root=audits_root,source=source)

        initial_items = list_work_items(workspace,audit_id)
        skipped_success = sum(item.required and item.status == SUCCESS for item in initial_items)
        unresolved_initial = tuple(
            item
            for item in initial_items
            if item.required and item.status not in _RESOLVED_STATES
        )
        selected_count, unselected_count = selected_counts(unresolved_initial)
        reprocess_id = start_reprocess_run(workspace,audit_id,source=source,note="selective core prerequisite recovery")
        attempted = 0
        successful = 0
        affected: set[str] = set()

        for item in tuple(value for value in _retryable_core(workspace,audit_id) if value.component == DISCOVERY_ACQUISITION):
            attempted += 1
            ok,changed = _attempt(workspace,audit_id,item,reprocess_id)
            successful += int(ok)
            affected.update(changed)
        synchronize_core_work_items(workspace,audit_id)

        for item in tuple(value for value in _retryable_core(workspace,audit_id) if value.component == HTTP_ACQUISITION):
            attempted += 1
            ok,changed = _attempt(workspace,audit_id,item,reprocess_id)
            successful += int(ok)
            affected.update(changed)
        synchronize_core_work_items(workspace,audit_id)

        render_items = tuple(value for value in _retryable_core(workspace,audit_id) if value.component == RENDER_CAPTURE)
        if render_items:
            from rasai import m3
            with m3.BrowserIdentityRenderer() as renderer:
                for item in render_items:
                    attempted += 1
                    ok,changed = _attempt(workspace,audit_id,item,reprocess_id,renderer=renderer)
                    successful += int(ok)
                    affected.update(changed)
        synchronize_core_work_items(workspace,audit_id)

        for item in tuple(value for value in _retryable_core(workspace,audit_id) if value.component == CONTENT_EXTRACTION):
            attempted += 1
            ok,changed = _attempt(workspace,audit_id,item,reprocess_id)
            successful += int(ok)
            affected.update(changed)
        synchronize_core_work_items(workspace,audit_id)

        for snapshot_id in sorted(affected):
            _recompute_deterministic_snapshot(workspace,audit_id,snapshot_id,reprocess_id)
        if affected:
            _invalidate_core_dependents(workspace, audit_id)
            from rasai.reprocess_ai import recompute_derived_after_ai
            recompute_derived_after_ai(
                workspace=workspace,audit_id=audit_id,reprocess_id=reprocess_id,semantic_changed=False,
            )

        original_start = module.start_reprocess_run
        original_finish = module.finish_reprocess_run
        original_latest = module._latest_pending
        def reuse_start(*args: Any, **kwargs: Any) -> str:
            return reprocess_id
        def defer_finish(*args: Any, **kwargs: Any):
            return recalculate(workspace,audit_id)
        def filtered_latest(active_workspace: AuditWorkspace, active_audit_id: str):
            # Core work already evaluated by this wrapper is removed from the
            # downstream list. AI dependency gating is task-specific in
            # audit_reprocess._block_ai_when_prerequisites_incomplete; do not block
            # unrelated AI merely because another core item is unresolved.
            return tuple(
                item for item in original_latest(active_workspace,active_audit_id)
                if item.component not in CORE_COMPONENTS
            )
        module.start_reprocess_run = reuse_start
        module.finish_reprocess_run = defer_finish
        module._latest_pending = filtered_latest
        try:
            downstream = original(audit_id,audits_root=audits_root,source=source)
        finally:
            module.start_reprocess_run = original_start
            module.finish_reprocess_run = original_finish
            module._latest_pending = original_latest

        attempted += int(getattr(downstream,"attempted_items",0) or 0)
        successful += int(getattr(downstream,"successful_items",0) or 0)
        summary = recalculate(workspace,audit_id)
        summary = finish_reprocess_run(
            workspace,reprocess_id,status=SUCCESS,
            attempted_items=attempted,successful_items=successful,
            note=(
                "RPR concluído; todos os requisitos da AUD foram satisfeitos"
                if summary.processing_status == "COMPLETE"
                else "RPR concluído; a AUD permanece com requisitos não resolvidos"
            ),
        )
        summary = project_report_validity(audit_id=audit_id,workspace=workspace)
        # The outer core wrapper owns this RPR. Only now, after its ledger is final,
        # may report-catalog snapshot the audit without becoming stale immediately.
        from rasai.report_completion import materialize_catalog_report_projection
        materialize_catalog_report_projection(audit_id=audit_id,workspace=workspace)
        return module.ReprocessResult(
            audit_id=audit_id,reprocess_id=reprocess_id,processing_status=summary.processing_status,
            score_status=summary.score_status,report_status=summary.report_status,
            consolidation_eligible=summary.consolidation_eligible,attempted_items=attempted,successful_items=successful,
            skipped_success_items=skipped_success,remaining_items=summary.pending_items+summary.blocked_items,
            temporal_expired_items=summary.expired_items,report_root=workspace.root / "report-catalog",
            selected_items=selected_count,unselected_items=unselected_count,
            ai_used=bool(getattr(downstream,"ai_used",False)),
        )

    reprocess_with_core._rasai_core_reprocessing = True
    reprocess_with_core._rasai_original = original
    return reprocess_with_core


def _wrap_finalizer(original: Any):
    if getattr(original,"_rasai_core_reprocessing",False):
        return original
    def finalize_with_core(*args: Any, **kwargs: Any):
        result = original(*args,**kwargs)
        audit_id = str(kwargs.get("audit_id") or (args[0] if args else ""))
        workspace = kwargs.get("workspace")
        if audit_id and workspace is not None:
            synchronize_core_work_items(workspace,audit_id)
            project_report_validity(audit_id=audit_id,workspace=workspace)
        return result
    finalize_with_core._rasai_core_reprocessing = True
    finalize_with_core._rasai_original = original
    return finalize_with_core


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    from rasai import audit_reprocess, report_completion
    report_completion.finalize_audit_report_site = _wrap_finalizer(report_completion.finalize_audit_report_site)
    audit_reprocess.reprocess_audit = _wrap_reprocess(audit_reprocess.reprocess_audit,audit_reprocess)
    _INSTALLED = True
