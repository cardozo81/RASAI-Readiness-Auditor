"""End-to-end audit orchestration for the stable local baseline."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from searchgeo import __version__
from searchgeo.content_extractability import execute_content_extractability
from searchgeo.domain import (
    Audit,
    AuditStatus,
    AuditTarget,
    CompletionStatus,
    TargetType,
    new_id,
    utc_now,
)
from searchgeo.m2 import execute_m2
from searchgeo.m3 import execute_m3
from searchgeo.m4 import execute_m4
from searchgeo.m5 import execute_m5
from searchgeo.m6 import execute_m6
from searchgeo.m7 import execute_m7
from searchgeo.m8 import execute_m8
from searchgeo.m9 import execute_m9
from searchgeo.m10 import execute_m10
from searchgeo.m11 import execute_m11
from searchgeo.m14_linking import link_findings_to_elements
from searchgeo.m14_persistence import M14Persistence
from searchgeo.m18_persistence import persist_provider_runtime
from searchgeo.m18_reporting import enrich_written_reports
from searchgeo.m20 import execute_m20
from searchgeo.m20_reporting import enrich_m20_report_site
from searchgeo.operational_log import try_append_operational_event
from searchgeo.persistence import AuditPersistence, AuditWorkspace
from searchgeo.pre_scoring_rules import execute_pre_scoring_rules
from searchgeo.report_site import materialize_report_site
from searchgeo.semantic import NoneProvider, SemanticAnalysisProvider
from searchgeo.source_quality import (
    assess_m2_result,
    limitation_strings,
    persist_assessment,
)
from searchgeo.source_quality_ai import maybe_explain_source_quality
from searchgeo.source_quality_browser import (
    browser_reconciliation_limitations,
    reconcile_source_quality_with_browser,
)
from searchgeo.url_utils import normalize_url, normalized_origin


@dataclass(frozen=True, slots=True)
class AuditRunResult:
    audit_id: str
    audit_root: Path
    report_path: Path
    completion_status: CompletionStatus
    audited_pages: int
    finding_count: int
    recommendation_count: int


def run_audit(
    target: str | Sequence[str],
    *,
    audits_root: str | Path = "audits",
    project_name: str | None = None,
    language: str = "pt-BR",
    market: str = "BR",
    max_pages: int = 100,
    semantic_provider: SemanticAnalysisProvider | None = None,
    content_remediation: bool = False,
    discovery_engine: Any | None = None,
    renderer: Any | None = None,
    lazy_probe: Any | None = None,
) -> AuditRunResult:
    """Execute the approved pipeline and leave a reopenable local audit workspace.

    ``target`` may be one URL/domain or an explicit sequence of URLs. A
    sequence always means URL_SET, even when normalization/deduplication leaves
    a single unique URL. This prevents an explicit set from silently falling
    back to ordinary crawl-expansion behavior.

    ``content_remediation`` enables M20 exact-text suggestions. It is OFF by
    default. M20 always materializes deterministic JSON-LD guidance, even when
    AI remediation is disabled, and never changes score/findings.
    """

    explicit_url_set = not isinstance(target, str)
    raw_targets, normalized_targets = _normalize_targets(target)
    if max_pages <= 0:
        raise ValueError("max_pages must be greater than zero")
    if len(normalized_targets) > max_pages:
        raise ValueError(
            f"explicit URL set contains {len(normalized_targets)} unique URLs but --max-pages is {max_pages}; "
            "increase --max-pages so no supplied URL is silently omitted"
        )

    origin = normalized_origin(normalized_targets[0])
    for normalized in normalized_targets[1:]:
        candidate_origin = normalized_origin(normalized)
        if candidate_origin != origin:
            raise ValueError(
                "all URLs in one audit must belong to the same normalized origin; "
                f"expected {origin}, got {candidate_origin}"
            )

    normalized_target = normalized_targets[0]
    project = (project_name or urlsplit(normalized_target).hostname or normalized_target).strip()
    if not project:
        raise ValueError("project_name must not be empty")

    audit_id = new_id("AUD")
    workspace = AuditWorkspace.create(Path(audits_root), audit_id)
    target_type = TargetType.URL_SET if explicit_url_set else _target_type(normalized_target)
    try_append_operational_event(
        workspace,
        "AUDIT_STARTED",
        audit_id=audit_id,
        project_name=project,
        target_type=target_type.value,
        normalized_origin=origin,
        supplied_targets=len(raw_targets),
        normalized_targets=len(normalized_targets),
        max_pages=max_pages,
        content_remediation=content_remediation,
        auditor_version=__version__,
    )

    capabilities = [
        "filesystem",
        "sqlite",
        "desktop_mobile",
        "visual_snapshot",
        "dom_element_observation",
        "static_report_site",
        "jsonld_remediation_guidance",
        "source_quality_fail_fast",
    ]
    if content_remediation:
        capabilities.append("optional_ai_content_remediation")
    if target_type is TargetType.URL_SET:
        capabilities.append("url_set")
    audit = Audit(
        audit_id=audit_id,
        project_name=project,
        status=AuditStatus.INITIALIZING,
        primary_language=language,
        market=market,
        max_pages=max_pages,
        capabilities=tuple(capabilities),
        created_at=utc_now(),
        started_at=utc_now(),
        auditor_version=__version__,
        ruleset_version="1",
    )
    audit_target = AuditTarget(
        target_id=new_id("TGT"),
        audit_id=audit_id,
        input_url=normalized_target,
        normalized_origin=origin,
        target_type=target_type,
    )

    with AuditPersistence(workspace) as persistence:
        persistence.audits.add(audit)
        persistence.targets.add(audit_target)
        with M14Persistence(workspace) as m14:
            normalized_per_raw = _normalized_per_raw(raw_targets)
            input_pairs: list[tuple[str, str]] = []
            seen: set[str] = set()
            for raw, normalized in zip(raw_targets, normalized_per_raw, strict=True):
                if normalized in seen:
                    continue
                seen.add(normalized)
                input_pairs.append((raw, normalized))
            m14.replace_input_urls(audit_id, tuple(input_pairs))
            m14.set_input_summary(
                audit_id,
                input_mode=target_type.value,
                supplied_count=len(raw_targets),
                normalized_unique_count=len(normalized_targets),
            )

        try:
            m2 = execute_m2(
                audit,
                audit_target,
                persistence,
                workspace,
                engine=discovery_engine,
                explicit_urls=(normalized_targets if target_type is TargetType.URL_SET else None),
            )

            source_quality = assess_m2_result(m2)
            persist_assessment(workspace, source_quality)
            preflight_source_blocked = source_quality.all_pages_hard_blocked
            browser_reconciliation = None

            if preflight_source_blocked:
                # M2 is intentionally crawler-like and can receive a different CDN/WAF/
                # redirect route than a real browser. Record the strong preflight signal,
                # but do not call it a definitive SOURCE_BLOCKED until the single normal
                # M3 Chromium navigation confirms the same technical blocker.
                try_append_operational_event(
                    workspace,
                    "SOURCE_QUALITY_PREFLIGHT_BLOCKER",
                    level="WARNING",
                    audit_id=audit_id,
                    blockers=source_quality.hard_blocker_kinds,
                    pages_considered=source_quality.pages_considered,
                    hard_blocked_pages=source_quality.hard_blocked_pages,
                    downstream_policy="VERIFY_ONCE_WITH_CHROMIUM_BEFORE_FAIL_FAST",
                )

            # Always allow the normal M3 Chromium pass to execute once. This is not an
            # extra retry: M3 needs that navigation for every successful audit anyway.
            # If it also fails, downstream repeated/external measurements are still cut.
            m3 = execute_m3(m2, persistence, workspace, renderer=renderer)

            if preflight_source_blocked:
                browser_reconciliation = reconcile_source_quality_with_browser(
                    assessment=source_quality,
                    m3_result=m3,
                    persistence=persistence,
                    workspace=workspace,
                )
                source_quality = browser_reconciliation.assessment

            source_blocked = source_quality.all_pages_hard_blocked
            if preflight_source_blocked:
                current = persistence.audits.get(audit_id)
                if source_blocked:
                    additions = limitation_strings(source_quality)
                elif browser_reconciliation is not None:
                    additions = browser_reconciliation_limitations(browser_reconciliation)
                else:
                    additions = ()
                if current is not None and additions:
                    persistence.audits.update(
                        replace(
                            current,
                            limitations=tuple(dict.fromkeys((*current.limitations, *additions))),
                        )
                    )

                if source_blocked:
                    try_append_operational_event(
                        workspace,
                        "SOURCE_QUALITY_BLOCKED",
                        level="ERROR",
                        audit_id=audit_id,
                        blockers=source_quality.hard_blocker_kinds,
                        pages_considered=source_quality.pages_considered,
                        hard_blocked_pages=source_quality.hard_blocked_pages,
                        downstream_policy="SKIP_REDUNDANT_BROWSER_AND_EXTERNAL_MEASUREMENTS",
                    )
                elif browser_reconciliation is not None and browser_reconciliation.recovered_any:
                    try_append_operational_event(
                        workspace,
                        "SOURCE_QUALITY_BROWSER_RECOVERED",
                        level="WARNING",
                        audit_id=audit_id,
                        recovered_urls=browser_reconciliation.recovered_urls,
                        browser_final_urls=tuple(
                            item.final_url for item in browser_reconciliation.browser_observations
                        ),
                        policy="CONTINUE_WITH_BROWSER_EVIDENCE_AND_REPORT_DIVERGENCE",
                    )

            rendered_contexts = sum(len(per_device) for per_device in m3.snapshot_ids.values())
            try_append_operational_event(
                workspace,
                "RENDERING_COMPLETED",
                audit_id=audit_id,
                pages=len(m3.snapshot_ids),
                contexts=rendered_contexts,
                failures=len(m3.failures),
                source_quality_preflight_blocker=preflight_source_blocked,
                source_quality_blocked=source_blocked,
                source_quality_browser_recovered=(
                    browser_reconciliation.recovered_any
                    if browser_reconciliation is not None
                    else False
                ),
            )
            m4 = execute_m4(m3, persistence, workspace)
            m5 = execute_m5(audit, audit_target, m2, m3, m4, persistence, workspace)
            m6 = execute_m6(
                audit_id=audit_id,
                m2_result=m2,
                m3_result=m3,
                m4_result=m4,
                m5_result=m5,
                persistence=persistence,
                workspace=workspace,
                lazy_probe=lazy_probe,
            )
            content = execute_content_extractability(
                audit_id=audit_id,
                m3_result=m3,
                persistence=persistence,
                workspace=workspace,
            )

            configured_provider = semantic_provider or NoneProvider()
            analysis_provider = NoneProvider() if source_blocked else configured_provider

            # A definitive blocker receives only the evidence-bound infrastructure AI
            # explanation. A browser-recovered divergence may also receive that one
            # explanation, but normal semantic analysis remains enabled because Chromium
            # produced trustworthy page content.
            explain_source_quality = source_blocked or (
                browser_reconciliation is not None and browser_reconciliation.recovered_any
            )
            if explain_source_quality:
                try:
                    ai_diagnosis = maybe_explain_source_quality(
                        audit_id=audit_id,
                        workspace=workspace,
                        provider=configured_provider,
                        assessment=source_quality,
                    )
                    try_append_operational_event(
                        workspace,
                        "SOURCE_QUALITY_AI_COMPLETED",
                        audit_id=audit_id,
                        state=ai_diagnosis.state.value,
                        provider=ai_diagnosis.provider,
                        model=ai_diagnosis.model,
                        reason=ai_diagnosis.reason,
                    )
                except Exception as exc:
                    try_append_operational_event(
                        workspace,
                        "SOURCE_QUALITY_AI_FAILURE",
                        level="WARNING",
                        audit_id=audit_id,
                        error_type=type(exc).__name__,
                        error_message=str(exc)[:512],
                    )

            m7 = execute_m7(
                audit_id=audit_id,
                m3_result=m3,
                m4_result=m4,
                m5_result=m5,
                m6_result=m6,
                persistence=persistence,
                workspace=workspace,
                provider=analysis_provider,
            )
            persist_provider_runtime(
                audit_id=audit_id,
                provider=configured_provider,
                workspace=workspace,
                audit_mode=m7.audit_mode.value,
            )
            try_append_operational_event(
                workspace,
                "AI_RUNTIME_RECORDED",
                audit_id=audit_id,
                provider_class=type(configured_provider).__name__,
                audit_mode=m7.audit_mode.value,
                source_quality_diagnostic_only=source_blocked,
            )

            _set_status(persistence, audit_id, AuditStatus.COMPARING)
            m8 = execute_m8(
                audit_id=audit_id,
                m3_result=m3,
                persistence=persistence,
                workspace=workspace,
            )

            findings_before_integrity = _unique(
                m5.finding_ids,
                m6.finding_ids,
                content.finding_ids,
                m7.finding_ids,
                m8.finding_ids,
            )
            pre_scoring = execute_pre_scoring_rules(
                audit_id=audit_id,
                m2_result=m2,
                m3_result=m3,
                persistence=persistence,
                workspace=workspace,
                finding_ids_to_validate=findings_before_integrity,
            )

            _set_status(persistence, audit_id, AuditStatus.SCORING)
            scoring_execution_ids = _unique(
                m5.rule_execution_ids,
                m6.rule_execution_ids,
                content.rule_execution_ids,
                m7.rule_execution_ids,
                m8.rule_execution_ids,
                pre_scoring.rule_execution_ids,
            )
            execute_m9(
                audit_id=audit_id,
                rule_execution_ids=scoring_execution_ids,
                persistence=persistence,
                workspace=workspace,
            )

            _set_status(persistence, audit_id, AuditStatus.RECOMMENDING)
            all_finding_ids = _unique(findings_before_integrity, pre_scoring.finding_ids)
            m10 = execute_m10(
                audit_id=audit_id,
                finding_ids=all_finding_ids,
                persistence=persistence,
                workspace=workspace,
            )
            link_findings_to_elements(
                finding_ids=all_finding_ids,
                persistence=persistence,
                workspace=workspace,
            )

            # M20 is strictly downstream of findings/scoring. It can only create
            # auxiliary suggestions and telemetry; it cannot mutate evaluated
            # entities or retroactively alter the audit result. A definitive source
            # blocker disables exact-text remediation because no trustworthy corpus exists.
            execute_m20(
                audit_id=audit_id,
                enabled=(content_remediation and not source_blocked),
                semantic_provider=analysis_provider,
                workspace=workspace,
            )

            _set_status(persistence, audit_id, AuditStatus.REPORTING)
            m11 = execute_m11(
                audit_id=audit_id,
                persistence=persistence,
                workspace=workspace,
            )
            enrich_written_reports(audit_id=audit_id, workspace=workspace)
            report_path = materialize_report_site(
                audit_id=audit_id,
                workspace=workspace,
                report_id=m11.report_id,
            )
            enrich_m20_report_site(audit_id=audit_id, workspace=workspace)
            try_append_operational_event(
                workspace,
                "REPORT_SITE_GENERATED",
                audit_id=audit_id,
                report_path=str(report_path.relative_to(workspace.root)),
            )

            current = persistence.audits.get(audit_id)
            if current is None:
                raise RuntimeError(f"audit disappeared before completion: {audit_id}")
            completion = (
                CompletionStatus.COMPLETE_WITH_LIMITATIONS
                if current.limitations or current.audit_mode is None or current.audit_mode.value != "FULL"
                else CompletionStatus.COMPLETE
            )
            persistence.audits.complete(audit_id, completion)
            try_append_operational_event(
                workspace,
                "AUDIT_COMPLETED",
                audit_id=audit_id,
                completion_status=completion.value,
                audited_pages=len(m2.page_ids),
                findings=len(all_finding_ids),
                recommendations=len(m10.recommendation_ids),
                source_quality_blocked=source_blocked,
            )

            return AuditRunResult(
                audit_id=audit_id,
                audit_root=workspace.root,
                report_path=report_path,
                completion_status=completion,
                audited_pages=len(m2.page_ids),
                finding_count=len(all_finding_ids),
                recommendation_count=len(m10.recommendation_ids),
            )
        except Exception as exc:
            current = persistence.audits.get(audit_id)
            if current is not None and current.status not in {AuditStatus.COMPLETED, AuditStatus.CANCELLED}:
                persistence.audits.update(replace(current, status=AuditStatus.FAILED))
            try_append_operational_event(
                workspace,
                "AUDIT_FAILED",
                level="ERROR",
                audit_id=audit_id,
                error_type=type(exc).__name__,
                error_message=str(exc)[:512],
            )
            raise


def _set_status(persistence: AuditPersistence, audit_id: str, status: AuditStatus) -> None:
    audit = persistence.audits.get(audit_id)
    if audit is None:
        raise RuntimeError(f"audit not found while setting status: {audit_id}")
    persistence.audits.update(replace(audit, status=status))


def _normalize_targets(target: str | Sequence[str]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    if isinstance(target, str):
        raw = (target,)
    else:
        raw = tuple(target)
    if not raw:
        raise ValueError("at least one target URL is required")
    if any(not isinstance(value, str) for value in raw):
        raise ValueError("every target must be a string URL or domain")
    normalized_per_raw = _normalized_per_raw(raw)
    normalized = tuple(dict.fromkeys(normalized_per_raw))
    return raw, normalized


def _normalized_per_raw(raw: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(normalize_url(value) for value in raw)


def _target_type(normalized_target: str) -> TargetType:
    parsed = urlsplit(normalized_target)
    return TargetType.DOMAIN if parsed.path in {"", "/"} and not parsed.query else TargetType.URL


def _unique(*groups: tuple[str, ...]) -> tuple[str, ...]:
    values: list[str] = []
    for group in groups:
        values.extend(group)
    return tuple(dict.fromkeys(values))
