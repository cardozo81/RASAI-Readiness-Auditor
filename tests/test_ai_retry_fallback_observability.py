from __future__ import annotations

import io
import json
from email.message import Message
import unittest
from urllib.error import HTTPError

from rasai.ai_canonical_orchestration import AiExecutionPolicy
from rasai.ai_resilience import retry_policy
from rasai.m18_ai import (
    DeepSeekProvider,
    MiMoProvider,
    OpenAIProvider,
    ProviderErrorClass,
    ProviderRoutingSession,
    ProviderState,
    SEMANTIC_RULE_IDS,
)
from rasai.semantic import SemanticEvidenceInput, SemanticInput


def semantic_input() -> SemanticInput:
    return SemanticInput(
        snapshot_id="SNP-R",
        page_url="https://example.com/",
        title="Example",
        main_content="Evidence",
        structured_data=None,
        primary_language="pt-BR",
        market="BR",
        evidence=(SemanticEvidenceInput("EVD-1", "TEXT_EXCERPT", "test", {"text": "Evidence"}),),
    )


def payload() -> dict[str, object]:
    return {
        "assessments": [
            {
                "rule_id": rule_id,
                "result": "UNKNOWN",
                "confidence": 0.0,
                "evidence_ids": [],
                "reasoning_summary": "fixture",
                "observed_value": {"summary": "", "details": []},
            }
            for rule_id in SEMANTIC_RULE_IDS
        ],
        "entities": [],
        "primary_intent": None,
        "secondary_intents": [],
    }


def success(*_):
    return {"output_text": json.dumps(payload())}


def http_error(status: int, error_type: str, code: str, retry_after: str | None = None) -> HTTPError:
    headers = Message()
    headers["x-request-id"] = "req-123"
    if retry_after is not None:
        headers["Retry-After"] = retry_after
    body = io.BytesIO(json.dumps({"error": {"type": error_type, "code": code}}).encode())
    return HTTPError("https://provider.invalid", status, "error", headers, body)


class AiRetryFallbackTests(unittest.TestCase):
    def test_provider_adapter_is_single_attempt_on_timeout(self) -> None:
        calls = 0
        def transport(*args):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise TimeoutError()
            return success(*args)

        provider = OpenAIProvider(api_key="x", transport=transport)
        result = provider.analyze(semantic_input())

        self.assertEqual(result.state, ProviderState.UNAVAILABLE)
        self.assertEqual(calls, 1)
        attempts = provider.consume_attempts()
        self.assertEqual(len(attempts), 1)
        self.assertEqual(attempts[0].decision, "STOP")
        self.assertFalse(attempts[0].retry_eligible)

    def test_explicit_single_provider_retries_only_in_next_canonical_cycle(self) -> None:
        calls = 0
        def transport(*args):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise TimeoutError()
            return success(*args)

        provider = OpenAIProvider(api_key="x", transport=transport)
        router = ProviderRoutingSession((provider,))
        router._rasai_execution_policy = AiExecutionPolicy(
            max_cycles=3,
            cycle_delay_seconds=60,
        )
        sleeps: list[float] = []
        router._rasai_cycle_sleeper = sleeps.append

        result = router.analyze(semantic_input())

        self.assertEqual(result.state, ProviderState.AVAILABLE)
        self.assertEqual(calls, 2)
        self.assertEqual(sleeps, [60])
        self.assertEqual(len(router.consume_attempts()), 2)

    def test_contract_error_is_never_retried(self) -> None:
        calls = 0
        def invalid(*_):
            nonlocal calls
            calls += 1
            return {"output_text": "{bad-json"}
        provider = OpenAIProvider(api_key="x", transport=invalid)
        result = provider.analyze(semantic_input())
        self.assertEqual(result.state, ProviderState.UNAVAILABLE)
        self.assertEqual(calls, 1)
        attempts = provider.consume_attempts()
        self.assertEqual(len(attempts), 1)
        self.assertFalse(attempts[0].retry_eligible)
        self.assertEqual(attempts[0].decision, "STOP")

    def test_retry_after_is_classified_for_orchestrator_but_adapter_does_not_retry(self) -> None:
        calls = 0
        def limited(*_):
            nonlocal calls
            calls += 1
            raise http_error(429, "rate_limit", "rate_limit", "120")

        provider = OpenAIProvider(api_key="x", transport=limited)
        result = provider.analyze(semantic_input())

        self.assertEqual(result.diagnostic.error_class, ProviderErrorClass.RATE_LIMIT_ERROR)
        self.assertEqual(calls, 1)
        self.assertEqual(result.diagnostic.retry_after_seconds, 120.0)
        policy = retry_policy(
            result.diagnostic.error_class,
            result.diagnostic.retry_after_seconds,
        )
        self.assertTrue(policy.eligible)
        self.assertEqual(policy.delay_seconds, 120.0)
        self.assertFalse(provider.consume_attempts()[0].retry_eligible)

    def test_auto_declares_fallback_source_reason_and_success(self) -> None:
        def primary(*_):
            raise http_error(401, "invalid_api_key", "invalid_api_key")
        router = ProviderRoutingSession((
            OpenAIProvider(api_key="x", transport=primary),
            DeepSeekProvider(api_key="x", transport=success),
            MiMoProvider(api_key="x", transport=success),
        ))
        result = router.analyze(semantic_input())
        self.assertEqual(result.provider, "DEEPSEEK")
        attempts = router.consume_attempts()
        self.assertEqual(len(attempts), 2)
        self.assertEqual(attempts[0].decision, "FALLBACK")
        self.assertEqual(attempts[1].decision, "FALLBACK_SUCCESS")
        self.assertEqual(attempts[1].fallback_from_provider, "OPENAI")
        self.assertIn("AUTH_ERROR", attempts[1].fallback_reason or "")

    def test_legacy_router_uses_same_three_cycle_budget_without_hidden_retry(self) -> None:
        calls = 0
        def timeout(*_):
            nonlocal calls
            calls += 1
            raise TimeoutError()

        router = ProviderRoutingSession((
            OpenAIProvider(api_key="x", transport=timeout),
            DeepSeekProvider(api_key="x", transport=timeout),
            MiMoProvider(api_key="x", transport=timeout),
        ))
        router._rasai_execution_policy = AiExecutionPolicy(
            max_cycles=3,
            cycle_delay_seconds=60,
        )
        sleeps: list[float] = []
        router._rasai_cycle_sleeper = sleeps.append

        result = router.analyze(semantic_input())

        self.assertEqual(result.state, ProviderState.UNAVAILABLE)
        self.assertEqual(calls, 9)
        self.assertEqual(len(router.consume_attempts()), calls)
        self.assertEqual(sleeps, [60, 60])

    def test_policy_contract_and_auth_are_non_retryable(self) -> None:
        self.assertFalse(retry_policy("CONTRACT_ERROR").eligible)
        self.assertFalse(retry_policy("AUTH_ERROR").eligible)
        self.assertTrue(retry_policy("TIMEOUT_ERROR").eligible)


if __name__ == "__main__":
    unittest.main()
