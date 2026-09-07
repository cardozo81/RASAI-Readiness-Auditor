"""Milestone and before/after deployment resolution for RASAI."""
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Iterable

from searchgeo.monitoring.compare import compare_audits, evaluate_release_gate
from searchgeo.monitoring.models import ComparisonResult, GatePolicy, GateResult

from .models import AuditIndexRecord, DeploymentPair, Milestone
from .store import PlatformStore


def _instant(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        local_tz = datetime.now().astimezone().tzinfo or UTC
        parsed = parsed.replace(tzinfo=local_tz)
    return parsed.astimezone(UTC)


def _before_after(
    audits: Iterable[AuditIndexRecord], occurred_at: str
) -> tuple[list[AuditIndexRecord], list[AuditIndexRecord]]:
    marker = _instant(occurred_at)
    before = sorted(
        (item for item in audits if _instant(item.event_time) < marker),
        key=lambda item: _instant(item.event_time),
        reverse=True,
    )
    after = sorted(
        (item for item in audits if _instant(item.event_time) >= marker),
        key=lambda item: _instant(item.event_time),
    )
    return before, after


def _comparison(baseline: AuditIndexRecord, current: AuditIndexRecord) -> ComparisonResult:
    return compare_audits(Path(baseline.workspace_path), Path(current.workspace_path))


def _belongs_to_scope(
    store: PlatformStore,
    audit: AuditIndexRecord,
    property_id: str,
    environment_id: str,
) -> bool:
    checker = getattr(store, "audit_belongs_to_scope", None)
    if callable(checker):
        return bool(checker(audit.audit_id, property_id, environment_id))
    return audit.property_id == property_id and audit.environment_id == environment_id


def resolve_deployment_pair(
    store: PlatformStore,
    milestone: str | Milestone,
    *,
    baseline_mode: str = "AUTO",
    baseline_audit_id: str | None = None,
    current_audit_id: str | None = None,
) -> DeploymentPair:
    """Resolve a technically comparable before/after pair around a milestone.

    AUTO searches the closest prior/posterior pair that ``compare_audits`` marks
    comparable. GOLDEN uses the approved baseline and the first compatible
    post-milestone audit. EXPLICIT requires caller-provided IDs. Canonical stores
    evaluate membership against all property/environment links of multi-domain
    audits rather than only the legacy primary property.
    """
    item = store.get_milestone(milestone) if isinstance(milestone, str) else milestone
    if item is None:
        raise KeyError(f"milestone not found: {milestone}")
    audits = store.list_audits(property_id=item.property_id, environment_id=item.environment_id)
    before, after = _before_after(audits, item.occurred_at)
    mode = baseline_mode.strip().upper()

    if current_audit_id:
        current = store.get_audit(current_audit_id)
        if current is None:
            raise KeyError(f"current audit not indexed: {current_audit_id}")
        if not _belongs_to_scope(store, current, item.property_id, item.environment_id):
            raise ValueError("current audit does not belong to milestone property/environment")
        after = [current]

    if mode == "EXPLICIT":
        if not baseline_audit_id or not current_audit_id:
            raise ValueError("EXPLICIT baseline mode requires baseline_audit_id and current_audit_id")
        baseline = store.get_audit(baseline_audit_id)
        current = store.get_audit(current_audit_id)
        if baseline is None or current is None:
            raise KeyError("explicit baseline/current audit must both be indexed")
        if not _belongs_to_scope(store, baseline, item.property_id, item.environment_id) or not _belongs_to_scope(
            store, current, item.property_id, item.environment_id
        ):
            raise ValueError("explicit audit pair must belong to milestone property/environment")
        comparison = _comparison(baseline, current)
        return DeploymentPair(
            item,
            baseline.audit_id,
            current.audit_id,
            "explicit baseline",
            "explicit current",
            comparison.comparable,
            comparison.compatibility_notes,
        )

    if mode == "GOLDEN":
        golden_id = baseline_audit_id or store.get_golden_baseline(item.property_id, item.environment_id)
        if golden_id is None:
            return DeploymentPair(
                item,
                None,
                after[0].audit_id if after else None,
                "golden baseline not set",
                "first post-milestone audit" if after else "no post-milestone audit",
                None,
            )
        golden = store.get_audit(golden_id)
        if golden is None:
            raise KeyError(f"golden baseline is not indexed: {golden_id}")
        if not _belongs_to_scope(store, golden, item.property_id, item.environment_id):
            raise ValueError("golden baseline does not belong to milestone property/environment")
        for candidate in after:
            comparison = _comparison(golden, candidate)
            if comparison.comparable:
                return DeploymentPair(
                    item,
                    golden.audit_id,
                    candidate.audit_id,
                    "golden baseline",
                    "first comparable post-milestone audit",
                    True,
                    comparison.compatibility_notes,
                )
        if after:
            comparison = _comparison(golden, after[0])
            return DeploymentPair(
                item,
                golden.audit_id,
                after[0].audit_id,
                "golden baseline",
                "no comparable post-milestone audit; nearest retained for diagnosis",
                comparison.comparable,
                comparison.compatibility_notes,
            )
        return DeploymentPair(item, golden.audit_id, None, "golden baseline", "no post-milestone audit", None)

    if mode != "AUTO":
        raise ValueError(f"unsupported baseline mode: {baseline_mode}")

    if baseline_audit_id:
        explicit_baseline = store.get_audit(baseline_audit_id)
        if explicit_baseline is None:
            raise KeyError(f"baseline audit not indexed: {baseline_audit_id}")
        if not _belongs_to_scope(store, explicit_baseline, item.property_id, item.environment_id):
            raise ValueError("baseline audit does not belong to milestone property/environment")
        before = [explicit_baseline]

    for current in after:
        for baseline in before:
            comparison = _comparison(baseline, current)
            if comparison.comparable:
                return DeploymentPair(
                    item,
                    baseline.audit_id,
                    current.audit_id,
                    "last comparable pre-milestone audit",
                    "first comparable post-milestone audit",
                    True,
                    comparison.compatibility_notes,
                )

    nearest_before = before[0] if before else None
    nearest_after = after[0] if after else None
    notes: tuple[str, ...] = ()
    comparable: bool | None = None
    if nearest_before and nearest_after:
        comparison = _comparison(nearest_before, nearest_after)
        comparable = comparison.comparable
        notes = comparison.compatibility_notes
    return DeploymentPair(
        item,
        nearest_before.audit_id if nearest_before else None,
        nearest_after.audit_id if nearest_after else None,
        "nearest pre-milestone audit" if nearest_before else "no pre-milestone audit",
        "nearest post-milestone audit" if nearest_after else "no post-milestone audit",
        comparable,
        notes,
    )


def compare_deployment_pair(
    store: PlatformStore,
    pair: DeploymentPair,
    *,
    gate_policy: GatePolicy | None = None,
) -> tuple[ComparisonResult, GateResult]:
    if pair.baseline_audit_id is None or pair.current_audit_id is None:
        raise ValueError("deployment pair is incomplete; both baseline and current audits are required")
    baseline = store.get_audit(pair.baseline_audit_id)
    current = store.get_audit(pair.current_audit_id)
    if baseline is None or current is None:
        raise KeyError("deployment pair references audit(s) missing from platform index")
    result = _comparison(baseline, current)
    return result, evaluate_release_gate(result, gate_policy)
