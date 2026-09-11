"""Cross-provider policy for punctual, token-efficient RASAi AI calls.

The policy deliberately does not merge device snapshots whose evidence identities differ:
evidence-bound scoring must remain traceable to the snapshot that was analyzed. Instead,
RASAi keeps one structured semantic call for the complete unresolved rule set of a
snapshot, removes transport-only/duplicated fields from the provider payload, and asks
providers to avoid prose duplication. No scoring formula is changed here.
"""
from __future__ import annotations

from typing import Any, Callable


AI_CALL_POLICY_VERSION = "AI-CALL-POLICY-002"
TOKEN_ECONOMY_INSTRUCTION = (
    "Be concise: do not restate the input evidence, rule text, or schema. "
    "Use the minimum wording needed for evidence-bound reasoning fields and avoid duplicate details. "
    "When requested_rule_ids is supplied, return assessments only for those rule_ids; omitted rules are resolved deterministically by RASAi."
)

_SEMANTIC_RULE_IDS = tuple(f"BR-GEO-{number:03d}" for number in range(28, 50))
_ALWAYS_DETERMINISTIC_RULE_IDS = frozenset({"BR-GEO-034", "BR-GEO-035"})
_INSTALLED = False


def _structured_data_absent(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, dict):
        blocks = value.get("blocks")
        return isinstance(blocks, list) and not blocks
    return False


def _requested_rule_ids(semantic_input: Any) -> tuple[str, ...]:
    """Return only rules for which a configured provider can affect M7 outcome."""
    excluded = set(_ALWAYS_DETERMINISTIC_RULE_IDS)
    if not str(getattr(semantic_input, "title", "") or "").strip():
        # Missing title is a hard deterministic BR-GEO-028 failure.
        excluded.add("BR-GEO-028")
    if _structured_data_absent(getattr(semantic_input, "structured_data", None)):
        # With no Structured Data, consistency rules are deterministically N/A.
        excluded.update({"BR-GEO-036", "BR-GEO-037"})
    return tuple(rule_id for rule_id in _SEMANTIC_RULE_IDS if rule_id not in excluded)


def _compact_semantic_provider_payload(payload: Any, semantic_input: Any) -> Any:
    if not isinstance(payload, dict):
        return payload
    compact = dict(payload)
    compact["requested_rule_ids"] = list(_requested_rule_ids(semantic_input))
    raw_evidence = compact.get("evidence")
    if isinstance(raw_evidence, list):
        evidence: list[Any] = []
        for raw in raw_evidence:
            if not isinstance(raw, dict):
                evidence.append(raw)
                continue
            item = dict(raw)
            # Local artifact paths cannot be dereferenced by an external model and add
            # tokens without evidence value. Evidence identity remains the evidence_id.
            item.pop("artifact_reference", None)
            if str(item.get("source") or "") == "semantic-input-builder":
                observed = item.get("observed_value")
                if isinstance(observed, dict):
                    # title and the first 2k characters were duplicate copies of fields
                    # already supplied losslessly at top level (title/main_content).
                    item["observed_value"] = {
                        "main_content_available": bool(observed.get("main_content_available")),
                        "structured_data_available": bool(observed.get("structured_data_available")),
                    }
            evidence.append(item)
        compact["evidence"] = evidence
    return compact


def _append_instruction(payload: Any, requested_rule_ids: tuple[str, ...] = ()) -> Any:
    if not isinstance(payload, dict):
        return payload
    instructions = payload.get("instructions")
    if isinstance(instructions, str):
        suffix = TOKEN_ECONOMY_INSTRUCTION
        if requested_rule_ids:
            suffix += " Requested rule_ids: " + ", ".join(requested_rule_ids) + "."
        if TOKEN_ECONOMY_INSTRUCTION not in instructions:
            payload = dict(payload)
            payload["instructions"] = instructions.rstrip() + " " + suffix
    return payload


def _patch_provider_payload(semantic: Any) -> None:
    original = semantic.SemanticInput.provider_payload
    if bool(getattr(original, "_rasai_ai_efficiency_policy", False)):
        return

    def compact_provider_payload(self: Any) -> dict[str, Any]:
        return _compact_semantic_provider_payload(original(self), self)

    compact_provider_payload._rasai_ai_efficiency_policy = True
    compact_provider_payload._rasai_original = original
    semantic.SemanticInput.provider_payload = compact_provider_payload


def _patch_request_method(cls: Any) -> None:
    original = getattr(cls, "_request_payload", None)
    if not callable(original) or getattr(cls, "_rasai_ai_efficiency_policy", False):
        return

    def compact_request(self: Any, *args: Any, **kwargs: Any) -> Any:
        semantic_input = args[0] if args else kwargs.get("semantic_input")
        requested = _requested_rule_ids(semantic_input) if semantic_input is not None else ()
        return _append_instruction(original(self, *args, **kwargs), requested)

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
    """Install lossless input de-duplication and concise output guidance."""
    global _INSTALLED
    if _INSTALLED:
        return

    from rasai import semantic
    from rasai import m18_ai

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

    _INSTALLED = True


def strategy_summary() -> dict[str, Any]:
    return {
        "version": AI_CALL_POLICY_VERSION,
        "semantic_granularity": "ONE_STRUCTURED_CALL_PER_SNAPSHOT_FOR_UNRESOLVED_RULES",
        "deterministic_rules_not_requested_from_ai": sorted(_ALWAYS_DETERMINISTIC_RULE_IDS),
        "origin_resource_repetition": "NONE_BY_DEVICE",
        "report_generation_ai_calls": 0,
        "device_snapshot_deduplication": "NOT_MERGED_WHEN_EVIDENCE_IDENTITIES_DIFFER",
        "input_policy": "LOSSLESS_DUPLICATE_REMOVAL_NO_ARTIFACT_PATHS",
        "output_policy": "CONCISE_EVIDENCE_BOUND_NO_INPUT_RESTATEMENT",
    }
