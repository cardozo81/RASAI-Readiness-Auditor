"""Governed runtime/report integration for Improvement Intelligence.

Deep analysis is additive and non-scoring, but it is still AI work.  It therefore runs
inside the explicit governed AI phase, after evidence sealing and before reporting.
The report finalizer is projection-only and never invokes a provider.
"""
from __future__ import annotations

from decimal import Decimal
from pathlib import Path
import sqlite3
from typing import Any

from rasai.ai_governance import begin_round, complete_round, register_task
from rasai.audit_fulfillment import (
    FAILED_RETRYABLE,
    REPLAY_SAFE,
    SUCCESS,
    register_work_item,
    set_work_item_status,
)
from rasai.audit_phase_runtime import register_ai_hook
from rasai.improvement_intelligence import (
    CONTRACT_VERSION,
    REPORT_FILE,
    ImprovementConfig,
    execute_improvement_intelligence,
)
from rasai.operational_log import try_append_operational_event

_INSTALLED = False
_SURFACE_ID = "improvement-intelligence"
_COMPONENT = "IMPROVEMENT_INTELLIGENCE"


def _fulfillment_configuration(config: ImprovementConfig) -> dict[str, Any]:
    return {
        "requested": True,
        "provider": config.provider,
        "model": config.model,
        "reasoning": config.reasoning,
        "domains": list(config.domains),
        "max_recommendations": config.max_recommendations,
        "language": config.language,
    }


def _register_required_fulfillment(workspace: Any, audit_id: str, config: ImprovementConfig) -> None:
    register_work_item(
        workspace,
        audit_id=audit_id,
        component=_COMPONENT,
        required=True,
        temporal_mode=REPLAY_SAFE,
        retryable=True,
        configuration=_fulfillment_configuration(config),
    )


def _project_fulfillment_result(
    workspace: Any,
    audit_id: str,
    *,
    status: str,
    reason: str | None = None,
) -> None:
    normalized = str(status or "").strip().upper()
    if normalized == "COMPLETE":
        set_work_item_status(
            workspace,
            audit_id=audit_id,
            component=_COMPONENT,
            status=SUCCESS,
        )
        return
    set_work_item_status(
        workspace,
        audit_id=audit_id,
        component=_COMPONENT,
        status=FAILED_RETRYABLE,
        error_class="AI_ANALYSIS",
        error_code=normalized or "IMPROVEMENT_INTELLIGENCE_UNAVAILABLE",
        error_message=str(reason or normalized or "Improvement Intelligence não concluída")[:512],
        retryable=True,
    )


