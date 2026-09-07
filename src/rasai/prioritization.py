"""M10 prioritization model, remediation grouping and deterministic recommendations."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Iterable

from rasai.domain import Finding, FindingDevice, Severity, new_id
from rasai.remediation import recipe_for


class Impact(StrEnum):
    VERY_HIGH = "VERY_HIGH"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    MINIMAL = "MINIMAL"


class Effort(StrEnum):
    VERY_LOW = "VERY_LOW"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    VERY_HIGH = "VERY_HIGH"
    UNKNOWN = "UNKNOWN"


class PriorityConfidence(StrEnum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    UNAVAILABLE = "UNAVAILABLE"


class PriorityClass(StrEnum):
    P0 = "P0"
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"
    P4 = "P4"
    INFO = "INFO"


@dataclass(frozen=True, slots=True)
class RemediationGroup:
    group_id: str
    rule_id: str
    root_cause: str
    affected_findings: tuple[str, ...]
    affected_pages: tuple[str, ...]
    devices: tuple[FindingDevice, ...]
    severity: Severity
    impact: Impact
    confidence: PriorityConfidence
    effort: Effort
    priority_score: float
    priority_class: PriorityClass


@dataclass(frozen=True, slots=True)
class Recommendation:
    recommendation_id: str
    audit_id: str
    finding_id: str | None
    remediation_group_id: str | None
    device: FindingDevice
    title: str
    description: str
    impact: Impact
    effort: Effort
    confidence: PriorityConfidence
    priority_score: float
    priority_class: PriorityClass
    status: str = "OPEN"

    def __post_init__(self) -> None:
        if bool(self.finding_id) == bool(self.remediation_group_id):
            raise ValueError("recommendation must reference exactly one finding or remediation group")


@dataclass(frozen=True, slots=True)
class PrioritizationResult:
    groups: tuple[RemediationGroup, ...]
    recommendations: tuple[Recommendation, ...]


_SEVERITY_VALUE = {
    Severity.CRITICAL: 100.0,
    Severity.HIGH: 80.0,
    Severity.MEDIUM: 55.0,
    Severity.LOW: 30.0,
    Severity.INFO: 0.0,
}
_IMPACT_VALUE = {
    Impact.VERY_HIGH: 100.0,
    Impact.HIGH: 75.0,
    Impact.MEDIUM: 50.0,
    Impact.LOW: 25.0,
    Impact.MINIMAL: 10.0,
}
_CONFIDENCE_VALUE = {
    PriorityConfidence.HIGH: 100.0,
    PriorityConfidence.MEDIUM: 70.0,
    PriorityConfidence.LOW: 40.0,
    PriorityConfidence.UNAVAILABLE: 0.0,
}
_EASE_VALUE = {
    Effort.VERY_LOW: 100.0,
    Effort.LOW: 80.0,
    Effort.MEDIUM: 60.0,
    Effort.HIGH: 35.0,
    Effort.VERY_HIGH: 15.0,
    Effort.UNKNOWN: 50.0,
}

_SEVERITY_ORDER = {
    Severity.INFO: 0,
    Severity.LOW: 1,
    Severity.MEDIUM: 2,
    Severity.HIGH: 3,
    Severity.CRITICAL: 4,
}


class PriorityEngine:
    """Apply PRIORITY-GEO-001 without modifying website scores."""

    version = "PRIORITY-GEO-001"

    def prioritize(self, *, audit_id: str, findings: Iterable[Finding], total_pages: int) -> PrioritizationResult:
        finding_list = tuple(findings)
        if total_pages < 0:
            raise ValueError("total_pages must not be negative")
        for finding in finding_list:
            if finding.audit_id != audit_id:
                raise ValueError(f"finding belongs to another audit: {finding.finding_id}")

        grouped: dict[tuple[str, str], list[Finding]] = {}
        for finding in finding_list:
            root_cause = self._root_cause(finding)
            grouped.setdefault((finding.rule_id, root_cause), []).append(finding)

        groups: list[RemediationGroup] = []
        recommendations: list[Recommendation] = []
        for (_, root_cause), members in sorted(grouped.items(), key=lambda item: item[0]):
            group = self._build_group(root_cause=root_cause, findings=members, total_pages=total_pages)
            groups.append(group)
            recommendations.append(self._recommendation(audit_id=audit_id, group=group, findings=members))

        groups.sort(key=lambda group: (-group.priority_score, group.rule_id, group.group_id))
        by_group = {recommendation.remediation_group_id: recommendation for recommendation in recommendations}
        recommendations = [by_group[group.group_id] for group in groups]
        return PrioritizationResult(tuple(groups), tuple(recommendations))

    @staticmethod
    def priority_score(*, severity: Severity, impact: Impact, confidence: PriorityConfidence, effort: Effort) -> float:
        score = (
            _SEVERITY_VALUE[severity] * 0.45
            + _IMPACT_VALUE[impact] * 0.30
            + _CONFIDENCE_VALUE[confidence] * 0.15
            + _EASE_VALUE[effort] * 0.10
        )
        return round(score, 2)

    @classmethod
    def priority_class(
        cls,
        *,
        severity: Severity,
        impact: Impact,
        confidence: PriorityConfidence,
        effort: Effort,
        category: str,
    ) -> PriorityClass:
        if severity is Severity.INFO:
            return PriorityClass.INFO
        if cls._is_p0(severity=severity, impact=impact, category=category):
            return PriorityClass.P0
        score = cls.priority_score(severity=severity, impact=impact, confidence=confidence, effort=effort)
        if score >= 75:
            return PriorityClass.P1
        if score >= 60:
            return PriorityClass.P2
        if score >= 40:
            return PriorityClass.P3
        return PriorityClass.P4

    def _build_group(self, *, root_cause: str, findings: list[Finding], total_pages: int) -> RemediationGroup:
        severity = max((finding.severity for finding in findings), key=_SEVERITY_ORDER.__getitem__)
        pages = tuple(sorted({finding.page_id for finding in findings if finding.page_id is not None}))
        devices = tuple(sorted({finding.device for finding in findings}, key=lambda device: device.value))
        impact = self._impact(findings=findings, affected_pages=pages, devices=devices, total_pages=total_pages)
        confidence = self._confidence(findings)
        effort = self._effort(findings[0].category)
        score = self.priority_score(severity=severity, impact=impact, confidence=confidence, effort=effort)
        pclass = self.priority_class(
            severity=severity,
            impact=impact,
            confidence=confidence,
            effort=effort,
            category=findings[0].category,
        )
        return RemediationGroup(
            group_id=new_id("RMG"),
            rule_id=findings[0].rule_id,
            root_cause=root_cause,
            affected_findings=tuple(sorted(finding.finding_id for finding in findings)),
            affected_pages=pages,
            devices=devices,
            severity=severity,
            impact=impact,
            confidence=confidence,
            effort=effort,
            priority_score=score,
            priority_class=pclass,
        )

    @staticmethod
    def _root_cause(finding: Finding) -> str:
        expected = " ".join((finding.expected_condition or "").split())
        return f"{finding.rule_id}:{finding.category}:{expected or 'EXPECTED_CONDITION_UNSPECIFIED'}"

    @staticmethod
    def _impact(
        *,
        findings: list[Finding],
        affected_pages: tuple[str, ...],
        devices: tuple[FindingDevice, ...],
        total_pages: int,
    ) -> Impact:
        if any(finding.page_id is None for finding in findings):
            return Impact.VERY_HIGH
        if total_pages > 0 and len(affected_pages) >= total_pages:
            return Impact.VERY_HIGH if len(devices) > 1 or FindingDevice.BOTH in devices else Impact.HIGH
        if len(affected_pages) > 1 or len(devices) > 1 or FindingDevice.BOTH in devices:
            return Impact.MEDIUM
        if affected_pages:
            return Impact.LOW
        return Impact.MINIMAL

    @staticmethod
    def _confidence(findings: list[Finding]) -> PriorityConfidence:
        sources = {finding.source.lower() for finding in findings}
        if any("semantic" in source or "ai" in source for source in sources):
            return PriorityConfidence.MEDIUM
        if all("deterministic" in source or "http" in source for source in sources):
            return PriorityConfidence.HIGH
        return PriorityConfidence.MEDIUM

    @staticmethod
    def _effort(category: str) -> Effort:
        normalized = category.upper()
        if any(token in normalized for token in ("JAVASCRIPT", "SPA", "RENDER", "ARCHITECT")):
            return Effort.HIGH
        if any(token in normalized for token in ("STRUCTURED", "SEMANTIC", "ENTITY", "ANSWER", "CITATION", "EVIDENCE", "INTENT", "DUPLICATE")):
            return Effort.MEDIUM
        if any(token in normalized for token in ("ACCESS", "INDEX", "LINK", "ROBOTS", "SITEMAP", "CANONICAL")):
            return Effort.LOW
        return Effort.UNKNOWN

    @staticmethod
    def _is_p0(*, severity: Severity, impact: Impact, category: str) -> bool:
        if severity is not Severity.CRITICAL or impact not in {Impact.VERY_HIGH, Impact.HIGH}:
            return False
        normalized = category.upper()
        return any(token in normalized for token in ("DISCOVERY", "ACCESS", "INDEX", "RENDER", "JAVASCRIPT", "SPA"))

    def _recommendation(self, *, audit_id: str, group: RemediationGroup, findings: list[Finding]) -> Recommendation:
        recipe = recipe_for(group.rule_id)
        expected = " ".join((findings[0].expected_condition or "").split())
        description = recipe.description
        if recipe.human_decision:
            description = f"{description} Decisão necessária: {recipe.human_decision}"
        if expected:
            description = f"{description} Critério da regra: {expected}."
        if recipe.fallback:
            description = f"Fallback de remediação. {description}"
        return Recommendation(
            recommendation_id=new_id("REC"),
            audit_id=audit_id,
            finding_id=None,
            remediation_group_id=group.group_id,
            device=_recommendation_device(group.devices),
            title=recipe.title,
            description=description,
            impact=group.impact,
            effort=group.effort,
            confidence=group.confidence,
            priority_score=group.priority_score,
            priority_class=group.priority_class,
        )


def _recommendation_device(devices: tuple[FindingDevice, ...]) -> FindingDevice:
    effective = {device for device in devices if device is not FindingDevice.NOT_APPLICABLE}
    if not effective:
        return FindingDevice.NOT_APPLICABLE
    if FindingDevice.BOTH in effective or len(effective) > 1:
        return FindingDevice.BOTH
    return next(iter(effective))
