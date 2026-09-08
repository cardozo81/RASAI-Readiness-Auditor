"""RASAi scoring, Coverage, Confidence and Consolidation for SCORE-GEO-004."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Iterable

from rasai.domain import DeviceContext, RuleExecution, RuleResult, new_id, utc_now
from rasai.score_geo_004 import (
    MIN_OVERALL_COVERAGE,
    MIN_PARTIAL_COVERAGE,
    SCORING_VERSION,
    method_trace_limitations,
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


DIMENSIONS = (
    "TECHNICAL_ACCESSIBILITY",
    "INDEXABILITY",
    "CONTENT_EXTRACTABILITY",
    "SEMANTIC_STRUCTURE",
    "ENTITY_CLARITY",
    "STRUCTURED_DATA",
    "ANSWERABILITY",
    "CITATION_READINESS",
    "EVIDENCE_TRUST",
    "INTENT_COVERAGE",
)


@dataclass(frozen=True, slots=True)
class RuleScoringMetadata:
    dimension: str | None
    weight: float = 1.0
    warning_factor: float = 0.5
    scoring_group: str | None = None


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
    """Reproducible SCORE-GEO-004 calculator with no website or AI execution.

    The engine distinguishes evidence/execution gaps, unresolved applicability and
    legitimate NOT_APPLICABLE states. A legitimate NOT_APPLICABLE dimension is
    excluded from Overall instead of receiving zero. An applicable dimension that
    is not sufficiently measured blocks a consolidated Overall.
    """

    def score(
        self,
        *,
        audit_id: str,
        executions: Iterable[RuleExecution],
        devices: Iterable[DeviceContext] | None = None,
    ) -> ScoringResult:
        execution_list = tuple(executions)
        selected_devices = tuple(dict.fromkeys(devices or (DeviceContext.DESKTOP, DeviceContext.MOBILE)))
        if not selected_devices:
            raise ValueError("scoring requires at least one device")
        scores: list[Score] = []
        contributions: list[ScoreContribution] = []
        for device in selected_devices:
            for dimension in DIMENSIONS:
                dimension_executions = tuple(
                    execution
                    for execution in execution_list
                    if _metadata(execution.rule_id).dimension == dimension
                    and (execution.device is None or execution.device is device)
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
            device: self._overall(audit_id, device, tuple(score for score in scores if score.device is device))
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

        buckets: dict[tuple[str, str], list[RuleExecution]] = {}
        for execution in executions:
            metadata = _metadata(execution.rule_id)
            scope = execution.page_id or "GLOBAL"
            group = metadata.scoring_group or f"RULE:{execution.rule_id}"
            buckets.setdefault((scope, group), []).append(execution)

        applicable_weight = 0.0
        evaluated_weight = 0.0
        numerator = 0.0
        contribution_rows: list[ScoreContribution] = []
        evidence_complete = True
        errors = 0
        unknowns = 0

        for (_scope, group), items in buckets.items():
            applicable_items = [item for item in items if item.result is not RuleResult.NOT_APPLICABLE]
            if not applicable_items:
                continue
            weight = max(_metadata(item.rule_id).weight for item in applicable_items)
            applicable_weight += weight
            evaluated = [item for item in applicable_items if item.result in {RuleResult.PASS, RuleResult.WARNING, RuleResult.FAIL}]
            errors += sum(item.result is RuleResult.ERROR for item in applicable_items)
            unknowns += sum(item.result is RuleResult.UNKNOWN for item in applicable_items)
            evidence_complete = evidence_complete and all(bool(item.evidence_ids) for item in evaluated)

            representative: RuleExecution
            factor: float | None
            if evaluated:
                representative = min(evaluated, key=lambda item: _factor(item.result, _metadata(item.rule_id).warning_factor) or 0.0)
                factor = _factor(representative.result, _metadata(representative.rule_id).warning_factor)
                assert factor is not None
                evaluated_weight += weight
                numerator += weight * factor
            else:
                representative = applicable_items[0]
                factor = None

            contribution_rows.append(
                ScoreContribution(
                    contribution_id=new_id("SCN"), score_id=score_id,
                    rule_id=representative.rule_id,
                    rule_execution_id=representative.rule_execution_id,
                    dimension=dimension, device=device, weight=weight,
                    result=representative.result, result_factor=factor,
                    effective_contribution=(weight * factor) if factor is not None else None,
                    scoring_group=None if group.startswith("RULE:") else group,
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
                score_id=score_id, audit_id=audit_id, dimension=dimension, device=device,
                value=round(value, 6) if value is not None else None,
                coverage=round(coverage, 6), confidence=confidence,
                consolidation_status=consolidation, scoring_version=SCORING_VERSION,
                calculated_at=utc_now(), limitations=tuple(limitations),
            ),
            tuple(contribution_rows),
        )

    def _overall(self, audit_id: str, device: DeviceContext, dimensions: tuple[Score, ...]) -> Score:
        applicable = tuple(
            item for item in dimensions
            if item.consolidation_status is not ConsolidationStatus.NOT_APPLICABLE
        )
        limitations: list[str] = [
            f"DIMENSION_NOT_APPLICABLE:{item.dimension}"
            for item in dimensions
            if item.consolidation_status is ConsolidationStatus.NOT_APPLICABLE
        ]
        blocking = tuple(
            item for item in applicable
            if item.consolidation_status is ConsolidationStatus.NOT_CONSOLIDATED or item.value is None
        )
        limitations.extend(f"DIMENSION_NOT_CONSOLIDATED:{item.dimension}" for item in blocking)

        coverage = sum(item.coverage for item in applicable) / len(applicable) if applicable else 0.0
        confidence = (
            min((item.confidence for item in applicable), key=_confidence_rank)
            if applicable else ScoreConfidence.UNAVAILABLE
        )
        complete_contract = len(dimensions) == len(DIMENSIONS) and bool(applicable) and not blocking

        if not complete_contract:
            return Score(
                score_id=new_id("SCR"), audit_id=audit_id, dimension="OVERALL_READINESS", device=device,
                value=None, coverage=round(coverage, 6), confidence=confidence,
                consolidation_status=ConsolidationStatus.NOT_CONSOLIDATED,
                scoring_version=SCORING_VERSION, calculated_at=utc_now(),
                limitations=tuple((*limitations, *method_trace_limitations())),
            )

        values = [float(item.value) for item in applicable if item.value is not None]
        value = sum(values) / len(values)
        if coverage >= MIN_OVERALL_COVERAGE and confidence in {ScoreConfidence.HIGH, ScoreConfidence.MEDIUM}:
            consolidation = ConsolidationStatus.CONSOLIDATED
        elif coverage >= MIN_PARTIAL_COVERAGE and confidence is not ScoreConfidence.UNAVAILABLE:
            consolidation = ConsolidationStatus.PARTIAL
            limitations.append("OVERALL_MEASUREMENT_BELOW_CONSOLIDATION_GATE")
        else:
            consolidation = ConsolidationStatus.NOT_CONSOLIDATED
            limitations.append("OVERALL_MEASUREMENT_BELOW_MINIMUM_GATE")

        return Score(
            score_id=new_id("SCR"), audit_id=audit_id, dimension="OVERALL_READINESS", device=device,
            value=round(value, 6), coverage=round(coverage, 6), confidence=confidence,
            consolidation_status=consolidation, scoring_version=SCORING_VERSION,
            calculated_at=utc_now(), limitations=tuple((*limitations, *method_trace_limitations())),
        )


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
    try:
        number = int(rule_id.rsplit("-", 1)[1])
    except (ValueError, IndexError):
        return RuleScoringMetadata(None)

    if number in {1, 2, 4, 52, 53, 54}:
        return RuleScoringMetadata(None)
    if number in {3, 55}:
        return RuleScoringMetadata(
            "TECHNICAL_ACCESSIBILITY", weight=0.25, warning_factor=0.80, scoring_group="SITEMAP"
        )
    if number in {17, 18, 56}:
        return RuleScoringMetadata(
            "TECHNICAL_ACCESSIBILITY", weight=0.60, warning_factor=0.60, scoring_group="ROBOTS"
        )
    if number in {5, 6}:
        return RuleScoringMetadata(
            "TECHNICAL_ACCESSIBILITY", weight=1.25, scoring_group="PAGE_ACCESS"
        )
    if number in {7, 8, 21, 22, 50}:
        return RuleScoringMetadata("TECHNICAL_ACCESSIBILITY", scoring_group=_technical_group(number))
    if 11 <= number <= 16 or number == 23:
        return RuleScoringMetadata("INDEXABILITY", scoring_group=_index_group(number))
    if number in {9, 10, 19, 20, 24, 25, 26, 27}:
        return RuleScoringMetadata("CONTENT_EXTRACTABILITY", scoring_group=_content_group(number))
    if 28 <= number <= 30:
        return RuleScoringMetadata("SEMANTIC_STRUCTURE", scoring_group={28:"SEMANTIC_TITLE",29:"SEMANTIC_HIERARCHY",30:"SEMANTIC_TOPIC"}[number])
    if 31 <= number <= 33:
        return RuleScoringMetadata("ENTITY_CLARITY", scoring_group={31:"ENTITY_PRIMARY",32:"ENTITY_CONTEXT",33:"ENTITY_AMBIGUITY"}[number])
    if 34 <= number <= 37:
        return RuleScoringMetadata(
            "STRUCTURED_DATA",
            warning_factor=0.80 if number == 34 else 0.50,
            scoring_group="STRUCTURED_DATA_SYNTAX" if number in {34,35} else "STRUCTURED_DATA_CONSISTENCY",
        )
    if 38 <= number <= 40:
        return RuleScoringMetadata("ANSWERABILITY", scoring_group="PRIMARY_INTENT" if number == 38 else "PRIMARY_ANSWERS")
    if 41 <= number <= 44:
        return RuleScoringMetadata("CITATION_READINESS", scoring_group={41:"FACTUAL_CLAIMS",42:"FACTUAL_CONTEXT",43:"FACTUAL_CONTEXT",44:"INFERENCE_LOAD"}[number])
    if 45 <= number <= 47:
        return RuleScoringMetadata("EVIDENCE_TRUST", scoring_group={45:"ATTRIBUTION",46:"RESPONSIBILITY",47:"FRESHNESS"}[number])
    if number in {48, 49}:
        return RuleScoringMetadata("INTENT_COVERAGE", scoring_group="INTENT_SET" if number == 48 else "INTENT_GAPS")
    if number == 51:
        return RuleScoringMetadata("CONTENT_EXTRACTABILITY", scoring_group="DUPLICATE_CONTENT")
    return RuleScoringMetadata(None)


def _technical_group(number: int) -> str | None:
    return {
        5: "PAGE_ACCESS", 6: "PAGE_ACCESS", 7: "REDIRECT", 8: "REDIRECT",
        17: "ROBOTS", 18: "ROBOTS", 21: "SPA_ROUTE", 22: "SPA_NAVIGATION", 50: "INTERNAL_LINKS",
    }.get(number)


def _index_group(number: int) -> str:
    if number in {11, 12, 15}:
        return "INDEX_DIRECTIVES"
    if number in {13, 14}:
        return "CANONICAL"
    return "SOFT_ERROR"


def _content_group(number: int) -> str | None:
    if number in {9, 10}:
        return "RENDER_ACCESS"
    if number in {19, 20, 24}:
        return "JS_CONTENT"
    if number in {25, 26, 27}:
        return "CONTENT_EXTRACTION"
    return None
