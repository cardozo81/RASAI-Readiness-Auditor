"""SQLite persistence for M20 content and JSON-LD suggestions."""

from __future__ import annotations

from dataclasses import dataclass
import json
import sqlite3
from typing import Any

from rasai.m18_ai import ProviderAttempt
from rasai.persistence import AuditWorkspace


def _dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


@dataclass(frozen=True, slots=True)
class ContentRemediationRun:
    audit_id: str
    enabled: bool
    strategy: str
    status: str
    eligible_findings: int
    attempted_contexts: int
    generated_suggestions: int
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class PersistedContentSuggestion:
    suggestion_id: str
    audit_id: str
    finding_id: str
    page_id: str
    snapshot_id: str
    device: str
    provider: str
    model: str | None
    objective: str
    target_location: str
    proposed_text: str
    evidence_ids: tuple[str, ...]
    confidence: float
    review_note: str
    created_at: str


@dataclass(frozen=True, slots=True)
class PersistedJsonLdSuggestion:
    suggestion_id: str
    audit_id: str
    page_id: str
    snapshot_id: str
    device: str
    status: str
    existing_types: tuple[str, ...]
    proposed_json: Any | None
    improvements: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    created_at: str


class M20Persistence:
    def __init__(self, workspace: AuditWorkspace) -> None:
        self._connection = sqlite3.connect(workspace.database)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._initialize()

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> "M20Persistence":
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()

    def _initialize(self) -> None:
        with self._connection:
            self._connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS content_remediation_runs (
                    audit_id TEXT PRIMARY KEY REFERENCES audits(audit_id) ON DELETE CASCADE,
                    enabled INTEGER NOT NULL,
                    strategy TEXT NOT NULL,
                    status TEXT NOT NULL,
                    eligible_findings INTEGER NOT NULL,
                    attempted_contexts INTEGER NOT NULL,
                    generated_suggestions INTEGER NOT NULL,
                    reason TEXT
                );

                CREATE TABLE IF NOT EXISTS content_remediation_suggestions (
                    suggestion_id TEXT PRIMARY KEY,
                    audit_id TEXT NOT NULL REFERENCES audits(audit_id) ON DELETE CASCADE,
                    finding_id TEXT NOT NULL REFERENCES findings(finding_id) ON DELETE CASCADE,
                    page_id TEXT NOT NULL REFERENCES pages(page_id) ON DELETE CASCADE,
                    snapshot_id TEXT NOT NULL REFERENCES page_snapshots(snapshot_id) ON DELETE CASCADE,
                    device TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    model TEXT,
                    objective TEXT NOT NULL,
                    target_location TEXT NOT NULL,
                    proposed_text TEXT NOT NULL,
                    evidence_ids TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    review_note TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(audit_id, finding_id, snapshot_id)
                );

                CREATE TABLE IF NOT EXISTS content_remediation_attempts (
                    attempt_id TEXT PRIMARY KEY,
                    audit_id TEXT NOT NULL REFERENCES audits(audit_id) ON DELETE CASCADE,
                    page_id TEXT NOT NULL REFERENCES pages(page_id) ON DELETE CASCADE,
                    snapshot_id TEXT NOT NULL REFERENCES page_snapshots(snapshot_id) ON DELETE CASCADE,
                    device TEXT NOT NULL,
                    url TEXT NOT NULL,
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
                    contract_version TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS jsonld_remediation_suggestions (
                    suggestion_id TEXT PRIMARY KEY,
                    audit_id TEXT NOT NULL REFERENCES audits(audit_id) ON DELETE CASCADE,
                    page_id TEXT NOT NULL REFERENCES pages(page_id) ON DELETE CASCADE,
                    snapshot_id TEXT NOT NULL REFERENCES page_snapshots(snapshot_id) ON DELETE CASCADE,
                    device TEXT NOT NULL,
                    status TEXT NOT NULL,
                    existing_types TEXT NOT NULL,
                    proposed_json TEXT,
                    improvements TEXT NOT NULL,
                    evidence_ids TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(audit_id, snapshot_id)
                );

                CREATE INDEX IF NOT EXISTS idx_m20_suggestions_audit
                    ON content_remediation_suggestions(audit_id,page_id,device);
                CREATE INDEX IF NOT EXISTS idx_m20_attempts_audit
                    ON content_remediation_attempts(audit_id,started_at,attempt_index);
                CREATE INDEX IF NOT EXISTS idx_m20_jsonld_audit
                    ON jsonld_remediation_suggestions(audit_id,page_id,device);
                """
            )

    def upsert_run(self, run: ContentRemediationRun) -> None:
        with self._connection:
            self._connection.execute(
                """
                INSERT INTO content_remediation_runs VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(audit_id) DO UPDATE SET
                    enabled=excluded.enabled,
                    strategy=excluded.strategy,
                    status=excluded.status,
                    eligible_findings=excluded.eligible_findings,
                    attempted_contexts=excluded.attempted_contexts,
                    generated_suggestions=excluded.generated_suggestions,
                    reason=excluded.reason
                """,
                (
                    run.audit_id,
                    1 if run.enabled else 0,
                    run.strategy,
                    run.status,
                    run.eligible_findings,
                    run.attempted_contexts,
                    run.generated_suggestions,
                    run.reason,
                ),
            )

    def add_suggestion(self, item: PersistedContentSuggestion) -> None:
        with self._connection:
            self._connection.execute(
                """
                INSERT OR REPLACE INTO content_remediation_suggestions VALUES (
                    ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?
                )
                """,
                (
                    item.suggestion_id,
                    item.audit_id,
                    item.finding_id,
                    item.page_id,
                    item.snapshot_id,
                    item.device,
                    item.provider,
                    item.model,
                    item.objective,
                    item.target_location,
                    item.proposed_text,
                    _dump(list(item.evidence_ids)),
                    item.confidence,
                    item.review_note,
                    item.created_at,
                ),
            )

    def add_attempt(
        self,
        *,
        attempt_id: str,
        audit_id: str,
        page_id: str,
        snapshot_id: str,
        device: str,
        url: str,
        attempt: ProviderAttempt,
    ) -> None:
        diagnostic = attempt.diagnostic
        usage = attempt.usage
        with self._connection:
            self._connection.execute(
                """
                INSERT INTO content_remediation_attempts VALUES (
                    ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?
                )
                """,
                (
                    attempt_id,
                    audit_id,
                    page_id,
                    snapshot_id,
                    device,
                    url,
                    attempt.provider,
                    attempt.model,
                    attempt.reasoning_profile,
                    attempt.provider_rank,
                    attempt.attempt_index,
                    attempt.started_at.isoformat(),
                    attempt.finished_at.isoformat(),
                    attempt.duration_ms,
                    attempt.status.value,
                    diagnostic.http_status if diagnostic else None,
                    diagnostic.error_class.value if diagnostic and diagnostic.error_class else None,
                    diagnostic.error_type if diagnostic else None,
                    diagnostic.error_code if diagnostic else None,
                    diagnostic.request_id if diagnostic else None,
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
                ),
            )

    def add_jsonld(self, item: PersistedJsonLdSuggestion) -> None:
        with self._connection:
            self._connection.execute(
                """
                INSERT OR REPLACE INTO jsonld_remediation_suggestions VALUES (
                    ?,?,?,?,?,?,?,?,?,?,?
                )
                """,
                (
                    item.suggestion_id,
                    item.audit_id,
                    item.page_id,
                    item.snapshot_id,
                    item.device,
                    item.status,
                    _dump(list(item.existing_types)),
                    _dump(item.proposed_json) if item.proposed_json is not None else None,
                    _dump(list(item.improvements)),
                    _dump(list(item.evidence_ids)),
                    item.created_at,
                ),
            )
