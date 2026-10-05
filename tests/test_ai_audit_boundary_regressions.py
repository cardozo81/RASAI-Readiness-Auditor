from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory

from rasai.ai_exchange_log import AiExchangeRecorder, persist_ai_exchange_log
from rasai.catalog_report_integrations import _provider_identity, _raw_payload_block
from rasai.domain import Audit
from rasai.improvement_intelligence import _TargetContext, _persist_attempt
from rasai.m18_ai import AttemptStatus, ProviderAttempt
from rasai.m18_persistence import M18Persistence
from rasai.persistence import AuditPersistence, AuditWorkspace
from rasai.provider_registry import provider_registrations
from rasai.report_presentation import humanize_report_html


def _workspace(root: Path, audit_id: str) -> AuditWorkspace:
    workspace = AuditWorkspace.create(root, audit_id)
    with AuditPersistence(workspace) as persistence:
        persistence.audits.add(Audit(audit_id=audit_id, project_name="AI boundary regression"))
    return workspace


def _attempt(
    *,
    attempt_id: str,
    contract: str,
    body: bytes,
    provider: str = "OPENAI",
    model: str = "gpt-test",
) -> ProviderAttempt:
    started = datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc)
    return ProviderAttempt(
        provider=provider,
        model=model,
        reasoning_profile="NONE",
        provider_rank=1,
        attempt_index=1,
        snapshot_id="",
        url="https://example.test/",
        started_at=started,
        finished_at=started,
        duration_ms=1,
        status=AttemptStatus.SUCCESS,
        request_message_summary=f"contract={contract}",
        request_payload_hash=sha256(body).hexdigest(),
        semantic_contract_version=contract,
        attempt_id=attempt_id,
    )


def test_provider_identities_are_not_generic_public_fallbacks() -> None:
    for registration in provider_registrations():
        provider = str(registration.provider_name)
        html = humanize_report_html(
            "<td>" + str(_provider_identity(provider)) + "</td>",
            page_name="ai-integrations.html",
        )
        assert provider in html
        assert "Condição técnica não catalogada" not in html


def test_persisted_raw_payload_is_not_semantically_humanized() -> None:
    raw = "Task specialization profile: SEMANTIC_READINESS (version 1.0) <raw>."
    html = humanize_report_html(
        _raw_payload_block(raw),
        page_name="ai-integrations.html",
    )
    assert "SEMANTIC_READINESS" in html
    assert "&lt;raw&gt;" in html
    assert "Condição técnica não catalogada" not in html


def test_directed_analysis_taskless_attempt_correlates_with_exchange() -> None:
    audit_id = "AUD-DIRECTED-CORRELATION"
    body = b'{"model":"gpt-test","instructions":"DIRECTED_ANALYSIS"}'
    attempt_id = "AIA-DIRECTED-1"
    with TemporaryDirectory() as directory:
        workspace = _workspace(Path(directory), audit_id)
        context = _TargetContext(
            page_id=None,  # type: ignore[arg-type]
            url="https://example.test/",
            input_url="https://example.test/",
            snapshot_id=None,  # type: ignore[arg-type]
            device="desktop",
            snapshot_rows=(),
            audit_language="pt-BR",
            market="BR",
            title=None,
            description=None,
            canonical=None,
            html="",
            structured_data=None,
        )
        attempt = _attempt(
            attempt_id=attempt_id,
            contract="DIRECTED-ANALYSIS-001",
            body=body,
        )
        recorder = AiExchangeRecorder()
        recorder.append_exchange(
            provider="OPENAI",
            model="gpt-test",
            endpoint="https://example.test/v1",
            body=body,
            started_at=attempt.started_at,
            duration_ms=1,
            outcome="RESPONSE",
            response={"ok": True},
        )
        assert recorder.bind_latest_attempt(attempt_id)

        _persist_attempt(
            workspace,
            audit_id,
            context,
            attempt,
            attempt_id=attempt_id,
            operation="DIRECTED_ANALYSIS",
        )
        persist_ai_exchange_log(audit_id=audit_id, workspace=workspace, recorder=recorder)

        connection = sqlite3.connect(workspace.database)
        try:
            attempt_row = connection.execute(
                "SELECT operation,ai_task_id,ai_round_id FROM ai_provider_attempts WHERE attempt_id=?",
                (attempt_id,),
            ).fetchone()
            exchange_row = connection.execute(
                "SELECT purpose,attempt_id FROM ai_exchange_log WHERE audit_id=?",
                (audit_id,),
            ).fetchone()
        finally:
            connection.close()

        assert attempt_row == ("DIRECTED_ANALYSIS", None, None)
        assert exchange_row == ("DIRECTED_ANALYSIS", attempt_id)


