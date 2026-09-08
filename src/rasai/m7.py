"""M7 - provider-independent semantic analysis, deterministic baseline and BR-GEO-028..049."""

from __future__ import annotations

from dataclasses import dataclass, replace
import json
from typing import Any

from rasai.domain import (
    AuditMode,
    AuditStatus,
    DeviceContext,
    EvidenceType,
    Finding,
    FindingDevice,
    RuleExecution,
    RuleResult,
    Severity,
    new_id,
    utc_now,
)
from rasai.evidence import EvidenceManager
from rasai.m3 import M3ExecutionResult
from rasai.m4 import M4ExecutionResult
from rasai.m5 import M5ExecutionResult
from rasai.m6 import M6ExecutionResult
from rasai.persistence import AuditPersistence, AuditWorkspace
from rasai.rules import RuleDefinition, RuleEvaluation, RuleScope
from rasai.semantic import (
    NoneProvider,
    ProviderCallResult,
    ProviderState,
    SEMANTIC_RULE_IDS,
    SemanticAnalysisProvider,
    SemanticEvidenceInput,
    SemanticInput,
    SemanticProviderResponse,
    SemanticRuleAssessment,
)
from rasai.semantic_baseline import (
    BASELINE_VERSION,
    BaselineAssessment,
    evaluate_semantic_baseline,
)
from rasai.semantic_persistence import EntityObservation, SemanticAssessment, SemanticPersistence


# M7 rule semantics changed because deterministic evidence can now resolve a
# conservative no-AI baseline. The SCORE-GEO-004 aggregation contract is unchanged.
_RULE_VERSION = "2"

_RULE_SPECS = (
    (28, "Page title must be present and semantically representative", "SEMANTIC_STRUCTURE", Severity.HIGH, "SEMANTIC_TITLE"),
    (29, "Main content must expose an understandable semantic hierarchy", "SEMANTIC_STRUCTURE", Severity.MEDIUM, "SEMANTIC_HIERARCHY"),
    (30, "Primary topic and major sections must be identifiable", "SEMANTIC_STRUCTURE", Severity.MEDIUM, "SEMANTIC_TOPIC"),
    (31, "Primary entity must be identifiable when applicable", "ENTITY_CLARITY", Severity.MEDIUM, "ENTITY_PRIMARY"),
    (32, "Important entity types and relationships must have sufficient context", "ENTITY_CLARITY", Severity.MEDIUM, "ENTITY_CONTEXT"),
    (33, "Material entity ambiguity must be detectable", "ENTITY_CLARITY", Severity.MEDIUM, "ENTITY_AMIGUITY"),
    (34, "Structured Data must be syntactically interpretable when present", "STRUCTURED_DATA", Severity.MEDIUM, "STRUCTURED_DATA_SYNTAX"),
    (35, "Structured Data types and relevant properties must be identifiable", "STRUCTURED_DATA", Severity.LOW, "STRUCTURED_DATA_SYNTAX"),
    (36, "Structured Data must remain consistent with visible page content", "STRUCTURED_DATA", Severity.MEDIUM, "STRUCTURED_DATA_CONSISTENCY"),
    (37, "Structured Data entities must be consistent with observed page entities", "STRUCTURED_DATA", Severity.MEDIUM, "STRUCTURED_DATA_CONSISTENCY"),
    (38, "Primary user intent must be identifiable", "ANSWERABILITY", Severity.HIGH, "PRIMARY_INTENT"),
    (39, "Relevant primary questions must receive explicit answers when applicable", "ANSWERABILITY", Severity.MEDIUM, "PRIMARY_ANSWERS"),
    (40, "Answers must contain sufficient context", "ANSWERABILITY", Severity.MEDIUM, "PRIMARY_ANSWERS"),
    (41, "Material factual claims must be explicitly identifiable", "CITATION_READINESS", Severity.LOW, "FACTUAL_CLAIMS"),
    (42, "Factual statements must contain sufficient factual context", "CITATION_READINESS", Severity.MEDIUM, "FACTUAL_CONTEXT"),
    (43, "Numeric, temporal and quantitative claims must include necessary qualifiers", "CITATION_READINESS", Severity.MEDIUM, "FACTUAL_CONTEXT"),
    (44, "Important information must be understandable without excessive inference", "CITATION_READINESS", Severity.MEDIUM, "INFERENCE_LOAD"),
    (45, "Material claims should expose appropriate attribution or supporting evidence when required", "EVIDENCE_TRUST", Severity.MEDIUM, "ATTRIBUTION"),
    (46, "Publisher, author or responsible entity should be identifiable when relevant", "EVIDENCE_TRUST", Severity.LOW, "RESPONSIBILITY"),
    (47, "Publication and freshness signals must remain internally consistent", "EVIDENCE_TRUST", Severity.MEDIUM, "FRESHNESS"),
    (48, "Primary and relevant secondary intents must be represented", "INTENT_COVERAGE", Severity.MEDIUM, "INTENT_SET"),
    (49, "Material intent coverage gaps must be evidence-backed", "INTENT_COVERAGE", Severity.MEDIUM, "INTENT_GAPS"),
)

