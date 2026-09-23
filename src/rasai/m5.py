"""M5 - deterministic Business Rules, dependencies, applicability and findings."""

from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from rasai.discovery import RobotsState, SitemapState
from rasai.domain import (
    Audit,
    AuditTarget,
    DeviceContext,
    EvidenceType,
    Finding,
    FindingDevice,
    RuleExecution,
    RuleResult,
    new_id,
    utc_now,
)
from rasai.evidence import EvidenceManager
from rasai.extraction import ContentExtractor
from rasai.javascript_spa import JavascriptSpaAnalyzer
from rasai.m2 import M2ExecutionResult
from rasai.m3 import M3ExecutionResult
from rasai.m4 import M4ExecutionResult
from rasai.persistence import AuditPersistence, AuditWorkspace
from rasai.rules import Check, DependencyResolver, RuleDefinition, RuleEvaluation, RuleRegistry, baseline_registry
from rasai.url_utils import is_same_origin, normalize_url, normalized_origin


_RULE_VERSION = "1"
_MATERIAL_REDIRECT_HOPS = 5
_SEARCH_CRAWLERS = ("Googlebot", "Googlebot Smartphone", "Bingbot", "OAI-SearchBot")


@dataclass(frozen=True, slots=True)
class M5ExecutionResult:
    rule_execution_ids: tuple[str, ...]
    finding_ids: tuple[str, ...]
    registry_rule_ids: tuple[str, ...]


@dataclass(slots=True)
class _ExecutionState:
    by_page: dict[tuple[str, str], RuleResult]
    by_snapshot: dict[tuple[str, str], RuleResult]
    global_results: dict[str, RuleResult]

    @classmethod
    def create(cls) -> "_ExecutionState":
        return cls(by_page={}, by_snapshot={}, global_results={})

    def put(self, execution: RuleExecution) -> None:
        if execution.snapshot_id:
            self.by_snapshot[(execution.rule_id, execution.snapshot_id)] = execution.result
        elif execution.page_id:
            self.by_page[(execution.rule_id, execution.page_id)] = execution.result
        else:
            self.global_results[execution.rule_id] = execution.result

    def lookup(self, rule_id: str, *, page_id: str | None, snapshot_id: str | None) -> RuleResult | None:
        if snapshot_id is not None:
            result = self.by_snapshot.get((rule_id, snapshot_id))
            if result is not None:
                return result
        if page_id is not None:
            result = self.by_page.get((rule_id, page_id))
            if result is not None:
                return result
        return self.global_results.get(rule_id)


