from __future__ import annotations

import time

from rasai.accepted_audit_refinements import (
    _deadline_candidate_call,
    _merge_recommendations,
    _repair_findings,
    _root_for_recommendation,
    _serp_completion_reason,
    _validate_partial_recommendations,
)
from rasai.m18_ai import AttemptStatus


class _FakeImprovement:
    @staticmethod
    def _validate_ai_payload(payload, findings, maximum):
        raw = payload["recommendations"][0]
        allowed = {item["finding_id"]: set(item["evidence_ids"]) for item in findings}
        finding_id = raw["finding_id"]
        if finding_id not in allowed:
            raise ValueError("unknown finding_id")
        if not set(raw.get("evidence_ids", [])).issubset(allowed[finding_id]):
            raise ValueError("evidence outside finding")
        return payload.get("summary", ""), [dict(raw)]


def test_partial_recommendations_preserve_valid_and_isolate_rejected() -> None:
    findings = [
        {"finding_id": "F-1", "evidence_ids": ["E-1"]},
        {"finding_id": "F-2", "evidence_ids": ["E-2"]},
    ]
    payload = {
        "summary": "análise parcial",
        "recommendations": [
            {"finding_id": "F-1", "evidence_ids": ["E-1"], "recommendation": "válida"},
            {"finding_id": "F-2", "evidence_ids": ["E-2", "E-FORA"], "recommendation": "rejeitada"},
        ],
    }

    summary, accepted, rejected = _validate_partial_recommendations(
        _FakeImprovement, payload, findings, 10
    )

    assert summary == "análise parcial"
    assert [item["finding_id"] for item in accepted] == ["F-1"]
    assert [item["finding_id"] for item in rejected] == ["F-2"]
    assert [item["finding_id"] for item in _repair_findings(findings, rejected)] == ["F-2"]
    assert [item["finding_id"] for item in _merge_recommendations(accepted, [{"finding_id": "F-2"}], 10)] == ["F-1", "F-2"]


def test_serp_reason_reports_provider_pagination_limit() -> None:
    observation = {
        "requested_depth": 20,
        "quality_metadata": '{"pagination_ended_before_requested_depth": true}',
    }
    assert _serp_completion_reason(observation, 8) == (
        "Provider encerrou a paginação antes da profundidade solicitada"
    )
    assert _serp_completion_reason({"requested_depth": 8, "quality_metadata": "{}"}, 8) == (
        "Profundidade solicitada atingida"
    )


def test_grouped_deterministic_recommendation_resolves_root_cause() -> None:
    root_by_find = {"F-1": {"finding_id": "F-1", "rule_id": "BR-GEO-017"}}
    group_by_id = {
        "RMG-1": {"group_id": "RMG-1", "affected_findings": '["F-1"]'}
    }

    root, finding_ids, group = _root_for_recommendation(
        {"remediation_group_id": "RMG-1"}, root_by_find, group_by_id
    )

    assert root["finding_id"] == "F-1"
    assert finding_ids == ["F-1"]
    assert group and group["group_id"] == "RMG-1"


def test_improvement_deadline_is_wall_clock_bounded() -> None:
    class Provider:
        name = "TEST"

    def slow_call(provider, *, body, timeout):
        time.sleep(0.20)
        return "late", None, None, AttemptStatus.SUCCESS, 200

    started = time.perf_counter()
    _raw, _usage, diagnostic, status, _duration = _deadline_candidate_call(
        Provider(), body=b"{}", timeout=0.04, candidate_call=slow_call
    )
    elapsed = time.perf_counter() - started

    assert elapsed < 0.15
    assert status is AttemptStatus.TECHNICAL_ERROR
    assert getattr(diagnostic, "error_code", None) == "IMPROVEMENT_WALL_CLOCK_TIMEOUT"