_M7_DEFINITIONS = tuple(
    RuleDefinition(
        f"BR-GEO-{number:03d}",
        name,
        category,
        category,
        RuleScope.SNAPSHOT,
        severity=severity,
        basis="STANDARD" if number in {28, 34, 35} else "HEURISTIC",
        scoring_group=scoring_group,
    )
    for number, name, category, severity, scoring_group in _RULE_SPECS
)

_EXPECTED = {
    "BR-GEO-028": "title is present and semantically representative of the page",
    "BR-GEO-029": "main content exposes an understandable semantic hierarchy",
    "BR-GEO-030": "primary topic and major sections are identifiable with sufficient confidence",
    "BR-GEO-031": "primary entity is identifiable when applicable",
    "BR-GEO-032": "important entity types and relationships have sufficient context",
    "BR-GEO-033": "material entity ambiguity is absent or explicitly identifiable",
    "BR-GEO-034": "Structured Data is syntactically interpretable when present",
    "BR-GEO-035": "Structured Data types and relevant properties are identifiable",
    "BR-GEO-036": "Structured Data remains consistent with visible page content",
    "BR-GEO-037": "Structured Data entities remain consistent with observed page entities",
    "BR-GEO-038": "primary user intent is identifiable with evidence",
    "BR-GEO-039": "relevant primary questions receive explicit answers when applicable",
    "BR-GEO-040": "answers contain sufficient context",
    "BR-GEO-041": "material factual claims are explicitly identifiable",
    "BR-GEO-042": "factual statements contain sufficient factual context",
    "BR-GEO-043": "numeric, temporal and quantitative claims contain necessary qualifiers",
    "BR-GEO-044": "important information is understandable without excessive inference",
    "BR-GEO-045": "material claims expose appropriate attribution or support when required",
    "BR-GEO-046": "publisher, author or responsible entity is identifiable when relevant",
    "BR-GEO-047": "publication and freshness signals are internally consistent",
    "BR-GEO-048": "one primary and up to five relevant secondary intents are represented",
    "BR-GEO-049": "material intent coverage gaps are evidence-backed",
}


@dataclass(frozen=True, slots=True)
class M7ExecutionResult:
    rule_execution_ids: tuple[str, ...]
    finding_ids: tuple[str, ...]
    assessment_ids: tuple[str, ...]
    entity_observation_ids: tuple[str, ...]
    audit_mode: AuditMode
    provider_states: dict[str, ProviderState]


@dataclass(frozen=True, slots=True)
class _AssessmentMetadata:
    provider: str
    model: str | None
    prompt_id: str
    prompt_version: str
    configuration_version: str
    reasoning_summary: str


@dataclass(frozen=True, slots=True)
class _Outcome:
    evaluation: RuleEvaluation
    confidence: float
    source_evidence_ids: tuple[str, ...]
    metadata: _AssessmentMetadata
    provider_used: bool = False


