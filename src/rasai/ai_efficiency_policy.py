"""Cross-provider policy for punctual, token-efficient RASAi AI calls.

The policy deliberately does not merge device snapshots whose evidence identities differ:
evidence-bound scoring must remain traceable to the snapshot that was analyzed. RASAi
keeps one structured semantic call for the complete contracted rule set of a snapshot,
removes provider-input fields that duplicate information already supplied losslessly,
and asks providers to avoid prose duplication. No scoring formula is changed here.
"""
from __future__ import annotations

from typing import Any, Callable


AI_CALL_POLICY_VERSION = "AI-CALL-POLICY-004"
TOKEN_ECONOMY_INSTRUCTION = (
    "Be concise: do not restate the input evidence, rule text, or schema. "
    "Use the minimum wording needed for evidence-bound reasoning fields and avoid duplicate details."
)


_INSTALLED = False


def _compact_semantic_provider_payload(payload: Any) -> Any:
    """Remove only transport-only or exact duplicate provider-input fields."""
    if not isinstance(payload, dict):
        return payload
    compact = dict(payload)
    raw_evidence = compact.get("evidence")
    if isinstance(raw_evidence, list):
        evidence: list[Any] = []
        for raw in raw_evidence:
            if not isinstance(raw, dict):
                evidence.append(raw)
                continue
            item = dict(raw)
            item.pop("artifact_reference", None)
            if str(item.get("source") or "") == "semantic-input-builder":
                observed = item.get("observed_value")
                if isinstance(observed, dict):
                    item["observed_value"] = {
                        "main_content_available": bool(observed.get("main_content_available")),
                        "structured_data_available": bool(observed.get("structured_data_available")),
                    }
            evidence.append(item)
        compact["evidence"] = evidence
    return compact


def _append_instruction(payload: Any) -> Any:
    if not isinstance(payload, dict):
        return payload
    instructions = payload.get("instructions")
    if isinstance(instructions, str) and TOKEN_ECONOMY_INSTRUCTION not in instructions:
        payload = dict(payload)
        payload["instructions"] = instructions.rstrip() + " " + TOKEN_ECONOMY_INSTRUCTION
    return payload


def _patch_provider_payload(semantic: Any) -> None:
    original = semantic.SemanticInput.provider_payload
    if bool(getattr(original, "_rasai_ai_efficiency_policy", False)):
        return

    def compact_provider_payload(self: Any) -> dict[str, Any]:
        return _compact_semantic_provider_payload(original(self))

    compact_provider_payload._rasai_ai_efficiency_policy = True
    compact_provider_payload._rasai_original = original
    semantic.SemanticInput.provider_payload = compact_provider_payload


def _patch_request_method(cls: Any) -> None:
    original = getattr(cls, "_request_payload", None)
    if not callable(original) or getattr(cls, "_rasai_ai_efficiency_policy", False):
        return

    def compact_request(self: Any, *args: Any, **kwargs: Any) -> Any:
        return _append_instruction(original(self, *args, **kwargs))

    cls._request_payload = compact_request
    cls._rasai_ai_efficiency_policy = True


def _patch_instruction_function(module: Any, name: str) -> None:
    original: Callable[..., Any] | None = getattr(module, name, None)
    marker = f"_rasai_efficiency_{name}"
    if not callable(original) or getattr(module, marker, False):
        return

    def compact(*args: Any, **kwargs: Any) -> Any:
        value = original(*args, **kwargs)
        if isinstance(value, str) and TOKEN_ECONOMY_INSTRUCTION not in value:
            return value.rstrip() + " " + TOKEN_ECONOMY_INSTRUCTION
        return value

    setattr(module, name, compact)
    setattr(module, marker, True)