def execute_m5(
    audit: Audit,
    target: AuditTarget,
    m2_result: M2ExecutionResult,
    m3_result: M3ExecutionResult,
    m4_result: M4ExecutionResult,
    persistence: AuditPersistence,
    workspace: AuditWorkspace,
    *,
    registry: RuleRegistry | None = None,
) -> M5ExecutionResult:
    """Execute the deterministic M5 rules while preserving M2 precomputed executions."""

    active_registry = registry or baseline_registry()
    _validate_registry(active_registry)
    resolver = DependencyResolver()
    manager = EvidenceManager(persistence)
    state = _ExecutionState.create()
    execution_ids: list[str] = []
    finding_ids: list[str] = []

    # M2 legitimately introduced the first technical RuleExecutions before M5.
    for execution_id in m2_result.rule_execution_ids:
        execution = persistence.rule_executions.get(execution_id)
        if execution is None:
            raise ValueError(f"M2 RuleExecution is not re-openable: {execution_id}")
        if execution.rule_id not in active_registry.ids():
            raise ValueError(f"M2 RuleExecution references unregistered rule: {execution.rule_id}")
        state.put(execution)
        execution_ids.append(execution.rule_execution_id)
        finding = _persist_finding_if_needed(
            active_registry.get(execution.rule_id), execution, persistence
        )
        if finding is not None:
            finding_ids.append(finding.finding_id)

    global_specs = (
        ("BR-GEO-001", _evaluate_target(audit, target)),
        ("BR-GEO-003", _evaluate_sitemaps(m2_result)),
        ("BR-GEO-017", _evaluate_robots(m2_result)),
    )
    for rule_id, evaluation in global_specs:
        execution = _execute_new(
            definition=active_registry.get(rule_id),
            evaluation=evaluation,
            audit_id=audit.audit_id,
            page_id=None,
            snapshot_id=None,
            device=None,
            manager=manager,
            persistence=persistence,
            resolver=resolver,
            state=state,
        )
        execution_ids.append(execution.rule_execution_id)
        finding = _persist_finding_if_needed(active_registry.get(rule_id), execution, persistence)
        if finding is not None:
            finding_ids.append(finding.finding_id)

    execution = _execute_new(
        definition=active_registry.get("BR-GEO-018"),
        evaluation=_evaluate_crawlers(m2_result),
        audit_id=audit.audit_id,
        page_id=None,
        snapshot_id=None,
        device=None,
        manager=manager,
        persistence=persistence,
        resolver=resolver,
        state=state,
    )
    execution_ids.append(execution.rule_execution_id)
    finding = _persist_finding_if_needed(active_registry.get("BR-GEO-018"), execution, persistence)
    if finding is not None:
        finding_ids.append(finding.finding_id)

    m3_failures = {(item.page_id, item.device) for item in m3_result.failures}
    m4_failures = {item.snapshot_id: item.error_kind for item in m4_result.failures}

    for discovered in m2_result.discovery.pages:
        page_id = m2_result.page_ids[discovered.normalized_url]
        acquisition = m2_result.discovery.page_acquisitions[discovered.normalized_url]

        for rule_id, evaluation in (
            ("BR-GEO-006", _evaluate_final_response(acquisition)),
            ("BR-GEO-008", _evaluate_redirect_materiality(acquisition)),
            ("BR-GEO-009", _evaluate_analyzable_html(acquisition)),
        ):
            execution = _execute_new(
                definition=active_registry.get(rule_id),
                evaluation=evaluation,
                audit_id=audit.audit_id,
                page_id=page_id,
                snapshot_id=None,
                device=None,
                manager=manager,
                persistence=persistence,
                resolver=resolver,
                state=state,
            )
            execution_ids.append(execution.rule_execution_id)
            finding = _persist_finding_if_needed(active_registry.get(rule_id), execution, persistence)
            if finding is not None:
                finding_ids.append(finding.finding_id)

        for device, snapshot_id in m3_result.snapshot_ids.get(page_id, {}).items():
            snapshot = persistence.snapshots.get(snapshot_id)
            if snapshot is None:
                raise ValueError(f"snapshot not re-openable: {snapshot_id}")

            snapshot_specs = (
                (
                    "BR-GEO-010",
                    _evaluate_rendering(
                        snapshot_id=snapshot_id,
                        render_failed=(page_id, device) in m3_failures,
                        extraction_failure=m4_failures.get(snapshot_id),
                        main_content_ref=snapshot.main_content_ref,
                    ),
                ),
                ("BR-GEO-011", _evaluate_index_directives(acquisition, snapshot.meta_robots)),
                ("BR-GEO-012", _evaluate_noindex(acquisition, snapshot.meta_robots)),
                ("BR-GEO-013", _evaluate_canonical(snapshot, workspace)),
                ("BR-GEO-014", _evaluate_canonical_target(snapshot, m2_result)),
                ("BR-GEO-015", _evaluate_raw_rendered_indexability(snapshot, workspace)),
                ("BR-GEO-016", _evaluate_soft404(snapshot, acquisition, workspace)),
            )
            for rule_id, evaluation in snapshot_specs:
                execution = _execute_new(
                    definition=active_registry.get(rule_id),
                    evaluation=evaluation,
                    audit_id=audit.audit_id,
                    page_id=page_id,
                    snapshot_id=snapshot_id,
                    device=device,
                    manager=manager,
                    persistence=persistence,
                    resolver=resolver,
                    state=state,
                )
                execution_ids.append(execution.rule_execution_id)
                finding = _persist_finding_if_needed(active_registry.get(rule_id), execution, persistence)
                if finding is not None:
                    finding_ids.append(finding.finding_id)

    return M5ExecutionResult(
        rule_execution_ids=tuple(execution_ids),
        finding_ids=tuple(finding_ids),
        registry_rule_ids=active_registry.ids(),
    )


def _validate_registry(registry: RuleRegistry) -> None:
    expected = tuple(f"BR-GEO-{number:03d}" for number in range(1, 19))
    if registry.ids() != expected:
        raise ValueError("M5 registry must contain BR-GEO-001..018 in normative order")