class _PriorState:
    def __init__(
        self,
        persistence: AuditPersistence,
        m5_result: M5ExecutionResult,
        m6_result: M6ExecutionResult,
    ) -> None:
        self._page: dict[tuple[str, str], RuleResult] = {}
        self._snapshot: dict[tuple[str, str], RuleResult] = {}
        for execution_id in (*m5_result.rule_execution_ids, *m6_result.rule_execution_ids):
            execution = persistence.rule_executions.get(execution_id)
            if execution is None:
                raise ValueError(f"prior RuleExecution is not re-openable: {execution_id}")
            if execution.snapshot_id:
                self._snapshot[(execution.rule_id, execution.snapshot_id)] = execution.result
            elif execution.page_id:
                self._page[(execution.rule_id, execution.page_id)] = execution.result

    def get(self, rule_id: str, page_id: str, snapshot_id: str) -> RuleResult | None:
        return self._snapshot.get((rule_id, snapshot_id)) or self._page.get((rule_id, page_id))


def execute_m7(
    *,
    audit_id: str,
    m3_result: M3ExecutionResult,
    m4_result: M4ExecutionResult,
    m5_result: M5ExecutionResult,
    m6_result: M6ExecutionResult,
    persistence: AuditPersistence,
    workspace: AuditWorkspace,
    provider: SemanticAnalysisProvider | None = None,
) -> M7ExecutionResult:
    """Execute semantic analysis with a deterministic no-AI baseline per snapshot."""

    active_provider = provider or NoneProvider()
    audit = persistence.audits.get(audit_id)
    if audit is None:
        raise ValueError(f"audit not found: {audit_id}")
    if audit.status not in {
        AuditStatus.ANALYZING,
        AuditStatus.COMPARING,
        AuditStatus.SCORING,
        AuditStatus.RECOMMENDING,
        AuditStatus.REPORTING,
        AuditStatus.COMPLETED,
    }:
        persistence.audits.update(replace(audit, status=AuditStatus.ANALYZING))
        audit = persistence.audits.get(audit_id) or audit

    evidence_manager = EvidenceManager(persistence)
    prior = _PriorState(persistence, m5_result, m6_result)
    execution_ids: list[str] = []
    finding_ids: list[str] = []
    assessment_ids: list[str] = []
    entity_ids: list[str] = []
    provider_states: dict[str, ProviderState] = {}
    limitations = list(audit.limitations)
    baseline_used = False

    with SemanticPersistence(workspace) as semantic_store:
        for page_id, per_device in m3_result.snapshot_ids.items():
            page = persistence.pages.get(page_id)
            if page is None or page.audit_id != audit_id:
                raise ValueError(f"M3 references page outside audit: {page_id}")

            for device, snapshot_id in per_device.items():
                snapshot = persistence.snapshots.get(snapshot_id)
                if snapshot is None or snapshot.page_id != page_id or snapshot.device != device:
                    raise ValueError(f"invalid snapshot mapping: {snapshot_id}")

                semantic_input, context_evidence_id = _build_semantic_input(
                    audit,
                    page.normalized_url,
                    snapshot,
                    m4_result,
                    persistence,
                    workspace,
                    evidence_manager,
                )
                baseline_by_rule = evaluate_semantic_baseline(semantic_input)
                call = _safe_provider_call(active_provider, semantic_input)
                if call.response is not None and not _normalized_response_is_valid(
                    call.response,
                    semantic_input.allowed_evidence_ids,
                ):
                    call = ProviderCallResult(
                        ProviderState.UNAVAILABLE,
                        reason="AI_PROVIDER_UNAVAILABLE:INVALID_NORMALIZED_OUTPUT",
                    )
                provider_states[snapshot_id] = call.state
                if call.reason and call.reason not in limitations:
                    limitations.append(call.reason)

                response = call.response if call.state is ProviderState.AVAILABLE else None
                if response is not None:
                    for candidate in response.entities:
                        observation = EntityObservation(
                            entity_observation_id=new_id("ENT"),
                            snapshot_id=snapshot_id,
                            name=candidate.name,
                            entity_type=candidate.entity_type,
                            confidence=candidate.confidence,
                            evidence_ids=candidate.evidence_ids,
                        )
                        semantic_store.add_entity(observation)
                        entity_ids.append(observation.entity_observation_id)

                assessments_by_rule = (
                    {item.rule_id: item for item in response.assessments}
                    if response is not None
                    else {}
                )
                structured_summary = _structured_summary(semantic_input.structured_data)

                for definition in _M7_DEFINITIONS:
                    provider_assessment = assessments_by_rule.get(definition.rule_id)
                    blocked = _dependency_state(
                        definition.rule_id,
                        prior,
                        page_id,
                        snapshot_id,
                    )
                    if blocked is not None:
                        outcome = _blocked_outcome(
                            definition.rule_id,
                            blocked,
                            context_evidence_id,
                        )
                    else:
                        outcome = _evaluate(
                            definition.rule_id,
                            snapshot.title,
                            structured_summary,
                            provider_assessment,
                            call,
                            context_evidence_id,
                            response,
                            baseline_by_rule.get(definition.rule_id),
                        )
                    baseline_used = baseline_used or outcome.metadata.provider == "DETERMINISTIC_BASELINE"

                    semantic_assessment = SemanticAssessment(
                        assessment_id=new_id("SMA"),
                        snapshot_id=snapshot_id,
                        assessment_type=definition.rule_id,
                        result=outcome.evaluation.result,
                        confidence=outcome.confidence,
                        evidence_ids=outcome.source_evidence_ids,
                        prompt_id=outcome.metadata.prompt_id,
                        prompt_version=outcome.metadata.prompt_version,
                        provider=outcome.metadata.provider,
                        model=outcome.metadata.model,
                        configuration_version=outcome.metadata.configuration_version,
                        reasoning_summary=outcome.metadata.reasoning_summary,
                    )
                    semantic_store.add_assessment(semantic_assessment)
                    assessment_ids.append(semantic_assessment.assessment_id)

                    execution_evidence_ids = list(outcome.source_evidence_ids)
                    if (
                        outcome.provider_used
                        and provider_assessment is not None
                        and response is not None
                    ):
                        ai_evidence = evidence_manager.record(
                            audit_id=audit_id,
                            page_id=page_id,
                            snapshot_id=snapshot_id,
                            device=device,
                            evidence_type=EvidenceType.AI_ANALYSIS,
                            source=f"semantic:{response.provider}:{definition.rule_id}",
                            observed_value={
                                "rule_id": definition.rule_id,
                                "result": provider_assessment.result.value,
                                "confidence": provider_assessment.confidence,
                                "source_evidence_ids": list(provider_assessment.evidence_ids),
                                "reasoning_summary": provider_assessment.reasoning_summary,
                            },
                        )
                        execution_evidence_ids.append(ai_evidence.evidence_id)

                    execution = RuleExecution(
                        rule_execution_id=new_id("REX"),
                        audit_id=audit_id,
                        rule_id=definition.rule_id,
                        rule_version=_RULE_VERSION,
                        page_id=page_id,
                        snapshot_id=snapshot_id,
                        device=device,
                        result=outcome.evaluation.result,
                        observed_value=outcome.evaluation.observed_value,
                        expected_condition=outcome.evaluation.expected_condition,
                        evidence_ids=tuple(dict.fromkeys(execution_evidence_ids)),
                        executed_at=utc_now(),
                        error=None,
                    )
                    persistence.rule_executions.add(execution)
                    execution_ids.append(execution.rule_execution_id)
                    finding = _finding(definition, execution, persistence)
                    if finding is not None:
                        finding_ids.append(finding.finding_id)

    mode = _resolve_mode(tuple(provider_states.values()))
    refreshed = persistence.audits.get(audit_id)
    if refreshed is None:
        raise ValueError(f"audit disappeared: {audit_id}")
    baseline_capabilities = (f"semantic_baseline:{BASELINE_VERSION}",) if baseline_used else ()
    persistence.audits.update(
        replace(
            refreshed,
            audit_mode=mode,
            capabilities=tuple(
                dict.fromkeys(
                    (*refreshed.capabilities, f"semantic_provider:{active_provider.name}", *baseline_capabilities)
                )
            ),
            limitations=tuple(dict.fromkeys(limitations)),
        )
    )

    return M7ExecutionResult(
        rule_execution_ids=tuple(execution_ids),
        finding_ids=tuple(finding_ids),
        assessment_ids=tuple(assessment_ids),
        entity_observation_ids=tuple(entity_ids),
        audit_mode=mode,
        provider_states=provider_states,
    )


