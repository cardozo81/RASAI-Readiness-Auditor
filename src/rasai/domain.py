"""Domain entities required by M1 - Audit + Persistence."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import uuid4


class AuditStatus(StrEnum):
    CREATED = "CREATED"
    INITIALIZING = "INITIALIZING"
    DISCOVERING = "DISCOVERING"
    ACQUIRING = "ACQUIRING"
    ANALYZING = "ANALYZING"
    COMPARING = "COMPARING"
    SCORING = "SCORING"
    RECOMMENDING = "RECOMMENDING"
    REPORTING = "REPORTING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class CompletionStatus(StrEnum):
    COMPLETE = "COMPLETE"
    COMPLETE_WITH_LIMITATIONS = "COMPLETE_WITH_LIMITATIONS"


class TargetType(StrEnum):
    DOMAIN = "DOMAIN"
    URL = "URL"
    URL_SET = "URL_SET"


class AuditMode(StrEnum):
    FULL = "FULL"
    DEGRADED = "DEGRADED"
    NO_AI = "NO_AI"


class DiscoverySource(StrEnum):
    SEED = "SEED"
    SITEMAP = "SITEMAP"
    INTERNAL_LINK = "INTERNAL_LINK"
    REDIRECT = "REDIRECT"
    MANUAL = "MANUAL"


class EvidenceType(StrEnum):
    HTTP_RESPONSE = "HTTP_RESPONSE"
    HTTP_HEADER = "HTTP_HEADER"
    ROBOTS_RULE = "ROBOTS_RULE"
    SITEMAP_ENTRY = "SITEMAP_ENTRY"
    HTML_ELEMENT = "HTML_ELEMENT"
    DOM_ELEMENT = "DOM_ELEMENT"
    VISUAL_SNAPSHOT = "VISUAL_SNAPSHOT"
    META_TAG = "META_TAG"
    CANONICAL = "CANONICAL"
    HEADING = "HEADING"
    LINK = "LINK"
    STRUCTURED_DATA = "STRUCTURED_DATA"
    MAIN_CONTENT = "MAIN_CONTENT"
    TEXT_EXCERPT = "TEXT_EXCERPT"
    AI_ANALYSIS = "AI_ANALYSIS"
    COMPARISON = "COMPARISON"


class DeviceContext(StrEnum):
    DESKTOP = "DESKTOP"
    MOBILE = "MOBILE"


class FindingDevice(StrEnum):
    DESKTOP = "DESKTOP"
    MOBILE = "MOBILE"
    BOTH = "BOTH"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class ArchitectureClassification(StrEnum):
    STATIC_OR_SSR = "STATIC_OR_SSR"
    HYDRATED = "HYDRATED"
    CSR_SPA = "CSR_SPA"
    MIXED = "MIXED"
    UNKNOWN = "UNKNOWN"


class RuleResult(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    WARNING = "WARNING"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    UNKNOWN = "UNKNOWN"
    ERROR = "ERROR"


class Severity(StrEnum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""

    return datetime.now(timezone.utc)


def new_id(prefix: str) -> str:
    """Generate a stable-format domain identifier such as ``AUD-<uuid>``."""

    return f"{prefix}-{uuid4().hex.upper()}"


@dataclass(slots=True)
class Audit:
    audit_id: str
    project_name: str
    status: AuditStatus = AuditStatus.CREATED
    completion_status: CompletionStatus | None = None
    primary_language: str = "pt-BR"
    market: str = "BR"
    max_pages: int = 100
    audit_mode: AuditMode | None = None
    capabilities: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()
    created_at: datetime = field(default_factory=utc_now)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    auditor_version: str = ""
    ruleset_version: str = ""

    def __post_init__(self) -> None:
        if self.max_pages <= 0:
            raise ValueError("max_pages must be greater than zero")


@dataclass(slots=True)
class AuditTarget:
    target_id: str
    audit_id: str
    input_url: str
    normalized_origin: str
    target_type: TargetType


@dataclass(slots=True)
class Page:
    page_id: str
    audit_id: str
    normalized_url: str
    discovered_url: str
    discovery_sources: tuple[DiscoverySource, ...] = ()
    depth: int = 0

    def __post_init__(self) -> None:
        if self.depth < 0:
            raise ValueError("depth must not be negative")


@dataclass(slots=True)
class PageSnapshot:
    snapshot_id: str
    page_id: str
    device: DeviceContext
    requested_url: str
    final_url: str | None
    captured_at: datetime
    http_status: int | None = None
    content_type: str | None = None
    title: str | None = None
    description: str | None = None
    canonical: str | None = None
    meta_robots: str | None = None
    rendering_mode: str | None = None
    raw_artifact_ref: str | None = None
    rendered_artifact_ref: str | None = None
    main_content_ref: str | None = None
    structured_data_ref: str | None = None
    browser_metadata: dict[str, Any] = field(default_factory=dict)
    architecture_classification: ArchitectureClassification = ArchitectureClassification.UNKNOWN


@dataclass(slots=True)
class Evidence:
    evidence_id: str
    audit_id: str
    page_id: str | None
    snapshot_id: str | None
    device: DeviceContext | None
    evidence_type: EvidenceType
    source: str
    observed_value: Any
    artifact_reference: str | None
    captured_at: datetime


@dataclass(slots=True)
class RuleExecution:
    rule_execution_id: str
    audit_id: str
    rule_id: str
    rule_version: str
    page_id: str | None
    snapshot_id: str | None
    device: DeviceContext | None
    result: RuleResult
    observed_value: Any
    expected_condition: str | None
    evidence_ids: tuple[str, ...]
    executed_at: datetime
    error: str | None = None


@dataclass(slots=True)
class Finding:
    finding_id: str
    audit_id: str
    rule_id: str
    rule_execution_id: str
    page_id: str | None
    device: FindingDevice
    category: str
    severity: Severity
    source: str
    title: str
    observed_value: Any
    expected_condition: str | None
    evidence_ids: tuple[str, ...]
    status: str

    def __post_init__(self) -> None:
        if not self.evidence_ids:
            raise ValueError("finding must reference at least one evidence")
