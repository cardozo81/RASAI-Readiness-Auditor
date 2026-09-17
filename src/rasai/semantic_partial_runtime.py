"""Governed partial-continuation runtime for M7 semantic AI.

Provider retry/fallback/quarantine/pricing remains owned by the existing provider
runtime.  This layer operates one level above it: a semantic round may accept a valid
subset of the requested BR-GEO rules, persist that subset, and issue a continuation
containing only unresolved rule ids.  Accepted rules are immutable for the sealed
evidence version.
"""
from __future__ import annotations

from collections.abc import Iterator, Sequence
from contextvars import ContextVar
from dataclasses import replace
import json
from typing import Any, Mapping

from rasai.ai_governance import (
    begin_round,
    complete_round,
    register_task,
    task_missing_requirements,
)
from rasai.audit_phase_runtime import require_sealed_evidence
from rasai import semantic


_CANONICAL_RULE_IDS = tuple(semantic.SEMANTIC_RULE_IDS)
_ACTIVE_RULE_IDS: ContextVar[tuple[str, ...]] = ContextVar(
    "rasai_semantic_requested_rules",
    default=_CANONICAL_RULE_IDS,
)
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


class _ContextualRuleIds(Sequence[str]):
    """Sequence facade resolving rule ids from the current continuation round."""

    def _values(self) -> tuple[str, ...]:
        values = _ACTIVE_RULE_IDS.get()
        return values or _CANONICAL_RULE_IDS

    def __len__(self) -> int:
        return len(self._values())

    def __getitem__(self, index):
        return self._values()[index]

    def __iter__(self) -> Iterator[str]:
        return iter(self._values())

    def __contains__(self, value: object) -> bool:
        return value in self._values()

    def __repr__(self) -> str:
        return repr(self._values())


_RULE_PROXY = _ContextualRuleIds()


def _assessment_payload(value: Any) -> dict[str, Any]:
    result = getattr(value, "result", None)
    return {
        "rule_id": str(getattr(value, "rule_id", "")),
        "result": str(getattr(result, "value", result or "")),
        "confidence": float(getattr(value, "confidence", 0.0) or 0.0),
        "evidence_ids": list(getattr(value, "evidence_ids", ()) or ()),
        "reasoning_summary": str(getattr(value, "reasoning_summary", "") or ""),
        "observed_value": getattr(value, "observed_value", {}),
    }


def _patch_rule_symbols() -> None:
    from rasai import m18_ai, openai_provider, provider_extensions

    semantic.SEMANTIC_RULE_IDS = _RULE_PROXY
    openai_provider.SEMANTIC_RULE_IDS = _RULE_PROXY
    m18_ai.SEMANTIC_RULE_IDS = _RULE_PROXY
    provider_extensions.SEMANTIC_RULE_IDS = _RULE_PROXY


