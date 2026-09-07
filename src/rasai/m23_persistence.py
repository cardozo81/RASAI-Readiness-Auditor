"""Persistência do M23: Synthetic Apdex e rastreabilidade Lighthouse."""
from __future__ import annotations

from dataclasses import dataclass
import json
import sqlite3
from typing import Any

from rasai.persistence import AuditWorkspace


def _dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


@dataclass(frozen=True, slots=True)
class SyntheticApdexRun:
    audit_id: str
    enabled: bool
    status: str
    task_id: str
    threshold_seconds: float | None
    frustration_seconds: float | None
    target_valid_samples: int
    max_attempts_per_context: int
    page_limit: int
    pages_considered: int
    contexts_considered: int
    attempted_samples: int
    valid_samples: int
    invalid_samples: int
    delay_seconds: float
    concurrency: int
    configuration: dict[str, Any]
    host_environment: dict[str, Any]
    reason: str | None
    updated_at: str


@dataclass(frozen=True, slots=True)
class SyntheticApdexSample:
    sample_id: str
    audit_id: str
    page_id: str
    snapshot_id: str
    device: str
    url: str
    run_index: int
    task_id: str
    profile_id: str
    profile_version: str
    status: str
    classification: str | None
    duration_ms: int | None
    http_status: int | None
    final_url: str | None
    error_code: str | None
    error_message: str | None
    cpu_method: str | None
    network_method: str | None
    cache_policy: str
    captured_at: str


@dataclass(frozen=True, slots=True)
class SyntheticApdexSummary:
    summary_id: str
    audit_id: str
    page_id: str
    device: str
    url: str
    task_id: str
    profile_id: str
    threshold_seconds: float
    frustration_seconds: float
    valid_samples: int
    invalid_samples: int
    satisfied_count: int
    tolerating_count: int
    frustrated_count: int
    success_count: int
    application_error_count: int
    timeout_count: int
    navigation_error_count: int
    apdex_score: float | None
    small_group: bool
    final_group: bool
    min_ms: float | None
    max_ms: float | None
    mean_ms: float | None
    median_ms: float | None
    stddev_ms: float | None
    coefficient_of_variation: float | None
    p75_ms: float | None
    p90_ms: float | None
    p95_ms: float | None
    p99_ms: float | None
    first_half_mean_ms: float | None
    second_half_mean_ms: float | None
    trend_percent: float | None
    calculated_at: str


@dataclass(frozen=True, slots=True)
class LighthouseExecutionProfile:
    observation_id: str
    audit_id: str
    device: str
    url: str
    form_factor: str | None
    throttling_method: str | None
    rtt_ms: float | None
    throughput_kbps: float | None
    request_latency_ms: float | None
    download_throughput_kbps: float | None
    upload_throughput_kbps: float | None
    cpu_slowdown_multiplier: float | None
    screen_mobile: bool | None
    screen_width: int | None
    screen_height: int | None
    device_scale_factor: float | None
    screen_disabled: bool | None
    emulated_user_agent: str | None
    host_user_agent: str | None
    network_user_agent: str | None
    benchmark_index: float | None
    lighthouse_total_ms: float | None
    collection_period_start: str | None
    collection_period_end: str | None
    raw_config: dict[str, Any]
    captured_at: str


