"""CLI shim for additive providers and Synthetic Navigation Apdex."""

from __future__ import annotations

import os
import sys
from typing import Sequence

from searchgeo import cli as _legacy_cli
from searchgeo import m20 as _m20
from searchgeo.external_metrics_integrity import (
    enrich_external_metrics_integrity_report_site,
    reconcile_external_metrics_integrity,
)
from searchgeo.m23_apdex import M23ExecutionResult, execute_m23_apdex
from searchgeo.m23_cli import SyntheticApdexConfig, configured_apdex, register_apdex_arguments
from searchgeo.m23_lighthouse_traceability import extract_lighthouse_execution_profiles
from searchgeo.m23_reporting import enrich_m23_report_site
from searchgeo.operational_log import try_append_operational_event
from searchgeo.provider_runtime_policy import (
    DEFAULT_WEB_PERFORMANCE_TIMEOUT_SECONDS,
    WEB_PERFORMANCE_TIMEOUT_ENV,
    build_content_remediation_router,
    build_semantic_provider,
)
from searchgeo.provider_registry import extension_cli_choices
from searchgeo.report_consistency_v2 import reconcile_report_outputs
from searchgeo.searchgeo_readiness_reporting import enrich_searchgeo_reporting
from searchgeo.source_quality import (
    enrich_source_quality_report_site,
    load_assessment,
    persist_m21_source_skip,
    persist_m23_source_skip,
)
from searchgeo.source_quality_report_summary import enrich_source_quality_blocker_summary

_LEGACY_BUILD_PARSER = _legacy_cli.build_parser


def build_parser():
    """Return a fresh legacy parser with provider and Synthetic Apdex extensions."""
    parser = _LEGACY_BUILD_PARSER()
    subparsers = next(
        action
        for action in parser._actions
        if getattr(action, "choices", None) and "audit" in action.choices
    )
    audit_parser = subparsers.choices["audit"]
    ai_action = next(action for action in audit_parser._actions if action.dest == "ai_provider")
    legacy_choices = tuple(ai_action.choices or ())
    ai_action.choices = legacy_choices + tuple(
        item for item in extension_cli_choices() if item not in legacy_choices
    )
    ai_action.help = (
        "semantic analysis provider; AUTO remains the homologated "
        "OpenAI/DeepSeek/MiMo chain, extension providers are explicit-only; "
        "when model/effort are not explicitly configured SearchGEO uses the "
        "simplest supported model and lowest supported reasoning effort"
    )
    web_timeout_action = next(
        action for action in audit_parser._actions
        if action.dest == "web_performance_timeout_seconds"
    )
    web_timeout_action.help = (
        "client wait limit for each complete PageSpeed/CrUX external response; "
        f"public default {DEFAULT_WEB_PERFORMANCE_TIMEOUT_SECONDS:g}s or "
        f"{WEB_PERFORMANCE_TIMEOUT_ENV}. PageSpeed runs Lighthouse remotely; "
        "this is not a separate Lighthouse page-load parameter"
    )
    register_apdex_arguments(audit_parser)
    return parser


def _resolve_m23_config(argv: list[str]) -> SyntheticApdexConfig | None:
    if "audit" not in argv:
        return None
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return configured_apdex(args)
    except ValueError as exc:
        parser.error(str(exc))
    return None


