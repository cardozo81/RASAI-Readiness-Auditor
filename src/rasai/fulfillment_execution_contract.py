"""Canonical execution/fulfillment reconciliation for optional RASAi work.

This module closes the gap between physical execution, provider attempts and the
logical AUD result. It is deliberately additive: pricing remains owned by the
canonical AI pricing engine, provider attempts remain append-only, and the existing
fulfillment tables remain the single source of truth for completion/reprocessing.
"""
from __future__ import annotations

from contextvars import ContextVar
from dataclasses import replace
import os
from pathlib import Path
import sqlite3
from typing import Any, Mapping

from rasai.audit_fulfillment import (
    FAILED_RETRYABLE,
    LIVE_RECOLLECTION,
    REPLAY_SAFE,
    REQUESTED_NOT_EXECUTED,
    SUCCESS,
    list_work_items,
    project_report_validity,
    read_summary,
    register_work_item,
    set_work_item_status,
)
from rasai.secret_safety import redact_text

NOT_CONFIGURED = "NOT_CONFIGURED"
AI_CONTRACT = "AI_CONTRACT"
M24_CONTRACT_ERROR_CODE = "TECHNICAL_AI_CONTRACT_VALIDATION_ERROR"

_INSTALLED = False
_CONSOLE_INSTALLED = False
_M24_VALIDATION_ERROR: ContextVar[tuple[str, str] | None] = ContextVar(
    "rasai_m24_validation_error",
    default=None,
)
_M24_PENDING_DETAIL: ContextVar[dict[str, str] | None] = ContextVar(
    "rasai_m24_pending_detail",
    default=None,
)
_M24_PREVIOUS_FAILURE: ContextVar[dict[str, str] | None] = ContextVar(
    "rasai_m24_previous_failure",
    default=None,
)


def _truthy(value: Any) -> bool:
    return str(value or "").strip().casefold() in {"1", "true", "yes", "on", "sim", "s"}


def _safe_detail(value: Any, *, limit: int = 1000) -> str:
    return redact_text(str(value or "").strip())[:limit]


def _table_exists(connection: sqlite3.Connection, name: str) -> bool:
    return connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (name,),
    ).fetchone() is not None


def _columns(connection: sqlite3.Connection, table: str) -> set[str]:
    if not _table_exists(connection, table):
        return set()
    return {str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})").fetchall()}


def _ensure_attempt_detail_column(workspace: Any) -> None:
    connection = sqlite3.connect(workspace.database)
    try:
        columns = _columns(connection, "ai_provider_attempts")
        if columns and "error_detail" not in columns:
            with connection:
                connection.execute("ALTER TABLE ai_provider_attempts ADD COLUMN error_detail TEXT")
    finally:
        connection.close()


