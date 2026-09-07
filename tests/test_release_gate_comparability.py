from __future__ import annotations

from pathlib import Path

from searchgeo.monitoring.compare import evaluate_release_gate
from searchgeo.monitoring.models import AuditSnapshot, ComparisonResult, GatePolicy


def _snapshot(audit_id: str, domain: str) -> AuditSnapshot:
    return AuditSnapshot(
        audit_id=audit_id,
        workspace=Path(audit_id),
        project_name="gate-comparability",
        event_time="2026-09-01T00:00:00+00:00",
        status="COMPLETED",
        completion_status="COMPLETE",
        auditor_version="test",
        ruleset_version="test",
        scoring_versions=("SCORE-GEO-003",),
        domains=(domain,),
        devices=("MOBILE",),
        urls=(f"https://{domain}/",),
        signals={},
    )


def test_release_gate_fails_closed_when_pair_is_not_comparable() -> None:
    result = ComparisonResult(
        baseline=_snapshot("AUD-A", "a.example"),
        current=_snapshot("AUD-B", "b.example"),
        comparable=False,
        compatibility_notes=("domain set differs",),
        events=(),
        counts={},
        material_counts={},
    )
    gate = evaluate_release_gate(result)
    assert gate.passed is False
    assert gate.blocking_events == ()
    assert "not comparable" in gate.reason
    assert "domain set differs" in gate.reason


def test_release_gate_noncomparable_override_is_explicit() -> None:
    result = ComparisonResult(
        baseline=_snapshot("AUD-A", "a.example"),
        current=_snapshot("AUD-B", "b.example"),
        comparable=False,
        compatibility_notes=("domain set differs",),
        events=(),
        counts={},
        material_counts={},
    )
    gate = evaluate_release_gate(result, GatePolicy(require_comparable=False))
    assert gate.passed is True
    assert "noncomparable-allowed" in gate.reason
