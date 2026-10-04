from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from rasai.ai_canonical_orchestration import AiExecutionPolicy
from rasai.m18_ai import AttemptStatus, ProviderAttempt
from rasai import request_remediation_intelligence as remediation


class _Provider:
    def __init__(self, name: str) -> None:
        self.name = name
        self.model = f"{name.lower()}-model"
        self.api_key = "test"
        self.policy = SimpleNamespace(rank=1, qualification="TEST")


def _solution(group_id: str) -> dict[str, object]:
    return {
        "group_id": group_id,
        "title": f"Fix {group_id}",
        "solution": f"Apply fix for {group_id}",
        "technical_detail": "Inspect the observed request/runtime evidence.",
        "example": "",
        "verification": "Repeat the deterministic check.",
        "confidence": 0.9,
        "effort": "LOW",
    }


def _attempt(provider, *, index: int, started, status, diagnostic, usage, **_kwargs):
    finished = datetime.now(timezone.utc)
    return ProviderAttempt(
        provider=provider.name,
        model=provider.model,
        reasoning_profile="NONE",
        provider_rank=1,
        attempt_index=index,
        snapshot_id="SNP-1",
        url="https://example.test/",
        started_at=started,
        finished_at=finished,
        duration_ms=1,
        status=status,
        diagnostic=diagnostic,
        usage=usage,
    )


def test_request_remediation_partial_moves_to_next_provider_without_private_repair(
    monkeypatch,
) -> None:
    from rasai import accepted_audit_refinements as accepted
    from rasai import ai_orchestration_unification as orchestration
    from rasai import improvement_exchange_capture as capture
    from rasai import improvement_intelligence as improvement

    providers = (_Provider("A"), _Provider("B"))
    runtime = SimpleNamespace(
        _rasai_execution_policy=AiExecutionPolicy(
            max_cycles=3,
            cycle_delay_seconds=0,
        ),
        _rasai_cycle_sleeper=lambda _seconds: None,
    )
    calls: list[str] = []

    monkeypatch.setattr(improvement, "_build_provider", lambda _config: runtime)
    monkeypatch.setattr(
        orchestration,
        "_provider_candidates",
        lambda _runtime, _hint, *, scope: providers,
    )
    monkeypatch.setattr(orchestration, "_structured_payload", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(orchestration, "_provider_extract", lambda _provider, raw: raw)
    monkeypatch.setattr(orchestration, "_attempt", _attempt)
    monkeypatch.setattr(orchestration, "record_canonical_attempt", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(improvement, "_persist_attempt", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(capture, "_persist_state", lambda _state: None)

    def fake_deadline(provider, *, body, timeout, candidate_call):
        calls.append(provider.name)
        payload = {
            "solutions": [
                _solution("G-1" if provider.name == "A" else "G-2")
            ]
        }
        return payload, None, None, AttemptStatus.SUCCESS, 1

    monkeypatch.setattr(accepted, "_deadline_candidate_call", fake_deadline)

    groups = [
        {
            "group_id": "G-1",
            "title": "Group 1",
            "evidence_fingerprint": "FP-1",
        },
        {
            "group_id": "G-2",
            "title": "Group 2",
            "evidence_fingerprint": "FP-2",
        },
    ]

    solutions, missing, provider, model, reason = remediation._call_ai_batch(
        audit_id="AUD-1",
        workspace=SimpleNamespace(),
        context=SimpleNamespace(
            url="https://example.test/",
            snapshot_id="SNP-1",
        ),
        config=SimpleNamespace(timeout_seconds=180),
        groups=groups,
        timeout=180,
    )

    assert calls == ["A", "B"]
    assert missing == []
    assert reason is None
    assert set(solutions) == {"G-1", "G-2"}
    assert solutions["G-1"]["_provider"] == "A"
    assert solutions["G-2"]["_provider"] == "B"
    assert provider == "B"
    assert model == "b-model"