def _execute_new(
    *,
    definition: RuleDefinition,
    evaluation: RuleEvaluation,
    audit_id: str,
    page_id: str | None,
    snapshot_id: str | None,
    device: DeviceContext | None,
    manager: EvidenceManager,
    persistence: AuditPersistence,
    resolver: DependencyResolver,
    state: _ExecutionState,
) -> RuleExecution:
    dependency = resolver.resolve(
        definition,
        lambda dep: state.lookup(dep, page_id=page_id, snapshot_id=snapshot_id),
    )
    active_evaluation = evaluation
    if not dependency.applicable:
        active_evaluation = RuleEvaluation(
            result=dependency.result or RuleResult.UNKNOWN,
            observed_value={"dependency_reason": dependency.reason},
            expected_condition=evaluation.expected_condition,
            reason=dependency.reason,
        )

    evidence = manager.record(
        audit_id=audit_id,
        page_id=page_id,
        snapshot_id=snapshot_id,
        device=device,
        evidence_type=EvidenceType.COMPARISON if definition.rule_id == "BR-GEO-015" else EvidenceType.HTML_ELEMENT,
        source=f"rules:{definition.rule_id}",
        observed_value={
            "result": active_evaluation.result.value,
            "observed": active_evaluation.observed_value,
            "checks": [
                {
                    "check_id": check.check_id,
                    "passed": check.passed,
                    "observed": check.observed,
                    "reason": check.reason,
                }
                for check in active_evaluation.checks
            ],
            "reason": active_evaluation.reason,
        },
    )
    execution = RuleExecution(
        rule_execution_id=new_id("REX"),
        audit_id=audit_id,
        rule_id=definition.rule_id,
        rule_version=_RULE_VERSION,
        page_id=page_id,
        snapshot_id=snapshot_id,
        device=device,
        result=active_evaluation.result,
        observed_value=active_evaluation.observed_value,
        expected_condition=active_evaluation.expected_condition,
        evidence_ids=(evidence.evidence_id,),
        executed_at=utc_now(),
        error=active_evaluation.reason if active_evaluation.result is RuleResult.ERROR else None,
    )
    persistence.rule_executions.add(execution)
    state.put(execution)
    return execution


def _persist_finding_if_needed(
    definition: RuleDefinition,
    execution: RuleExecution,
    persistence: AuditPersistence,
) -> Finding | None:
    if execution.result not in {RuleResult.FAIL, RuleResult.WARNING}:
        return None
    if not execution.evidence_ids:
        return None
    if execution.device is DeviceContext.DESKTOP:
        device = FindingDevice.DESKTOP
    elif execution.device is DeviceContext.MOBILE:
        device = FindingDevice.MOBILE
    else:
        device = FindingDevice.BOTH
    finding = Finding(
        finding_id=new_id("FND"),
        audit_id=execution.audit_id,
        rule_id=execution.rule_id,
        rule_execution_id=execution.rule_execution_id,
        page_id=execution.page_id,
        device=device,
        category=definition.category,
        severity=definition.severity,
        source="deterministic-rules-engine",
        title=definition.name,
        observed_value=execution.observed_value,
        expected_condition=execution.expected_condition,
        evidence_ids=execution.evidence_ids,
        status="OPEN",
    )
    persistence.findings.add(finding)
    return finding


def _evaluate_target(audit: Audit, target: AuditTarget) -> RuleEvaluation:
    valid = True
    reason = None
    try:
        normalized = normalize_url(target.input_url)
        origin = normalized_origin(normalized)
        valid = target.audit_id == audit.audit_id and normalized_origin(target.normalized_origin) == origin
    except ValueError as exc:
        normalized = None
        origin = None
        valid = False
        reason = type(exc).__name__
    return RuleEvaluation(
        result=RuleResult.PASS if valid else RuleResult.FAIL,
        observed_value={"normalized_url": normalized, "normalized_origin": origin, "target_type": target.target_type.value},
        expected_condition="audit target is valid, normalized and scoped to the audit",
        checks=(Check("target_normalized", valid, normalized, reason),),
    )


