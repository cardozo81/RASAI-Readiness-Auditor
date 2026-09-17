"""Incremental, evidence-version-bound continuation for M24 technical AI.

The existing M24 provider runtime remains the owner of provider selection, fallback,
request construction, attempts, usage and cost. This layer coordinates logical rounds:
valid resource assessments are retained, and a continuation asks only for resource
requirements still missing from the same sealed evidence version.

The wrapper is installed by the governed runtime and therefore affects both initial AUD
execution and selective RPR recovery without duplicating provider policy.
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import replace
import json
from pathlib import Path
import sqlite3
from typing import Any, Iterator, Mapping, Sequence

from rasai import ai_governance
from rasai.ai_selective_invalidation import register_task_dependency
from rasai.audit_phase_runtime import require_sealed_evidence
from rasai.semantic import ProviderState


_PURPOSE = "TECHNICAL_AI"
_CONTRACT = "M24-TECHNICAL-REMEDIATION-v2"
_MAX_CONTINUATION_ROUNDS = 3
_ACTIVE_RESOURCES: ContextVar[tuple[str, ...] | None] = ContextVar(
    "rasai_m24_requested_resources",
    default=None,
)
_INSTALLED = False
_ORIGINAL_RESOURCE_CONTEXT = None
_ORIGINAL_SCHEMA = None
_ORIGINAL_MAYBE = None


def _canonical_resource(value: Any) -> str:
    return str(value or "").strip().upper()


def _requirement(resource: str) -> str:
    return f"RESOURCE:{_canonical_resource(resource)}"


def _resource_from_requirement(value: str) -> str:
    text = str(value).strip().upper()
    return text.split(":", 1)[1] if text.startswith("RESOURCE:") else text


def _task_row(workspace: Any, task_id: str) -> dict[str, Any] | None:
    connection = sqlite3.connect(workspace.database)
    connection.row_factory = sqlite3.Row
    try:
        row = connection.execute(
            "SELECT * FROM ai_tasks WHERE ai_task_id=?",
            (task_id,),
        ).fetchone()
        return dict(row) if row is not None else None
    finally:
        connection.close()


def _task_accepted(workspace: Any, task_id: str) -> dict[str, dict[str, Any]]:
    row = _task_row(workspace, task_id)
    if row is None:
        return {}
    try:
        parsed = json.loads(str(row.get("accepted_json") or "{}"))
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return {
        str(key): dict(value)
        for key, value in parsed.items()
        if isinstance(value, Mapping)
    }


def latest_task_status(workspace: Any, audit_id: str) -> str | None:
    """Return the M24 task state bound to the latest evidence version."""
    connection = sqlite3.connect(workspace.database)
    try:
        row = connection.execute(
            """SELECT t.status FROM ai_tasks t
               JOIN ai_evidence_versions e ON e.evidence_snapshot_id=t.evidence_snapshot_id
               WHERE t.audit_id=? AND t.purpose=?
               ORDER BY e.version_number DESC,t.updated_at DESC LIMIT 1""",
            (audit_id, _PURPOSE),
        ).fetchone()
        return str(row[0]) if row else None
    except sqlite3.OperationalError:
        return None
    finally:
        connection.close()


def _round_artifact(workspace: Any, round_id: str) -> dict[str, Any] | None:
    source = Path(workspace.artifacts) / "m24" / "ai-technical-remediation.json"
    if not source.is_file():
        return None
    try:
        text = source.read_text(encoding="utf-8")
        payload = json.loads(text)
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError):
        return None
    target_dir = Path(workspace.artifacts) / "m24" / "ai-rounds"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{round_id}.json"
    target.write_text(text, encoding="utf-8", newline="\n")
    if isinstance(payload, dict):
        payload = dict(payload)
        payload["governance_round_id"] = round_id
        payload["round_artifact_reference"] = target.relative_to(workspace.root).as_posix()
        return payload
    return None


def _merge_round_payloads(
    *,
    workspace: Any,
    accepted: Mapping[str, Mapping[str, Any]],
    round_payloads: Sequence[Mapping[str, Any]],
    state: str,
    provider: str | None,
    model: str | None,
    reason: str | None,
) -> None:
    """Materialize one effective M24 projection while retaining every round artifact."""
    summaries: list[str] = []
    policy_notes: list[str] = []
    actions: list[dict[str, Any]] = []
    seen_actions: set[str] = set()
    round_refs: list[str] = []
    for payload in round_payloads:
        explanation = payload.get("explanation")
        if isinstance(explanation, Mapping):
            summary = str(explanation.get("summary_pt") or "").strip()
            if summary and summary not in summaries:
                summaries.append(summary)
            policy = str(explanation.get("policy_note_pt") or "").strip()
            if policy and policy not in policy_notes:
                policy_notes.append(policy)
            for raw in explanation.get("actions") or ():
                if not isinstance(raw, Mapping):
                    continue
                item = dict(raw)
                key = str(item.get("diagnostic_code") or json.dumps(item, sort_keys=True, default=str))
                if key in seen_actions:
                    continue
                seen_actions.add(key)
                actions.append(item)
        ref = str(payload.get("round_artifact_reference") or "").strip()
        if ref:
            round_refs.append(ref)

    ordered = []
    for resource in ("SITEMAP", "ROBOTS"):
        item = accepted.get(_requirement(resource))
        if item is not None:
            ordered.append(dict(item))

    explanation = {
        "summary_pt": "\n\n".join(summaries) if summaries else "Avaliação técnica consolidada por rounds evidence-bound.",
        "actions": actions,
        "resource_assessments": ordered,
        "policy_note_pt": "\n\n".join(policy_notes) if policy_notes else "Resultados consolidados preservam somente assessments validados contra a evidência selada.",
        "governance_round_artifacts": round_refs,
    }
    payload = {
        "contract_version": _CONTRACT,
        "state": state,
        "provider": provider,
        "model": model,
        "reason": reason,
        "explanation": explanation,
        "scoring_impact": "BOUNDED_STATIC_FACTORS" if ordered else "NONE",
        "governance": {
            "purpose": _PURPOSE,
            "accepted_requirements": sorted(accepted),
            "round_artifacts": round_refs,
        },
    }
    path = Path(workspace.artifacts) / "m24" / "ai-technical-remediation.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    reference = path.relative_to(workspace.root).as_posix()
    connection = sqlite3.connect(workspace.database)
    try:
        with connection:
            connection.execute(
                """UPDATE m24_ai_results
                   SET state=?,provider=?,model=?,reason=?,artifact_reference=?,updated_at=datetime('now')
                   WHERE audit_id=(SELECT audit_id FROM m24_ai_results WHERE artifact_reference IS NOT NULL OR audit_id IS NOT NULL LIMIT 1)""",
                (state, provider, model, reason, reference),
            )
    except sqlite3.OperationalError:
        pass
    finally:
        connection.close()


def _persist_effective_result(
    *,
    workspace: Any,
    audit_id: str,
    state: str,
    provider: str | None,
    model: str | None,
    reason: str | None,
    accepted: Mapping[str, Mapping[str, Any]],
    round_payloads: Sequence[Mapping[str, Any]],
) -> None:
    # Same projection as _merge_round_payloads, but update the correct AUD explicitly.
    summaries: list[str] = []
    policy_notes: list[str] = []
    actions: list[dict[str, Any]] = []
    seen_actions: set[str] = set()
    round_refs: list[str] = []
    for payload in round_payloads:
        explanation = payload.get("explanation")
        if isinstance(explanation, Mapping):
            summary = str(explanation.get("summary_pt") or "").strip()
            if summary and summary not in summaries:
                summaries.append(summary)
            policy = str(explanation.get("policy_note_pt") or "").strip()
            if policy and policy not in policy_notes:
                policy_notes.append(policy)
            for raw in explanation.get("actions") or ():
                if not isinstance(raw, Mapping):
                    continue
                item = dict(raw)
                key = str(item.get("diagnostic_code") or json.dumps(item, sort_keys=True, default=str))
                if key in seen_actions:
                    continue
                seen_actions.add(key)
                actions.append(item)
        ref = str(payload.get("round_artifact_reference") or "").strip()
        if ref:
            round_refs.append(ref)
    ordered = [
        dict(accepted[_requirement(resource)])
        for resource in ("SITEMAP", "ROBOTS")
        if _requirement(resource) in accepted
    ]
    payload = {
        "contract_version": _CONTRACT,
        "state": state,
        "provider": provider,
        "model": model,
        "reason": reason,
        "explanation": {
            "summary_pt": "\n\n".join(summaries) if summaries else "Avaliação técnica consolidada por rounds evidence-bound.",
            "actions": actions,
            "resource_assessments": ordered,
            "policy_note_pt": "\n\n".join(policy_notes) if policy_notes else "Resultados consolidados preservam somente assessments validados contra a evidência selada.",
            "governance_round_artifacts": round_refs,
        },
        "scoring_impact": "BOUNDED_STATIC_FACTORS" if ordered else "NONE",
        "governance": {
            "purpose": _PURPOSE,
            "accepted_requirements": sorted(accepted),
            "round_artifacts": round_refs,
        },
    }
    path = Path(workspace.artifacts) / "m24" / "ai-technical-remediation.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    reference = path.relative_to(workspace.root).as_posix()
    connection = sqlite3.connect(workspace.database)
    try:
        with connection:
            connection.execute(
                """UPDATE m24_ai_results SET state=?,provider=?,model=?,reason=?,artifact_reference=?,updated_at=datetime('now')
                   WHERE audit_id=?""",
                (state, provider, model, reason, reference, audit_id),
            )
    finally:
        connection.close()


@contextmanager
def _requested_resources(resources: Sequence[str]) -> Iterator[None]:
    token = _ACTIVE_RESOURCES.set(tuple(dict.fromkeys(_canonical_resource(item) for item in resources if _canonical_resource(item))))
    try:
        yield
    finally:
        _ACTIVE_RESOURCES.reset(token)


def _install_context_filters() -> None:
    global _ORIGINAL_RESOURCE_CONTEXT, _ORIGINAL_SCHEMA
    from rasai import m24_ai

    current_context = m24_ai._resource_context_facts
    if not bool(getattr(current_context, "_rasai_m24_partial", False)):
        _ORIGINAL_RESOURCE_CONTEXT = current_context

        def resource_context(workspace: Any, audit_id: str):
            facts, evidence = current_context(workspace, audit_id)
            active = _ACTIVE_RESOURCES.get()
            if not active:
                return facts, evidence
            allowed = frozenset(active)
            filtered_evidence = {
                str(key): value
                for key, value in evidence.items()
                if _canonical_resource(key) in allowed
            }
            filtered_facts = [
                item
                for item in facts
                if _canonical_resource(item.get("category")) in allowed
            ]
            return filtered_facts, filtered_evidence

        resource_context._rasai_m24_partial = True
        resource_context._rasai_original = current_context
        m24_ai._resource_context_facts = resource_context
    else:
        _ORIGINAL_RESOURCE_CONTEXT = getattr(current_context, "_rasai_original", current_context)

    current_schema = m24_ai._schema
    if not bool(getattr(current_schema, "_rasai_m24_partial", False)):
        _ORIGINAL_SCHEMA = current_schema

        def schema():
            output = current_schema()
            active = _ACTIVE_RESOURCES.get()
            if not active:
                return output
            resources = list(dict.fromkeys(active))
            spec = output["properties"]["resource_assessments"]
            spec["minItems"] = 1
            spec["maxItems"] = max(1, len(resources))
            spec["items"]["properties"]["resource"]["enum"] = resources
            return output

        schema._rasai_m24_partial = True
        schema._rasai_original = current_schema
        m24_ai._schema = schema
    else:
        _ORIGINAL_SCHEMA = getattr(current_schema, "_rasai_original", current_schema)


def _available_resources(workspace: Any, audit_id: str) -> tuple[str, ...]:
    from rasai import m24_ai

    # Call outside an active continuation filter to inspect the complete technical
    # resource universe available in the sealed AUD.
    token = _ACTIVE_RESOURCES.set(None)
    try:
        _facts, evidence = m24_ai._resource_context_facts(workspace, audit_id)
    finally:
        _ACTIVE_RESOURCES.reset(token)
    return tuple(
        resource
        for resource in ("SITEMAP", "ROBOTS")
        if resource in {_canonical_resource(key) for key in evidence}
    )


def _install_maybe_wrapper() -> None:
    global _ORIGINAL_MAYBE
    from rasai import m24_ai

    current = m24_ai.maybe_remediate_m24
    if bool(getattr(current, "_rasai_m24_partial", False)):
        _ORIGINAL_MAYBE = getattr(current, "_rasai_original", current)
        return
    _ORIGINAL_MAYBE = current

    def maybe_remediate_m24(*, audit_id: str, workspace: Any, provider: Any, diagnostics: tuple[Any, ...]):
        evidence_snapshot = require_sealed_evidence(audit_id=audit_id, workspace=workspace)
        resources = _available_resources(workspace, audit_id)

        # Preserve the original advisory behavior when there is no score-bound resource
        # requirement. The call remains one atomic technical-remediation request.
        if not resources:
            return current(
                audit_id=audit_id,
                workspace=workspace,
                provider=provider,
                diagnostics=diagnostics,
            )

        requirements = tuple(_requirement(resource) for resource in resources)
        task_id = ai_governance.register_task(
            workspace=workspace,
            audit_id=audit_id,
            purpose=_PURPOSE,
            scope_type="AUDIT",
            scope_key="AUDIT",
            evidence_snapshot_id=evidence_snapshot.evidence_snapshot_id,
            requirements=requirements,
            semantic_contract_version=_CONTRACT,
        )
        register_task_dependency(
            workspace=workspace,
            ai_task_id=task_id,
            dependency_kind="TECHNICAL_RESOURCE_EVIDENCE",
            scope_key="AUDIT",
        )
        accepted = _task_accepted(workspace, task_id)
        pending = list(ai_governance.task_missing_requirements(workspace, task_id))
        round_payloads: list[dict[str, Any]] = []
        last_result = None
        provider_name = model_name = None

        # A rerender/reconciliation of the same evidence version never repays an already
        # complete task. Rehydrate the effective result from persisted accepted items.
        if not pending:
            return m24_ai.M24AiResult(
                state=ProviderState.AVAILABLE,
                provider=None,
                model=None,
                explanation={
                    "summary_pt": "Resultado técnico reutilizado da mesma evidence version.",
                    "actions": [],
                    "resource_assessments": [
                        dict(accepted[key]) for key in requirements if key in accepted
                    ],
                    "policy_note_pt": "Nenhuma nova chamada de provider foi necessária.",
                },
                reason="REUSED_GOVERNED_TASK",
            )

        for _ in range(_MAX_CONTINUATION_ROUNDS):
            if not pending:
                break
            requested = tuple(pending)
            active_resources = tuple(_resource_from_requirement(item) for item in requested)
            filtered_diagnostics = tuple(
                item
                for item in diagnostics
                if _canonical_resource(getattr(item, "category", "")) in set(active_resources)
            )
            # Keep an empty diagnostic set valid: resource baseline facts are loaded by
            # the existing provider runtime from deterministic rule executions.
            round_id = ai_governance.begin_round(
                workspace=workspace,
                ai_task_id=task_id,
                requested_requirements=requested,
                input_payload={
                    "evidence_snapshot_id": evidence_snapshot.evidence_snapshot_id,
                    "requested_requirements": list(requested),
                    "diagnostic_codes": [str(getattr(item, "code", "")) for item in filtered_diagnostics],
                },
                input_summary={
                    "requested_resources": list(active_resources),
                    "diagnostics": len(filtered_diagnostics),
                },
            )
            with _requested_resources(active_resources):
                result = current(
                    audit_id=audit_id,
                    workspace=workspace,
                    provider=provider,
                    diagnostics=filtered_diagnostics,
                )
            last_result = result
            if result.provider:
                provider_name = result.provider
            if result.model:
                model_name = result.model
            archived = _round_artifact(workspace, round_id)
            if archived is not None:
                round_payloads.append(archived)

            new_values: dict[str, dict[str, Any]] = {}
            explanation = result.explanation or {}
            raw_assessments = explanation.get("resource_assessments") if isinstance(explanation, Mapping) else None
            if isinstance(raw_assessments, list):
                for raw in raw_assessments:
                    if not isinstance(raw, Mapping):
                        continue
                    key = _requirement(str(raw.get("resource") or ""))
                    if key not in requested or key in accepted:
                        continue
                    value = dict(raw)
                    accepted[key] = value
                    new_values[key] = value

            remaining = tuple(item for item in requested if item not in new_values)
            ai_governance.complete_round(
                workspace=workspace,
                ai_round_id=round_id,
                accepted=new_values,
                rejected={},
                missing=remaining,
                output_payload={
                    "provider_state": result.state.value,
                    "provider": result.provider,
                    "model": result.model,
                    "accepted_requirements": list(new_values),
                    "missing_requirements": list(remaining),
                    "reason": result.reason,
                },
                failed=result.state is not ProviderState.AVAILABLE,
            )
            pending = list(ai_governance.task_missing_requirements(workspace, task_id))
            if not new_values:
                break

        unresolved = tuple(ai_governance.task_missing_requirements(workspace, task_id))
        final_state = "AVAILABLE" if accepted else (
            last_result.state.value if last_result is not None else "UNAVAILABLE"
        )
        reason = (
            "AI_PARTIAL_AFTER_CONTINUATION:" + ",".join(unresolved)
            if unresolved and accepted
            else (last_result.reason if last_result is not None else "M24_AI_UNAVAILABLE")
        )
        _persist_effective_result(
            workspace=workspace,
            audit_id=audit_id,
            state=final_state,
            provider=provider_name,
            model=model_name,
            reason=reason,
            accepted=accepted,
            round_payloads=round_payloads,
        )
        if accepted:
            return m24_ai.M24AiResult(
                state=ProviderState.AVAILABLE,
                provider=provider_name,
                model=model_name,
                explanation={
                    "summary_pt": "Avaliação técnica consolidada por rounds evidence-bound.",
                    "actions": [],
                    "resource_assessments": [
                        dict(accepted[key]) for key in requirements if key in accepted
                    ],
                    "policy_note_pt": "Resultados aceitos foram preservados; continuações solicitaram apenas requisitos faltantes.",
                },
                reason=reason,
            )
        return last_result or m24_ai.M24AiResult(
            state=ProviderState.UNAVAILABLE,
            reason="M24_AI_UNAVAILABLE",
        )

    maybe_remediate_m24._rasai_m24_partial = True
    maybe_remediate_m24._rasai_original = current
    m24_ai.maybe_remediate_m24 = maybe_remediate_m24


def _install_reprocess_completion_guard() -> None:
    """A partial governed M24 task must remain retryable in RPR."""
    try:
        from rasai import reprocess_ai
    except ImportError:
        return
    current = reprocess_ai.recover_technical_ai
    if bool(getattr(current, "_rasai_m24_partial", False)):
        return

    def recover_technical_ai(*args: Any, **kwargs: Any):
        success, provider = current(*args, **kwargs)
        workspace = kwargs.get("workspace")
        audit_id = str(kwargs.get("audit_id") or "")
        status = latest_task_status(workspace, audit_id) if workspace is not None and audit_id else None
        if status and status != ai_governance.TASK_COMPLETE:
            return False, provider
        return success, provider

    recover_technical_ai._rasai_m24_partial = True
    recover_technical_ai._rasai_original = current
    reprocess_ai.recover_technical_ai = recover_technical_ai


def _install_fulfillment_guard() -> None:
    """Do not project provider-level SUCCESS while logical M24 requirements are partial."""
    try:
        from rasai import fulfillment_execution_contract as contract
        from rasai.audit_fulfillment import (
            FAILED_RETRYABLE,
            REPLAY_SAFE,
            register_work_item,
            set_work_item_status,
        )
    except ImportError:
        return
    current = contract.reconcile_technical_ai_fulfillment
    if bool(getattr(current, "_rasai_m24_partial", False)):
        return

    def reconcile_technical_ai_fulfillment(*, workspace: Any, audit_id: str, state: str | None = None) -> None:
        status = latest_task_status(workspace, audit_id)
        if status in {ai_governance.TASK_PARTIAL, ai_governance.TASK_FAILED, ai_governance.TASK_STALE}:
            register_work_item(
                workspace,
                audit_id=audit_id,
                component="TECHNICAL_AI",
                required=True,
                temporal_mode=REPLAY_SAFE,
                retryable=True,
                configuration={"governance_task_status": status},
            )
            set_work_item_status(
                workspace,
                audit_id=audit_id,
                component="TECHNICAL_AI",
                status=FAILED_RETRYABLE,
                error_class="AI_REQUIREMENTS",
                error_code="TECHNICAL_AI_PARTIAL_REQUIREMENTS",
                error_message="a resposta técnica preservou itens válidos, mas ainda existem requisitos de IA não resolvidos",
                retryable=True,
            )
            return
        current(workspace=workspace, audit_id=audit_id, state=state)

    reconcile_technical_ai_fulfillment._rasai_m24_partial = True
    reconcile_technical_ai_fulfillment._rasai_original = current
    contract.reconcile_technical_ai_fulfillment = reconcile_technical_ai_fulfillment


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    _install_context_filters()
    _install_maybe_wrapper()
    _install_reprocess_completion_guard()
    _install_fulfillment_guard()
    _INSTALLED = True


__all__ = ["install", "latest_task_status"]