def _safe_provider_call(
    provider: SemanticAnalysisProvider,
    semantic_input: SemanticInput,
) -> ProviderCallResult:
    try:
        result = provider.analyze(semantic_input)
    except Exception as exc:
        return ProviderCallResult(
            ProviderState.UNAVAILABLE,
            reason=f"AI_PROVIDER_UNAVAILABLE:{type(exc).__name__}",
        )
    if not isinstance(result, ProviderCallResult):
        return ProviderCallResult(
            ProviderState.UNAVAILABLE,
            reason="AI_PROVIDER_UNAVAILABLE:INVALID_PROVIDER_CONTRACT",
        )
    return result


def _build_semantic_input(
    audit: Any,
    page_url: str,
    snapshot: Any,
    m4_result: M4ExecutionResult,
    persistence: AuditPersistence,
    workspace: AuditWorkspace,
    manager: EvidenceManager,
) -> tuple[SemanticInput, str]:
    main_content = _read_text(workspace, snapshot.main_content_ref) or ""
    structured_data = _read_json(workspace, snapshot.structured_data_ref)
    context = manager.record(
        audit_id=audit.audit_id,
        page_id=snapshot.page_id,
        snapshot_id=snapshot.snapshot_id,
        device=snapshot.device,
        evidence_type=EvidenceType.TEXT_EXCERPT,
        source="semantic-input-builder",
        observed_value={
            "title": snapshot.title,
            "main_content_excerpt": main_content[:2000],
            "main_content_available": bool(main_content),
            "structured_data_available": structured_data is not None,
        },
        artifact_reference=snapshot.main_content_ref,
    )

    evidence_ids = list(m4_result.evidence_ids.get(snapshot.snapshot_id, ()))
    evidence_ids.append(context.evidence_id)
    evidence_inputs: list[SemanticEvidenceInput] = []
    for evidence_id in dict.fromkeys(evidence_ids):
        evidence = persistence.evidence.get(evidence_id)
        if evidence is None or evidence.snapshot_id != snapshot.snapshot_id:
            continue
        evidence_inputs.append(
            SemanticEvidenceInput(
                evidence_id=evidence.evidence_id,
                evidence_type=evidence.evidence_type.value,
                source=evidence.source,
                observed_value=evidence.observed_value,
                artifact_reference=evidence.artifact_reference,
            )
        )

    return (
        SemanticInput(
            snapshot_id=snapshot.snapshot_id,
            page_url=page_url,
            title=snapshot.title,
            main_content=main_content,
            structured_data=structured_data,
            primary_language=audit.primary_language,
            market=audit.market,
            evidence=tuple(evidence_inputs),
        ),
        context.evidence_id,
    )


