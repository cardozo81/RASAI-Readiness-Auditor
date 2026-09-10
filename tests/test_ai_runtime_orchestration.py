"""Regression tests for execution-wide AI AUTO orchestration and audit logging."""
from __future__ import annotations

from datetime import datetime, timezone
import json
from types import SimpleNamespace

from rasai.ai_exchange_log import AiExchangeRecorder
from rasai.dynamic_ai_routing import AiExecutionCoordinator, DynamicProviderRoutingSession
from rasai.m18_ai import (
    AttemptStatus,
    ProviderAttempt,
    ProviderDiagnostic,
    ProviderErrorClass,
    ProviderState,
    RuntimeProviderState,
    SemanticProviderResult,
)
from rasai.provider_wire_schema import project_provider_request_body


def _attempt(
    provider: str,
    *,
    status: AttemptStatus,
    error_class: ProviderErrorClass | None = None,
    http_status: int | None = None,
) -> ProviderAttempt:
    now = datetime.now(timezone.utc)
    diagnostic = None
    if error_class is not None or http_status is not None:
        diagnostic = ProviderDiagnostic(error_class=error_class, http_status=http_status)
    return ProviderAttempt(
        provider=provider,
        model=f"{provider.lower()}-model",
        reasoning_profile="NONE",
        provider_rank=1,
        attempt_index=1,
        snapshot_id="S1",
        url="https://example.test/",
        started_at=now,
        finished_at=now,
        duration_ms=1,
        status=status,
        diagnostic=diagnostic,
    )


class _FakeProvider:
    def __init__(self, name: str, rank: int, outcomes: list[tuple[str, ProviderErrorClass | None, int | None]]) -> None:
        self.name = name
        self.model = f"{name.lower()}-model"
        self.reasoning_profile = "NONE"
        self.policy = SimpleNamespace(rank=rank, qualification="TEST")
        self._outcomes = list(outcomes)
        self._last = ()
        self._runtime_state = RuntimeProviderState.ACTIVE
        self.calls = 0

    def analyze(self, semantic_input, *, max_attempts: int = 1):
        assert max_attempts == 1
        self.calls += 1
        token, error_class, http_status = self._outcomes.pop(0) if self._outcomes else ("success", None, None)
        if token == "success":
            attempt = _attempt(self.name, status=AttemptStatus.SUCCESS)
            result = SemanticProviderResult(ProviderState.AVAILABLE, provider=self.name, model=self.model)
        else:
            attempt = _attempt(
                self.name,
                status=AttemptStatus.TECHNICAL_ERROR,
                error_class=error_class,
                http_status=http_status,
            )
            result = SemanticProviderResult(
                ProviderState.UNAVAILABLE,
                reason=attempt.diagnostic.reason if attempt.diagnostic else "AI_PROVIDER_UNAVAILABLE",
                provider=self.name,
                model=self.model,
                diagnostic=attempt.diagnostic,
            )
            self._runtime_state = RuntimeProviderState.QUARANTINED_FOR_AUDIT
        self._last = (attempt,)
        return result

    def consume_attempts(self):
        value = self._last
        self._last = ()
        return value


def test_auto_rotates_between_needs_and_falls_forward_on_temporary_error() -> None:
    a = _FakeProvider("A", 1, [("success", None, None), ("terminal", ProviderErrorClass.CREDIT_ERROR, 402)])
    b = _FakeProvider("B", 2, [("temporary", ProviderErrorClass.TIMEOUT_ERROR, None), ("success", None, None)])
    c = _FakeProvider("C", 3, [("success", None, None)])
    d = _FakeProvider("D", 4, [("success", None, None)])
    session = DynamicProviderRoutingSession((a, b, c, d))
    semantic_input = SimpleNamespace(page_url="https://example.test/")

    assert session.analyze(semantic_input).provider == "A"
    # Next need starts at B; B times out only for this attempt and C succeeds.
    assert session.analyze(semantic_input).provider == "C"
    assert session.coordinator.is_eligible("B") is True
    # Cursor advances after C, so D is next instead of starting at A again.
    assert session.analyze(semantic_input).provider == "D"
    # A then returns a terminal credit error. B remains eligible and is the fallback.
    assert session.analyze(semantic_input).provider == "B"
    assert session.coordinator.is_eligible("A") is False
    assert session.coordinator.health_snapshot()["A"]["exclusion_reason"].startswith("TERMINAL:CREDIT_ERROR")
    assert [a.calls, b.calls, c.calls, d.calls] == [2, 2, 1, 1]


def test_temporary_circuit_breaker_opens_on_three_failures_within_five_observations() -> None:
    coordinator = AiExecutionCoordinator(("A",))
    sequence = [
        AttemptStatus.TECHNICAL_ERROR,
        AttemptStatus.SUCCESS,
        AttemptStatus.TECHNICAL_ERROR,
        AttemptStatus.SUCCESS,
        AttemptStatus.TECHNICAL_ERROR,
    ]
    for status in sequence:
        coordinator.record_attempt(
            _attempt(
                "A",
                status=status,
                error_class=ProviderErrorClass.TIMEOUT_ERROR if status is not AttemptStatus.SUCCESS else None,
            )
        )
    health = coordinator.health_snapshot()["A"]
    assert health["rolling_observations"] == 5
    assert health["rolling_failures"] == 3
    assert health["eligible"] is False
    assert health["exclusion_reason"] == "CIRCUIT_BREAKER:3_FAILURES_IN_LAST_5"


