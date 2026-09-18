"""Additive SQLite persistence for provider routing, telemetry and pricing."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
import json
import logging
import sqlite3
import threading
from typing import Any, Iterator

from rasai.ai_cost_policy import PRICING_CATALOG
from rasai.m18_ai import ProviderAttempt
from rasai.persistence import AuditWorkspace

_LOGGER = logging.getLogger(__name__)

_ATTEMPT_GOVERNANCE: ContextVar[
    tuple[str | None, str | None, str | None] | None
] = ContextVar("rasai_ai_attempt_governance", default=None)
_ATTEMPT_GOVERNANCE_BY_ATTEMPT: dict[
    tuple[str, str, str, str, int],
    tuple[str | None, str | None, str | None],
] = {}
_ATTEMPT_GOVERNANCE_LOCK = threading.Lock()


def _attempt_governance_key(attempt: ProviderAttempt) -> tuple[str, str, str, str, int]:
    return (
        str(attempt.provider),
        str(attempt.snapshot_id or ""),
        str(attempt.request_payload_hash or ""),
        attempt.started_at.isoformat(),
        int(attempt.attempt_index),
    )


def remember_attempt_governance(
    attempt: ProviderAttempt,
    *,
    operation: str | None,
    ai_task_id: str | None,
    ai_round_id: str | None,
) -> None:
    with _ATTEMPT_GOVERNANCE_LOCK:
        _ATTEMPT_GOVERNANCE_BY_ATTEMPT[_attempt_governance_key(attempt)] = (
            operation,
            ai_task_id,
            ai_round_id,
        )


def _consume_attempt_governance(
    attempt: ProviderAttempt,
) -> tuple[str | None, str | None, str | None] | None:
    with _ATTEMPT_GOVERNANCE_LOCK:
        return _ATTEMPT_GOVERNANCE_BY_ATTEMPT.pop(_attempt_governance_key(attempt), None)


def current_attempt_governance() -> tuple[str | None, str | None, str | None] | None:
    return _ATTEMPT_GOVERNANCE.get()


def _durable_semantic_governance(
    store: "M18Persistence",
    *,
    audit_id: str,
    attempt: ProviderAttempt,
) -> tuple[str | None, str | None, str | None] | None:
    """Resolve the semantic task/round from durable governance timing and snapshot scope."""
    snapshot_id = str(attempt.snapshot_id or "")
    if not snapshot_id:
        return None
    try:
        rows = store._connection.execute(
            """
            SELECT t.ai_task_id,r.ai_round_id,r.started_at,r.finished_at
            FROM ai_tasks t
            JOIN ai_request_rounds r ON r.ai_task_id=t.ai_task_id
            WHERE t.audit_id=? AND t.purpose='SEMANTIC_M7' AND t.scope_key=?
            ORDER BY r.started_at DESC,r.round_index DESC
            """,
            (audit_id, snapshot_id),
        ).fetchall()
    except sqlite3.OperationalError:
        return None

    started = attempt.started_at
    finished = attempt.finished_at
    for row in rows:
        try:
            round_started = datetime.fromisoformat(str(row["started_at"]).replace("Z", "+00:00"))
            raw_finished = row["finished_at"]
            round_finished = (
                datetime.fromisoformat(str(raw_finished).replace("Z", "+00:00"))
                if raw_finished
                else None
            )
        except (TypeError, ValueError):
            continue
        if round_started.tzinfo is None:
            round_started = round_started.replace(tzinfo=timezone.utc)
        if round_finished is not None and round_finished.tzinfo is None:
            round_finished = round_finished.replace(tzinfo=timezone.utc)
        if started.tzinfo is None:
            started = started.replace(tzinfo=timezone.utc)
        if finished.tzinfo is None:
            finished = finished.replace(tzinfo=timezone.utc)
        if started < round_started:
            continue
        if round_finished is not None and finished > round_finished:
            continue
        return ("SEMANTIC_M7", str(row["ai_task_id"]), str(row["ai_round_id"]))
    return None


@contextmanager
def attempt_governance(
    *,
    operation: str | None = None,
    ai_task_id: str | None = None,
    ai_round_id: str | None = None,
) -> Iterator[None]:
    parent = _ATTEMPT_GOVERNANCE.get()
    token = _ATTEMPT_GOVERNANCE.set(
        (
            operation if operation is not None else (parent[0] if parent else None),
            ai_task_id if ai_task_id is not None else (parent[1] if parent else None),
            ai_round_id if ai_round_id is not None else (parent[2] if parent else None),
        )
    )
    try:
        yield
    finally:
        _ATTEMPT_GOVERNANCE.reset(token)


def _dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _resolve_session_status(
    *,
    strategy: str,
    enabled: bool,
    configured: bool,
    audit_mode: str,
    provider_states: dict[str, str],
) -> tuple[str, bool]:
    """Resolve operational AI status without conflating selection, configuration and failure."""

    chain_exhausted = (
        strategy == "AUTO"
        and configured
        and bool(provider_states)
        and all(value == "QUARANTINED_FOR_AUDIT" for value in provider_states.values())
    )
    if strategy == "NONE" or not enabled:
        return "DISABLED", chain_exhausted
    if not configured:
        return "NOT_CONFIGURED", chain_exhausted
    if chain_exhausted:
        return "CHAIN_EXHAUSTED", chain_exhausted
    if audit_mode == "FULL":
        return "SUCCESS", chain_exhausted
    return "DEGRADED", chain_exhausted


@dataclass(frozen=True, slots=True)
class AiAuditSession:
    audit_id: str
    strategy: str
    enabled: bool
    initial_provider: str | None
    initial_model: str | None
    initial_reasoning_profile: str | None
    configured_chain: tuple[dict[str, Any], ...]
    excluded_configurations: tuple[str, ...] = ()
    effective_provider: str | None = None
    effective_model: str | None = None
    effective_reasoning_profile: str | None = None
    status: str = "PENDING"
    provider_states: dict[str, str] | None = None
    successful_urls: dict[str, int] | None = None


class M18Persistence:
    def __init__(self, workspace: AuditWorkspace) -> None:
        self._connection = sqlite3.connect(workspace.database)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._initialize()

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> "M18Persistence":
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()

    def _initialize(self) -> None:
        with self._connection:
            self._connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS ai_audit_sessions (
                    audit_id TEXT PRIMARY KEY REFERENCES audits(audit_id) ON DELETE CASCADE,
                    strategy TEXT NOT NULL,
                    enabled INTEGER NOT NULL,
                    initial_provider TEXT,
                    initial_model TEXT,
                    initial_reasoning_profile TEXT,
                    configured_chain TEXT NOT NULL,
                    excluded_configurations TEXT NOT NULL,
                    effective_provider TEXT,
                    effective_model TEXT,
                    effective_reasoning_profile TEXT,
                    status TEXT NOT NULL,
                    provider_states TEXT NOT NULL,
                    successful_urls TEXT NOT NULL,
                    qualification_version TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS ai_provider_attempts (
                    attempt_id TEXT PRIMARY KEY,
                    audit_id TEXT NOT NULL REFERENCES audits(audit_id) ON DELETE CASCADE,
                    page_id TEXT REFERENCES pages(page_id) ON DELETE CASCADE,
                    snapshot_id TEXT REFERENCES page_snapshots(snapshot_id) ON DELETE CASCADE,
                    url TEXT NOT NULL,
                    device TEXT,
                    provider TEXT NOT NULL,
                    model TEXT,
                    reasoning_profile TEXT NOT NULL,
                    provider_rank INTEGER NOT NULL,
                    attempt_index INTEGER NOT NULL,
                    started_at TEXT NOT NULL,
                    finished_at TEXT NOT NULL,
                    duration_ms INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    http_status INTEGER,
                    error_class TEXT,
                    error_type TEXT,
                    error_code TEXT,
                    request_id TEXT,
                    input_tokens INTEGER,
                    cached_input_tokens INTEGER,
                    output_tokens INTEGER,
                    reasoning_tokens INTEGER,
                    total_tokens INTEGER,
                    estimated_cost REAL,
                    cost_currency TEXT,
                    pricing_version TEXT,
                    request_message_summary TEXT NOT NULL,
                    request_payload_hash TEXT,
                    semantic_contract_version TEXT NOT NULL,
                    operation TEXT,
                    ai_task_id TEXT,
                    ai_round_id TEXT,
                    provider_qualification TEXT,
                    provider_reliability_score REAL,
                    qualification_version TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_ai_attempts_audit
                    ON ai_provider_attempts(audit_id, started_at);
                CREATE INDEX IF NOT EXISTS idx_ai_attempts_snapshot
                    ON ai_provider_attempts(snapshot_id, attempt_index);
                CREATE INDEX IF NOT EXISTS idx_ai_attempts_provider
                    ON ai_provider_attempts(audit_id, provider, status);

                CREATE TABLE IF NOT EXISTS provider_pricing_catalog (
                    provider TEXT NOT NULL,
                    model TEXT NOT NULL,
                    effective_from TEXT NOT NULL,
                    pricing_context TEXT NOT NULL,
                    input_price_per_million REAL NOT NULL,
                    cached_input_price_per_million REAL NOT NULL,
                    output_price_per_million REAL NOT NULL,
                    currency TEXT NOT NULL,
                    source_reference TEXT NOT NULL,
                    pricing_version TEXT NOT NULL,
                    PRIMARY KEY(provider, model, pricing_version, pricing_context)
                );
                """
            )
            existing_attempt_columns = {
                str(row['name']) for row in self._connection.execute('PRAGMA table_info(ai_provider_attempts)').fetchall()
            }
            for column, ddl in (
                ('retry_eligible', 'INTEGER NOT NULL DEFAULT 0'),
                ('retry_after_seconds', 'REAL'),
                ('decision', "TEXT NOT NULL DEFAULT 'STOP'"),
                ('fallback_from_provider', 'TEXT'),
                ('fallback_reason', 'TEXT'),
                ('operation', 'TEXT'),
                ('ai_task_id', 'TEXT'),
                ('ai_round_id', 'TEXT'),
            ):
                if column not in existing_attempt_columns:
                    self._connection.execute(f'ALTER TABLE ai_provider_attempts ADD COLUMN {column} {ddl}')
            for item in PRICING_CATALOG:
                self._connection.execute(
                    """
                    INSERT OR REPLACE INTO provider_pricing_catalog (
                        provider, model, effective_from, pricing_context,
                        input_price_per_million, cached_input_price_per_million,
                        output_price_per_million, currency, source_reference, pricing_version
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        item.provider,
                        item.model,
                        item.effective_from,
                        item.pricing_context,
                        item.input_price_per_million,
                        item.cached_input_price_per_million,
                        item.output_price_per_million,
                        item.currency,
                        item.source_reference,
                        item.pricing_version,
                    ),
                )

    def upsert_session(self, session: AiAuditSession) -> None:
        from rasai.m18_ai import QUALIFICATION_VERSION

        with self._connection:
            self._connection.execute(
                """
                INSERT INTO ai_audit_sessions (
                    audit_id,strategy,enabled,initial_provider,initial_model,
                    initial_reasoning_profile,configured_chain,excluded_configurations,
                    effective_provider,effective_model,effective_reasoning_profile,status,
                    provider_states,successful_urls,qualification_version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(audit_id) DO UPDATE SET
                    strategy=excluded.strategy,
                    enabled=excluded.enabled,
                    initial_provider=excluded.initial_provider,
                    initial_model=excluded.initial_model,
                    initial_reasoning_profile=excluded.initial_reasoning_profile,
                    configured_chain=excluded.configured_chain,
                    excluded_configurations=excluded.excluded_configurations,
                    effective_provider=excluded.effective_provider,
                    effective_model=excluded.effective_model,
                    effective_reasoning_profile=excluded.effective_reasoning_profile,
                    status=excluded.status,
                    provider_states=excluded.provider_states,
                    successful_urls=excluded.successful_urls,
                    qualification_version=excluded.qualification_version
                """,
                (
                    session.audit_id,
                    session.strategy,
                    1 if session.enabled else 0,
                    session.initial_provider,
                    session.initial_model,
                    session.initial_reasoning_profile,
                    _dump(list(session.configured_chain)),
                    _dump(list(session.excluded_configurations)),
                    session.effective_provider,
                    session.effective_model,
                    session.effective_reasoning_profile,
                    session.status,
                    _dump(session.provider_states or {}),
                    _dump(session.successful_urls or {}),
                    QUALIFICATION_VERSION,
                ),
            )

    def add_attempt(
        self,
        *,
        attempt_id: str,
        audit_id: str,
        page_id: str | None,
        snapshot_id: str | None,
        url: str,
        device: str | None,
        attempt: ProviderAttempt,
        operation: str | None = None,
        ai_task_id: str | None = None,
        ai_round_id: str | None = None,
    ) -> None:
        governance = _ATTEMPT_GOVERNANCE.get()
        if governance is not None:
            inherited_operation, inherited_task_id, inherited_round_id = governance
            operation = operation or inherited_operation
            ai_task_id = ai_task_id or inherited_task_id
            ai_round_id = ai_round_id or inherited_round_id
        diagnostic = attempt.diagnostic
        usage = attempt.usage
        columns = (
            "attempt_id", "audit_id", "page_id", "snapshot_id", "url", "device", "provider", "model",
            "reasoning_profile", "provider_rank", "attempt_index", "started_at", "finished_at", "duration_ms",
            "status", "http_status", "error_class", "error_type", "error_code", "request_id",
            "retry_eligible", "retry_after_seconds", "decision", "fallback_from_provider", "fallback_reason",
            "input_tokens", "cached_input_tokens", "output_tokens", "reasoning_tokens", "total_tokens",
            "estimated_cost", "cost_currency", "pricing_version", "request_message_summary", "request_payload_hash",
            "semantic_contract_version", "operation", "ai_task_id", "ai_round_id",
            "provider_qualification", "provider_reliability_score", "qualification_version",
        )
        values = (
            attempt_id, audit_id, page_id, snapshot_id, url, device, attempt.provider, attempt.model,
            attempt.reasoning_profile, attempt.provider_rank, attempt.attempt_index,
            attempt.started_at.isoformat(), attempt.finished_at.isoformat(), attempt.duration_ms, attempt.status.value,
            diagnostic.http_status if diagnostic else None,
            diagnostic.error_class.value if diagnostic and diagnostic.error_class else None,
            diagnostic.error_type if diagnostic else None,
            diagnostic.error_code if diagnostic else None,
            diagnostic.request_id if diagnostic else None,
            1 if attempt.retry_eligible else 0,
            diagnostic.retry_after_seconds if diagnostic else None,
            attempt.decision,
            attempt.fallback_from_provider,
            attempt.fallback_reason,
            usage.input_tokens if usage else None,
            usage.cached_input_tokens if usage else None,
            usage.output_tokens if usage else None,
            usage.reasoning_tokens if usage else None,
            usage.total_tokens if usage else None,
            attempt.estimated_cost,
            attempt.cost_currency,
            attempt.pricing_version,
            attempt.request_message_summary[:512],
            attempt.request_payload_hash,
            attempt.semantic_contract_version,
            operation,
            ai_task_id,
            ai_round_id,
            attempt.provider_qualification,
            attempt.provider_reliability_score,
            attempt.qualification_version,
        )
        placeholders = ",".join("?" for _ in columns)
        with self._connection:
            self._connection.execute(
                f"INSERT INTO ai_provider_attempts ({','.join(columns)}) VALUES ({placeholders})",
                values,
            )

    def list_attempts(self, audit_id: str) -> tuple[sqlite3.Row, ...]:
        return tuple(
            self._connection.execute(
                "SELECT * FROM ai_provider_attempts WHERE audit_id=? ORDER BY started_at,attempt_index,attempt_id",
                (audit_id,),
            ).fetchall()
        )

    def get_session(self, audit_id: str) -> sqlite3.Row | None:
        return self._connection.execute(
            "SELECT * FROM ai_audit_sessions WHERE audit_id=?", (audit_id,)
        ).fetchone()


def persist_provider_runtime(*, audit_id: str, provider: Any, workspace: AuditWorkspace, audit_mode: str) -> AiAuditSession:
    """Materialize one audit's in-memory provider telemetry after the semantic stage completes."""

    from rasai.domain import new_id
    from rasai.m18_ai import provider_attempt_history, provider_session_snapshot

    snapshot = provider_session_snapshot(provider)
    history = provider_attempt_history(provider)
    with M18Persistence(workspace) as store:
        for attempt in history:
            row = store._connection.execute(
                """
                SELECT ps.page_id, ps.device, p.normalized_url
                FROM page_snapshots ps JOIN pages p ON p.page_id=ps.page_id
                WHERE ps.snapshot_id=? AND p.audit_id=?
                """,
                (attempt.snapshot_id, audit_id),
            ).fetchone()
            if row is None:
                continue
            governance = _consume_attempt_governance(attempt)
            if governance is None:
                governance = _durable_semantic_governance(
                    store,
                    audit_id=audit_id,
                    attempt=attempt,
                )
            store.add_attempt(
                attempt_id=new_id("AIA"),
                audit_id=audit_id,
                page_id=str(row["page_id"]),
                snapshot_id=attempt.snapshot_id,
                url=str(row["normalized_url"]),
                device=str(row["device"]),
                attempt=attempt,
                operation=governance[0] if governance else None,
                ai_task_id=governance[1] if governance else None,
                ai_round_id=governance[2] if governance else None,
            )
            diagnostic = attempt.diagnostic
            usage = attempt.usage
            _LOGGER.info(
                "AI attempt audit_id=%s url=%s device=%s provider=%s model=%s depth=%s status=%s duration_ms=%s input_tokens=%s cached_input_tokens=%s output_tokens=%s reasoning_tokens=%s estimated_cost=%s currency=%s error_class=%s",
                audit_id,
                str(row["normalized_url"]),
                str(row["device"]),
                attempt.provider,
                attempt.model,
                attempt.reasoning_profile,
                attempt.status.value,
                attempt.duration_ms,
                usage.input_tokens if usage else None,
                usage.cached_input_tokens if usage else None,
                usage.output_tokens if usage else None,
                usage.reasoning_tokens if usage else None,
                attempt.estimated_cost,
                attempt.cost_currency,
                diagnostic.error_class.value if diagnostic and diagnostic.error_class else None,
            )

        successes = [item for item in history if item.status.value == "SUCCESS"]
        strategy = str(snapshot.get("strategy") or "NONE")
        states = dict(snapshot.get("provider_states") or {})
        enabled = strategy != "NONE"
        if strategy == "SINGLE_PROVIDER":
            configured = bool(getattr(provider, "api_key", None))
        elif strategy == "AUTO":
            configured = bool(snapshot.get("configured_chain"))
        else:
            configured = False
        status, chain_exhausted = _resolve_session_status(
            strategy=strategy,
            enabled=enabled,
            configured=configured,
            audit_mode=audit_mode,
            provider_states=states,
        )

        effective_provider = snapshot.get("effective_provider")
        effective_model = snapshot.get("effective_model")
        effective_reasoning = snapshot.get("effective_reasoning_profile")
        if strategy == "SINGLE_PROVIDER" and successes:
            effective_provider = successes[-1].provider
            effective_model = successes[-1].model
            effective_reasoning = successes[-1].reasoning_profile

        session = AiAuditSession(
            audit_id=audit_id,
            strategy=strategy,
            enabled=enabled,
            initial_provider=snapshot.get("initial_provider"),
            initial_model=snapshot.get("initial_model"),
            initial_reasoning_profile=snapshot.get("initial_reasoning_profile"),
            configured_chain=tuple(snapshot.get("configured_chain") or ()),
            excluded_configurations=tuple(snapshot.get("excluded_configurations") or ()),
            effective_provider=effective_provider,
            effective_model=effective_model,
            effective_reasoning_profile=effective_reasoning,
            status=status,
            provider_states=states,
            successful_urls=dict(snapshot.get("successful_urls") or {}),
        )
        store.upsert_session(session)
        _LOGGER.info(
            "AI session audit_id=%s strategy=%s enabled=%s configured=%s status=%s effective_provider=%s effective_model=%s attempts=%s successful_attempts=%s",
            audit_id,
            session.strategy,
            session.enabled,
            configured,
            session.status,
            session.effective_provider,
            session.effective_model,
            len(history),
            len(successes),
        )

        if chain_exhausted:
            audit_row = store._connection.execute(
                "SELECT limitations FROM audits WHERE audit_id=?", (audit_id,)
            ).fetchone()
            if audit_row is not None:
                try:
                    limitations = json.loads(str(audit_row["limitations"]))
                except (TypeError, ValueError, json.JSONDecodeError):
                    limitations = []
                if "AI_PROVIDER_CHAIN_EXHAUSTED" not in limitations:
                    limitations.append("AI_PROVIDER_CHAIN_EXHAUSTED")
                    with store._connection:
                        store._connection.execute(
                            "UPDATE audits SET limitations=? WHERE audit_id=?",
                            (_dump(limitations), audit_id),
                        )
        return session