def _install_m24_diagnostic_preservation() -> None:
    """Keep local evidence-contract rejection distinct from provider unavailability."""
    from rasai import m24_ai
    from rasai.m18_ai import AttemptStatus, ProviderDiagnostic, ProviderErrorClass, ProviderState

    if getattr(m24_ai, "_rasai_contract_diagnostic_preservation", False):
        return

    original_validate = m24_ai._validate
    original_call = m24_ai._call
    original_persist = m24_ai._persist_attempt
    original_remediate = m24_ai.maybe_remediate_m24

    def validate_with_detail(*args: Any, **kwargs: Any):
        try:
            return original_validate(*args, **kwargs)
        except Exception as exc:
            _M24_VALIDATION_ERROR.set((type(exc).__name__, _safe_detail(exc)))
            raise

    def call_with_contract_diagnostic(candidate: Any, *args: Any, **kwargs: Any):
        token = _M24_VALIDATION_ERROR.set(None)
        try:
            result, attempt = original_call(candidate, *args, **kwargs)
            validation_error = _M24_VALIDATION_ERROR.get()
        finally:
            _M24_VALIDATION_ERROR.reset(token)

        if attempt.status is not AttemptStatus.CONTRACT_ERROR:
            return result, attempt

        detail_type = validation_error[0] if validation_error else (
            attempt.diagnostic.error_type if attempt.diagnostic is not None else "ContractError"
        )
        detail_message = validation_error[1] if validation_error else ""
        diagnostic = attempt.diagnostic or ProviderDiagnostic(ProviderErrorClass.CONTRACT_ERROR)
        diagnostic = replace(
            diagnostic,
            error_class=ProviderErrorClass.CONTRACT_ERROR,
            error_type=detail_type,
            error_code=diagnostic.error_code or M24_CONTRACT_ERROR_CODE,
        )
        attempt = replace(
            attempt,
            diagnostic=diagnostic,
            retry_eligible=True,
            decision="REPROCESS_ELIGIBLE",
        )
        reason = f"AI_CONTRACT:{diagnostic.error_code}"
        if detail_message:
            reason += f":{detail_message}"
        result = replace(result, state=ProviderState.UNAVAILABLE, reason=reason)
        _M24_PENDING_DETAIL.set(
            {
                "request_payload_hash": str(attempt.request_payload_hash),
                "provider": str(attempt.provider),
                "model": str(attempt.model or ""),
                "error_type": str(detail_type or "ContractError"),
                "error_code": str(diagnostic.error_code or M24_CONTRACT_ERROR_CODE),
                "error_detail": detail_message,
            }
        )
        return result, attempt

    def persist_with_detail(*, workspace: Any, audit_id: str, page_row: Any, attempt: Any) -> None:
        previous = _M24_PREVIOUS_FAILURE.get()
        effective_attempt = attempt
        if previous and str(previous.get("provider") or "") != str(attempt.provider):
            effective_attempt = replace(
                attempt,
                fallback_from_provider=str(previous.get("provider") or "") or None,
                fallback_reason=str(previous.get("reason") or "") or None,
            )
            connection = sqlite3.connect(workspace.database)
            try:
                columns = _columns(connection, "ai_provider_attempts")
                if "decision" in columns:
                    with connection:
                        connection.execute(
                            """UPDATE ai_provider_attempts SET decision='FALLBACK'
                               WHERE attempt_id=(
                                   SELECT attempt_id FROM ai_provider_attempts
                                   WHERE audit_id=? AND provider=? AND request_payload_hash=?
                                   ORDER BY started_at DESC,rowid DESC LIMIT 1
                               )""",
                            (
                                audit_id,
                                str(previous.get("provider") or ""),
                                str(previous.get("request_payload_hash") or ""),
                            ),
                        )
            finally:
                connection.close()

        original_persist(
            workspace=workspace,
            audit_id=audit_id,
            page_row=page_row,
            attempt=effective_attempt,
        )
        _ensure_attempt_detail_column(workspace)

        pending = _M24_PENDING_DETAIL.get()
        if (
            pending
            and str(pending.get("request_payload_hash") or "") == str(effective_attempt.request_payload_hash)
            and str(pending.get("provider") or "") == str(effective_attempt.provider)
        ):
            connection = sqlite3.connect(workspace.database)
            try:
                with connection:
                    connection.execute(
                        """UPDATE ai_provider_attempts SET error_detail=?
                           WHERE attempt_id=(
                               SELECT attempt_id FROM ai_provider_attempts
                               WHERE audit_id=? AND provider=? AND request_payload_hash=?
                                 AND semantic_contract_version LIKE 'M24%'
                               ORDER BY started_at DESC,rowid DESC LIMIT 1
                           )""",
                        (
                            _safe_detail(pending.get("error_detail")),
                            audit_id,
                            str(effective_attempt.provider),
                            str(effective_attempt.request_payload_hash),
                        ),
                    )
            finally:
                connection.close()
            _M24_PENDING_DETAIL.set(None)

        status = str(getattr(effective_attempt.status, "value", effective_attempt.status) or "").upper()
        if status == "SUCCESS":
            _M24_PREVIOUS_FAILURE.set(None)
        else:
            diagnostic = effective_attempt.diagnostic
            _M24_PREVIOUS_FAILURE.set(
                {
                    "provider": str(effective_attempt.provider),
                    "request_payload_hash": str(effective_attempt.request_payload_hash),
                    "reason": str(
                        getattr(diagnostic.error_class, "value", diagnostic.error_class)
                        if diagnostic is not None
                        else status
                    ),
                }
            )

    def remediate_with_attempt_chain(*args: Any, **kwargs: Any):
        token_failure = _M24_PREVIOUS_FAILURE.set(None)
        token_detail = _M24_PENDING_DETAIL.set(None)
        try:
            return original_remediate(*args, **kwargs)
        finally:
            _M24_PREVIOUS_FAILURE.reset(token_failure)
            _M24_PENDING_DETAIL.reset(token_detail)

    validate_with_detail._rasai_contract_diagnostic_preservation = True
    call_with_contract_diagnostic._rasai_contract_diagnostic_preservation = True
    persist_with_detail._rasai_contract_diagnostic_preservation = True
    remediate_with_attempt_chain._rasai_contract_diagnostic_preservation = True
    m24_ai._validate = validate_with_detail
    m24_ai._call = call_with_contract_diagnostic
    m24_ai._persist_attempt = persist_with_detail
    m24_ai.maybe_remediate_m24 = remediate_with_attempt_chain
    m24_ai._rasai_contract_diagnostic_preservation = True


