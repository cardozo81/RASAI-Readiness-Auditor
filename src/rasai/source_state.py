"""Canonical source/capability state used by reports and execution projections.

The contract deliberately separates configuration/request/execution/data semantics so a
source cannot be presented as "included" merely because a broader catalog was selected.
It is secret-free and carries only provenance/status metadata.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any


SOURCE_STATE_CONTRACT = "SOURCE-STATE-001"


@dataclass(frozen=True, slots=True)
class SourceState:
    source_id: str
    capability_available: bool
    configured: bool
    requested: bool
    enabled: bool
    executed: bool
    execution_status: str
    data_available: bool
    data_status: str
    freshness_mode: str = "NOT_APPLICABLE"
    captured_at: str | None = None
    source_audit_id: str | None = None
    reused: bool = False
    error_count: int = 0
    result_count: int = 0
    artifact_reference: str | None = None
    detail: str = ""

    def validate(self) -> "SourceState":
        if not self.source_id.strip():
            raise ValueError("source_id must not be empty")
        if self.error_count < 0 or self.result_count < 0:
            raise ValueError("source counts must be >= 0")
        if self.executed and not self.requested:
            # Background/system sources may be explicitly enabled without being a user
            # catalog request. In that case requested remains false only when detail says
            # the source is system-derived; report builders should normally set requested.
            if "system" not in self.detail.casefold() and "autom" not in self.detail.casefold():
                raise ValueError("executed user-facing source must be requested")
        if self.data_available and not self.executed:
            raise ValueError("data_available requires executed=true")
        if self.reused and self.freshness_mode != "REUSED_EVIDENCE":
            raise ValueError("reused source must use REUSED_EVIDENCE freshness_mode")
        if self.freshness_mode == "REUSED_EVIDENCE":
            if not self.reused:
                raise ValueError("REUSED_EVIDENCE requires reused=true")
            if not self.captured_at or not self.source_audit_id:
                raise ValueError("reused evidence requires captured_at and source_audit_id")
        if not self.executed and self.execution_status.upper() in {"SUCCESS", "COMPLETE", "COMPLETED"}:
            raise ValueError("non-executed source cannot have successful execution_status")
        return self

    def as_dict(self) -> dict[str, Any]:
        return {"contract": SOURCE_STATE_CONTRACT, **asdict(self)}


def not_requested(source_id: str, *, capability_available: bool = True, configured: bool = False, detail: str = "") -> SourceState:
    return SourceState(
        source_id=source_id,
        capability_available=capability_available,
        configured=configured,
        requested=False,
        enabled=False,
        executed=False,
        execution_status="NOT_REQUESTED",
        data_available=False,
        data_status="NO_DATA",
        detail=detail,
    ).validate()


__all__ = ["SOURCE_STATE_CONTRACT", "SourceState", "not_requested"]