def _install_report_contract() -> None:
    from rasai import context_scope_runtime, report_contract, report_manifest, report_navigation, report_registry

    if not any(surface.id == _SURFACE_ID for surface in report_contract.REPORT_SURFACES):
        surface = report_contract.ReportSurface(
            id=_SURFACE_ID,
            filename=REPORT_FILE,
            label="Análise profunda e melhorias",
            optional=False,
            inputs=(
                "evidências persistidas da URL alvo",
                "HTML bruto/renderizado e estrutura semântica",
                "Findings/RuleExecutions",
                "PageSpeed/Lighthouse quando coletado",
                "SERP/Competitive Search Intelligence quando observado",
                "robots.txt, sitemap, llms.txt e diagnósticos de descoberta",
                "headers HTTP persistidos para postura de segurança passiva",
            ),
            outputs=(
                "backlog priorizado evidence-bound",
                "recomendações técnicas e de conteúdo",
                "HTML original versus HTML sugerido pela IA",
                "hipóteses de melhoria SEO/SERP sem causalidade de ranking",
                "postura de segurança passiva e remediações",
                "impacto potencial por Performance/SEO/Best Practices/Acessibilidade/AI Access/Security",
            ),
            required_dependencies=("audit.db",),
            optional_dependencies=(
                "exatamente uma URL de entrada",
                "provider de IA explícito",
                "Web Performance/Lighthouse",
                "Search Intelligence",
            ),
            ai_usage=(
                "Quando habilitada, executa na fase de IA governada, após o sealing de evidências, "
                "reutilizando a orquestração canônica de provider. Cada tentativa permanece em ai_provider_attempts."
            ),
            score_impact="Nenhum; advisory/non-scoring. SARI/SCORE-GEO permanecem determinísticos e independentes da recomendação.",
            source_of_truth="audit.db + artifacts persistidos; sugestões de IA são derivadas e identificadas separadamente",
        )
        surfaces = list(report_contract.REPORT_SURFACES)
        insertion = next(
            (index for index, item in enumerate(surfaces) if item.id == "content-suggestions"),
            len(surfaces),
        )
        surfaces.insert(insertion, surface)
        report_contract.REPORT_SURFACES = tuple(surfaces)
        report_contract.CANONICAL_NAV_ITEMS = tuple(
            (item.label, item.filename) for item in report_contract.REPORT_SURFACES
        )
        report_contract.CANONICAL_FILENAMES = tuple(
            item.filename for item in report_contract.REPORT_SURFACES
        )

    report_navigation.CANONICAL_NAV_ITEMS = report_contract.CANONICAL_NAV_ITEMS
    report_navigation.NAV_ITEMS = report_contract.CANONICAL_NAV_ITEMS
    report_registry.CANONICAL_NAV_ITEMS = report_contract.CANONICAL_NAV_ITEMS
    report_registry.REPORT_SURFACES = report_contract.REPORT_SURFACES
    report_manifest.REPORT_SURFACES = report_contract.REPORT_SURFACES

    groups: list[tuple[str, tuple[str, ...]]] = []
    for label, filenames in context_scope_runtime._NAV_GROUPS:
        values = list(filenames)
        if label == "Ações e referência" and REPORT_FILE not in values:
            anchor = values.index("content-suggestions.html") if "content-suggestions.html" in values else 0
            values.insert(anchor, REPORT_FILE)
        groups.append((label, tuple(values)))
    context_scope_runtime._NAV_GROUPS = tuple(groups)


def _install_consolidated_boundary() -> None:
    try:
        from rasai.consolidation import reporting
    except Exception:
        return
    original = reporting._render_executive
    if getattr(original, "_rasai_improvement_boundary", False):
        return

    def render_executive(data):
        html = original(data)
        notice = (
            "<section class='notice' data-current-rasai-boundary='true'><strong>Fronteira do consolidado atual:</strong> "
            "SARI/SCORE-GEO, Coverage, Confidence e gates mantêm sua série metodológica própria. Lighthouse/Core Web Vitals, "
            "Apdex, SERP/Search Intelligence, postura de segurança e Improvement Intelligence são sinais complementares e não são "
            "promediados artificialmente dentro do SARI temporal. Recomendações de IA são advisory e o ganho só é tratado como "
            "observado depois de nova medição/before-after.</section>"
        )
        return notice + html

    render_executive._rasai_improvement_boundary = True
    render_executive._rasai_original = original
    reporting._render_executive = render_executive


def _install_ai_cost_attribution() -> None:
    try:
        from rasai import documented_contract_reconciliation as reconciliation
    except Exception:
        return
    original = reconciliation._db_ai_costs
    if getattr(original, "_rasai_improvement_cost_attribution", False):
        return

    def db_ai_costs(database: Path) -> dict[str, dict[str, Decimal]]:
        totals: dict[str, dict[str, Decimal]] = {}
        if not database.is_file():
            return totals
        connection = sqlite3.connect(database)
        try:
            definitions = (
                (
                    "ai_provider_attempts",
                    "CASE "
                    f"WHEN semantic_contract_version='{CONTRACT_VERSION}' THEN 'Improvement Intelligence por IA' "
                    "WHEN semantic_contract_version LIKE 'M24-%' THEN 'Remediação técnica por IA' "
                    "ELSE 'Análise semântica por IA' END",
                ),
                ("content_remediation_attempts", "'Remediação textual por IA'"),
            )
            for table, label_sql in definitions:
                exists = connection.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
                ).fetchone()
                if not exists:
                    continue
                rows = connection.execute(
                    f"SELECT {label_sql},cost_currency,SUM(estimated_cost) FROM {table} "
                    "WHERE estimated_cost IS NOT NULL AND cost_currency IS NOT NULL GROUP BY 1,cost_currency"
                ).fetchall()
                for label, currency, amount in rows:
                    bucket = totals.setdefault(str(currency), {})
                    bucket[str(label)] = bucket.get(str(label), Decimal("0")) + Decimal(str(amount))
        finally:
            connection.close()
        return totals

    db_ai_costs._rasai_improvement_cost_attribution = True
    db_ai_costs._rasai_original = original
    reconciliation._db_ai_costs = db_ai_costs


