"""Data contracts for RASAI monitoring.

Monitoring is intentionally derived from immutable AUD workspaces. It does not
write to source audit databases and does not change SARI/SCORE-GEO semantics.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

Direction = Literal["HIGHER_BETTER", "LOWER_BETTER", "STATE", "RESULT"]
ChangeStatus = Literal[
    "NEW",
    "RESOLVED",
    "REGRESSED",
    "IMPROVED",
    "CHANGED",
    "UNCHANGED",
    "DATA_UNAVAILABLE",
    "NOT_COMPARABLE",
]


@dataclass(frozen=True, slots=True)
class Signal:
    key: str
    domain: str
    label: str
    value: Any
    device: str | None = None
    url: str | None = None
    rule_id: str | None = None
    severity: str = "INFO"
    direction: Direction = "STATE"
    unit: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AuditSnapshot:
    audit_id: str
    workspace: Path
    project_name: str
    event_time: str
    status: str
    completion_status: str | None
    auditor_version: str
    ruleset_version: str
    scoring_versions: tuple[str, ...]
    domains: tuple[str, ...]
    devices: tuple[str, ...]
    urls: tuple[str, ...]
    signals: dict[str, Signal]
    limitations: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ChangeEvent:
    key: str
    domain: str
    label: str
    status: ChangeStatus
    before: Any
    after: Any
    severity: str
    material: bool
    device: str | None = None
    url: str | None = None
    rule_id: str | None = None
    unit: str | None = None
    delta: float | None = None
    delta_percent: float | None = None
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class ComparisonResult:
    baseline: AuditSnapshot
    current: AuditSnapshot
    comparable: bool
    compatibility_notes: tuple[str, ...]
    events: tuple[ChangeEvent, ...]
    counts: dict[str, int]
    material_counts: dict[str, int]

    @property
    def regressions(self) -> tuple[ChangeEvent, ...]:
        return tuple(event for event in self.events if event.status == "REGRESSED" and event.material)

    @property
    def improvements(self) -> tuple[ChangeEvent, ...]:
        return tuple(event for event in self.events if event.status in {"IMPROVED", "RESOLVED"} and event.material)


@dataclass(frozen=True, slots=True)
class GatePolicy:
    # Default gate: deterministic BR rules plus deterministic PAGE state only.
    deterministic_only: bool = True
    require_comparable: bool = True
    block_new_failures: bool = True
    include_performance: bool = False
    include_synthetic: bool = False
    include_finding_aggregates: bool = False
    include_score_dimensions: bool = False
    fail_on_critical: bool = True
    max_high_regressions: int = 0
    max_medium_regressions: int = 3
    dimension_drop_points: float = 5.0
    fail_dimensions: tuple[str, ...] = ("TECHNICAL_ACCESSIBILITY", "INDEXABILITY", "CONTENT_EXTRACTABILITY")


@dataclass(frozen=True, slots=True)
class GateResult:
    passed: bool
    blocking_events: tuple[ChangeEvent, ...]
    warnings: tuple[ChangeEvent, ...]
    policy: GatePolicy
    reason: str


@dataclass(frozen=True, slots=True)
class MonitoringReportResult:
    report_dir: Path
    report_path: Path
    manifest_path: Path