def _read_text(workspace: AuditWorkspace, reference: str | None) -> str | None:
    if not reference:
        return None
    path = workspace.root / reference
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8", errors="replace")


def _read_json(workspace: AuditWorkspace, reference: str | None) -> Any:
    text = _read_text(workspace, reference)
    if text is None:
        return None
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        return {"parse_error": "INVALID_PERSISTED_JSON"}


def _structured_summary(value: Any) -> dict[str, Any]:
    if value is None:
        return {
            "present": False,
            "blocks": 0,
            "invalid_blocks": 0,
            "types": [],
        }
    if not isinstance(value, dict):
        return {
            "present": True,
            "blocks": 0,
            "invalid_blocks": 1,
            "types": [],
        }
    blocks = value.get("blocks")
    if not isinstance(blocks, list):
        return {
            "present": True,
            "blocks": 0,
            "invalid_blocks": 1,
            "types": [],
        }

    invalid = 0
    types: list[str] = []
    for block in blocks:
        if not isinstance(block, dict):
            invalid += 1
            continue
        if block.get("parse_error"):
            invalid += 1
        for item in block.get("types", []):
            if isinstance(item, str):
                types.append(item)
    return {
        "present": bool(blocks),
        "blocks": len(blocks),
        "invalid_blocks": invalid,
        "types": list(dict.fromkeys(types)),
    }


