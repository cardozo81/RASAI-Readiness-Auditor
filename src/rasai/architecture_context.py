"""Conservative, read-only architectural context resolution.

This module does not alter collection, scoring or persisted evidence.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Architecture = Literal["STATIC_OR_SSR", "HYDRATED", "CSR_SPA", "MIXED", "UNKNOWN"]
Mode = Literal["AUTO", "DECLARED", "UNFORCED"]
Applicability = Literal["ADVISORY_SAFE", "INAPPLICABLE"]
CLASSES = frozenset({"STATIC_OR_SSR", "HYDRATED", "CSR_SPA", "MIXED", "UNKNOWN"})
CONTRACT_VERSION = "architecture-context-v1"


@dataclass(frozen=True)
class ArchitectureObservation:
    architecture: str
    requested_url: str
    device: str
    snapshot_id: str
    evidence_ref: str
    audit_id: str = ""
    page_id: str = ""
    final_url: str = ""


@dataclass(frozen=True)
class ArchitectureContext:
    observed_architecture: str
    declared_architecture: str | None
    selected_mode: str
    effective_architecture: str | None
    source: str
    consumer_id: str
    applicability: str
    abstention_reason: str | None
    discrepancy: bool
    evidence_ref: str | None
    contract_version: str = CONTRACT_VERSION


def resolve_architecture(
    *,
    mode: Mode,
    declared_architecture: str | None,
    observations: tuple[ArchitectureObservation, ...],
    requested_url: str,
    device: str,
    snapshot_id: str,
    consumer_id: str,
    audit_id: str = "",
    page_id: str = "",
    final_url: str = "",
    advisory_consumers: frozenset[str] = frozenset(),
    phase: Literal["PRE_COLLECTION", "POST_COLLECTION"] = "POST_COLLECTION",
) -> ArchitectureContext:
    """Resolve architecture only for allowlisted advisory consumers.

    Fail closed on missing/conflicting physical evidence. A declared choice
    never replaces measured facts; pre-collection AUTO does not infer from M6.
    """
    if mode not in {"AUTO", "DECLARED", "UNFORCED"}:
        raise ValueError("Unknown architecture mode")
    if declared_architecture is not None and declared_architecture not in CLASSES:
        raise ValueError("Unknown declared architecture")
    if mode == "DECLARED" and (declared_architecture is None or declared_architecture == "UNKNOWN"):
        raise ValueError("DECLARED requires a concrete architecture")
    if phase not in {"PRE_COLLECTION", "POST_COLLECTION"}:
        raise ValueError("Unknown execution phase")
    if not all(isinstance(x, str) and x.strip() for x in (requested_url, device, snapshot_id, consumer_id)):
        raise ValueError("Context identity must be nonempty")

    # Legacy observations without these optional identities may only serve an
    # equally legacy request. Never silently project across an explicitly scoped AUD.
    matches = tuple(o for o in observations if
                    o.requested_url == requested_url and
                    o.device == device and o.snapshot_id == snapshot_id and
                    o.audit_id == audit_id and o.page_id == page_id and
                    o.final_url == final_url)
    valid = (len(matches) == 1 and matches[0].architecture in CLASSES
             and isinstance(matches[0].evidence_ref, str) and bool(matches[0].evidence_ref.strip()))
    observed = matches[0].architecture if valid else "UNKNOWN"
    evidence = matches[0].evidence_ref if valid else None
    discrepancy = (mode == "DECLARED" and valid and observed != "UNKNOWN"
                   and observed != declared_architecture)
    eligible = consumer_id in advisory_consumers
    reason = None
    source = "UNFORCED"
    effective = None
    if not eligible:
        reason = "CONSUMER_NOT_APPROVED"
    elif mode == "UNFORCED":
        reason = "UNFORCED"
    elif mode == "DECLARED":
        effective = declared_architecture
        source = "USER_DECLARED"
    elif phase == "PRE_COLLECTION":
        reason = "OBSERVATION_NOT_AVAILABLE_BEFORE_COLLECTION"
    elif not valid:
        reason = "MISSING_CONFLICTING_OR_INVALID_EVIDENCE"
    elif observed == "UNKNOWN":
        reason = "UNKNOWN_OBSERVED_ARCHITECTURE"
    else:
        effective = observed
        source = "AUTO_DISCOVERY"

    return ArchitectureContext(
        observed_architecture=observed,
        declared_architecture=declared_architecture if mode == "DECLARED" else None,
        selected_mode=mode,
        effective_architecture=effective,
        source=source,
        consumer_id=consumer_id,
        applicability="ADVISORY_SAFE" if eligible else "INAPPLICABLE",
        abstention_reason=reason,
        discrepancy=bool(discrepancy),
        evidence_ref=evidence,
    )
