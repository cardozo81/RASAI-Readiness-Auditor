"""Bounded scoring bridge for optional evidence-bound crawling/discovery AI assessments."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from rasai.domain import EvidenceType, Finding, FindingDevice, RuleExecution, RuleResult, Severity, new_id, utc_now
from rasai.evidence import EvidenceManager
from rasai.persistence import AuditPersistence

_RESOURCE_RULE = {"SITEMAP": "BR-GEO-055", "ROBOTS": "BR-GEO-056"}
_VERDICT_RESULT = {"POSITIVE": RuleResult.PASS, "NEUTRAL": RuleResult.WARNING, "NEGATIVE": RuleResult.FAIL}


@dataclass(frozen=True, slots=True)
class M24ScoringResult:
    rule_execution_ids: tuple[str, ...]
    finding_ids: tuple[str, ...]


def _bounded_result(verdict: str, confidence: float) -> RuleResult:
    normalized = verdict.strip().upper()
    result = _VERDICT_RESULT.get(normalized)
    if result is None:
        raise ValueError(f"unsupported technical AI verdict: {verdict}")
    # Low-confidence model output may signal review, but never creates a hard PASS/FAIL.
    if confidence < 0.60:
        return RuleResult.WARNING
    return result


def persist_m24_scoring_assessments(
    *,
    audit_id: str,
    persistence: AuditPersistence,
    ai_state: str,
    provider: str | None,
    model: str | None,
    assessments: tuple[dict[str, Any], ...],
) -> M24ScoringResult:
    if ai_state != "AVAILABLE" or not assessments:
        return M24ScoringResult((), ())
    manager = EvidenceManager(persistence)
    executions: list[str] = []
    findings: list[str] = []
    for assessment in assessments:
        resource = str(assessment.get("resource") or "").strip().upper()
        rule_id = _RESOURCE_RULE.get(resource)
        if rule_id is None:
            continue
        verdict = str(assessment.get("verdict") or "").strip().upper()
        try:
            confidence = float(assessment.get("confidence"))
        except (TypeError, ValueError):
            continue
        rationale = str(assessment.get("rationale_pt") or "").strip()
        source_evidence = tuple(str(item) for item in assessment.get("evidence_ids", ()) if str(item))
        if not source_evidence or not rationale:
            continue
        if any(persistence.evidence.get(evidence_id) is None for evidence_id in source_evidence):
            continue
        result = _bounded_result(verdict, confidence)
        evidence = manager.record(
            audit_id=audit_id,
            page_id=None,
            snapshot_id=None,
            device=None,
            evidence_type=EvidenceType.AI_ANALYSIS,
            source=f"technical-discovery:{provider or 'UNKNOWN'}:{resource}",
            observed_value={
                "resource": resource,
                "verdict": verdict,
                "confidence": confidence,
                "rationale_pt": rationale,
                "provider": provider,
                "model": model,
                "source_evidence_ids": list(source_evidence),
                "weight_policy": "STATIC_VERSIONED_SCORING_METADATA",
                "positive_bonus_policy": "NO_DOUBLE_COUNT_SAME_SCORING_GROUP",
            },
        )
        execution = RuleExecution(
            rule_execution_id=new_id("REX"),
            audit_id=audit_id,
            rule_id=rule_id,
            rule_version="1",
            page_id=None,
            snapshot_id=None,
            device=None,
            result=result,
            observed_value={
                "resource": resource,
                "ai_verdict": verdict,
                "ai_confidence": confidence,
                "rationale_pt": rationale,
            },
            expected_condition=(
                f"optional AI assessment of {resource.lower()} corroborates the deterministic resource evidence "
                "without inventing weights or overriding hard facts"
            ),
            evidence_ids=(evidence.evidence_id,),
            executed_at=utc_now(),
            error=None,
        )
        persistence.rule_executions.add(execution)
        executions.append(execution.rule_execution_id)
        if result in {RuleResult.WARNING, RuleResult.FAIL}:
            finding = Finding(
                finding_id=new_id("FND"),
                audit_id=audit_id,
                rule_id=rule_id,
                rule_execution_id=execution.rule_execution_id,
                page_id=None,
                device=FindingDevice.BOTH,
                category=resource,
                severity=Severity.MEDIUM if result is RuleResult.WARNING else Severity.HIGH,
                source="evidence-bound-technical-ai",
                title=f"Qualidade técnica de {resource.lower()} requer revisão",
                observed_value=execution.observed_value,
                expected_condition=execution.expected_condition,
                evidence_ids=execution.evidence_ids,
                status="OPEN",
            )
            persistence.findings.add(finding)
            findings.append(finding.finding_id)
    return M24ScoringResult(tuple(executions), tuple(findings))
