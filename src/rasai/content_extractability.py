"""Deterministic Content Extractability rules BR-GEO-025..027.

This module closes the normative gap between extraction (M4) and semantic analysis
(M7) without introducing semantic-provider dependencies or arbitrary word-count
thresholds.
"""

from __future__ import annotations

from dataclasses import dataclass
import re

from rasai.domain import (
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
from rasai.extraction import ContentExtractor
from rasai.m3 import M3ExecutionResult
from rasai.persistence import AuditPersistence, AuditWorkspace
from rasai.rules import RuleDefinition, RuleScope


_RULE_VERSION = "1"

_DEFINITIONS = (
    RuleDefinition(
        "BR-GEO-025",
        "Main content must be identifiable",
        "CONTENT_EXTRACTABILITY",
        "CONTENT_EXTRACTABILITY",
        RuleScope.SNAPSHOT,
        severity=Severity.HIGH,
        basis="HEURISTIC",
        scoring_group="CONTENT_EXTRACTION",
    ),
    RuleDefinition(
        "BR-GEO-026",
        "Page must contain meaningful content beyond navigation and boilerplate",
        "CONTENT_EXTRACTABILITY",
        "CONTENT_EXTRACTABILITY",
        RuleScope.SNAPSHOT,
        dependencies=("BR-GEO-025",),
        severity=Severity.HIGH,
        basis="HEURISTIC",
        scoring_group="CONTENT_EXTRACTION",
    ),
    RuleDefinition(
        "BR-GEO-027",
        "Essential information must survive extraction without material loss",
        "CONTENT_EXTRACTABILITY",
        "CONTENT_EXTRACTABILITY",
        RuleScope.SNAPSHOT,
        dependencies=("BR-GEO-025",),
        severity=Severity.MEDIUM,
        basis="HEURISTIC",
        scoring_group="CONTENT_EXTRACTION",
    ),
)


@dataclass(frozen=True, slots=True)
class ContentExtractabilityResult:
    rule_execution_ids: tuple[str, ...]
    finding_ids: tuple[str, ...]


def execute_content_extractability(
    *,
    audit_id: str,
    m3_result: M3ExecutionResult,
    persistence: AuditPersistence,
    workspace: AuditWorkspace,
) -> ContentExtractabilityResult:
    """Execute BR-GEO-025..027 independently for every Desktop/Mobile snapshot."""

    manager = EvidenceManager(persistence)
    extractor = ContentExtractor()
    execution_ids: list[str] = []
    finding_ids: list[str] = []

    for page_id, per_device in m3_result.snapshot_ids.items():
        for device, snapshot_id in per_device.items():
            snapshot = persistence.snapshots.get(snapshot_id)
            if snapshot is None or snapshot.page_id != page_id or snapshot.device is not device:
                raise ValueError(f"invalid snapshot mapping: {snapshot_id}")

            rendered_html = _read(workspace, snapshot.rendered_artifact_ref)
            persisted_main = _read(workspace, snapshot.main_content_ref)
            extracted = extractor.extract(rendered_html) if rendered_html is not None else None

            evaluations = _evaluate(extracted, persisted_main)
            prior: dict[str, RuleResult] = {}
            for definition in _DEFINITIONS:
                result, observed, expected, reason = evaluations[definition.rule_id]
                if definition.dependencies:
                    blocked = next(
                        (
                            dependency
                            for dependency in definition.dependencies
                            if prior.get(dependency)
                            in {
                                RuleResult.FAIL,
                                RuleResult.ERROR,
                                RuleResult.UNKNOWN,
                                RuleResult.NOT_APPLICABLE,
                            }
                        ),
                        None,
                    )
                    if blocked is not None:
                        dependency_result = prior[blocked]
                        result = (
                            RuleResult.UNKNOWN
                            if dependency_result is RuleResult.UNKNOWN
                            else RuleResult.NOT_APPLICABLE
                        )
                        observed = {
                            "reason": "CONTENT_EXTRACTION_PREREQUISITE_BLOCKED",
                            "dependency": blocked,
                            "dependency_result": dependency_result.value,
                        }
                        reason = "CONTENT_EXTRACTION_PREREQUISITE_BLOCKED"

                evidence = manager.record(
                    audit_id=audit_id,
                    page_id=page_id,
                    snapshot_id=snapshot_id,
                    device=device,
                    evidence_type=EvidenceType.COMPARISON,
                    source=f"content-extractability:{definition.rule_id}",
                    observed_value={
                        "result": result.value,
                        "observed": observed,
                        "reason": reason,
                    },
                    artifact_reference=snapshot.main_content_ref,
                )
                execution = RuleExecution(
                    rule_execution_id=new_id("REX"),
                    audit_id=audit_id,
                    rule_id=definition.rule_id,
                    rule_version=_RULE_VERSION,
                    page_id=page_id,
                    snapshot_id=snapshot_id,
                    device=device,
                    result=result,
                    observed_value=observed,
                    expected_condition=expected,
                    evidence_ids=(evidence.evidence_id,),
                    executed_at=utc_now(),
                    error=None,
                )
                persistence.rule_executions.add(execution)
                execution_ids.append(execution.rule_execution_id)
                prior[definition.rule_id] = result

                finding = _finding(definition, execution, persistence)
                if finding is not None:
                    finding_ids.append(finding.finding_id)

    return ContentExtractabilityResult(tuple(execution_ids), tuple(finding_ids))


def _evaluate(extracted: object | None, persisted_main: str | None) -> dict[str, tuple[RuleResult, object, str, str | None]]:
    expected_025 = "main content is deterministically identifiable from the rendered document"
    expected_026 = "meaningful non-boilerplate page content is recoverable without arbitrary word-count thresholds"
    expected_027 = "material factual qualifiers observable in extracted non-boilerplate text survive the persisted main-content extraction"

    if extracted is None:
        unknown = (RuleResult.UNKNOWN, {"reason": "RENDERED_UNAVAILABLE"}, expected_025, "RENDERED_UNAVAILABLE")
        return {
            "BR-GEO-025": unknown,
            "BR-GEO-026": (RuleResult.UNKNOWN, {"reason": "RENDERED_UNAVAILABLE"}, expected_026, "RENDERED_UNAVAILABLE"),
            "BR-GEO-027": (RuleResult.UNKNOWN, {"reason": "RENDERED_UNAVAILABLE"}, expected_027, "RENDERED_UNAVAILABLE"),
        }

    main_content = getattr(extracted, "main_content", "") or ""
    text_blocks = tuple(getattr(extracted, "text_blocks", ()) or ())
    source = getattr(extracted, "main_content_source", "UNKNOWN")

    identifiable = bool(main_content.strip()) and source != "BODY_FALLBACK"
    if identifiable:
        r025, reason025 = RuleResult.PASS, None
    elif main_content.strip():
        r025, reason025 = RuleResult.WARNING, "MAIN_CONTENT_ONLY_BODY_FALLBACK"
    else:
        r025, reason025 = RuleResult.FAIL, "MAIN_CONTENT_NOT_IDENTIFIED"

    meaningful = bool(" ".join(text_blocks).strip())
    r026 = RuleResult.PASS if meaningful else RuleResult.FAIL
    reason026 = None if meaningful else "NON_BOILERPLATE_CONTENT_NOT_IDENTIFIED"

    persisted = (persisted_main or "").strip()
    rendered_non_boilerplate = " ".join(text_blocks).strip()
    material = _material_qualifiers(rendered_non_boilerplate)
    missing = tuple(item for item in material if item not in persisted.casefold())
    if not persisted:
        r027, reason027 = RuleResult.FAIL, "PERSISTED_MAIN_CONTENT_EMPTY"
    elif missing:
        r027, reason027 = RuleResult.WARNING, "MATERIAL_QUALIFIERS_LOST_DURING_EXTRACTION"
    else:
        r027, reason027 = RuleResult.PASS, None

    return {
        "BR-GEO-025": (
            r025,
            {"main_content_source": source, "main_content_available": bool(main_content.strip())},
            expected_025,
            reason025,
        ),
        "BR-GEO-026": (
            r026,
            {"non_boilerplate_blocks": len(text_blocks), "meaningful_content_available": meaningful},
            expected_026,
            reason026,
        ),
        "BR-GEO-027": (
            r027,
            {"material_qualifiers": list(material), "missing_from_persisted_main": list(missing)},
            expected_027,
            reason027,
        ),
    }


def _material_qualifiers(text: str) -> tuple[str, ...]:
    """Return explicit factual qualifiers without semantic interpretation.

    The detector intentionally has no minimum word count. It only tracks concrete
    qualifiers whose loss would materially change a factual statement: percentages,
    currency amounts, common measurement units and explicit date-like values.
    """

    normalized = text.casefold()
    patterns = (
        r"(?:r\$|us\$|€|£|\$)\s*\d+(?:[.,]\d+)*",
        r"\b\d+(?:[.,]\d+)?\s*%",
        r"\b\d+(?:[.,]\d+)?\s*(?:kg|g|mg|km|m|cm|mm|l|ml|gb|mb|tb|ms|s|min|h|hrs?|dias?|days?|anos?|years?)\b",
        r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b",
        r"\b\d{4}-\d{2}-\d{2}\b",
    )
    found: list[str] = []
    for pattern in patterns:
        found.extend(match.group(0).strip() for match in re.finditer(pattern, normalized, flags=re.IGNORECASE))
    return tuple(dict.fromkeys(found))


def _read(workspace: AuditWorkspace, reference: str | None) -> str | None:
    if not reference:
        return None
    path = workspace.root / reference
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8", errors="replace")


def _finding(definition: RuleDefinition, execution: RuleExecution, persistence: AuditPersistence) -> Finding | None:
    if execution.result not in {RuleResult.FAIL, RuleResult.WARNING} or not execution.evidence_ids:
        return None
    device = FindingDevice.DESKTOP if execution.device is DeviceContext.DESKTOP else FindingDevice.MOBILE
    finding = Finding(
        finding_id=new_id("FND"),
        audit_id=execution.audit_id,
        rule_id=execution.rule_id,
        rule_execution_id=execution.rule_execution_id,
        page_id=execution.page_id,
        device=device,
        category=definition.category,
        severity=definition.severity,
        source="deterministic-content-extractability",
        title=definition.name,
        observed_value=execution.observed_value,
        expected_condition=execution.expected_condition,
        evidence_ids=execution.evidence_ids,
        status="OPEN",
    )
    persistence.findings.add(finding)
    return finding