def _governed_improvement_hook(*, audit_id: str, workspace: Any, evidence_snapshot: Any):
    """Execute deep analysis inside the governed AI phase, never in reporting."""
    try:
        config = ImprovementConfig.from_environment()
    except Exception as exc:
        try_append_operational_event(
            workspace,
            "IMPROVEMENT_INTELLIGENCE_CONFIGURATION_INVALID",
            level="WARNING",
            audit_id=audit_id,
            error_type=type(exc).__name__,
            error_message=str(exc)[:512],
            scoring_impact="NONE",
        )
        return {"status": "SKIPPED", "reason": "CONFIGURATION_INVALID"}

    if not config.enabled:
        return {"status": "SKIPPED", "reason": "DISABLED"}

    _register_required_fulfillment(workspace, audit_id, config)
    requirements = tuple(f"DOMAIN:{domain}" for domain in config.domains)
    task_id = register_task(
        workspace=workspace,
        audit_id=audit_id,
        purpose=_COMPONENT,
        scope_type="AUDIT",
        scope_key="AUDIT",
        evidence_snapshot_id=evidence_snapshot.evidence_snapshot_id,
        requirements=requirements,
        semantic_contract_version=CONTRACT_VERSION,
    )
    round_id = begin_round(
        workspace=workspace,
        ai_task_id=task_id,
        requested_requirements=requirements,
        input_payload={
            "evidence_snapshot_id": evidence_snapshot.evidence_snapshot_id,
            "evidence_fingerprint": evidence_snapshot.fingerprint,
            "config_fingerprint": config.fingerprint(),
            "domains": list(config.domains),
        },
        input_summary={
            "evidence_count": len(evidence_snapshot.evidence_ids),
            "domains": list(config.domains),
            "provider": config.provider,
            "model": config.model,
        },
    )

    try_append_operational_event(
        workspace,
        "IMPROVEMENT_INTELLIGENCE_STARTED",
        audit_id=audit_id,
        contract_version=CONTRACT_VERSION,
        provider=config.provider,
        model=config.model,
        reasoning=config.reasoning,
        domains=config.domains,
        scoring_impact="NONE",
        security_mode="PASSIVE_ONLY",
        evidence_snapshot_id=evidence_snapshot.evidence_snapshot_id,
    )

    def progress(stage: str, percent: float, detail: str) -> None:
        try_append_operational_event(
            workspace,
            "IMPROVEMENT_INTELLIGENCE_STAGE",
            audit_id=audit_id,
            stage=stage,
            progress_percent=percent,
            detail=detail,
            provider=config.provider,
            model=config.model,
            evidence_snapshot_id=evidence_snapshot.evidence_snapshot_id,
        )

    try:
        result = execute_improvement_intelligence(
            audit_id=audit_id,
            workspace=workspace,
            config=config,
            progress=progress,
        )
        _project_fulfillment_result(
            workspace,
            audit_id,
            status=result.status,
            reason=result.reason,
        )
        # Improvement Intelligence returns one consolidated contract.  Domain-specific
        # records remain in its existing tables; governance marks each requested domain
        # as resolved only when the contract completed.  A limited/failed run remains
        # partial and can be reprocessed without overwriting the accepted provider data.
        complete = str(result.status).upper() == "COMPLETE"
        accepted = (
            {requirement: {"status": "COMPLETE"} for requirement in requirements}
            if complete
            else {}
        )
        complete_round(
            workspace=workspace,
            ai_round_id=round_id,
            accepted=accepted,
            rejected={},
            missing=() if complete else requirements,
            output_payload={
                "status": result.status,
                "target_url": result.target_url,
                "findings_count": result.findings_count,
                "recommendations_count": result.recommendations_count,
                "provider": result.provider,
                "model": result.model,
                "reason": result.reason,
                "reused": result.reused,
            },
            failed=not complete,
        )
        try_append_operational_event(
            workspace,
            "IMPROVEMENT_INTELLIGENCE_COMPLETED",
            level="WARNING" if result.status == "COMPLETE_WITH_LIMITATIONS" else "INFO",
            audit_id=audit_id,
            status=result.status,
            target_url=result.target_url,
            findings=result.findings_count,
            recommendations=result.recommendations_count,
            provider=result.provider,
            model=result.model,
            reasoning=result.reasoning,
            reason=result.reason,
            reused=result.reused,
            scoring_impact="NONE",
            evidence_snapshot_id=evidence_snapshot.evidence_snapshot_id,
        )
        return {
            "status": result.status,
            "findings": result.findings_count,
            "recommendations": result.recommendations_count,
            "reused": result.reused,
        }
    except Exception as exc:
        _project_fulfillment_result(
            workspace,
            audit_id,
            status="RUNTIME_ERROR",
            reason=f"{type(exc).__name__}: {str(exc)[:400]}",
        )
        complete_round(
            workspace=workspace,
            ai_round_id=round_id,
            accepted={},
            rejected={"RUNTIME": {"error_type": type(exc).__name__, "message": str(exc)[:400]}},
            missing=requirements,
            output_payload={"error_type": type(exc).__name__, "message": str(exc)[:400]},
            failed=True,
        )
        try_append_operational_event(
            workspace,
            "IMPROVEMENT_INTELLIGENCE_FAILURE",
            level="WARNING",
            audit_id=audit_id,
            error_type=type(exc).__name__,
            error_message=str(exc)[:512],
            scoring_impact="NONE",
            evidence_snapshot_id=evidence_snapshot.evidence_snapshot_id,
        )
        return {"status": "ERROR", "reason": type(exc).__name__}


