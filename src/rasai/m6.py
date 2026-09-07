"""M6 - JavaScript / SPA rules and bounded interaction diagnostics."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from rasai.domain import (
    ArchitectureClassification,
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
from rasai.javascript_spa import BoundedScrollProbe, JavascriptSpaAnalyzer, LazyProbe, StateComparison
from rasai.m2 import M2ExecutionResult
from rasai.m3 import M3ExecutionResult
from rasai.m4 import M4ExecutionResult
from rasai.m5 import M5ExecutionResult
from rasai.persistence import AuditPersistence, AuditWorkspace
from rasai.rules import DependencyResolver, RuleDefinition, RuleEvaluation, RuleScope
from rasai.spa_persistence import SnapshotArchitectureWriter


_RULE_VERSION = "1"


_M6_DEFINITIONS = (
    RuleDefinition("BR-GEO-019", "Raw and rendered page states must remain semantically consistent", "JAVASCRIPT_RENDERING", "CONTENT_EXTRACTABILITY", RuleScope.SNAPSHOT, dependencies=("BR-GEO-009",), severity=Severity.HIGH, basis="STANDARD", scoring_group="JS_CONTENT"),
    RuleDefinition("BR-GEO-020", "Essential content must remain recoverable after JavaScript rendering", "JAVASCRIPT_RENDERING", "CONTENT_EXTRACTABILITY", RuleScope.SNAPSHOT, dependencies=("BR-GEO-009",), severity=Severity.HIGH, basis="STANDARD", scoring_group="JS_CONTENT"),
    RuleDefinition("BR-GEO-021", "Indexable client-side routes must resolve through direct URL access", "JAVASCRIPT_RENDERING", "TECHNICAL_ACCESSIBILITY", RuleScope.SNAPSHOT, dependencies=("BR-GEO-005", "BR-GEO-009"), severity=Severity.HIGH, basis="STANDARD", scoring_group="SPA_ROUTE"),
    RuleDefinition("BR-GEO-022", "Important internal navigation must expose crawlable destinations", "JAVASCRIPT_RENDERING", "TECHNICAL_ACCESSIBILITY", RuleScope.SNAPSHOT, dependencies=("BR-GEO-009",), severity=Severity.MEDIUM, basis="STANDARD", scoring_group="SPA_NAVIGATION"),
    RuleDefinition("BR-GEO-023", "Client-side routing must not create misleading soft-404 states", "JAVASCRIPT_RENDERING", "INDEXABILITY", RuleScope.SNAPSHOT, dependencies=("BR-GEO-006",), severity=Severity.HIGH, basis="HEURISTIC", scoring_group="SOFT_ERROR"),
    RuleDefinition("BR-GEO-024", "Lazy loading must not prevent recovery of essential content", "JAVASCRIPT_RENDERING", "CONTENT_EXTRACTABILITY", RuleScope.SNAPSHOT, dependencies=("BR-GEO-009",), severity=Severity.MEDIUM, basis="HEURISTIC", scoring_group="JS_CONTENT"),
)


@dataclass(frozen=True, slots=True)
class M6ExecutionResult:
    rule_execution_ids: tuple[str, ...]
    finding_ids: tuple[str, ...]
    architecture_by_snapshot: dict[str, ArchitectureClassification]


class _PriorState:
    def __init__(self, persistence: AuditPersistence, execution_ids: tuple[str, ...]) -> None:
        self._by_page: dict[tuple[str, str], RuleResult] = {}
        self._by_snapshot: dict[tuple[str, str], RuleResult] = {}
        self._global: dict[str, RuleResult] = {}
        for execution_id in execution_ids:
            execution = persistence.rule_executions.get(execution_id)
            if execution is None:
                raise ValueError(f"M5 RuleExecution is not re-openable: {execution_id}")
            if execution.snapshot_id:
                self._by_snapshot[(execution.rule_id, execution.snapshot_id)] = execution.result
            elif execution.page_id:
                self._by_page[(execution.rule_id, execution.page_id)] = execution.result
            else:
                self._global[execution.rule_id] = execution.result

    def lookup(self, rule_id: str, *, page_id: str, snapshot_id: str) -> RuleResult | None:
        return (
            self._by_snapshot.get((rule_id, snapshot_id))
            or self._by_page.get((rule_id, page_id))
            or self._global.get(rule_id)
        )


def execute_m6(
    *,
    audit_id: str,
    m2_result: M2ExecutionResult,
    m3_result: M3ExecutionResult,
    m4_result: M4ExecutionResult,
    m5_result: M5ExecutionResult,
    persistence: AuditPersistence,
    workspace: AuditWorkspace,
    lazy_probe: LazyProbe | None = None,
) -> M6ExecutionResult:
    """Execute BR-GEO-019..024 per snapshot with bounded SPA diagnostics."""

    analyzer = JavascriptSpaAnalyzer()
    manager = EvidenceManager(persistence)
    writer = SnapshotArchitectureWriter(workspace)
    resolver = DependencyResolver()
    prior = _PriorState(persistence, m5_result.rule_execution_ids)
    probe = lazy_probe or BoundedScrollProbe().render_after_scroll
    execution_ids: list[str] = []
    finding_ids: list[str] = []
    architecture: dict[str, ArchitectureClassification] = {}

    for discovered in m2_result.discovery.pages:
        page_id = m2_result.page_ids[discovered.normalized_url]
        acquisition = m2_result.discovery.page_acquisitions[discovered.normalized_url]
        for device, snapshot_id in m3_result.snapshot_ids.get(page_id, {}).items():
            snapshot = persistence.snapshots.get(snapshot_id)
            if snapshot is None:
                raise ValueError(f"snapshot not re-openable: {snapshot_id}")
            raw_html = _read(workspace, snapshot.raw_artifact_ref)
            rendered_html = _read(workspace, snapshot.rendered_artifact_ref)
            comparison = analyzer.compare(raw_html, rendered_html) if raw_html is not None and rendered_html is not None else None
            classification = comparison.architecture if comparison is not None else ArchitectureClassification.UNKNOWN
            writer.update(snapshot_id, classification)
            architecture[snapshot_id] = classification

            evaluations: dict[str, RuleEvaluation] = {
                "BR-GEO-019": _evaluate_019(comparison),
                "BR-GEO-020": _evaluate_020(comparison),
                "BR-GEO-021": _evaluate_021(classification, acquisition, rendered_html),
                "BR-GEO-022": _evaluate_022(analyzer, rendered_html, snapshot.final_url or snapshot.requested_url, m2_result.discovery.origin),
                "BR-GEO-023": _evaluate_023(analyzer, rendered_html, acquisition.status),
            }

            lazy_after: str | None = None
            if rendered_html is not None:
                preliminary = analyzer.lazy_loading(rendered_html, after_probe_html=None)
                if preliminary.has_lazy_signals and not preliminary.initial_content_recoverable:
                    probe_result = probe(snapshot.final_url or snapshot.requested_url, device)
                    lazy_after = probe_result.rendered_html if probe_result.succeeded else None
                evaluations["BR-GEO-024"] = _evaluate_024(analyzer, rendered_html, lazy_after)
            else:
                evaluations["BR-GEO-024"] = _unknown("RENDERED_UNAVAILABLE", "lazy-loaded essential content remains recoverable")

            for definition in _M6_DEFINITIONS:
                dependency = resolver.resolve(
                    definition,
                    lambda dep, p=page_id, s=snapshot_id: prior.lookup(dep, page_id=p, snapshot_id=s),
                )
                evaluation = evaluations[definition.rule_id]
                if not dependency.applicable:
                    evaluation = RuleEvaluation(
                        result=dependency.result or RuleResult.UNKNOWN,
                        observed_value={"dependency_reason": dependency.reason},
                        expected_condition=evaluation.expected_condition,
                        reason=dependency.reason,
                    )
                execution = _persist_execution(
                    definition,
                    evaluation,
                    audit_id=audit_id,
                    page_id=page_id,
                    snapshot_id=snapshot_id,
                    device=device,
                    manager=manager,
                    persistence=persistence,
                )
                execution_ids.append(execution.rule_execution_id)
                finding = _persist_finding(definition, execution, persistence)
                if finding is not None:
                    finding_ids.append(finding.finding_id)

    return M6ExecutionResult(tuple(execution_ids), tuple(finding_ids), architecture)


def _read(workspace: AuditWorkspace, reference: str | None) -> str | None:
    if not reference:
        return None
    path = workspace.root / reference
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8", errors="replace")


def _unknown(reason: str, expected: str) -> RuleEvaluation:
    return RuleEvaluation(RuleResult.UNKNOWN, {"reason": reason}, expected, reason=reason)


def _evaluate_019(comparison: StateComparison | None) -> RuleEvaluation:
    if comparison is None:
        return _unknown("RAW_OR_RENDERED_UNAVAILABLE", "RAW and rendered states remain materially consistent")
    material_conflicts = tuple(field for field in comparison.changed_fields if field in {"canonical", "robots"})
    content_loss = bool(comparison.raw_main_content and not comparison.rendered_main_content)
    if material_conflicts or content_loss:
        result = RuleResult.FAIL
    else:
        result = RuleResult.PASS
    return RuleEvaluation(
        result,
        {
            "architecture": comparison.architecture.value,
            "changed_fields": list(comparison.changed_fields),
            "material_conflicts": list(material_conflicts),
            "content_lost_after_render": content_loss,
        },
        "RAW and rendered states remain materially consistent without unsafe directive/content loss",
    )


def _evaluate_020(comparison: StateComparison | None) -> RuleEvaluation:
    if comparison is None:
        return _unknown("RAW_OR_RENDERED_UNAVAILABLE", "essential content remains recoverable after JavaScript rendering")
    if comparison.rendered_main_content:
        result = RuleResult.PASS
        reason = None
    elif comparison.raw_main_content:
        result = RuleResult.FAIL
        reason = "CONTENT_LOST_AFTER_RENDER"
    else:
        result = RuleResult.UNKNOWN
        reason = "ESSENTIAL_CONTENT_NOT_IDENTIFIED"
    return RuleEvaluation(
        result,
        {"raw_content": bool(comparison.raw_main_content), "rendered_content": bool(comparison.rendered_main_content), "architecture": comparison.architecture.value},
        "essential content remains recoverable after JavaScript rendering; RAW shell plus complete rendered content is valid",
        reason=reason,
    )


def _evaluate_021(classification: ArchitectureClassification, acquisition: object, rendered_html: str | None) -> RuleEvaluation:
    if classification not in {ArchitectureClassification.CSR_SPA, ArchitectureClassification.MIXED}:
        return RuleEvaluation(RuleResult.NOT_APPLICABLE, {"architecture": classification.value}, "indexable client-side routes resolve via direct URL access")
    status = getattr(acquisition, "status", None)
    network_error = getattr(acquisition, "network_error", None)
    ok = network_error is None and status is not None and 200 <= status <= 299 and rendered_html is not None
    return RuleEvaluation(
        RuleResult.PASS if ok else RuleResult.FAIL,
        {"architecture": classification.value, "direct_status": status, "network_error": getattr(getattr(network_error, "kind", None), "value", None), "rendered": rendered_html is not None},
        "indexable client-side routes resolve via direct URL access",
    )


def _evaluate_022(analyzer: JavascriptSpaAnalyzer, rendered_html: str | None, base_url: str, origin: str) -> RuleEvaluation:
    if rendered_html is None:
        return _unknown("RENDERED_UNAVAILABLE", "important internal navigation exposes crawlable destinations")
    assessment = analyzer.navigation(rendered_html, base_url=base_url, origin=origin)
    result = RuleResult.WARNING if assessment.non_crawlable_navigation_controls else RuleResult.PASS
    return RuleEvaluation(
        result,
        {"crawlable_internal_links": list(assessment.crawlable_internal_links), "non_crawlable_navigation_controls": assessment.non_crawlable_navigation_controls},
        "important internal navigation exposes crawlable href destinations",
        reason="NON_CRAWLABLE_NAVIGATION_CONTROLS" if result is RuleResult.WARNING else None,
    )


def _evaluate_023(analyzer: JavascriptSpaAnalyzer, rendered_html: str | None, status: int | None) -> RuleEvaluation:
    if rendered_html is None:
        return _unknown("RENDERED_UNAVAILABLE", "client-side routing does not create misleading soft-404 states")
    detected = analyzer.soft404(http_status=status, rendered_html=rendered_html)
    return RuleEvaluation(
        RuleResult.FAIL if detected else RuleResult.PASS,
        {"http_status": status, "soft_404": detected},
        "client-side routing does not return error semantics behind successful HTTP status",
        reason="STRONG_SOFT_404_SIGNAL" if detected else None,
    )


def _evaluate_024(analyzer: JavascriptSpaAnalyzer, rendered_html: str, after_probe_html: str | None) -> RuleEvaluation:
    assessment = analyzer.lazy_loading(rendered_html, after_probe_html=after_probe_html)
    return RuleEvaluation(
        assessment.result,
        {
            "has_lazy_signals": assessment.has_lazy_signals,
            "initial_content_recoverable": assessment.initial_content_recoverable,
            "after_probe_content_recoverable": assessment.after_probe_content_recoverable,
        },
        "lazy loading does not prevent recovery of essential content within bounded predictable interaction",
        reason=assessment.reason,
    )


def _persist_execution(
    definition: RuleDefinition,
    evaluation: RuleEvaluation,
    *,
    audit_id: str,
    page_id: str,
    snapshot_id: str,
    device: DeviceContext,
    manager: EvidenceManager,
    persistence: AuditPersistence,
) -> RuleExecution:
    evidence = manager.record(
        audit_id=audit_id,
        page_id=page_id,
        snapshot_id=snapshot_id,
        device=device,
        evidence_type=EvidenceType.COMPARISON if definition.rule_id in {"BR-GEO-019", "BR-GEO-020"} else EvidenceType.DOM_ELEMENT,
        source=f"javascript-spa:{definition.rule_id}",
        observed_value={"result": evaluation.result.value, "observed": evaluation.observed_value, "reason": evaluation.reason},
    )
    execution = RuleExecution(
        rule_execution_id=new_id("REX"),
        audit_id=audit_id,
        rule_id=definition.rule_id,
        rule_version=_RULE_VERSION,
        page_id=page_id,
        snapshot_id=snapshot_id,
        device=device,
        result=evaluation.result,
        observed_value=evaluation.observed_value,
        expected_condition=evaluation.expected_condition,
        evidence_ids=(evidence.evidence_id,),
        executed_at=utc_now(),
    )
    persistence.rule_executions.add(execution)
    return execution


def _persist_finding(definition: RuleDefinition, execution: RuleExecution, persistence: AuditPersistence) -> Finding | None:
    if execution.result not in {RuleResult.FAIL, RuleResult.WARNING} or not execution.evidence_ids:
        return None
    device = FindingDevice.DESKTOP if execution.device is DeviceContext.DESKTOP else FindingDevice.MOBILE
    finding = Finding(
        finding_id=new_id("FND"), audit_id=execution.audit_id, rule_id=execution.rule_id,
        rule_execution_id=execution.rule_execution_id, page_id=execution.page_id, device=device,
        category=definition.category, severity=definition.severity, source="deterministic-javascript-spa",
        title=definition.name, observed_value=execution.observed_value,
        expected_condition=execution.expected_condition, evidence_ids=execution.evidence_ids, status="OPEN",
    )
    persistence.findings.add(finding)
    return finding
