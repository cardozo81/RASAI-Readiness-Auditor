"""CLI shim for additive providers, M23 Synthetic Apdex and M24 crawling diagnostics."""
from __future__ import annotations

import os
import sys
from typing import Sequence

from rasai import cli as _legacy_cli
from rasai import m20 as _m20
from rasai import report_navigation as _report_navigation
from rasai.external_metrics_integrity import (
    enrich_external_metrics_integrity_report_site,
    reconcile_external_metrics_integrity,
)
from rasai.m23_apdex import M23ExecutionResult, execute_m23_apdex
from rasai.m23_cli import SyntheticApdexConfig, configured_apdex, register_apdex_arguments
from rasai.m23_lighthouse_traceability import extract_lighthouse_execution_profiles
from rasai.m23_reporting import enrich_m23_report_site
from rasai.m24_cli import M24Config, configured_m24, register_m24_arguments
from rasai.m24_crawling_discovery import M24ExecutionResult, execute_m24
from rasai.m24_discovery_extensions import install_discovery_extensions
from rasai.m24_reporting import enrich_m24_report_site
from rasai.operational_log import try_append_operational_event
from rasai.provider_runtime_policy import (
    DEFAULT_WEB_PERFORMANCE_TIMEOUT_SECONDS,
    WEB_PERFORMANCE_TIMEOUT_ENV,
    build_content_remediation_router,
    build_semantic_provider,
)
from rasai.provider_registry import extension_cli_choices
from rasai.report_consistency_v2 import reconcile_report_outputs
from rasai.rasai_readiness_reporting import enrich_rasai_reporting
from rasai.source_quality import (
    enrich_source_quality_report_site,
    load_assessment,
    persist_m21_source_skip,
    persist_m23_source_skip,
)
from rasai.source_quality_report_summary import enrich_source_quality_blocker_summary

_LEGACY_BUILD_PARSER = _legacy_cli.build_parser


def build_parser():
    """Return a fresh legacy parser with additive provider/M23/M24 extensions."""
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
        "when model/effort are not explicitly configured RASAi uses the "
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
    register_m24_arguments(audit_parser)
    return parser


def _parse_extended_args(argv: list[str]):
    if "audit" not in argv:
        return None
    parser = build_parser()
    return parser, parser.parse_args(argv)


def _resolve_m23_config(argv: list[str]) -> SyntheticApdexConfig | None:
    parsed = _parse_extended_args(argv)
    if parsed is None:
        return None
    parser, args = parsed
    try:
        return configured_apdex(args)
    except ValueError as exc:
        parser.error(str(exc))
    return None


def _resolve_m24_config(argv: list[str]) -> M24Config | None:
    parsed = _parse_extended_args(argv)
    if parsed is None:
        return None
    parser, args = parsed
    try:
        return configured_m24(args)
    except ValueError as exc:
        parser.error(str(exc))
    return None


def _restore_canonical_device_navigation_labels() -> None:
    """Prevent report-specific wording from leaking into later in-process reports/tests."""
    restored: list[tuple[str, str]] = []
    for label, filename in _report_navigation.NAV_ITEMS:
        if filename == "mobile.html":
            label = "Relatório Mobile"
        elif filename == "desktop.html":
            label = "Relatório Desktop"
        restored.append((label, filename))
    _report_navigation.NAV_ITEMS = tuple(restored)


def _materialize_rasai_fail_open(*, audit_id, workspace, event_prefix: str) -> None:
    """Best-effort SARI projection even when a later optional domain fails."""
    if audit_id is None or workspace is None:
        return
    try:
        rasai_path = enrich_rasai_reporting(audit_id=audit_id, workspace=workspace)
        try_append_operational_event(
            workspace,
            f"{event_prefix}_RASAI_READINESS_REPORT_GENERATED",
            audit_id=audit_id,
            methodology="SARI-001",
            compatible_scoring_engine="SCORE-GEO-002",
            report_path=str(rasai_path.relative_to(workspace.root)),
        )
    except Exception as exc:
        try_append_operational_event(
            workspace,
            f"{event_prefix}_RASAI_READINESS_REPORT_FAILURE",
            level="WARNING",
            audit_id=audit_id,
            error_type=type(exc).__name__,
            error_message=str(exc)[:512],
        )
    finally:
        _restore_canonical_device_navigation_labels()


