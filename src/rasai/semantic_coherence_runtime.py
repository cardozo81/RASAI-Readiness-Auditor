"""Runtime extension that adds semantic-coherence output to existing AI calls.

No provider/router is replaced. The extension augments the existing semantic JSON schema
and normalizer, so routing, retries, pricing, attempts and exchange logging stay owned by
the global AI orchestration. Missing coherence output degrades only the new CAT-03
coherence capability; the pre-existing semantic BR-GEO result remains usable.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Mapping

from rasai.semantic_coherence import (
    CoherenceResult,
    PAGE_COHERENCE_IDS,
    PROPERTY_SIGNAL_NAMES,
    PageCoherenceAssessment,
    PropertySemanticSignal,
    coherence_prompt_directive,
    page_coherence_output_schema,
    property_signal_output_schema,
)

_INSTALLED = False


@dataclass(frozen=True, slots=True)
class SemanticCoherenceProviderResponse:
    """Duck-compatible semantic response plus non-scoring coherence outputs."""

    assessments: tuple[Any, ...]
    entities: tuple[Any, ...]
    primary_intent: str | None
    secondary_intents: tuple[str, ...]
    provider: str
    model: str | None
    configuration_version: str
    prompt_id: str
    prompt_version: str
    coherence_assessments: tuple[PageCoherenceAssessment, ...] = ()
    property_signals: tuple[PropertySemanticSignal, ...] = ()


def _confidence(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("semantic coherence confidence must be numeric")
    result = float(value)
    if not 0.0 <= result <= 1.0:
        raise ValueError("semantic coherence confidence must be between 0 and 1")
    return result


def _evidence_ids(value: Any, allowed: frozenset[str]) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError("semantic coherence evidence_ids must be an array of strings")
    ids = tuple(dict.fromkeys(value))
    unknown = set(ids) - allowed
    if unknown:
        raise ValueError(f"semantic coherence referenced unknown evidence_ids: {sorted(unknown)}")
    return ids


def _normalize_page_coherence(value: Any, allowed: frozenset[str]) -> tuple[PageCoherenceAssessment, ...]:
    if not isinstance(value, list):
        raise ValueError("coherence_assessments must be an array")
    by_id: dict[str, PageCoherenceAssessment] = {}
    required = {
        "criterion_id", "result", "confidence", "declared_context", "observed_context",
        "evidence_ids", "reasoning_summary",
    }
    for raw in value:
        if not isinstance(raw, Mapping) or set(raw) != required:
            raise ValueError("semantic coherence assessment has missing or unexpected fields")
        criterion_id = str(raw["criterion_id"])
        if criterion_id not in PAGE_COHERENCE_IDS or criterion_id in by_id:
            raise ValueError(f"invalid or duplicate semantic coherence criterion: {criterion_id}")
        try:
            result = CoherenceResult(str(raw["result"]))
        except ValueError as exc:
            raise ValueError(f"invalid semantic coherence result for {criterion_id}") from exc
        evidence_ids = _evidence_ids(raw["evidence_ids"], allowed)
        if result in {CoherenceResult.COHERENT, CoherenceResult.PARTIAL, CoherenceResult.INCOHERENT} and not evidence_ids:
            raise ValueError(f"{criterion_id} requires evidence for result {result.value}")
        declared = raw["declared_context"]
        observed = raw["observed_context"]
        reasoning = raw["reasoning_summary"]
        if not all(isinstance(item, str) for item in (declared, observed, reasoning)):
            raise ValueError("semantic coherence context/reasoning fields must be strings")
        by_id[criterion_id] = PageCoherenceAssessment(
            criterion_id=criterion_id,
            result=result,
            confidence=_confidence(raw["confidence"]),
            declared_context=declared.strip(),
            observed_context=observed.strip(),
            evidence_ids=evidence_ids,
            reasoning_summary=reasoning.strip(),
        )
    if tuple(by_id) != PAGE_COHERENCE_IDS:
        missing = [item for item in PAGE_COHERENCE_IDS if item not in by_id]
        raise ValueError("incomplete semantic coherence output; missing: " + ", ".join(missing))
    return tuple(by_id[item] for item in PAGE_COHERENCE_IDS)


def _normalize_property_signals(value: Any, allowed: frozenset[str]) -> tuple[PropertySemanticSignal, ...]:
    if not isinstance(value, list):
        raise ValueError("property_signals must be an array")
    by_name: dict[str, PropertySemanticSignal] = {}
    required = {"signal_name", "value", "confidence", "evidence_ids"}
    for raw in value:
        if not isinstance(raw, Mapping) or set(raw) != required:
            raise ValueError("property signal has missing or unexpected fields")
        name = str(raw["signal_name"])
        if name not in PROPERTY_SIGNAL_NAMES or name in by_name:
            raise ValueError(f"invalid or duplicate property signal: {name}")
        signal_value = raw["value"]
        if signal_value is not None:
            if not isinstance(signal_value, str) or not signal_value.strip():
                raise ValueError(f"property signal {name} value must be non-empty text or null")
            signal_value = signal_value.strip()[:1000]
        evidence_ids = _evidence_ids(raw["evidence_ids"], allowed)
        if signal_value is not None and not evidence_ids:
            raise ValueError(f"property signal {name} requires evidence when a value is returned")
        if signal_value is None and evidence_ids:
            raise ValueError(f"property signal {name} with null value must not cite evidence")
        by_name[name] = PropertySemanticSignal(
            signal_name=name,
            value=signal_value,
            confidence=_confidence(raw["confidence"]),
            evidence_ids=evidence_ids,
        )
    if tuple(by_name) != PROPERTY_SIGNAL_NAMES:
        missing = [item for item in PROPERTY_SIGNAL_NAMES if item not in by_name]
        raise ValueError("incomplete property signal output; missing: " + ", ".join(missing))
    return tuple(by_name[item] for item in PROPERTY_SIGNAL_NAMES)


def _extend_schema(schema: dict[str, Any], allowed: frozenset[str] | None = None) -> dict[str, Any]:
    result = json.loads(json.dumps(schema, ensure_ascii=False))
    properties = result.get("properties")
    required = result.get("required")
    if not isinstance(properties, dict) or not isinstance(required, list):
        return result
    properties["coherence_assessments"] = page_coherence_output_schema(allowed)
    properties["property_signals"] = property_signal_output_schema(allowed)
    for name in ("coherence_assessments", "property_signals"):
        if name not in required:
            required.append(name)
    return result


def _response_with_coherence(base: Any, assessments: tuple[PageCoherenceAssessment, ...], signals: tuple[PropertySemanticSignal, ...]) -> SemanticCoherenceProviderResponse:
    return SemanticCoherenceProviderResponse(
        assessments=tuple(base.assessments),
        entities=tuple(base.entities),
        primary_intent=base.primary_intent,
        secondary_intents=tuple(base.secondary_intents),
        provider=str(base.provider),
        model=base.model,
        configuration_version=str(base.configuration_version),
        prompt_id=str(base.prompt_id),
        prompt_version=str(base.prompt_version),
        coherence_assessments=assessments,
        property_signals=signals,
    )


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    from rasai import semantic
    from rasai import openai_provider

    original_schema = semantic.semantic_output_schema
    original_normalize = semantic.normalize_provider_payload

    def semantic_output_schema_with_coherence() -> dict[str, Any]:
        return _extend_schema(original_schema())

    def normalize_with_coherence(
        payload: Any,
        allowed_evidence_ids: frozenset[str],
        *,
        provider: str,
        model: str | None,
        configuration_version: str,
        prompt_id: str,
        prompt_version: str,
    ) -> Any:
        if not isinstance(payload, dict):
            return original_normalize(
                payload,
                allowed_evidence_ids,
                provider=provider,
                model=model,
                configuration_version=configuration_version,
                prompt_id=prompt_id,
                prompt_version=prompt_version,
            )
        has_coherence = "coherence_assessments" in payload or "property_signals" in payload
        if not has_coherence:
            # Fail-open only for the additive coherence capability. Existing semantic
            # validation remains strict and the report will show coherence as unavailable.
            base = original_normalize(
                payload,
                allowed_evidence_ids,
                provider=provider,
                model=model,
                configuration_version=configuration_version,
                prompt_id=prompt_id,
                prompt_version=prompt_version,
            )
            return _response_with_coherence(base, (), ())
        if "coherence_assessments" not in payload or "property_signals" not in payload:
            raise semantic.SemanticSchemaError("semantic coherence output is partially missing")
        reduced = dict(payload)
        raw_coherence = reduced.pop("coherence_assessments")
        raw_signals = reduced.pop("property_signals")
        base = original_normalize(
            reduced,
            allowed_evidence_ids,
            provider=provider,
            model=model,
            configuration_version=configuration_version,
            prompt_id=prompt_id,
            prompt_version=prompt_version,
        )
        try:
            coherence = _normalize_page_coherence(raw_coherence, allowed_evidence_ids)
            signals = _normalize_property_signals(raw_signals, allowed_evidence_ids)
        except ValueError as exc:
            raise semantic.SemanticSchemaError(str(exc)) from exc
        return _response_with_coherence(base, coherence, signals)

    semantic.semantic_output_schema = semantic_output_schema_with_coherence
    semantic.normalize_provider_payload = normalize_with_coherence
    # These modules imported the callables by value; update their module bindings while
    # preserving their existing provider classes and global orchestration.
    openai_provider.semantic_output_schema = semantic_output_schema_with_coherence
    openai_provider.normalize_provider_payload = normalize_with_coherence

    original_contextual = openai_provider.SEMANTIC_RULE_CRITERIA["BR-GEO-049"]
    openai_provider.SEMANTIC_RULE_CRITERIA["BR-GEO-049"] = openai_provider._ContextualCriterion(
        str(original_contextual) + "\n\n" + coherence_prompt_directive()
    )

    try:
        from rasai import m18_ai
        m18_ai.normalize_provider_payload = normalize_with_coherence
        original_deepseek_schema = m18_ai._deepseek_semantic_output_schema

        def deepseek_schema_with_supported_arrays(allowed_evidence_ids: frozenset[str] | None = None) -> dict[str, Any]:
            schema = original_deepseek_schema(allowed_evidence_ids)
            for name in ("coherence_assessments", "property_signals"):
                value = schema.get("properties", {}).get(name)
                if isinstance(value, dict):
                    value.pop("minItems", None)
                    value.pop("maxItems", None)
            return schema

        m18_ai._deepseek_semantic_output_schema = deepseek_schema_with_supported_arrays
    except ImportError:
        pass

    try:
        from rasai import provider_extensions
        provider_extensions.normalize_provider_payload = normalize_with_coherence
    except ImportError:
        pass

    try:
        from rasai import copilot_provider
        original_prompt = copilot_provider._semantic_prompt

        def semantic_prompt_with_coherence(semantic_input: Any) -> str:
            return original_prompt(semantic_input) + "\n\n" + coherence_prompt_directive()

        copilot_provider._semantic_prompt = semantic_prompt_with_coherence
    except ImportError:
        pass

    _INSTALLED = True