def _dependency_state(
    rule_id: str,
    prior: _PriorState,
    page_id: str,
    snapshot_id: str,
) -> RuleResult | None:
    html = prior.get("BR-GEO-009", page_id, snapshot_id)
    if html in {RuleResult.FAIL, RuleResult.ERROR, RuleResult.NOT_APPLICABLE}:
        return RuleResult.NOT_APPLICABLE
    if html in {None, RuleResult.UNKNOWN}:
        return RuleResult.UNKNOWN

    if rule_id not in {"BR-GEO-034", "BR-GEO-035"}:
        rendered = prior.get("BR-GEO-020", page_id, snapshot_id)
        if rendered in {RuleResult.FAIL, RuleResult.ERROR, RuleResult.NOT_APPLICABLE}:
            return RuleResult.NOT_APPLICABLE
        if rendered in {None, RuleResult.UNKNOWN}:
            return RuleResult.UNKNOWN
    return None


def _blocked_outcome(
    rule_id: str,
    result: RuleResult,
    context_evidence_id: str,
) -> _Outcome:
    return _Outcome(
        evaluation=RuleEvaluation(
            result,
            {"reason": "SEMANTIC_PREREQUISITE_BLOCKED"},
            _EXPECTED[rule_id],
            reason="SEMANTIC_PREREQUISITE_BLOCKED",
        ),
        confidence=0.0,
        source_evidence_ids=(context_evidence_id,),
        metadata=_AssessmentMetadata(
            provider="FALLBACK",
            model=None,
            prompt_id="deterministic-m7",
            prompt_version="2",
            configuration_version="2",
            reasoning_summary="Prerequisite technical/content rule blocked semantic evaluation.",
        ),
        provider_used=False,
    )


