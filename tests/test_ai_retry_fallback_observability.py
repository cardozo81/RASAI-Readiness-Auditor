from __future__ import annotations

import io
import json
from email.message import Message
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from rasai.ai_resilience import MAX_AUTO_ATTEMPTS_PER_CONTEXT, retry_policy
from rasai.m18_ai import (
    DeepSeekProvider,
    MiMoProvider,
    OpenAIProvider,
    ProviderErrorClass,
    ProviderRoutingSession,
    ProviderState,
    SEMANTIC_RULE_IDS,
)
from rasai.m18_reporting import _attempt_row, _failover_summary
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
    def test_timeout_retries_once_then_succeeds(self) -> None:
        calls = 0
        def transport(*args):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise TimeoutError()
            return success(*args)
        provider = OpenAIProvider(api_key="x", transport=transport)
        with patch("rasai.m18_ai.time.sleep", return_value=None):
            result = provider.analyze(semantic_input())
        self.assertEqual(result.state, ProviderState.AVAILABLE)
        self.assertEqual(calls, 2)
        attempts = provider.consume_attempts()
        self.assertEqual([item.decision for item in attempts], ["RETRY", "SUCCESS_AFTER_RETRY"])
        self.assertTrue(attempts[0].retry_eligible)

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

    def test_retry_after_above_cap_stops_without_second_paid_call(self) -> None:
        calls = 0
        def limited(*_):
            nonlocal calls
            calls += 1
            raise http_error(429, "rate_limit", "rate_limit", "120")
        provider = OpenAIProvider(api_key="x", transport=limited)
        result = provider.analyze(semantic_input())
        self.assertEqual(result.diagnostic.error_class, ProviderErrorClass.RATE_LIMIT_ERROR)
        self.assertEqual(calls, 1)
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

    def test_legacy_auto_router_is_bounded_even_when_every_provider_times_out(self) -> None:
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
        with patch("rasai.m18_ai.time.sleep", return_value=None):
            result = router.analyze(semantic_input())
        self.assertEqual(result.state, ProviderState.UNAVAILABLE)
        # This legacy router retries each concrete provider once, therefore six
        # calls are sufficient and the historical eight-call global ceiling is
        # only an upper bound. Public AI=auto uses DynamicProviderRoutingSession.
        self.assertEqual(calls, 6)
        self.assertLessEqual(calls, MAX_AUTO_ATTEMPTS_PER_CONTEXT)
        self.assertEqual(len(router.consume_attempts()), calls)

    def test_report_row_exposes_diagnostic_and_fallback(self) -> None:
        row = {
            "url": "https://example.com/", "device": "MOBILE", "semantic_contract_version": "M18-SEMANTIC-22-v1",
            "attempt_index": 2, "provider": "DEEPSEEK", "model": "deepseek-v4-pro", "status": "SUCCESS",
            "error_class": None, "error_type": None, "http_status": None, "error_code": None, "request_id": None,
            "retry_eligible": 0, "decision": "FALLBACK_SUCCESS", "fallback_from_provider": "OPENAI",
            "fallback_reason": "AI_PROVIDER_UNAVAILABLE:AUTH_ERROR:HTTP_401", "input_tokens": 10, "output_tokens": 5,
            "estimated_cost": 0.001, "cost_currency": "USD", "duration_ms": 12,
        }
        html = _attempt_row(row)
        self.assertIn("FALLBACK_SUCCESS", html)
        self.assertIn("OPENAI", html)
        summary = _failover_summary([row])
        self.assertIn("deveria atender", summary)
        self.assertIn("AUTH_ERROR", summary)

    def test_policy_contract_and_auth_are_non_retryable(self) -> None:
        self.assertFalse(retry_policy("CONTRACT_ERROR").eligible)
        self.assertFalse(retry_policy("AUTH_ERROR").eligible)
        self.assertTrue(retry_policy("TIMEOUT_ERROR").eligible)


if __name__ == "__main__":
    unittest.main()
