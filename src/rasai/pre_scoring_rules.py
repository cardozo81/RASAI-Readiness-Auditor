"""Pre-scoring deterministic rules BR-GEO-050, BR-GEO-051 and BR-GEO-053."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from pathlib import Path
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
from rasai.m2 import M2ExecutionResult
from rasai.m3 import M3ExecutionResult
from rasai.persistence import AuditPersistence, AuditWorkspace
from rasai.url_utils import is_same_origin, normalize_url


_NEAR_DUPLICATE_JACCARD = 0.90  # versioned M8 heuristic; exact duplicates are always identified.
_TOKEN = re.compile(r"\w+", re.UNICODE)


@dataclass(frozen=True, slots=True)
class PreScoringRulesResult:
    rule_execution_ids: tuple[str, ...]
    finding_ids: tuple[str, ...]


def execute_pre_scoring_rules(
    *,
    audit_id: str,
    m2_result: M2ExecutionResult,
    m3_result: M3ExecutionResult,
    persistence: AuditPersistence,
    workspace: AuditWorkspace,
    finding_ids_to_validate: tuple[str, ...] = (),
) -> PreScoringRulesResult:
    manager = EvidenceManager(persistence)
    extractor = ContentExtractor()
    executions: list[str] = []
    findings: list[str] = []

    # BR-GEO-050 - evaluated per snapshot because navigation may differ by device.
    known_acquisitions = m2_result.discovery.page_acquisitions
    for page_id, per_device in m3_result.snapshot_ids.items():
        for device, snapshot_id in per_device.items():
            snapshot = persistence.snapshots.get(snapshot_id)
            html = _read(workspace.root, snapshot.rendered_artifact_ref) if snapshot else None
            if snapshot is None or html is None:
                result = RuleResult.UNKNOWN
                observed = {"reason": "RENDERED_UNAVAILABLE"}
            else:
                page = extractor.extract(html)
                unusable: list[dict[str, object]] = []
                resolved: list[str] = []
                for link in page.links:
                    try:
                        url = normalize_url(link.href, base_url=snapshot.final_url or snapshot.requested_url)
                    except ValueError:
                        continue
                    if not is_same_origin(url, m2_result.discovery.origin):
                        continue
                    resolved.append(url)
                    acquisition = known_acquisitions.get(url)
                    if acquisition is None:
                        continue  # outside audited page budget: do not guess destination status.
                    if acquisition.network_error is not None or acquisition.status is None or acquisition.status >= 400:
                        unusable.append({
                            "url": url,
                            "status": acquisition.status,
                            "network_error": getattr(getattr(acquisition.network_error, "kind", None), "value", None),
                        })
                result = RuleResult.WARNING if unusable else RuleResult.PASS
                observed = {
                    "internal_destinations": list(dict.fromkeys(resolved)),
                    "known_unusable_destinations": unusable,
                    "unverified_destinations_outside_audited_universe": [
                        url for url in dict.fromkeys(resolved) if url not in known_acquisitions
                    ],
                }
            execution, finding = _persist(
                audit_id=audit_id,
                page_id=page_id,
                snapshot_id=snapshot_id,
                device=device,
                rule_id="BR-GEO-050",
                title="Internal links must expose technically usable destinations",
                category="INTERNAL_LINKS",
                severity=Severity.MEDIUM,
                result=result,
                observed=observed,
                expected="internal href destinations within the audited universe are normalized and technically usable",
                manager=manager,
                persistence=persistence,
            )
            executions.append(execution.rule_execution_id)
            if finding:
                findings.append(finding.finding_id)

    # BR-GEO-051 - duplicate/near-duplicate only inside the audited universe, per device.
    for device in (DeviceContext.DESKTOP, DeviceContext.MOBILE):
        content_by_page: dict[str, str] = {}
        snapshot_by_page: dict[str, str] = {}
        for page_id, per_device in m3_result.snapshot_ids.items():
            snapshot_id = per_device.get(device)
            if not snapshot_id:
                continue
            snapshot = persistence.snapshots.get(snapshot_id)
            html = _read(workspace.root, snapshot.rendered_artifact_ref) if snapshot else None
            if html is None:
                continue
            content_by_page[page_id] = extractor.extract(html).main_content
            snapshot_by_page[page_id] = snapshot_id
        duplicate_pairs = _duplicate_pairs(content_by_page)
        affected: dict[str, list[dict[str, object]]] = {}
        for left, right, similarity in duplicate_pairs:
            affected.setdefault(left, []).append({"page_id": right, "similarity": similarity})
            affected.setdefault(right, []).append({"page_id": left, "similarity": similarity})
        for page_id, snapshot_id in snapshot_by_page.items():
            pairs = affected.get(page_id, [])
            result = RuleResult.WARNING if pairs else RuleResult.PASS
            execution, finding = _persist(
                audit_id=audit_id,
                page_id=page_id,
                snapshot_id=snapshot_id,
                device=device,
                rule_id="BR-GEO-051",
                title="Material duplicate or near-duplicate pages must be identifiable",
                category="DUPLICATE_CONTENT",
                severity=Severity.MEDIUM,
                result=result,
                observed={
                    "matches": pairs,
                    "near_duplicate_jaccard_threshold": _NEAR_DUPLICATE_JACCARD,
                    "universe": "AUDITED_ONLY",
                },
                expected="material exact or near-duplicate content is identified only within the audited universe",
                manager=manager,
                persistence=persistence,
            )
            executions.append(execution.rule_execution_id)
            if finding:
                findings.append(finding.finding_id)

    # BR-GEO-053 - explicit auditor-integrity rule over findings supplied by the pipeline.
    invalid: list[dict[str, str]] = []
    checked = 0
    for finding_id in finding_ids_to_validate:
        finding = persistence.findings.get(finding_id)
        if finding is None:
            invalid.append({"finding_id": finding_id, "reason": "FINDING_NOT_REOPENABLE"})
            continue
        checked += 1
        execution = persistence.rule_executions.get(finding.rule_execution_id)
        if execution is None:
            invalid.append({"finding_id": finding_id, "reason": "RULE_EXECUTION_NOT_REOPENABLE"})
            continue
        for evidence_id in finding.evidence_ids:
            if persistence.evidence.get(evidence_id) is None:
                invalid.append({"finding_id": finding_id, "reason": f"EVIDENCE_NOT_REOPENABLE:{evidence_id}"})
    result = RuleResult.FAIL if invalid else RuleResult.PASS
    execution, finding = _persist(
        audit_id=audit_id,
        page_id=None,
        snapshot_id=None,
        device=None,
        rule_id="BR-GEO-053",
        title="Every finding must be fully traceable",
        category="AUDITOR_INTEGRITY",
        severity=Severity.CRITICAL,
        result=result,
        observed={"checked_findings": checked, "invalid": invalid},
        expected="every supplied finding reopens its RuleExecution and every referenced Evidence",
        manager=manager,
        persistence=persistence,
    )
    executions.append(execution.rule_execution_id)
    if finding:
        findings.append(finding.finding_id)

    return PreScoringRulesResult(tuple(executions), tuple(findings))


def _duplicate_pairs(content_by_page: dict[str, str]) -> tuple[tuple[str, str, float], ...]:
    pairs: list[tuple[str, str, float]] = []
    for (left, a), (right, b) in combinations(content_by_page.items(), 2):
        aa, bb = _normalized(a), _normalized(b)
        if not aa or not bb:
            continue
        if aa == bb:
            pairs.append((left, right, 1.0))
            continue
        at, bt = set(_TOKEN.findall(aa)), set(_TOKEN.findall(bb))
        union = at | bt
        similarity = len(at & bt) / len(union) if union else 0.0
        if similarity >= _NEAR_DUPLICATE_JACCARD:
            pairs.append((left, right, round(similarity, 6)))
    return tuple(pairs)


def _normalized(value: str) -> str:
    return " ".join(value.casefold().split())


def _read(root: Path, reference: str | None) -> str | None:
    if not reference:
        return None
    path = root / reference
    return path.read_text(encoding="utf-8", errors="replace") if path.is_file() else None


def _persist(
    *,
    audit_id: str,
    page_id: str | None,
    snapshot_id: str | None,
    device: DeviceContext | None,
    rule_id: str,
    title: str,
    category: str,
    severity: Severity,
    result: RuleResult,
    observed: object,
    expected: str,
    manager: EvidenceManager,
    persistence: AuditPersistence,
) -> tuple[RuleExecution, Finding | None]:
    evidence = manager.record(
        audit_id=audit_id,
        page_id=page_id,
        snapshot_id=snapshot_id,
        device=device,
        evidence_type=EvidenceType.COMPARISON,
        source=f"pre-scoring:{rule_id}",
        observed_value={"result": result.value, "observed": observed},
    )
    execution = RuleExecution(
        rule_execution_id=new_id("REX"), audit_id=audit_id, rule_id=rule_id, rule_version="1",
        page_id=page_id, snapshot_id=snapshot_id, device=device, result=result,
        observed_value=observed, expected_condition=expected, evidence_ids=(evidence.evidence_id,),
        executed_at=utc_now(), error=None,
    )
    persistence.rule_executions.add(execution)
    if result not in {RuleResult.FAIL, RuleResult.WARNING}:
        return execution, None
    finding_device = (
        FindingDevice.DESKTOP if device is DeviceContext.DESKTOP
        else FindingDevice.MOBILE if device is DeviceContext.MOBILE
        else FindingDevice.NOT_APPLICABLE
    )
    finding = Finding(
        finding_id=new_id("FND"), audit_id=audit_id, rule_id=rule_id,
        rule_execution_id=execution.rule_execution_id, page_id=page_id, device=finding_device,
        category=category, severity=severity, source="deterministic-pre-scoring",
        title=title, observed_value=observed, expected_condition=expected,
        evidence_ids=execution.evidence_ids, status="OPEN",
    )
    persistence.findings.add(finding)
    return execution, finding