def _evaluate_sitemaps(m2: M2ExecutionResult) -> RuleEvaluation:
    states = [item.state for item in m2.discovery.sitemaps]
    if any(state is SitemapState.NETWORK_ERROR for state in states):
        result = RuleResult.UNKNOWN
        reason = "SITEMAP_NETWORK_ERROR"
    elif any(state is SitemapState.INVALID for state in states):
        result = RuleResult.FAIL
        reason = "SITEMAP_INVALID"
    elif any(state is SitemapState.HTTP_ERROR for state in states):
        result = RuleResult.WARNING
        reason = "SITEMAP_HTTP_ERROR"
    elif any(state is SitemapState.OBTAINED for state in states):
        result = RuleResult.PASS
        reason = None
    else:
        result = RuleResult.WARNING
        reason = "SITEMAP_ABSENT"
    return RuleEvaluation(
        result=result,
        observed_value={"sitemaps": [{"url": item.url, "state": item.state.value, "error": item.error} for item in m2.discovery.sitemaps]},
        expected_condition=(
            "a usable sitemap is a modest positive discovery signal; absence is a small readiness gap, "
            "and an invalid published sitemap is materially unfavorable"
        ),
        reason=reason,
    )


def _evaluate_final_response(acquisition: Any) -> RuleEvaluation:
    status = acquisition.status
    if acquisition.network_error is not None:
        result = RuleResult.NOT_APPLICABLE
    elif status is None:
        result = RuleResult.UNKNOWN
    elif 200 <= status <= 299:
        result = RuleResult.PASS
    else:
        result = RuleResult.FAIL
    return RuleEvaluation(
        result=result,
        observed_value={"status": status, "final_url": acquisition.final_url},
        expected_condition="final HTTP response is usable for the intended page",
    )


def _evaluate_redirect_materiality(acquisition: Any) -> RuleEvaluation:
    hops = len(acquisition.redirects)
    result = RuleResult.WARNING if hops >= _MATERIAL_REDIRECT_HOPS else RuleResult.PASS
    return RuleEvaluation(
        result=result,
        observed_value={"redirect_count": hops, "materiality_threshold": _MATERIAL_REDIRECT_HOPS},
        expected_condition="redirect chain remains below the versioned materiality threshold",
        reason="EXCESSIVE_REDIRECT_CHAIN" if result is RuleResult.WARNING else None,
    )


def _evaluate_analyzable_html(acquisition: Any) -> RuleEvaluation:
    content_type = (acquisition.header("Content-Type") or "").lower()
    expected_html = "html" in content_type or not content_type
    if not expected_html:
        result = RuleResult.NOT_APPLICABLE
    elif acquisition.body:
        result = RuleResult.PASS
    else:
        result = RuleResult.FAIL
    return RuleEvaluation(
        result=result,
        observed_value={"content_type": content_type or None, "body_bytes": len(acquisition.body)},
        expected_condition="expected HTML documents expose analyzable document content",
    )


def _evaluate_rendering(
    *, snapshot_id: str, render_failed: bool, extraction_failure: str | None, main_content_ref: str | None
) -> RuleEvaluation:
    if not render_failed:
        result = RuleResult.PASS
        reason = None
    elif extraction_failure == "EXTRACTION_INPUT_UNAVAILABLE" or not main_content_ref:
        result = RuleResult.FAIL
        reason = "RENDER_FAILURE_PREVENTED_CONTENT_RECOVERY"
    else:
        result = RuleResult.UNKNOWN
        reason = "RENDER_FAILED_BUT_RAW_FALLBACK_REMAINED_ANALYZABLE"
    return RuleEvaluation(
        result=result,
        observed_value={"snapshot_id": snapshot_id, "render_failed": render_failed, "main_content_ref": main_content_ref, "extraction_failure": extraction_failure},
        expected_condition="rendering failure does not prevent recovery of essential analyzable content",
        reason=reason,
    )


def _directive_tokens(acquisition: Any, meta_robots: str | None) -> dict[str, set[str]]:
    header = {token.strip().lower() for value in acquisition.header_values("X-Robots-Tag") for token in value.replace(";", ",").split(",") if token.strip()}
    meta = {token.strip().lower() for token in (meta_robots or "").split(",") if token.strip()}
    return {"header": header, "meta": meta}


def _has_noindex(tokens: set[str]) -> bool:
    return any(token == "noindex" or token.endswith(": noindex") for token in tokens)


def _has_index(tokens: set[str]) -> bool:
    return any(token == "index" or token.endswith(": index") for token in tokens)


def _evaluate_index_directives(acquisition: Any, meta_robots: str | None) -> RuleEvaluation:
    tokens = _directive_tokens(acquisition, meta_robots)
    combined = tokens["header"] | tokens["meta"]
    conflict = _has_noindex(combined) and _has_index(combined)
    return RuleEvaluation(
        result=RuleResult.FAIL if conflict else RuleResult.PASS,
        observed_value={"x_robots_tag": sorted(tokens["header"]), "meta_robots": sorted(tokens["meta"]), "conflict": conflict},
        expected_condition="indexability directives are interpretable and non-conflicting",
    )


