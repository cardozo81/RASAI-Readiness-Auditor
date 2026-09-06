"""Persistência aditiva do M25 — Synthetic User Experience Apdex.

As tabelas M25 são deliberadamente separadas das tabelas M23. O M23 continua
sendo a fonte de verdade do Synthetic Navigation Apdex normativo T/4T; M25
armazena uma medição sintética calibrável e nunca reescreve resultados M23.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import sqlite3
from typing import Any

from searchgeo.persistence import AuditWorkspace


def _dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


@dataclass(frozen=True, slots=True)
class SyntheticUxRun:
    audit_id: str
    enabled: bool
    status: str
    task_id: str
    target_samples_per_page: int
    max_attempts_per_page: int
    page_limit: int
    pages_considered: int
    attempted_samples: int
    valid_samples: int
    invalid_samples: int
    device_mix: dict[str, float]
    session_mode: str
    kpm: str
    satisfied_threshold_seconds: float
    frustrated_threshold_seconds: float
    errors_affect_apdex: bool
    error_scope: str
    settle_seconds: float
    calibration_source: str
    dynatrace_application_id: str | None
    calibration_metadata: dict[str, Any]
    configuration: dict[str, Any]
    host_environment: dict[str, Any]
    reason: str | None
    updated_at: str


@dataclass(frozen=True, slots=True)
class SyntheticUxSample:
    sample_id: str
    audit_id: str
    page_id: str
    url: str
    device: str
    run_index: int
    task_id: str
    profile_id: str
    session_mode: str
    status: str
    classification: str | None
    kpm: str
    kpm_value_ms: float | None
    user_action_duration_ms: float | None
    navigation_duration_ms: float | None
    response_start_ms: float | None
    response_end_ms: float | None
    dom_interactive_ms: float | None
    load_event_start_ms: float | None
    load_event_end_ms: float | None
    lcp_ms: float | None
    cls: float | None
    http_status: int | None
    final_url: str | None
    xhr_fetch_count: int
    dynamic_resource_count: int
    javascript_error_count: int
    console_error_count: int
    request_failed_count: int
    first_party_request_failed_count: int
    http_error_count: int
    first_party_http_error_count: int
    network_settled: bool
    error_forced_frustrated: bool
    error_code: str | None
    error_message: str | None
    cpu_method: str | None
    network_method: str | None
    captured_at: str


@dataclass(frozen=True, slots=True)
class SyntheticUxSummary:
    summary_id: str
    audit_id: str
    page_id: str
    url: str
    device: str
    task_id: str
    profile_id: str
    target_samples: int
    valid_samples: int
    invalid_samples: int
    satisfied_count: int
    tolerating_count: int
    frustrated_count: int
    error_forced_frustrated_count: int
    apdex_score: float | None
    small_group: bool
    final_group: bool
    mean_ms: float | None
    median_ms: float | None
    p75_ms: float | None
    p90_ms: float | None
    p95_ms: float | None
    p99_ms: float | None
    javascript_error_samples: int
    request_error_samples: int
    network_unsettled_samples: int
    calculated_at: str


class M25Persistence:
    def __init__(self, workspace: AuditWorkspace) -> None:
        self.connection = sqlite3.connect(workspace.database)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self._initialize()

    def __enter__(self) -> "M25Persistence":
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()

    def close(self) -> None:
        self.connection.close()

    def _initialize(self) -> None:
        with self.connection:
            self.connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS synthetic_ux_apdex_runs (
                    audit_id TEXT PRIMARY KEY REFERENCES audits(audit_id) ON DELETE CASCADE,
                    enabled INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    task_id TEXT NOT NULL,
                    target_samples_per_page INTEGER NOT NULL,
                    max_attempts_per_page INTEGER NOT NULL,
                    page_limit INTEGER NOT NULL,
                    pages_considered INTEGER NOT NULL,
                    attempted_samples INTEGER NOT NULL,
                    valid_samples INTEGER NOT NULL,
                    invalid_samples INTEGER NOT NULL,
                    device_mix TEXT NOT NULL,
                    session_mode TEXT NOT NULL,
                    kpm TEXT NOT NULL,
                    satisfied_threshold_seconds REAL NOT NULL,
                    frustrated_threshold_seconds REAL NOT NULL,
                    errors_affect_apdex INTEGER NOT NULL,
                    error_scope TEXT NOT NULL,
                    settle_seconds REAL NOT NULL,
                    calibration_source TEXT NOT NULL,
                    dynatrace_application_id TEXT,
                    calibration_metadata TEXT NOT NULL,
                    configuration TEXT NOT NULL,
                    host_environment TEXT NOT NULL,
                    reason TEXT,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS synthetic_ux_apdex_samples (
                    sample_id TEXT PRIMARY KEY,
                    audit_id TEXT NOT NULL REFERENCES audits(audit_id) ON DELETE CASCADE,
                    page_id TEXT NOT NULL REFERENCES pages(page_id) ON DELETE CASCADE,
                    url TEXT NOT NULL,
                    device TEXT NOT NULL,
                    run_index INTEGER NOT NULL,
                    task_id TEXT NOT NULL,
                    profile_id TEXT NOT NULL,
                    session_mode TEXT NOT NULL,
                    status TEXT NOT NULL,
                    classification TEXT,
                    kpm TEXT NOT NULL,
                    kpm_value_ms REAL,
                    user_action_duration_ms REAL,
                    navigation_duration_ms REAL,
                    response_start_ms REAL,
                    response_end_ms REAL,
                    dom_interactive_ms REAL,
                    load_event_start_ms REAL,
                    load_event_end_ms REAL,
                    lcp_ms REAL,
                    cls REAL,
                    http_status INTEGER,
                    final_url TEXT,
                    xhr_fetch_count INTEGER NOT NULL,
                    dynamic_resource_count INTEGER NOT NULL,
                    javascript_error_count INTEGER NOT NULL,
                    console_error_count INTEGER NOT NULL,
                    request_failed_count INTEGER NOT NULL,
                    first_party_request_failed_count INTEGER NOT NULL,
                    http_error_count INTEGER NOT NULL,
                    first_party_http_error_count INTEGER NOT NULL,
                    network_settled INTEGER NOT NULL,
                    error_forced_frustrated INTEGER NOT NULL,
                    error_code TEXT,
                    error_message TEXT,
                    cpu_method TEXT,
                    network_method TEXT,
                    captured_at TEXT NOT NULL,
                    UNIQUE(audit_id,page_id,device,run_index)
                );

                CREATE TABLE IF NOT EXISTS synthetic_ux_apdex_summaries (
                    summary_id TEXT PRIMARY KEY,
                    audit_id TEXT NOT NULL REFERENCES audits(audit_id) ON DELETE CASCADE,
                    page_id TEXT NOT NULL REFERENCES pages(page_id) ON DELETE CASCADE,
                    url TEXT NOT NULL,
                    device TEXT NOT NULL,
                    task_id TEXT NOT NULL,
                    profile_id TEXT NOT NULL,
                    target_samples INTEGER NOT NULL,
                    valid_samples INTEGER NOT NULL,
                    invalid_samples INTEGER NOT NULL,
                    satisfied_count INTEGER NOT NULL,
                    tolerating_count INTEGER NOT NULL,
                    frustrated_count INTEGER NOT NULL,
                    error_forced_frustrated_count INTEGER NOT NULL,
                    apdex_score REAL,
                    small_group INTEGER NOT NULL,
                    final_group INTEGER NOT NULL,
                    mean_ms REAL,
                    median_ms REAL,
                    p75_ms REAL,
                    p90_ms REAL,
                    p95_ms REAL,
                    p99_ms REAL,
                    javascript_error_samples INTEGER NOT NULL,
                    request_error_samples INTEGER NOT NULL,
                    network_unsettled_samples INTEGER NOT NULL,
                    calculated_at TEXT NOT NULL,
                    UNIQUE(audit_id,page_id,device)
                );

                CREATE INDEX IF NOT EXISTS idx_synthetic_ux_samples_audit
                    ON synthetic_ux_apdex_samples(audit_id,page_id,device,run_index);
                CREATE INDEX IF NOT EXISTS idx_synthetic_ux_summaries_audit
                    ON synthetic_ux_apdex_summaries(audit_id,page_id,device);
                """
            )

    def clear_audit(self, audit_id: str) -> None:
        with self.connection:
            self.connection.execute("DELETE FROM synthetic_ux_apdex_samples WHERE audit_id=?", (audit_id,))
            self.connection.execute("DELETE FROM synthetic_ux_apdex_summaries WHERE audit_id=?", (audit_id,))
            self.connection.execute("DELETE FROM synthetic_ux_apdex_runs WHERE audit_id=?", (audit_id,))

    def upsert_run(self, item: SyntheticUxRun) -> None:
        with self.connection:
            self.connection.execute(
                """
                INSERT OR REPLACE INTO synthetic_ux_apdex_runs (
                    audit_id,enabled,status,task_id,target_samples_per_page,max_attempts_per_page,
                    page_limit,pages_considered,attempted_samples,valid_samples,invalid_samples,
                    device_mix,session_mode,kpm,satisfied_threshold_seconds,frustrated_threshold_seconds,
                    errors_affect_apdex,error_scope,settle_seconds,calibration_source,dynatrace_application_id,
                    calibration_metadata,configuration,host_environment,reason,updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    item.audit_id, int(item.enabled), item.status, item.task_id,
                    item.target_samples_per_page, item.max_attempts_per_page, item.page_limit,
                    item.pages_considered, item.attempted_samples, item.valid_samples,
                    item.invalid_samples, _dump(item.device_mix), item.session_mode, item.kpm,
                    item.satisfied_threshold_seconds, item.frustrated_threshold_seconds,
                    int(item.errors_affect_apdex), item.error_scope, item.settle_seconds,
                    item.calibration_source, item.dynatrace_application_id,
                    _dump(item.calibration_metadata), _dump(item.configuration),
                    _dump(item.host_environment), item.reason, item.updated_at,
                ),
            )

    def add_sample(self, item: SyntheticUxSample) -> None:
        with self.connection:
            self.connection.execute(
                """
                INSERT OR REPLACE INTO synthetic_ux_apdex_samples (
                    sample_id,audit_id,page_id,url,device,run_index,task_id,profile_id,session_mode,
                    status,classification,kpm,kpm_value_ms,user_action_duration_ms,navigation_duration_ms,
                    response_start_ms,response_end_ms,dom_interactive_ms,load_event_start_ms,load_event_end_ms,
                    lcp_ms,cls,http_status,final_url,xhr_fetch_count,dynamic_resource_count,
                    javascript_error_count,console_error_count,request_failed_count,
                    first_party_request_failed_count,http_error_count,first_party_http_error_count,
                    network_settled,error_forced_frustrated,error_code,error_message,cpu_method,
                    network_method,captured_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    item.sample_id, item.audit_id, item.page_id, item.url, item.device,
                    item.run_index, item.task_id, item.profile_id, item.session_mode, item.status,
                    item.classification, item.kpm, item.kpm_value_ms,
                    item.user_action_duration_ms, item.navigation_duration_ms,
                    item.response_start_ms, item.response_end_ms, item.dom_interactive_ms,
                    item.load_event_start_ms, item.load_event_end_ms, item.lcp_ms, item.cls,
                    item.http_status, item.final_url, item.xhr_fetch_count,
                    item.dynamic_resource_count, item.javascript_error_count,
                    item.console_error_count, item.request_failed_count,
                    item.first_party_request_failed_count, item.http_error_count,
                    item.first_party_http_error_count, int(item.network_settled),
                    int(item.error_forced_frustrated), item.error_code, item.error_message,
                    item.cpu_method, item.network_method, item.captured_at,
                ),
            )

    def upsert_summary(self, item: SyntheticUxSummary) -> None:
        with self.connection:
            self.connection.execute(
                """
                INSERT OR REPLACE INTO synthetic_ux_apdex_summaries (
                    summary_id,audit_id,page_id,url,device,task_id,profile_id,target_samples,
                    valid_samples,invalid_samples,satisfied_count,tolerating_count,frustrated_count,
                    error_forced_frustrated_count,apdex_score,small_group,final_group,mean_ms,
                    median_ms,p75_ms,p90_ms,p95_ms,p99_ms,javascript_error_samples,
                    request_error_samples,network_unsettled_samples,calculated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    item.summary_id, item.audit_id, item.page_id, item.url, item.device,
                    item.task_id, item.profile_id, item.target_samples, item.valid_samples,
                    item.invalid_samples, item.satisfied_count, item.tolerating_count,
                    item.frustrated_count, item.error_forced_frustrated_count, item.apdex_score,
                    int(item.small_group), int(item.final_group), item.mean_ms, item.median_ms,
                    item.p75_ms, item.p90_ms, item.p95_ms, item.p99_ms,
                    item.javascript_error_samples, item.request_error_samples,
                    item.network_unsettled_samples, item.calculated_at,
                ),
            )
