"""Runtime/report integration for Improvement Intelligence.

The feature is additive and fail-open. It materializes one canonical advisory report,
keeps SARI/SCORE-GEO untouched and reuses only persisted audit/Search evidence.
"""
from __future__ import annotations

from decimal import Decimal
from pathlib import Path
import sqlite3
from typing import Any

from rasai.improvement_intelligence import (
    CONTRACT_VERSION,
    REPORT_FILE,
    ImprovementConfig,
    execute_improvement_intelligence,
)
from rasai.operational_log import try_append_operational_event

_INSTALLED = False
_SURFACE_ID = "improvement-intelligence"


def _install_report_contract() -> None:
    from rasai import context_scope_runtime, report_contract, report_manifest, report_navigation, report_registry

    # Compatibility only. The current public contract declares the surface statically
    # in report_contract; this branch supports older composed imports without creating a
    # second registry when the static declaration is already present.
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
            optional_dependencies=("exatamente uma URL de entrada", "provider de IA explícito", "Web Performance/Lighthouse", "Search Intelligence"),
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


def _install_consolidated_alignment() -> None:
    """Bring the historical/consolidated surface to the current public vocabulary."""
    try:
        from rasai.consolidation import reporting
    except Exception:
        return
    reporting.REPORT_FORMAT_VERSION = "CONS-4"
    reporting._DIMENSIONS.update({
        "DISCOVERY_ACCESS": "Discovery & Crawler Access",
        "INDEXABILITY": "Indexability & Canonicalization",
        "CONTENT_EXTRACTABILITY": "Rendering & Extractability",
        "SEMANTIC_STRUCTURE": "Semantic Structure",
        "ENTITY_CLARITY": "Entity Clarity",
        "STRUCTURED_DATA": "Structured Data",
        "ANSWERABILITY": "Answerability",
        "CITATION_READINESS": "Citation Readiness",
        "EVIDENCE_TRUST": "Evidence & Trust",
        "INTENT_COVERAGE": "Intent Coverage",
        "CONTENT_VALUE": "Content Value",
        # Backward-readable only. New audits use DISCOVERY_ACCESS.
        "TECHNICAL_ACCESSIBILITY": "Discovery & Crawler Access (histórico legado)",
    })
    original = reporting._render_executive
    if getattr(original, "_rasai_improvement_boundary", False):
        return

    def render_executive(data):
        html = original(data)
        notice = (
            "<section class='notice' data-current-rasai-boundary='true'><strong>Fronteira do consolidado atual:</strong> "
            "SARI/SCORE-GEO, Coverage, Confidence e gates mantêm sua série metodológica própria. Lighthouse/Core Web Vitals, "
            "Apdex, SERP/Search Intelligence, postura de segurança e Improvement Intelligence são sinais complementares e não são "
            "promediados artificialmente dentro do SARI histórico. Recomendações de IA são advisory e o ganho só é tratado como "
            "observado depois de nova medição/before-after.</section>"
        )
        return notice + html

    render_executive._rasai_improvement_boundary = True
    render_executive._rasai_original = original
    reporting._render_executive = render_executive


def _install_ai_cost_attribution() -> None:
    """Keep deep-analysis cost separate from semantic and technical remediation cost."""
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


def _install_report_completion() -> None:
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

        # The canonical report finalizer now owns the Improvement Intelligence page,
        # navigation normalization and manifest write. This wrapper executes only the
        # optional analysis before that finalizer, avoiding duplicate HTML/manifest I/O.
        base = original(
            audit_id=audit_id,
            workspace=workspace,
            context_interpretations=context_interpretations,
            routing_snapshot=routing_snapshot,
        )
        return report_completion.AuditReportCompletion(
            expected_pages=base.expected_pages,
            generated_pages=base.generated_pages,
            missing_pages=base.missing_pages,
            renderer_errors=tuple((*base.renderer_errors, *errors)),
        )

    report_completion.finalize_audit_report_site = finalize_with_improvement
    report_completion._rasai_improvement_intelligence_completion = True


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    _install_report_contract()
    _install_consolidated_alignment()
    _install_ai_cost_attribution()
    _install_report_completion()
    _INSTALLED = True
