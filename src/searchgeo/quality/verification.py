"""Incremental fix verification across two persisted RASAi audits.

Verification is evidence-bound: it maps persisted rule-state changes and never
claims a fix when the current audit is unavailable or methodologically
incomparable.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from searchgeo.monitoring.compare import compare_audits


@dataclass(frozen=True, slots=True)
class VerificationItem:
    rule_id: str
    url: str | None
    device: str | None
    severity: str
    status: str
    before: Any
    after: Any
    reason: str


@dataclass(frozen=True, slots=True)
class VerificationBundle:
    baseline_audit_id: str
    current_audit_id: str
    items: tuple[VerificationItem, ...]
    counts: dict[str, int]
    limitations: tuple[str, ...]


def verify_fixes(
    baseline_workspace: str | Path,
    current_workspace: str | Path,
    *,
    url: str | None = None,
    rule_id: str | None = None,
) -> VerificationBundle:
    result = compare_audits(baseline_workspace, current_workspace)
    items: list[VerificationItem] = []
    for event in result.events:
        if event.domain != "RULE" or not event.rule_id:
            continue
        if url and event.url != url:
            continue
        if rule_id and event.rule_id != rule_id:
            continue
        before = str(event.before or "").upper()
        if before not in {"FAIL", "WARNING"}:
            continue
        if event.status == "RESOLVED":
            status = "FIXED"
            reason = "Baseline finding state reached PASS in the current audit."
        elif event.status == "IMPROVED":
            status = "PARTIALLY_FIXED"
            reason = "Rule state improved but has not been demonstrated as fully resolved."
        elif event.status in {"DATA_UNAVAILABLE", "NOT_COMPARABLE"}:
            status = "NOT_VERIFIABLE"
            reason = event.reason or "Current evidence is unavailable or not comparable."
        elif event.status == "UNCHANGED":
            status = "NOT_FIXED"
            reason = "The same FAIL/WARNING state remains in the current audit."
        elif event.status == "REGRESSED":
            status = "NOT_FIXED"
            reason = "The rule state degraded relative to the baseline."
        else:
            status = "NOT_VERIFIABLE"
            reason = event.reason or f"Rule transition {event.status} is not sufficient to assert a fix."
        items.append(
            VerificationItem(
                rule_id=event.rule_id,
                url=event.url,
                device=event.device,
                severity=event.severity,
                status=status,
                before=event.before,
                after=event.after,
                reason=reason,
            )
        )

    counts: dict[str, int] = {}
    for item in items:
        counts[item.status] = counts.get(item.status, 0) + 1
    limitations = list(result.compatibility_notes)
    if not items:
        limitations.append("No baseline FAIL/WARNING rule matched the requested verification scope.")
    limitations.append("Verification proves only the persisted rule transition between the two selected audits; it does not prove downstream Search/AI impact.")
    return VerificationBundle(
        baseline_audit_id=result.baseline.audit_id,
        current_audit_id=result.current.audit_id,
        items=tuple(items),
        counts=counts,
        limitations=tuple(limitations),
    )
