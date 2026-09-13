"""Evidence-readiness gate for technical AI during initial execution and recovery.

Technical AI is optional but, when selected, it becomes a required fulfillment item.
A configured provider is called only after deterministic robots/sitemap evidence exists.
Missing prerequisite evidence is WAITING_FOR_DATA: it is not a provider failure, does not
create an AI attempt and incurs no AI cost.
"""
from __future__ import annotations

from dataclasses import replace
import json
import sqlite3
from typing import Any

from rasai.audit_fulfillment import (
    FAILED_RETRYABLE,
    NOT_APPLICABLE,
    REPLAY_SAFE,
    SUCCESS,
    WAITING_FOR_DATA,
    list_work_items,
    register_work_item,
    set_work_item_status,
)

_INSTALLED = False
_RESOURCE_RULE_IDS = ("BR-GEO-003", "BR-GEO-017", "BR-GEO-018")
_WAIT_REASON = "TECHNICAL_EVIDENCE_INSUFFICIENT"


def _load(value: Any, default: Any) -> Any:
    if value in (None, ""):
        return default
    if isinstance(value, (dict, list, tuple)):
        return value
    try:
        return json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return default


def technical_evidence_ready(workspace: Any, audit_id: str) -> bool:
    """Return True only when persisted technical source evidence can ground the call."""
    connection = sqlite3.connect(workspace.database)
    connection.row_factory = sqlite3.Row
    try:
        try:
            rows = connection.execute(
                """SELECT evidence_ids FROM rule_executions
                   WHERE audit_id=? AND rule_id IN (?,?,?)""",
                (audit_id, *_RESOURCE_RULE_IDS),
            ).fetchall()
        except sqlite3.OperationalError:
            return False
        for row in rows:
            evidence_ids = _load(row["evidence_ids"], [])
            if isinstance(evidence_ids, (list, tuple)) and any(str(item).strip() for item in evidence_ids):
                return True
        return False
    finally:
        connection.close()


def _mark_waiting(workspace: Any, audit_id: str) -> None:
    register_work_item(
        workspace,
        audit_id=audit_id,
        component="TECHNICAL_AI",
        scope_key="AUDIT",
        required=True,
        temporal_mode=REPLAY_SAFE,
        status=WAITING_FOR_DATA,
        retryable=True,
        configuration={"enabled": True},
    )
    set_work_item_status(
        workspace,
        audit_id=audit_id,
        component="TECHNICAL_AI",
        scope_key="AUDIT",
        status=WAITING_FOR_DATA,
        error_class="PREREQUISITE",
        error_code=_WAIT_REASON,
        error_message="technical AI requires persisted robots/sitemap evidence before provider execution",
        retryable=True,
    )


def _persist_waiting_run(workspace: Any, audit_id: str) -> None:
    connection = sqlite3.connect(workspace.database)
    try:
        try:
            with connection:
                connection.execute(
                    "UPDATE m24_runs SET ai_enabled=1,ai_state=? WHERE audit_id=?",
                    (WAITING_FOR_DATA, audit_id),
                )
        except sqlite3.OperationalError:
            return
    finally:
        connection.close()


def _unwrap_fulfillment(function: Any) -> Any:
    current = function
    seen: set[int] = set()
    while bool(getattr(current, "_rasai_fulfillment", False)) and id(current) not in seen:
        seen.add(id(current))
        candidate = getattr(current, "_rasai_original", None)
        if not callable(candidate):
            break
        current = candidate
    return current


def _wrap_m24(base: Any) -> Any:
    base = _unwrap_fulfillment(base)
    if bool(getattr(base, "_rasai_technical_evidence_gate", False)):
        return base

    def execute_m24_with_evidence_gate(*args: Any, **kwargs: Any):
        audit_id = str(kwargs.get("audit_id") or "")
        workspace = kwargs.get("workspace")
        enabled = bool(kwargs.get("technical_ai", False))
        if not audit_id or workspace is None or not enabled:
            return base(*args, **kwargs)

        register_work_item(
            workspace,
            audit_id=audit_id,
            component="TECHNICAL_AI",
            scope_key="AUDIT",
            required=True,
            temporal_mode=REPLAY_SAFE,
            configuration={"enabled": True},
        )

        if not technical_evidence_ready(workspace, audit_id):
            deterministic_kwargs = dict(kwargs)
            deterministic_kwargs["technical_ai"] = False
            result = base(*args, **deterministic_kwargs)
            _persist_waiting_run(workspace, audit_id)
            _mark_waiting(workspace, audit_id)
            try:
                return replace(result, ai_enabled=True, ai_state=WAITING_FOR_DATA)
            except TypeError:
                return result

        result = base(*args, **kwargs)
        state = str(getattr(result, "ai_state", "") or "").upper()
        if state == "AVAILABLE":
            set_work_item_status(
                workspace,
                audit_id=audit_id,
                component="TECHNICAL_AI",
                status=SUCCESS,
                result_ref=f"m24-ai:{getattr(result, 'ai_provider', None) or 'provider'}",
            )
        elif state in {"NOT_APPLICABLE", "NO_ELIGIBLE_FINDINGS"}:
            set_work_item_status(
                workspace,
                audit_id=audit_id,
                component="TECHNICAL_AI",
                status=NOT_APPLICABLE,
                retryable=False,
            )
        else:
            set_work_item_status(
                workspace,
                audit_id=audit_id,
                component="TECHNICAL_AI",
                status=FAILED_RETRYABLE,
                error_class="AI_PROVIDER",
                error_code=state or "M24_AI_UNAVAILABLE",
                error_message=f"M24 technical AI state={state or 'UNKNOWN'}",
                retryable=True,
            )
        return result

    execute_m24_with_evidence_gate._rasai_technical_evidence_gate = True
    execute_m24_with_evidence_gate._rasai_original = base
    return execute_m24_with_evidence_gate


