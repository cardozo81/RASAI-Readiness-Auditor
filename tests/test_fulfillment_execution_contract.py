from __future__ import annotations

from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory

from rasai.audit_fulfillment import REPLAY_SAFE, SUCCESS, list_work_items, register_work_item, set_work_item_status
from rasai.domain import Audit, CompletionStatus
from rasai.fulfillment_execution_contract import (
    AI_CONTRACT,
    M24_CONTRACT_ERROR_CODE,
    NOT_CONFIGURED,
    REQUESTED_NOT_EXECUTED,
    _ensure_attempt_detail_column,
    _reconcile_explicit_services,
    _reconcile_requested_apdex,
    _reconcile_requested_improvement,
    audit_result_lines,
    reconcile_technical_ai_fulfillment,
)
from rasai.persistence import AuditPersistence, AuditWorkspace
from rasai.standards_service_registry import services


AUDIT_ID = "AUD-FULFILLMENT-EXECUTION-CONTRACT"


def _workspace(root: Path) -> AuditWorkspace:
    workspace = AuditWorkspace.create(root, AUDIT_ID)
    with AuditPersistence(workspace) as persistence:
        persistence.audits.add(Audit(audit_id=AUDIT_ID, project_name="execution contract"))
    return workspace


def _create_attempt_table(workspace: AuditWorkspace, *, with_error_detail: bool = True) -> None:
    detail_column = ",error_detail TEXT" if with_error_detail else ""
    connection = sqlite3.connect(workspace.database)
    try:
        with connection:
            connection.execute("DROP TABLE IF EXISTS ai_provider_attempts")
            connection.execute(
                f"""CREATE TABLE ai_provider_attempts(
                    attempt_id TEXT PRIMARY KEY,
                    audit_id TEXT,
                    provider TEXT,
                    model TEXT,
                    attempt_index INTEGER,
                    status TEXT,
                    error_class TEXT,
                    http_status INTEGER,
                    error_type TEXT,
                    error_code TEXT,
                    semantic_contract_version TEXT,
                    retry_eligible INTEGER,
                    decision TEXT,
                    fallback_from_provider TEXT,
                    fallback_reason TEXT,
                    input_tokens INTEGER,
                    cached_input_tokens INTEGER,
                    output_tokens INTEGER,
                    reasoning_tokens INTEGER,
                    total_tokens INTEGER,
                    estimated_cost REAL,
                    cost_currency TEXT,
                    pricing_version TEXT,
                    request_payload_hash TEXT,
                    started_at TEXT,
                    finished_at TEXT,
                    duration_ms INTEGER
                    {detail_column}
                )"""
            )
    finally:
        connection.close()