def _patch_schema_and_normalization() -> None:
    from rasai import m18_ai, openai_provider, provider_extensions

    original_hardened = openai_provider.hardened_semantic_output_schema
    if not bool(getattr(original_hardened, "_rasai_partial_semantic", False)):
        def hardened(allowed_evidence_ids=None):
            schema = original_hardened(allowed_evidence_ids)
            assessments = schema["properties"]["assessments"]
            requested = tuple(_ACTIVE_RULE_IDS.get())
            # Structured-output providers are asked for all requested rules, but the
            # wire contract deliberately permits a non-empty subset so a valid partial
            # response can be retained and continued instead of discarded wholesale.
            assessments["minItems"] = 1
            assessments["maxItems"] = max(1, len(requested))
            assessments["items"]["properties"]["rule_id"]["enum"] = list(requested)
            return schema

        hardened._rasai_partial_semantic = True
        hardened._rasai_original = original_hardened
        openai_provider.hardened_semantic_output_schema = hardened
        m18_ai.hardened_semantic_output_schema = hardened
        provider_extensions.hardened_semantic_output_schema = hardened

    original_normalize = semantic.normalize_provider_payload
    if not bool(getattr(original_normalize, "_rasai_partial_semantic", False)):
        def normalize(payload: Any, allowed_evidence_ids, **kwargs):
            normalized = original_normalize(payload, allowed_evidence_ids, **kwargs)
            requested = tuple(_ACTIVE_RULE_IDS.get())
            received = tuple(
                item.rule_id
                for item in normalized.assessments
                if item.rule_id in requested
            )
            if received:
                # Existing provider adapters validate cardinality immediately after
                # normalization.  Narrowing the contextual sequence to the locally
                # validated response lets that validation mean "complete response for
                # this returned subset"; the outer M7 coordinator remains responsible
                # for the original requested set and continuation.
                _ACTIVE_RULE_IDS.set(received)
            return normalized

        normalize._rasai_partial_semantic = True
        normalize._rasai_original = original_normalize
        semantic.normalize_provider_payload = normalize
        openai_provider.normalize_provider_payload = normalize
        m18_ai.normalize_provider_payload = normalize
        provider_extensions.normalize_provider_payload = normalize

    original_deepseek_schema = m18_ai._deepseek_semantic_output_schema
    if not bool(getattr(original_deepseek_schema, "_rasai_partial_semantic", False)):
        def deepseek_schema(allowed_evidence_ids=None):
            schema = original_deepseek_schema(allowed_evidence_ids)
            assessments = schema.get("properties", {}).get("assessments", {})
            if isinstance(assessments, dict):
                assessments["required"] = []
            return schema

        deepseek_schema._rasai_partial_semantic = True
        deepseek_schema._rasai_original = original_deepseek_schema
        m18_ai._deepseek_semantic_output_schema = deepseek_schema

    original_canonicalize = m18_ai._canonicalize_deepseek_wire_payload
    if not bool(getattr(original_canonicalize, "_rasai_partial_semantic", False)):
        def canonicalize(payload: Any) -> Any:
            if not isinstance(payload, Mapping):
                return payload
            assessments = payload.get("assessments")
            if not isinstance(assessments, Mapping):
                return payload
            requested = tuple(_ACTIVE_RULE_IDS.get())
            allowed = frozenset(requested)
            received = frozenset(str(key) for key in assessments)
            if not received or not received.issubset(allowed):
                raise semantic.SemanticSchemaError("INVALID_SEMANTIC_RULE_SUBSET")
            canonical: list[dict[str, Any]] = []
            for rule_id in requested:
                if rule_id not in assessments:
                    continue
                raw = assessments.get(rule_id)
                if not isinstance(raw, Mapping):
                    raise semantic.SemanticSchemaError(
                        f"INVALID_ASSESSMENT_OBJECT_{rule_id}"
                    )
                if "rule_id" in raw:
                    raise semantic.SemanticSchemaError(
                        f"UNEXPECTED_RULE_ID_FIELD_{rule_id}"
                    )
                canonical.append({"rule_id": rule_id, **dict(raw)})
            output = dict(payload)
            output["assessments"] = canonical
            return output

        canonicalize._rasai_partial_semantic = True
        canonicalize._rasai_original = original_canonicalize
        m18_ai._canonicalize_deepseek_wire_payload = canonicalize