def _correct_reprocess_diagnostics() -> None:
    from rasai import reprocess_ai
    from rasai.m24_crawling_discovery import M24Diagnostic

    def diagnostics(workspace: Any, audit_id: str):
        connection = sqlite3.connect(workspace.database)
        connection.row_factory = sqlite3.Row
        try:
            try:
                rows = connection.execute(
                    "SELECT * FROM m24_diagnostics WHERE audit_id=? ORDER BY diagnostic_id",
                    (audit_id,),
                ).fetchall()
            except sqlite3.OperationalError:
                rows = ()
        finally:
            connection.close()
        return tuple(
            M24Diagnostic(
                code=str(row["code"]),
                category=str(row["category"]),
                severity=str(row["severity"]),
                title=str(row["title"]),
                scope_url=row["scope_url"],
                observed=_load(row["observed_value"], {}),
                evidence_ids=tuple(str(value) for value in _load(row["evidence_ids"], [])),
                remediation=str(row["remediation"]),
            )
            for row in rows
        )

    reprocess_ai._m24_diagnostics = diagnostics

    original_recover = reprocess_ai.recover_technical_ai
    if bool(getattr(original_recover, "_rasai_technical_evidence_gate", False)):
        return

    def recover_with_gate(*, workspace: Any, audit_id: str, item: Any, reprocess_id: str, provider: Any | None = None):
        if not technical_evidence_ready(workspace, audit_id):
            _mark_waiting(workspace, audit_id)
            return False, provider
        return original_recover(
            workspace=workspace,
            audit_id=audit_id,
            item=item,
            reprocess_id=reprocess_id,
            provider=provider,
        )

    recover_with_gate._rasai_technical_evidence_gate = True
    recover_with_gate._rasai_original = original_recover
    reprocess_ai.recover_technical_ai = recover_with_gate


def _preserve_waiting_recovery_state() -> None:
    from rasai import audit_reprocess

    original = audit_reprocess._apply_result
    if bool(getattr(original, "_rasai_preserve_waiting", False)):
        return

    def apply_result(workspace: Any, *, item: Any, success: bool, error_code: str, result_ref: str) -> bool:
        if not success:
            current = next(
                (
                    candidate
                    for candidate in list_work_items(workspace, item.audit_id)
                    if candidate.component == item.component and candidate.scope_key == item.scope_key
                ),
                None,
            )
            if current is not None and current.status == WAITING_FOR_DATA:
                return False
        return original(
            workspace,
            item=item,
            success=success,
            error_code=error_code,
            result_ref=result_ref,
        )

    apply_result._rasai_preserve_waiting = True
    apply_result._rasai_original = original
    audit_reprocess._apply_result = apply_result


def _install_m24_resource_evidence_contract() -> None:
    """Expose the validator's per-resource evidence universe to every M24 provider.

    The M24 validator intentionally rejects a ROBOTS assessment that cites SITEMAP
    evidence (and vice versa). The provider prompt must therefore carry the same
    resource-scoped contract; otherwise a valid global evidence id can trigger a local
    contract error and an unnecessary paid fallback.
    """
    from rasai import m24_ai

    original = m24_ai._candidate_payload
    if bool(getattr(original, "_rasai_resource_evidence_contract", False)):
        return

    def candidate_payload(candidate: Any, *, schema: dict[str, Any], instructions: str, facts: list[dict[str, Any]]):
        resource_evidence: dict[str, list[str]] = {}
        for fact in facts:
            if not isinstance(fact, dict):
                continue
            if str(fact.get("scoring_role") or "") != "BOUNDED_RESOURCE_ASSESSMENT_ELIGIBLE":
                continue
            resource = str(fact.get("category") or "").strip().upper()
            if resource not in {"ROBOTS", "SITEMAP"}:
                continue
            evidence_ids = [
                str(item).strip()
                for item in (fact.get("evidence_ids") or [])
                if str(item).strip()
            ]
            if evidence_ids:
                current = resource_evidence.setdefault(resource, [])
                for evidence_id in evidence_ids:
                    if evidence_id not in current:
                        current.append(evidence_id)

        if resource_evidence:
            resource_contract = json.dumps(
                resource_evidence,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            )
            instructions = (
                instructions
                + " Para resource_assessments, a lista de evidence_ids é restrita por recurso. "
                + "Use exclusivamente os IDs do recurso correspondente no mapa autoritativo a seguir; "
                + "não cruze ROBOTS com SITEMAP e não gere assessment para recurso ausente do mapa. "
                + f"resource_evidence_ids={resource_contract}."
            )

        return original(
            candidate,
            schema=schema,
            instructions=instructions,
            facts=facts,
        )

    candidate_payload._rasai_resource_evidence_contract = True
    candidate_payload._rasai_original = original
    m24_ai._candidate_payload = candidate_payload


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    from rasai import audit_runner, cli_extensions, m24_crawling_discovery

    wrapped = _wrap_m24(m24_crawling_discovery.execute_m24)
    m24_crawling_discovery.execute_m24 = wrapped
    cli_extensions.execute_m24 = wrapped
    audit_runner.execute_m24 = wrapped

    _correct_reprocess_diagnostics()
    _preserve_waiting_recovery_state()
    _install_m24_resource_evidence_contract()
    _INSTALLED = True