def install() -> None:
    """Install lossless input de-duplication, readiness gates and shared AI consumers."""
    global _INSTALLED
    if _INSTALLED:
        return

    from rasai import m18_ai, semantic
    from rasai.ai_model_runtime import install as install_ai_model_runtime
    from rasai.semantic_coherence_runtime import install as install_semantic_coherence_runtime
    from rasai.semantic_corpus_runtime import install as install_semantic_corpus_runtime

    install_ai_model_runtime()
    install_semantic_coherence_runtime()
    install_semantic_corpus_runtime()

    _patch_provider_payload(semantic)
    _patch_request_method(semantic.OpenAIProvider)
    _patch_request_method(m18_ai.ResponsesSemanticProvider)

    try:
        from rasai import provider_extensions
        _patch_instruction_function(provider_extensions, "_semantic_instructions")
    except ImportError:
        pass

    try:
        from rasai import provider_extensions_m20
        _patch_instruction_function(provider_extensions_m20, "_instructions")
    except ImportError:
        pass

    from rasai.execution_completion_reliability import install as install_execution_completion_reliability
    from rasai.execution_completion_regression import install as install_execution_completion_regression

    install_execution_completion_reliability()
    install_execution_completion_regression()

    from rasai.ai_attempt_diagnostic_reporting import install as install_ai_attempt_diagnostic_reporting
    from rasai.audit_fulfillment_runtime import install as install_audit_fulfillment
    from rasai.audit_fulfillment_saas import install as install_audit_fulfillment_saas
    from rasai.core_integrity_runtime import install as install_core_integrity
    from rasai.core_reprocessing import install as install_core_reprocessing
    from rasai.core_reprocessing_context import install as install_core_reprocessing_context
    from rasai.execution_evidence_reporting import install as install_execution_evidence_reporting
    from rasai.execution_profile_report_capabilities import install as install_execution_profile_report_capabilities
    from rasai.fulfillment_execution_contract import install as install_fulfillment_execution_contract
    from rasai.reprocess_failure_preservation import install as install_reprocess_failure_preservation
    from rasai.reprocess_runtime_safety import install as install_reprocess_runtime_safety
    from rasai.report_public_ux_guard import install as install_report_public_ux_guard
    from rasai.semantic_recovery_runtime import install as install_semantic_recovery
    from rasai.technical_ai_eligibility import install as install_technical_ai_eligibility

    install_audit_fulfillment()
    install_core_reprocessing()
    install_core_integrity()
    install_core_reprocessing_context()
    install_semantic_recovery()
    install_audit_fulfillment_saas()
    install_technical_ai_eligibility()
    install_fulfillment_execution_contract()
    install_reprocess_failure_preservation()
    install_reprocess_runtime_safety()
    install_ai_attempt_diagnostic_reporting()
    install_execution_evidence_reporting()
    install_execution_profile_report_capabilities()
    install_report_public_ux_guard()

    from rasai.accepted_audit_refinements import install as install_accepted_audit_refinements
    from rasai.accepted_report_compat import install as install_accepted_report_compat
    from rasai.accepted_timeout_context import install as install_accepted_timeout_context
    from rasai.ai_orchestration_unification import install_ai_orchestration_unification
    from rasai.ai_orchestration_unification_cleanup import (
        install_ai_orchestration_unification_cleanup,
    )
    from rasai.catalog_report_search_trust_runtime import install as install_catalog_report_search_trust_runtime
    from rasai.improvement_exchange_capture import install as install_improvement_exchange_capture

    install_ai_orchestration_unification()
    install_ai_orchestration_unification_cleanup()
    install_accepted_audit_refinements()
    install_accepted_timeout_context()
    install_accepted_report_compat()
    # Must be installed after accepted report refinements so CAT-05 source-state and
    # provenance semantics are the final renderer layer on every materialization.
    install_catalog_report_search_trust_runtime()
    install_improvement_exchange_capture()

    from rasai.completion_recovery_alignment import install as install_completion_recovery_alignment

    install_completion_recovery_alignment()

    from rasai.ai_task_profile_runtime import install as install_ai_task_profile_runtime
    from rasai.ai_task_profile_semantic_compat import install as install_ai_task_profile_semantic_compat

    install_ai_task_profile_runtime()
    install_ai_task_profile_semantic_compat()

    _INSTALLED = True


def strategy_summary() -> dict[str, Any]:
    return {
        "version": AI_CALL_POLICY_VERSION,
        "semantic_granularity": "ONE_STRUCTURED_CALL_PER_SNAPSHOT_FOR_RULES_AND_COHERENCE",
        "semantic_corpus_gate": "WHOLE_AUDIT_CONTEXT_READY_BEFORE_FIRST_PROVIDER_CALL",
        "property_cross_page_policy": "DETERMINISTIC_AGGREGATION_OF_PERSISTED_PAGE_AI_OUTPUTS",
        "origin_resource_repetition": "NONE_BY_DEVICE",
        "report_generation_ai_calls": 0,
        "device_snapshot_deduplication": "NOT_MERGED_WHEN_EVIDENCE_IDENTITIES_DIFFER",
        "input_policy": "LOSSLESS_DUPLICATE_REMOVAL_NO_LOCAL_ARTIFACT_PATHS",
        "output_policy": "CONCISE_EVIDENCE_BOUND_NO_INPUT_RESTATEMENT",
        "eligibility_policy": "NO_PROVIDER_CALL_UNTIL_REQUIRED_PERSISTED_EVIDENCE_IS_READY",
    }