def _latest_m24_attempt(workspace: Any, audit_id: str) -> dict[str, Any] | None:
    connection = sqlite3.connect(workspace.database)
    connection.row_factory = sqlite3.Row
    try:
        if not _table_exists(connection, "ai_provider_attempts"):
            return None
        columns = _columns(connection, "ai_provider_attempts")
        detail = ",error_detail" if "error_detail" in columns else ",NULL AS error_detail"
        row = connection.execute(
            """SELECT provider,model,attempt_index,status,error_class,http_status,error_type,
                      error_code,semantic_contract_version,retry_eligible,decision,
                      fallback_from_provider,fallback_reason,input_tokens,cached_input_tokens,
                      output_tokens,reasoning_tokens,total_tokens,estimated_cost,cost_currency,
                      pricing_version,started_at,finished_at,duration_ms"""
            + detail
            + """ FROM ai_provider_attempts
                   WHERE audit_id=? AND semantic_contract_version LIKE 'M24%'
                   ORDER BY started_at DESC,attempt_index DESC,rowid DESC LIMIT 1""",
            (audit_id,),
        ).fetchone()
        return dict(row) if row is not None else None
    except sqlite3.Error:
        return None
    finally:
        connection.close()


def reconcile_technical_ai_fulfillment(*, workspace: Any, audit_id: str, state: str | None = None) -> None:
    """Project the real technical-AI provider attempt into canonical fulfillment."""
    attempt = _latest_m24_attempt(workspace, audit_id)
    if attempt is None:
        return
    provider = str(attempt.get("provider") or "")
    model = str(attempt.get("model") or "")
    status = str(attempt.get("status") or "").upper()
    error_class = str(attempt.get("error_class") or "").upper()
    detail = _safe_detail(attempt.get("error_detail"))
    register_work_item(
        workspace,
        audit_id=audit_id,
        component="TECHNICAL_AI",
        required=True,
        temporal_mode=REPLAY_SAFE,
        retryable=True,
        configuration={
            "enabled": True,
            "provider": provider,
            "model": model,
            "semantic_contract_version": attempt.get("semantic_contract_version"),
            "latest_provider_attempt": attempt.get("attempt_index"),
            "pricing_version": attempt.get("pricing_version"),
        },
    )
    if status == "SUCCESS" or str(state or "").upper() == "AVAILABLE":
        set_work_item_status(
            workspace,
            audit_id=audit_id,
            component="TECHNICAL_AI",
            status=SUCCESS,
            result_ref=f"technical-ai:{provider or 'provider'}",
            retryable=False,
        )
        return
    if error_class == "CONTRACT_ERROR" or status == "CONTRACT_ERROR":
        message = detail or "provider respondeu; resposta rejeitada pelo contrato evidence-bound do RASAi"
        set_work_item_status(
            workspace,
            audit_id=audit_id,
            component="TECHNICAL_AI",
            status=FAILED_RETRYABLE,
            error_class=AI_CONTRACT,
            error_code=str(attempt.get("error_code") or M24_CONTRACT_ERROR_CODE),
            error_message=message,
            retryable=True,
        )
        return
    set_work_item_status(
        workspace,
        audit_id=audit_id,
        component="TECHNICAL_AI",
        status=FAILED_RETRYABLE,
        error_class="AI_PROVIDER",
        error_code=str(attempt.get("error_code") or attempt.get("error_type") or state or status or "TECHNICAL_AI_UNAVAILABLE"),
        error_message=detail or f"technical AI state={state or status or 'UNKNOWN'}",
        retryable=True,
    )