def test_competitive_intelligence_correlates_by_attempt_id_not_purpose_join() -> None:
    audit_id = "AUD-COMPETITIVE-CORRELATION"
    body = b'{"model":"gpt-test","text":{"format":{"name":"rasai_competitive_ai"}}}'
    attempt_id = "AIA-COMPETITIVE-1"
    with TemporaryDirectory() as directory:
        workspace = _workspace(Path(directory), audit_id)
        attempt = _attempt(
            attempt_id=attempt_id,
            contract="COMPETITIVE-AI-001",
            body=body,
        )
        with M18Persistence(workspace) as store:
            store.add_attempt(
                attempt_id=attempt_id,
                audit_id=audit_id,
                page_id=None,
                snapshot_id=None,
                url="https://example.test/",
                device="search",
                attempt=attempt,
                operation="COMPETITIVE_INTELLIGENCE",
                ai_task_id="AIT-COMP-1",
                ai_round_id="AIR-COMP-1",
            )

        recorder = AiExchangeRecorder()
        recorder.append_exchange(
            provider="OPENAI",
            model="gpt-test",
            endpoint="https://example.test/v1",
            body=body,
            started_at=attempt.started_at,
            duration_ms=1,
            outcome="RESPONSE",
            response={"ok": True},
        )
        assert recorder.exchanges[-1].purpose == "COMPETITIVE_INTELLIGENCE"
        assert recorder.bind_latest_attempt(attempt_id)
        persist_ai_exchange_log(audit_id=audit_id, workspace=workspace, recorder=recorder)

        connection = sqlite3.connect(workspace.database)
        try:
            row = connection.execute(
                "SELECT purpose,attempt_id FROM ai_exchange_log WHERE audit_id=?",
                (audit_id,),
            ).fetchone()
        finally:
            connection.close()
        assert row == ("COMPETITIVE_INTELLIGENCE", attempt_id)


def test_legacy_exchange_schema_remains_readable_and_is_upgraded_additively() -> None:
    audit_id = "AUD-LEGACY-EXCHANGE"
    with TemporaryDirectory() as directory:
        workspace = _workspace(Path(directory), audit_id)
        connection = sqlite3.connect(workspace.database)
        try:
            connection.executescript(
                """
                CREATE TABLE ai_exchange_log (
                    exchange_id TEXT PRIMARY KEY,
                    audit_id TEXT NOT NULL REFERENCES audits(audit_id) ON DELETE CASCADE,
                    sequence_no INTEGER NOT NULL,
                    provider TEXT NOT NULL,
                    model TEXT,
                    purpose TEXT NOT NULL,
                    snapshot_id TEXT,
                    page_url TEXT,
                    endpoint TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    finished_at TEXT NOT NULL,
                    duration_ms INTEGER NOT NULL,
                    outcome TEXT NOT NULL,
                    http_status INTEGER,
                    exception_type TEXT,
                    request_payload TEXT NOT NULL,
                    request_sha256 TEXT NOT NULL,
                    request_truncated INTEGER NOT NULL,
                    response_payload TEXT,
                    response_sha256 TEXT,
                    response_truncated INTEGER NOT NULL
                );
                """
            )
            connection.commit()
        finally:
            connection.close()

        recorder = AiExchangeRecorder()
        recorder.append_exchange(
            provider="OPENAI",
            model="gpt-test",
            endpoint="https://example.test/v1",
            body=b'{"instructions":"legacy semantic request"}',
            started_at=datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc),
            duration_ms=1,
            outcome="RESPONSE",
            response={"ok": True},
        )
        assert persist_ai_exchange_log(
            audit_id=audit_id,
            workspace=workspace,
            recorder=recorder,
        ) == 1

        connection = sqlite3.connect(workspace.database)
        try:
            columns = {
                str(row[1])
                for row in connection.execute("PRAGMA table_info(ai_exchange_log)").fetchall()
            }
            row = connection.execute(
                "SELECT provider,request_payload,attempt_id FROM ai_exchange_log WHERE audit_id=?",
                (audit_id,),
            ).fetchone()
        finally:
            connection.close()

        assert {"request_payload_hash", "attempt_id"}.issubset(columns)
        assert row[0] == "OPENAI"
        assert "legacy semantic request" in row[1]
        assert row[2] is None