def _insert_contract_error(workspace: AuditWorkspace) -> None:
    _create_attempt_table(workspace)
    connection = sqlite3.connect(workspace.database)
    try:
        with connection:
            connection.execute(
                """INSERT INTO ai_provider_attempts(
                    attempt_id,audit_id,provider,model,attempt_index,status,error_class,
                    error_type,error_code,semantic_contract_version,retry_eligible,decision,
                    input_tokens,cached_input_tokens,output_tokens,reasoning_tokens,total_tokens,
                    estimated_cost,cost_currency,pricing_version,request_payload_hash,started_at,
                    finished_at,duration_ms,error_detail
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    "AIA-1", AUDIT_ID, "DEEPSEEK", "deepseek-v4-pro", 1,
                    "CONTRACT_ERROR", "CONTRACT_ERROR", "ValueError",
                    M24_CONTRACT_ERROR_CODE, "M24-TECHNICAL-REMEDIATION-v2", 1,
                    "REPROCESS_ELIGIBLE", 1000, 100, 200, 0, 1200, 0.00123,
                    "USD", "RASAI-PRICING-2026-09-13", "hash-1",
                    "2026-09-13T20:00:00+00:00", "2026-09-13T20:00:01+00:00", 1000,
                    "M24 AI resource assessment references evidence outside its resource universe",
                ),
            )
    finally:
        connection.close()


def test_contract_error_projects_ai_contract_instead_of_provider_unavailable() -> None:
    with TemporaryDirectory() as directory:
        workspace = _workspace(Path(directory))
        _insert_contract_error(workspace)

        reconcile_technical_ai_fulfillment(workspace=workspace, audit_id=AUDIT_ID, state="UNAVAILABLE")

        item = next(item for item in list_work_items(workspace, AUDIT_ID) if item.component == "TECHNICAL_AI")
        assert item.status == "FAILED_RETRYABLE"
        assert item.retryable is True
        assert item.last_error_class == AI_CONTRACT
        assert item.last_error_code == M24_CONTRACT_ERROR_CODE
        assert item.last_error_message == "M24 AI resource assessment references evidence outside its resource universe"
        assert item.configuration["provider"] == "DEEPSEEK"
        assert item.configuration["model"] == "deepseek-v4-pro"


def test_contract_error_reconciliation_does_not_reprice_observed_attempt() -> None:
    with TemporaryDirectory() as directory:
        workspace = _workspace(Path(directory))
        _insert_contract_error(workspace)

        reconcile_technical_ai_fulfillment(workspace=workspace, audit_id=AUDIT_ID, state="UNAVAILABLE")

        connection = sqlite3.connect(workspace.database)
        try:
            row = connection.execute(
                "SELECT estimated_cost,cost_currency,pricing_version,input_tokens,total_tokens FROM ai_provider_attempts WHERE attempt_id='AIA-1'"
            ).fetchone()
        finally:
            connection.close()
        assert row == (0.00123, "USD", "RASAI-PRICING-2026-09-13", 1000, 1200)


def test_attempt_error_detail_schema_is_additive() -> None:
    with TemporaryDirectory() as directory:
        workspace = _workspace(Path(directory))
        _create_attempt_table(workspace, with_error_detail=False)
        _ensure_attempt_detail_column(workspace)
        connection = sqlite3.connect(workspace.database)
        try:
            columns = {str(row[1]) for row in connection.execute("PRAGMA table_info(ai_provider_attempts)")}
        finally:
            connection.close()
        assert "error_detail" in columns


def test_requested_synthetic_apdex_without_run_is_not_silently_omitted(monkeypatch) -> None:
    with TemporaryDirectory() as directory:
        workspace = _workspace(Path(directory))
        monkeypatch.setenv("RASAI_SYNTHETIC_APDEX", "true")
        monkeypatch.delenv("RASAI_APDEX_EXPERIENCE", raising=False)

        _reconcile_requested_apdex(workspace, AUDIT_ID)

        item = next(item for item in list_work_items(workspace, AUDIT_ID) if item.component == "SYNTHETIC_APDEX")
        assert item.status == REQUESTED_NOT_EXECUTED
        assert item.last_error_class == "ORCHESTRATION"
        assert item.last_error_code == REQUESTED_NOT_EXECUTED


def test_requested_experience_apdex_without_run_is_not_silently_omitted(monkeypatch) -> None:
    with TemporaryDirectory() as directory:
        workspace = _workspace(Path(directory))
        monkeypatch.delenv("RASAI_SYNTHETIC_APDEX", raising=False)
        monkeypatch.setenv("RASAI_APDEX_EXPERIENCE", "true")

        _reconcile_requested_apdex(workspace, AUDIT_ID)

        item = next(item for item in list_work_items(workspace, AUDIT_ID) if item.component == "EXPERIENCE_APDEX")
        assert item.status == REQUESTED_NOT_EXECUTED
        assert item.retryable is True


def test_gsc_missing_site_url_is_configuration_failure_not_technical_ai(monkeypatch) -> None:
    with TemporaryDirectory() as directory:
        workspace = _workspace(Path(directory))
        for service in services():
            monkeypatch.delenv(service.enabled_env, raising=False)
        monkeypatch.setenv("RASAI_GSC_ENABLED", "true")
        monkeypatch.setenv("RASAI_GOOGLE_SEARCH_CONSOLE_ACCESS_TOKEN", "test-oauth-token")
        monkeypatch.delenv("RASAI_GOOGLE_SEARCH_CONSOLE_SITE_URL", raising=False)

        _reconcile_explicit_services(workspace, AUDIT_ID)

        items = {item.component: item for item in list_work_items(workspace, AUDIT_ID)}
        assert items["GOOGLE_SEARCH_CONSOLE"].status == NOT_CONFIGURED
        assert items["GOOGLE_SEARCH_CONSOLE"].last_error_class == "CONFIGURATION"
        assert items["GOOGLE_SEARCH_CONSOLE"].last_error_code == "SITE_URL_REQUIRED"
        assert "TECHNICAL_AI" not in items


def test_requested_improvement_without_materialized_run_is_visible(monkeypatch) -> None:
    with TemporaryDirectory() as directory:
        workspace = _workspace(Path(directory))
        monkeypatch.setenv("RASAI_IMPROVEMENT_INTELLIGENCE", "true")

        _reconcile_requested_improvement(workspace, AUDIT_ID)

        item = next(item for item in list_work_items(workspace, AUDIT_ID) if item.component == "IMPROVEMENT_INTELLIGENCE")
        assert item.status == NOT_CONFIGURED
        assert item.last_error_class == "CONFIGURATION"
        assert item.last_error_code == "AI_NOT_CONFIGURED"
        # Standalone reconciliation consumes no parallel provider selector.
        # Empty provider/model means the primary execution routing snapshot did not
        # materialize a provider for this isolated reconciliation.
        assert item.configuration["provider"] == ""
        assert item.configuration["model"] == ""


def test_physical_100_percent_does_not_turn_partial_fulfillment_into_complete() -> None:
    with TemporaryDirectory() as directory:
        workspace = _workspace(Path(directory))
        register_work_item(
            workspace,
            audit_id=AUDIT_ID,
            component="CORE_AUDIT",
            required=True,
            temporal_mode=REPLAY_SAFE,
            status=SUCCESS,
            retryable=False,
        )
        set_work_item_status(
            workspace,
            audit_id=AUDIT_ID,
            component="CORE_AUDIT",
            status=SUCCESS,
            result_ref="audit:ok",
            retryable=False,
        )
        register_work_item(
            workspace,
            audit_id=AUDIT_ID,
            component="TECHNICAL_AI",
            required=True,
            temporal_mode=REPLAY_SAFE,
            status=REQUESTED_NOT_EXECUTED,
            retryable=True,
        )
        set_work_item_status(
            workspace,
            audit_id=AUDIT_ID,
            component="TECHNICAL_AI",
            status=REQUESTED_NOT_EXECUTED,
            error_class="ORCHESTRATION",
            error_code=REQUESTED_NOT_EXECUTED,
            error_message="requested but absent",
            retryable=True,
        )

        lines = audit_result_lines(workspace, AUDIT_ID)
        text = "\n".join(lines)
        assert "Execução física : 100% ENCERRADA" in text
        assert "Status do AUD   : PARCIAL - REPROCESSÁVEL" in text
        assert "Relatório       : PRELIMINARY" in text
        assert "Consolidação    : NÃO ELEGÍVEL" in text
        assert "Requisitos      : 1/2 atendidos" in text


def test_complete_is_reported_only_when_all_required_items_succeed() -> None:
    with TemporaryDirectory() as directory:
        workspace = _workspace(Path(directory))
        register_work_item(
            workspace,
            audit_id=AUDIT_ID,
            component="CORE_AUDIT",
            required=True,
            temporal_mode=REPLAY_SAFE,
            status=SUCCESS,
            retryable=False,
        )
        set_work_item_status(
            workspace,
            audit_id=AUDIT_ID,
            component="CORE_AUDIT",
            status=SUCCESS,
            result_ref="audit:ok",
            retryable=False,
        )
        with AuditPersistence(workspace) as persistence:
            persistence.audits.complete(AUDIT_ID, CompletionStatus.COMPLETE)
        text = "\n".join(audit_result_lines(workspace, AUDIT_ID))
        assert "Status do AUD   : COMPLETO" in text
        assert "Relatório       : FINAL" in text
        assert "Score           : FINAL" in text
        assert "Consolidação    : ELEGÍVEL" in text

def test_improvement_not_configured_is_not_overwritten_as_generic_retry_failure(monkeypatch) -> None:
    from types import SimpleNamespace
    from rasai import improvement_intelligence

    with TemporaryDirectory() as directory:
        workspace = _workspace(Path(directory))
        monkeypatch.setenv(improvement_intelligence.ENABLED_ENV, "true")
        monkeypatch.setattr(
            improvement_intelligence.ImprovementConfig,
            "from_environment",
            classmethod(
                lambda cls: SimpleNamespace(
                    provider="none",
                    model="",
                    reasoning="",
                )
            ),
        )
        connection = sqlite3.connect(workspace.database)
        try:
            with connection:
                connection.execute(
                    """CREATE TABLE improvement_intelligence_runs(
                        audit_id TEXT PRIMARY KEY,
                        status TEXT,
                        reason TEXT
                    )"""
                )
                connection.execute(
                    "INSERT INTO improvement_intelligence_runs(audit_id,status,reason) VALUES(?,?,?)",
                    (AUDIT_ID, "COMPLETE_WITH_LIMITATIONS", "AI_NOT_CONFIGURED"),
                )
        finally:
            connection.close()

        _reconcile_requested_improvement(workspace, AUDIT_ID)

        item = next(
            item
            for item in list_work_items(workspace, AUDIT_ID)
            if item.component == "IMPROVEMENT_INTELLIGENCE"
        )
        assert item.status == NOT_CONFIGURED
        assert item.last_error_class == "CONFIGURATION"
        assert item.last_error_code == "AI_NOT_CONFIGURED"