def _install_m24_fulfillment_projection() -> None:
    from rasai import audit_runner, cli_extensions, m24_crawling_discovery

    base = m24_crawling_discovery.execute_m24
    if getattr(base, "_rasai_execution_contract_projection", False):
        return

    def execute_with_diagnostic_projection(*args: Any, **kwargs: Any):
        result = base(*args, **kwargs)
        audit_id = str(kwargs.get("audit_id") or "")
        workspace = kwargs.get("workspace")
        enabled = bool(kwargs.get("technical_ai", False))
        if audit_id and workspace is not None and enabled:
            reconcile_technical_ai_fulfillment(
                workspace=workspace,
                audit_id=audit_id,
                state=str(getattr(result, "ai_state", "") or ""),
            )
        return result

    execute_with_diagnostic_projection._rasai_execution_contract_projection = True
    execute_with_diagnostic_projection._rasai_original = base
    m24_crawling_discovery.execute_m24 = execute_with_diagnostic_projection
    cli_extensions.execute_m24 = execute_with_diagnostic_projection
    audit_runner.execute_m24 = execute_with_diagnostic_projection


def _work_item(workspace: Any, audit_id: str, component: str):
    return next(
        (item for item in list_work_items(workspace, audit_id) if item.component == component and item.scope_key == "AUDIT"),
        None,
    )


def _mark_requested_not_executed(
    workspace: Any,
    audit_id: str,
    component: str,
    *,
    temporal_mode: str,
    configuration: Mapping[str, Any] | None = None,
) -> None:
    register_work_item(
        workspace,
        audit_id=audit_id,
        component=component,
        required=True,
        temporal_mode=temporal_mode,
        status=REQUESTED_NOT_EXECUTED,
        retryable=True,
        configuration=configuration or {"requested": True},
    )
    set_work_item_status(
        workspace,
        audit_id=audit_id,
        component=component,
        status=REQUESTED_NOT_EXECUTED,
        error_class="ORCHESTRATION",
        error_code=REQUESTED_NOT_EXECUTED,
        error_message="recurso solicitado e elegível não possui execução materializada nesta auditoria",
        retryable=True,
    )