def main(argv: Sequence[str] | None = None) -> int:
    """Run legacy CLI with additive provider, M23 and fail-open M24 enrichment."""
    effective_argv = list(argv) if argv is not None else list(sys.argv[1:])
    install_discovery_extensions()
    os.environ.setdefault(
        WEB_PERFORMANCE_TIMEOUT_ENV,
        f"{DEFAULT_WEB_PERFORMANCE_TIMEOUT_SECONDS:g}",
    )
    m23_config = _resolve_m23_config(effective_argv)
    m24_config = _resolve_m24_config(effective_argv)

    original_build_parser = _legacy_cli.build_parser
    original_provider_builder = _legacy_cli.build_semantic_provider
    original_m20_router = _m20.build_content_remediation_router
    original_execute_m21 = _legacy_cli.execute_m21
    original_enrich_m21 = _legacy_cli.enrich_m21_report_site

    configured_provider_for_m24 = None
    m23_result: M23ExecutionResult | None = None
    m23_report_path = None
    m23_error: str | None = None
    m23_executed_for: set[str] = set()
    m24_result: M24ExecutionResult | None = None
    m24_report_path = None
    m24_error: str | None = None
    m24_executed_for: set[str] = set()
    source_quality_skip: tuple[str, ...] = ()

    def capture_build_semantic_provider(*args, **kwargs):
        nonlocal configured_provider_for_m24
        configured_provider_for_m24 = build_semantic_provider(*args, **kwargs)
        return configured_provider_for_m24

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

    def run_m24_once(*, audit_id, workspace) -> None:
        nonlocal m24_result, m24_error
        if m24_config is None or audit_id in m24_executed_for:
            return
        m24_executed_for.add(audit_id)
        assessment = load_assessment(workspace)
        allow_network = not (
            assessment is not None and assessment.all_pages_hard_blocked
        )
        try:
            m24_result = execute_m24(
                audit_id=audit_id,
                workspace=workspace,
                technical_ai=m24_config.technical_ai,
                semantic_provider=configured_provider_for_m24,
                allow_network=allow_network,
            )
            try_append_operational_event(
                workspace,
                "M24_CRAWLING_DISCOVERY_COMPLETED",
                audit_id=audit_id,
                status=m24_result.status,
                diagnostics=m24_result.diagnostics_count,
                llms_state=m24_result.llms_state,
                ai_state=m24_result.ai_state,
                scoring_impact=m24_result.scoring_impact,
                network_allowed=allow_network,
            )
        except Exception as exc:
            m24_error = f"{type(exc).__name__}: {str(exc)[:512]}"
            try_append_operational_event(
                workspace,
                "M24_CRAWLING_DISCOVERY_FAILURE",
                level="WARNING",
                audit_id=audit_id,
                error_type=type(exc).__name__,
                error_message=str(exc)[:512],
                scoring_impact="NONE",
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
                    run_m24_once(audit_id=audit_id, workspace=workspace)
                    _materialize_rasai_fail_open(
                        audit_id=audit_id,
                        workspace=workspace,
                        event_prefix="M21_FAILURE",
                    )
                raise

        if audit_id is not None and workspace is not None:
            run_m23_once(audit_id=audit_id, workspace=workspace)
            run_m24_once(audit_id=audit_id, workspace=workspace)
        return result

    def enrich_m21_and_m23(*args, **kwargs):
        nonlocal m23_report_path, m23_error, m24_report_path, m24_error
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
                # Run before the final SARI/M24 projection so every already-created
                # domain page receives the same deterministic origin/redirect/TLS context.
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
                # Preserve PR #70 ownership: SARI is finalized before M24 adds a
                # separate non-scoring technical page and then normalizes navigation.
                rasai_path = enrich_rasai_reporting(
                    audit_id=audit_id,
                    workspace=workspace,
                )
                try_append_operational_event(
                    workspace,
                    "RASAI_READINESS_REPORT_GENERATED",
                    audit_id=audit_id,
                    methodology="SARI-001",
                    compatible_scoring_engine="SCORE-GEO-002",
                    report_path=str(rasai_path.relative_to(workspace.root)),
                )
            except Exception as exc:
                try_append_operational_event(
                    workspace,
                    "RASAI_READINESS_REPORT_FAILURE",
                    level="WARNING",
                    audit_id=audit_id,
                    error_type=type(exc).__name__,
                    error_message=str(exc)[:512],
                )
            finally:
                _restore_canonical_device_navigation_labels()

            if m24_result is not None:
                try:
                    m24_report_path = enrich_m24_report_site(
                        audit_id=audit_id,
                        workspace=workspace,
                    )
                    try_append_operational_event(
                        workspace,
                        "M24_REPORT_GENERATED",
                        audit_id=audit_id,
                        report_path=str(m24_report_path.relative_to(workspace.root)),
                        scoring_impact="NONE",
                    )
                    # PR #70 owns RASAi/device labels. Re-run the projection only
                    # to normalize every final page after M24 has added its nav item;
                    # persisted measurements remain untouched.
                    enrich_rasai_reporting(
                        audit_id=audit_id,
                        workspace=workspace,
                    )
                    _restore_canonical_device_navigation_labels()
                except Exception as exc:
                    m24_error = f"{type(exc).__name__}: {str(exc)[:512]}"
                    try_append_operational_event(
                        workspace,
                        "M24_REPORT_FAILURE",
                        level="WARNING",
                        audit_id=audit_id,
                        error_type=type(exc).__name__,
                        error_message=str(exc)[:512],
                        scoring_impact="NONE",
                    )
        return result

    try:
        _legacy_cli.build_parser = build_parser
        _legacy_cli.build_semantic_provider = capture_build_semantic_provider
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
                "a auditoria RASAi principal foi preservada"
            )

    if m24_config is not None:
        if m24_result is not None:
            print(
                "Rastreamento e descoberta M24: "
                f"{m24_result.status} (diagnósticos {m24_result.diagnostics_count}; "
                f"llms.txt {m24_result.llms_state}; IA técnica {m24_result.ai_state}; "
                "impacto no score NENHUM)"
            )
            if m24_report_path is not None:
                print(f"Relatório de rastreamento e descoberta: {m24_report_path}")
        elif m24_error:
            print(
                "Rastreamento e descoberta M24: INCOMPLETO por erro operacional; "
                "SCORE-GEO-002/SARI-001 foram preservados"
            )
    return code
