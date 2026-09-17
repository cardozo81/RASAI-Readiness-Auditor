"""Governed partial continuation for semantic AI without weakening provider contracts.

The provider layer remains fail-closed by default: a direct provider call still expects
the complete canonical semantic contract.  Only a governed M7 call that is already bound
to a sealed evidence version enters a temporary rule-scope context.  Inside that context
a provider may return a valid subset of the rules requested for that logical round; the
outer coordinator persists that subset and asks only for the unresolved rules next.

Provider routing, retry, fallback, quarantine, usage and pricing remain owned by the
existing provider runtime.
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import replace
import json
import sqlite3
from typing import Any, Iterator, Mapping, Sequence

from rasai.ai_governance import (
    begin_round,
    complete_round,
    latest_evidence_snapshot,
    register_task,
    task_missing_requirements,
)
from rasai import semantic


_CANONICAL_RULE_IDS = tuple(semantic.SEMANTIC_RULE_IDS)
_EXECUTION_CONTEXT: ContextVar[tuple[str, Any, Any] | None] = ContextVar(
    "rasai_semantic_execution_context",
    default=None,
)
_RULE_PROVIDER_METADATA: ContextVar[dict[str, dict[str, str | None]]] = ContextVar(
    "rasai_semantic_rule_provider_metadata",
    default={},
)
_MAX_CONTINUATION_ROUNDS = 4
_INSTALLED = False


def _assessment_payload(value: Any, metadata: Mapping[str, Any] | None = None) -> dict[str, Any]:
    result = getattr(value, "result", None)
    output = {
        "rule_id": str(getattr(value, "rule_id", "")),
        "result": str(getattr(result, "value", result or "")),
        "confidence": float(getattr(value, "confidence", 0.0) or 0.0),
        "evidence_ids": list(getattr(value, "evidence_ids", ()) or ()),
        "reasoning_summary": str(getattr(value, "reasoning_summary", "") or ""),
        "observed_value": getattr(value, "observed_value", {}),
    }
    if metadata:
        output["provider_metadata"] = {
            "provider": metadata.get("provider"),
            "model": metadata.get("model"),
            "prompt_id": metadata.get("prompt_id"),
            "prompt_version": metadata.get("prompt_version"),
            "configuration_version": metadata.get("configuration_version"),
        }
    return output


def _assessment_from_payload(value: Mapping[str, Any]):
    from rasai.domain import RuleResult
    from rasai.semantic import SemanticRuleAssessment

    try:
        rule_id = str(value.get("rule_id") or "")
        if rule_id not in _CANONICAL_RULE_IDS:
            return None
        return SemanticRuleAssessment(
            rule_id=rule_id,
            result=RuleResult(str(value.get("result") or "UNKNOWN")),
            confidence=float(value.get("confidence") or 0.0),
            evidence_ids=tuple(str(item) for item in value.get("evidence_ids") or ()),
            reasoning_summary=str(value.get("reasoning_summary") or ""),
            observed_value=value.get("observed_value") or {},
        )
    except (TypeError, ValueError):
        return None


def _persisted_task_values(workspace: Any, task_id: str) -> tuple[dict[str, Any], dict[str, dict[str, str | None]]]:
    connection = sqlite3.connect(workspace.database)
    try:
        row = connection.execute(
            "SELECT accepted_json FROM ai_tasks WHERE ai_task_id=?",
            (task_id,),
        ).fetchone()
    except sqlite3.OperationalError:
        row = None
    finally:
        connection.close()
    if row is None:
        return {}, {}
    try:
        raw = json.loads(str(row[0] or "{}"))
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}, {}
    if not isinstance(raw, dict):
        return {}, {}

    accepted: dict[str, Any] = {}
    metadata: dict[str, dict[str, str | None]] = {}
    for key, value in raw.items():
        if not isinstance(value, Mapping):
            continue
        assessment = _assessment_from_payload(value)
        if assessment is None:
            continue
        rule_id = str(key)
        accepted[rule_id] = assessment
        raw_meta = value.get("provider_metadata")
        if isinstance(raw_meta, Mapping):
            metadata[rule_id] = {
                "provider": str(raw_meta.get("provider") or "") or None,
                "model": str(raw_meta.get("model") or "") or None,
                "prompt_id": str(raw_meta.get("prompt_id") or "") or None,
                "prompt_version": str(raw_meta.get("prompt_version") or "") or None,
                "configuration_version": str(raw_meta.get("configuration_version") or "") or None,
            }
    return accepted, metadata


def _set_rule_symbols(modules: Sequence[Any], values: tuple[str, ...]) -> None:
    for module in modules:
        if hasattr(module, "SEMANTIC_RULE_IDS"):
            module.SEMANTIC_RULE_IDS = values


@contextmanager
def _scoped_provider_contract(requested: Sequence[str]) -> Iterator[None]:
    """Temporarily narrow the semantic wire contract for one governed provider call.

    Module symbols are restored before control returns to the caller, so direct provider
    use and unrelated audits retain the canonical 22-rule fail-closed contract.  The
    audit worker executes provider calls synchronously; ContextVar-backed outer state
    keeps nested governed execution isolated.
    """
    from rasai import m18_ai, openai_provider, provider_extensions

    requested_ids = tuple(dict.fromkeys(str(item) for item in requested if str(item) in _CANONICAL_RULE_IDS))
    if not requested_ids:
        yield
        return

    modules = (semantic, openai_provider, m18_ai, provider_extensions)
    saved_rule_ids = {module: getattr(module, "SEMANTIC_RULE_IDS", None) for module in modules}
    saved_hardened = {
        openai_provider: openai_provider.hardened_semantic_output_schema,
        m18_ai: m18_ai.hardened_semantic_output_schema,
        provider_extensions: provider_extensions.hardened_semantic_output_schema,
    }
    saved_normalize = {
        semantic: semantic.normalize_provider_payload,
        openai_provider: openai_provider.normalize_provider_payload,
        m18_ai: m18_ai.normalize_provider_payload,
        provider_extensions: provider_extensions.normalize_provider_payload,
    }
    saved_deepseek_schema = m18_ai._deepseek_semantic_output_schema
    saved_deepseek_canonicalize = m18_ai._canonicalize_deepseek_wire_payload

    original_hardened = openai_provider.hardened_semantic_output_schema
    original_normalize = semantic.normalize_provider_payload
    original_deepseek_schema = m18_ai._deepseek_semantic_output_schema

    def set_expected(values: Sequence[str]) -> tuple[str, ...]:
        normalized = tuple(dict.fromkeys(str(item) for item in values if str(item) in requested_ids))
        if normalized:
            _set_rule_symbols(modules, normalized)
        return normalized

    def partial_hardened(allowed_evidence_ids=None):
        schema = original_hardened(allowed_evidence_ids)
        active = tuple(getattr(openai_provider, "SEMANTIC_RULE_IDS", requested_ids))
        assessments = schema["properties"]["assessments"]
        assessments["minItems"] = 1
        assessments["maxItems"] = max(1, len(active))
        assessments["items"]["properties"]["rule_id"]["enum"] = list(active)
        return schema

    def partial_normalize(payload: Any, allowed_evidence_ids, **kwargs):
        normalized = original_normalize(payload, allowed_evidence_ids, **kwargs)
        received = tuple(item.rule_id for item in normalized.assessments)
        if received:
            set_expected(received)
        return normalized

    def partial_deepseek_schema(allowed_evidence_ids=None):
        schema = original_deepseek_schema(allowed_evidence_ids)
        assessments = schema.get("properties", {}).get("assessments", {})
        if isinstance(assessments, dict):
            # Ask for every requested property but allow a provider response to be
            # salvaged item-by-item if it arrives incomplete; the outer task records
            # what remains unresolved and performs the continuation.
            assessments["required"] = []
        return schema

    def partial_deepseek_canonicalize(payload: Any) -> Any:
        if not isinstance(payload, Mapping):
            return payload
        assessments = payload.get("assessments")
        if not isinstance(assessments, Mapping):
            return payload
        expected = tuple(getattr(m18_ai, "SEMANTIC_RULE_IDS", requested_ids))
        allowed = frozenset(expected)
        received = tuple(str(key) for key in assessments)
        if not received or not set(received).issubset(allowed):
            raise semantic.SemanticSchemaError("INVALID_SEMANTIC_RULE_SUBSET")
        canonical: list[dict[str, Any]] = []
        for rule_id in expected:
            if rule_id not in assessments:
                continue
            raw = assessments.get(rule_id)
            if not isinstance(raw, Mapping):
                raise semantic.SemanticSchemaError(f"INVALID_ASSESSMENT_OBJECT_{rule_id}")
            if "rule_id" in raw:
                raise semantic.SemanticSchemaError(f"UNEXPECTED_RULE_ID_FIELD_{rule_id}")
            canonical.append({"rule_id": rule_id, **dict(raw)})
        set_expected(tuple(item["rule_id"] for item in canonical))
        output = dict(payload)
        output["assessments"] = canonical
        return output

    _set_rule_symbols(modules, requested_ids)
    for module in saved_hardened:
        module.hardened_semantic_output_schema = partial_hardened
    for module in saved_normalize:
        module.normalize_provider_payload = partial_normalize
    m18_ai._deepseek_semantic_output_schema = partial_deepseek_schema
    m18_ai._canonicalize_deepseek_wire_payload = partial_deepseek_canonicalize
    try:
        yield
    finally:
        for module, value in saved_rule_ids.items():
            if value is not None:
                module.SEMANTIC_RULE_IDS = value
        for module, value in saved_hardened.items():
            module.hardened_semantic_output_schema = value
        for module, value in saved_normalize.items():
            module.normalize_provider_payload = value
        m18_ai._deepseek_semantic_output_schema = saved_deepseek_schema
        m18_ai._canonicalize_deepseek_wire_payload = saved_deepseek_canonicalize


def _install_m7_continuation() -> None:
    from rasai import m7

    original_execute = m7.execute_m7
    original_safe = m7._safe_provider_call
    original_evaluate = m7._evaluate
    if bool(getattr(original_safe, "_rasai_partial_semantic", False)):
        return

    def execute_m7(*args: Any, **kwargs: Any):
        audit_id = str(kwargs.get("audit_id") or "")
        workspace = kwargs.get("workspace")
        if not audit_id or workspace is None:
            return original_execute(*args, **kwargs)

        # Low-level/unit consumers retain the original M7 contract.  The orchestrated
        # AUD/RPR paths seal evidence first; only those paths activate continuation.
        snapshot = latest_evidence_snapshot(workspace, audit_id)
        if snapshot is None:
            return original_execute(*args, **kwargs)

        token = _EXECUTION_CONTEXT.set((audit_id, workspace, snapshot))
        try:
            return original_execute(*args, **kwargs)
        finally:
            _EXECUTION_CONTEXT.reset(token)

    def safe_provider_call(provider: Any, semantic_input: Any):
        context = _EXECUTION_CONTEXT.get()
        if context is None or str(getattr(provider, "name", "NONE")).upper() == "NONE":
            return original_safe(provider, semantic_input)

        audit_id, workspace, evidence_snapshot = context
        task_id = register_task(
            workspace=workspace,
            audit_id=audit_id,
            purpose="SEMANTIC_M7",
            scope_type="SNAPSHOT",
            scope_key=str(semantic_input.snapshot_id),
            evidence_snapshot_id=evidence_snapshot.evidence_snapshot_id,
            requirements=_CANONICAL_RULE_IDS,
            semantic_contract_version="M18-SEMANTIC-22-v1",
            prompt_id="rasai-semantic-v1",
            prompt_version="1",
        )
        try:
            from rasai.ai_selective_invalidation import register_task_dependency
            register_task_dependency(
                workspace=workspace,
                ai_task_id=task_id,
                dependency_kind="SNAPSHOT_EVIDENCE",
                scope_key=str(semantic_input.snapshot_id),
            )
        except Exception:
            pass

        accepted, provider_meta = _persisted_task_values(workspace, task_id)
        entities: list[Any] = []
        entity_keys: set[tuple[Any, ...]] = set()
        primary_intent: str | None = None
        secondary_intents: list[str] = []
        response_template: Any | None = None
        last_call: Any | None = None
        pending = list(task_missing_requirements(workspace, task_id))

        for _ in range(_MAX_CONTINUATION_ROUNDS):
            if not pending:
                break
            requested = tuple(pending)
            round_id = begin_round(
                workspace=workspace,
                ai_task_id=task_id,
                requested_requirements=requested,
                input_payload={
                    "snapshot_id": semantic_input.snapshot_id,
                    "requested_rule_ids": list(requested),
                    "evidence_ids": sorted(semantic_input.allowed_evidence_ids),
                    "evidence_snapshot_id": evidence_snapshot.evidence_snapshot_id,
                },
                input_summary={
                    "requested_rules": len(requested),
                    "evidence_count": len(semantic_input.evidence),
                    "page_url": semantic_input.page_url,
                },
            )
            with _scoped_provider_contract(requested):
                call = original_safe(provider, semantic_input)
            last_call = call
            response = getattr(call, "response", None)
            new_values: dict[str, Any] = {}
            if response is not None:
                response_template = response_template or response
                for assessment in response.assessments:
                    rule_id = str(assessment.rule_id)
                    if rule_id not in requested or rule_id in accepted:
                        continue
                    meta = {
                        "provider": str(getattr(response, "provider", "") or ""),
                        "model": getattr(response, "model", None),
                        "prompt_id": str(getattr(response, "prompt_id", "") or ""),
                        "prompt_version": str(getattr(response, "prompt_version", "") or ""),
                        "configuration_version": str(getattr(response, "configuration_version", "") or ""),
                    }
                    accepted[rule_id] = assessment
                    provider_meta[rule_id] = meta
                    new_values[rule_id] = _assessment_payload(assessment, meta)
                for entity in response.entities:
                    key = (str(entity.name).casefold(), str(entity.entity_type), tuple(entity.evidence_ids))
                    if key not in entity_keys:
                        entity_keys.add(key)
                        entities.append(entity)
                if primary_intent is None and response.primary_intent:
                    primary_intent = response.primary_intent
                for intent in response.secondary_intents:
                    if intent not in secondary_intents and len(secondary_intents) < 5:
                        secondary_intents.append(intent)

            remaining = tuple(rule for rule in requested if rule not in new_values)
            complete_round(
                workspace=workspace,
                ai_round_id=round_id,
                accepted=new_values,
                rejected={},
                missing=remaining,
                output_payload={
                    "provider_state": str(getattr(call, "state", "UNAVAILABLE")),
                    "accepted_rule_ids": list(new_values),
                    "missing_rule_ids": list(remaining),
                    "reason": getattr(call, "reason", None),
                },
                failed=response is None,
            )
            pending = list(task_missing_requirements(workspace, task_id))
            if not new_values:
                break

        if not accepted:
            return last_call or original_safe(provider, semantic_input)

        template = response_template
        if template is None:
            # All values were reused from this same sealed evidence version. Metadata is
            # preserved per rule below; the aggregate response needs only stable defaults.
            first_meta = next(iter(provider_meta.values()), {})
            provider_name = str(first_meta.get("provider") or "GOVERNED_REUSE")
            model = first_meta.get("model")
            prompt_id = str(first_meta.get("prompt_id") or "rasai-semantic-v1")
            prompt_version = str(first_meta.get("prompt_version") or "1")
            configuration_version = str(first_meta.get("configuration_version") or "1")
        else:
            provider_name = str(getattr(template, "provider", "") or "")
            model = getattr(template, "model", None)
            prompt_id = str(getattr(template, "prompt_id", "") or "")
            prompt_version = str(getattr(template, "prompt_version", "") or "")
            configuration_version = str(getattr(template, "configuration_version", "") or "")

        merged = semantic.SemanticProviderResponse(
            assessments=tuple(accepted[rule_id] for rule_id in _CANONICAL_RULE_IDS if rule_id in accepted),
            entities=tuple(entities),
            primary_intent=primary_intent,
            secondary_intents=tuple(secondary_intents),
            provider=provider_name,
            model=model,
            configuration_version=configuration_version,
            prompt_id=prompt_id,
            prompt_version=prompt_version,
        )
        _RULE_PROVIDER_METADATA.set(provider_meta)
        unresolved = tuple(rule_id for rule_id in _CANONICAL_RULE_IDS if rule_id not in accepted)
        return semantic.ProviderCallResult(
            semantic.ProviderState.AVAILABLE,
            response=merged,
            reason=("AI_PARTIAL_AFTER_CONTINUATION:" + ",".join(unresolved) if unresolved else None),
        )

    def evaluate(*args: Any, **kwargs: Any):
        outcome = original_evaluate(*args, **kwargs)
        provider_assessment = kwargs.get("provider_assessment")
        if provider_assessment is None and len(args) >= 4:
            provider_assessment = args[3]
        if provider_assessment is None or not bool(getattr(outcome, "provider_used", False)):
            return outcome
        meta = _RULE_PROVIDER_METADATA.get().get(str(getattr(provider_assessment, "rule_id", "")))
        if not meta:
            return outcome
        return replace(
            outcome,
            metadata=replace(
                outcome.metadata,
                provider=meta.get("provider") or outcome.metadata.provider,
                model=meta.get("model"),
                prompt_id=meta.get("prompt_id") or outcome.metadata.prompt_id,
                prompt_version=meta.get("prompt_version") or outcome.metadata.prompt_version,
                configuration_version=meta.get("configuration_version") or outcome.metadata.configuration_version,
            ),
        )

    execute_m7._rasai_partial_semantic = True
    execute_m7._rasai_original = original_execute
    safe_provider_call._rasai_partial_semantic = True
    safe_provider_call._rasai_original = original_safe
    evaluate._rasai_partial_semantic = True
    evaluate._rasai_original = original_evaluate
    m7.execute_m7 = execute_m7
    m7._safe_provider_call = safe_provider_call
    m7._evaluate = evaluate

    # audit_runner imported execute_m7 by value; keep the high-level pipeline on the
    # governed wrapper while direct low-level imports remain behaviorally compatible.
    try:
        from rasai import audit_runner
        if getattr(audit_runner, "execute_m7", None) is original_execute:
            audit_runner.execute_m7 = execute_m7
    except ImportError:
        pass


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    _install_m7_continuation()
    _INSTALLED = True


__all__ = ["install"]