def _reconcile_requested_improvement(workspace: Any, audit_id: str) -> None:
    from rasai.improvement_intelligence import ENABLED_ENV, ImprovementConfig

    if not _truthy(os.environ.get(ENABLED_ENV)):
        return

    # Preserve a more specific state already projected by the governed CAT-08 hook.
    # The final reconciliation must not collapse execution-policy or prerequisite causes
    # into the generic provider-none fallback.
    existing = _work_item(workspace, audit_id, "IMPROVEMENT_INTELLIGENCE")
    if existing is not None:
        existing_code = str(getattr(existing, "last_error_code", "") or "").upper()
        existing_status = str(getattr(existing, "status", "") or "").upper()
        if (
            existing_code in {
                "AI_NOT_AUTHORIZED_FOR_EXECUTION",
                "AI_PREREQUISITES_INCOMPLETE",
            }
            and existing_status in {"REQUESTED_NOT_EXECUTED", "WAITING_FOR_DATA"}
        ):
            return

    try:
        config = ImprovementConfig.from_environment()
    except Exception as exc:
        register_work_item(
            workspace,
            audit_id=audit_id,
            component="IMPROVEMENT_INTELLIGENCE",
            required=True,
            temporal_mode=REPLAY_SAFE,
            retryable=True,
            configuration={"requested": True},
        )
        set_work_item_status(
            workspace,
            audit_id=audit_id,
            component="IMPROVEMENT_INTELLIGENCE",
            status=NOT_CONFIGURED,
            error_class="CONFIGURATION",
            error_code="IMPROVEMENT_CONFIGURATION_INVALID",
            error_message=_safe_detail(exc),
            retryable=True,
        )
        return

    register_work_item(
        workspace,
        audit_id=audit_id,
        component="IMPROVEMENT_INTELLIGENCE",
        required=True,
        temporal_mode=REPLAY_SAFE,
        retryable=True,
        configuration={
            "requested": True,
            "provider": config.provider,
            "model": config.model,
            "reasoning": config.reasoning,
        },
    )
    connection = sqlite3.connect(workspace.database)
    connection.row_factory = sqlite3.Row
    try:
        row = None
        if _table_exists(connection, "improvement_intelligence_runs"):
            row = connection.execute(
                "SELECT * FROM improvement_intelligence_runs WHERE audit_id=?",
                (audit_id,),
            ).fetchone()
    finally:
        connection.close()
    if row is None:
        provider = str(config.provider or "").strip().casefold()
        if provider in {"", "none"}:
            set_work_item_status(
                workspace,
                audit_id=audit_id,
                component="IMPROVEMENT_INTELLIGENCE",
                status=NOT_CONFIGURED,
                error_class="CONFIGURATION",
                error_code="AI_NOT_CONFIGURED",
                error_message=(
                    "CAT-08 requer IA para fechamento integral, mas nenhum provider "
                    "apto foi configurado nesta execução"
                ),
                retryable=True,
            )
        else:
            _mark_requested_not_executed(
                workspace,
                audit_id,
                "IMPROVEMENT_INTELLIGENCE",
                temporal_mode=REPLAY_SAFE,
                configuration={
                    "requested": True,
                    "provider": config.provider,
                    "model": config.model,
                    "reasoning": config.reasoning,
                },
            )
        return
    run_status = str(row["status"] or "").upper()
    reason = str(row["reason"] or "") if "reason" in row.keys() else ""
    normalized_reason = reason.strip().upper()
    if run_status == "COMPLETE":
        set_work_item_status(
            workspace,
            audit_id=audit_id,
            component="IMPROVEMENT_INTELLIGENCE",
            status=SUCCESS,
            result_ref="improvement-intelligence:effective",
            retryable=False,
        )
    elif normalized_reason in {"AI_NOT_CONFIGURED", "AI_PROVIDER_NOT_CONFIGURED"}:
        set_work_item_status(
            workspace,
            audit_id=audit_id,
            component="IMPROVEMENT_INTELLIGENCE",
            status=NOT_CONFIGURED,
            error_class="CONFIGURATION",
            error_code="AI_NOT_CONFIGURED",
            error_message=(
                "CAT-08 requer IA para fechamento integral, mas nenhum provider apto "
                "foi configurado nesta execução"
            ),
            retryable=True,
        )
    elif normalized_reason == "AI_NOT_AUTHORIZED_FOR_EXECUTION":
        set_work_item_status(
            workspace,
            audit_id=audit_id,
            component="IMPROVEMENT_INTELLIGENCE",
            status=REQUESTED_NOT_EXECUTED,
            error_class="EXECUTION_POLICY",
            error_code="AI_NOT_AUTHORIZED_FOR_EXECUTION",
            error_message=(
                "CAT-08 requer IA para fechamento integral, mas o uso de IA não foi "
                "autorizado nesta AUD"
            ),
            retryable=True,
        )
    elif normalized_reason == "AI_PREREQUISITES_INCOMPLETE":
        set_work_item_status(
            workspace,
            audit_id=audit_id,
            component="IMPROVEMENT_INTELLIGENCE",
            status="WAITING_FOR_DATA",
            error_class="PREREQUISITE",
            error_code="AI_PREREQUISITES_INCOMPLETE",
            error_message=_safe_detail(reason or "pré-requisitos de IA incompletos"),
            retryable=True,
        )
    else:
        set_work_item_status(
            workspace,
            audit_id=audit_id,
            component="IMPROVEMENT_INTELLIGENCE",
            status=FAILED_RETRYABLE,
            error_class="AI_ANALYSIS",
            error_code=normalized_reason or run_status or "IMPROVEMENT_INCOMPLETE",
            error_message=_safe_detail(reason or "Improvement Intelligence não concluiu sem limitações"),
            retryable=True,
        )


def _reconcile_requested_apdex(workspace: Any, audit_id: str) -> None:
    requested = (
        ("RASAI_SYNTHETIC_APDEX", "SYNTHETIC_APDEX"),
        ("RASAI_APDEX_EXPERIENCE", "EXPERIENCE_APDEX"),
    )
    for env_name, component in requested:
        if not _truthy(os.environ.get(env_name)):
            continue
        if _work_item(workspace, audit_id, component) is None:
            _mark_requested_not_executed(
                workspace,
                audit_id,
                component,
                temporal_mode=LIVE_RECOLLECTION,
                configuration={"requested": True, "source": env_name},
            )


def _service_run(workspace: Any, audit_id: str, service_id: str) -> dict[str, Any] | None:
    connection = sqlite3.connect(workspace.database)
    connection.row_factory = sqlite3.Row
    try:
        if not _table_exists(connection, "standards_service_runs"):
            return None
        row = connection.execute(
            "SELECT * FROM standards_service_runs WHERE audit_id=? AND service_id=?",
            (audit_id, service_id),
        ).fetchone()
        return dict(row) if row is not None else None
    finally:
        connection.close()