def _evaluate_noindex(acquisition: Any, meta_robots: str | None) -> RuleEvaluation:
    tokens = _directive_tokens(acquisition, meta_robots)
    noindex = _has_noindex(tokens["header"] | tokens["meta"])
    return RuleEvaluation(
        result=RuleResult.WARNING if noindex else RuleResult.PASS,
        observed_value={"explicit_noindex": noindex, "x_robots_tag": sorted(tokens["header"]), "meta_robots": sorted(tokens["meta"])},
        expected_condition="explicit noindex directives are detected and surfaced when present",
        reason="EXPLICIT_NOINDEX" if noindex else None,
    )


class _CanonicalParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.values: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "link":
            return
        values = {key.lower(): value or "" for key, value in attrs}
        rel = {token.lower() for token in values.get("rel", "").split()}
        href = values.get("href", "").strip()
        if "canonical" in rel and href:
            self.values.append(href)


def _artifact_text(workspace: AuditWorkspace, reference: str | None) -> str | None:
    if not reference:
        return None
    path = workspace.root / reference
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8", errors="replace")


def _canonical_values(snapshot: Any, workspace: AuditWorkspace) -> tuple[str, ...]:
    html = _artifact_text(workspace, snapshot.rendered_artifact_ref)
    if html is None:
        return (snapshot.canonical,) if snapshot.canonical else ()
    parser = _CanonicalParser()
    parser.feed(html)
    parser.close()
    return tuple(parser.values)


def _evaluate_canonical(snapshot: Any, workspace: AuditWorkspace) -> RuleEvaluation:
    values = _canonical_values(snapshot, workspace)
    if not values:
        return RuleEvaluation(
            result=RuleResult.WARNING,
            observed_value={"canonicals": []},
            expected_condition="canonical declarations are interpretable and non-conflicting; absence is surfaced conservatively",
            reason="CANONICAL_ABSENT",
        )
    normalized: list[str] = []
    invalid: list[str] = []
    for value in values:
        try:
            normalized.append(normalize_url(value, base_url=snapshot.final_url or snapshot.requested_url))
        except ValueError:
            invalid.append(value)
    unique = tuple(dict.fromkeys(normalized))
    failed = bool(invalid) or len(unique) > 1
    return RuleEvaluation(
        result=RuleResult.FAIL if failed else RuleResult.PASS,
        observed_value={"declared": list(values), "normalized": list(unique), "invalid": invalid},
        expected_condition="canonical declarations parse to at most one valid target",
    )


def _evaluate_canonical_target(snapshot: Any, m2: M2ExecutionResult) -> RuleEvaluation:
    canonical = snapshot.canonical
    if not canonical:
        return RuleEvaluation(RuleResult.NOT_APPLICABLE, {"canonical": None}, "declared canonical target is technically valid and contextually plausible")
    try:
        normalized = normalize_url(canonical, base_url=snapshot.final_url or snapshot.requested_url)
    except ValueError:
        return RuleEvaluation(RuleResult.FAIL, {"canonical": canonical, "valid": False}, "declared canonical target is technically valid and contextually plausible")
    acquisition = m2.discovery.page_acquisitions.get(normalized)
    if acquisition is None:
        result = RuleResult.UNKNOWN
        status = None
        reason = "CANONICAL_TARGET_OUTSIDE_AUDITED_UNIVERSE"
    else:
        status = acquisition.status
        result = RuleResult.PASS if acquisition.network_error is None and status is not None and 200 <= status <= 299 else RuleResult.FAIL
        reason = None
    same_origin = is_same_origin(normalized, m2.discovery.origin)
    return RuleEvaluation(
        result=result,
        observed_value={"canonical": canonical, "normalized": normalized, "same_origin": same_origin, "target_status": status},
        expected_condition="declared canonical target is technically valid and contextually plausible",
        reason=reason,
    )


