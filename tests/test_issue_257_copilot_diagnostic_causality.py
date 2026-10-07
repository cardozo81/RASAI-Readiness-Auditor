from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
import sqlite3

import pytest

from rasai.ai_exchange_log import AiExchangeRecorder, instrument_provider_transport, persist_ai_exchange_log
from rasai.ai_orchestration_unification import _candidate_call
from rasai.catalog_report_final_refinements import _ai_integrations_body
from rasai.domain import Audit
from rasai.m18_ai import (
    AttemptStatus,
    ProviderAttempt,
    ProviderDiagnostic,
    ProviderErrorClass,
)
from rasai.m18_persistence import M18Persistence
from rasai.persistence import AuditPersistence, AuditWorkspace
from rasai.semantic import SemanticProviderError


AUDIT_ID = "AUD-ISSUE-257"


def _workspace(tmp_path):
    workspace = AuditWorkspace.create(tmp_path, AUDIT_ID)
    with AuditPersistence(workspace) as persistence:
        persistence.audits.add(Audit(audit_id=AUDIT_ID, project_name="issue-257"))
    return workspace


def _failing_provider():
    def fail(_url, _headers, _body, _timeout):
        raise SemanticProviderError(
            "GitHub Copilot SDK failed; Authorization: Bearer live-token-93af"
        )

    return SimpleNamespace(
        name="COPILOT",
        model="auto",
        endpoint="copilot://sdk",
        _headers=lambda: {"Content-Type": "application/json"},
        _transport=fail,
    )


def test_candidate_call_preserves_sanitized_semantic_provider_error_detail() -> None:
    provider = _failing_provider()

    raw, usage, diagnostic, status, _duration = _candidate_call(
        provider,
        body=b'{"model":"auto","prompt":"test"}',
        timeout=1.0,
    )

    assert raw is None
    assert usage is None
    assert status is AttemptStatus.TECHNICAL_ERROR
    assert diagnostic is not None
    assert diagnostic.error_class is ProviderErrorClass.UNKNOWN_PROVIDER_ERROR
    assert diagnostic.error_type == "SemanticProviderError"
    assert diagnostic.error_detail
    assert "live-token-93af" not in diagnostic.error_detail
    assert "[REDACTED]" in diagnostic.error_detail


def test_exchange_log_persists_secret_safe_exception_detail(tmp_path) -> None:
    workspace = _workspace(tmp_path)
    provider = _failing_provider()
    recorder = AiExchangeRecorder()
    instrument_provider_transport(provider, recorder)

    with pytest.raises(SemanticProviderError):
        provider._transport(
            provider.endpoint,
            provider._headers(),
            b'{"model":"auto","prompt":"test"}',
            1.0,
        )

    exchange = recorder.exchanges[-1]
    assert exchange.exception_type == "SemanticProviderError"
    assert exchange.exception_detail
    assert "live-token-93af" not in exchange.exception_detail
    assert "[REDACTED]" in exchange.exception_detail

    assert persist_ai_exchange_log(
        audit_id=AUDIT_ID,
        workspace=workspace,
        recorder=recorder,
    ) == 1

    connection = sqlite3.connect(workspace.database)
    try:
        row = connection.execute(
            "SELECT exception_type,exception_detail FROM ai_exchange_log WHERE audit_id=?",
            (AUDIT_ID,),
        ).fetchone()
    finally:
        connection.close()

    assert row == (
        "SemanticProviderError",
        exchange.exception_detail,
    )


def test_attempt_persistence_and_report_keep_provider_error_detail(tmp_path) -> None:
    workspace = _workspace(tmp_path)
    detail = "GitHub Copilot SDK session rejected the request safely"
    now = datetime.now(timezone.utc)
    attempt = ProviderAttempt(
        provider="COPILOT",
        model="auto",
        reasoning_profile="PROVIDER_DEFAULT",
        provider_rank=900,
        attempt_index=1,
        snapshot_id="",
        url="https://example.test/",
        started_at=now,
        finished_at=now,
        duration_ms=1,
        status=AttemptStatus.TECHNICAL_ERROR,
        diagnostic=ProviderDiagnostic(
            ProviderErrorClass.UNKNOWN_PROVIDER_ERROR,
            error_type="SemanticProviderError",
            error_detail=detail,
        ),
        request_message_summary="contract=M18-SEMANTIC-22-v1",
        request_payload_hash="hash-257",
    )

    with M18Persistence(workspace) as store:
        store.add_attempt(
            attempt_id="AIA-257",
            audit_id=AUDIT_ID,
            page_id=None,
            snapshot_id=None,
            url="https://example.test/",
            device=None,
            attempt=attempt,
        )

    connection = sqlite3.connect(workspace.database)
    try:
        row = connection.execute(
            "SELECT error_class,error_type,error_detail FROM ai_provider_attempts "
            "WHERE attempt_id='AIA-257'"
        ).fetchone()
    finally:
        connection.close()

    assert row == (
        ProviderErrorClass.UNKNOWN_PROVIDER_ERROR.value,
        "SemanticProviderError",
        detail,
    )

    data = SimpleNamespace(
        audit_id=AUDIT_ID,
        targets=("https://example.test/",),
        selected={"CAT-03"},
        audit={"project_name": "issue-257", "status": "COMPLETED"},
        fulfillment={"processing_status": "PARTIAL_RETRYABLE"},
    )
    html = _ai_integrations_body(workspace.database, data)
    assert detail in html
    assert "SemanticProviderError" in html