def main(argv: Sequence[str] | None = None) -> int:
    """Run legacy CLI with additive providers and fail-open Synthetic Apdex enrichment."""
    effective_argv = list(argv) if argv is not None else list(sys.argv[1:])
    os.environ.setdefault(
        WEB_PERFORMANCE_TIMEOUT_ENV,
        f"{DEFAULT_WEB_PERFORMANCE_TIMEOUT_SECONDS:g}",
    )
    m23_config = _resolve_m23_config(effective_argv)

    original_build_parser = _legacy_cli.build_parser
    original_provider_builder = _legacy_cli.build_semantic_provider
    original_m20_router = _m20.build_content_remediation_router
    original_execute_m21 = _legacy_cli.execute_m21
    original_enrich_m21 = _legacy_cli.enrich_m21_report_site

    m23_result: M23ExecutionResult | None = None
    m23_report_path = None
    m23_error: str | None = None
    m23_executed_for: set[str] = set()
    source_quality_skip: tuple[str, ...] = ()

    def run_m23_once(*, audit_id, workspace) -> None:
        nonlocal m23_result, m23_error, source_quality_skip
        if m23_config is None or audit_id in m23_executed_for:
            return
        m23_executed_for.add(audit_id)

        assessment = load_assessment(workspace)
        if (
            m23_config.enabled
            and assessment is not None
            and assessment.all_pages_hard_blocked
        ):
            source_quality_skip = assessment.hard_blocker_kinds
            m23_result = persist_m23_source_skip(
                audit_id=audit_id,
                workspace=workspace,
                config=m23_config,
                assessment=assessment,
            )
            try_append_operational_event(
                workspace,
                "SOURCE_QUALITY_DOWNSTREAM_SKIPPED",
                level="WARNING",
                audit_id=audit_id,
                component="SYNTHETIC_APDEX",
                blockers=assessment.hard_blocker_kinds,
                attempted_samples=0,
            )
            return

        if m23_config.enabled:
            try:
                trace = extract_lighthouse_execution_profiles(
                    audit_id=audit_id,
                    workspace=workspace,
                )
                try_append_operational_event(
                    workspace,
                    "M23_LIGHTHOUSE_TRACEABILITY_COMPLETED",
                    audit_id=audit_id,
                    observations_considered=trace.observations_considered,
                    profiles_extracted=trace.profiles_extracted,
                    missing_artifacts=trace.missing_artifacts,
                    invalid_artifacts=trace.invalid_artifacts,
                )
            except Exception as exc:
                try_append_operational_event(
                    workspace,
                    "M23_LIGHTHOUSE_TRACEABILITY_FAILURE",
                    level="WARNING",
                    audit_id=audit_id,
                    error_type=type(exc).__name__,
                    error_message=str(exc)[:512],
                )
        try:
            m23_result = execute_m23_apdex(
                audit_id=audit_id,
                workspace=workspace,
                config=m23_config,
            )
        except Exception as exc:
            m23_error = f"{type(exc).__name__}: {str(exc)[:512]}"
            try_append_operational_event(
                workspace,
                "M23_RUNTIME_FAILURE",
                level="ERROR",
                audit_id=audit_id,
                error_type=type(exc).__name__,
                error_message=str(exc)[:512],
            )

    def execute_m21_and_m23(*args, **kwargs):
        nonlocal source_quality_skip
        audit_id = kwargs.get("audit_id")
        workspace = kwargs.get("workspace")
        config = kwargs.get("config")

        assessment = (
            load_assessment(workspace)
            if audit_id is not None and workspace is not None
            else None
        )
        if (
            assessment is not None
            and assessment.all_pages_hard_blocked
            and config is not None
            and bool(getattr(config, "enabled", False))
        ):
            source_quality_skip = assessment.hard_blocker_kinds
            result = persist_m21_source_skip(
                audit_id=audit_id,
                workspace=workspace,
                config=config,
                assessment=assessment,
            )
            try_append_operational_event(
                workspace,
                "SOURCE_QUALITY_DOWNSTREAM_SKIPPED",
                level="WARNING",
                audit_id=audit_id,
                component="WEB_PERFORMANCE",
                blockers=assessment.hard_blocker_kinds,
                external_attempts=0,
            )
        else:
            try:
                result = original_execute_m21(*args, **kwargs)
                if audit_id is not None and workspace is not None:
                    result = reconcile_external_metrics_integrity(
                        audit_id=audit_id,
                        workspace=workspace,
                        result=result,
                    )
            except Exception:
                if audit_id is not None and workspace is not None:
                    run_m23_once(audit_id=audit_id, workspace=workspace)
                raise

        if audit_id is not None and workspace is not None:
            run_m23_once(audit_id=audit_id, workspace=workspace)
        return result

    def enrich_m21_and_m23(*args, **kwargs):
        nonlocal m23_report_path, m23_error
        audit_id = kwargs.get("audit_id")
        workspace = kwargs.get("workspace")
        result = original_enrich_m21(*args, **kwargs)
        if (
            m23_config is not None
            and m23_config.enabled
            and m23_result is not None
            and audit_id is not None
            and workspace is not None
        ):
            try:
                m23_report_path = enrich_m23_report_site(
                    audit_id=audit_id,
                    workspace=workspace,
                )
            except Exception as exc:
                m23_error = f"{type(exc).__name__}: {str(exc)[:512]}"
                try_append_operational_event(
                    workspace,
                    "M23_REPORT_FAILURE",
                    level="ERROR",
                    audit_id=audit_id,
                    error_type=type(exc).__name__,
                    error_message=str(exc)[:512],
                )
        if audit_id is not None and workspace is not None:
            try:
                reconcile_report_outputs(audit_id=audit_id, workspace=workspace)
            except Exception as exc:
                try_append_operational_event(
                    workspace,
                    "REPORT_CONSISTENCY_FAILURE",
                    level="WARNING",
                    audit_id=audit_id,
                    error_type=type(exc).__name__,
                    error_message=str(exc)[:512],
                )
            try:
                enrich_external_metrics_integrity_report_site(
                    audit_id=audit_id,
                    workspace=workspace,
                )
            except Exception as exc:
                try_append_operational_event(
                    workspace,
                    "EXTERNAL_METRICS_INTEGRITY_REPORT_FAILURE",
                    level="WARNING",
                    audit_id=audit_id,
                    error_type=type(exc).__name__,
                    error_message=str(exc)[:512],
                )
            try:
                # Run last so every generated HTML page receives the same deterministic
                # origin/redirect/TLS context, including M21/M23 pages.
                enrich_source_quality_report_site(
                    audit_id=audit_id,
                    workspace=workspace,
                )
                enrich_source_quality_blocker_summary(
                    audit_id=audit_id,
                    workspace=workspace,
                )
            except Exception as exc:
                try_append_operational_event(
                    workspace,
                    "SOURCE_QUALITY_REPORT_FAILURE",
                    level="WARNING",
                    audit_id=audit_id,
                    error_type=type(exc).__name__,
                    error_message=str(exc)[:512],
                )
            try:
                # The executive dashboard must be the final report projection so it can
                # remove legacy cross-domain summaries and reflect the final persisted
                # state of SearchGEO, Lighthouse/CrUX, Accessibility and Apdex.
                searchgeo_path = enrich_searchgeo_reporting(
                    audit_id=audit_id,
                    workspace=workspace,
                )
                try_append_operational_event(
                    workspace,
                    "SEARCHGEO_READINESS_REPORT_GENERATED",
                    audit_id=audit_id,
                    methodology="SGRI-001",
                    compatible_scoring_engine="SCORE-GEO-002",
                    report_path=str(searchgeo_path.relative_to(workspace.root)),
                )
            except Exception as exc:
                try_append_operational_event(
                    workspace,
                    "SEARCHGEO_READINESS_REPORT_FAILURE",
                    level="WARNING",
                    audit_id=audit_id,
                    error_type=type(exc).__name__,
                    error_message=str(exc)[:512],
                )
        return result

    try:
        _legacy_cli.build_parser = build_parser
        _legacy_cli.build_semantic_provider = build_semantic_provider
        _m20.build_content_remediation_router = build_content_remediation_router
        _legacy_cli.execute_m21 = execute_m21_and_m23
        _legacy_cli.enrich_m21_report_site = enrich_m21_and_m23
        code = _legacy_cli.main(effective_argv)
    finally:
        _legacy_cli.build_parser = original_build_parser
        _legacy_cli.build_semantic_provider = original_provider_builder
        _m20.build_content_remediation_router = original_m20_router
        _legacy_cli.execute_m21 = original_execute_m21
        _legacy_cli.enrich_m21_report_site = original_enrich_m21

    if source_quality_skip:
        print(
            "Qualidade da origem: BLOQUEIO TÉCNICO "
            f"({', '.join(source_quality_skip)}). "
            "Etapas externas/repetitivas dependentes da URL foram interrompidas; "
            "consulte o bloco 'Auditoria limitada por bloqueio técnico da origem' no relatório "
            "e o arquivo logs/audit.log para o diagnóstico completo."
        )

    if m23_config is not None:
        if not m23_config.enabled:
            print("Synthetic Apdex: DESABILITADO")
        elif m23_result is not None and m23_result.status == "SKIPPED_SOURCE_BLOCKER":
            print(
                "Synthetic Apdex: NÃO EXECUTADO por bloqueio técnico da origem "
                "(0 navegações sintéticas adicionais)"
            )
        elif m23_result is not None:
            print(
                "Synthetic Apdex: HABILITADO "
                f"({m23_result.status}; páginas {m23_result.pages_considered}; "
                f"contextos {m23_result.contexts_considered}; "
                f"amostras válidas {m23_result.valid_samples}/{m23_result.attempted_samples})"
            )
            if m23_result.small_group_summaries:
                print(
                    "Synthetic Apdex aviso: há grupo(s) pequeno(s) com menos de 100 "
                    "amostras válidas; resultado é diagnóstico e recebe marcador *."
                )
            if m23_report_path is not None:
                print(f"Relatório Apdex: {m23_report_path}")
        elif m23_error:
            print(
                "Synthetic Apdex: INCOMPLETO por erro operacional; "
                "a auditoria SearchGEO principal foi preservada"
            )
    return code