def _evaluate(
    rule_id: str,
    title: str | None,
    structured: dict[str, Any],
    provider_assessment: SemanticRuleAssessment | None,
    call: ProviderCallResult,
    context_evidence_id: str,
    response: SemanticProviderResponse | None,
    baseline_assessment: BaselineAssessment | None,
) -> _Outcome:
    # Hard deterministic facts are authoritative in every mode.
    deterministic = _deterministic_outcome(
        rule_id,
        title,
        structured,
        context_evidence_id,
    )
    if deterministic is not None:
        return deterministic

    if rule_id in {"BR-GEO-036", "BR-GEO-037"} and not structured["present"]:
        return _Outcome(
            evaluation=RuleEvaluation(
                RuleResult.NOT_APPLICABLE,
                {"structured_data_present": False},
                _EXPECTED[rule_id],
                reason="STRUCTURED_DATA_ABSENT",
            ),
            confidence=1.0,
            source_evidence_ids=(context_evidence_id,),
            metadata=_AssessmentMetadata(
                provider="DETERMINISTIC",
                model=None,
                prompt_id="deterministic-m7",
                prompt_version="2",
                configuration_version="2",
                reasoning_summary="Structured Data is absent; the consistency rule is not applicable.",
            ),
            provider_used=False,
        )

    # Preserve provider behavior when a valid semantic assessment exists. The
    # deterministic baseline is the fallback for NO_AI / missing provider output,
    # not a silent override of a configured semantic provider.
    if provider_assessment is not None and response is not None:
        observed = provider_assessment.observed_value
        if rule_id == "BR-GEO-048":
            observed = {
                "provider_observed": provider_assessment.observed_value,
                "primary_intent": response.primary_intent,
                "secondary_intents": list(response.secondary_intents),
            }
        return _Outcome(
            evaluation=RuleEvaluation(
                provider_assessment.result,
                observed,
                _EXPECTED[rule_id],
                reason=(
                    provider_assessment.reasoning_summary
                    if provider_assessment.result is RuleResult.UNKNOWN
                    else None
                ),
            ),
            confidence=provider_assessment.confidence,
            source_evidence_ids=provider_assessment.evidence_ids,
            metadata=_AssessmentMetadata(
                provider=response.provider,
                model=response.model,
                prompt_id=response.prompt_id,
                prompt_version=response.prompt_version,
                configuration_version=response.configuration_version,
                reasoning_summary=provider_assessment.reasoning_summary,
            ),
            provider_used=True,
        )

    # A deliberately unavailable/invalid configured provider remains visible as
    # degradation. Explicit NO_AI and valid-but-incomplete provider responses may
    # use the local evidence-bound baseline instead.
    if (
        baseline_assessment is not None
        and call.state in {ProviderState.NOT_CONFIGURED, ProviderState.AVAILABLE}
    ):
        return _baseline_outcome(baseline_assessment)

    reason = call.reason or (
        "AI_OUTPUT_MISSING_RULE"
        if call.state is ProviderState.AVAILABLE
        else "AI_NOT_CONFIGURED"
    )
    return _Outcome(
        evaluation=RuleEvaluation(
            RuleResult.UNKNOWN,
            {"reason": reason, "provider_state": call.state.value},
            _EXPECTED[rule_id],
            reason=reason,
        ),
        confidence=0.0,
        source_evidence_ids=(context_evidence_id,),
        metadata=_AssessmentMetadata(
            provider="NONE" if call.state is ProviderState.NOT_CONFIGURED else "UNAVAILABLE",
            model=None,
            prompt_id="semantic-fallback",
            prompt_version="2",
            configuration_version="2",
            reasoning_summary=reason,
        ),
        provider_used=False,
    )


def _baseline_outcome(assessment: BaselineAssessment) -> _Outcome:
    return _Outcome(
        evaluation=RuleEvaluation(
            assessment.result,
            assessment.observed_value,
            _EXPECTED[assessment.rule_id],
            reason=assessment.reason,
        ),
        confidence=assessment.confidence,
        source_evidence_ids=assessment.evidence_ids,
        metadata=_AssessmentMetadata(
            provider="DETERMINISTIC_BASELINE",
            model=None,
            prompt_id="deterministic-semantic-baseline",
            prompt_version="1",
            configuration_version=BASELINE_VERSION,
            reasoning_summary=assessment.reasoning_summary,
        ),
        provider_used=False,
    )