def _install_governed_ai_phase() -> None:
    register_ai_hook(_COMPONENT, _governed_improvement_hook, order=300)


def _install_report_completion() -> None:
    """Keep only report-contract projection in finalization; never execute AI here."""
    from rasai import report_completion

    if getattr(report_completion, "_rasai_improvement_intelligence_completion", False):
        return
    if REPORT_FILE not in report_completion.AUDIT_ALWAYS_PAGES:
        report_completion.AUDIT_ALWAYS_PAGES = (*report_completion.AUDIT_ALWAYS_PAGES, REPORT_FILE)

    original = report_completion.finalize_audit_report_site

    def finalize_with_improvement(
        *,
        audit_id: str,
        workspace: Any,
        context_interpretations=(),
        routing_snapshot=None,
    ):
        # The renderer stack (including progress_completion_refinement) reads the
        # already-persisted Improvement Intelligence state and writes HTML.  No
        # collector/provider is called from this wrapper.
        return original(
            audit_id=audit_id,
            workspace=workspace,
            context_interpretations=context_interpretations,
            routing_snapshot=routing_snapshot,
        )

    finalize_with_improvement._rasai_projection_only = True
    finalize_with_improvement._rasai_original = original
    report_completion.finalize_audit_report_site = finalize_with_improvement
    report_completion._rasai_improvement_intelligence_completion = True


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    from rasai.report_quality_reconciliation import install as install_report_quality_reconciliation

    install_report_quality_reconciliation()
    _install_report_contract()
    _install_consolidated_boundary()
    _install_ai_cost_attribution()
    _install_governed_ai_phase()
    _install_report_completion()
    _INSTALLED = True
