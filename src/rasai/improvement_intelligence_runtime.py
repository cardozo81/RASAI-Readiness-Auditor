"""Runtime/report integration for Improvement Intelligence.

The feature is additive and fail-open. It materializes one canonical advisory report,
keeps SARI/SCORE-GEO untouched and reuses only persisted audit/Search evidence.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from rasai.improvement_intelligence import (
    CONTRACT_VERSION,
    REPORT_FILE,
    ImprovementConfig,
    execute_improvement_intelligence,
    write_improvement_report,
)
from rasai.operational_log import try_append_operational_event

_INSTALLED = False
_SURFACE_ID = "improvement-intelligence"


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
            required_dependencies=("exatamente uma URL de entrada", "audit.db"),
            optional_dependencies=("provider de IA explícito", "Web Performance/Lighthouse", "Search Intelligence"),
            ai_usage=(
                "Quando habilitada, executa análise estruturada própria com provider/modelo/esforço escolhidos para esta finalidade, "
                "reutilizando somente a credencial já configurada. Cada tentativa é registrada em ai_provider_attempts."
            ),
            score_impact="Nenhum; advisory/non-scoring. SARI/SCORE-GEO permanecem determinísticos e independentes da recomendação.",
            source_of_truth="audit.db + artifacts persistidos; sugestões de IA são derivadas e identificadas separadamente",
        )
        surfaces = list(report_contract.REPORT_SURFACES)
        insertion = next((index for index, item in enumerate(surfaces) if item.id == "content-suggestions"), len(surfaces))
        surfaces.insert(insertion, surface)
        report_contract.REPORT_SURFACES = tuple(surfaces)
        report_contract.CANONICAL_NAV_ITEMS = tuple((item.label, item.filename) for item in report_contract.REPORT_SURFACES)
        report_contract.CANONICAL_FILENAMES = tuple(item.filename for item in report_contract.REPORT_SURFACES)

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


def _install_report_completion() -> None:
    from rasai import report_completion, report_navigation
    from rasai.report_manifest import write_report_manifest

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
        errors: list[str] = []
        try:
            config = ImprovementConfig.from_environment()
        except Exception as exc:
            config = None
            errors.append(f"improvement-config:{type(exc).__name__}:{str(exc)[:240]}")
            try_append_operational_event(
                workspace,
                "IMPROVEMENT_INTELLIGENCE_CONFIGURATION_INVALID",
                level="WARNING",
                audit_id=audit_id,
                error_type=type(exc).__name__,
                error_message=str(exc)[:512],
                scoring_impact="NONE",
            )

        if config is not None and config.enabled:
            try:
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
                    )

                result = execute_improvement_intelligence(
                    audit_id=audit_id,
                    workspace=workspace,
                    config=config,
                    progress=progress,
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
                )
            except Exception as exc:
                errors.append(f"improvement-runtime:{type(exc).__name__}:{str(exc)[:240]}")
                try_append_operational_event(
                    workspace,
                    "IMPROVEMENT_INTELLIGENCE_FAILURE",
                    level="WARNING",
                    audit_id=audit_id,
                    error_type=type(exc).__name__,
                    error_message=str(exc)[:512],
                    scoring_impact="NONE",
                )

        base = original(
            audit_id=audit_id,
            workspace=workspace,
            context_interpretations=context_interpretations,
            routing_snapshot=routing_snapshot,
        )
        errors = [*base.renderer_errors, *errors]
        try:
            write_improvement_report(audit_id=audit_id, workspace=workspace)
            report_dir = Path(workspace.root) / "report"
            report_navigation.normalize_report_navigation(report_dir)
            write_report_manifest(report_dir)
        except Exception as exc:
            errors.append(f"improvement-report:{type(exc).__name__}:{str(exc)[:240]}")
            try_append_operational_event(
                workspace,
                "IMPROVEMENT_INTELLIGENCE_REPORT_FAILURE",
                level="WARNING",
                audit_id=audit_id,
                error_type=type(exc).__name__,
                error_message=str(exc)[:512],
            )

        inspected = report_completion.inspect_audit_report_site(audit_id=audit_id, workspace=workspace)
        return report_completion.AuditReportCompletion(
            expected_pages=inspected.expected_pages,
            generated_pages=inspected.generated_pages,
            missing_pages=inspected.missing_pages,
            renderer_errors=tuple(errors),
        )

    report_completion.finalize_audit_report_site = finalize_with_improvement
    report_completion._rasai_improvement_intelligence_completion = True


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    _install_report_contract()
    _install_report_completion()
    _INSTALLED = True