def _reconcile_explicit_services(workspace: Any, audit_id: str) -> None:
    """Project only service gaps not already represented by a canonical domain work item."""
    from rasai.standards_service_registry import service, service_state

    item = service("google-search-console")
    state_info = service_state(item, os.environ)
    if state_info.get("configuration_source") != "EXPLICIT" or not bool(state_info.get("requested")):
        return

    component = "GOOGLE_SEARCH_CONSOLE"
    register_work_item(
        workspace,
        audit_id=audit_id,
        component=component,
        required=True,
        temporal_mode=LIVE_RECOLLECTION,
        retryable=True,
        configuration={"requested": True, "service_id": item.id},
    )
    if not bool(state_info.get("configured")):
        missing = tuple(str(value) for value in state_info.get("missing_configuration", ()) if str(value))
        error_code = "SITE_URL_REQUIRED" if "RASAI_GOOGLE_SEARCH_CONSOLE_SITE_URL" in missing else "CONFIGURATION_REQUIRED"
        set_work_item_status(
            workspace,
            audit_id=audit_id,
            component=component,
            status=NOT_CONFIGURED,
            error_class="CONFIGURATION",
            error_code=error_code,
            error_message=("configuração ausente: " + ", ".join(missing)) if missing else "Google Search Console solicitado sem configuração completa",
            retryable=True,
        )
        return

    run = _service_run(workspace, audit_id, item.id)
    if run is None:
        _mark_requested_not_executed(
            workspace,
            audit_id,
            component,
            temporal_mode=LIVE_RECOLLECTION,
            configuration={"requested": True, "service_id": item.id},
        )
        return
    state = str(run.get("state") or "").upper()
    attempted = int(run.get("targets_attempted") or 0)
    succeeded = int(run.get("targets_succeeded") or 0)
    if state in {"SUCCESS", "READY"} and (attempted == 0 or succeeded == attempted):
        set_work_item_status(
            workspace,
            audit_id=audit_id,
            component=component,
            status=SUCCESS,
            result_ref="standards-service:google-search-console:effective",
            retryable=False,
        )
    elif state == "NOT_CONFIGURED":
        set_work_item_status(
            workspace,
            audit_id=audit_id,
            component=component,
            status=NOT_CONFIGURED,
            error_class="CONFIGURATION",
            error_code="CONFIGURATION_REQUIRED",
            error_message="Google Search Console solicitado sem configuração completa",
            retryable=True,
        )
    else:
        set_work_item_status(
            workspace,
            audit_id=audit_id,
            component=component,
            status=FAILED_RETRYABLE,
            error_class="EXTERNAL_SERVICE",
            error_code=state or "SERVICE_INCOMPLETE",
            error_message=f"Google Search Console terminou em {state or 'UNKNOWN'} ({succeeded}/{attempted} alvos com sucesso)",
            retryable=True,
        )


def reconcile_requested_components(*, workspace: Any, audit_id: str) -> None:
    """Make requested-but-absent work visible before final AUD status is projected."""
    try:
        from rasai.audit_fulfillment_runtime import _sync_persisted_components
        _sync_persisted_components(audit_id=audit_id, workspace=workspace)
    except Exception:
        pass
    reconcile_technical_ai_fulfillment(workspace=workspace, audit_id=audit_id)
    _reconcile_requested_improvement(workspace, audit_id)
    _reconcile_requested_apdex(workspace, audit_id)
    _reconcile_explicit_services(workspace, audit_id)
    project_report_validity(audit_id=audit_id, workspace=workspace)


def _install_final_reconciliation() -> None:
    from rasai import report_completion

    original = report_completion.finalize_audit_report_site
    if getattr(original, "_rasai_execution_contract_reconciliation", False):
        return

    def finalize_with_execution_contract(*args: Any, **kwargs: Any):
        result = original(*args, **kwargs)
        audit_id = str(kwargs.get("audit_id") or (args[0] if args else ""))
        workspace = kwargs.get("workspace")
        if audit_id and workspace is not None:
            reconcile_requested_components(workspace=workspace, audit_id=audit_id)
        return result

    finalize_with_execution_contract._rasai_execution_contract_reconciliation = True
    finalize_with_execution_contract._rasai_original = original
    report_completion.finalize_audit_report_site = finalize_with_execution_contract


