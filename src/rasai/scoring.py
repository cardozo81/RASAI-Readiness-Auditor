"""RASAi scoring, Coverage, Confidence and Consolidation for SCORE-GEO-004."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Iterable

from rasai.domain import DeviceContext, RuleExecution, RuleResult, new_id, utc_now
from rasai.score_geo_004 import (
    CRITICAL_DIMENSIONS,
    CRITICAL_GATES,
    DIMENSION_WEIGHTS,
    EVIDENCE_ROLE_DETERMINISTIC_PRIMARY,
    FEATURE_ORDER,
    GROUP_WEIGHTS,
    MIN_OVERALL_COVERAGE,
    MIN_PARTIAL_COVERAGE,
    SCORING_VERSION,
    method_trace_limitations,
    rule_contract,
)


class ScoreConfidence(StrEnum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    UNAVAILABLE = "UNAVAILABLE"


class ConsolidationStatus(StrEnum):
    CONSOLIDATED = "CONSOLIDATED"
    PARTIAL = "PARTIAL"
    NOT_CONSOLIDATED = "NOT_CONSOLIDATED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


DIMENSIONS = FEATURE_ORDER


@dataclass(frozen=True, slots=True)
class RuleScoringMetadata:
    dimension: str | None
    weight: float = 1.0
    warning_factor: float = 0.5
    scoring_group: str | None = None
    evidence_role: str = EVIDENCE_ROLE_DETERMINISTIC_PRIMARY


@dataclass(frozen=True, slots=True)
class ScoreContribution:
    contribution_id: str
    score_id: str
    rule_id: str
    rule_execution_id: str
    dimension: str
    device: DeviceContext
    weight: float
    result: RuleResult
    result_factor: float | None
    effective_contribution: float | None
    scoring_group: str | None


@dataclass(frozen=True, slots=True)
class Score:
    score_id: str
    audit_id: str
    dimension: str
    device: DeviceContext
    value: float | None
    coverage: float
    confidence: ScoreConfidence
    consolidation_status: ConsolidationStatus
    scoring_version: str
    calculated_at: datetime
    limitations: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ScoringResult:
    scores: tuple[Score, ...]
    contributions: tuple[ScoreContribution, ...]
    overall_by_device: dict[DeviceContext, Score]


class ScoringEngine:
    """Reproducible hierarchical SCORE-GEO-004 calculator.

    Rule executions are first resolved inside one page/global scope, then each
    scoring-group weight is divided across its applicable scopes.  Therefore a
    group keeps the same relative importance when an audit grows from a few pages
    to hundreds of pages.

    Deterministic facts have precedence over AI-correlative executions in the
    same scope/group.  AI may resolve an otherwise unevaluated group, but it may
    not override an evaluated deterministic PASS/WARNING/FAIL.
    """

    def score(
        self,
        *,
        audit_id: str,
        executions: Iterable[RuleExecution],
        devices: Iterable[DeviceContext] | None = None,
    ) -> ScoringResult:
        execution_list = tuple(executions)
        selected_devices = tuple(
            dict.fromkeys(devices or (DeviceContext.DESKTOP, DeviceContext.MOBILE))
        )
        if not selected_devices:
            raise ValueError("scoring requires at least one device")

        scores: list[Score] = []
        contributions: list[ScoreContribution] = []
        for device in selected_devices:
            device_executions = tuple(
                execution
                for execution in execution_list
                if execution.device is None or execution.device is device
            )
            for dimension in DIMENSIONS:
                dimension_executions = tuple(
                    execution
                    for execution in device_executions
                    if _metadata(execution.rule_id).dimension == dimension
                )
                score, score_contributions = self._dimension_score(
                    audit_id=audit_id,
                    device=device,
                    dimension=dimension,
                    executions=dimension_executions,
                )
                scores.append(score)
                contributions.extend(score_contributions)

        overall = {
            device: self._overall(
                audit_id,
                device,
                tuple(score for score in scores if score.device is device),
                tuple(
                    execution
                    for execution in execution_list
                    if execution.device is None or execution.device is device
                ),
            )
            for device in selected_devices
        }
        return ScoringResult(tuple(scores), tuple(contributions), overall)

    def _dimension_score(
        self,
        *,
        audit_id: str,
        device: DeviceContext,
        dimension: str,
        executions: tuple[RuleExecution, ...],
    ) -> tuple[Score, tuple[ScoreContribution, ...]]:
        score_id = new_id("SCR")

        if not executions:
            return (
                Score(
                    score_id=score_id,
                    audit_id=audit_id,
                    dimension=dimension,
                    device=device,
                    value=None,
                    coverage=0.0,
                    confidence=ScoreConfidence.UNAVAILABLE,
                    consolidation_status=ConsolidationStatus.NOT_CONSOLIDATED,
                    scoring_version=SCORING_VERSION,
                    calculated_at=utc_now(),
                    limitations=("NO_RULE_EXECUTIONS",),
                ),
                (),
            )

        # group -> scope -> executions.  Scope is page-level whenever possible;
        # GLOBAL is used for resources such as robots/sitemap.
        grouped: dict[str, dict[str, list[RuleExecution]]] = {}
        for execution in executions:
            metadata = _metadata(execution.rule_id)
            if metadata.dimension != dimension:
                continue
            group = metadata.scoring_group or f"RULE:{execution.rule_id}"
            scope = execution.page_id or "GLOBAL"
            grouped.setdefault(group, {}).setdefault(scope, []).append(execution)

        applicable_weight = 0.0
        evaluated_weight = 0.0
        numerator = 0.0
        contribution_rows: list[ScoreContribution] = []
        evidence_complete = True
        errors = 0
        unknowns = 0

        for group, scopes in grouped.items():
            group_weight = GROUP_WEIGHTS.get(dimension, {}).get(group)
            if group_weight is None:
                # Contracted scoring groups must have a fixed weight.  Unknown
                # groups are excluded rather than receiving an accidental weight.
                continue

            applicable_scopes: list[tuple[str, list[RuleExecution]]] = []
            for scope, items in scopes.items():
                applicable_items = [
                    item for item in items if item.result is not RuleResult.NOT_APPLICABLE
                ]
                if applicable_items:
                    applicable_scopes.append((scope, applicable_items))

            if not applicable_scopes:
                continue

            applicable_weight += group_weight
            scope_weight = group_weight / len(applicable_scopes)

            for _scope, applicable_items in applicable_scopes:
                errors += sum(item.result is RuleResult.ERROR for item in applicable_items)
                unknowns += sum(item.result is RuleResult.UNKNOWN for item in applicable_items)
                representative, factor = _representative(applicable_items)
                if factor is not None:
                    evaluated_weight += scope_weight
                    numerator += scope_weight * factor
                    evidence_complete = evidence_complete and bool(representative.evidence_ids)

                contribution_rows.append(
                    ScoreContribution(
                        contribution_id=new_id("SCN"),
                        score_id=score_id,
                        rule_id=representative.rule_id,
                        rule_execution_id=representative.rule_execution_id,
                        dimension=dimension,
                        device=device,
                        weight=scope_weight,
                        result=representative.result,
                        result_factor=factor,
                        effective_contribution=(scope_weight * factor) if factor is not None else None,
                        scoring_group=group,
                    )
                )

        limitations: list[str] = []
        if applicable_weight == 0:
            if any(_not_applicable_is_prerequisite_blocked(item) for item in executions):
                limitations.append("APPLICABILITY_UNRESOLVED:PREREQUISITE_BLOCKED")
                consolidation = ConsolidationStatus.NOT_CONSOLIDATED
            else:
                limitations.append("NO_APPLICABLE_RULES")
                consolidation = ConsolidationStatus.NOT_APPLICABLE
            return (
                Score(
                    score_id=score_id,
                    audit_id=audit_id,
                    dimension=dimension,
                    device=device,
                    value=None,
                    coverage=0.0,
                    confidence=ScoreConfidence.UNAVAILABLE,
                    consolidation_status=consolidation,
                    scoring_version=SCORING_VERSION,
                    calculated_at=utc_now(),
                    limitations=tuple(limitations),
                ),
                tuple(contribution_rows),
            )

        coverage = evaluated_weight / applicable_weight
        value = (numerator / evaluated_weight * 100.0) if evaluated_weight else None
        confidence = _confidence(coverage, evidence_complete=evidence_complete, errors=errors)
        consolidation = _consolidation(coverage, confidence)
        if unknowns:
            limitations.append(f"UNKNOWN_RULE_EXECUTIONS:{unknowns}")
        if errors:
            limitations.append(f"ERROR_RULE_EXECUTIONS:{errors}")
        if not evidence_complete:
            limitations.append("EVALUATED_EXECUTION_WITHOUT_EVIDENCE")

        return (
            Score(
                score_id=score_id,
                audit_id=audit_id,
                dimension=dimension,
                device=device,
                value=round(value, 6) if value is not None else None,
                coverage=round(coverage, 6),
                confidence=confidence,
                consolidation_status=consolidation,
                scoring_version=SCORING_VERSION,
                calculated_at=utc_now(),
                limitations=tuple(limitations),
            ),
            tuple(contribution_rows),
        )

    def _overall(
        self,
        audit_id: str,
        device: DeviceContext,
        dimensions: tuple[Score, ...],
        executions: tuple[RuleExecution, ...],
    ) -> Score:
        applicable = tuple(
            item
            for item in dimensions
            if item.consolidation_status is not ConsolidationStatus.NOT_APPLICABLE
        )
        limitations: list[str] = [
            f"DIMENSION_NOT_APPLICABLE:{item.dimension}"
            for item in dimensions
            if item.consolidation_status is ConsolidationStatus.NOT_APPLICABLE
        ]

        if len(dimensions) != len(DIMENSIONS):
            limitations.append("INCOMPLETE_DIMENSION_CONTRACT")

        total_weight = sum(DIMENSION_WEIGHTS[item.dimension] for item in applicable)
        measured = tuple(item for item in applicable if item.value is not None)
        measured_weight = sum(DIMENSION_WEIGHTS[item.dimension] for item in measured)

        coverage = (
            sum(DIMENSION_WEIGHTS[item.dimension] * item.coverage for item in applicable)
            / total_weight
            if total_weight
            else 0.0
        )
        value = (
            sum(DIMENSION_WEIGHTS[item.dimension] * float(item.value) for item in measured)
            / measured_weight
            if measured_weight
            else None
        )
        confidence = _overall_confidence(applicable)

        critical_measurement_blockers = tuple(
            item
            for item in applicable
            if item.dimension in CRITICAL_DIMENSIONS
            and (
                item.value is None
                or item.consolidation_status is ConsolidationStatus.NOT_CONSOLIDATED
            )
        )
        for item in critical_measurement_blockers:
            limitations.append(f"CRITICAL_DIMENSION_NOT_CONSOLIDATED:{item.dimension}")

        for item in applicable:
            if item.dimension in CRITICAL_DIMENSIONS:
                continue
            if item.value is None or item.consolidation_status is ConsolidationStatus.NOT_CONSOLIDATED:
                limitations.append(f"DIMENSION_MEASUREMENT_LIMITED:{item.dimension}")

        gate_states = _critical_gate_states(executions)
        for gate, state in gate_states.items():
            limitations.append(f"CRITICAL_GATE:{gate}:{state}")
        readiness_status = _readiness_status(gate_states)
        limitations.append(f"READINESS_STATUS:{readiness_status}")

        if value is None:
            consolidation = ConsolidationStatus.NOT_CONSOLIDATED
            limitations.append("OVERALL_HAS_NO_EVALUATED_DIMENSION")
        elif critical_measurement_blockers:
            consolidation = ConsolidationStatus.NOT_CONSOLIDATED
            limitations.append("CRITICAL_MEASUREMENT_GATE_NOT_SATISFIED")
        elif coverage >= MIN_OVERALL_COVERAGE and confidence in {
            ScoreConfidence.HIGH,
            ScoreConfidence.MEDIUM,
        }:
            consolidation = ConsolidationStatus.CONSOLIDATED
        elif coverage >= MIN_PARTIAL_COVERAGE and confidence is not ScoreConfidence.UNAVAILABLE:
            consolidation = ConsolidationStatus.PARTIAL
            limitations.append("OVERALL_MEASUREMENT_BELOW_CONSOLIDATION_GATE")
        else:
            consolidation = ConsolidationStatus.NOT_CONSOLIDATED
            limitations.append("OVERALL_MEASUREMENT_BELOW_MINIMUM_GATE")

        return Score(
            score_id=new_id("SCR"),
            audit_id=audit_id,
            dimension="OVERALL_READINESS",
            device=device,
            value=round(value, 6) if value is not None else None,
            coverage=round(coverage, 6),
            confidence=confidence,
            consolidation_status=consolidation,
            scoring_version=SCORING_VERSION,
            calculated_at=utc_now(),
            limitations=tuple((*limitations, *method_trace_limitations())),
        )


def _representative(
    applicable_items: list[RuleExecution] | tuple[RuleExecution, ...],
) -> tuple[RuleExecution, float | None]:
    evaluated = [
        item
        for item in applicable_items
        if item.result in {RuleResult.PASS, RuleResult.WARNING, RuleResult.FAIL}
    ]
    deterministic = [
        item
        for item in evaluated
        if _metadata(item.rule_id).evidence_role == EVIDENCE_ROLE_DETERMINISTIC_PRIMARY
    ]
    candidates = deterministic or evaluated
    if candidates:
        representative = min(
            candidates,
            key=lambda item: _factor(
                item.result,
                _metadata(item.rule_id).warning_factor,
            )
            if _factor(item.result, _metadata(item.rule_id).warning_factor) is not None
            else 2.0,
        )
        return representative, _factor(
            representative.result,
            _metadata(representative.rule_id).warning_factor,
        )

    deterministic_unresolved = [
        item
        for item in applicable_items
        if _metadata(item.rule_id).evidence_role == EVIDENCE_ROLE_DETERMINISTIC_PRIMARY
    ]
    representative = deterministic_unresolved[0] if deterministic_unresolved else applicable_items[0]
    return representative, None


def _critical_gate_states(executions: tuple[RuleExecution, ...]) -> dict[str, str]:
    states: dict[str, str] = {}
    for gate, (dimension, groups) in CRITICAL_GATES.items():
        selected = [
            item
            for item in executions
            if _metadata(item.rule_id).dimension == dimension
            and _metadata(item.rule_id).scoring_group in groups
        ]
        if not selected:
            states[gate] = "UNKNOWN"
            continue

        scoped: dict[tuple[str, str], list[RuleExecution]] = {}
        for item in selected:
            group = _metadata(item.rule_id).scoring_group or item.rule_id
            scoped.setdefault((item.page_id or "GLOBAL", group), []).append(item)

        saw_applicable = False
        saw_warning = False
        saw_unresolved = False
        blocked = False
        for items in scoped.values():
            applicable = [item for item in items if item.result is not RuleResult.NOT_APPLICABLE]
            if not applicable:
                continue
            saw_applicable = True
            _representative_execution, factor = _representative(applicable)
            if factor is None:
                saw_unresolved = True
            elif factor <= 0.0:
                blocked = True
                break
            elif factor < 1.0:
                saw_warning = True

        if blocked:
            states[gate] = "BLOCKED"
        elif not saw_applicable or saw_unresolved:
            states[gate] = "UNKNOWN"
        elif saw_warning:
            states[gate] = "WARNING"
        else:
            states[gate] = "PASS"
    return states


def _readiness_status(gates: dict[str, str]) -> str:
    values = set(gates.values())
    if "BLOCKED" in values:
        return "BLOCKED"
    if "UNKNOWN" in values:
        return "UNKNOWN"
    if "WARNING" in values:
        return "ATTENTION"
    return "READY"


def _not_applicable_is_prerequisite_blocked(execution: RuleExecution) -> bool:
    if execution.result is not RuleResult.NOT_APPLICABLE:
        return False
    observed = execution.observed_value
    if not isinstance(observed, dict):
        return False
    reason = observed.get("reason")
    return isinstance(reason, str) and "PREREQUISITE_BLOCKED" in reason.upper()


def _factor(result: RuleResult, warning_factor: float) -> float | None:
    return {
        RuleResult.PASS: 1.0,
        RuleResult.WARNING: warning_factor,
        RuleResult.FAIL: 0.0,
    }.get(result)


def _confidence(coverage: float, *, evidence_complete: bool, errors: int) -> ScoreConfidence:
    if coverage <= 0:
        return ScoreConfidence.UNAVAILABLE
    if coverage >= 0.90 and evidence_complete and errors == 0:
        return ScoreConfidence.HIGH
    if coverage >= 0.80 and errors == 0:
        return ScoreConfidence.MEDIUM
    return ScoreConfidence.LOW


def _overall_confidence(dimensions: tuple[Score, ...]) -> ScoreConfidence:
    if not dimensions:
        return ScoreConfidence.UNAVAILABLE
    measured = tuple(item for item in dimensions if item.value is not None)
    if not measured:
        return ScoreConfidence.UNAVAILABLE

    critical = tuple(item for item in dimensions if item.dimension in CRITICAL_DIMENSIONS)
    if any(item.confidence in {ScoreConfidence.UNAVAILABLE, ScoreConfidence.LOW} for item in critical):
        return ScoreConfidence.LOW

    total_weight = sum(DIMENSION_WEIGHTS[item.dimension] for item in dimensions)
    if total_weight <= 0:
        return ScoreConfidence.UNAVAILABLE
    weighted = sum(
        DIMENSION_WEIGHTS[item.dimension] * _confidence_value(item.confidence)
        for item in dimensions
    ) / total_weight
    if weighted >= 0.90:
        return ScoreConfidence.HIGH
    if weighted >= 0.70:
        return ScoreConfidence.MEDIUM
    return ScoreConfidence.LOW


def _confidence_value(value: ScoreConfidence) -> float:
    return {
        ScoreConfidence.UNAVAILABLE: 0.0,
        ScoreConfidence.LOW: 0.40,
        ScoreConfidence.MEDIUM: 0.75,
        ScoreConfidence.HIGH: 1.0,
    }[value]


def _consolidation(coverage: float, confidence: ScoreConfidence) -> ConsolidationStatus:
    if confidence is ScoreConfidence.UNAVAILABLE or coverage < 0.50:
        return ConsolidationStatus.NOT_CONSOLIDATED
    if coverage >= 0.80 and confidence in {ScoreConfidence.HIGH, ScoreConfidence.MEDIUM}:
        return ConsolidationStatus.CONSOLIDATED
    return ConsolidationStatus.PARTIAL


def _confidence_rank(value: ScoreConfidence) -> int:
    return {
        ScoreConfidence.UNAVAILABLE: 0,
        ScoreConfidence.LOW: 1,
        ScoreConfidence.MEDIUM: 2,
        ScoreConfidence.HIGH: 3,
    }[value]


def _metadata(rule_id: str) -> RuleScoringMetadata:
    contract = rule_contract(rule_id)
    if contract is None:
        return RuleScoringMetadata(None)
    return RuleScoringMetadata(
        dimension=contract.dimension,
        weight=contract.group_weight,
        warning_factor=contract.warning_factor,
        scoring_group=contract.scoring_group,
        evidence_role=contract.evidence_role,
    )
