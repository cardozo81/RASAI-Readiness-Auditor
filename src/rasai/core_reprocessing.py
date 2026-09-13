"""Selective recovery of core evidence that precedes AI and derived analysis.

The fulfillment contract treats acquisition, browser capture and deterministic extraction
as explicit requirements.  Recovery never reruns a successful requirement.  Live
recollection stays inside the AUD validity window, while extraction replays persisted
artifacts without network access.  AI remains ineligible while any core evidence
requirement is unresolved.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from types import SimpleNamespace
from typing import Any

from rasai.acquisition import HttpAcquisitionResult, HttpClient, NetworkError, NetworkErrorKind, RedirectHop
from rasai.audit_fulfillment import (
    DISABLED,
    FAILED_RETRYABLE,
    LIVE_RECOLLECTION,
    NOT_APPLICABLE,
    REPLAY_SAFE,
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
from rasai.domain import DeviceContext, Evidence, EvidenceType, RuleExecution, RuleResult, new_id, utc_now
from rasai.evidence import EvidenceManager
from rasai.persistence import AuditPersistence, AuditWorkspace

HTTP_ACQUISITION = "HTTP_ACQUISITION"
RENDER_CAPTURE = "RENDER_CAPTURE"
CONTENT_EXTRACTION = "CONTENT_EXTRACTION"
CORE_COMPONENTS = frozenset({HTTP_ACQUISITION, RENDER_CAPTURE, CONTENT_EXTRACTION})
_AI_COMPONENTS = frozenset({"SEMANTIC_AI", "TECHNICAL_AI", "CONTENT_REMEDIATION_AI"})
_REDIRECT_FAILURES = {"REDIRECT_LOOP", "TOO_MANY_REDIRECTS", "INVALID_REDIRECT"}
_INSTALLED = False


def _parse_json(raw: Any, default: Any) -> Any:
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


def _is_expired(item: WorkItem) -> bool:
    if item.temporal_mode != LIVE_RECOLLECTION or item.status == SUCCESS:
        return False
    deadline = _parse_time(item.valid_until)
    return bool(deadline and datetime.now(timezone.utc) > deadline)


def _table_exists(connection: sqlite3.Connection, name: str) -> bool:
    return connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1", (name,)
    ).fetchone() is not None


def _file_exists(workspace: AuditWorkspace, reference: str | None) -> bool:
    return bool(reference and (workspace.root / str(reference)).is_file())


def _text_exists(workspace: AuditWorkspace, reference: str | None) -> bool:
    if not _file_exists(workspace, reference):
        return False
    return bool((workspace.root / str(reference)).read_text(encoding="utf-8", errors="replace").strip())


def _latest_rule_result(connection: sqlite3.Connection, audit_id: str, rule_id: str, *, page_id: str | None = None, snapshot_id: str | None = None) -> str | None:
    clauses = ["audit_id=?", "rule_id=?"]
    params: list[Any] = [audit_id, rule_id]
    if page_id is not None:
        clauses.append("page_id=?")
        params.append(page_id)
    if snapshot_id is not None:
        clauses.append("snapshot_id=?")
        params.append(snapshot_id)
    row = connection.execute(
        f"SELECT result FROM rule_executions WHERE {' AND '.join(clauses)} ORDER BY executed_at DESC,rowid DESC LIMIT 1",
        tuple(params),
    ).fetchone()
    return str(row[0]) if row else None


def synchronize_core_work_items(workspace: AuditWorkspace, audit_id: str) -> None:
    """Materialize current core-evidence requirements from persisted AUD state."""
    connection = sqlite3.connect(workspace.database)
    connection.row_factory = sqlite3.Row
    try:
        audit = connection.execute("SELECT started_at,created_at FROM audits WHERE audit_id=?", (audit_id,)).fetchone()
        if audit is None:
            raise ValueError(f"audit_id not found in audit.db: {audit_id}")
        audit_time = str(audit["started_at"] or audit["created_at"] or "") or None
        pages = connection.execute(
            "SELECT page_id,normalized_url FROM pages WHERE audit_id=? ORDER BY depth,page_id", (audit_id,)
        ).fetchall()
        for page in pages:
            page_id = str(page["page_id"])
            url = str(page["normalized_url"])
            http_ok = _latest_rule_result(connection, audit_id, "BR-GEO-005", page_id=page_id) == RuleResult.PASS.value
            register_work_item(
                workspace,
                audit_id=audit_id,
                component=HTTP_ACQUISITION,
                scope_key=page_id,
                required=True,
                temporal_mode=LIVE_RECOLLECTION,
                status=SUCCESS if http_ok else FAILED_RETRYABLE,
                retryable=True,
                source_captured_at=audit_time,
                configuration={"url": url, "page_id": page_id},
            )
            if http_ok:
                set_work_item_status(
                    workspace,audit_id=audit_id,component=HTTP_ACQUISITION,scope_key=page_id,
                    status=SUCCESS,result_ref=f"http:{page_id}:effective",retryable=True,
                )
            else:
                set_work_item_status(
                    workspace,audit_id=audit_id,component=HTTP_ACQUISITION,scope_key=page_id,
                    status=FAILED_RETRYABLE,error_class="ACQUISITION",error_code="HTTP_ACQUISITION_INCOMPLETE",
                    error_message="no effective retrievable HTTP acquisition is persisted for this page",retryable=True,
                )

        snapshots = connection.execute(
            """SELECT ps.*,p.audit_id FROM page_snapshots ps JOIN pages p ON p.page_id=ps.page_id
               WHERE p.audit_id=? ORDER BY ps.captured_at,ps.snapshot_id""", (audit_id,)
        ).fetchall()
        for snapshot in snapshots:
            snapshot_id = str(snapshot["snapshot_id"])
            page_id = str(snapshot["page_id"])
            device = str(snapshot["device"])
            metadata = _parse_json(snapshot["browser_metadata"], {})
            render_ok = bool(metadata.get("render_succeeded")) and _file_exists(workspace, snapshot["rendered_artifact_ref"])
            register_work_item(
                workspace,
                audit_id=audit_id,
                component=RENDER_CAPTURE,
                scope_key=snapshot_id,
                required=True,
                temporal_mode=LIVE_RECOLLECTION,
                status=SUCCESS if render_ok else FAILED_RETRYABLE,
                retryable=True,
                source_captured_at=str(snapshot["captured_at"] or audit_time or "") or None,
                configuration={
                    "page_id": page_id,
                    "device": device,
                    "url": str(snapshot["requested_url"]),
                },
            )
            if render_ok:
                set_work_item_status(
                    workspace,audit_id=audit_id,component=RENDER_CAPTURE,scope_key=snapshot_id,
                    status=SUCCESS,result_ref=str(snapshot["rendered_artifact_ref"]),retryable=True,
                )
            else:
                set_work_item_status(
                    workspace,audit_id=audit_id,component=RENDER_CAPTURE,scope_key=snapshot_id,
                    status=FAILED_RETRYABLE,error_class="RENDER",error_code="RENDER_CAPTURE_INCOMPLETE",
                    error_message="rendered document was not captured successfully",retryable=True,
                )

            evidence_ok = bool(connection.execute(
                """SELECT 1 FROM evidence WHERE audit_id=? AND snapshot_id=?
                   AND source IN ('RENDERED_DOM','RAW_HTML_FALLBACK') LIMIT 1""",
                (audit_id, snapshot_id),
            ).fetchone())
            source_available = _file_exists(workspace, snapshot["rendered_artifact_ref"]) or _file_exists(workspace, snapshot["raw_artifact_ref"])
            extraction_status = SUCCESS if evidence_ok else (FAILED_RETRYABLE if source_available else WAITING_FOR_DATA)
            register_work_item(
                workspace,
                audit_id=audit_id,
                component=CONTENT_EXTRACTION,
                scope_key=snapshot_id,
                required=True,
                temporal_mode=REPLAY_SAFE,
                status=extraction_status,
                retryable=True,
                source_captured_at=str(snapshot["captured_at"] or audit_time or "") or None,
                configuration={"page_id": page_id, "device": device},
            )
            if evidence_ok:
                set_work_item_status(
                    workspace,audit_id=audit_id,component=CONTENT_EXTRACTION,scope_key=snapshot_id,
                    status=SUCCESS,result_ref=f"extraction:{snapshot_id}:effective",retryable=True,
                )
            elif source_available:
                set_work_item_status(
                    workspace,audit_id=audit_id,component=CONTENT_EXTRACTION,scope_key=snapshot_id,
                    status=FAILED_RETRYABLE,error_class="EXTRACTION",error_code="EXTRACTION_INCOMPLETE",
                    error_message="persisted source exists but deterministic extraction is incomplete",retryable=True,
                )
            else:
                set_work_item_status(
                    workspace,audit_id=audit_id,component=CONTENT_EXTRACTION,scope_key=snapshot_id,
                    status=WAITING_FOR_DATA,error_class="PREREQUISITE",error_code="EXTRACTION_SOURCE_UNAVAILABLE",
                    error_message="extraction waits for a persisted RAW or rendered document",retryable=True,
                )
    finally:
        connection.close()
    recalculate(workspace, audit_id)


def _archive_rule_scope(workspace: AuditWorkspace, *, audit_id: str, reprocess_id: str, component: str, rule_ids: tuple[str, ...], page_id: str | None = None, snapshot_id: str | None = None) -> None:
    if not rule_ids:
        return
    marks = ",".join("?" for _ in rule_ids)
    clauses = ["audit_id=?", f"rule_id IN ({marks})"]
    params: list[Any] = [audit_id, *rule_ids]
    if page_id is not None:
        clauses.append("page_id=?")
        params.append(page_id)
    if snapshot_id is not None:
        clauses.append("snapshot_id=?")
        params.append(snapshot_id)
    connection = sqlite3.connect(workspace.database)
    connection.row_factory = sqlite3.Row
    try:
        rows = tuple(dict(row) for row in connection.execute(
            f"SELECT * FROM rule_executions WHERE {' AND '.join(clauses)}", tuple(params)
        ).fetchall())
        ids = tuple(str(row["rule_execution_id"]) for row in rows)
        finding_rows: tuple[dict[str, Any], ...] = ()
        if ids:
            id_marks = ",".join("?" for _ in ids)
            finding_rows = tuple(dict(row) for row in connection.execute(
                f"SELECT * FROM findings WHERE rule_execution_id IN ({id_marks})", ids
            ).fetchall())
    finally:
        connection.close()
    if rows:
        archive_rows(
            workspace,audit_id=audit_id,reprocess_id=reprocess_id,component=component,
            entity_type="rule_execution",id_field="rule_execution_id",rows=rows,
        )
    if finding_rows:
        archive_rows(
            workspace,audit_id=audit_id,reprocess_id=reprocess_id,component=component,
            entity_type="finding",id_field="finding_id",rows=finding_rows,
        )
    if not rows:
        return
    connection = sqlite3.connect(workspace.database)
    connection.execute("PRAGMA foreign_keys=ON")
    try:
        with connection:
            id_marks = ",".join("?" for _ in ids)
            connection.execute(f"DELETE FROM findings WHERE rule_execution_id IN ({id_marks})", ids)
            connection.execute(f"DELETE FROM rule_executions WHERE rule_execution_id IN ({id_marks})", ids)
    finally:
        connection.close()


def _write_reprocess_artifact(workspace: AuditWorkspace, reprocess_id: str, family: str, name: str, payload: bytes) -> str | None:
    if not payload:
        return None
    directory = workspace.artifacts / "reprocess" / reprocess_id / family
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_bytes(payload)
    return path.relative_to(workspace.root).as_posix()


def _read_bytes(workspace: AuditWorkspace, reference: str | None) -> bytes:
    if not _file_exists(workspace, reference):
        return b""
    return (workspace.root / str(reference)).read_bytes()


def _load_acquisition(workspace: AuditWorkspace, page_id: str) -> HttpAcquisitionResult | None:
    connection = sqlite3.connect(workspace.database)
    connection.row_factory = sqlite3.Row
    try:
        row = connection.execute(
            """SELECT observed_value,artifact_reference FROM evidence
               WHERE page_id=? AND evidence_type=? AND source='http'
               ORDER BY captured_at DESC,rowid DESC LIMIT 1""",
            (page_id, EvidenceType.HTTP_RESPONSE.value),
        ).fetchone()
    finally:
        connection.close()
    if row is None:
        return None
    observed = _parse_json(row["observed_value"], {})
    redirects = tuple(
        RedirectHop(
            status=int(item.get("status") or 0),
            source_url=str(item.get("source_url") or ""),
            location=str(item.get("location") or ""),
            target_url=str(item.get("target_url") or ""),
        )
        for item in observed.get("redirect_chain", ())
        if isinstance(item, dict)
    )
    raw_error = observed.get("network_error")
    network_error = None
    if isinstance(raw_error, dict) and raw_error.get("kind"):
        try:
            kind = NetworkErrorKind(str(raw_error["kind"]))
        except ValueError:
            kind = NetworkErrorKind.UNKNOWN
        network_error = NetworkError(kind, str(raw_error.get("message") or ""))
    return HttpAcquisitionResult(
        requested_url=str(observed.get("requested_url") or ""),
        final_url=(str(observed.get("final_url")) if observed.get("final_url") else None),
        status=(int(observed["status"]) if observed.get("status") is not None else None),
        headers=tuple((str(k), str(v)) for k, v in observed.get("headers", ()) if isinstance(k, str)),
        body=_read_bytes(workspace, row["artifact_reference"]),
        redirects=redirects,
        network_error=network_error,
        elapsed_ms=int(observed.get("elapsed_ms") or 0),
    )


def _replace_http_rules(workspace: AuditWorkspace, *, audit_id: str, page_id: str, acquisition: HttpAcquisitionResult, evidence_ids: tuple[str, ...], reprocess_id: str) -> None:
    _archive_rule_scope(
        workspace,audit_id=audit_id,reprocess_id=reprocess_id,component=HTTP_ACQUISITION,
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
        RuleExecution(
            new_id("REX"),audit_id,"BR-GEO-004","1",page_id,None,None,RuleResult.PASS,
            {"requested_url":acquisition.requested_url,"final_url":acquisition.final_url,"status":acquisition.status,
             "network_error":error_kind,"body_preserved":bool(acquisition.body)},
            "HTTP acquisition result and body artifact are preserved when available",evidence_ids,utc_now(),
        ),
        RuleExecution(
            new_id("REX"),audit_id,"BR-GEO-005","1",page_id,None,None,
            RuleResult.PASS if retrievable else RuleResult.FAIL,
            {"status":acquisition.status,"network_error":error_kind},
            "page yields a technical HTTP response without DNS/TLS/connection/timeout failure",evidence_ids,utc_now(),
        ),
        RuleExecution(
            new_id("REX"),audit_id,"BR-GEO-007","1",page_id,None,None,redirect_result,
            {"redirects":[{"status":hop.status,"source_url":hop.source_url,"location":hop.location,"target_url":hop.target_url} for hop in acquisition.redirects],
             "network_error":error_kind},
            "redirect chain resolves without loops or invalid hops",evidence_ids,utc_now(),
        ),
    )
    with AuditPersistence(workspace) as persistence:
        for execution in executions:
            persistence.rule_executions.add(execution)


def _recover_http(workspace: AuditWorkspace, audit_id: str, item: WorkItem, reprocess_id: str) -> tuple[bool, str]:
    url = str(item.configuration.get("url") or "").strip()
    page_id = item.scope_key
    if not url:
        connection = sqlite3.connect(workspace.database)
        try:
            row = connection.execute("SELECT normalized_url FROM pages WHERE page_id=? AND audit_id=?", (page_id,audit_id)).fetchone()
        finally:
            connection.close()
        url = str(row[0]) if row else ""
    if not url:
        return False, "PAGE_URL_UNAVAILABLE"
    acquisition = HttpClient().acquire(url)
    artifact_ref = _write_reprocess_artifact(workspace,reprocess_id,"http",f"{page_id}.response",acquisition.body)
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
            header = Evidence(
                new_id("EV-GEO"),audit_id,page_id,None,None,EvidenceType.HTTP_HEADER,"http",
                {"headers":[list(value) for value in acquisition.headers]},None,utc_now(),
            )
            persistence.evidence.add(header)
            evidence_ids.append(header.evidence_id)
    if artifact_ref:
        connection = sqlite3.connect(workspace.database)
        try:
            with connection:
                connection.execute("UPDATE page_snapshots SET raw_artifact_ref=? WHERE page_id=?", (artifact_ref,page_id))
        finally:
            connection.close()
    _replace_http_rules(
        workspace,audit_id=audit_id,page_id=page_id,acquisition=acquisition,
        evidence_ids=tuple(evidence_ids),reprocess_id=reprocess_id,
    )
    success = acquisition.network_error is None and acquisition.status is not None
    code = "HTTP_ACQUISITION_RECOVERED" if success else (
        acquisition.network_error.kind.value if acquisition.network_error else "HTTP_RESPONSE_UNAVAILABLE"
    )
    return success, code


def _snapshot_row(workspace: AuditWorkspace, audit_id: str, snapshot_id: str) -> sqlite3.Row | None:
    connection = sqlite3.connect(workspace.database)
    connection.row_factory = sqlite3.Row
    try:
        return connection.execute(
            """SELECT ps.*,p.audit_id FROM page_snapshots ps JOIN pages p ON p.page_id=ps.page_id
               WHERE ps.snapshot_id=? AND p.audit_id=?""", (snapshot_id,audit_id)
        ).fetchone()
    finally:
        connection.close()


def _archive_snapshot(workspace: AuditWorkspace, *, audit_id: str, snapshot_id: str, reprocess_id: str, component: str) -> None:
    row = _snapshot_row(workspace,audit_id,snapshot_id)
    if row is None:
        return
    archive_rows(
        workspace,audit_id=audit_id,reprocess_id=reprocess_id,component=component,
        entity_type="page_snapshot",id_field="snapshot_id",rows=(dict(row),),
    )


def _recover_render(workspace: AuditWorkspace, audit_id: str, item: WorkItem, reprocess_id: str, renderer: Any) -> tuple[bool, str]:
    snapshot_id = item.scope_key
    row = _snapshot_row(workspace,audit_id,snapshot_id)
    if row is None:
        return False, "SNAPSHOT_NOT_FOUND"
    device = DeviceContext(str(row["device"]))
    url = str(row["requested_url"])
    trace = []
    acquisition = _load_acquisition(workspace, str(row["page_id"]))
    if acquisition is not None:
        trace = [{"url":hop.source_url,"status":hop.status,"location":hop.location} for hop in acquisition.redirects]
    try:
        result = renderer.render(url, device, preflight_navigation_trace=trace)
    except TypeError:
        result = renderer.render(url, device)
    if result.error_kind is not None or not result.rendered_html:
        return False, getattr(result.error_kind, "value", None) or "RENDERED_DOCUMENT_UNAVAILABLE"
    _archive_snapshot(
        workspace,audit_id=audit_id,snapshot_id=snapshot_id,reprocess_id=reprocess_id,component=RENDER_CAPTURE,
    )
    rendered_ref = _write_reprocess_artifact(
        workspace,reprocess_id,"rendered",f"{snapshot_id}.html",result.rendered_html.encode("utf-8")
    )
    visual_ref = _write_reprocess_artifact(
        workspace,reprocess_id,"visual",f"{snapshot_id}.png",result.screenshot_png or b""
    )
    metadata = _parse_json(row["browser_metadata"], {})
    metadata.update(dict(result.browser_metadata or {}))
    metadata["render_succeeded"] = True
    metadata["visual_artifact_ref"] = visual_ref
    metadata["reprocess"] = {"reprocess_id":reprocess_id,"captured_at":utc_now().isoformat()}
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
    if visual_ref:
        with AuditPersistence(workspace) as persistence:
            persistence.evidence.add(Evidence(
                new_id("EV-GEO"),audit_id,str(row["page_id"]),snapshot_id,device,EvidenceType.VISUAL_SNAPSHOT,
                "chromium:reprocess",{"artifact_reference":visual_ref,"requested_url":url,"final_url":result.final_url or row["final_url"]},
                visual_ref,utc_now(),
            ))
    return True, "RENDER_CAPTURE_RECOVERED"


def _recover_extraction(workspace: AuditWorkspace, audit_id: str, item: WorkItem, reprocess_id: str) -> tuple[bool, str]:
    from rasai.m3 import M3ExecutionResult
    from rasai.m4 import execute_m4

    snapshot_id = item.scope_key
    row = _snapshot_row(workspace,audit_id,snapshot_id)
    if row is None:
        return False, "SNAPSHOT_NOT_FOUND"
    if not (_file_exists(workspace,row["rendered_artifact_ref"]) or _file_exists(workspace,row["raw_artifact_ref"])):
        return False, "EXTRACTION_SOURCE_UNAVAILABLE"
    _archive_snapshot(
        workspace,audit_id=audit_id,snapshot_id=snapshot_id,reprocess_id=reprocess_id,component=CONTENT_EXTRACTION,
    )
    page_id = str(row["page_id"])
    device = DeviceContext(str(row["device"]))
    with AuditPersistence(workspace) as persistence:
        result = execute_m4(
            M3ExecutionResult(snapshot_ids={page_id:{device:snapshot_id}},failures=()),
            persistence,
            workspace,
        )
    failure = next((value for value in result.failures if value.snapshot_id == snapshot_id), None)
    if failure is not None:
        return False, failure.error_kind
    connection = sqlite3.connect(workspace.database)
    try:
        evidence_ok = bool(connection.execute(
            """SELECT 1 FROM evidence WHERE audit_id=? AND snapshot_id=?
               AND source IN ('RENDERED_DOM','RAW_HTML_FALLBACK') LIMIT 1""",
            (audit_id,snapshot_id),
        ).fetchone())
    finally:
        connection.close()
    return evidence_ok, "EXTRACTION_RECOVERED" if evidence_ok else "EXTRACTION_EVIDENCE_UNAVAILABLE"


def _all_acquisitions(workspace: AuditWorkspace, audit_id: str) -> tuple[dict[str, HttpAcquisitionResult], str]:
    connection = sqlite3.connect(workspace.database)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute("SELECT page_id,normalized_url FROM pages WHERE audit_id=?", (audit_id,)).fetchall()
        target = connection.execute("SELECT normalized_origin FROM audit_targets WHERE audit_id=? ORDER BY rowid LIMIT 1", (audit_id,)).fetchone()
    finally:
        connection.close()
    output: dict[str, HttpAcquisitionResult] = {}
    for row in rows:
        acquisition = _load_acquisition(workspace,str(row["page_id"]))
        if acquisition is not None:
            output[str(row["normalized_url"])] = acquisition
    return output, str(target[0]) if target else ""


def _current_rule_ids(workspace: AuditWorkspace, audit_id: str) -> tuple[str, ...]:
    connection = sqlite3.connect(workspace.database)
    try:
        rows = connection.execute(
            "SELECT rule_execution_id FROM rule_executions WHERE audit_id=? ORDER BY executed_at,rowid", (audit_id,)
        ).fetchall()
        return tuple(str(row[0]) for row in rows)
    finally:
        connection.close()


def _recompute_deterministic_for_snapshot(workspace: AuditWorkspace, audit_id: str, snapshot_id: str, reprocess_id: str) -> None:
    from rasai import m5, m6
    from rasai.javascript_spa import JavascriptSpaAnalyzer
    from rasai.rules import DependencyResolver, baseline_registry
    from rasai.spa_persistence import SnapshotArchitectureWriter

    row = _snapshot_row(workspace,audit_id,snapshot_id)
    if row is None:
        return
    page_id = str(row["page_id"])
    acquisition = _load_acquisition(workspace,page_id)
    if acquisition is None:
        return
    _archive_rule_scope(
        workspace,audit_id=audit_id,reprocess_id=reprocess_id,component="CORE_DERIVED",
        rule_ids=("BR-GEO-006","BR-GEO-008","BR-GEO-009"),page_id=page_id,
    )
    _archive_rule_scope(
        workspace,audit_id=audit_id,reprocess_id=reprocess_id,component="CORE_DERIVED",
        rule_ids=tuple(f"BR-GEO-{value:03d}" for value in range(10,17)),snapshot_id=snapshot_id,
    )
    _archive_rule_scope(
        workspace,audit_id=audit_id,reprocess_id=reprocess_id,component="CORE_DERIVED",
        rule_ids=tuple(f"BR-GEO-{value:03d}" for value in range(19,25)),snapshot_id=snapshot_id,
    )

    acquisitions, origin = _all_acquisitions(workspace,audit_id)
    m2_view = SimpleNamespace(discovery=SimpleNamespace(page_acquisitions=acquisitions, origin=origin))
    registry = baseline_registry()
    resolver = DependencyResolver()
    with AuditPersistence(workspace) as persistence:
        state = m5._ExecutionState.create()
        for execution_id in _current_rule_ids(workspace,audit_id):
            execution = persistence.rule_executions.get(execution_id)
            if execution is not None:
                state.put(execution)
        manager = EvidenceManager(persistence)
        page_specs = (
            ("BR-GEO-006", m5._evaluate_final_response(acquisition)),
            ("BR-GEO-008", m5._evaluate_redirect_materiality(acquisition)),
            ("BR-GEO-009", m5._evaluate_analyzable_html(acquisition)),
        )
        for rule_id,evaluation in page_specs:
            execution = m5._execute_new(
                definition=registry.get(rule_id),evaluation=evaluation,audit_id=audit_id,page_id=page_id,
                snapshot_id=None,device=None,manager=manager,persistence=persistence,resolver=resolver,state=state,
            )
            m5._persist_finding_if_needed(registry.get(rule_id),execution,persistence)

        snapshot = persistence.snapshots.get(snapshot_id)
        if snapshot is None:
            return
        specs = (
            ("BR-GEO-010", m5._evaluate_rendering(snapshot_id=snapshot_id,render_failed=False,extraction_failure=None,main_content_ref=snapshot.main_content_ref)),
            ("BR-GEO-011", m5._evaluate_index_directives(acquisition,snapshot.meta_robots)),
            ("BR-GEO-012", m5._evaluate_noindex(acquisition,snapshot.meta_robots)),
            ("BR-GEO-013", m5._evaluate_canonical(snapshot,workspace)),
            ("BR-GEO-014", m5._evaluate_canonical_target(snapshot,m2_view)),
            ("BR-GEO-015", m5._evaluate_raw_rendered_indexability(snapshot,workspace)),
            ("BR-GEO-016", m5._evaluate_soft404(snapshot,acquisition,workspace)),
        )
        for rule_id,evaluation in specs:
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
            "BR-GEO-022":m6._evaluate_022(analyzer,rendered_html,snapshot.final_url or snapshot.requested_url,origin),
            "BR-GEO-023":m6._evaluate_023(analyzer,rendered_html,acquisition.status),
        }
        if rendered_html is None:
            evaluations["BR-GEO-024"] = m6._unknown("RENDERED_UNAVAILABLE","lazy-loaded essential content remains recoverable")
        else:
            preliminary = analyzer.lazy_loading(rendered_html,after_probe_html=None)
            if not preliminary.has_lazy_signals or preliminary.initial_content_recoverable:
                evaluations["BR-GEO-024"] = m6._evaluate_024(analyzer,rendered_html,None)
            else:
                same_session = snapshot.browser_metadata.get("bounded_lazy_probe") if isinstance(snapshot.browser_metadata,dict) else None
                if isinstance(same_session,dict) and same_session.get("attempted"):
                    evaluations["BR-GEO-024"] = m6._evaluate_024_same_session(preliminary,same_session)
                else:
                    evaluations["BR-GEO-024"] = m6._unknown("LAZY_PROBE_UNAVAILABLE_NO_REFETCH","lazy-loaded essential content remains recoverable")
        prior = m6._PriorState(persistence,_current_rule_ids(workspace,audit_id))
        resolver = DependencyResolver()
        manager = EvidenceManager(persistence)
        for definition in m6._M6_DEFINITIONS:
            dependency = resolver.resolve(
                definition,
                lambda dep,p=page_id,s=snapshot_id: prior.lookup(dep,page_id=p,snapshot_id=s),
            )
            evaluation = evaluations[definition.rule_id]
            if not dependency.applicable:
                from rasai.rules import RuleEvaluation
                evaluation = RuleEvaluation(
                    result=dependency.result or RuleResult.UNKNOWN,
                    observed_value={"dependency_reason":dependency.reason},
                    expected_condition=evaluation.expected_condition,
                    reason=dependency.reason,
                )
            execution = m6._persist_execution(
                definition,evaluation,audit_id=audit_id,page_id=page_id,snapshot_id=snapshot_id,
                device=snapshot.device,manager=manager,persistence=persistence,
            )
            m6._persist_finding(definition,execution,persistence)


def _attempt_core_item(workspace: AuditWorkspace, audit_id: str, item: WorkItem, reprocess_id: str, *, renderer: Any | None = None) -> bool:
    attempt_id = begin_attempt(
        workspace,audit_id=audit_id,component=item.component,scope_key=item.scope_key,
        reprocess_id=reprocess_id,metadata={"temporal_mode":item.temporal_mode},
    )
    try:
        if item.component == HTTP_ACQUISITION:
            success, code = _recover_http(workspace,audit_id,item,reprocess_id)
        elif item.component == RENDER_CAPTURE:
            if renderer is None:
                raise RuntimeError("renderer session is required for RENDER_CAPTURE recovery")
            success, code = _recover_render(workspace,audit_id,item,reprocess_id,renderer)
        elif item.component == CONTENT_EXTRACTION:
            success, code = _recover_extraction(workspace,audit_id,item,reprocess_id)
        else:
            success, code = False, "UNSUPPORTED_CORE_COMPONENT"
    except Exception as exc:
        finish_attempt(
            workspace,attempt_id,status=FAILED_RETRYABLE,error_class=type(exc).__name__,
            error_code="CORE_RECOVERY_EXCEPTION",error_message=str(exc),retryable=True,
        )
        return False
    if success:
        finish_attempt(
            workspace,attempt_id,status=SUCCESS,result_ref=f"{item.component.casefold()}:{item.scope_key}:effective",
            metadata={"result_code":code},retryable=True,
        )
        return True
    status = WAITING_FOR_DATA if code == "EXTRACTION_SOURCE_UNAVAILABLE" else FAILED_RETRYABLE
    finish_attempt(
        workspace,attempt_id,status=status,error_class="CORE_RECOVERY",error_code=code,
        error_message=f"selective recovery did not satisfy {item.component}/{item.scope_key}",retryable=True,
    )
    return False


def _core_pending(workspace: AuditWorkspace, audit_id: str) -> tuple[WorkItem, ...]:
    return tuple(
        item for item in list_work_items(workspace,audit_id,pending_only=True)
        if item.component in CORE_COMPONENTS and item.required
    )


def _core_unresolved(workspace: AuditWorkspace, audit_id: str) -> bool:
    return bool(_core_pending(workspace,audit_id))


def _wrap_reprocess(original: Any, module: Any):
    if getattr(original,"_rasai_core_reprocessing",False):
        return original

    def reprocess_with_core(audit_id: str, *, audits_root: str | Path = "audits", source: str = "CLI"):
        workspace = AuditWorkspace.open(Path(audits_root) / audit_id)
        module._backfill_contract(workspace,audit_id)
        synchronize_core_work_items(workspace,audit_id)
        initial_items = list_work_items(workspace,audit_id)
        initial_success = sum(item.required and item.status == SUCCESS for item in initial_items)
        core = tuple(item for item in _core_pending(workspace,audit_id) if not _is_expired(item))
        if not core:
            return original(audit_id,audits_root=audits_root,source=source)

        reprocess_id = start_reprocess_run(workspace,audit_id,source=source,note="selective core evidence recovery")
        attempted = 0
        successful = 0
        affected_snapshots: set[str] = set()

        for component in (HTTP_ACQUISITION,):
            for item in tuple(value for value in _core_pending(workspace,audit_id) if value.component == component and not _is_expired(value)):
                attempted += 1
                if _attempt_core_item(workspace,audit_id,item,reprocess_id):
                    successful += 1

        render_items = tuple(value for value in _core_pending(workspace,audit_id) if value.component == RENDER_CAPTURE and not _is_expired(value))
        if render_items:
            from rasai import m3
            with m3.BrowserIdentityRenderer() as renderer:
                for item in render_items:
                    attempted += 1
                    if _attempt_core_item(workspace,audit_id,item,reprocess_id,renderer=renderer):
                        successful += 1
                        affected_snapshots.add(item.scope_key)

        synchronize_core_work_items(workspace,audit_id)
        for item in tuple(value for value in _core_pending(workspace,audit_id) if value.component == CONTENT_EXTRACTION and not _is_expired(value)):
            attempted += 1
            if _attempt_core_item(workspace,audit_id,item,reprocess_id):
                successful += 1
                affected_snapshots.add(item.scope_key)

        synchronize_core_work_items(workspace,audit_id)
        for snapshot_id in sorted(affected_snapshots):
            try:
                _recompute_deterministic_for_snapshot(workspace,audit_id,snapshot_id,reprocess_id)
            except Exception:
                # The core work-item remains authoritative; downstream AI will stay
                # gated when its deterministic dependencies are not ready.
                pass
        synchronize_core_work_items(workspace,audit_id)

        original_start = module.start_reprocess_run
        original_finish = module.finish_reprocess_run
        original_latest = module._latest_pending

        def reuse_start(*args: Any, **kwargs: Any) -> str:
            return reprocess_id

        def defer_finish(*args: Any, **kwargs: Any):
            return recalculate(workspace,audit_id)

        def filtered_latest(active_workspace: AuditWorkspace, active_audit_id: str):
            items = original_latest(active_workspace,active_audit_id)
            unresolved = _core_unresolved(active_workspace,active_audit_id)
            return tuple(
                item for item in items
                if item.component not in CORE_COMPONENTS
                and not (unresolved and item.component in _AI_COMPONENTS)
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
        run_status = SUCCESS if summary.processing_status == "COMPLETE" else FAILED_RETRYABLE
        summary = finish_reprocess_run(
            workspace,reprocess_id,status=run_status,attempted_items=attempted,successful_items=successful,
            note=("all configured requirements satisfied" if summary.processing_status == "COMPLETE" else "one or more configured requirements remain unresolved"),
        )
        summary = project_report_validity(audit_id=audit_id,workspace=workspace)
        return module.ReprocessResult(
            audit_id=audit_id,reprocess_id=reprocess_id,processing_status=summary.processing_status,
            score_status=summary.score_status,report_status=summary.report_status,
            consolidation_eligible=summary.consolidation_eligible,attempted_items=attempted,
            successful_items=successful,skipped_success_items=initial_success,
            remaining_items=summary.pending_items+summary.blocked_items,
            temporal_expired_items=summary.expired_items,report_root=workspace.root / "report",
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
    """Install core-evidence fulfillment after the common fulfillment runtime."""
    global _INSTALLED
    if _INSTALLED:
        return
    from rasai import audit_reprocess, report_completion

    report_completion.finalize_audit_report_site = _wrap_finalizer(report_completion.finalize_audit_report_site)
    audit_reprocess.reprocess_audit = _wrap_reprocess(audit_reprocess.reprocess_audit,audit_reprocess)
    _INSTALLED = True
