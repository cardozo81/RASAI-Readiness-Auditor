"""Data contracts for historical/consolidated reporting.

This package is intentionally independent from the audit execution pipeline.
All source audit databases are treated as immutable evidence and opened read-only.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class ConsolidationFilter:
    domains: tuple[str, ...] = ()
    date_from: date | None = None
    date_to: date | None = None
    devices: tuple[str, ...] = ()
    urls: tuple[str, ...] = ()

    def canonical(self) -> dict[str, Any]:
        return {
            "domains": sorted({item.casefold() for item in self.domains if item}),
            "date_from": self.date_from.isoformat() if self.date_from else None,
            "date_to": self.date_to.isoformat() if self.date_to else None,
            "devices": sorted({item.upper() for item in self.devices if item}),
            "urls": sorted({item for item in self.urls if item}),
        }


@dataclass(frozen=True, slots=True)
class SourceAudit:
    audit_id: str
    db_path: Path
    source_fingerprint: str
    url_set_fingerprint: str
    project_name: str
    status: str
    completion_status: str | None
    created_at: str
    started_at: str | None
    completed_at: str | None
    event_time: str
    auditor_version: str
    ruleset_version: str
    domains: tuple[str, ...]
    devices: tuple[str, ...]
    urls: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RefreshIssue:
    db_path: str
    reason: str


@dataclass(frozen=True, slots=True)
class RefreshResult:
    discovered: int
    indexed: int
    reused: int
    removed: int
    issues: tuple[RefreshIssue, ...] = ()


@dataclass(frozen=True, slots=True)
class GenerationResult:
    report_dir: Path
    report_path: Path
    manifest_path: Path
    reused: bool
    request_fingerprint: str
    refresh: RefreshResult


@dataclass(frozen=True, slots=True)
class NumericSummary:
    count: int
    current: float | None
    initial: float | None
    mean: float | None
    median: float | None
    minimum: float | None
    maximum: float | None
    change_absolute: float | None
    change_percent: float | None


@dataclass(frozen=True, slots=True)
class ScoreSummary:
    device: str
    dimension: str
    scoring_versions: tuple[str, ...]
    url_universes: int
    observations: int
    valid_observations: int
    average_coverage: float | None
    confidence_counts: dict[str, int]
    consolidation_counts: dict[str, int]
    statistics: NumericSummary
    limitation: str | None = None


@dataclass(frozen=True, slots=True)
class MetricSummary:
    name: str
    unit: str
    statistics: NumericSummary


@dataclass(frozen=True, slots=True)
class PerformanceSummary:
    device: str
    observations: int
    urls: int
    metrics: tuple[MetricSummary, ...]
    cwv_counts: dict[str, int]
    source_scopes: dict[str, int]


@dataclass(frozen=True, slots=True)
class ApdexSummary:
    device: str
    profile_ids: tuple[str, ...]
    thresholds: tuple[float, ...]
    observations: int
    urls: int
    valid_samples: int
    invalid_samples: int
    weighted_apdex: float | None
    small_groups: int
    final_groups: int
    duration_metrics: tuple[MetricSummary, ...]
    limitation: str | None = None


@dataclass(frozen=True, slots=True)
class FindingSummary:
    severity_counts: dict[str, int]
    category_counts: dict[str, int]
    affected_pages: int
    observations: int


@dataclass(frozen=True, slots=True)
class ConsolidatedData:
    filters: ConsolidationFilter
    audits: tuple[dict[str, Any], ...]
    source_fingerprint: str
    scores: tuple[ScoreSummary, ...]
    performance: tuple[PerformanceSummary, ...]
    apdex: tuple[ApdexSummary, ...]
    findings: FindingSummary
    unique_urls: int
    date_min: str | None
    date_max: str | None
    limitations: tuple[str, ...] = field(default_factory=tuple)
    # Raw, already-filtered analytical points are retained only inside the
    # consolidation boundary. They support historical charts/explainability and
    # never become a second source of truth: every value originates in AUD-*/audit.db.
    score_history: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    finding_history: tuple[dict[str, Any], ...] = field(default_factory=tuple)