def _patch_provider_attempt_summary() -> None:
    """Keep per-round attempt telemetry honest when the requested set is < 22."""
    from rasai import m18_ai

    current = m18_ai.ResponsesSemanticProvider.analyze
    if bool(getattr(current, "_rasai_partial_semantic", False)):
        return

    def analyze(self, semantic_input, *args: Any, **kwargs: Any):
        requested = tuple(_ACTIVE_RULE_IDS.get())
        result = current(self, semantic_input, *args, **kwargs)
        accepted = len(getattr(getattr(result, "response", None), "assessments", ()) or ())
        replacements: dict[Any, Any] = {}
        for attempt in tuple(getattr(self, "_last_attempts", ()) or ()):
            summary = str(getattr(attempt, "request_message_summary", "") or "")
            summary = summary.replace(
                "rules=22",
                f"rules_requested={len(requested)};rules_accepted={accepted}",
            )
            replacements[attempt] = replace(attempt, request_message_summary=summary)
        if replacements:
            self._last_attempts = tuple(
                replacements.get(item, item)
                for item in tuple(getattr(self, "_last_attempts", ()) or ())
            )
            history = list(getattr(self, "_history", []) or [])
            self._history[:] = [replacements.get(item, item) for item in history]
        return result

    analyze._rasai_partial_semantic = True
    analyze._rasai_original = current
    m18_ai.ResponsesSemanticProvider.analyze = analyze


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
        snapshot = require_sealed_evidence(audit_id=audit_id, workspace=workspace)
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
            # Governance persistence is additive; semantic evaluation must retain the
            # provider runtime's existing fail-open behavior if provenance persistence
            # itself is unavailable.
            pass

        accepted: dict[str, Any] = {}
        provider_meta: dict[str, dict[str, str | None]] = {}
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
            token = _ACTIVE_RULE_IDS.set(requested)
            try:
                call = original_safe(provider, semantic_input)
            finally:
                _ACTIVE_RULE_IDS.reset(token)
            last_call = call
            response = getattr(call, "response", None)
            new_values: dict[str, Any] = {}
            if response is not None:
                response_template = response_template or response
                for assessment in response.assessments:
                    rule_id = str(assessment.rule_id)
                    if rule_id not in requested or rule_id in accepted:
                        continue
                    accepted[rule_id] = assessment
                    new_values[rule_id] = _assessment_payload(assessment)
                    provider_meta[rule_id] = {
                        "provider": str(getattr(response, "provider", "") or ""),
                        "model": getattr(response, "model", None),
                        "prompt_id": str(getattr(response, "prompt_id", "") or ""),
                        "prompt_version": str(getattr(response, "prompt_version", "") or ""),
                        "configuration_version": str(
                            getattr(response, "configuration_version", "") or ""
                        ),
                    }
                for entity in response.entities:
                    key = (
                        str(entity.name).casefold(),
                        str(entity.entity_type),
                        tuple(entity.evidence_ids),
                    )
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
        assert template is not None
        merged = semantic.SemanticProviderResponse(
            assessments=tuple(
                accepted[rule_id]
                for rule_id in _CANONICAL_RULE_IDS
                if rule_id in accepted
            ),
            entities=tuple(entities),
            primary_intent=primary_intent,
            secondary_intents=tuple(secondary_intents),
            provider=str(getattr(template, "provider", "")),
            model=getattr(template, "model", None),
            configuration_version=str(
                getattr(template, "configuration_version", "") or ""
            ),
            prompt_id=str(getattr(template, "prompt_id", "") or ""),
            prompt_version=str(getattr(template, "prompt_version", "") or ""),
        )
        _RULE_PROVIDER_METADATA.set(provider_meta)
        unresolved = tuple(
            rule_id for rule_id in _CANONICAL_RULE_IDS if rule_id not in accepted
        )
        return semantic.ProviderCallResult(
            semantic.ProviderState.AVAILABLE,
            response=merged,
            reason=(
                "AI_PARTIAL_AFTER_CONTINUATION:" + ",".join(unresolved)
                if unresolved
                else None
            ),
        )

    def evaluate(*args: Any, **kwargs: Any):
        outcome = original_evaluate(*args, **kwargs)
        provider_assessment = kwargs.get("provider_assessment")
        if provider_assessment is None and len(args) >= 4:
            provider_assessment = args[3]
        if provider_assessment is None or not bool(getattr(outcome, "provider_used", False)):
            return outcome
        meta = _RULE_PROVIDER_METADATA.get().get(
            str(getattr(provider_assessment, "rule_id", ""))
        )
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
                configuration_version=(
                    meta.get("configuration_version")
                    or outcome.metadata.configuration_version
                ),
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

    # audit_runner imported execute_m7 by value.
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
    _patch_rule_symbols()
    _patch_schema_and_normalization()
    _patch_provider_attempt_summary()
    _install_m7_continuation()
    _INSTALLED = True


__all__ = ["install"]
