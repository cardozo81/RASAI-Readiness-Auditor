"""End-to-end audit orchestration for the governed RASAi pipeline."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from rasai import __version__
from rasai.audit_phase_runtime import (
    mark_ai_sealed,
    run_collection_phase,
    run_registered_ai_phase,
    seal_collection_evidence,
)
from rasai.content_extractability import execute_content_extractability
from rasai.domain import (
    Audit,
    AuditStatus,
    AuditTarget,
    CompletionStatus,
    TargetType,
    new_id,
    utc_now,
)
from rasai.m2 import execute_m2
from rasai.m3 import execute_m3
from rasai.m4 import execute_m4
from rasai.m5 import execute_m5
from rasai.m6 import execute_m6
from rasai.m7 import execute_m7
from rasai.m8 import execute_m8
from rasai.m9 import execute_m9
from rasai.m10 import execute_m10
from rasai.m14_linking import link_findings_to_elements
from rasai.m14_persistence import M14Persistence
from rasai.m16_root_cause import materialize_root_causes
from rasai.m17_precision import materialize_m17_precision
from rasai.m18_persistence import persist_provider_runtime
from rasai.m20 import execute_m20
from rasai.m24_crawling_discovery import execute_m24, load_m24_result
from rasai.m24_governed_ai import execute_m24_ai_phase
from rasai.m24_scoring import persist_m24_scoring_assessments
from rasai.operational_log import try_append_operational_event
from rasai.persistence import AuditPersistence, AuditWorkspace
from rasai.pre_scoring_rules import execute_pre_scoring_rules
from rasai.recommendation_governance import evaluate_recommendations
from rasai.semantic import NoneProvider, SemanticAnalysisProvider
from rasai.source_quality import (
    assess_m2_result,
    limitation_strings,
    persist_assessment,
)
from rasai.source_quality_ai import maybe_explain_source_quality
from rasai.source_quality_browser import (
    browser_reconciliation_limitations,
    reconcile_source_quality_with_browser,
)
from rasai.url_utils import normalize_url, normalized_origin


@dataclass(frozen=True, slots=True)
class AuditRunResult:
    audit_id: str
    audit_root: Path
    report_path: Path | None
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
    technical_remediation: bool = False,
    discovery_engine: Any | None = None,
    renderer: Any | None = None,
    lazy_probe: Any | None = None,
) -> AuditRunResult:
    """Execute one governed audit and leave a reopenable local workspace.

    AI is never used as a collector.  All registered external observations reach a
    terminal state, M24 deterministic/network facts are materialized, and an immutable
    evidence version is sealed before the first governed provider boundary.  Existing
    provider routing/retry/fallback/cost telemetry remains unchanged inside each AI
    consumer.
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
        technical_remediation=technical_remediation,
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
        "governed_evidence_sealing",
        "dynamic_ai_tasks",
    ]
    if content_remediation:
        capabilities.append("optional_ai_content_remediation")
    if technical_remediation:
        capabilities.append("optional_ai_technical_discovery_assessment")
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

        from rasai.audit_resume_runtime import (
            finish_execution_session,
            persist_resume_plan,
            start_execution_session,
        )
        from rasai.device_context import configured_device_context

        execution_session = start_execution_session(
            workspace,
            audit_id,
            kind="INITIAL",
            source="AUDIT",
            reject_active=False,
        )

        try:
            persist_resume_plan(
                workspace,
                audit_id,
                targets=normalized_targets,
                target_type=target_type.value,
                language=language,
                market=market,
                max_pages=max_pages,
                device_context=configured_device_context(),
                content_remediation=content_remediation,
                technical_remediation=technical_remediation,
                semantic_ai_requested=str(getattr(semantic_provider, "name", "NONE") or "NONE").upper() not in {"", "NONE"},
                semantic_provider=str(getattr(semantic_provider, "name", "NONE") or "NONE"),
            )

            # ------------------------------------------------------------------
            # CORE COLLECTION / EXTRACTION
            # ------------------------------------------------------------------
            # Discovery/acquisition is a durable checkpoint of its own. If the
            # process dies inside M2, the attempt remains RUNNING and recovery can
            # distinguish that incomplete stage from already-completed page evidence.
            from rasai.audit_fulfillment import (
                FAILED_RETRYABLE,
                LIVE_RECOLLECTION,
                SUCCESS,
                begin_attempt,
                finish_attempt,
                register_work_item,
            )
            from rasai.core_reprocessing import DISCOVERY_ACQUISITION

            register_work_item(
                workspace,
                audit_id=audit_id,
                component=DISCOVERY_ACQUISITION,
                scope_key="AUDIT",
                required=True,
                temporal_mode=LIVE_RECOLLECTION,
                retryable=True,
                configuration={
                    "target_type": target_type.value,
                    "targets": list(normalized_targets),
                    "max_pages": max_pages,
                },
                source_captured_at=audit.started_at.isoformat() if audit.started_at else None,
            )
            discovery_attempt_id = begin_attempt(
                workspace,
                audit_id=audit_id,
                component=DISCOVERY_ACQUISITION,
                scope_key="AUDIT",
                metadata={"stage": "M2_DISCOVERY_ACQUISITION"},
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
            except Exception as exc:
                finish_attempt(
                    workspace,
                    discovery_attempt_id,
                    status=FAILED_RETRYABLE,
                    error_class=type(exc).__name__,
                    error_code="M2_DISCOVERY_ACQUISITION_FAILED",
                    error_message=str(exc),
                    retryable=True,
                )
                raise
            finish_attempt(
                workspace,
                discovery_attempt_id,
                status=SUCCESS,
                result_ref=f"discovery:{audit_id}:effective",
                retryable=True,
                metadata={"pages": len(m2.page_ids)},
            )

            source_quality = assess_m2_result(m2)
            persist_assessment(workspace, source_quality)
            preflight_source_blocked = source_quality.all_pages_hard_blocked
            browser_reconciliation = None

            if preflight_source_blocked:
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

            # One normal Chromium pass is still required to distinguish a crawler-like
            # acquisition block from an actual browser-visible source block.
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

            # ------------------------------------------------------------------
            # EXTERNAL COLLECTION.  Runtime-installed collectors (M21/M23, GSC,
            # CrUX history, Clarity, Common Crawl, etc.) must terminate here.
            # ------------------------------------------------------------------
            collection_states, collection_details = run_collection_phase(
                audit_id=audit_id,
                workspace=workspace,
                source_blocked=source_blocked,
            )

            # Deterministic comparison is independent from semantic AI and therefore
            # belongs to the pre-seal analytical context.
            _set_status(persistence, audit_id, AuditStatus.COMPARING)
            m8 = execute_m8(
                audit_id=audit_id,
                m3_result=m3,
                persistence=persistence,
                workspace=workspace,
            )

            # M24 owns one additional bounded network observation (llms.txt).  Run only
            # its deterministic side before sealing.  cli_extensions may already have
            # materialized this while composing M21/M23; in that case reuse it.
            m24_collected = load_m24_result(audit_id=audit_id, workspace=workspace)
            if m24_collected is None:
                m24_collected = execute_m24(
                    audit_id=audit_id,
                    workspace=workspace,
                    technical_ai=False,
                    semantic_provider=None,
                    allow_network=not source_blocked,
                )
            collection_states["CRAWLING_DISCOVERY"] = m24_collected.status
            collection_details["CRAWLING_DISCOVERY"] = {
                "status": m24_collected.status,
                "llms_state": m24_collected.llms_state,
                "diagnostics": m24_collected.diagnostics_count,
                "ai_deferred": technical_remediation,
            }

            evidence_snapshot = seal_collection_evidence(
                audit_id=audit_id,
                workspace=workspace,
                collection_states=collection_states,
                collection_details=collection_details,
            )

            configured_provider = semantic_provider or NoneProvider()
            analysis_provider = NoneProvider() if source_blocked else configured_provider
            try_append_operational_event(
                workspace,
                "AI_PHASE_STARTED",
                audit_id=audit_id,
                evidence_snapshot_id=evidence_snapshot.evidence_snapshot_id,
                evidence_fingerprint=evidence_snapshot.fingerprint,
            )

            # ------------------------------------------------------------------
            # GOVERNED AI ANALYSIS.  Every call below happens after EVIDENCE_SEALED.
            # ------------------------------------------------------------------
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
                        evidence_snapshot_id=evidence_snapshot.evidence_snapshot_id,
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
                evidence_snapshot_id=evidence_snapshot.evidence_snapshot_id,
            )

            m24 = execute_m24_ai_phase(
                audit_id=audit_id,
                workspace=workspace,
                provider=configured_provider,
                enabled=(technical_remediation and not source_blocked),
            )
            m24_scoring = persist_m24_scoring_assessments(
                audit_id=audit_id,
                persistence=persistence,
                ai_state=m24.ai_state,
                provider=m24.ai_provider,
                model=m24.ai_model,
                assessments=m24.ai_assessments,
            )

            findings_before_integrity = _unique(
                m5.finding_ids,
                m6.finding_ids,
                content.finding_ids,
                m7.finding_ids,
                m8.finding_ids,
                m24_scoring.finding_ids,
            )

            # M20 is advisory/non-scoring, but it is still provider work. Keep it in
            # the same governed AI window so no provider boundary remains after AI_SEALED.
            execute_m20(
                audit_id=audit_id,
                enabled=(content_remediation and not source_blocked),
                semantic_provider=analysis_provider,
                workspace=workspace,
            )

            registered_ai_outcomes = run_registered_ai_phase(
                audit_id=audit_id,
                workspace=workspace,
                evidence_snapshot=evidence_snapshot,
            )
            mark_ai_sealed(
                audit_id=audit_id,
                workspace=workspace,
                evidence_snapshot=evidence_snapshot,
                outcomes=registered_ai_outcomes,
            )

            # ------------------------------------------------------------------
            # FINAL BUSINESS DERIVATIONS. No provider/collector work is allowed here.
            # Integrity rules validate the complete AI-derived finding set before score
            # and recommendations are materialized.
            # ------------------------------------------------------------------
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
                m24_scoring.rule_execution_ids,
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

            # Recommendation governance is a persisted final derivation. It must be
            # complete before REPORTING starts so every HTML renderer/finalizer remains
            # a read-only projection over the already-final audit model.
            evaluate_recommendations(workspace.database, audit_id)

            # Flush every durable final derivation before REPORTING. This includes
            # configuration/provenance/fulfillment/cost data needed by the renderers.
            from rasai import ai_exchange_log
            from rasai.ai_execution_state import current_ai_executions
            from rasai.audit_configuration_reuse_runtime import persist_current_configuration
            from rasai.audit_fulfillment_runtime import finalize_core_work_item_before_reporting
            from rasai.console_cost_confirmation import persist_active_outcome_before_reporting
            from rasai.governed_report_projection_runtime import reconcile_before_reporting

            finalize_core_work_item_before_reporting(
                workspace=workspace,
                audit_id=audit_id,
                audited_pages=len(m2.page_ids),
            )
            persist_current_configuration(workspace.root, audit_id)
            for execution in current_ai_executions():
                ai_exchange_log.persist_ai_exchange_log(
                    audit_id=audit_id,
                    workspace=workspace,
                    recorder=execution.recorder,
                )
            reconcile_before_reporting(workspace=workspace, audit_id=audit_id)
            persist_active_outcome_before_reporting(audit_id=audit_id, workspace=workspace)

            # Root-cause and precision are durable audit derivations consumed by
            # report-catalog and downstream analysis. They belong to the core audit
            # flow and are independent of HTML projection.
            materialize_root_causes(audit_id=audit_id, workspace=workspace)
            materialize_m17_precision(audit_id=audit_id, workspace=workspace)
            report_path = None

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
                evidence_snapshot_id=evidence_snapshot.evidence_snapshot_id,
            )

            result = AuditRunResult(
                audit_id=audit_id,
                audit_root=workspace.root,
                report_path=report_path,
                completion_status=completion,
                audited_pages=len(m2.page_ids),
                finding_count=len(all_finding_ids),
                recommendation_count=len(m10.recommendation_ids),
            )
            finish_execution_session(
                workspace,
                execution_session,
                state="COMPLETED",
            )
            return result
        except Exception as exc:
            try:
                from rasai.fulfillment_execution_contract import _reconcile_requested_improvement
                _reconcile_requested_improvement(workspace, audit_id)
            except Exception as fulfillment_exc:
                try_append_operational_event(
                    workspace,
                    "AUDIT_FAILURE_FULFILLMENT_RECONCILIATION_FAILED",
                    level="WARNING",
                    audit_id=audit_id,
                    error_type=type(fulfillment_exc).__name__,
                )
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
            finish_execution_session(
                workspace,
                execution_session,
                state="FAILED",
                note=f"{type(exc).__name__}: {str(exc)[:512]}",
            )
            raise
        except BaseException as exc:
            # KeyboardInterrupt/SystemExit must release the in-process lease before
            # outer console/CLI cancellation handling runs. Abrupt process death cannot
            # execute this block and is reconciled later from PID/heartbeat state.
            finish_execution_session(
                workspace,
                execution_session,
                state="INTERRUPTED",
                note=f"{type(exc).__name__}: {str(exc)[:512]}",
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