def _deterministic_outcome(
    rule_id: str,
    title: str | None,
    structured: dict[str, Any],
    context_evidence_id: str,
) -> _Outcome | None:
    metadata = _AssessmentMetadata(
        provider="DETERMINISTIC",
        model=None,
        prompt_id="deterministic-m7",
        prompt_version="2",
        configuration_version="2",
        reasoning_summary="",
    )

    if rule_id == "BR-GEO-028" and not (title or "").strip():
        return _Outcome(
            evaluation=RuleEvaluation(
                RuleResult.FAIL,
                {"title_present": False},
                _EXPECTED[rule_id],
                reason="TITLE_MISSING",
            ),
            confidence=1.0,
            source_evidence_ids=(context_evidence_id,),
            metadata=replace(
                metadata,
                reasoning_summary="Title is deterministically absent; semantic representativeness cannot compensate for absence.",
            ),
        )

    if rule_id == "BR-GEO-034":
        if not structured["present"]:
            result = RuleResult.WARNING
            reason = "STRUCTURED_DATA_ABSENT"
        elif structured["invalid_blocks"]:
            result = RuleResult.FAIL
            reason = "STRUCTURED_DATA_NOT_INTERPRETABLE"
        else:
            result = RuleResult.PASS
            reason = None
        return _Outcome(
            evaluation=RuleEvaluation(
                result,
                structured,
                _EXPECTED[rule_id],
                reason=reason,
            ),
            confidence=1.0,
            source_evidence_ids=(context_evidence_id,),
            metadata=replace(
                metadata,
                reasoning_summary=(
                    "Structured Data presence/syntax is evaluated deterministically from preserved JSON-LD blocks; "
                    "absence is a modest readiness gap, not a hard failure."
                ),
            ),
        )

    if rule_id == "BR-GEO-035":
        if not structured["present"]:
            result = RuleResult.NOT_APPLICABLE
            reason = "STRUCTURED_DATA_ABSENT"
        elif structured["types"]:
            result = RuleResult.PASS
            reason = None
        elif structured["invalid_blocks"]:
            result = RuleResult.NOT_APPLICABLE
            reason = "BR_GEO_034_BLOCKS_TYPE_IDENTIFICATION"
        else:
            result = RuleResult.WARNING
            reason = "STRUCTURED_DATA_TYPE_NOT_IDENTIFIABLE"
        return _Outcome(
            evaluation=RuleEvaluation(
                result,
                structured,
                _EXPECTED[rule_id],
                reason=reason,
            ),
            confidence=1.0,
            source_evidence_ids=(context_evidence_id,),
            metadata=replace(
                metadata,
                reasoning_summary="Structured Data types are identified deterministically from preserved @type values.",
            ),
        )
    return None


def _normalized_response_is_valid(
    response: SemanticProviderResponse,
    allowed: frozenset[str],
) -> bool:
    if len(response.secondary_intents) > 5:
        return False
    seen: set[str] = set()
    for assessment in response.assessments:
        if assessment.rule_id not in SEMANTIC_RULE_IDS or assessment.rule_id in seen:
            return False
        seen.add(assessment.rule_id)
        if not 0 <= assessment.confidence <= 1:
            return False
        if set(assessment.evidence_ids) - allowed:
            return False
        if (
            assessment.result not in {RuleResult.UNKNOWN, RuleResult.NOT_APPLICABLE}
            and not assessment.evidence_ids
        ):
            return False
    for entity in response.entities:
        if not 0 <= entity.confidence <= 1:
            return False
        if not entity.evidence_ids or set(entity.evidence_ids) - allowed:
            return False
    return True


def _resolve_mode(states: tuple[ProviderState, ...]) -> AuditMode:
    if not states or all(state is ProviderState.NOT_CONFIGURED for state in states):
        return AuditMode.NO_AI
    if any(
        state in {ProviderState.UNAVAILABLE, ProviderState.NOT_CONFIGURED}
        for state in states
    ):
        return AuditMode.DEGRADED
    return AuditMode.FULL


def _finding(
    definition: RuleDefinition,
    execution: RuleExecution,
    persistence: AuditPersistence,
) -> Finding | None:
    if execution.result not in {RuleResult.FAIL, RuleResult.WARNING}:
        return None
    if not execution.evidence_ids:
        return None
    if execution.device is DeviceContext.DESKTOP:
        finding_device = FindingDevice.DESKTOP
    elif execution.device is DeviceContext.MOBILE:
        finding_device = FindingDevice.MOBILE
    else:
        return None

    finding = Finding(
        finding_id=new_id("FND"),
        audit_id=execution.audit_id,
        rule_id=execution.rule_id,
        rule_execution_id=execution.rule_execution_id,
        page_id=execution.page_id,
        device=finding_device,
        category=definition.category,
        severity=definition.severity,
        source="semantic-analysis",
        title=definition.name,
        observed_value=execution.observed_value,
        expected_condition=execution.expected_condition,
        evidence_ids=execution.evidence_ids,
        status="OPEN",
    )
    persistence.findings.add(finding)
    return finding


def m7_rule_ids() -> tuple[str, ...]:
    return tuple(item.rule_id for item in _M7_DEFINITIONS)