def audit_result_lines(workspace: Any, audit_id: str) -> tuple[str, ...]:
    summary = read_summary(workspace, audit_id)
    if summary is None:
        return ()
    logical_labels = {
        "COMPLETE": "COMPLETO",
        "PARTIAL_RETRYABLE": "PARCIAL - REPROCESSÁVEL",
        "PARTIAL_BLOCKED": "PARCIAL - BLOQUEADO",
        "EXPIRED_FOR_COMPLETION": "EXPIRADO PARA CONCLUSÃO",
        "PROCESSING": "EM PROCESSAMENTO",
        "FAILED_FATAL": "FALHA FATAL",
    }
    lines = [
        "=" * 68,
        "RESULTADO DA AUDITORIA",
        "=" * 68,
        "Execução física : 100% ENCERRADA",
        f"Audit ID        : {audit_id}",
        f"Status do AUD   : {logical_labels.get(summary.processing_status, summary.processing_status)}",
        f"Relatório       : {summary.report_status}",
        f"Score           : {summary.score_status}",
        f"Consolidação    : {'ELEGÍVEL' if summary.consolidation_eligible else 'NÃO ELEGÍVEL'}",
        f"Requisitos      : {summary.successful_items}/{summary.required_items} atendidos",
    ]
    pending = [item for item in list_work_items(workspace, audit_id, pending_only=True) if item.required]
    if pending:
        lines.extend(("", "PENDÊNCIAS"))
        for item in pending:
            action = "CONFIGURAR" if item.status == NOT_CONFIGURED else "REPROCESSAR"
            lines.append(f"[{action}] {item.component}")
            lines.append(f"Estado     : {item.status}")
            if item.last_error_class:
                lines.append(f"Classe     : {item.last_error_class}")
            provider = str(item.configuration.get("provider") or "")
            model = str(item.configuration.get("model") or "")
            if provider:
                lines.append(f"Provider   : {provider}")
            if model:
                lines.append(f"Modelo     : {model}")
            if item.last_error_code:
                lines.append(f"Código     : {item.last_error_code}")
            if item.last_error_message:
                lines.append(f"Detalhe    : {_safe_detail(item.last_error_message)}")
            lines.append("")
        lines.extend(
            (
                "AÇÃO RECOMENDADA",
                "Resolver dependências de configuração/orquestração e reprocessar somente os requisitos pendentes.",
            )
        )
    return tuple(lines)


def install_console_projection(console_module: Any | None = None) -> None:
    """Render physical completion separately from the canonical AUD outcome."""
    global _CONSOLE_INSTALLED
    if _CONSOLE_INSTALLED:
        return
    from rasai import console_runtime

    if console_module is None:
        try:
            from rasai import interactive_console as console_module
        except ImportError:
            console_module = None
    target = console_module if console_module is not None else console_runtime
    original = getattr(target, "run_audit_from_console", None)
    if not callable(original) or getattr(original, "_rasai_execution_result_projection", False):
        _CONSOLE_INSTALLED = True
        return

    def run_with_canonical_result(state: Any) -> int:
        code = original(state)
        audit_id = str(getattr(state, "audit_id", "") or "")
        if not audit_id:
            return code
        root = Path(getattr(state, "audits_root", "audits")) / audit_id
        summary = read_summary(root, audit_id)
        if summary is None:
            return code
        state.status = summary.processing_status
        state.operation = "LOCAL:DONE"
        state.error = ""
        console_runtime._RUN_PROGRESS[id(state)] = console_runtime._RunProgress(
            label="Execução encerrada",
            percent=100.0,
            detail=f"processamento físico encerrado; resultado lógico do AUD: {summary.processing_status}",
            exact=True,
            stage_percent=100.0,
            stage_exact=True,
            overall_percent=100.0,
            overall_exact=True,
        )
        render = getattr(target, "render_header", console_runtime.render_header)
        render(state)
        for line in audit_result_lines(root, audit_id):
            print(line)
        return code

    run_with_canonical_result._rasai_execution_result_projection = True
    run_with_canonical_result._rasai_original = original
    target.run_audit_from_console = run_with_canonical_result
    _CONSOLE_INSTALLED = True


def install() -> None:
    """Install the shared local/SaaS execution-to-fulfillment contract."""
    global _INSTALLED
    if _INSTALLED:
        return
    _install_m24_diagnostic_preservation()
    _install_m24_fulfillment_projection()
    _install_final_reconciliation()
    _INSTALLED = True