def _evaluate_raw_rendered_indexability(snapshot: Any, workspace: AuditWorkspace) -> RuleEvaluation:
    raw = _artifact_text(workspace, snapshot.raw_artifact_ref)
    rendered = _artifact_text(workspace, snapshot.rendered_artifact_ref)
    if raw is None or rendered is None:
        return RuleEvaluation(
            RuleResult.UNKNOWN,
            {"raw_available": raw is not None, "rendered_available": rendered is not None},
            "JavaScript does not introduce unsafe canonical or indexability conflicts",
            reason="RAW_OR_RENDERED_UNAVAILABLE",
        )
    extractor = ContentExtractor()
    raw_page = extractor.extract(raw)
    rendered_page = extractor.extract(rendered)
    raw_noindex = _has_noindex({token.strip().lower() for token in (raw_page.meta_robots or "").split(",") if token.strip()})
    rendered_noindex = _has_noindex({token.strip().lower() for token in (rendered_page.meta_robots or "").split(",") if token.strip()})
    canonical_conflict = bool(raw_page.canonical and rendered_page.canonical and raw_page.canonical != rendered_page.canonical)
    directive_conflict = raw_noindex != rendered_noindex
    conflict = canonical_conflict or directive_conflict
    return RuleEvaluation(
        result=RuleResult.FAIL if conflict else RuleResult.PASS,
        observed_value={
            "raw_canonical": raw_page.canonical,
            "rendered_canonical": rendered_page.canonical,
            "raw_noindex": raw_noindex,
            "rendered_noindex": rendered_noindex,
            "canonical_conflict": canonical_conflict,
            "directive_conflict": directive_conflict,
        },
        expected_condition="JavaScript does not introduce unsafe canonical or indexability conflicts",
    )


def _evaluate_soft404(snapshot: Any, acquisition: Any, workspace: AuditWorkspace) -> RuleEvaluation:
    rendered = _artifact_text(workspace, snapshot.rendered_artifact_ref)
    if rendered is None:
        return RuleEvaluation(
            RuleResult.UNKNOWN,
            {"http_status": acquisition.status, "rendered_available": False},
            "error-like pages do not masquerade as valid indexable pages",
            reason="RENDERED_UNAVAILABLE",
        )
    detected = JavascriptSpaAnalyzer().soft404(
        http_status=acquisition.status,
        rendered_html=rendered,
    )
    return RuleEvaluation(
        RuleResult.FAIL if detected else RuleResult.PASS,
        {"http_status": acquisition.status, "soft_404": detected, "rendered_available": True},
        "error-like pages do not masquerade as valid indexable pages",
        reason="STRONG_SOFT_404_SIGNAL" if detected else None,
    )

def _evaluate_robots(m2: M2ExecutionResult) -> RuleEvaluation:
    state = m2.discovery.robots.state
    if state is RobotsState.OBTAINED:
        result = RuleResult.PASS
        reason = None
    elif state is RobotsState.ABSENT:
        result = RuleResult.WARNING
        reason = "ROBOTS_ABSENT"
    else:
        result = RuleResult.UNKNOWN
        reason = f"ROBOTS_{state.value}"
    return RuleEvaluation(
        result=result,
        observed_value={"state": state.value, "url": m2.discovery.robots.url},
        expected_condition=(
            "robots.txt is interpretable when present; absence is not a crawling failure, "
            "but it does not receive the same positive readiness factor as an explicit usable policy"
        ),
        reason=reason,
    )


def _evaluate_crawlers(m2: M2ExecutionResult) -> RuleEvaluation:
    access = m2.discovery.robots.crawler_access
    unresolved: list[dict[str, str]] = []
    blocked_search: list[dict[str, str]] = []
    blocked_gptbot: list[str] = []
    for url, crawlers in access.items():
        for crawler in (*_SEARCH_CRAWLERS, "GPTBot"):
            allowed = crawlers.get(crawler)
            if allowed is None:
                unresolved.append({"url": url, "crawler": crawler})
            elif allowed is False and crawler in _SEARCH_CRAWLERS:
                blocked_search.append({"url": url, "crawler": crawler})
            elif allowed is False and crawler == "GPTBot":
                blocked_gptbot.append(url)
    if unresolved:
        result = RuleResult.UNKNOWN
        reason = "CRAWLER_ACCESS_UNRESOLVED"
    elif blocked_search:
        result = RuleResult.WARNING
        reason = "SEARCH_CRAWLER_BLOCKED"
    else:
        result = RuleResult.PASS
        reason = None
    return RuleEvaluation(
        result=result,
        observed_value={"blocked_search_crawlers": blocked_search, "blocked_gptbot": blocked_gptbot, "unresolved": unresolved},
        expected_condition="crawler access is resolved independently; GPTBot blocking alone does not penalize Search readiness",
        reason=reason,
    )
