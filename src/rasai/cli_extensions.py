"""CLI composition for providers, Synthetic Apdex and crawling diagnostics."""
from __future__ import annotations

import os
import sys
from typing import Sequence

from rasai import cli as _audit_cli
from rasai import m20 as _m20
from rasai.external_metrics_integrity import reconcile_external_metrics_integrity
from rasai.m23_apdex import M23ExecutionResult, execute_m23_apdex
from rasai.m23_cli import SyntheticApdexConfig, configured_apdex, register_apdex_arguments
from rasai.m23_lighthouse_traceability import extract_lighthouse_execution_profiles
from rasai.m24_cli import M24Config, configured_m24, register_m24_arguments
from rasai.m24_crawling_discovery import M24ExecutionResult, execute_m24, load_m24_result
from rasai.m24_discovery_extensions import install_discovery_extensions
from rasai.operational_log import try_append_operational_event
from rasai.provider_runtime_policy import (
    DEFAULT_WEB_PERFORMANCE_TIMEOUT_SECONDS,
    WEB_PERFORMANCE_TIMEOUT_ENV,
    build_content_remediation_router,
    build_semantic_provider,
)
from rasai.provider_registry import extension_cli_choices
from rasai.source_quality import load_assessment, persist_m21_source_skip, persist_m23_source_skip

_BASE_BUILD_PARSER = _audit_cli.build_parser