def test_http_404_removes_provider_immediately() -> None:
    coordinator = AiExecutionCoordinator(("A", "B"))
    coordinator.record_attempt(
        _attempt(
            "A",
            status=AttemptStatus.TECHNICAL_ERROR,
            error_class=ProviderErrorClass.UNKNOWN_PROVIDER_ERROR,
            http_status=404,
        )
    )
    assert coordinator.is_eligible("A") is False
    assert coordinator.ordered_names() == ("B",)


def test_one_need_never_loops_over_same_provider() -> None:
    providers = tuple(
        _FakeProvider(name, rank, [("temporary", ProviderErrorClass.NETWORK_ERROR, None)])
        for rank, name in enumerate(("A", "B", "C"), 1)
    )
    session = DynamicProviderRoutingSession(providers)
    result = session.analyze(SimpleNamespace(page_url="https://example.test/"))
    assert result.state is ProviderState.UNAVAILABLE
    assert [provider.calls for provider in providers] == [1, 1, 1]
    assert len(session.consume_attempts()) == 3


def _context_interpretation() -> dict[str, object]:
    interpreted = {
        "status": "INTERPRETED",
        "value": "ymyl",
        "confidence": 0.91,
        "rationale": "Conteúdo trata decisão financeira relevante.",
        "evidence_ids": ["EV-1"],
    }
    not_determinable = {
        "status": "NOT_DETERMINABLE",
        "value": None,
        "confidence": 0.0,
        "rationale": "Evidência insuficiente.",
        "evidence_ids": [],
    }
    return {
        "risk_profile": interpreted,
        "ymyl_category": {
            **interpreted,
            "value": "financial-security",
        },
        "page_purpose": {**interpreted, "value": "informational"},
        "intended_audience": {**interpreted, "value": "general"},
        "experience_requirement": {**interpreted, "value": "beneficial"},
        "freshness_sensitivity": {**interpreted, "value": "high"},
        "content_origin": not_determinable,
    }


def test_exchange_log_redacts_secrets_private_reasoning_and_transient_context() -> None:
    recorder = AiExchangeRecorder(max_capture_bytes=4096)
    request = {
        "api_key": "do-not-store",
        "input": {
            "snapshot_id": "S1",
            "page_url": "https://example.test/",
            "evidence": [{"evidence_id": "EV-1", "observed_value": "conteúdo"}],
        },
    }
    response = {
        "authorization": "Bearer secret",
        "reasoning_content": "private chain",
        "output": {
            "content_context_interpretation": _context_interpretation(),
            "answer": "ok",
        },
    }
    recorder.append_exchange(
        provider="OPENAI",
        model="test-model",
        endpoint="https://example.test/v1/responses?key=secret-value&x=1",
        body=json.dumps(request).encode("utf-8"),
        started_at=datetime.now(timezone.utc),
        duration_ms=4,
        outcome="RESPONSE",
        response=response,
    )

    assert len(recorder.exchanges) == 1
    exchange = recorder.exchanges[0]
    assert "do-not-store" not in exchange.request_payload
    assert "[REDACTED]" in exchange.request_payload
    assert "secret-value" not in exchange.endpoint
    assert "private chain" not in (exchange.response_payload or "")
    assert "Bearer secret" not in (exchange.response_payload or "")
    assert "financial-security" not in (exchange.response_payload or "")
    assert "INTERPRETACAO_AUTO_EXIBIDA_NO_RELATORIO_NAO_PERSISTIDA" in (exchange.response_payload or "")
    assert len(recorder.context_interpretations) == 1
    transient = recorder.context_interpretations[0]
    assert transient.fields["ymyl_category"]["value"] == "financial-security"
    assert transient.fields["risk_profile"]["confidence"] == 0.91


def test_openai_wire_projection_removes_unsupported_constraints_only_from_schema() -> None:
    payload = {
        "model": "test",
        "input": [{"schema": {"minimum": "page-data-must-not-be-rewritten"}}],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "fixture",
                "strict": True,
                "schema": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "name": {"type": "string", "minLength": 1, "maxLength": 100},
                        "items": {
                            "type": "array",
                            "minItems": 1,
                            "maxItems": 3,
                            "uniqueItems": True,
                            "items": {"type": "string"},
                        },
                        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    },
                    "required": ["name", "items", "confidence"],
                },
            }
        },
    }
    projected = json.loads(project_provider_request_body("OPENAI", json.dumps(payload).encode()).decode())
    schema = projected["text"]["format"]["schema"]
    assert schema["required"] == ["name", "items", "confidence"]
    assert schema["additionalProperties"] is False
    assert "minLength" not in schema["properties"]["name"]
    assert "maxLength" not in schema["properties"]["name"]
    assert "minItems" not in schema["properties"]["items"]
    assert "maxItems" not in schema["properties"]["items"]
    assert "uniqueItems" not in schema["properties"]["items"]
    assert "minimum" not in schema["properties"]["confidence"]
    assert "maximum" not in schema["properties"]["confidence"]
    assert projected["input"][0]["schema"]["minimum"] == "page-data-must-not-be-rewritten"


def test_non_openai_wire_body_is_byte_identical() -> None:
    body = b'{"text":{"format":{"schema":{"type":"string","minLength":1}}}}'
    assert project_provider_request_body("GEMINI", body) is body
