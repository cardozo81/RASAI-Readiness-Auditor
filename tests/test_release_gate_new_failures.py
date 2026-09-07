from __future__ import annotations

from pathlib import Path

from rasai.monitoring.compare import _compare_signal, evaluate_release_gate
from rasai.monitoring.models import AuditSnapshot, ComparisonResult, GatePolicy, Signal


def _snapshot(audit_id: str) -> AuditSnapshot:
    return AuditSnapshot(
        audit_id=audit_id,
        workspace=Path(audit_id),
        project_name="gate-test",
        event_time="2026-09-01T00:00:00+00:00",
        status="COMPLETED",
        completion_status="COMPLETE",
        auditor_version="test",
        ruleset_version="test",
        scoring_versions=("SCORE-GEO-003",),
        domains=("example.test",),
        devices=("MOBILE",),
        urls=("https://example.test/new",),
        signals={},
    )


def _result(*events) -> ComparisonResult:
    return ComparisonResult(
        baseline=_snapshot("AUD-BASE"),
        current=_snapshot("AUD-CURRENT"),
        comparable=True,
        compatibility_notes=(),
        events=tuple(events),
        counts={},
        material_counts={},
    )


def test_new_deterministic_fail_blocks_by_default_and_can_be_explicitly_allowed() -> None:
    signal = Signal(
        key="RULE|MOBILE|https://example.test/new|BR-GEO-001",
        domain="RULE",
        label="BR-GEO-001",
        value="FAIL",
        device="MOBILE",
        url="https://example.test/new",
        rule_id="BR-GEO-001",
        severity="CRITICAL",
        direction="RESULT",
    )
    event = _compare_signal(None, signal)
    assert event.status == "NEW"
    assert event.material is True

    strict = evaluate_release_gate(_result(event))
    assert strict.passed is False
    assert strict.blocking_events == (event,)

    opted_out = evaluate_release_gate(_result(event), GatePolicy(block_new_failures=False))
    assert opted_out.passed is True
    assert opted_out.blocking_events == ()


def test_new_bad_http_state_is_material_but_new_healthy_http_is_not() -> None:
    bad = Signal(
        key="PAGE|MOBILE|https://example.test/new|http_status",
        domain="PAGE",
        label="HTTP status",
        value=500,
        device="MOBILE",
        url="https://example.test/new",
        severity="HIGH",
        direction="STATE",
        metadata={"field": "http_status"},
    )
    healthy = Signal(
        key="PAGE|MOBILE|https://example.test/ok|http_status",
        domain="PAGE",
        label="HTTP status",
        value=200,
        device="MOBILE",
        url="https://example.test/ok",
        severity="HIGH",
        direction="STATE",
        metadata={"field": "http_status"},
    )
    bad_event = _compare_signal(None, bad)
    healthy_event = _compare_signal(None, healthy)
    assert bad_event.status == "NEW" and bad_event.material is True
    assert healthy_event.status == "NEW" and healthy_event.material is False
    assert evaluate_release_gate(_result(bad_event, healthy_event)).passed is False


def test_new_noindex_state_is_material() -> None:
    signal = Signal(
        key="PAGE|MOBILE|https://example.test/new|meta_robots",
        domain="PAGE",
        label="Meta robots",
        value="noindex,follow",
        device="MOBILE",
        url="https://example.test/new",
        severity="HIGH",
        direction="STATE",
        metadata={"field": "meta_robots"},
    )
    event = _compare_signal(None, signal)
    assert event.status == "NEW"
    assert event.material is True
    assert evaluate_release_gate(_result(event)).passed is False