class M23Persistence:
    def __init__(self, workspace: AuditWorkspace) -> None:
        self.connection = sqlite3.connect(workspace.database)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self._initialize()

    def __enter__(self) -> "M23Persistence":
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()

    def close(self) -> None:
        self.connection.close()

    def _initialize(self) -> None:
        with self.connection:
            self.connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS synthetic_apdex_runs (
                    audit_id TEXT PRIMARY KEY REFERENCES audits(audit_id) ON DELETE CASCADE,
                    enabled INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    task_id TEXT NOT NULL,
                    threshold_seconds REAL,
                    frustration_seconds REAL,
                    target_valid_samples INTEGER NOT NULL,
                    max_attempts_per_context INTEGER NOT NULL,
                    page_limit INTEGER NOT NULL,
                    pages_considered INTEGER NOT NULL,
                    contexts_considered INTEGER NOT NULL,
                    attempted_samples INTEGER NOT NULL,
                    valid_samples INTEGER NOT NULL,
                    invalid_samples INTEGER NOT NULL,
                    delay_seconds REAL NOT NULL,
                    concurrency INTEGER NOT NULL,
                    configuration TEXT NOT NULL,
                    host_environment TEXT NOT NULL,
                    reason TEXT,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS synthetic_apdex_samples (
                    sample_id TEXT PRIMARY KEY,
                    audit_id TEXT NOT NULL REFERENCES audits(audit_id) ON DELETE CASCADE,
                    page_id TEXT NOT NULL REFERENCES pages(page_id) ON DELETE CASCADE,
                    snapshot_id TEXT NOT NULL REFERENCES page_snapshots(snapshot_id) ON DELETE CASCADE,
                    device TEXT NOT NULL,
                    url TEXT NOT NULL,
                    run_index INTEGER NOT NULL,
                    task_id TEXT NOT NULL,
                    profile_id TEXT NOT NULL,
                    profile_version TEXT NOT NULL,
                    status TEXT NOT NULL,
                    classification TEXT,
                    duration_ms INTEGER,
                    http_status INTEGER,
                    final_url TEXT,
                    error_code TEXT,
                    error_message TEXT,
                    cpu_method TEXT,
                    network_method TEXT,
                    cache_policy TEXT NOT NULL,
                    captured_at TEXT NOT NULL,
                    UNIQUE(audit_id,snapshot_id,run_index)
                );

                CREATE TABLE IF NOT EXISTS synthetic_apdex_summaries (
                    summary_id TEXT PRIMARY KEY,
                    audit_id TEXT NOT NULL REFERENCES audits(audit_id) ON DELETE CASCADE,
                    page_id TEXT NOT NULL REFERENCES pages(page_id) ON DELETE CASCADE,
                    device TEXT NOT NULL,
                    url TEXT NOT NULL,
                    task_id TEXT NOT NULL,
                    profile_id TEXT NOT NULL,
                    threshold_seconds REAL NOT NULL,
                    frustration_seconds REAL NOT NULL,
                    valid_samples INTEGER NOT NULL,
                    invalid_samples INTEGER NOT NULL,
                    satisfied_count INTEGER NOT NULL,
                    tolerating_count INTEGER NOT NULL,
                    frustrated_count INTEGER NOT NULL,
                    success_count INTEGER NOT NULL,
                    application_error_count INTEGER NOT NULL,
                    timeout_count INTEGER NOT NULL,
                    navigation_error_count INTEGER NOT NULL,
                    apdex_score REAL,
                    small_group INTEGER NOT NULL,
                    final_group INTEGER NOT NULL,
                    min_ms REAL,
                    max_ms REAL,
                    mean_ms REAL,
                    median_ms REAL,
                    stddev_ms REAL,
                    coefficient_of_variation REAL,
                    p75_ms REAL,
                    p90_ms REAL,
                    p95_ms REAL,
                    p99_ms REAL,
                    first_half_mean_ms REAL,
                    second_half_mean_ms REAL,
                    trend_percent REAL,
                    calculated_at TEXT NOT NULL,
                    UNIQUE(audit_id,page_id,device)
                );

                CREATE TABLE IF NOT EXISTS lighthouse_execution_profiles (
                    observation_id TEXT PRIMARY KEY REFERENCES web_performance_observations(observation_id) ON DELETE CASCADE,
                    audit_id TEXT NOT NULL REFERENCES audits(audit_id) ON DELETE CASCADE,
                    device TEXT NOT NULL,
                    url TEXT NOT NULL,
                    form_factor TEXT,
                    throttling_method TEXT,
                    rtt_ms REAL,
                    throughput_kbps REAL,
                    request_latency_ms REAL,
                    download_throughput_kbps REAL,
                    upload_throughput_kbps REAL,
                    cpu_slowdown_multiplier REAL,
                    screen_mobile INTEGER,
                    screen_width INTEGER,
                    screen_height INTEGER,
                    device_scale_factor REAL,
                    screen_disabled INTEGER,
                    emulated_user_agent TEXT,
                    host_user_agent TEXT,
                    network_user_agent TEXT,
                    benchmark_index REAL,
                    lighthouse_total_ms REAL,
                    collection_period_start TEXT,
                    collection_period_end TEXT,
                    raw_config TEXT NOT NULL,
                    captured_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_apdex_samples_audit
                    ON synthetic_apdex_samples(audit_id,page_id,device,run_index);
                CREATE INDEX IF NOT EXISTS idx_apdex_summaries_audit
                    ON synthetic_apdex_summaries(audit_id,page_id,device);
                CREATE INDEX IF NOT EXISTS idx_lighthouse_profiles_audit
                    ON lighthouse_execution_profiles(audit_id,device);
                """
            )

    def upsert_run(self, item: SyntheticApdexRun) -> None:
        with self.connection:
            self.connection.execute(
                "INSERT OR REPLACE INTO synthetic_apdex_runs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    item.audit_id, int(item.enabled), item.status, item.task_id,
                    item.threshold_seconds, item.frustration_seconds,
                    item.target_valid_samples, item.max_attempts_per_context,
                    item.page_limit, item.pages_considered, item.contexts_considered,
                    item.attempted_samples, item.valid_samples, item.invalid_samples,
                    item.delay_seconds, item.concurrency, _dump(item.configuration),
                    _dump(item.host_environment), item.reason, item.updated_at,
                ),
            )

    def add_sample(self, item: SyntheticApdexSample) -> None:
        with self.connection:
            self.connection.execute(
                "INSERT OR REPLACE INTO synthetic_apdex_samples VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    item.sample_id, item.audit_id, item.page_id, item.snapshot_id,
                    item.device, item.url, item.run_index, item.task_id, item.profile_id,
                    item.profile_version, item.status, item.classification, item.duration_ms,
                    item.http_status, item.final_url, item.error_code, item.error_message,
                    item.cpu_method, item.network_method, item.cache_policy, item.captured_at,
                ),
            )

    def upsert_summary(self, item: SyntheticApdexSummary) -> None:
        values = (
            item.summary_id, item.audit_id, item.page_id, item.device, item.url,
            item.task_id, item.profile_id, item.threshold_seconds, item.frustration_seconds,
            item.valid_samples, item.invalid_samples, item.satisfied_count,
            item.tolerating_count, item.frustrated_count, item.success_count,
            item.application_error_count, item.timeout_count, item.navigation_error_count,
            item.apdex_score, int(item.small_group), int(item.final_group), item.min_ms,
            item.max_ms, item.mean_ms, item.median_ms, item.stddev_ms,
            item.coefficient_of_variation, item.p75_ms, item.p90_ms, item.p95_ms,
            item.p99_ms, item.first_half_mean_ms, item.second_half_mean_ms,
            item.trend_percent, item.calculated_at,
        )
        with self.connection:
            self.connection.execute(
                "INSERT OR REPLACE INTO synthetic_apdex_summaries VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                values,
            )

    def upsert_lighthouse_profile(self, item: LighthouseExecutionProfile) -> None:
        values = (
            item.observation_id, item.audit_id, item.device, item.url, item.form_factor,
            item.throttling_method, item.rtt_ms, item.throughput_kbps,
            item.request_latency_ms, item.download_throughput_kbps,
            item.upload_throughput_kbps, item.cpu_slowdown_multiplier,
            None if item.screen_mobile is None else int(item.screen_mobile),
            item.screen_width, item.screen_height, item.device_scale_factor,
            None if item.screen_disabled is None else int(item.screen_disabled),
            item.emulated_user_agent, item.host_user_agent, item.network_user_agent,
            item.benchmark_index, item.lighthouse_total_ms,
            item.collection_period_start, item.collection_period_end,
            _dump(item.raw_config), item.captured_at,
        )
        with self.connection:
            self.connection.execute(
                "INSERT OR REPLACE INTO lighthouse_execution_profiles VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                values,
            )