def build_parser():
    """Return the audit parser with the current provider and diagnostic extensions."""
    parser = _BASE_BUILD_PARSER()
    subparsers = next(
        action
        for action in parser._actions
        if getattr(action, "choices", None) and "audit" in action.choices
    )
    audit_parser = subparsers.choices["audit"]
    ai_action = next(action for action in audit_parser._actions if action.dest == "ai_provider")
    base_choices = tuple(ai_action.choices or ())
    ai_action.choices = base_choices + tuple(
        item for item in extension_cli_choices() if item not in base_choices
    )
    ai_action.help = (
        "semantic analysis provider; AUTO uses the configured OpenAI/DeepSeek/MiMo chain, "
        "other registered providers are explicit-only; when model/effort are not explicitly "
        "configured RASAi uses the simplest supported model and lowest supported reasoning effort"
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


def main(argv: Sequence[str] | None = None) -> int:
    """Run the audit CLI with current provider and fail-open enrichment composition."""
    effective_argv = list(argv) if argv is not None else list(sys.argv[1:])
    install_discovery_extensions()
    os.environ.setdefault(
        WEB_PERFORMANCE_TIMEOUT_ENV,
        f"{DEFAULT_WEB_PERFORMANCE_TIMEOUT_SECONDS:g}",
    )
    m23_config = _resolve_m23_config(effective_argv)
    m24_config = _resolve_m24_config(effective_argv)

    parsed_resume = _parse_extended_args(effective_argv)
    resume_args = parsed_resume[1] if parsed_resume is not None else None
    from rasai.m25_runtime import peek_pending_config

    experience_config = peek_pending_config()
    resume_options: dict[str, object] = {
        "synthetic_apdex": (
            {
                "enabled": bool(m23_config.enabled),
                "threshold_seconds": m23_config.threshold_seconds,
                "target_valid_samples": int(m23_config.target_valid_samples),
                "max_attempts_per_context": int(m23_config.max_attempts_per_context),
                "max_pages": int(m23_config.max_pages),
                "timeout_seconds": float(m23_config.timeout_seconds),
                "delay_seconds": float(m23_config.delay_seconds),
                "concurrency": int(m23_config.concurrency),
                "mobile_profile": m23_config.mobile_profile.as_dict(),
                "desktop_profile": m23_config.desktop_profile.as_dict(),
            }
            if m23_config is not None
            else {"enabled": False}
        ),
        "experience_apdex": experience_config.as_dict(),
    }
    if resume_args is not None:
        queries = [
            " ".join(str(value).split())
            for value in (getattr(resume_args, "search_queries", ()) or ())
            if str(value).strip()
        ]
        if queries:
            from rasai.search_intelligence.config import SerpRuntimeConfig

            search_runtime = SerpRuntimeConfig.from_environment(validate=False)
            resume_options["search_intelligence"] = {
                "enabled": True,
                "queries": list(dict.fromkeys(queries)),
                "depth": int(getattr(resume_args, "search_depth", 20) or 20),
                "region": str(getattr(resume_args, "search_region", "") or ""),
                "device": str(getattr(resume_args, "search_device", "mobile") or "mobile"),
                "competitive": bool(getattr(resume_args, "search_competitive", True)),
                "compare_content": bool(getattr(resume_args, "search_compare_content", False)),
                "max_content_pages": int(getattr(resume_args, "search_max_content_pages", 3) or 3),
                "content_timeout_seconds": float(getattr(resume_args, "search_content_timeout_seconds", 10.0) or 10.0),
                "content_max_bytes": int(getattr(resume_args, "search_content_max_bytes", 2_000_000) or 2_000_000),
                "content_max_redirects": int(getattr(resume_args, "search_content_max_redirects", 5) or 5),
                "ai_competitive": bool(getattr(resume_args, "search_ai_competitive", False)),
                "ymyl_mode": str(getattr(resume_args, "search_ymyl_mode", "AUTO") or "AUTO").upper(),
                "mode": str(search_runtime.mode),
                "provider": str(search_runtime.provider),
                "fixture_path": str(search_runtime.fixture_path) if search_runtime.fixture_path else "",
                "max_queries": int(search_runtime.max_queries),
                "max_requests": int(search_runtime.max_requests),
                "max_depth": int(search_runtime.max_depth),
                "max_competitors": int(search_runtime.max_competitors),
                "timeout_seconds": float(search_runtime.timeout_seconds),
                "retries": int(search_runtime.retries),
                "min_interval_seconds": float(search_runtime.min_interval_seconds),
            }

    original_build_parser = _audit_cli.build_parser
    original_provider_builder = _audit_cli.build_semantic_provider
    original_m20_router = _m20.build_content_remediation_router
    original_execute_m21 = _audit_cli.execute_m21

    configured_provider_for_m24 = None
    m23_result: M23ExecutionResult | None = None
    m23_error: str | None = None
    m23_executed_for: set[str] = set()
    m24_result: M24ExecutionResult | None = None
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
            m24_result = load_m24_result(audit_id=audit_id, workspace=workspace)
            if m24_result is None:
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
                raise

        if audit_id is not None and workspace is not None:
            run_m23_once(audit_id=audit_id, workspace=workspace)
            run_m24_once(audit_id=audit_id, workspace=workspace)
        return result

    try:
        _audit_cli.build_parser = build_parser
        _audit_cli.build_semantic_provider = capture_build_semantic_provider
        _m20.build_content_remediation_router = build_content_remediation_router
        _audit_cli.execute_m21 = execute_m21_and_m23
        from rasai.audit_resume_runtime import resume_plan_options

        with resume_plan_options(resume_options):
            code = _audit_cli.main(effective_argv)
    finally:
        _audit_cli.build_parser = original_build_parser
        _audit_cli.build_semantic_provider = original_provider_builder
        _m20.build_content_remediation_router = original_m20_router
        _audit_cli.execute_m21 = original_execute_m21

    if source_quality_skip:
        print(
            "Qualidade da origem: BLOQUEIO TÉCNICO "
            f"({', '.join(source_quality_skip)}). "
            "Etapas externas/repetitivas dependentes da URL foram interrompidas; "
            "consulte o estado persistido da auditoria e o arquivo logs/audit.log para o diagnóstico completo."
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
        elif m23_error:
            print(
                "Synthetic Apdex: INCOMPLETO por erro operacional; "
                "a auditoria RASAi principal foi preservada"
            )

    if m24_config is not None:
        if m24_result is not None:
            print(
                "Rastreamento e descoberta: "
                f"{m24_result.status} (diagnósticos {m24_result.diagnostics_count}; "
                f"llms.txt {m24_result.llms_state}; IA técnica {m24_result.ai_state}; "
                f"impacto no score {m24_result.scoring_impact})"
            )
        elif m24_error:
            print(
                "Rastreamento e descoberta: INCOMPLETO por erro operacional; "
                "Método de Pontuação de Prontidão e Índice de Prontidão Search & IA foram preservados (IDs técnicos SCORE-GEO-004/SARI-001)"
            )
    return code